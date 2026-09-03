#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email-Driven Auto-Reply (Vacation) Handler for Postfix + Dovecot Pigeonhole Sieve
Supports:
1. Legacy regex commands: #autoreply, #vacation, #休假, #不在, #出差, #請假
2. Local Ollama LLM Natural Language Understanding (Traditional Chinese, Simplified Chinese, Vietnamese, English)
3. Graceful fallback to regex if Ollama is unreachable, unconfigured, or timed out.
"""

import sys
import os
import re
import json
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr, formatdate
from datetime import datetime, time, timedelta
import subprocess
import urllib.request
import urllib.error

try:
    import syslog
    HAS_SYSLOG = True
except ImportError:
    HAS_SYSLOG = False

def log_maillog(msg, priority=None):
    """
    Writes log message directly to /var/log/maillog via syslog LOG_MAIL.
    Falls back gracefully to sys.stderr if syslog is not available (e.g. non-POSIX).
    """
    if HAS_SYSLOG:
        try:
            p = priority if priority is not None else syslog.LOG_INFO
            syslog.openlog(ident="handle_autoreply", facility=syslog.LOG_MAIL)
            syslog.syslog(p, msg)
        except Exception:
            pass
    sys.stderr.write(f"handle_autoreply: {msg}\n")

TZ_OFFSET_STR = "+08:00"
TZ_SIEVE_ZONE = "+0800"
VMAIL_BASE = "/home/vmail"
DEFAULT_DAYS = 1

def load_ollama_config():
    """
    Dovecot Pigeonhole sieve_extprograms restricts environment variables passed to child scripts
    (only HOME, USER, HOST, SENDER, RECIPIENT, ORIG_RECIPIENT are passed).
    This function discovers OLLAMA_* and DEFAULT_LANG variables through multiple fallback channels:
    1. os.environ
    2. /etc/dovecot/ollama.env / /etc/mailserver_env.json
    3. /proc/1/environ (Docker container PID 1 environment)
    """
    conf = {
        "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "").strip().rstrip("/"),
        "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL", "").strip(),
        "OLLAMA_TIMEOUT": os.environ.get("OLLAMA_TIMEOUT", "").strip(),
        "DEFAULT_LANG": os.environ.get("DEFAULT_LANG", os.environ.get("AUTOREPLY_LANG", "")).strip(),
    }

    env_files = ["/etc/dovecot/ollama.env", "/etc/mailserver_env.json", "/etc/mailserver.env"]
    for ef in env_files:
        if os.path.exists(ef):
            try:
                if ef.endswith(".json"):
                    with open(ef, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for k in ["OLLAMA_HOST", "OLLAMA_MODEL", "OLLAMA_TIMEOUT", "DEFAULT_LANG"]:
                            if not conf.get(k) and k in data and data[k]:
                                conf[k] = str(data[k]).strip()
                else:
                    with open(ef, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip("'").strip('"')
                                if k in conf and not conf[k]:
                                    conf[k] = v
            except Exception:
                pass

    if not conf["OLLAMA_HOST"] or not conf["DEFAULT_LANG"]:
        try:
            if os.path.exists("/proc/1/environ"):
                with open("/proc/1/environ", "rb") as f:
                    content = f.read()
                for item in content.split(b"\0"):
                    if item.startswith(b"OLLAMA_HOST=") and not conf["OLLAMA_HOST"]:
                        conf["OLLAMA_HOST"] = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip().rstrip("/")
                    elif item.startswith(b"OLLAMA_MODEL=") and not conf["OLLAMA_MODEL"]:
                        conf["OLLAMA_MODEL"] = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
                    elif item.startswith(b"OLLAMA_TIMEOUT=") and not conf["OLLAMA_TIMEOUT"]:
                        conf["OLLAMA_TIMEOUT"] = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
                    elif item.startswith(b"DEFAULT_LANG=") and not conf["DEFAULT_LANG"]:
                        conf["DEFAULT_LANG"] = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
        except Exception:
            pass

    if not conf["OLLAMA_MODEL"]:
        conf["OLLAMA_MODEL"] = "qwen2.5:7b"
    try:
        timeout = float(conf["OLLAMA_TIMEOUT"]) if conf["OLLAMA_TIMEOUT"] else 180.0
    except Exception:
        timeout = 180.0

    return conf["OLLAMA_HOST"], conf["OLLAMA_MODEL"], timeout, conf["DEFAULT_LANG"]

OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT, DEFAULT_LANG = load_ollama_config()

VIETNAMESE_CHARS_RE = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

TRADITIONAL_CHARS = set("開關後發點經會過這還個為國來對說與時麼機學請銷體辦讓總聽見話圖雙處幾萬電廣東車長門專變報業題頭動實導單無愛兒區認氣質視許資標農選計濟調")
SIMPLIFIED_CHARS = set("开关后发点经会过这还个为国来对说与时么机学请销体办让总听见话图双处几万电广东车长门专变报业题头动实导单无爱儿区认气质视许资标农选计济调")

def detect_language(text, fallback="zh-TW"):
    """
    Deterministically detects whether text is Traditional Chinese, Simplified Chinese,
    Vietnamese, or English. If DEFAULT_LANG is configured, respects user's preference.
    """
    if DEFAULT_LANG and DEFAULT_LANG.lower() in ["en", "zh-tw", "zh-cn", "vi"]:
        # Map case-insensitively
        m = {"en": "en", "zh-tw": "zh-TW", "zh-cn": "zh-CN", "vi": "vi"}
        return m.get(DEFAULT_LANG.lower(), fallback)

    if not text:
        return fallback

    text_lower = text.lower()
    if VIETNAMESE_CHARS_RE.search(text) or any(w in text_lower for w in ["nghỉ phép", "công tác", "vắng mặt", "trả lời tự động", "hủy"]):
        return "vi"

    t_count = sum(1 for c in text if c in TRADITIONAL_CHARS)
    s_count = sum(1 for c in text if c in SIMPLIFIED_CHARS)

    if s_count > t_count:
        return "zh-CN"
    if t_count > 0:
        return "zh-TW"
    if CHINESE_RE.search(text):
        return "zh-TW"

    return "en"

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
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$", s)
    if m:
        sec = int(m.group(6)) if m.group(6) else (59 if default_time == time.max else 0)
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), sec)

    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        t = default_time
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), t.hour, t.minute, t.second)

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

def disable_autoreply(from_addr, lang="zh-TW"):
    sieve_dir = find_user_sieve_dir(from_addr)
    sieve_file = os.path.join(sieve_dir, "dovecot.sieve")
    cfg_file = os.path.join(sieve_dir, "autoreply_config.json")

    content = "# Auto-Reply Disabled\nrequire [\"fileinto\"];\nkeep;\n"
    with open(sieve_file, "w", encoding="utf-8") as f:
        f.write(content)
    compile_sieve(sieve_file)

    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({"enabled": False}, f)

    try:
        os.chown(sieve_file, 1001, 1001)
        os.chown(cfg_file, 1001, 1001)
        svbin = sieve_file.replace(".sieve", ".svbin")
        if os.path.exists(svbin):
            os.chown(svbin, 1001, 1001)
    except Exception:
        pass

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notices = {
        "zh-TW": (
            "【自動回覆通知】自動回覆功能已成功停用",
            f"您好：\n\n您的電子郵件自動回覆（Auto-Reply / Vacation）已於系統中成功停用。\n\n帳號：{from_addr}\n更新時間：{now_str} (UTC+8 台北時間)\n"
        ),
        "zh-CN": (
            "【自动回复通知】自动回复功能已成功停用",
            f"您好：\n\n您的电子邮件自动回复（Auto-Reply / Vacation）已在系统中成功停用。\n\n账号：{from_addr}\n更新时间：{now_str} (UTC+8 台北时间)\n"
        ),
        "vi": (
            "[Thông báo tự động trả lời] Tính năng trả lời tự động đã được tắt",
            f"Xin chào:\n\nTính năng trả lời tự động email (Auto-Reply / Vacation) của bạn đã được tắt thành công.\n\nTài khoản: {from_addr}\nThời gian cập nhật: {now_str} (UTC+8 Giờ Đài Bắc)\n"
        ),
        "en": (
            "[Auto-Reply Notification] Auto-Reply has been disabled",
            f"Hello,\n\nYour email Auto-Reply / Vacation responder has been successfully disabled.\n\nAccount: {from_addr}\nUpdated at: {now_str} (UTC+8 Taipei Time)\n"
        )
    }
    subj, body = notices.get(lang, notices["zh-TW"])
    send_notification(from_addr, subj, body)
    log_maillog(f"Auto-reply disabled for {from_addr} (lang: {lang})", syslog.LOG_INFO if HAS_SYSLOG else None)

def get_standard_templates(lang, user_name, start_str, end_str):
    templates = {
        "zh-TW": {
            "subject": "【自動回覆】休假中 / Out of Office",
            "body": (
                f"您好：\n\n"
                f"我目前於 {start_str} 至 {end_str} 休假/公出中，期間無法即時查閱郵件。\n"
                f"若有緊急事務請電洽，一般信件將於銷假後儘速處理。\n\n"
                f"祝好\n{user_name}"
            )
        },
        "zh-CN": {
            "subject": "【自动回复】休假中 / Out of Office",
            "body": (
                f"您好：\n\n"
                f"我目前于 {start_str} 至 {end_str} 休假/公出中，期间无法即时查阅邮件。\n"
                f"若有紧急事务请电洽，一般信件将于销假后尽快处理。\n\n"
                f"祝好\n{user_name}"
            )
        },
        "vi": {
            "subject": "[Tự động trả lời] Vắng mặt / Out of Office",
            "body": (
                f"Xin chào:\n\n"
                f"Hiện tại tôi đang nghỉ phép/đi công tác từ ngày {start_str} đến ngày {end_str} và không thể kiểm tra email thường xuyên.\n"
                f"Nếu có việc khẩn cấp xin vui lòng liên hệ qua điện thoại, các email khác sẽ được xử lý sau khi tôi trở lại làm việc.\n\n"
                f"Trân trọng\n{user_name}"
            )
        },
        "en": {
            "subject": "[Auto-Reply] Out of Office",
            "body": (
                f"Hello,\n\n"
                f"I am currently out of office from {start_str} to {end_str} and cannot check emails immediately.\n"
                f"If you have urgent matters, please call. Other emails will be processed upon my return.\n\n"
                f"Best regards,\n{user_name}"
            )
        }
    }
    return templates.get(lang, templates["zh-TW"])

def call_ollama_parser(subject_raw, body_raw):
    """
    Calls Ollama on independent GPU server using JSON mode.
    Returns dict with parsed fields, or None if offline/error.
    """
    if not OLLAMA_HOST:
        return None

    now = datetime.now()
    weekday_names = ["Monday/星期一", "Tuesday/星期二", "Wednesday/星期三", "Thursday/星期四", "Friday/星期五", "Saturday/星期六", "Sunday/星期日"]
    weekday_str = weekday_names[now.weekday()]
    
    system_prompt = f"""You are an intelligent email out-of-office (vacation/leave/business trip) parser for an enterprise email server.
