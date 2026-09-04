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
import signal
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional

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
    messages = []
    try:
        proc = cmd_exec(["postqueue", "-j"], capture_output=True, text=True, check=False)
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


def process_hold_queue(delay_seconds: int, enabled: bool, now_ts: Optional[float] = None, run_cmd: Optional[Callable] = None) -> int:
    """
    掃描 Hold 佇列並放行到期的信件：
    回傳放行（release）的郵件數量。
    """
    cmd_exec = run_cmd or subprocess.run
    current_time = time.time() if now_ts is None else now_ts
    released_count = 0

    hold_msgs = get_queued_hold_messages(run_cmd=cmd_exec)
    for msg in hold_msgs:
        qid = msg.get("queue_id")
        arrival_ts = msg.get("arrival_time", current_time)
        age = current_time - arrival_ts

        # 若未啟用收回，或延遲秒數為 0，或已達留置秒數
        if not enabled or delay_seconds <= 0 or age >= delay_seconds:
            try:
                cmd = ["postsuper", "-H", qid]
                res = cmd_exec(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    released_count += 1
                    # 立即透過 postqueue -i 喚醒 qmgr 排程即刻派送，終結預設 300 秒之 deferred 延遲
                    cmd_exec(["postqueue", "-i", qid], capture_output=True, text=True, check=False)
                    log(f"Released and scheduled immediate delivery for message {qid} (sender: {msg.get('sender')}, held {age:.1f}s)")
                else:
                    log(f"Failed to release {qid}: {res.stderr.strip()}", syslog.LOG_WARNING)
            except Exception as e:
                log(f"Exception releasing {qid}: {e}", syslog.LOG_ERR)

    # 若本輪有釋放任何信件，執行 postqueue -f 確保所有釋放信件立即觸發派送
    if released_count > 0:
        try:
            cmd_exec(["postqueue", "-f"], capture_output=True, text=True, check=False)
        except Exception:
            pass

    return released_count


def cancel_hold_message(queue_id: str, run_cmd: Optional[Callable] = None) -> bool:
    """從 Hold 佇列中強制抹除指定信件 (postsuper -d)"""
    cmd_exec = run_cmd or subprocess.run
    try:
        res = cmd_exec(["postsuper", "-d", queue_id], capture_output=True, text=True, check=False)
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
