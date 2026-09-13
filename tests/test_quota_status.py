import unittest
import re
from unittest.mock import patch, MagicMock
import os
import sys

# 將 scripts 加入 sys.path 以便測試
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

class TestQuotaStatusQuery(unittest.TestCase):
    def test_status_regex_triggers(self):
        status_regex = r"#(?:status|quota|容量|配額|狀態|dungluong|kiemtra)"
        
        valid_subjects = [
            "#status",
            "#STATUS",
            "Fwd: #status",
            "#quota",
            "#QUOTA",
            "查詢 #容量",
            "#配額",
            "#狀態 查詢",
            "#dungluong",
            "#kiemtra"
        ]
        for subj in valid_subjects:
            self.assertTrue(re.search(status_regex, subj, re.IGNORECASE), f"Should match subject: {subj}")

        invalid_subjects = [
            "Normal subject without command",
            "status update meeting",
            "quota discussion tomorrow",
            "#autoreply on",
            "#vacation off"
        ]
        for subj in invalid_subjects:
            self.assertFalse(re.search(status_regex, subj, re.IGNORECASE), f"Should NOT match subject: {subj}")

    @patch("handle_autoreply.subprocess.run")
    def test_get_user_quota_info_success(self, mock_run):
        from handle_autoreply import get_user_quota_info

        # 模擬 doveadm quota get -u william@kafeiou.pw 輸出
        mock_output = (
            "Quota name Type    Value  Limit  %\n"
            "User quota STORAGE 2621440 52428800 5\n"
            "User quota MESSAGE   150      -  0\n"
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        info = get_user_quota_info("william@kafeiou.pw")
        self.assertEqual(info["used_mb"], 2560.0) # 2621440 KB = 2560 MB
        self.assertEqual(info["used_gb"], 2.5)
        self.assertEqual(info["limit_gb"], 50.0) # 52428800 KB = 50 GB
        self.assertEqual(info["percent"], 5.0)
        self.assertEqual(info["percent_str"], "5.0%")

    def test_make_progress_bar(self):
        from handle_autoreply import make_progress_bar

        bar_0 = make_progress_bar(0)
        self.assertEqual(bar_0, "□□□□□□□□□□")

        bar_50 = make_progress_bar(50)
        self.assertEqual(bar_50, "■■■■■□□□□□")

        bar_100 = make_progress_bar(100)
        self.assertEqual(bar_100, "■■■■■■■■■■")

    @patch("handle_autoreply.send_notification")
    @patch("handle_autoreply.get_user_quota_info")
    def test_handle_status_query_all_languages(self, mock_quota, mock_send):
        from handle_autoreply import handle_status_query

        mock_quota.return_value = {
            "used_mb": 1024.0,
            "used_gb": 1.0,
            "limit_gb": 50.0,
            "percent": 2.0,
            "percent_str": "2.0%"
        }

        # 測試 8 國語言狀態查詢皆能產出對應報告，且包含 587 與純帳號提醒
        languages = ["zh-TW", "zh-CN", "en", "vi", "fr", "de", "ja", "es"]
        for lang in languages:
            mock_send.reset_mock()
            handle_status_query("alice@example.com", lang, ignore_cooldown=True)
            self.assertTrue(mock_send.called, f"send_notification should be called for lang: {lang}")
            
            call_args = mock_send.call_args[0]
            to_addr = call_args[0]
            subject = call_args[1]
            body = call_args[2]

            self.assertEqual(to_addr, "alice@example.com")
            self.assertTrue(len(subject) > 0)
            self.assertIn("587", body, f"Body for {lang} should mention Port 587")
            self.assertIn("alice", body, f"Body for {lang} should mention pure username alice")
            self.assertIn("50.0", body, f"Body for {lang} should mention allocated quota")

    @patch("handle_autoreply.send_notification")
    @patch("handle_autoreply.get_user_quota_info")
    def test_status_query_cooldown_rate_limit(self, mock_quota, mock_send):
        from handle_autoreply import handle_status_query
        import tempfile
        import shutil

        mock_quota.return_value = {
            "used_mb": 512.0, "used_gb": 0.5, "limit_gb": 50.0, "percent": 1.0, "percent_str": "1.0%"
        }

        test_user = f"rate_limit_test_{os.getpid()}@example.com"
        
        # 第一次呼叫：成功發送
        mock_send.reset_mock()
        handle_status_query(test_user, "zh-TW")
        self.assertTrue(mock_send.called, "第一次查詢應正常發送通知")

        # 10 秒內第二次呼叫：被冷卻阻擋，不觸發發送
        mock_send.reset_mock()
        handle_status_query(test_user, "zh-TW")
        self.assertFalse(mock_send.called, "10秒內重複查詢應被防狂按保護攔截，不發送通知")

    @patch("handle_autoreply.handle_status_query")
    def test_main_exclusive_self_sent_guardrails(self, mock_status):
        import io
        from handle_autoreply import main

        def make_raw_email(from_val, to_val, cc_val=None, bcc_val=None, subject="#status"):
            lines = [
                f"From: {from_val}",
                f"To: {to_val}",
            ]
            if cc_val:
                lines.append(f"Cc: {cc_val}")
            if bcc_val:
                lines.append(f"Bcc: {bcc_val}")
            lines.extend([
                f"Subject: {subject}",
                "Content-Type: text/plain; charset=utf-8",
                "",
                "Please check status"
            ])
            return "\n".join(lines).encode("utf-8")

        # 案例 1：嚴格本人單一收件人 -> 通過並調用 handle_status_query
        mock_status.reset_mock()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(make_raw_email("user@example.com", "user@example.com")))), \
             self.assertRaises(SystemExit):
            main()
        mock_status.assert_called_once()

        # 案例 2：To 包含多個收件人 -> 阻擋退出，不調用 handle_status_query
        mock_status.reset_mock()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(make_raw_email("user@example.com", "user@example.com, colleague@example.com")))), \
             self.assertRaises(SystemExit):
            main()
        mock_status.assert_not_called()

        # 案例 3：From != To (他人寄送) -> 阻擋退出
        mock_status.reset_mock()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(make_raw_email("attacker@example.com", "user@example.com")))), \
             self.assertRaises(SystemExit):
            main()
        mock_status.assert_not_called()

        # 案例 4：有副本 (Cc) 存在 -> 阻擋退出
        mock_status.reset_mock()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(make_raw_email("user@example.com", "user@example.com", cc_val="boss@example.com")))), \
             self.assertRaises(SystemExit):
            main()
        mock_status.assert_not_called()

        # 案例 5：有密件副本 (Bcc) 存在 -> 阻擋退出
        mock_status.reset_mock()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(make_raw_email("user@example.com", "user@example.com", bcc_val="boss@example.com")))), \
             self.assertRaises(SystemExit):
            main()
        mock_status.assert_not_called()

if __name__ == "__main__":
    unittest.main()
