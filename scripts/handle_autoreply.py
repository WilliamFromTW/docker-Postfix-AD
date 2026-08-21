#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email-Driven Auto-Reply (Vacation) Handler for Postfix + Dovecot Pigeonhole Sieve
Listens via Sieve Extprograms pipe on standard input.
"""

import sys
import os
import re
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr, formatdate
from datetime import datetime, time
import subprocess

TZ_OFFSET_STR = "+08:00"
TZ_SIEVE_ZONE = "+0800"
VMAIL_BASE = "/home/vmail"
DEFAULT_DAYS = 1

def is_chinese_text(s):
    if not s:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", s))

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

def get_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
        if not body:
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        body = re.sub(r"<[^>]+>", " ", body)
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body.strip()

def parse_date_str(s, default_time=time.min):
    now = datetime.now()
    s = s.strip()
    
    # 1. Full datetime: YYYY-MM-DD HH:MM or YYYY/MM/DD HH:MM
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$", s)
    if m:
        sec = int(m.group(6)) if m.group(6) else (59 if default_time == time.max else 0)
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), sec)

    # 2. Full date: YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        t = default_time
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), t.hour, t.minute, t.second)

    # 3. Short date: MM-DD or MM/DD
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
    if m:
        year = now.year
        month = int(m.group(1))
        day = int(m.group(2))
        t = default_time
        return datetime(year, month, day, t.hour, t.minute, t.second)

    return None

def send_notification(to_addr, subject, body_text):
    msg = MIMEText(body_text, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Auto-Reply Service <postmaster@{to_addr.split('@')[-1]}>"
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Auto-Submitted"] = "auto-generated"

    sendmail_paths = ["/usr/sbin/sendmail", "/usr/lib/sendmail"]
    sendmail_bin = None
    for p in sendmail_paths:
        if os.path.exists(p):
            sendmail_bin = p
            break

    if sendmail_bin:
        try:
            proc = subprocess.Popen([sendmail_bin, "-t", "-oi"], stdin=subprocess.PIPE)
            proc.communicate(input=msg.as_bytes())
        except Exception as e:
            sys.stderr.write(f"Error sending confirmation email: {e}\n")

def escape_sieve_string(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')

def find_user_sieve_dir(email_addr):
    local_part = email_addr.split("@")[0].lower()
    cand1 = os.path.join(VMAIL_BASE, email_addr.lower(), "sieve")
    cand2 = os.path.join(VMAIL_BASE, local_part, "sieve")
    
    if os.path.exists(cand1):
        return cand1
    if os.path.exists(cand2):
        return cand2
    
    os.makedirs(cand1, exist_ok=True)
    return cand1

def compile_sieve(sieve_path):
    sievec_paths = ["/usr/bin/sievec", "/usr/sbin/sievec"]
    sievec_bin = None
    for p in sievec_paths:
        if os.path.exists(p):
            sievec_bin = p
            break
    if sievec_bin and os.path.exists(sieve_path):
        subprocess.run([sievec_bin, sieve_path], check=False)

def main():
    raw_email = sys.stdin.buffer.read()
    if not raw_email:
        sys.exit(0)

    try:
        msg = email.message_from_bytes(raw_email)
    except Exception as e:
        sys.stderr.write(f"Failed to parse email: {e}\n")
        sys.exit(0)

    from_header = decode_mime_words(msg.get("From", ""))
    to_header = decode_mime_words(msg.get("To", ""))
    subject_raw = decode_mime_words(msg.get("Subject", ""))
    body = get_email_body(msg)

    _, from_addr = parseaddr(from_header)
    _, to_addr = parseaddr(to_header)

    from_addr = from_addr.lower().strip()
    to_addr = to_addr.lower().strip()

    if not from_addr or not to_addr:
        sys.exit(0)

    # Verify sender is setting for themselves (From == To)
    if from_addr != to_addr:
        sys.stderr.write(f"Sender {from_addr} does not match recipient {to_addr}. Ignoring.\n")
        sys.exit(0)

    # Check for keyword in subject
    trigger_pattern = r"#(?:autoreply|vacation|休假|不在|出差|請假)(?:\s+(.*))?$"
    match = re.search(trigger_pattern, subject_raw, re.IGNORECASE)
    if not match:
        sys.exit(0)

    param_str = (match.group(1) or "").strip()
    is_chinese = is_chinese_text(subject_raw)

    sieve_dir = find_user_sieve_dir(from_addr)
    sieve_file = os.path.join(sieve_dir, "dovecot.sieve")

    # 1. Turn OFF
    if re.search(r"^(off|cancel|stop|關閉|取消|停用)", param_str, re.IGNORECASE):
        content = "# Auto-Reply Disabled\nrequire [\"fileinto\"];\nkeep;\n"
        with open(sieve_file, "w", encoding="utf-8") as f:
            f.write(content)
        compile_sieve(sieve_file)

        try:
            os.chown(sieve_file, 1001, 1001)
            svbin = sieve_file.replace(".sieve", ".svbin")
            if os.path.exists(svbin):
                os.chown(svbin, 1001, 1001)
        except Exception:
            pass

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if is_chinese:
            send_notification(
                from_addr,
                "【自動回覆通知】自動回覆功能已停用 (Auto-Reply Disabled)",
                f"您好：\n\n您的電子郵件自動回覆（Auto-Reply / Vacation）已於系統中成功停用。\n\n帳號：{from_addr}\n更新時間：{now_str} (UTC+8 台北時間)\n"
            )
        else:
            send_notification(
                from_addr,
                "[Auto-Reply Notification] Auto-Reply has been disabled",
                f"Hello,\n\nYour email Auto-Reply / Vacation responder has been successfully disabled.\n\nAccount: {from_addr}\nUpdated at: {now_str} (UTC+8 Taipei Time)\n"
            )
        sys.exit(0)

    # 2. Parse Date Range or Always ON
    start_dt = None
    end_dt = None
    custom_subject = ""
    is_always_on = False

    if re.search(r"^on(?:\s+(.*))?$", param_str, re.IGNORECASE):
        is_always_on = True
        m_on = re.search(r"^on(?:\s+(.*))?$", param_str, re.IGNORECASE)
        custom_subject = (m_on.group(1) or "").strip()
    else:
        date_range_match = re.search(r"^([0-9\-\/\:\s]+)(?:~|\-|至|到|to)([0-9\-\/\:\s]+)(?:\s+(.*))?$", param_str)
        if date_range_match:
            s_raw = date_range_match.group(1).strip()
            e_raw = date_range_match.group(2).strip()
            custom_subject = (date_range_match.group(3) or "").strip()
            
            start_dt = parse_date_str(s_raw, default_time=time(0, 0, 0))
            end_dt = parse_date_str(e_raw, default_time=time(23, 59, 59))

    # Determine Reply Subject and Body
    if not custom_subject:
        custom_subject = "休假中 / Out of Office" if is_chinese else "Out of Office"
    
    if is_chinese:
        reply_subject = f"【自動回覆】{custom_subject}"
    else:
        reply_subject = f"[Auto-Reply] {custom_subject}"

    user_name = from_addr.split('@')[0]
    if not body:
        if is_chinese:
            if start_dt and end_dt:
                body = (
                    f"您好：\n\n"
                    f"我目前於 {start_dt.strftime('%Y-%m-%d')} 至 {end_dt.strftime('%Y-%m-%d')} 休假/公出中，期間無法即時查閱郵件。\n"
                    f"若有緊急事務請電洽，一般信件將於銷假後儘速處理。\n\n"
                    f"祝好\n{user_name}"
                )
            else:
                body = (
                    f"您好：\n\n"
                    f"我目前公出/休假中，期間無法即時查閱郵件。\n"
                    f"若有緊急事務請電洽，一般信件將於銷假後儘速處理。\n\n"
                    f"祝好\n{user_name}"
                )
        else:
            if start_dt and end_dt:
                body = (
                    f"Hello,\n\n"
                    f"I am currently out of office from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')} and cannot check emails immediately.\n"
                    f"If you have urgent matters, please call. Other emails will be processed upon my return.\n\n"
                    f"Best regards,\n{user_name}"
                )
            else:
                body = (
                    f"Hello,\n\n"
                    f"I am currently out of office and cannot check emails immediately.\n"
                    f"If you have urgent matters, please call. Other emails will be processed upon my return.\n\n"
                    f"Best regards,\n{user_name}"
                )

    escaped_body = escape_sieve_string(body)
    escaped_subj = escape_sieve_string(reply_subject)

    # Build Sieve Script with Bot & DMARC/Bounce Protection
    sieve_lines = [
        'require ["vacation", "date", "relational"];',
        '',
        '# Smart Filter: Do not auto-reply to noreply, bots, DMARC reports, or bounces',
        'if not anyof (',
        '  header :matches "From" ["*noreply*", "*no-reply*", "*donotreply*", "*mailer-daemon*", "*postmaster*", "*dmarc*", "*bounce*", "*notification*"],',
        '  header :matches "Sender" ["*noreply*", "*no-reply*", "*donotreply*", "*mailer-daemon*", "*postmaster*", "*dmarc*", "*bounce*", "*notification*"],',
        '  header :matches "Precedence" ["bulk", "list", "junk", "auto_reply"],',
        '  header :matches "Auto-Submitted" ["auto-generated", "auto-replied"],',
        '  header :contains "Content-Type" "multipart/report"',
        ') {'
    ]

    if is_always_on or not (start_dt and end_dt):
        sieve_lines.extend([
            '  vacation',
            f'    :days {DEFAULT_DAYS}',
            f'    :from "{from_addr}"',
            f'    :subject "{escaped_subj}"',
            f'    "{escaped_body}";',
            '}',
            'keep;'
        ])
        time_desc = "即刻生效，直到寄信停用" if is_chinese else "Active immediately until turned off"
        time_notif_short = "即刻生效" if is_chinese else "Active immediately"
    else:
        iso_start = f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')}{TZ_OFFSET_STR}"
        iso_end = f"{end_dt.strftime('%Y-%m-%dT%H:%M:%S')}{TZ_OFFSET_STR}"

        sieve_lines.extend([
            '  if allof (',
            f'    currentdate :zone "{TZ_SIEVE_ZONE}" :value "ge" "iso8601" "{iso_start}",',
            f'    currentdate :zone "{TZ_SIEVE_ZONE}" :value "le" "iso8601" "{iso_end}"',
            '  ) {',
            '    vacation',
            f'      :days {DEFAULT_DAYS}',
            f'      :from "{from_addr}"',
            f'      :subject "{escaped_subj}"',
            f'      "{escaped_body}";',
            '  }',
            '}',
            'keep;'
        ])
        if is_chinese:
            time_desc = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8 台北時間)"
            time_notif_short = f"{start_dt.strftime('%Y-%m-%d')} 至 {end_dt.strftime('%Y-%m-%d')}"
        else:
            time_desc = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} to {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8 Taipei Time)"
            time_notif_short = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"

    sieve_content = "\n".join(sieve_lines) + "\n"

    with open(sieve_file, "w", encoding="utf-8") as f:
        f.write(sieve_content)

    compile_sieve(sieve_file)

    try:
        os.chown(sieve_file, 1001, 1001)
        svbin = sieve_file.replace(".sieve", ".svbin")
        if os.path.exists(svbin):
            os.chown(svbin, 1001, 1001)
    except Exception:
        pass

    # Send Success Notification Email
    if is_chinese:
        notif_subj = f"【自動回覆通知】已成功啟用自動回覆 (生效期間：{time_notif_short})"
        notif_body = (
            f"=====================================================\n"
            f"✅ 電子郵件自動回覆 (Auto-Reply) 已成功設定並啟用！\n"
            f"=====================================================\n\n"
            f"• 帳號：{from_addr}\n"
            f"• 生效區間：{time_desc}\n"
            f"• 防轟炸頻率：同一寄件者 24 小時內最多回覆 1 次 (:days {DEFAULT_DAYS})\n"
            f"• 自動回覆主旨：{reply_subject}\n\n"
            f"【自動回覆內文預覽】：\n"
            f"-----------------------------------------------------\n"
            f"{body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 如欲提前關閉自動回覆，請隨時寄一封主旨為 #autoreply off 的郵件給自己即可停用。\n"
        )
    else:
        notif_subj = f"[Auto-Reply Notification] Auto-Reply enabled successfully (Active: {time_notif_short})"
        notif_body = (
            f"=====================================================\n"
            f"✅ Email Auto-Reply has been successfully enabled!\n"
            f"=====================================================\n\n"
            f"• Account: {from_addr}\n"
            f"• Active Period: {time_desc}\n"
            f"• Frequency Limit: At most 1 reply per 24 hours to the same sender (:days {DEFAULT_DAYS})\n"
            f"• Auto-Reply Subject: {reply_subject}\n\n"
            f"【Auto-Reply Body Preview】:\n"
            f"-----------------------------------------------------\n"
            f"{body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 To turn off auto-reply at any time, simply send an email to yourself with subject: #autoreply off\n"
        )

    send_notification(from_addr, notif_subj, notif_body)

if __name__ == "__main__":
    main()
