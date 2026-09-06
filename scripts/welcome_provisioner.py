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
from email.header import decode_header, Header
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


def encode_header_rfc2047(val):
    """
    若標頭字串包含非 ASCII 字元，轉為 RFC 2047 MIME 編碼以確保符合 7-bit ASCII 標準，
    徹底防止觸發 Postfix SMTPUTF8 與下游 Dovecot LMTP 投遞拒收問題
    """
    if not val:
        return ""
    try:
        val.encode('ascii')
        return val
    except UnicodeEncodeError:
        return Header(val, 'utf-8').encode()


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


def query_ldap_user_identity(user_name, user_email):
    """
    向 Active Directory 查詢使用者權威身分 (sAMAccountName, mail, userPrincipalName) 與語系屬性
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
        return {}

    clean_user = user_name.replace("(", "").replace(")", "").replace("*", "")
    clean_email = user_email.replace("(", "").replace(")", "").replace("*", "")
    query = f"(|(sAMAccountName={clean_user})(mail={clean_email})(userPrincipalName={clean_email}))"
    cmd = ["ldapsearch", "-x", "-h", host_ip, "-b", search_base, query,
           "sAMAccountName", "mail", "userPrincipalName", "preferredLanguage", "countryCode", "c"]
    if bind_dn and bind_pw:
        cmd.extend(["-D", bind_dn, "-w", bind_pw])

    info = {}
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("samaccountname:"):
                    info["sAMAccountName"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("mail:"):
                    info["mail"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("userprincipalname:"):
                    info["userPrincipalName"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("preferredlanguage:"):
                    v = line.split(":", 1)[1].strip()
                    norm = normalize_language(v)
                    if norm:
                        info["lang"] = norm
                elif line.lower().startswith("countrycode:"):
                    cc = line.split(":", 1)[1].strip()
                    if cc == "886":
                        info["lang"] = "zh-TW"
                    elif cc == "86":
                        info["lang"] = "zh-CN"
                    elif cc == "84":
                        info["lang"] = "vi"
                    elif cc == "840":
                        info["lang"] = "en"
                elif line.lower().startswith("c:") and "lang" not in info:
                    c = line.split(":", 1)[1].strip().upper()
                    if c == "TW":
                        info["lang"] = "zh-TW"
                    elif c == "CN":
                        info["lang"] = "zh-CN"
                    elif c == "VN":
                        info["lang"] = "vi"
                    elif c in ("US", "GB", "EN"):
                        info["lang"] = "en"
    except Exception:
        pass
    return info


def query_ldap_user_language(user_name, user_email):
    """
    若配置有 LDAP 且安裝有 ldapsearch，嘗試從 Active Directory 查詢 preferredLanguage, countryCode, c
    """
    info = query_ldap_user_identity(user_name, user_email)
    return info.get("lang", "")


def detect_user_language(user_name, user_email, domain="", msg=None, explicit_lang="", cached_ldap_lang=""):
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

    # 2. LDAP 查詢 (優先使用快取)
    ldap_lang = cached_ldap_lang or query_ldap_user_language(user_name, user_email)
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


def acquire_atomic_welcomed_lock(user_name, user_email, home_dir=None, extra_identifiers=None):
    """
    以原子建立 .welcomed 檔案的方式防止並行與重複派送 (支援 cross-identifier 全域防護)
    若成功建立回傳 (True, lock_path)，若已存在回傳 (False, existing_path)
    """
    identifiers = set()
    if user_name:
        identifiers.add(user_name.lower())
    if user_email:
        identifiers.add(user_email.lower())
        if "@" in user_email:
            identifiers.add(user_email.split("@")[0].lower())
    if extra_identifiers:
        for ident in extra_identifiers:
            if ident:
                identifiers.add(ident.lower())
                if "@" in ident:
                    identifiers.add(ident.split("@")[0].lower())

    candidates = []
    if home_dir:
        candidates.append(os.path.join(home_dir, ".welcomed"))

    for ident in sorted(identifiers):
        candidates.append(f"/home/vmail/{ident}/.welcomed")
        candidates.append(f"/home/vmail/.welcomed_{ident}")

    # 1. 檢查是否任何一處已存在
    for c in candidates:
        if os.path.exists(c):
            return False, c

    # 2. 選定主目錄進行原子建立
    target_lock = candidates[0]
    target_dir = os.path.dirname(target_lock)
    if target_dir:
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            pass

    try:
        fd = os.open(target_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"welcomed_at={datetime.now().isoformat()}\nuser={user_name}\nemail={user_email}\n")

        # 同步在 /home/vmail 建立共享鎖以防跨事件並發
        shared_lock = f"/home/vmail/.welcomed_{user_name.lower()}"
        if target_lock != shared_lock:
            try:
                sfd = os.open(shared_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                with os.fdopen(sfd, "w", encoding="utf-8") as sf:
                    sf.write(f"welcomed_at={datetime.now().isoformat()}\nuser={user_name}\nemail={user_email}\n")
            except Exception:
                pass

        return True, target_lock
    except FileExistsError:
        return False, target_lock
    except Exception as e:
        sys.stderr.write(f"[welcome_provisioner] Lock creation warning: {e}\n")
        # 若無法寫入預設目錄，嘗試在 /tmp/ 標記防呆
        fallback_lock = f"/tmp/.welcomed_{user_name.lower()}"
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
                                 mail_server="", user_lang="zh-TW"):
    """
    開戶完成後向 postmaster (自動遞送至 SPAM_EMAIL) 發送詳細系統通報信 (含伺服器連線參數)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[系統通報] 新帳號開戶完成: {user_name} ({user_lang})"
    subject_enc = encode_header_rfc2047(subject)
    admin_recipient = f"postmaster@{domain}"

    templates_html = "".join([f"<li><code>{os.path.basename(t)}</code></li>" for t in sent_templates])

    body = f"""From: postmaster@{domain}
To: {admin_recipient}
Subject: {subject_enc}
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
      SMTP: <code>{mail_server}:465/587 (SSL)</code>
    </li>
    <li><strong>憑證模式：</strong> <code>{cert_mode}</code></li>
    <li><strong>完成時間：</strong> {now_str}</li>
    <li><strong>入職範本派發清單：</strong>
      <ul>{templates_html}</ul>
    </li>
  </ul>
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

    raw_recipient = recipient
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

    # 2.5 查詢 Active Directory LDAP 解析權威身分 (Canonical User Identity)
    ad_info = query_ldap_user_identity(user_name, user_email)
    canonical_user = ad_info.get("sAMAccountName") or user_name
    canonical_email = ad_info.get("mail") or ad_info.get("userPrincipalName") or user_email
    cached_ldap_lang = ad_info.get("lang", "")

    # 3. 原子鎖定檢查 (跨身分與全域交叉防重複)
    locked, lock_path = acquire_atomic_welcomed_lock(
        user_name=canonical_user,
        user_email=canonical_email,
        home_dir=args.home_dir,
        extra_identifiers=[user_name, user_email, raw_recipient]
    )
    if not locked:
        sys.stdout.write(f"[welcome_provisioner] User {canonical_user} already welcomed, skipping.\n")
        return False

    # 更新為權威身分，確保模板替換與寄件一致
    user_name = canonical_user
    user_email = canonical_email

    # 4. 智慧語系判定
    user_lang = detect_user_language(
        user_name=user_name,
        user_email=user_email,
        domain=domain,
        msg=raw_msg,
        explicit_lang=args.lang,
        cached_ldap_lang=cached_ldap_lang
    )

    sys.stdout.write(f"[welcome_provisioner] Provisioning onboarding pack for {user_email} (event: {args.event}, lang: {user_lang})\n")

    # 5. 主機與憑證類型動態偵測
    mail_server = get_host_name(domain)
    cert_mode = detect_certificate_type(args.cert_path, mail_server)

    # 6. 載入並依序派送範本
    templates_dir = args.templates_dir
    if not templates_dir:
        candidates = [
            "/etc/dovecot/welcome_templates",
            os.path.join(os.path.dirname(__file__), "..", "dovecot", "welcome_templates"),
        ]
        for c in candidates:
            if os.path.isdir(c) and glob.glob(os.path.join(c, "*.eml")):
                templates_dir = c
                break

    selected_templates = find_templates_for_lang(templates_dir, user_lang)

    sent_templates = []
    if not selected_templates:
        sys.stderr.write(f"[welcome_provisioner] Warning: No template files found in {templates_dir or 'candidates'}. Rolling back lock.\n")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass
        return False
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
                }
                for placeholder, val in replacements.items():
                    content = content.replace(placeholder, val)

                # 處理 Subject 標頭的 RFC 2047 MIME 編碼 (徹底防杜 Postfix SMTPUTF8 限制)
                lines = content.splitlines(True)
                new_lines = []
                in_header = True
                for line in lines:
                    if in_header and line.lower().startswith("subject:"):
                        prefix, subj_val = line.split(":", 1)
                        new_lines.append(f"{prefix}: {encode_header_rfc2047(subj_val.strip())}\n")
                    else:
                        if in_header and line.strip() == "":
                            in_header = False
                        new_lines.append(line)
                content = "".join(new_lines)

                sent_ok = send_mail(content, user_email, envelope_from="postmaster")
                if sent_ok:
                    sent_templates.append(t_file)
                else:
                    sys.stderr.write(f"[welcome_provisioner] Failed to send template {t_file} to {user_email}\n")
                    if os.path.exists(lock_path):
                        try:
                            os.remove(lock_path)
                        except Exception:
                            pass
            except Exception as e:
                sys.stderr.write(f"[welcome_provisioner] Error sending template {t_file}: {e}\n")
                if os.path.exists(lock_path):
                    try:
                        os.remove(lock_path)
                    except Exception:
                        pass

    if not sent_templates:
        sys.stderr.write(f"[welcome_provisioner] No templates were successfully sent to {user_email}. Rolling back lock.\n")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass
        return False

    # 7. 發送管理員開戶完成詳細通報信
    notify_admin_onboarding_done(
        user_name=user_name,
        user_email=user_email,
        domain=domain,
        event_type=args.event,
        cert_mode=cert_mode,
        sent_templates=sent_templates,
        mail_server=mail_server,
        user_lang=user_lang
    )
    return True


if __name__ == "__main__":
    args = parse_args()
    process_onboarding(args)
