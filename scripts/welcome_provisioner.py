#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新人首通入職歡迎郵件包派發系統 (Mailbox Onboarding Provisioner)
支援雙重觸發 (Sieve 遞送 / Post-login 登入)、原子防重複鎖、憑證類型偵測、四語系 (zh-TW, zh-CN, en, vi) 自動判定與網管運維通報
"""

import os
import sys
import argparse
import email
from email.header import decode_header
from datetime import datetime
import subprocess
import glob
import re

SYSTEM_ACCOUNTS = {
    "postmaster", "abuse", "root", "mailer-daemon", "vmail",
    "spam", "amavis", "clamav", "rspamd", "dmarc", "nobody"
}

SUPPORTED_LANGUAGES = ["zh-TW", "zh-CN", "en", "vi"]


def parse_args():
    parser = argparse.ArgumentParser(description="Dovecot Mailbox Onboarding Welcome Pack Provisioner")
    parser.add_argument("--event", default="delivery", choices=["delivery", "imap_login", "manual"],
                        help="Triggering event type")
    parser.add_argument("--recipient", default="", help="Target recipient email or username")
    parser.add_argument("--home-dir", default="", help="Custom home directory for the user")
    parser.add_argument("--templates-dir", default="", help="Path to welcome templates directory")
    parser.add_argument("--cert-path", default="", help="Path to server SSL certificate")
    parser.add_argument("--lang", default="", help="Explicitly specify user language (zh-TW, zh-CN, en, vi)")
    return parser.parse_args()


def decode_str(header_val):
    if not header_val:
        return ""
    decoded_fragments = decode_header(header_val)
    parts = []
    for content, charset in decoded_fragments:
        if isinstance(content, bytes):
            try:
                parts.append(content.decode(charset or "utf-8", errors="ignore"))
            except Exception:
                parts.append(content.decode("utf-8", errors="ignore"))
        else:
            parts.append(str(content))
    return "".join(parts).strip()


def extract_recipient_from_stdin():
    try:
        raw_bytes = sys.stdin.buffer.read()
        if not raw_bytes:
            return "", None
        msg = email.message_from_bytes(raw_bytes)
        for h in ["Delivered-To", "X-Original-To", "To"]:
            val = decode_str(msg.get(h, ""))
            if val:
                match = re.search(r'[\w\.-]+@[\w\.-]+', val)
                if match:
                    return match.group(0), msg
                return val.strip("<> "), msg
        return "", msg
    except Exception:
        pass
    return "", None


def get_host_name(domain=""):
    """
    動態多層解析郵件主機名稱 (優先序: 環境變數 -> /etc/postfix/main.cf -> /etc/mailname -> fallback)
    """
    h = os.getenv("HOST_NAME")
    if h and h.strip() and h.strip() != "HOST_NAME":
        return h.strip()

    if os.path.exists("/etc/postfix/main.cf"):
        try:
            with open("/etc/postfix/main.cf", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("myhostname") and "=" in line:
                        val = line.split("=", 1)[1].strip()
                        if val and val != "HOST_NAME" and not val.startswith("$"):
                            return val
        except Exception:
            pass

    if os.path.exists("/etc/mailname"):
        try:
            with open("/etc/mailname", "r", encoding="utf-8", errors="ignore") as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass

    if domain:
        return f"mail.{domain}"

    try:
        import socket
        fqdn = socket.getfqdn()
        if fqdn and fqdn != "localhost":
            return fqdn
    except Exception:
        pass

    return "mail.example.com"


def normalize_language(lang_code):
    if not lang_code:
        return ""
    code = lang_code.strip().lower().replace("_", "-")
    if code.startswith("zh-tw") or code.startswith("zh-hant") or code == "tw":
        return "zh-TW"
    if code.startswith("zh-cn") or code.startswith("zh-hans") or code.startswith("zh-sg") or code == "cn":
        return "zh-CN"
    if code.startswith("vi") or code == "vn":
        return "vi"
    if code.startswith("en"):
        return "en"
    return ""


def query_ldap_user_language(user_name, user_email):
    """
    若配置有 LDAP 且安裝有 ldapsearch，嘗試從 Active Directory 查詢 preferredLanguage, countryCode, c
    """
    search_base = os.getenv("SEARCH_BASE", "")
    host_ip = os.getenv("HOST_IP", "127.0.0.1")
    bind_dn = os.getenv("BIND_DN", "")
    bind_pw = os.getenv("BIND_PW", "")

    if not bind_dn and os.path.exists("/etc/dovecot/dovecot-ldap.conf.ext"):
        try:
            with open("/etc/dovecot/dovecot-ldap.conf.ext", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("base") and "=" in line:
                        search_base = search_base or line.split("=", 1)[1].strip()
                    elif line.startswith("hosts") and "=" in line:
                        h = line.split("=", 1)[1].strip()
                        host_ip = host_ip or h.split(":")[0]
                    elif line.startswith("dn") and "=" in line and not line.startswith("dnpass"):
                        bind_dn = bind_dn or line.split("=", 1)[1].strip()
                    elif line.startswith("dnpass") and "=" in line:
                        bind_pw = bind_pw or line.split("=", 1)[1].strip()
        except Exception:
            pass

    if not search_base:
        return ""

    query = f"(|(sAMAccountName={user_name})(mail={user_email})(userPrincipalName={user_email}))"
    cmd = ["ldapsearch", "-x", "-h", host_ip, "-b", search_base, query, "preferredLanguage", "countryCode", "c"]
    if bind_dn and bind_pw:
        cmd.extend(["-D", bind_dn, "-w", bind_pw])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("preferredlanguage:"):
                    v = line.split(":", 1)[1].strip()
                    norm = normalize_language(v)
                    if norm:
                        return norm
                elif line.lower().startswith("countrycode:"):
                    cc = line.split(":", 1)[1].strip()
                    if cc == "886":
                        return "zh-TW"
                    elif cc == "86":
                        return "zh-CN"
                    elif cc == "84":
                        return "vi"
                    elif cc == "840":
                        return "en"
                elif line.lower().startswith("c:"):
                    c = line.split(":", 1)[1].strip().upper()
                    if c == "TW":
                        return "zh-TW"
                    elif c == "CN":
                        return "zh-CN"
                    elif c == "VN":
                        return "vi"
                    elif c in ("US", "GB", "EN"):
                        return "en"
    except Exception:
        pass
    return ""


def detect_user_language(user_name, user_email, domain="", msg=None, explicit_lang=""):
    """
    智慧判定使用者語系 (4 級判定鏈):
    1. 明確參數 (--lang)
    2. AD LDAP 屬性 (preferredLanguage, countryCode, c)
    3. 郵件網域後綴 (TLD: .tw, .cn, .vn)
    4. 觸發郵件標頭 (Accept-Language / Content-Language)
    5. 系統環境變數 DEFAULT_LANG (預設 zh-TW)
    """
    if explicit_lang:
        norm = normalize_language(explicit_lang)
        if norm in SUPPORTED_LANGUAGES:
            return norm

    # 2. LDAP 查詢
    ldap_lang = query_ldap_user_language(user_name, user_email)
    if ldap_lang:
        return ldap_lang

    # 3. 網域後綴判定
    domain_lower = domain.lower()
    if domain_lower.endswith(".tw"):
        return "zh-TW"
    if domain_lower.endswith(".cn"):
        return "zh-CN"
    if domain_lower.endswith(".vn"):
        return "vi"

    # 4. 郵件標頭
    if msg:
        for header in ["Accept-Language", "Content-Language"]:
            val = msg.get(header, "")
            norm = normalize_language(val)
            if norm in SUPPORTED_LANGUAGES:
                return norm

    # 5. 環境變數預設
    env_default = normalize_language(os.getenv("DEFAULT_LANG", "zh-TW"))
    if env_default in SUPPORTED_LANGUAGES:
        return env_default

    return "zh-TW"


def detect_certificate_type(cert_path=None, host_name=None):
    """
    偵測憑證是自簽測試憑證還是 Let's Encrypt / 公開受信任憑證。
    回傳: 'self_signed' 或 'lets_encrypt'
    """
    if not host_name:
        host_name = get_host_name()

    if not cert_path:
        candidates = [
            f"/etc/letsencrypt/live/{host_name}/cert.pem",
            f"/etc/letsencrypt/live/{host_name}/chain.pem",
            f"/etc/letsencrypt/live/{host_name}/fullchain.pem",
            "/etc/dovecot/cert.pem",
        ]
        for c in candidates:
            if os.path.exists(c):
                cert_path = c
                break

    if not cert_path or not os.path.exists(cert_path):
        return "self_signed"

    try:
        with open(cert_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "Let's Encrypt R3 Fake CA" in content or "Fake CA" in content:
            return "self_signed"

        cmd = ["openssl", "x509", "-in", cert_path, "-noout", "-issuer", "-subject"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            out = res.stdout.lower()
            if "fake ca" in out:
                return "self_signed"
            # 檢查自簽 (issuer == subject)
            issuers = [l for l in res.stdout.splitlines() if l.startswith("issuer=")]
            subjects = [l for l in res.stdout.splitlines() if l.startswith("subject=")]
            if issuers and subjects and issuers[0].replace("issuer=", "").strip() == subjects[0].replace("subject=", "").strip():
                return "self_signed"
            if "let's encrypt" in out or "r3" in out or "isrg root" in out:
                return "lets_encrypt"
    except Exception:
        pass

    return "self_signed"


def generate_powershell_trust_cmd(mail_server, user_lang="zh-TW"):
    """
    生成具備完整 try...catch 錯誤攔截、多行排版、語系在地化且無折行風險的 PowerShell 指令
    """
    if user_lang == "zh-CN":
        ok_msg = "[OK] $mailServer 通讯录安全证书已成功导入受信任列表！"
        err_msg = "[ERROR] 证书导入失败"
    elif user_lang == "vi":
        ok_msg = "[OK] Da them chung chi bao mat $mailServer thanh cong!"
        err_msg = "[ERROR] Khong the them chung chi"
    elif user_lang == "en":
        ok_msg = "[OK] $mailServer Certificate Added Successfully!"
        err_msg = "[ERROR] Failed to import certificate"
    else:  # zh-TW
        ok_msg = "[OK] $mailServer 通訊錄安全憑證已成功匯入受信任清單！"
        err_msg = "[ERROR] 憑證匯入失敗"

    return f"""try {{
    $mailServer = '{mail_server}'
    $tcp = New-Object System.Net.Sockets.TcpClient($mailServer, 3269)
    $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({{$true}} -as [System.Net.Security.RemoteCertificateValidationCallback]))
    $ssl.AuthenticateAsClient($mailServer)
    if (-not $ssl.RemoteCertificate) {{ throw "No certificate received from $mailServer:3269" }}
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $store.Open('ReadWrite')
    $store.Add($cert)
    $store.Close()
    $tcp.Close()
    Write-Host "{ok_msg}" -ForegroundColor Green
}} catch {{
    Write-Host "{err_msg}: $($_.Exception.Message)" -ForegroundColor Red
}}"""


def generate_cert_block(cert_mode, powershell_cmd, user_lang="zh-TW"):
    """
    依據語言及憑證類型生成開戶信中的安全憑證指引區塊 (註明網管職責與協助方式)
    """
    if cert_mode == "self_signed":
        if user_lang == "zh-CN":
            title = "🔒 步骤 0：Windows 导入安全证书 (IT/管理员协助)"
            desc = "本系统使用企业内部安全证书。若您的电脑受 AD 域控管理，IT 部门通常已自动下发信任；若为个人电脑或需手动设置，请联系 IT 网管或以 <strong>系统管理员身份</strong> 运行 PowerShell 执行下列命令："
            note = "💡 提示：执行完毕后即可安全启用 Outlook 3269 (SSL) 连接。"
        elif user_lang == "en":
            title = "🔒 Step 0: Import Security Certificate on Windows (IT / Admin)"
            desc = "This system uses an internal security certificate. If your PC is managed by corporate AD domain, IT administrators usually deploy this certificate automatically. For personal computers or manual setup, please contact IT support or open PowerShell as <strong>Administrator</strong> and run the following command:"
            note = "💡 Tip: After execution, Outlook can securely connect via port 3269 (SSL)."
        elif user_lang == "vi":
            title = "🔒 Bước 0: Nhập chứng chỉ bảo mật trên Windows (IT / Quản trị viên)"
            desc = "Hệ thống sử dụng chứng chỉ bảo mật nội bộ. Nếu máy tính của bạn thuộc mạng Active Directory của công ty, bộ phận CNTT thường đã tự động cài đặt. Đối với máy tính cá nhân hoặc cài đặt thủ công, vui lòng mở PowerShell với quyền <strong>Administrator</strong> và chạy lệnh sau:"
            note = "💡 Mẹo: Sau khi chạy lệnh, Outlook có thể kết nối an toàn qua cổng 3269 (SSL)."
        else:  # zh-TW
            title = "🔒 步驟 0：Windows 匯入安全憑證 (IT/網管人員協助)"
            desc = "本系統目前使用內部安全憑證。若您的電腦受公司 AD 網域管理，資訊部門 (網管) 通常已自動派送信任；若為個人電腦或需手動設定，請洽 IT 網管人員或以 <strong>系統管理員身分</strong> 開啟 PowerShell 執行下列指令："
            note = "💡 提示：執行完畢後即可安全啟用 Outlook 3269 (SSL) 連線，無需繁瑣匯出憑證檔。"

        return f"""
  <div class="step-box" style="border-left-color: #ed8936; background: #fffaf0;">
    <h3 style="margin-top:0; color: #c05621;">{title}</h3>
    <p>{desc}</p>
    <pre style="background: #1a202c; color: #ecc94b; padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre; word-wrap: normal; font-family: Consolas, 'Courier New', monospace; font-size: 0.88em;"><code>{powershell_cmd}</code></pre>
    <p style="font-size:0.88em; color:#744210; margin-bottom:0;">{note}</p>
  </div>