The current anchor date and time is: {now.strftime('%Y-%m-%d %H:%M:%S')} ({weekday_str}), Timezone: UTC+8 (Asia/Taipei).
User input may be in Traditional Chinese (zh-TW), Simplified Chinese (zh-CN), Vietnamese (vi), or English (en).

Analyze the user's email Subject and optional Body to determine vacation/leave intent.
Requirements:
1. "is_vacation": true if user intends to set, take, or cancel a vacation, leave, day off, out-of-office, or business trip. Otherwise false.
2. "action": "enable" (set auto-reply) | "disable" (cancel/stop/销假/hủy/turn off auto-reply) | "ignore" (not a vacation instruction).
3. "start_date": "YYYY-MM-DD" formatted start date. If morning/afternoon/single day, the date unit is that full date. If relative (e.g. "tomorrow", "下週三", "thứ 4 tuần sau"), calculate the exact date based on the anchor date. If ambiguous or not provided, return null.
4. "end_date": "YYYY-MM-DD" formatted end date. If single-day leave, end_date must equal start_date. If relative range (e.g. "下週三到五"), end_date is the last day. If ambiguous or not provided, return null.
5. "detected_lang": "zh-TW" | "zh-CN" | "vi" | "en".
6. "reason": Brief summary of reason (e.g. "休假", "出差", "nghỉ phép", "vacation").

