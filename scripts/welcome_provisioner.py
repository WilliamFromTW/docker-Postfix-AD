#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新人首通入職歡迎郵件包派發系統 (Mailbox Onboarding Provisioner)
支援雙重觸發 (Sieve 遞送 / Post-login 登入)、原子防重複鎖、憑證類型偵測與管理員通報
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


def parse_args():
    parser = argparse.ArgumentParser(description="Dovecot Mailbox Onboarding Welcome Pack Provisioner")
    parser.add_argument("--event", default="delivery", choices=["delivery", "imap_login", "manual"],
                        help="Triggering event type")
    parser.add_argument("--recipient", default="", help="Target recipient email or username")
    parser.add_argument("--home-dir", default="", help="Custom home directory for the user")
    parser.add_argument("--templates-dir", default="", help="Path to welcome templates directory")
    parser.add_argument("--cert-path", default="", help="Path to server SSL certificate")
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
            return ""
        msg = email.message_from_bytes(raw_bytes)
        for h in ["Delivered-To", "X-Original-To", "To"]:
            val = decode_str(msg.get(h, ""))
            if val:
                match = re.search(r'[\w\.-]+@[\w\.-]+', val)
                if match:
                    return match.group(0)
                return val.strip("<> ")
    except Exception:
        pass
    return ""


def detect_certificate_type(cert_path=None, host_name=None):
    """
    偵測憑證是自簽測試憑證還是 Let's Encrypt / 公開受信任憑證。
    回傳: 'self_signed' 或 'lets_encrypt'
    """
    if not host_name:
        host_name = os.getenv("HOST_NAME", os.getenv("DOMAIN_NAME", "mail.example.com"))

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


def generate_powershell_trust_cmd(mail_server):
    return (
        f'Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -Command \\"'
        f'$tcp = New-Object System.Net.Sockets.TcpClient(\'{mail_server}\', 3269); '
        f'$ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({{$true}} -as [System.Net.Security.RemoteCertificateValidationCallback])); '
        f'$ssl.AuthenticateAsClient(\'{mail_server}\'); '
        f'$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate); '
        f'$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(\'Root\', \'LocalMachine\'); '
        f'$store.Open(\'ReadWrite\'); '
        f'$store.Add($cert); '
        f'$store.Close(); '
        f'Write-Host \'[OK] {mail_server} 通訊錄安全憑證已成功匯入受信任清單！\' -ForegroundColor Green\\""'
    )


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
        proc = subprocess.run(cmd, input=raw_email_content.encode("utf-8"),
                              capture_output=True, check=True)
        return True
    except FileNotFoundError:
        # 測試環境若無 sendmail，記錄日誌模擬成功
        sys.stdout.write(f"[welcome_provisioner:mock_sendmail] To: {recipient}, From: {envelope_from}\n")
        return True
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"[welcome_provisioner] Sendmail failed: {e.stderr.decode('utf-8', errors='ignore')}\n")
        return False


def notify_admin_onboarding_done(user_name, user_email, domain, event_type, cert_mode, sent_templates):
    """
    開戶完成後向 postmaster 發送系統通報信 (自動遞送至 SPAM_EMAIL)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[系統通報] 新帳號開戶完成: {user_name}"
    admin_recipient = f"postmaster@{domain}"

    templates_html = "".join([f"<li><code>{os.path.basename(t)}</code></li>" for t in sent_templates])

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
    <li><strong>憑證模式：</strong> <code>{cert_mode}</code></li>
    <li><strong>完成時間：</strong> {now_str}</li>
    <li><strong>入職範本派發清單：</strong>
      <ul>{templates_html}</ul>
    </li>
  </ul>
  <hr style="border: none; border-top: 1px solid #e2e8f0;">
  <p style="font-size: 0.85em; color: #718096;">此信件由系統開戶排程自動寄發至 postmaster (已綁定至 SPAM_EMAIL)。</p>
</body>
</html>
"""
    send_mail(body, admin_recipient, envelope_from="postmaster")


def process_onboarding(args):
    # 1. 解析收件者
    recipient = args.recipient.strip()
    if not recipient:
        recipient = os.getenv("USER", "")
    if not recipient:
        recipient = extract_recipient_from_stdin()
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

    sys.stdout.write(f"[welcome_provisioner] Provisioning onboarding pack for {user_email} (event: {args.event})\n")

    # 4. 憑證類型偵測
    mail_server = os.getenv("HOST_NAME", f"mail.{domain}")
    search_base = os.getenv("SEARCH_BASE", f"DC={domain.replace('.', ',DC=')}")
    cert_mode = detect_certificate_type(args.cert_path, mail_server)

    powershell_cmd = generate_powershell_trust_cmd(mail_server)

    if cert_mode == "self_signed":
        cert_block = f"""
  <div class="step-box" style="border-left-color: #ed8936; background: #fffaf0;">
    <h3 style="margin-top:0; color: #c05621;">🔒 步驟 0：Windows 匯入安全憑證 (僅需執行一次)</h3>
    <p>由於系統目前使用內部安全測試憑證，請以 <strong>系統管理員身分</strong> 開啟 PowerShell 並貼上執行下列指令，即可自動完成信任：</p>
    <pre style="background: #1a202c; color: #ecc94b; padding: 12px; border-radius: 6px; overflow-x: auto;"><code>{powershell_cmd}</code></pre>
    <p style="font-size:0.88em; color:#744210; margin-bottom:0;">執行完畢後即可安全啟用 Outlook 3269 (SSL) 連線，無需手動繁瑣匯出憑證檔。</p>
  </div>
"""
    else:
        cert_block = """
  <div class="step-box" style="border-left-color: #38a169; background: #f0fff4;">
    <h3 style="margin-top:0; color: #276749;">🛡️ 安全憑證驗證已啟用</h3>
    <p style="margin-bottom:0;">本系統已啟用 Let's Encrypt 官方受信任 SSL 憑證，Windows 及 Outlook 將自動信任連線，無需手動匯入憑證！</p>
  </div>
"""

    # 5. 載入並依序派送範本
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

    template_files = []
    if templates_dir and os.path.isdir(templates_dir):
        template_files = sorted(glob.glob(os.path.join(templates_dir, "*.eml")))

    sent_templates = []
    if not template_files:
        sys.stderr.write("[welcome_provisioner] Warning: No template files found in templates directory\n")
    else:
        for t_file in template_files:
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

    # 6. 發送管理員開戶完成通報信
    notify_admin_onboarding_done(user_name, user_email, domain, args.event, cert_mode, sent_templates)
    return True


if __name__ == "__main__":
    args = parse_args()
    process_onboarding(args)
