#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15-Second Delayed Auto-Reply (Vacation) Worker for Postfix + Dovecot Pigeonhole Sieve.
Triggered by global sieve_before script.
Detaches immediately via double-fork so Dovecot LMTP delivery is never blocked.
Sleeps for 15 seconds in background, then sends the auto-reply email via sendmail.
"""

import sys
import os
import time
import json
import re
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr, formatdate
from datetime import datetime, timezone, timedelta
import subprocess

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    import syslog
    HAS_SYSLOG = True
except ImportError:
    HAS_SYSLOG = False

def log_maillog(msg, priority=None):
    """
    Writes log message directly to /var/log/maillog via syslog LOG_MAIL.
    Falls back gracefully to sys.stderr if syslog is not available.
    """
    if HAS_SYSLOG:
        try:
            p = priority if priority is not None else syslog.LOG_INFO
            syslog.openlog(ident="send_delayed_vacation", facility=syslog.LOG_MAIL)
            syslog.syslog(p, msg)
        except Exception:
            pass
    sys.stderr.write(f"send_delayed_vacation: {msg}\n")

DELAY_SECONDS = 15
RATE_LIMIT_HOURS = 24
VMAIL_BASE = "/home/vmail"

def get_configured_tz():
    """
    Natively adopts the Docker container's configured timezone (from TZ env,
    /etc/dovecot/ollama.env, /etc/timezone, /proc/1/environ, or /etc/localtime).
    Supports all IANA timezones and numeric offsets with zero hardcoding.
    """
    tz_val = os.environ.get("TZ", "").strip()

    if not tz_val:
        for fpath in ["/etc/dovecot/ollama.env", "/etc/timezone"]:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("TZ="):
                                tz_val = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                            elif line and not line.startswith("#") and fpath == "/etc/timezone":
                                tz_val = line
                                break
                except Exception:
                    pass
            if tz_val:
                break

    if not tz_val and os.path.exists("/proc/1/environ"):
        try:
            with open("/proc/1/environ", "rb") as f:
                content = f.read()
            for item in content.split(b"\0"):
                if item.startswith(b"TZ="):
                    tz_val = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
                    break
        except Exception:
            pass

    if tz_val:
        if ZoneInfo:
            try:
                return ZoneInfo(tz_val)
            except Exception:
                pass
        m = re.match(r"^(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?$", tz_val, re.IGNORECASE)
        if m:
            sign = 1 if m.group(1) == "+" else -1
            hours = int(m.group(2))
            mins = int(m.group(3)) if m.group(3) else 0
            return timezone(sign * timedelta(hours=hours, minutes=mins))

    # Natively use container's local timezone
    return datetime.now().astimezone().tzinfo

def decode_mime_words(s):
    if not s:
        return ""
    decoded_fragments = []
    for frag, enc in decode_header(s):
        if isinstance(frag, bytes):
            enc = enc or "utf-8"
            try:
                decoded_fragments.append(frag.decode(enc, errors="replace"))
            except Exception:
                decoded_fragments.append(frag.decode("utf-8", errors="replace"))
        else:
            decoded_fragments.append(str(frag))
    return "".join(decoded_fragments).strip()

def check_and_update_rate_limit(sieve_dir, sender_email):
    """
    Ensures the same sender is only replied once every 24 hours (:days 1 equivalent).
    """
    db_file = os.path.join(sieve_dir, "vacation_rate_limit.json")
    now_ts = time.time()
    records = {}

    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = {}

    # Cleanup expired records older than 24 hours
    cutoff = now_ts - (RATE_LIMIT_HOURS * 3600)
    cleaned = {k: v for k, v in records.items() if v > cutoff}

    sender_key = sender_email.lower().strip()
    if sender_key in cleaned:
        # Already replied in last 24 hours, skip
        return False

    # Record new reply timestamp
    cleaned[sender_key] = now_ts
    try:
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(cleaned, f)
        os.chown(db_file, 1001, 1001)
    except Exception:
        pass

    return True

def send_autoreply_email(owner_email, sender_email, subject, body, orig_msg_id):
    """
    Sends the auto-reply email via system sendmail with correct headers.
    """
    msg = MIMEText(body, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = owner_email
    msg["To"] = sender_email
    msg["Date"] = formatdate(localtime=True)
    msg["Auto-Submitted"] = "auto-replied"
    msg["Precedence"] = "bulk"
    if orig_msg_id:
        msg["In-Reply-To"] = orig_msg_id
        msg["References"] = orig_msg_id

    sendmail_paths = ["/usr/sbin/sendmail", "/usr/lib/sendmail"]
    sendmail_bin = None
    for p in sendmail_paths:
        if os.path.exists(p):
            sendmail_bin = p
            break

    if sendmail_bin:
        try:
            cmd = [sendmail_bin, "-t", "-oi", "-f", owner_email]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate(input=msg.as_bytes())
            if proc.returncode == 0:
                log_maillog(f"Auto-reply email sent successfully to {sender_email} (from {owner_email})")
            else:
                log_maillog(f"sendmail returned exit code {proc.returncode}: {stderr.decode(errors='ignore')}", syslog.LOG_ERR if HAS_SYSLOG else None)
        except Exception as e:
            log_maillog(f"Error executing sendmail: {e}", syslog.LOG_ERR if HAS_SYSLOG else None)
    else:
        log_maillog("sendmail binary not found on system", syslog.LOG_ERR if HAS_SYSLOG else None)

def background_delayed_task(owner_email, sender_email, subject, body, orig_msg_id):
    """
    Runs in a detached background daemon process. Sleeps 15s then sends email.
    """
    try:
        log_maillog(f"Starting {DELAY_SECONDS}s delay before auto-reply to {sender_email}...")
        time.sleep(DELAY_SECONDS)
        send_autoreply_email(owner_email, sender_email, subject, body, orig_msg_id)
    except Exception as e:
        log_maillog(f"Delayed task error: {e}", syslog.LOG_ERR if HAS_SYSLOG else None)

def main():
    raw_email = sys.stdin.buffer.read()
    if not raw_email:
        sys.exit(0)

    try:
        msg = email.message_from_bytes(raw_email)
    except Exception:
        sys.exit(0)

    # 1. Determine recipient (mailbox owner)
    recipient_env = os.environ.get("RECIPIENT", "").strip()
    if recipient_env:
        _, owner_email = parseaddr(recipient_env)
        owner_email = owner_email.lower().strip()
    else:
        delivered_to = msg.get("Delivered-To", "") or msg.get("X-Original-To", "") or msg.get("Envelope-To", "") or msg.get("To", "")
        _, owner_email = parseaddr(decode_mime_words(delivered_to))
        owner_email = owner_email.lower().strip()

    if not owner_email:
        sys.exit(0)

    # 2. Determine sender
    sender_env = os.environ.get("SENDER", "").strip()
    if sender_env:
        _, sender_email = parseaddr(sender_env)
        sender_email = sender_email.lower().strip()
    else:
        from_header = decode_mime_words(msg.get("From", ""))
        _, sender_email = parseaddr(from_header)
        sender_email = sender_email.lower().strip()

    # Don't auto-reply to empty sender or self
    if not sender_email or sender_email == owner_email:
        sys.exit(0)

    log_maillog(f"Incoming email intercepted for auto-reply evaluation: from='{sender_email}', to='{owner_email}'")

    # 3. Check Sieve storage directory for this user
    sieve_dir = os.path.join(VMAIL_BASE, owner_email, "sieve")
    if not os.path.exists(sieve_dir):
        local_part = owner_email.split("@")[0]
        sieve_dir = os.path.join(VMAIL_BASE, local_part, "sieve")
        if not os.path.exists(sieve_dir):
            sys.exit(0)

    # 4. Read config generated by handle_autoreply.py
    cfg_path = os.path.join(sieve_dir, "autoreply_config.json")
    if not os.path.exists(cfg_path):
        sys.exit(0)

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        sys.exit(0)

    if not cfg.get("enabled", False):
        log_maillog(f"Auto-reply is disabled for {owner_email}")
        sys.exit(0)

    # 5. Validate active date window
    if not cfg.get("is_always_on", False):
        start_ts = cfg.get("start_ts")
        end_ts = cfg.get("end_ts")
        now_ts = time.time()
        if start_ts and end_ts:
            if not (start_ts <= now_ts <= end_ts):
                app_tz = get_configured_tz()
                log_maillog(
                    f"Auto-reply inactive for {owner_email}: current time "
                    f"({datetime.fromtimestamp(now_ts, app_tz).strftime('%Y-%m-%d %H:%M:%S %z')}) "
                    f"is outside vacation window [{cfg.get('start_str', start_ts)} ~ {cfg.get('end_str', end_ts)}]"
                )
                sys.exit(0)

    # 6. Check 24-hour rate limit
    if not check_and_update_rate_limit(sieve_dir, sender_email):
        log_maillog(f"Auto-reply rate limited for {sender_email} (already sent within 24 hours)")
        sys.exit(0)

    reply_subject = cfg.get("subject", "【自動回覆】休假中 / Out of Office")
    reply_body = cfg.get("body", "您好：我目前休假/公出中，將於銷假後儘速處理您的郵件。")
    orig_msg_id = msg.get("Message-ID", "")

    log_maillog(f"Auto-reply criteria met for {owner_email} -> {sender_email}. Forking {DELAY_SECONDS}s delayed worker...")

    # Double-Fork to detach immediately and release Dovecot LMTP in < 0.005s
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        sys.exit(0)

    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        sys.exit(0)

    try:
        sys.stdout.flush()
        sys.stderr.flush()
        with open(os.devnull, "r") as devnull_r, open(os.devnull, "a+") as devnull_w:
            os.dup2(devnull_r.fileno(), sys.stdin.fileno())
            os.dup2(devnull_w.fileno(), sys.stdout.fileno())
            os.dup2(devnull_w.fileno(), sys.stderr.fileno())
    except Exception:
        pass

    background_delayed_task(owner_email, sender_email, reply_subject, reply_body, orig_msg_id)

if __name__ == "__main__":
    main()