Respond ONLY with valid JSON matching this schema:
{{
  "is_vacation": true,
  "action": "enable",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "detected_lang": "zh-TW",
  "reason": "休假"
}}"""

    user_content = f"Subject: {subject_raw}\nBody: {body_raw}"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "format": "json"
    }

    url = f"{OLLAMA_HOST}/api/chat"
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

    t0 = datetime.now()
    log_maillog(f"Querying Ollama NLU at {OLLAMA_HOST} (model: {OLLAMA_MODEL}, timeout: {OLLAMA_TIMEOUT}s)...", syslog.LOG_INFO if HAS_SYSLOG else None)

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            if resp.status == 200:
                elapsed = (datetime.now() - t0).total_seconds()
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_content = resp_data.get("message", {}).get("content", "")
                result = json.loads(msg_content)
                log_maillog(
                    f"Ollama inference succeeded in {elapsed:.2f}s: action={result.get('action')}, "
                    f"is_vacation={result.get('is_vacation')}, start={result.get('start_date')}, "
                    f"end={result.get('end_date')}, lang={result.get('detected_lang')}",
                    syslog.LOG_INFO if HAS_SYSLOG else None
                )
                return result
    except Exception as e:
        elapsed = (datetime.now() - t0).total_seconds()
        log_maillog(f"Ollama call failed or timed out after {elapsed:.2f}s ({OLLAMA_HOST}): {e}", syslog.LOG_WARNING if HAS_SYSLOG else None)
        return None

    return None

def apply_autoreply(from_addr, start_dt, end_dt, is_always_on, custom_subject, body, lang="zh-TW", ai_parsed=False):
    sieve_dir = find_user_sieve_dir(from_addr)
    sieve_file = os.path.join(sieve_dir, "dovecot.sieve")
    cfg_file = os.path.join(sieve_dir, "autoreply_config.json")
    user_name = from_addr.split('@')[0]

    start_str = start_dt.strftime('%Y-%m-%d') if start_dt else ""
    end_str = end_dt.strftime('%Y-%m-%d') if end_dt else ""

    # Determine body & subject
    std_info = get_standard_templates(lang, user_name, start_str, end_str)
    if not custom_subject:
        reply_subject = std_info["subject"]
    else:
        prefix = "【自動回覆】" if lang in ["zh-TW", "zh-CN"] else ("[Tự động trả lời] " if lang == "vi" else "[Auto-Reply] ")
        reply_subject = f"{prefix}{custom_subject}"

    if not body:
        final_body = std_info["body"]
    else:
        final_body = body

    # Check if a previous auto-reply was already active
    was_previously_enabled = False
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                old_cfg = json.load(f)
                if old_cfg.get("enabled"):
                    was_previously_enabled = True
        except Exception:
            pass

    cfg_data = {
        "enabled": True,
        "owner": from_addr,
        "subject": reply_subject,
        "body": final_body,
        "is_always_on": is_always_on,
        "start_ts": start_dt.timestamp() if start_dt else None,
        "end_ts": end_dt.timestamp() if end_dt else None,
        "lang": lang,
        "ai_parsed": ai_parsed
    }
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(cfg_data, f, ensure_ascii=False, indent=2)

    sieve_content = "# Auto-Reply Enabled (Managed via Global Sieve & send_delayed_vacation.py)\nrequire [\"fileinto\"];\nkeep;\n"
    with open(sieve_file, "w", encoding="utf-8") as f:
        f.write(sieve_content)
    compile_sieve(sieve_file)

    try:
        os.chown(sieve_file, 1001, 1001)
        os.chown(cfg_file, 1001, 1001)
        svbin = sieve_file.replace(".sieve", ".svbin")
        if os.path.exists(svbin):
            os.chown(svbin, 1001, 1001)
    except Exception:
        pass

    # Send Notification Email
    ai_tag = " [🤖 AI 智慧解析]" if ai_parsed else ""
    if is_always_on or not (start_dt and end_dt):
        time_desc_map = {
            "zh-TW": "即刻生效，直到寄信停用",
            "zh-CN": "即刻生效，直到发信停用",
            "vi": "Có hiệu lực ngay lập tức cho đến khi tắt",
            "en": "Active immediately until turned off"
        }
        time_notif_short = "即刻生效"
        time_desc = time_desc_map.get(lang, time_desc_map["zh-TW"])
    else:
        time_desc = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)"
        time_notif_short = f"{start_str} ~ {end_str}"

    overwrite_tip_map = {
        "zh-TW": "📌 提示：已自動為您覆蓋先前的休假回覆設定。\n" if was_previously_enabled else "",
        "zh-CN": "📌 提示：已自动为您覆盖先前的休假回复设置。\n" if was_previously_enabled else "",
        "vi": "📌 Ghi chú: Đã tự động ghi đè cài đặt nghỉ phép trước đó của bạn.\n" if was_previously_enabled else "",
        "en": "📌 Note: Automatically overwritten your previous out-of-office setting.\n" if was_previously_enabled else ""
    }
    overwrite_tip = overwrite_tip_map.get(lang, "")

    notifications = {
        "zh-TW": (
            f"【自動回覆通知】已成功啟用自動回覆 (生效期間：{time_notif_short}){ai_tag}",
            f"=====================================================\n"
            f"✅ 電子郵件自動回覆 (Auto-Reply) 已成功設定並啟用！{ai_tag}\n"
            f"=====================================================\n\n"
            f"• 帳號：{from_addr}\n"
            f"• 生效區間：{time_desc}\n"
            f"• 回應延遲：15 秒自然延遲發信（防機器人探測）\n"
            f"• 防轟炸頻率：同一寄件者 24 小時內最多回覆 1 次 (:days {DEFAULT_DAYS})\n"
            f"• 自動回覆主旨：{reply_subject}\n\n"
            f"{overwrite_tip}"
            f"【自動回覆內文預覽】：\n"
            f"-----------------------------------------------------\n"
            f"{final_body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 如欲提前關閉自動回覆，請隨時寄信「取消休假」或主旨「#autoreply off」給自己即可停用。\n"
        ),
        "zh-CN": (
            f"【自动回复通知】已成功启用自动回复 (生效期间：{time_notif_short}){ai_tag}",
            f"=====================================================\n"
            f"✅ 电子邮件自动回复 (Auto-Reply) 已成功设置并启用！{ai_tag}\n"
            f"=====================================================\n\n"
            f"• 账号：{from_addr}\n"
            f"• 生效区间：{time_desc}\n"
            f"• 响应延迟：15 秒自然延迟发信（防机器人探测）\n"
            f"• 防轰炸频率：同一发件人 24 小时内最多回复 1 次 (:days {DEFAULT_DAYS})\n"
            f"• 自动回复主旨：{reply_subject}\n\n"
            f"{overwrite_tip}"
            f"【自动回复正文预览】：\n"
            f"-----------------------------------------------------\n"
            f"{final_body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 如欲提前关闭自动回复，请随时发信“取消休假”或主题“#autoreply off”给自己即可停用。\n"
        ),
        "vi": (
            f"[Thông báo tự động trả lời] Đã kích hoạt trả lời tự động ({time_notif_short}){ai_tag}",
            f"=====================================================\n"
            f"✅ Tính năng trả lời tự động email đã được kích hoạt thành công!{ai_tag}\n"
            f"=====================================================\n\n"
            f"• Tài khoản: {from_addr}\n"
            f"• Thời gian hiệu lực: {time_desc}\n"
            f"• Độ trễ phản hồi: Tự động gửi thư sau 15 giây\n"
            f"• Tần suất giới hạn: Tối đa 1 lần trong 24 giờ cho cùng 1 người gửi (:days {DEFAULT_DAYS})\n"
            f"• Tiêu đề phản hồi: {reply_subject}\n\n"
            f"{overwrite_tip}"
            f"【Nội dung phản hồi xem trước】:\n"
            f"-----------------------------------------------------\n"
            f"{final_body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 Để hủy trả lời tự động sớm, bạn chỉ cần gửi email 'Hủy nghỉ phép' hoặc tiêu đề '#autoreply off' cho chính mình.\n"
        ),
        "en": (
            f"[Auto-Reply Notification] Auto-Reply enabled successfully ({time_notif_short}){ai_tag}",
            f"=====================================================\n"
            f"✅ Email Auto-Reply has been successfully enabled!{ai_tag}\n"
            f"=====================================================\n\n"
            f"• Account: {from_addr}\n"
            f"• Active Period: {time_desc}\n"
            f"• Response Delay: 15-second natural sending delay\n"
            f"• Frequency Limit: At most 1 reply per 24 hours to the same sender (:days {DEFAULT_DAYS})\n"
            f"• Auto-Reply Subject: {reply_subject}\n\n"
            f"{overwrite_tip}"
            f"【Auto-Reply Body Preview】:\n"
            f"-----------------------------------------------------\n"
            f"{final_body}\n"
            f"-----------------------------------------------------\n\n"
            f"💡 To turn off auto-reply early, simply send an email saying 'cancel out of office' or subject '#autoreply off' to yourself.\n"
        )
    }
    subj, notif_text = notifications.get(lang, notifications["zh-TW"])
    send_notification(from_addr, subj, notif_text)
    engine_name = "Ollama AI" if ai_parsed else "Regex"
    action_type = "updated (overwrote previous)" if was_previously_enabled else "enabled"
    log_maillog(f"Auto-reply {action_type} for {from_addr} via {engine_name} ({time_notif_short}, always_on={is_always_on}, lang={lang})", syslog.LOG_INFO if HAS_SYSLOG else None)

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

    # 1. Verify self-sent email (From == To)
    if from_addr != to_addr:
        sys.exit(0)

    log_maillog(f"Received self-sent command email for {from_addr}: Subject='{subject_raw}'", syslog.LOG_INFO if HAS_SYSLOG else None)
    log_maillog(f"Ollama config: HOST='{OLLAMA_HOST}', MODEL='{OLLAMA_MODEL}', TIMEOUT={OLLAMA_TIMEOUT}s", syslog.LOG_INFO if HAS_SYSLOG else None)

    # Detect baseline language
    detected_lang = detect_language(subject_raw + " " + body)

    # 2. Check for legacy explicit disable commands first
    disable_regex = r"#(?:autoreply|vacation|休假|不在|出差|請假)\s+(?:off|cancel|stop|關閉|取消|停用)"
    if re.search(disable_regex, subject_raw, re.IGNORECASE):
        disable_autoreply(from_addr, detected_lang)
        sys.exit(0)

    # 3. Check for legacy explicit regex syntax with date or 'on'
    legacy_regex = r"#(?:autoreply|vacation|休假|不在|出差|請假)(?:\s+(.*))?$"
    legacy_match = re.search(legacy_regex, subject_raw, re.IGNORECASE)

    # 4. Attempt Ollama AI Parsing if configured
    ollama_result = None
    ollama_attempted = False
    if OLLAMA_HOST:
        ollama_attempted = True
        ollama_result = call_ollama_parser(subject_raw, body)

    if ollama_result and isinstance(ollama_result, dict):
        # AI Succeeded
        is_vacation = ollama_result.get("is_vacation", False)
        action = str(ollama_result.get("action", "ignore")).lower().strip()
        # 確定回覆語系：
        # 1. 若環境變數有強制指定 DEFAULT_LANG（如 "en" 或 "zh-TW"），一律優先採用
        # 2. 中文一律以字元特徵庫為準（避免 Qwen 等模型習慣性將中文標記為 zh-CN）
        if DEFAULT_LANG and DEFAULT_LANG.lower() in ["en", "zh-tw", "zh-cn", "vi"]:
            m = {"en": "en", "zh-tw": "zh-TW", "zh-cn": "zh-CN", "vi": "vi"}
            ai_lang = m.get(DEFAULT_LANG.lower(), detected_lang)
        elif CHINESE_RE.search(subject_raw + " " + body):
            ai_lang = detect_language(subject_raw + " " + body)
        else:
            ai_lang = detect_language(subject_raw + " " + body)

        if is_vacation and action in ["disable", "cancel", "stop", "off", "销假", "銷假", "hủy", "delete"]:
            disable_autoreply(from_addr, ai_lang)
            sys.exit(0)

        s_date = ollama_result.get("start_date")
        e_date = ollama_result.get("end_date")

        if is_vacation and (action in ["enable", "start", "create", "on", "set"] or (s_date and e_date and action not in ["disable", "ignore"])):
            if s_date and e_date:
                try:
                    s_dt = datetime.strptime(s_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                    e_dt = datetime.strptime(e_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    apply_autoreply(from_addr, s_dt, e_dt, is_always_on=False, custom_subject=None, body=body, lang=ai_lang, ai_parsed=True)
                    sys.exit(0)
                except Exception as ex:
                    log_maillog(f"Failed to parse dates from AI: {ex}", syslog.LOG_WARNING if HAS_SYSLOG else None)
            else:
                # Ambiguous dates: Notify user to specify dates
                unclear_notices = {
                    "zh-TW": (
                        "【自動回覆通知】AI 辨識到休假意圖，但時間不明確",
                        f"您好：\n\n系統已透過 AI 辨識到您的休假意圖，但未能從信件中確認具體的起訖日期。\n\n請重新寄信並補充明確時間（例如：「明天整天休假」、「9/10 至 9/12 休假」或「下週一到三出差」），系統將自動為您設定。\n"
                    ),
                    "zh-CN": (
                        "【自动回复通知】AI 识别到休假意图，但时间不明确",
                        f"您好：\n\n系统已通过 AI 识别到您的休假意图，但未能从邮件中确认具体的起讫日期。\n\n请重新发信并补充明确时间（例如：“明天整天休假”、“9/10 至 9/12 休假”或“下周一到三出差”），系统将自动为您设置。\n"
                    ),
                    "vi": (
                        "[Thông báo tự động trả lời] AI nhận diện được kỳ nghỉ nhưng thời gian chưa rõ ràng",
                        f"Xin chào:\n\nHệ thống đã nhận diện được ý định nghỉ phép của bạn qua AI, nhưng chưa thể xác định ngày bắt đầu và kết thúc cụ thể.\n\nVui lòng gửi lại email với thời gian rõ ràng (ví dụ: 'Nghỉ phép từ ngày 10/9 đến 12/9' hoặc 'Thứ 4 tuần sau nghỉ phép'), hệ thống sẽ tự động cấu hình cho bạn.\n"
                    ),
                    "en": (
                        "[Auto-Reply Notification] Vacation intent detected, but dates are unclear",
                        f"Hello,\n\nThe system detected your vacation / out-of-office intent via AI, but could not determine clear start and end dates.\n\nPlease resend an email with explicit dates (e.g. 'Out of office from Sep 10 to Sep 12' or 'Tomorrow on leave'), and the system will automatically configure it.\n"
                    )
                }
                subj, u_body = unclear_notices.get(ai_lang, unclear_notices["zh-TW"])
                send_notification(from_addr, subj, u_body)
                sys.exit(0)

    # 5. Fallback to Legacy Regex
    if legacy_match:
        log_maillog(f"Matching legacy regex syntax for {from_addr}", syslog.LOG_INFO if HAS_SYSLOG else None)
        param_str = (legacy_match.group(1) or "").strip()
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

        apply_autoreply(from_addr, start_dt, end_dt, is_always_on, custom_subject, body, lang=detected_lang, ai_parsed=False)
        sys.exit(0)

    # 6. If Ollama was configured but failed/unreachable, and the user sent a natural language vacation email (no #)
    if ollama_attempted and not ollama_result:
        log_maillog(f"Ollama NLU unreachable or failed; checking if email requires offline notice for {from_addr}", syslog.LOG_WARNING if HAS_SYSLOG else None)
        # Check if subject matches common vacation words
        vacation_keywords = ["休假", "請假", "请假", "出差", "不在", "nghỉ", "công tác", "vacation", "holiday", "leave", "out of office"]
        if any(k in subject_raw.lower() for k in vacation_keywords):
            ai_down_notices = {
                "zh-TW": (
                    "【自動回覆通知】AI 服務暫時無法連線",
                    f"您好：\n\n系統偵測到您的信件包含休假或公出需求，但本機端 AI (Ollama) 伺服器暫時無法連線或處理超時。\n\n若需立即啟用自動回覆，請改用標準指令格式發信給自己：\n例如：主旨填寫 #autoreply 9/10~9/12 出差中\n"
                ),
                "zh-CN": (
                    "【自动回复通知】AI 服务暂时无法连线",
                    f"您好：\n\n系统检测到您的邮件包含休假或出差需求，但本地端 AI (Ollama) 服务器暂时无法连接或处理超时。\n\n若需立即启用自动回复，请改用标准指令格式发信给自己：\n例如：主题填写 #autoreply 9/10~9/12 出差中\n"
                ),
                "vi": (
                    "[Thông báo tự động trả lời] Dịch vụ AI tạm thời không phản hồi",
                    f"Xin chào:\n\nHệ thống nhận thấy email của bạn có nhu cầu nghỉ phép hoặc công tác, nhưng máy chủ AI (Ollama) cục bộ tạm thời không thể kết nối hoặc đã hết thời gian chờ.\n\nĐể kích hoạt tính năng tự động trả lời ngay lập tức, vui lòng sử dụng cú pháp chuẩn gửi cho chính mình:\nVí dụ: Tiêu đề '#autoreply 10/9~12/9 Đi công tác'\n"
                ),
                "en": (
                    "[Auto-Reply Notification] AI Service Temporarily Unreachable",
                    f"Hello,\n\nThe system detected leave or out-of-office keywords in your email, but the local AI (Ollama) server is temporarily unreachable or timed out.\n\nTo enable auto-reply immediately, please send an email to yourself using the standard command syntax:\nFor example: Subject '#autoreply 9/10~9/12 Out of Office'\n"
                )
            }
            s_down, b_down = ai_down_notices.get(detected_lang, ai_down_notices["zh-TW"])
            send_notification(from_addr, s_down, b_down)

    # Otherwise, normal note-to-self mail, simply keep in inbox
    sys.exit(0)

if __name__ == "__main__":
    main()
