#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
delayed_queue_daemon.py - Postfix 出站暫存佇列守護精靈 (Layer 1 Delay Buffer Daemon)

功能職責：
1. 常駐背景監聽 Postfix Hold 佇列 (/var/spool/postfix/hold)。
2. 動態監控 /etc/dovecot/recall.env 配置異動。
3. 當郵件在 Hold 佇列停留時間達到 RECALL_DELAY_SECONDS（預設 10 秒），
   自動調用 `postsuper -H <queue_id>` 將郵件放行並正常遞送。
4. 若 RECALL_DELAY_SECONDS <= 0 或 ENABLE_RECALL="no"，
   自動更新 /etc/postfix/submission_hold 為 DUNNO 並釋放所有 Hold 佇列信件，確保 0 延遲。
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional

# 確保能搜尋到 /usr/sbin, /usr/local/sbin 等二進位檔
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

CONFIG_PATH = os.environ.get("RECALL_CONFIG_PATH", "/etc/dovecot/recall.env")
SUBMISSION_HOLD_MAP = os.environ.get("SUBMISSION_HOLD_MAP", "/etc/postfix/submission_hold")
DEFAULT_CONFIG = {
    "ENABLE_RECALL": "yes",
    "RECALL_DELAY_SECONDS": 10,
    "RECALL_MAX_HOURS": 2
}

running = True


def sig_handler(signum, frame):
    global running
    running = False
    if syslog:
        syslog.syslog(syslog.LOG_INFO, f"delayed_queue_daemon: Received signal {signum}, exiting gracefully.")


def log(msg: str, level=None):
    if syslog:
        try:
            syslog.syslog(level if level is not None else syslog.LOG_INFO, f"delayed_queue_daemon: {msg}")
        except Exception:
            pass
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def load_config(config_path: str = CONFIG_PATH) -> Dict[str, any]:
    """讀取 /etc/dovecot/recall.env 參數"""
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
        log(f"Error loading config {config_path}: {e}", syslog.LOG_ERR)

    return cfg


