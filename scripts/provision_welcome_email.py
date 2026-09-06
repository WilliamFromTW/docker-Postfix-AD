#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
First-Login Localized Welcome Email Provisioning Engine for Dovecot.
Detects user language from Active Directory preferredLanguage attribute (via Dovecot user_attrs),
replaces personalization variables, and atomically deposits the welcome email into Maildir/new/
with concurrency protection and idempotency guarantees.
"""

import os
import sys
import time
import socket
import datetime
import email.utils
import shutil

TEMPLATE_DIR_DEFAULT = "/etc/dovecot/welcome_templates"

def detect_language(raw_lang: str) -> str:
    """Normalize and match language against supported templates, defaulting to en."""
    if not raw_lang:
        return "en"
    l = raw_lang.strip().lower()
    if any(k in l for k in ["zh-tw", "tw", "hant"]):
        return "zh-TW"
    if any(k in l for k in ["zh-cn", "cn", "hans"]):
        return "zh-CN"
    if any(k in l for k in ["vi", "vn"]):
        return "vi"
    return "en"

def find_template(lang: str, template_dir: str) -> str:
    """Locate matching template file, falling back to en if specific language is missing."""
    candidate = os.path.join(template_dir, f"welcome.{lang}.eml")
    if os.path.isfile(candidate):
        return candidate
    fallback = os.path.join(template_dir, "welcome.en.eml")
    if os.path.isfile(fallback):
        return fallback
    return ""

def main():
    user = os.environ.get("USER", "").strip()
    home = os.environ.get("HOME", "").strip()

    # If home is not set, derive from standard /home/vmail/<user>
    if not home and user:
        home = os.path.join("/home/vmail", user)

    if not home:
        # Cannot determine user directory, exit safely
        return 0

    sent_flag = os.path.join(home, ".welcome_sent")
    lock_dir = os.path.join(home, ".welcome_lock")

    # Fast short-circuit: already sent
    if os.path.exists(sent_flag):
        return 0

    # Atomic lock acquisition using mkdir
    acquired = False
    try:
        os.makedirs(home, exist_ok=True)
        os.mkdir(lock_dir)
        acquired = True
    except FileExistsError:
        # Lock exists, check if stale (> 60 seconds)
        try:
            stat = os.stat(lock_dir)
            if time.time() - stat.st_mtime > 60:
                try:
                    os.rmdir(lock_dir)
                    os.mkdir(lock_dir)
                    acquired = True
                except Exception:
                    acquired = False
            else:
                acquired = False
        except Exception:
            acquired = False
    except Exception as e:
        sys.stderr.write(f"[welcome-email] Failed to create lock dir: {e}\n")
        return 0

    if not acquired:
        # Another process is currently provisioning, exit gracefully
        return 0

    try:
        # Double check flag after acquiring lock
        if os.path.exists(sent_flag):
            return 0

        # Read LDAP preferredLanguage passed via Dovecot user_attrs (USER_LANG or user_lang)
        raw_lang = os.environ.get("USER_LANG") or os.environ.get("user_lang") or ""
        target_lang = detect_language(raw_lang)

        # Locate template directory
        template_dir = os.environ.get("WELCOME_TEMPLATE_DIR", TEMPLATE_DIR_DEFAULT)
        if not os.path.isdir(template_dir):
            # Fallback to local script relative directory if running in dev/test
            script_dir = os.path.dirname(os.path.abspath(__file__))
            dev_template_dir = os.path.join(os.path.dirname(script_dir), "welcome_templates")
            if os.path.isdir(dev_template_dir):
                template_dir = dev_template_dir

        template_file = find_template(target_lang, template_dir)
        if not template_file:
            sys.stderr.write(f"[welcome-email] No template found for lang '{target_lang}' in {template_dir}\n")
            return 0

        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Derive variables
        domain = os.environ.get("DOMAIN_NAME", "").strip()
        host = os.environ.get("HOST_NAME", "").strip()

        # Determine full email address
        if "@" in user:
            email_addr = user
        elif "@" in os.path.basename(home):
            email_addr = os.path.basename(home)
        elif domain:
            email_addr = f"{user}@{domain}"
        else:
            email_addr = user

        account = email_addr.split("@")[0] if "@" in email_addr else user

        if not domain and "@" in email_addr:
            domain = email_addr.split("@")[1]

        if not host:
            host = domain if domain else socket.getfqdn()

        date_str = email.utils.formatdate(localtime=True)
        msg_id = email.utils.make_msgid(domain=domain if domain else None)

        # Substitute variables
        replacements = {
            "${EMAIL}": email_addr,
            "${ACCOUNT}": account,
            "${DOMAIN_NAME}": domain,
            "${HOST_NAME}": host,
            "${DATE}": date_str,
            "${MESSAGE_ID}": msg_id,
        }
        for k, v in replacements.items():
            content = content.replace(k, v)

        # Ensure Maildir directories exist
        maildir = os.path.join(home, "Maildir")
        tmp_dir = os.path.join(maildir, "tmp")
        new_dir = os.path.join(maildir, "new")
        cur_dir = os.path.join(maildir, "cur")

        os.makedirs(tmp_dir, exist_ok=True)
        os.makedirs(new_dir, exist_ok=True)
        os.makedirs(cur_dir, exist_ok=True)

        # Generate unique Maildir filename: <seconds>.M<microseconds>P<pid>Q1.<hostname>
        now = time.time()
        sec = int(now)
        usec = int((now - sec) * 1000000)
        pid = os.getpid()
        hostname = socket.gethostname()
        filename = f"{sec}.M{usec:06d}P{pid}Q1.{hostname}"

        tmp_file = os.path.join(tmp_dir, filename)
        new_file = os.path.join(new_dir, filename)

        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(content)

        try:
            os.chmod(tmp_file, 0o600)
        except Exception:
            pass

        # Atomic rename into new/
        os.replace(tmp_file, new_file)

        # Write sent flag to permanently prevent future runs
        with open(sent_flag, "w", encoding="utf-8") as f:
            f.write(f"Sent: {datetime.datetime.now().isoformat()}\nEmail: {email_addr}\nLang: {target_lang}\nTemplate: {os.path.basename(template_file)}\n")

    except Exception as e:
        sys.stderr.write(f"[welcome-email] Error provisioning welcome email: {e}\n")
    finally:
        # Always remove atomic lock
        try:
            if os.path.exists(lock_dir):
                os.rmdir(lock_dir)
        except Exception:
            shutil.rmtree(lock_dir, ignore_errors=True)

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"[welcome-email] Unexpected error: {e}\n")
        sys.exit(0)
