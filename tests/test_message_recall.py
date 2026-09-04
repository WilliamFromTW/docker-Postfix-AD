#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
test_message_recall.py - 企業級雙層郵件收回系統單元測試套件
"""

import email
from email.mime.text import MIMEText
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# 將 scripts 加入 import 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import delayed_queue_daemon
import handle_recall


class TestDelayedQueueDaemon(unittest.TestCase):
    """測試第一層出站暫存守護精靈 (delayed_queue_daemon.py)"""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp_dir.name, "recall.env")
        self.map_path = os.path.join(self.tmp_dir.name, "submission_hold")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_config_defaults(self):
        """測試無配置檔時之預設值"""
        cfg = delayed_queue_daemon.load_config("/non/existent/path")
        self.assertEqual(cfg["ENABLE_RECALL"], "yes")
        self.assertEqual(cfg["RECALL_DELAY_SECONDS"], 10)
        self.assertEqual(cfg["RECALL_MAX_HOURS"], 2)

    def test_load_custom_config(self):
        """測試自訂配置檔解析"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write('ENABLE_RECALL="no"\n')
            f.write("RECALL_DELAY_SECONDS=30\n")
            f.write("RECALL_MAX_HOURS=4\n")

        cfg = delayed_queue_daemon.load_config(self.config_path)
        self.assertEqual(cfg["ENABLE_RECALL"], "no")
        self.assertEqual(cfg["RECALL_DELAY_SECONDS"], 30)
        self.assertEqual(cfg["RECALL_MAX_HOURS"], 4)

    def test_sync_submission_hold_map(self):
        """測試動態同步 /etc/postfix/submission_hold：>0 為 HOLD，0 為 DUNNO"""
        mock_run = MagicMock()

        # 1. 啟用且秒數 10s
        delayed_queue_daemon.sync_submission_hold_map(enabled=True, delay_seconds=10, map_path=self.map_path, run_cmd=mock_run)
        with open(self.map_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("HOLD", content)
        self.assertIn("10s", content)

        # 2. 停用 (enabled=False)
        delayed_queue_daemon.sync_submission_hold_map(enabled=False, delay_seconds=10, map_path=self.map_path, run_cmd=mock_run)
        with open(self.map_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content.strip(), "/^/ DUNNO")

        # 3. 延遲設為 0s (Bypass direct send)
        delayed_queue_daemon.sync_submission_hold_map(enabled=True, delay_seconds=0, map_path=self.map_path, run_cmd=mock_run)
        with open(self.map_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content.strip(), "/^/ DUNNO")

    def test_process_hold_queue_releasing(self):
        """測試暫存佇列掃描與逾時自動釋放 (postsuper -H)"""
        now = 1000.0
        mock_output = "\n".join([
            json.dumps({"queue_name": "hold", "queue_id": "MSG_OLD", "arrival_time": 985.0, "sender": "alice@domain.com"}), # 15s ago -> release
            json.dumps({"queue_name": "hold", "queue_id": "MSG_NEW", "arrival_time": 995.0, "sender": "bob@domain.com"}),   # 5s ago -> keep
            json.dumps({"queue_name": "incoming", "queue_id": "MSG_INC", "arrival_time": 900.0}),                           # not in hold
        ])

        mock_cmd = MagicMock()
        mock_cmd.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        released = delayed_queue_daemon.process_hold_queue(delay_seconds=10, enabled=True, now_ts=now, run_cmd=mock_cmd)

        # 只有 MSG_OLD (15s >= 10s) 應該被釋放
        # 驗證有呼叫 postsuper -H MSG_OLD 解除保留
        mock_cmd.assert_any_call(["postsuper", "-H", "MSG_OLD"], capture_output=True, text=True, check=False)
        # 驗證有呼叫 postqueue -i MSG_OLD 排程即刻派送
        mock_cmd.assert_any_call(["postqueue", "-i", "MSG_OLD"], capture_output=True, text=True, check=False)
        # 驗證有呼叫 postqueue -f 刷新佇列
        mock_cmd.assert_any_call(["postqueue", "-f"], capture_output=True, text=True, check=False)

    def test_cancel_hold_message(self):
        """測試佇列中強制抹除 (postsuper -d)"""
        mock_cmd = MagicMock()
        mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")

        res = delayed_queue_daemon.cancel_hold_message("TEST_QID", run_cmd=mock_cmd)
        self.assertTrue(res)
        mock_cmd.assert_called_once()
        called_args = mock_cmd.call_args[0][0]
        self.assertTrue(called_args[0].endswith("postsuper"))
        self.assertEqual(called_args[1:], ["-d", "TEST_QID"])

    def test_is_recall_message(self):
        """測試佇列中辨識收回信件 (#recall, Recall:, X-MS-Exchange)"""
        def mock_cmd(cmd, **kwargs):
            cmd_base = os.path.basename(cmd[0])
            qid = cmd[2]
            if cmd_base == "postcat":
                if qid == "QID_RECALL":
                    return MagicMock(returncode=0, stdout="Subject: #recall 專案進度\n", stderr="")
                elif qid == "QID_OUTLOOK":
                    return MagicMock(returncode=0, stdout="Subject: Recall: 專案進度\n", stderr="")
                elif qid == "QID_MIME":
                    return MagicMock(returncode=0, stdout="Subject: =?UTF-8?B?I3JlY2FsbCDmuKzntao=?=\n", stderr="")
                elif qid == "QID_HEADER":
                    return MagicMock(returncode=0, stdout="X-MS-Exchange-Organization-Recall-Action: delete\n", stderr="")
                else:
                    return MagicMock(returncode=0, stdout="Subject: 一般業務郵件\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        self.assertTrue(delayed_queue_daemon.is_recall_message("QID_RECALL", run_cmd=mock_cmd))
        self.assertTrue(delayed_queue_daemon.is_recall_message("QID_OUTLOOK", run_cmd=mock_cmd))
        self.assertTrue(delayed_queue_daemon.is_recall_message("QID_MIME", run_cmd=mock_cmd))
        self.assertTrue(delayed_queue_daemon.is_recall_message("QID_HEADER", run_cmd=mock_cmd))
        self.assertFalse(delayed_queue_daemon.is_recall_message("QID_NORMAL", run_cmd=mock_cmd))

    def test_process_hold_queue_fast_pass_recall(self):
        """測試收回指令信件享 0 秒直通特權 (未滿 10 秒即刻放行)"""
        now = 1000.0
        # MSG_RECALL 僅進入佇列 2 秒 (未滿 10 秒)，但為主旨 #recall 之收回信
        mock_queue = json.dumps({
            "queue_name": "hold",
            "queue_id": "MSG_RECALL",
            "arrival_time": 998.0, # 2s ago (< 10s)
            "sender": "boss@smile.taipei"
        })

        def mock_cmd(cmd, **kwargs):
            cmd_base = os.path.basename(cmd[0])
            if cmd_base == "postqueue" and cmd[1] == "-j":
                return MagicMock(returncode=0, stdout=mock_queue, stderr="")
            elif cmd_base == "postcat" and cmd[2] == "MSG_RECALL":
                return MagicMock(returncode=0, stdout="Subject: Fwd: #recall 緊急撤回\n", stderr="")
            elif cmd_base == "postsuper" and cmd[1] == "-H":
                return MagicMock(returncode=0, stdout="", stderr="")
            elif cmd_base == "postqueue":
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        released = delayed_queue_daemon.process_hold_queue(delay_seconds=10, enabled=True, now_ts=now, run_cmd=mock_cmd)
        # 即使只進佇列 2 秒，也必須被立即放行
        self.assertEqual(released, 1)


class TestHandleRecall(unittest.TestCase):
    """測試第二層收回核心與 Sieve 處理腳本 (handle_recall.py)"""

    def test_is_recall_trigger(self):
        """測試 Outlook 與行動端收回觸發識別"""
        # 1. Exchange 原生標頭
        msg1 = MIMEText("test body")
        msg1["X-MS-Exchange-Organization-Recall-Action"] = "delete"
        is_rec, t_type = handle_recall.is_recall_trigger(msg1)
        self.assertTrue(is_rec)
        self.assertEqual(t_type, "outlook_action")

        # 2. Outlook 原生主旨
        msg2 = MIMEText("test body")
        msg2["Subject"] = "Recall: 專案進度週報"
        is_rec, t_type = handle_recall.is_recall_trigger(msg2)
        self.assertTrue(is_rec)
        self.assertEqual(t_type, "outlook_subject")

        # 3. 撤回中文主旨
        msg3 = MIMEText("test body")
        msg3["Subject"] = "撤回：開會時間變更通知"
        is_rec, t_type = handle_recall.is_recall_trigger(msg3)
        self.assertTrue(is_rec)
        self.assertEqual(t_type, "outlook_subject")

        # 4. 行動端 #recall 關鍵字
        msg4 = MIMEText("test body")
        msg4["Subject"] = "#recall Re: 專案時程表"
        is_rec, t_type = handle_recall.is_recall_trigger(msg4)
        self.assertTrue(is_rec)
        self.assertEqual(t_type, "mobile_hash")

        # 5. 一般信件 (非收回)
        msg5 = MIMEText("test body")
        msg5["Subject"] = "Re: 一般業務信件"
        is_rec, t_type = handle_recall.is_recall_trigger(msg5)
        self.assertFalse(is_rec)

    def test_extract_target_message_id(self):
        """測試目標 Message-ID 解析"""
        # 透過 In-Reply-To
        msg = MIMEText("test body")
        msg["In-Reply-To"] = "<ORIG-12345@company.com>"
        target_id = handle_recall.extract_target_message_id(msg, "alice@company.com")
        self.assertEqual(target_id, "ORIG-12345@company.com")

        # 透過 References
        msg2 = MIMEText("test body")
        msg2["References"] = "<REF1@company.com> <REF2@company.com> <TARGET-999@company.com>"
        target_id2 = handle_recall.extract_target_message_id(msg2, "alice@company.com")
        self.assertEqual(target_id2, "TARGET-999@company.com")

    def test_check_and_cancel_hold_queue(self):
        """測試第一層：在 Hold 佇列中命中並刪除信件"""
        target_id = "TARGET-MSG-ID-001"
        sender = "boss@smile.taipei"

        postqueue_json = json.dumps({
            "queue_name": "hold",
            "queue_id": "HOLDQ123",
            "sender": "boss@smile.taipei",
            "arrival_time": time.time() - 3.0
        })

        postcat_headers = f"""Received: by mailserver...
From: boss@smile.taipei
To: team@smile.taipei
Subject: 機密報告
Message-ID: <{target_id}>
"""

        def mock_cmd(cmd, **kwargs):
            if cmd[0] == "postqueue":
                return MagicMock(returncode=0, stdout=postqueue_json, stderr="")
            elif cmd[0] == "postcat" and cmd[2] == "HOLDQ123":
                return MagicMock(returncode=0, stdout=postcat_headers, stderr="")
            elif cmd[0] == "postsuper" and cmd[1] == "-d" and cmd[2] == "HOLDQ123":
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        success = handle_recall.check_and_cancel_hold_queue(target_id, sender, run_cmd=mock_cmd)
        self.assertTrue(success)

    def test_expunge_internal_mailbox_within_time(self):
        """測試第二層：2 小時內強制抹除 (SEEN/未讀均抹除)"""
        target_id = "TARGET-002"
        recipient = "staff@smile.taipei"

        # 模擬 30 分鐘前送達 (1800 秒前)
        received_ts = int(time.time()) - 1800

        recorded_cmds = []
        def mock_cmd(cmd, **kwargs):
            recorded_cmds.append(cmd)
            self.assertNotIn("mailboxes", cmd, "doveadm CLI does not accept plural 'mailboxes'")
            if cmd[0] == "doveadm" and cmd[1] == "search":
                return MagicMock(returncode=0, stdout="GUID-12345\n", stderr="")
            elif cmd[0] == "doveadm" and cmd[1] == "fetch":
                return MagicMock(returncode=0, stdout=f"{received_ts}\n", stderr="")
            elif cmd[0] == "doveadm" and cmd[1] == "expunge":
                self.assertIn("mailbox", cmd)
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        status, reason = handle_recall.expunge_internal_mailbox(recipient, target_id, max_hours=2, run_cmd=mock_cmd)
        self.assertEqual(status, "SUCCESS")
        self.assertIn("已讀/未讀均銷毀", reason)
        self.assertTrue(any(c[1] == "expunge" for c in recorded_cmds))

    def test_expunge_internal_mailbox_expired(self):
        """測試第二層：超過 2 小時拒絕抹除 (保護時效)"""
        target_id = "TARGET-003"
        recipient = "staff@smile.taipei"

        # 模擬 3 小時前送達 (10800 秒前)
        received_ts = int(time.time()) - 10800

        def mock_cmd(cmd, **kwargs):
            if cmd[0] == "doveadm" and cmd[1] == "search":
                return MagicMock(returncode=0, stdout="GUID-12345\n", stderr="")
            elif cmd[0] == "doveadm" and cmd[1] == "fetch":
                return MagicMock(returncode=0, stdout=f"{received_ts}\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        status, reason = handle_recall.expunge_internal_mailbox(recipient, target_id, max_hours=2, run_cmd=mock_cmd)
        self.assertEqual(status, "EXPIRED")
        self.assertIn("已超過收回時效", reason)

    def test_expunge_internal_mailbox_sender_verification(self):
        """測試第二層：只有原寄件者能抹除信件 (防範同事惡意收回他人信件)"""
        target_id = "SEC-TEST-001"
        recipient = "victim@smile.taipei"
        author = "alice@smile.taipei"
        attacker = "bob@smile.taipei"
        received_ts = int(time.time()) - 300

        def mock_cmd(cmd, **kwargs):
            cmd_base = os.path.basename(cmd[0])
            if cmd_base == "doveadm":
                # 檢查指令是否有帶入 HEADER From 條件
                if "From" in cmd:
                    from_idx = cmd.index("From") + 1
                    expected_from = cmd[from_idx]
                    # 只有 From == alice 時，收件者信箱才能找到該信
                    if expected_from == author:
                        if cmd[1] in ["search", "expunge"]:
                            return MagicMock(returncode=0, stdout="GUID-SEC-123\n", stderr="")
                        elif cmd[1] == "fetch":
                            return MagicMock(returncode=0, stdout=f"{received_ts}\n", stderr="")
                    else:
                        # 攻擊者 Bob 嘗試抹除，信箱查無此信 (因為原信是 Alice 寄的)
                        return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        # 1. 真正寄件者 Alice 收回：成功
        status1, reason1 = handle_recall.expunge_internal_mailbox(recipient, target_id, max_hours=2, sender=author, run_cmd=mock_cmd)
        self.assertEqual(status1, "SUCCESS")

        # 2. 偽造/非原作者 Bob 嘗試收回：失敗 (NOT_FOUND)
        status2, reason2 = handle_recall.expunge_internal_mailbox(recipient, target_id, max_hours=2, sender=attacker, run_cmd=mock_cmd)
        self.assertEqual(status2, "NOT_FOUND")

    def test_build_status_report_multilingual(self):
        """測試四國語言報告生成 (zh-TW, zh-CN, en, vi)"""
        results = [
            {"recipient": "colleague@smile.taipei", "internal": True, "status": "SUCCESS", "reason": "已從收件者信箱強制抹除 (已讀/未讀均銷毀)"},
            {"recipient": "client@gmail.com", "internal": False, "status": "UNSUPPORTED", "reason": "外部信箱 (已攔截收回通知信，無法自第三方伺服器刪除)"}
        ]

        report = handle_recall.build_status_report(
            sender="boss@smile.taipei",
            target_subject="測試重要主旨",
            target_msg_id="TEST-MSG-ID@smile.taipei",
            trigger_type="outlook_action",
            results=results
        )

        # 驗證 MIME 封裝結構
        self.assertTrue(report.is_multipart())
        self.assertEqual(report["To"], "boss@smile.taipei")
        self.assertIn("Message Recall Status", report["Subject"])

        # 取得純文字與 HTML 內容
        payload_text = report.get_payload(0).get_payload(decode=True).decode("utf-8")
        payload_html = report.get_payload(1).get_payload(decode=True).decode("utf-8")

        # 驗證包含四國語言宣告
        for lang_token in ["繁體中文", "简体中文", "English", "tiếng Việt"]:
            self.assertIn(lang_token.lower(), payload_text.lower())
            self.assertIn(lang_token.lower(), payload_html.lower())

        # 驗證 POP3 備註
        self.assertIn("POP3", payload_text)
        self.assertIn("POP3", payload_html)

        # 驗證收件者清單
        self.assertIn("colleague@smile.taipei", payload_text)
        self.assertIn("client@gmail.com", payload_text)

    def test_clean_subject(self):
        """測試主旨徹底清理 (相容回覆 Re:, 轉寄 Fwd:, 轉寄:, 回覆: 以及 #recall 各種排列組合)"""
        test_cases = {
            "#recall 測試郵件": "測試郵件",
            "#recall Re: 測試郵件": "測試郵件",
            "Re: #recall 測試郵件": "測試郵件",
            "Re: #recall: 測試郵件": "測試郵件",
            "回覆: #recall 測試郵件": "測試郵件",
            "Fwd: #recall 專案計畫": "專案計畫",
            "#recall Fwd: 專案計畫": "專案計畫",
            "#recall 轉寄: 專案計畫": "專案計畫",
            "轉寄: 專案計畫 #recall": "專案計畫",
            "Re: FW: 轉寄: #recall 開會通知": "開會通知",
            "Recall: 機密檔案": "機密檔案",
            "#recall": "",
        }
        for raw, expected in test_cases.items():
            self.assertEqual(handle_recall.clean_subject(raw), expected, f"Failed on subject: {raw}")

    def test_search_body_for_original_subject(self):
        """測試當主旨只寫 #recall 時，自動從內文引言區塊提取原主旨"""
        body = """
----- 原始郵件 -----
寄件者: boss@smile.taipei
收件者: team@smile.taipei
主旨: 核心系統維護公告
日期: 2026-09-04
"""
        msg = MIMEText(body)
        msg["Subject"] = "#recall"
        orig_sub = handle_recall.search_body_for_original_subject(msg)
        self.assertEqual(orig_sub, "核心系統維護公告")

    def test_loop_prevention(self):
        """測試防自觸發迴圈 (Auto-Submitted, postmaster, 回報信)"""
        # 1. 排除 Auto-Submitted
        msg1 = MIMEText("test")
        msg1["Subject"] = "#recall 重要信件"
        msg1["Auto-Submitted"] = "auto-replied"
        is_rec, _ = handle_recall.is_recall_trigger(msg1)
        self.assertFalse(is_rec)

        # 2. 排除 postmaster / mailer-daemon / vmail
        msg2 = MIMEText("test")
        msg2["Subject"] = "#recall 重要信件"
        msg2["From"] = "postmaster@smile.taipei"
        is_rec, _ = handle_recall.is_recall_trigger(msg2)
        self.assertFalse(is_rec)

        msg2b = MIMEText("test")
        msg2b["Subject"] = "#recall 重要信件"
        msg2b["From"] = "vmail@smile.taipei"
        is_rec, _ = handle_recall.is_recall_trigger(msg2b)
        self.assertFalse(is_rec)

        # 3. 排除狀態報告信自身
        msg3 = MIMEText("test")
        msg3["Subject"] = "郵件收回狀態報告 / Message Recall Status: 測試"
        is_rec, _ = handle_recall.is_recall_trigger(msg3)
        self.assertFalse(is_rec)

    def test_extract_target_message_id_from_body(self):
        """測試轉發信件從內文中解析原始 Message-ID"""
        body = """
---------- Forwarded message ---------
From: boss@smile.taipei
Date: Fri, Sep 4, 2026 at 6:15 PM
Subject: 業務報價單
To: client@company.com
Message-ID: <FORWARDED-MSG-ID-888@smile.taipei>

這是原信內容...
"""
        msg = MIMEText(body)
        msg["Subject"] = "Fwd: #recall 業務報價單"
        msg["From"] = "boss@smile.taipei"
        msg["To"] = "boss@smile.taipei"

        target_id = handle_recall.extract_target_message_id(msg, "boss@smile.taipei")
        self.assertEqual(target_id, "FORWARDED-MSG-ID-888@smile.taipei")

    def test_extract_target_message_id_from_sent_fallback(self):
        """測試轉發信件內文無 Message-ID 時，自動搜尋寄件備份 Sent 成功匹配"""
        msg = MIMEText("純轉發內文無任何標頭")
        msg["Subject"] = "Fwd: #recall 行動端測試"
        msg["From"] = "boss@smile.taipei"
        msg["To"] = "boss@smile.taipei"

        def mock_cmd(cmd, **kwargs):
            cmd_base = os.path.basename(cmd[0])
            if cmd_base == "doveadm" and cmd[1] == "fetch" and "mailbox" in cmd and "HEADER" in cmd:
                return MagicMock(returncode=0, stdout="hdr.message-id: Message-ID: <SENT-MATCH-777@smile.taipei>\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        target_id = handle_recall.extract_target_message_id(msg, "boss@smile.taipei", run_cmd=mock_cmd)
        self.assertEqual(target_id, "SENT-MATCH-777@smile.taipei")

    def test_extract_original_recipients_from_sent(self):
        """測試從 Sent 寄件備份中還原原信的收件者 (To, Cc)"""
        def mock_cmd(cmd, **kwargs):
            cmd_base = os.path.basename(cmd[0])
            if cmd_base == "doveadm" and cmd[1] == "fetch":
                output = "To: user1@smile.taipei, user2@smile.taipei\nCc: manager@smile.taipei\n"
                return MagicMock(returncode=0, stdout=output, stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        recips = handle_recall.extract_original_recipients_from_sent("boss@smile.taipei", "TARGET-123", run_cmd=mock_cmd)
        self.assertIn("user1@smile.taipei", recips)
        self.assertIn("user2@smile.taipei", recips)
        self.assertIn("manager@smile.taipei", recips)

    def test_send_report_email_postmaster_envelope(self):
        """測試報告郵件發送時使用 postmaster 信封寄件者"""
        report = MIMEText("test report")
        mock_cmd = MagicMock()
        mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")

        handle_recall.send_report_email(report, "user@kafeiou.pw", sender_domain="kafeiou.pw", run_cmd=mock_cmd)
        mock_cmd.assert_called_once()
        called_args = mock_cmd.call_args[0][0]
        self.assertIn("-f", called_args)
        self.assertIn("postmaster@kafeiou.pw", called_args)


if __name__ == "__main__":
    unittest.main()