"""
    else:
        if user_lang == "zh-CN":
            return """
  <div class="step-box" style="border-left-color: #38a169; background: #f0fff4;">
    <h3 style="margin-top:0; color: #276749;">🛡️ 安全证书验证已启用</h3>
    <p style="margin-bottom:0;">本系统已启用官方受信任 SSL 证书，Windows 与 Outlook 将自动信任连接，无需手动导入证书！</p>
  </div>
"""
        elif user_lang == "en":
            return """
  <div class="step-box" style="border-left-color: #38a169; background: #f0fff4;">
    <h3 style="margin-top:0; color: #276749;">🛡️ Trusted SSL Certificate Active</h3>
    <p style="margin-bottom:0;">This server is secured by an official trusted SSL certificate. Windows and Outlook will connect automatically without manual certificate import!</p>
  </div>
"""
        elif user_lang == "vi":
            return """
  <div class="step-box" style="border-left-color: #38a169; background: #f0fff4;">
    <h3 style="margin-top:0; color: #276749;">🛡️ Đã kích hoạt chứng chỉ SSL đáng tin cậy</h3>
    <p style="margin-bottom:0;">Hệ thống sử dụng chứng chỉ SSL chính thức được tin cậy. Windows và Outlook sẽ tự động kết nối mà không cần cài đặt chứng chỉ thủ công!</p>
  </div>