def sync_submission_hold_map(enabled: bool, delay_seconds: int, map_path: str = SUBMISSION_HOLD_MAP, run_cmd: Optional[Callable] = None):
    """
    動態同步 /etc/postfix/submission_hold：
    - 若啟用且秒數 > 0：寫入 /^/ HOLD Delay buffer for message recall
    - 若停用或秒數 <= 0：寫入 /^/ DUNNO (0 延遲直發)
    """
    cmd_exec = run_cmd or subprocess.run
    target_line = f"/^/ HOLD Delay buffer for message recall ({delay_seconds}s)\n" if (enabled and delay_seconds > 0) else "/^/ DUNNO\n"
    
    current_content = ""
    if os.path.exists(map_path):
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                current_content = f.read()
        except Exception:
            pass

    if current_content != target_line:
        try:
            os.makedirs(os.path.dirname(map_path), exist_ok=True)
            with open(map_path, "w", encoding="utf-8") as f:
                f.write(target_line)
            log(f"Updated {map_path} -> {'HOLD (' + str(delay_seconds) + 's)' if (enabled and delay_seconds > 0) else 'DUNNO'}")
            
            # 通知 Postfix 重新載入對應 map
            try:
                cmd_exec(["postfix", "reload"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except Exception:
                pass
        except Exception as e:
            log(f"Failed to update {map_path}: {e}", syslog.LOG_ERR)


def get_queued_hold_messages(run_cmd: Optional[Callable] = None) -> List[Dict]:
    """使用 postqueue -j 檢索 Hold 佇列中的郵件清單"""
    cmd_exec = run_cmd or subprocess.run
    postqueue_bin = get_bin_path("postqueue")
    messages = []
    try:
        proc = cmd_exec([postqueue_bin, "-j"], capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("queue_name") == "hold":
                        messages.append(data)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log(f"Error querying postqueue: {e}", syslog.LOG_WARNING)
    return messages


import email
from email.header import decode_header, make_header


def decode_mime_words(raw: str) -> str:
    """解碼 RFC 2047 MIME 編碼字串 (例如 =?UTF-8?B?...?=)"""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return raw.strip()


def is_recall_message(qid: str, run_cmd: Optional[Callable] = None) -> bool:
    """
    檢查 Hold 佇列中的郵件是否為收回請求信：
    比對主旨（支援 RFC 2047 Base64 解碼與 RFC 2822 多行折疊解析）是否包含 #recall、Recall:、撤回:、收回:，
    或帶有 Exchange 原生收回標頭。
    收回信應享有 0 秒即刻直通 (Fast-Pass) 權限，完全不需等待 10 秒。
    """
    cmd_exec = run_cmd or subprocess.run
    postcat_bin = get_bin_path("postcat")
    try:
        proc = cmd_exec([postcat_bin, "-q", "-h", qid], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            log(f"postcat -q -h failed for {qid}: returncode={proc.returncode}, stderr={proc.stderr.strip()}", syslog.LOG_WARNING)
        if proc.returncode == 0 and proc.stdout:
            # 1. 透過標準 email 套件完整解析（自動還原多行折疊標頭）
            try:
                msg = email.message_from_string(proc.stdout)
                if msg.get("X-MS-Exchange-Organization-Recall-Action"):
                    return True
                raw_sub = msg.get("Subject", "")
                if raw_sub:
                    decoded_sub = decode_mime_words(raw_sub)
                    for sub_text in [decoded_sub, raw_sub]:
                        if re.search(r'#recall\b', sub_text, re.IGNORECASE) or re.search(r'(?:Recall|撤回|收回)\s*[:：]', sub_text, re.IGNORECASE):
                            return True
            except Exception:
                pass

            # 2. 備用逐行比對 (相容非標準輸出或部分欄位)
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("subject:"):
                    raw_sub = line[8:].strip()
                    decoded_sub = decode_mime_words(raw_sub)
                    for sub_text in [decoded_sub, raw_sub]:
                        if re.search(r'#recall\b', sub_text, re.IGNORECASE) or re.search(r'(?:Recall|撤回|收回)\s*[:：]', sub_text, re.IGNORECASE):
                            return True
                elif line.lower().startswith("x-ms-exchange-organization-recall-action:"):
                    return True
    except Exception:
        pass
    return False


def process_hold_queue(delay_seconds: int, enabled: bool, now_ts: Optional[float] = None, run_cmd: Optional[Callable] = None) -> int:
    """
    掃描 Hold 佇列並放行到期的信件：
    - 若信件為收回指令 (#recall, Recall: 等)，享受 0 秒即刻穿透放行 (Fast-Pass)。
    - 一般信件則等待滿 delay_seconds (預設 10 秒) 後放行。
    回傳放行（release）的郵件數量。
    """
    cmd_exec = run_cmd or subprocess.run
    postsuper_bin = get_bin_path("postsuper")
    postqueue_bin = get_bin_path("postqueue")
    current_time = time.time() if now_ts is None else now_ts
    released_count = 0

    hold_msgs = get_queued_hold_messages(run_cmd=cmd_exec)
    for msg in hold_msgs:
        qid = msg.get("queue_id")
        arrival_ts = msg.get("arrival_time", current_time)
        age = current_time - arrival_ts

        # 檢查是否為收回指令信 (若是則享有 0 秒直通放行特權)
        is_recall = is_recall_message(qid, run_cmd=cmd_exec)

        # 若未啟用收回，或延遲秒數為 0，或為收回信 (0s 穿透)，或已達留置秒數
        if not enabled or delay_seconds <= 0 or is_recall or age >= delay_seconds:
            try:
                cmd = [postsuper_bin, "-H", qid]
                res = cmd_exec(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    released_count += 1
                    # 立即透過 postqueue -i 喚醒 qmgr 排程即刻派送，終結預設 300 秒之 deferred 延遲
                    cmd_exec([postqueue_bin, "-i", qid], capture_output=True, text=True, check=False)
                    if is_recall:
                        log(f"Fast-passed recall command message {qid} immediately (0s delay, held {age:.1f}s)")
                    else:
                        log(f"Released and scheduled immediate delivery for message {qid} (sender: {msg.get('sender')}, held {age:.1f}s)")
                else:
                    log(f"Failed to release {qid}: {res.stderr.strip()}", syslog.LOG_WARNING)
            except Exception as e:
                log(f"Exception releasing {qid}: {e}", syslog.LOG_ERR)

    # 若本輪有釋放任何信件，執行 postqueue -f 確保所有釋放信件立即觸發派送
    if released_count > 0:
        try:
            cmd_exec([postqueue_bin, "-f"], capture_output=True, text=True, check=False)
        except Exception:
            pass

    return released_count


def cancel_hold_message(queue_id: str, run_cmd: Optional[Callable] = None) -> bool:
    """從 Hold 佇列中強制抹除指定信件 (postsuper -d)"""
    cmd_exec = run_cmd or subprocess.run
    postsuper_bin = get_bin_path("postsuper")
    try:
        res = cmd_exec([postsuper_bin, "-d", queue_id], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            log(f"Successfully killed message in hold queue: {queue_id}")
            return True
        else:
            log(f"postsuper -d failed for {queue_id}: {res.stderr.strip()}", syslog.LOG_WARNING)
            return False
    except Exception as e:
        log(f"Exception killing {queue_id}: {e}", syslog.LOG_ERR)
        return False


def main():
    try:
        syslog.openlog(ident="delayed_queue_daemon", facility=syslog.LOG_MAIL)
    except Exception:
        pass

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    log("delayed_queue_daemon started.")
    last_mtime = 0
    cached_cfg = DEFAULT_CONFIG

    while running:
        # 1. 檢查配置檔更新
        try:
            if os.path.exists(CONFIG_PATH):
                mtime = os.path.getmtime(CONFIG_PATH)
                if mtime != last_mtime:
                    last_mtime = mtime
                    cached_cfg = load_config(CONFIG_PATH)
                    is_enabled = cached_cfg.get("ENABLE_RECALL") == "yes"
                    delay_sec = cached_cfg.get("RECALL_DELAY_SECONDS", 10)
                    sync_submission_hold_map(is_enabled, delay_sec)
                    log(f"Loaded config: ENABLE_RECALL={cached_cfg.get('ENABLE_RECALL')}, DELAY={delay_sec}s, MAX_HOURS={cached_cfg.get('RECALL_MAX_HOURS')}h")
        except Exception as e:
            log(f"Config check error: {e}", syslog.LOG_WARNING)

        # 2. 處理 Hold 佇列中逾時應釋放的信件
        is_enabled = cached_cfg.get("ENABLE_RECALL") == "yes"
        delay_sec = cached_cfg.get("RECALL_DELAY_SECONDS", 10)
        process_hold_queue(delay_seconds=delay_sec, enabled=is_enabled)

        # 3. 休眠 1 秒
        time.sleep(1.0)

    log("delayed_queue_daemon stopped.")


if __name__ == "__main__":
    main()
