#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handle_recall.py - 企業級雙層郵件收回處理器 (Two-Tier Message Recall Handler)

觸發方式：
由 Dovecot Sieve (90-recall.sieve 或 autoreply_handler.sieve) 於收到收回郵件時 pipe 觸發：
1. 支援 Outlook 原生收回 (X-MS-Exchange-Organization-Recall-Action, Recall:, 撤回:, 收回:)
2. 支援行動裝置 Sent Items 回覆主旨前綴 #recall

處理邏輯：
- Layer 1 (佇列暫存檢查): 若郵件仍在 Postfix Hold 佇列，執行 postsuper -d 抹除 (內外部均收不到)。
- Layer 2 (信箱強制抹除): 對同網域內部信箱，檢查是否在 RECALL_MAX_HOURS 內，
  執行 `doveadm expunge` 強制抹除 (無論已讀 SEEN 或未讀)。
- 外部收件者: 攔截收回通知不出站，並於報表載明外部無法遠端銷毀。
- 發送繁中/簡中/英文/越南文四國語言彙總報表給原寄件者。
"""

import email
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, parseaddr
import json
import os
import re
import shutil
import subprocess
import sys
try:
    import syslog
except ImportError:
    class DummySyslog:
        LOG_INFO = 6
        LOG_WARNING = 4
        LOG_ERR = 3
        LOG_MAIL = 2
        @staticmethod
        def syslog(*args, **kwargs):
            pass
        @staticmethod
        def openlog(*args, **kwargs):
            pass
    syslog = DummySyslog()
import time
from typing import Dict, List, Optional, Tuple

# 確保在 Dovecot Sieve (vmail) 隔離環境下能搜尋到 /usr/sbin, /usr/local/sbin 等二進位檔
default_paths = ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]
current_path = os.environ.get("PATH", "")
path_parts = current_path.split(os.pathsep) if current_path else []
for p in reversed(default_paths):
    if p not in path_parts:
        path_parts.insert(0, p)
os.environ["PATH"] = os.pathsep.join(path_parts)


def get_bin_path(name: str) -> str:
    """尋找可執行檔的路徑，優先檢查 PATH，若找不到則檢查標準 Linux 系統目錄"""
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        f"/usr/sbin/{name}",
        f"/usr/local/sbin/{name}",
        f"/usr/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/sbin/{name}",
        f"/bin/{name}",
    ]
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return name

CONFIG_PATH = os.environ.get("RECALL_CONFIG_PATH", "/etc/dovecot/recall.env")
DEFAULT_CONFIG = {
    "ENABLE_RECALL": "yes",
    "RECALL_DELAY_SECONDS": 10,
    "RECALL_MAX_HOURS": 2
}


def log(msg: str, level=syslog.LOG_INFO):
    try:
        syslog.syslog(level, f"handle_recall: {msg}")
    except Exception:
        pass
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] handle_recall: {msg}", file=sys.stderr, flush=True)


def load_config(config_path: str = CONFIG_PATH) -> Dict[str, any]:
    cfg = dict(DEFAULT_CONFIG)
    if not os.path.exists(config_path):
        return cfg
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "ENABLE_RECALL":
                        cfg["ENABLE_RECALL"] = val.lower()
                    elif key == "RECALL_DELAY_SECONDS":
                        try:
                            cfg["RECALL_DELAY_SECONDS"] = max(0, int(val))
                        except ValueError:
                            cfg["RECALL_DELAY_SECONDS"] = 10
                    elif key == "RECALL_MAX_HOURS":
                        try:
                            cfg["RECALL_MAX_HOURS"] = max(1, int(val))
                        except ValueError:
                            cfg["RECALL_MAX_HOURS"] = 2
    except Exception as e:
        log(f"Error reading config: {e}", syslog.LOG_ERR)
    return cfg


def decode_mime_words(raw_header: Optional[str]) -> str:
    """解碼 RFC 2047 編碼字串 (例如 =?UTF-8?B?...?=)"""
    if not raw_header:
        return ""
    try:
        return str(make_header(decode_header(raw_header))).strip()
    except Exception:
        return str(raw_header).strip()


def clean_subject(raw_subject: str) -> str:
    """
    徹底清理主旨中的 #recall、收回關鍵字以及所有回覆/轉寄前綴：
    相容：Re:, RE:, Fwd:, FW:, 轉寄:, 轉發:, 回覆:, 回复:, Recall:, 撤回:, 收回:, 冒號等
    不論順序如何（如 #recall Re:, Re: #recall, Fwd: #recall, 轉寄: #recall），
    循環清理直到還原為最原始的純淨主旨。
    """
    cleaned = decode_mime_words(raw_subject).strip()
    while True:
        prev = cleaned
        # 1. 移除 #recall 標籤 (不論在開頭、中間或結尾)
        cleaned = re.sub(r'#recall\b', '', cleaned, flags=re.IGNORECASE).strip()
        # 2. 移除開頭殘留冒號與空白
        cleaned = re.sub(r'^[:：]\s*', '', cleaned).strip()
        # 3. 移除收回/撤回/Recall 前綴
        cleaned = re.sub(r'^(?:recall|撤回|收回)\s*[:：]?\s*', '', cleaned, flags=re.IGNORECASE).strip()
        # 4. 循環移除所有語言的回覆/轉寄前綴
        cleaned = re.sub(r'^(?:re|fwd|fw|轉寄|轉發|回覆|回复)\s*[:：]?\s*', '', cleaned, flags=re.IGNORECASE).strip()
        if cleaned == prev:
            break
    return cleaned


def search_body_for_original_subject(msg: email.message.Message) -> Optional[str]:
    """從郵件內文 (特別是轉發或回覆的引言區塊) 搜尋原始主旨"""
    body_parts = []
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ["text/plain", "text/html"]:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode("utf-8", errors="ignore"))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body_parts.append(payload.decode("utf-8", errors="ignore"))
    except Exception:
        pass

    combined = "\n".join(body_parts)
    # 匹配引言區塊中的 主旨 / 標題 / Subject
    match = re.search(r'(?:Subject|主旨|標題)\s*[:：]\s*([^\r\n<]+)', combined, re.IGNORECASE)
    if match:
        sub = match.group(1).strip()
        cleaned = clean_subject(sub)
        if cleaned:
            return cleaned
    return None


def is_recall_trigger(msg: email.message.Message) -> Tuple[bool, str]:
    """
    檢測是否為收回請求：
    回傳 (is_recall, trigger_type)
    trigger_type: 'outlook_action' | 'outlook_subject' | 'mobile_hash' | ''
    """
    # 0. 排除自動通知、系統回報信，避免無限迴圈
    auto_sub = msg.get("Auto-Submitted", "").lower()
    if auto_sub in ["auto-replied", "auto-generated"]:
        return False, ""

    from_header = decode_mime_words(msg.get("From", "")).lower()
    sender_header = decode_mime_words(msg.get("Sender", "")).lower()
    for sys_sender in ["postmaster@", "mailer-daemon@", "vmail@"]:
        if sys_sender in from_header or sys_sender in sender_header:
            return False, ""

    subject = decode_mime_words(msg.get("Subject", ""))
    # 排除收回狀態報告信自身
    if any(sig in subject for sig in ["郵件收回狀態報告", "Message Recall Status"]):
        return False, ""

    # 1. 檢查 Exchange/Outlook 原生標頭
    if msg.get("X-MS-Exchange-Organization-Recall-Action"):
        return True, "outlook_action"

    # 2. 檢查行動端 #recall 關鍵字 (例如: "#recall", "Re: #recall", "#recall: 測試")
    if re.search(r'#recall\b', subject, re.IGNORECASE):
        return True, "mobile_hash"

    # 3. 檢查 Outlook 原生主旨
    if re.match(r'^(?:Recall|撤回|收回)\s*[:：]', subject, re.IGNORECASE):
        return True, "outlook_subject"

    return False, ""


def clean_message_id(msg_id: Optional[str]) -> str:
    if not msg_id:
        return ""
    msg_id = msg_id.strip()
    match = re.search(r'<([^>]+)>', msg_id)
    if match:
        return match.group(1)
    return msg_id.strip("<>").strip()


def search_body_for_message_id(msg: email.message.Message) -> Optional[str]:
    """從郵件內文 (特別是轉發 Forward 區塊) 搜尋原始 Message-ID"""
    body_parts = []
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ["text/plain", "text/html"]:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode("utf-8", errors="ignore"))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body_parts.append(payload.decode("utf-8", errors="ignore"))
    except Exception:
        pass

    combined = "\n".join(body_parts)
    # 匹配轉發區塊中的 Message-ID: <...>
    match = re.search(r'(?:Message-ID|Message-Id)\s*[:：]\s*<([^>]+)>', combined, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_target_message_id(msg: email.message.Message, sender: str, run_cmd: Optional[subprocess.run] = None) -> Optional[str]:
    """
    提取目標欲收回郵件的 Message-ID：
    優先順序：
    1. In-Reply-To
    2. References (最後一個 ID)
    3. X-MS-Exchange-Original-Message-Id
    4. 內文解析 (轉發信中包含的原始 Message-ID)
    5. 搜尋發件者 Sent 備份信箱比對主旨 (Fallback，支援回覆與轉發)
    """
    # 1. In-Reply-To
    in_reply_to = msg.get("In-Reply-To")
    if in_reply_to:
        cid = clean_message_id(in_reply_to)
        if cid:
            return cid

    # 2. X-MS-Exchange-Original-Message-Id
    orig_id = msg.get("X-MS-Exchange-Original-Message-Id")
    if orig_id:
        cid = clean_message_id(orig_id)
        if cid:
            return cid

    # 3. References
    references = msg.get("References")
    if references:
        ids = re.findall(r'<([^>]+)>', references)
        if ids:
            return ids[-1]

    # 4. 內文解析 (轉發/回覆區塊)
    body_msg_id = search_body_for_message_id(msg)
    if body_msg_id:
        return body_msg_id

    # 5. Fallback: 由主旨搜尋 Sent 信箱 (多信匣支援 + 動態信匣偵測)
    clean_sub = clean_subject(msg.get("Subject", ""))
    if not clean_sub:
        # 若主旨只有 #recall，嘗試從內文引言區塊提取原主旨
        clean_sub = search_body_for_original_subject(msg) or ""

    if sender:
        cmd_exec = run_cmd or subprocess.run
        doveadm_bin = get_bin_path("doveadm")

        # 動態偵測使用者的 Sent 目錄名稱
        sent_candidates = []
        try:
            list_res = cmd_exec([doveadm_bin, "mailbox", "list", "-u", sender], capture_output=True, text=True, check=False)
            if list_res.returncode == 0 and list_res.stdout:
                for line in list_res.stdout.splitlines():
                    box = line.strip()
                    if any(k in box.lower() for k in ["sent", "寄件"]):
                        if box not in sent_candidates:
                            sent_candidates.append(box)
        except Exception:
            pass

        for default_box in ["Sent", "Sent Items", "Sent Messages", "INBOX.Sent"]:
            if default_box not in sent_candidates:
                sent_candidates.append(default_box)

        for folder in sent_candidates:
            try:
                search_args = ["mailbox", folder]
                if clean_sub:
                    search_args.extend(["HEADER", "Subject", clean_sub])

                # 方式 A：直接 fetch header
                fetch_res = cmd_exec(
                    [doveadm_bin, "fetch", "-u", sender, "hdr.message-id"] + search_args,
                    capture_output=True, text=True, check=False
                )
                if fetch_res.returncode == 0 and fetch_res.stdout:
                    matches = re.findall(r'<([^>]+@[^>]+)>', fetch_res.stdout)
                    if not matches:
                        matches = re.findall(r'Message-ID:\s*<([^>]+)>', fetch_res.stdout, re.IGNORECASE)
                    if matches:
                        return matches[-1]

                # 方式 B：search 取得 GUID 後 fetch
                res = cmd_exec(
                    [doveadm_bin, "search", "-u", sender] + search_args,
                    capture_output=True, text=True, check=False
                )
                if res.returncode == 0 and res.stdout.strip():
                    lines = res.stdout.strip().splitlines()
                    last_line = lines[-1].strip()
                    tokens = last_line.split()
                    query = ["mailbox", folder]
                    if len(tokens) >= 2:
                        query.extend(["mailbox-guid", tokens[0], "uid", tokens[1]])
                    elif len(tokens) == 1:
                        query.extend(["mailbox-guid", tokens[0]])

                    fetch_res2 = cmd_exec(
                        [doveadm_bin, "fetch", "-u", sender, "hdr.message-id"] + query,
                        capture_output=True, text=True, check=False
                    )
                    if fetch_res2.returncode == 0 and fetch_res2.stdout:
                        matches = re.findall(r'<([^>]+@[^>]+)>', fetch_res2.stdout)
                        if not matches:
                            matches = re.findall(r'Message-ID:\s*<([^>]+)>', fetch_res2.stdout, re.IGNORECASE)
                        if matches:
                            return matches[-1]
            except Exception as e:
                log(f"Sent mailbox fallback search failed in {folder}: {e}", syslog.LOG_WARNING)

    return None


def get_all_recipients(msg: email.message.Message) -> List[str]:
    """提取信件中所有的收件地址 (To, Cc, Bcc)"""
    recipients = []
    for hdr in ["To", "Cc", "Bcc"]:
        val = msg.get(hdr)
        if val:
            for part in val.split(","):
                addr = parseaddr(part)[1].strip()
                if addr and addr.lower() not in [r.lower() for r in recipients]:
                    recipients.append(addr.lower())
    return recipients


def is_internal_recipient(email_addr: str, sender_domain: str, run_cmd: Optional[subprocess.run] = None) -> bool:
    """判斷是否為同網域內部信箱"""
    cmd_exec = run_cmd or subprocess.run
    if "@" not in email_addr:
        return False
    recip_domain = email_addr.split("@", 1)[1].lower()
    if sender_domain and recip_domain == sender_domain.lower():
        return True

    # 檢查 doveadm user 是否存在該帳號
    try:
        doveadm_bin = get_bin_path("doveadm")
        res = cmd_exec([doveadm_bin, "user", email_addr], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    return False


def check_and_cancel_hold_queue(
    target_msg_id: str,
    sender: str,
    run_cmd: Optional[subprocess.run] = None,
    out_recipients: Optional[List[str]] = None
) -> bool:
    """
    第一層 (Layer 1): 檢查 Postfix Hold 佇列。
    若發現目標信件存在於 Hold 佇列，直接執行 postsuper -d 銷毀。
    """
    cmd_exec = run_cmd or subprocess.run
    postqueue_bin = get_bin_path("postqueue")
    postcat_bin = get_bin_path("postcat")
    postsuper_bin = get_bin_path("postsuper")

    try:
        proc = cmd_exec([postqueue_bin, "-j"], capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not proc.stdout:
            return False

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("queue_name") != "hold":
                    continue
                qid = data.get("queue_id")
                qsender = data.get("sender", "")

                # 比對寄件者是否相符
                if sender and qsender and sender.lower() != qsender.lower():
                    continue

                # 透過 postcat 讀取 header 檢查 Message-ID
                cat_proc = cmd_exec([postcat_bin, "-h", qid], capture_output=True, text=True, check=False)
                if cat_proc.returncode == 0 and cat_proc.stdout:
                    match = re.search(r'Message-ID:\s*<([^>]+)>', cat_proc.stdout, re.IGNORECASE)
                    if match and match.group(1).strip() == target_msg_id.strip():
                        # 命中目標信件，若有需要則提取收件者
                        if out_recipients is not None:
                            for hline in cat_proc.stdout.splitlines():
                                if any(hline.lower().startswith(p) for p in ["to:", "cc:"]):
                                    val = re.sub(r'^(?:to|cc)\s*[:：]\s*', '', hline, flags=re.IGNORECASE)
                                    for part in val.split(","):
                                        addr = parseaddr(part)[1].strip().lower()
                                        if addr and addr not in out_recipients:
                                            out_recipients.append(addr)

                        # 執行強制抹除
                        del_proc = cmd_exec([postsuper_bin, "-d", qid], capture_output=True, text=True, check=False)
                        if del_proc.returncode == 0:
                            log(f"[Layer 1 Success] Killed queued message {qid} (Message-ID: {target_msg_id})")
                            return True
            except Exception:
                continue
    except Exception as e:
        log(f"Error checking hold queue: {e}", syslog.LOG_ERR)

    return False


def expunge_internal_mailbox(
    recipient: str,
    target_msg_id: str,
    max_hours: int,
    sender: str = "",
    run_cmd: Optional[subprocess.run] = None
) -> Tuple[str, str]:
    """
    第二層 (Layer 2): 同網域內部信箱強制抹除
    嚴格比對 Message-ID 與原信發件者 From (只有原發件者有權收回自己的信件)
    回傳 (status, reason)
    status: 'SUCCESS' | 'EXPIRED' | 'NOT_FOUND' | 'ERROR'
    """
    cmd_exec = run_cmd or subprocess.run
    doveadm_bin = get_bin_path("doveadm")

    # 構建檢索條件：Message-ID 加上寄件者 From 雙重驗證
    criteria = ["HEADER", "Message-ID", f"<{target_msg_id}>"]
    if sender:
        criteria.extend(["HEADER", "From", sender])

    try:
        # 1. 搜尋目標信件是否在 INBOX 中
        search_cmd = [doveadm_bin, "search", "-u", recipient, "mailbox", "INBOX"] + criteria
        search_res = cmd_exec(search_cmd, capture_output=True, text=True, check=False)
        if search_res.returncode != 0 or not search_res.stdout.strip():
            # 搜尋全信匣 (包含使用者自訂資料夾)
            search_cmd2 = [doveadm_bin, "search", "-u", recipient, "mailboxes", "*"] + criteria
            search_res = cmd_exec(search_cmd2, capture_output=True, text=True, check=False)
            if search_res.returncode != 0 or not search_res.stdout.strip():
                return "NOT_FOUND", "信件不存在或非發起者所寄出"

        # 2. 獲取信件接收時間 (date.saved 或 date.received)
        fetch_cmd = [doveadm_bin, "fetch", "-u", recipient, "date.saved", "mailbox", "INBOX"] + criteria
        fetch_res = cmd_exec(fetch_cmd, capture_output=True, text=True, check=False)
        saved_ts = None
        if fetch_res.returncode == 0 and fetch_res.stdout:
            for line in fetch_res.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    saved_ts = int(line)
                    break

        if saved_ts:
            age_hours = (time.time() - saved_ts) / 3600.0
            if age_hours > max_hours:
                return "EXPIRED", f"已超過收回時效 ({max_hours} 小時)"

        # 3. 執行強制抹除 (doveadm expunge 嚴格限定 Message-ID 與 From 雙重條件)
        expunge_cmd = [doveadm_bin, "expunge", "-u", recipient, "mailboxes", "*"] + criteria
        exp_res = cmd_exec(expunge_cmd, capture_output=True, text=True, check=False)
        if exp_res.returncode == 0:
            log(f"[Layer 2 Success] Expunged message <{target_msg_id}> from user {recipient} (sender: {sender or 'any'})")
            return "SUCCESS", "已從收件者信箱強制抹除 (已讀/未讀均銷毀)"
        else:
            return "ERROR", f"抹除操作失敗: {exp_res.stderr.strip()}"

    except Exception as e:
        log(f"Expunge error for recipient {recipient}: {e}", syslog.LOG_ERR)
        return "ERROR", str(e)


def extract_original_recipients_from_sent(sender: str, target_msg_id: str, run_cmd: Optional[subprocess.run] = None) -> List[str]:
    """從寄件者的 Sent 目錄中讀取原信的 To 與 Cc 收件者"""
    cmd_exec = run_cmd or subprocess.run
    doveadm_bin = get_bin_path("doveadm")
    sent_candidates = ["Sent", "Sent Items", "Sent Messages", "INBOX.Sent"]
    found_recips: List[str] = []

    for folder in sent_candidates:
        try:
            fetch_res = cmd_exec(
                [doveadm_bin, "fetch", "-u", sender, "hdr.to hdr.cc", "mailbox", folder, "HEADER", "Message-ID", f"<{target_msg_id}>"],
                capture_output=True, text=True, check=False
            )
            if fetch_res.returncode == 0 and fetch_res.stdout:
                for line in fetch_res.stdout.splitlines():
                    line = line.strip()
                    if any(line.lower().startswith(p) for p in ["to:", "cc:", "hdr.to:", "hdr.cc:"]):
                        val = re.sub(r'^(?:hdr\.)?(?:to|cc)\s*[:：]\s*', '', line, flags=re.IGNORECASE)
                        for part in val.split(","):
                            addr = parseaddr(part)[1].strip().lower()
                            if addr and addr not in found_recips:
                                found_recips.append(addr)
                if found_recips:
                    break
        except Exception:
            pass
    return found_recips


def build_status_report(
    sender: str,
    target_subject: str,
    target_msg_id: str,
    trigger_type: str,
    results: List[Dict[str, str]]
) -> MIMEMultipart:
    """生成繁中、簡中、英文、越南文四國語言彙總報告郵件"""
    clean_sub = clean_subject(target_subject)
    sender_domain = sender.split('@')[1] if '@' in sender else 'localhost'
    postmaster = f"postmaster@{sender_domain}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Mail Delivery System <{postmaster}>"
    msg["To"] = sender
    msg["Subject"] = f"郵件收回狀態報告 / Message Recall Status: {clean_sub}"
    msg["Date"] = formatdate(localtime=True)
    msg["Auto-Submitted"] = "auto-replied"
    msg["Precedence"] = "auto_reply"
    msg["X-Auto-Response-Suppress"] = "All"

    # 表格內容生成
    table_rows_text = ""
    table_rows_html = ""
    for r in results:
        recip = r.get("recipient", "")
        domain_type = "內部 (Internal)" if r.get("internal") else "外部 (External)"
        status = r.get("status", "")
        reason = r.get("reason", "")
        color = "#28a745" if status == "SUCCESS" else ("#dc3545" if status in ["EXPIRED", "ERROR"] else "#6c757d")
        
        table_rows_text += f"- {recip} [{domain_type}]: {status} - {reason}\n"
        table_rows_html += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd;">{recip}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{domain_type}</td>
            <td style="padding: 8px; border: 1px solid #ddd; color: {color}; font-weight: bold;">{status}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{reason}</td>
        </tr>
        """

    # 純文字內容 (4 語言)
    text_content = f"""
======================================================================
郵件收回狀態報告 / MESSAGE RECALL STATUS REPORT
======================================================================
原郵件主旨 / Subject : {clean_sub}
訊息識別碼 / Message-ID: <{target_msg_id}>
觸發方式   / Trigger   : {trigger_type}
時間戳記   / Timestamp : {time.strftime('%Y-%m-%d %H:%M:%S')}

【收回結果明細 / Recall Results】
{table_rows_text}

----------------------------------------------------------------------
【繁體中文說明】
- 第一層佇列攔截：10 秒內收回之郵件已在伺服器出站佇列銷毀，內外部收件人皆未收到。
- 第二層信箱抹除：同網域收件人之郵件已在 2 小時時效內強制抹除 (包含已讀與未讀)。
- 外部收件人說明：外部第三方伺服器不支援跨站抹除，但系統已攔截所有收回通知，避免打擾對方。
- POP3 備註：若同仁使用 POP3 且已下載至本機電腦，伺服器已抹除但本機硬碟檔案無法遠端銷毀。

【简体中文说明】
- 第一层队列拦截：10 秒内收回之邮件已在出站队列销毁，内外部收件人均未收到。
- 第二层邮箱抹除：同域名收件人之邮件已在 2 小时时效内强制抹除 (包含已读与未读)。
- 外部收件人说明：外部第三方服务器不支持跨站抹除，但系统已拦截所有收回通知，避免打扰客户。

【English Notes】
- Layer 1 (Queue Buffer): Recalls within 10s were deleted in the queue; no recipients received it.
- Layer 2 (Mailbox Expunge): Internal recipients had the message expunged regardless of read status.
- External Recipients: Cannot remotely delete from external servers; recall notices were suppressed.

【Ghi chú tiếng Việt】
- Lớp 1 (Hàng đợi trễ): Thư thu hồi trong 10 giây đã bị xóa khỏi hàng đợi máy chủ.
- Lớp 2 (Xóa hộp thư): Thư của người nhận nội bộ đã bị xóa cưỡng chế (bao gồm đã đọc và chưa đọc).
- Người nhận bên ngoài: Không thể xóa trên máy chủ bên thứ ba; thông báo thu hồi đã bị chặn.
======================================================================
"""

    # HTML 內容 (4 語言美觀排版)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; margin: 20px;">
        <div style="max-width: 800px; margin: auto; border: 1px solid #e1e4e8; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <div style="background-color: #0366d6; color: white; padding: 18px 24px;">
                <h2 style="margin: 0; font-size: 20px;">郵件收回狀態報告 / Message Recall Status Report</h2>
                <div style="font-size: 13px; opacity: 0.9; margin-top: 4px;">Docker-Postfix-AD Two-Tier Recall System</div>
            </div>
            
            <div style="padding: 24px;">
                <table style="width: 100%; margin-bottom: 20px; font-size: 14px;">
                    <tr><td style="width: 130px; font-weight: bold; color: #586069;">原郵件主旨 / Subject:</td><td><strong>{clean_sub}</strong></td></tr>
                    <tr><td style="font-weight: bold; color: #586069;">Message-ID:</td><td style="font-family: monospace; color: #444;">&lt;{target_msg_id}&gt;</td></tr>
                    <tr><td style="font-weight: bold; color: #586069;">觸發機制 / Trigger:</td><td>{trigger_type}</td></tr>
                    <tr><td style="font-weight: bold; color: #586069;">處理時間 / Time:</td><td>{time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                </table>

                <h3 style="font-size: 16px; border-bottom: 2px solid #eaecef; padding-bottom: 6px; margin-top: 24px;">收件人處理明細 / Recipient Processing Status</h3>
                <table style="width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px;">
                    <thead>
                        <tr style="background-color: #f6f8fa; text-align: left;">
                            <th style="padding: 8px; border: 1px solid #ddd;">收件人 (Recipient)</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">網域 (Domain)</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">狀態 (Status)</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">處理說明 (Details)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>

                <div style="margin-top: 28px; padding: 16px; background-color: #f8f9fa; border-radius: 6px; font-size: 12px; color: #495057;">
                    <h4 style="margin: 0 0 8px 0; font-size: 13px; color: #212529;">注意事項與安全宣告 / System Notes</h4>
                    <p style="margin: 4px 0;"><strong>繁體中文：</strong>同網域信箱信件已於 2 小時時效內強制抹除（無論同仁是否已讀）。外部郵件若逾 10 秒暫存已無法從第三方伺服器刪除，但系統已全數攔截撤回通知信避免尷尬。若同仁使用 POP3 且已收至本機，本機硬碟複本無法遠端銷毀。</p>
                    <p style="margin: 4px 0;"><strong>简体中文：</strong>同域名邮箱邮件已于 2 小时时效内强制抹除（无论同事是否已读）。外部邮件若逾 10 秒暂存已无法从第三方服务器删除，但系统已全数拦截撤回通知信避免打扰。若同事使用 POP3 且已收取至本地，本地硬盘副本无法远程销毁。</p>
                    <p style="margin: 4px 0;"><strong>English:</strong> Internal mailbox messages are forcefully expunged within 2 hours regardless of read/unread status. For external recipients, recall notices are suppressed. POP3 messages already downloaded cannot be wiped remotely.</p>
                    <p style="margin: 4px 0;"><strong>Tiếng Việt:</strong> Thư nội bộ đã bị xóa cưỡng chế trong vòng 2 giờ bất kể đã đọc hay chưa. Thông báo thu hồi gửi ra ngoài đã bị chặn.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    return msg


def send_report_email(report_msg: MIMEMultipart, recipient: str, sender_domain: str = "", run_cmd: Optional[subprocess.run] = None):
    """透過本機 sendmail 發送報告郵件給寄件者，並指定 postmaster 為信封寄件者避免以 vmail 發出"""
    cmd_exec = run_cmd or subprocess.run
    domain = sender_domain or (recipient.split("@", 1)[1] if "@" in recipient else "localhost")
    postmaster = f"postmaster@{domain}"
    sendmail_bin = get_bin_path("sendmail")
    cmd = [sendmail_bin, "-t", "-oi", "-f", postmaster]
    try:
        proc = cmd_exec(cmd, input=report_msg.as_bytes(), check=False)
        if proc.returncode == 0:
            log(f"Successfully sent recall status report to {recipient} via envelope sender {postmaster}")
        else:
            log(f"Failed to send recall report to {recipient}, code={proc.returncode}", syslog.LOG_WARNING)
    except Exception as e:
        log(f"send_report_email exception: {e}", syslog.LOG_ERR)


def process_recall(raw_email_bytes: bytes, run_cmd: Optional[subprocess.run] = None) -> bool:
    """處理收回核心入口流程"""
    cmd_exec = run_cmd or subprocess.run
    cfg = load_config()
    if cfg.get("ENABLE_RECALL") != "yes":
        log("Recall system is disabled via ENABLE_RECALL=no.")
        return False

    msg = email.message_from_bytes(raw_email_bytes)

    # 1. 檢驗是否為收回信件
    is_recall, trigger_type = is_recall_trigger(msg)
    if not is_recall:
        return False

    sender_addr = parseaddr(msg.get("From", ""))[1].strip()
    if not sender_addr:
        log("Cannot process recall: Missing From header.", syslog.LOG_WARNING)
        return False

    sender_domain = sender_addr.split("@", 1)[1] if "@" in sender_addr else ""
    log(f"Processing recall triggered via {trigger_type} by sender: {sender_addr}")

    # 2. 提取目標 Message-ID
    target_msg_id = extract_target_message_id(msg, sender_addr, run_cmd=cmd_exec)
    if not target_msg_id:
        log("Cannot identify target Message-ID for recall.", syslog.LOG_WARNING)
        # 發送目標未找到通知
        report = build_status_report(
            sender=sender_addr,
            target_subject=msg.get("Subject", ""),
            target_msg_id="UNKNOWN",
            trigger_type=trigger_type,
            results=[{"recipient": sender_addr, "internal": True, "status": "ERROR", "reason": "無法解析原郵件 Message-ID (No In-Reply-To, References, or Sent mailbox match)"}]
        )
        send_report_email(report, sender_addr, sender_domain=sender_domain, run_cmd=cmd_exec)
        return True

    # 3. 提取收件人清單
    recipients = get_all_recipients(msg)
    # 若為轉發或自寄給自己的信 (recipients 僅有寄件者本人)，嘗試從寄件備份 Sent 中提取真正原信收件者
    orig_recips = extract_original_recipients_from_sent(sender_addr, target_msg_id, run_cmd=cmd_exec)
    if orig_recips:
        if not recipients or (len(recipients) == 1 and recipients[0].lower() == sender_addr.lower()):
            recipients = orig_recips
        else:
            for orx in orig_recips:
                if orx.lower() not in [r.lower() for r in recipients]:
                    recipients.append(orx)

    if not recipients:
        recipients = [sender_addr]

    results: List[Dict[str, str]] = []

    # 4. 第一層 (Layer 1): 佇列暫存檢查 (10 秒內)
    hold_recips: List[str] = []
    queue_killed = check_and_cancel_hold_queue(target_msg_id, sender_addr, run_cmd=cmd_exec, out_recipients=hold_recips)
    if queue_killed:
        if hold_recips and (len(recipients) == 1 and recipients[0].lower() == sender_addr.lower()):
            recipients = hold_recips
        for r in recipients:
            is_int = is_internal_recipient(r, sender_domain, run_cmd=cmd_exec)
            results.append({
                "recipient": r,
                "internal": is_int,
                "status": "SUCCESS",
                "reason": "在出站佇列 (10s 暫存) 中成功攔截銷毀，未送出"
            })
    else:
        # 5. 第二層 (Layer 2): 信箱強制抹除 (2 小時內)
        max_hours = cfg.get("RECALL_MAX_HOURS", 2)
        for r in recipients:
            is_int = is_internal_recipient(r, sender_domain, run_cmd=cmd_exec)
            if not is_int:
                results.append({
                    "recipient": r,
                    "internal": False,
                    "status": "UNSUPPORTED",
                    "reason": "外部信箱 (已攔截收回通知信，無法自第三方伺服器刪除)"
                })
            else:
                st, reason = expunge_internal_mailbox(r, target_msg_id, max_hours, sender=sender_addr, run_cmd=cmd_exec)
                results.append({
                    "recipient": r,
                    "internal": True,
                    "status": st,
                    "reason": reason
                })

    # 6. 生成並寄送多語言狀態報告給寄件者
    report = build_status_report(
        sender=sender_addr,
        target_subject=msg.get("Subject", ""),
        target_msg_id=target_msg_id,
        trigger_type=trigger_type,
        results=results
    )
    send_report_email(report, sender_addr, sender_domain=sender_domain, run_cmd=cmd_exec)

    return True


def main():
    try:
        syslog.openlog(ident="handle_recall", facility=syslog.LOG_MAIL)
    except Exception:
        pass

    raw_bytes = sys.stdin.buffer.read()
    if not raw_bytes:
        sys.exit(0)

    try:
        process_recall(raw_bytes)
    except Exception as e:
        log(f"Fatal error in process_recall: {e}", syslog.LOG_ERR)

    # 永遠返回 0，讓 Sieve 順利完成並接續執行 discard
    sys.exit(0)


if __name__ == "__main__":
    main()