"""
        else:
            return """
  <div class="step-box" style="border-left-color: #38a169; background: #f0fff4;">
    <h3 style="margin-top:0; color: #276749;">🛡️ 安全憑證驗證已啟用</h3>
    <p style="margin-bottom:0;">本系統已啟用官方受信任 SSL 憑證，Windows 及 Outlook 將自動信任連線，無需手動匯入憑證！</p>
  </div>
"""


def find_templates_for_lang(templates_dir, user_lang):
    """
    根據使用者語系載入最佳範本群組 (優先尋找 .{lang}.eml，否則 fallback 到預設 .eml)
    """
    if not templates_dir or not os.path.isdir(templates_dir):
        return []

    all_eml = glob.glob(os.path.join(templates_dir, "*.eml"))
    groups = {}
    for f in sorted(all_eml):
        fname = os.path.basename(f)
        m = re.match(r'^(.*?)\.(zh-TW|zh-CN|en|vi)\.eml$', fname, re.IGNORECASE)
        if m:
            base_key = m.group(1)
            lang = normalize_language(m.group(2))
        else:
            base_key = re.sub(r'\.eml$', '', fname)
            lang = "default"

        if base_key not in groups:
            groups[base_key] = {}
        groups[base_key][lang] = f

    chosen = []
    for base_key in sorted(groups.keys()):
        lang_dict = groups[base_key]
        if user_lang in lang_dict:
            chosen.append(lang_dict[user_lang])
        elif "default" in lang_dict:
            chosen.append(lang_dict["default"])
        elif lang_dict:
            chosen.append(next(iter(lang_dict.values())))
    return chosen


def acquire_atomic_welcomed_lock(user_name, user_email, home_dir=None):
    """
    以原子建立 .welcomed 檔案的方式防止並行與重複派送
    若成功建立回傳 (True, lock_path)，若已存在回傳 (False, existing_path)
    """
    candidates = []
    if home_dir:
        candidates.append(os.path.join(home_dir, ".welcomed"))
    candidates.append(f"/home/vmail/{user_email}/.welcomed")
    candidates.append(f"/home/vmail/{user_name}/.welcomed")

    # 1. 檢查是否任何一處已存在
    for c in candidates:
        if os.path.exists(c):
            return False, c

    # 2. 選定主目錄進行原子建立
    target_lock = candidates[0]
    target_dir = os.path.dirname(target_lock)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass

    try:
        fd = os.open(target_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"welcomed_at={datetime.now().isoformat()}\nuser={user_name}\nemail={user_email}\n")
        return True, target_lock
    except FileExistsError:
        return False, target_lock
    except Exception as e:
        sys.stderr.write(f"[welcome_provisioner] Lock creation warning: {e}\n")
        # 若無法寫入預設目錄，嘗試在 /tmp/ 標記防呆
        fallback_lock = f"/tmp/.welcomed_{user_name}"
        try:
            fd = os.open(fallback_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"welcomed_at={datetime.now().isoformat()}\nuser={user_name}\nemail={user_email}\n")
            return True, fallback_lock
        except FileExistsError:
            return False, fallback_lock


def send_mail(raw_email_content, recipient, envelope_from="postmaster"):
    """
    透過本機 sendmail -i -f 派發郵件 (自動享受 OpenDKIM 數位簽章)
    """
    cmd = ["/usr/sbin/sendmail", "-i", "-f", envelope_from, recipient]
    try:
        subprocess.run(cmd, input=raw_email_content.encode("utf-8"),
                       capture_output=True, check=True)
        return True
    except FileNotFoundError:
        sys.stdout.write(f"[welcome_provisioner:mock_sendmail] To: {recipient}, From: {envelope_from}\n")
        return True
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"[welcome_provisioner] Sendmail failed: {e.stderr.decode('utf-8', errors='ignore')}\n")
        return False


def notify_admin_onboarding_done(user_name, user_email, domain, event_type, cert_mode, sent_templates,
                                 mail_server="", powershell_cmd="", user_lang="zh-TW"):
    """
    開戶完成後向 postmaster (自動遞送至 SPAM_EMAIL) 發送詳細系統通報信 (含伺服器連線參數與網管專用指令)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[系統通報] 新帳號開戶完成: {user_name} ({user_lang})"
    admin_recipient = f"postmaster@{domain}"

    templates_html = "".join([f"<li><code>{os.path.basename(t)}</code></li>" for t in sent_templates])

    admin_cert_block = ""
    if cert_mode == "self_signed" and powershell_cmd:
        admin_cert_block = f"""
    <div style="background: #edf2f7; border-left: 4px solid #4a5568; padding: 12px; margin-top: 15px; border-radius: 4px;">
      <h4 style="margin-top:0; color: #2d3748;">🛠️ 【網管專區】Windows 用戶端憑證信任指令</h4>
      <p style="font-size:0.9em; margin-bottom: 8px;">網管人員可於受測端電腦開啟 Administrator PowerShell 貼上執行以快速驗證，或透過 AD GPO 集中發布至全域電腦：</p>
      <pre style="background: #1a202c; color: #ecc94b; padding: 10px; border-radius: 4px; overflow-x: auto; white-space: pre; word-wrap: normal; font-family: Consolas, 'Courier New', monospace; font-size: 0.85em;"><code>{powershell_cmd}</code></pre>
      <p style="font-size:0.85em; color: #718096; margin-bottom:0;">📌 GPO 派送建議：電腦設定 (Computer Configuration) ➔ 原則 ➔ Windows 設定 ➔ 安全性設定 ➔ 公開金鑰原則 ➔ 受信任的根憑證授權單位。</p>
    </div>
"""

    body = f"""From: postmaster@{domain}
To: {admin_recipient}
Subject: {subject}
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8

<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: sans-serif; line-height: 1.5; color: #333;">
  <h3 style="color: #2b6cb0;">【系統管理通報】新進同仁信箱自動開戶已完成</h3>
  <ul>
    <li><strong>同仁帳號：</strong> {user_name}</li>
    <li><strong>同仁信箱：</strong> <code>{user_email}</code></li>
    <li><strong>觸發事件：</strong> <code>{event_type}</code></li>
    <li><strong>判定語系：</strong> <code>{user_lang}</code></li>
    <li><strong>郵件伺服器 (Host)：</strong> <code>{mail_server}</code></li>
    <li><strong>連線資訊：</strong>
      IMAP: <code>{mail_server}:993 (SSL)</code> |
      SMTP: <code>{mail_server}:465/587 (SSL)</code> |
      LDAPS GAL: <code>{mail_server}:3269 (SSL)</code>
    </li>
    <li><strong>憑證模式：</strong> <code>{cert_mode}</code></li>
    <li><strong>完成時間：</strong> {now_str}</li>
    <li><strong>入職範本派發清單：</strong>
      <ul>{templates_html}</ul>
    </li>
  </ul>
  {admin_cert_block}
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 20px;">
  <p style="font-size: 0.85em; color: #718096;">此信件由系統開戶排程自動寄發至 postmaster (已綁定至 SPAM_EMAIL)。</p>
</body>
</html>
"""
    send_mail(body, admin_recipient, envelope_from="postmaster")


def process_onboarding(args):
    # 1. 解析收件者與傳入郵件標頭 (若透過 stdin)
    raw_msg = None
    recipient = args.recipient.strip()
    if not recipient:
        recipient = os.getenv("USER", "")
    if not recipient:
        recipient, raw_msg = extract_recipient_from_stdin()
    if not recipient:
        sys.stderr.write("[welcome_provisioner] No recipient found, skipping.\n")
        return False

    default_domain = os.getenv("DOMAIN_NAME", "example.com")
    if "@" in recipient:
        user_name = recipient.split("@")[0]
        domain = recipient.split("@")[1]
        user_email = recipient
    else:
        user_name = recipient
        domain = default_domain
        user_email = f"{recipient}@{domain}"

    # 2. 排除系統帳號
    if user_name.lower() in SYSTEM_ACCOUNTS:
        return False

    # 3. 原子鎖定檢查
    locked, lock_path = acquire_atomic_welcomed_lock(user_name, user_email, args.home_dir)
    if not locked:
        sys.stdout.write(f"[welcome_provisioner] User {user_name} already welcomed, skipping.\n")
        return False

    # 4. 智慧語系判定
    user_lang = detect_user_language(
        user_name=user_name,
        user_email=user_email,
        domain=domain,
        msg=raw_msg,
        explicit_lang=args.lang
    )

    sys.stdout.write(f"[welcome_provisioner] Provisioning onboarding pack for {user_email} (event: {args.event}, lang: {user_lang})\n")

    # 5. 主機與憑證類型動態偵測
    mail_server = get_host_name(domain)
    search_base = os.getenv("SEARCH_BASE", f"DC={domain.replace('.', ',DC=')}")
    cert_mode = detect_certificate_type(args.cert_path, mail_server)

    powershell_cmd = generate_powershell_trust_cmd(mail_server, user_lang)
    cert_block = generate_cert_block(cert_mode, powershell_cmd, user_lang)

    # 6. 載入並依序派送範本
    templates_dir = args.templates_dir
    if not templates_dir:
        candidates = [
            "/etc/dovecot/welcome_templates",
            os.path.join(os.path.dirname(__file__), "..", "dovecot", "welcome_templates"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                templates_dir = c
                break

    selected_templates = find_templates_for_lang(templates_dir, user_lang)

    sent_templates = []
    if not selected_templates:
        sys.stderr.write("[welcome_provisioner] Warning: No template files found in templates directory\n")
    else:
        for t_file in selected_templates:
            try:
                with open(t_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # 智慧變數替換
                replacements = {
                    "${USER_NAME}": user_name,
                    "${USER_EMAIL}": user_email,
                    "${DOMAIN}": domain,
                    "${MAIL_SERVER}": mail_server,
                    "${SEARCH_BASE}": search_base,
                    "${POWERSHELL_CMD}": powershell_cmd,
                    "${CERT_INSTRUCTION_BLOCK}": cert_block,
                }
                for placeholder, val in replacements.items():
                    content = content.replace(placeholder, val)

                send_mail(content, user_email, envelope_from="postmaster")
                sent_templates.append(t_file)
            except Exception as e:
                sys.stderr.write(f"[welcome_provisioner] Error sending template {t_file}: {e}\n")

    # 7. 發送管理員開戶完成詳細通報信
    notify_admin_onboarding_done(
        user_name=user_name,
        user_email=user_email,
        domain=domain,
        event_type=args.event,
        cert_mode=cert_mode,
        sent_templates=sent_templates,
        mail_server=mail_server,
        powershell_cmd=powershell_cmd,
        user_lang=user_lang
    )
    return True


if __name__ == "__main__":
    args = parse_args()
    process_onboarding(args)
