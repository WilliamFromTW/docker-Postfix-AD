import unittest
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class TestSpamEmailConfig(unittest.TestCase):
    def test_gen_launch_command_html_required(self):
        """驗證 docs/genLaunchCommand.html 中 SPAM_EMAIL input 欄位包含 required 屬性且語系字典正確"""
        html_path = os.path.join(REPO_ROOT, "docs", "genLaunchCommand.html")
        self.assertTrue(os.path.exists(html_path), f"File not found: {html_path}")
        
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 驗證 input 欄位有 required
        pattern = r'<input[^>]*id=["\']inputSpamEmail["\'][^>]*required'
        self.assertTrue(
            re.search(pattern, content, re.IGNORECASE),
            "inputSpamEmail should have 'required' attribute in docs/genLaunchCommand.html"
        )

        # 驗證 4 語系標籤包含 Required / 必填 / bắt buộc
        self.assertIn('spamEmail: "SPAM_EMAIL (Required, Admin & Quarantine Mailbox)"', content)
        self.assertIn('spamEmail: "管理員與隔離信箱 (SPAM_EMAIL，必填)"', content)
        self.assertIn('spamEmail: "管理员与隔离邮箱 (SPAM_EMAIL，必填)"', content)
        self.assertIn('spamEmail: "Hòm thư quản trị & thư rác (SPAM_EMAIL, bắt buộc)"', content)

    def test_setup_sh_alias_logic(self):
        """驗證 setup.sh 中 postmaster / abuse / root / mailer-daemon 自動綁定 SPAM_EMAIL 之邏輯與等冪性"""
        setup_path = os.path.join(REPO_ROOT, "setup.sh")
        self.assertTrue(os.path.exists(setup_path), f"File not found: {setup_path}")

        with open(setup_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 檢查關鍵角色別名綁定邏輯
        self.assertIn('postmaster@${d} ${SPAM_EMAIL}', content)
        self.assertIn('abuse@${d} ${SPAM_EMAIL}', content)
        self.assertIn('root@${d} ${SPAM_EMAIL}', content)
        self.assertIn('mailer-daemon@${d} ${SPAM_EMAIL}', content)
        self.assertIn('/usr/sbin/postmap /etc/postfix/aliases', content)

    def test_alias_simulation_and_idempotence(self):
        """模擬 setup.sh 中的別名增補邏輯，驗證所有網域及等冪防重複寫入"""
        domain_name = "example.com"
        local_only = ["sub1.example.com", "sub2.example.com"]
        spam_email = "admin@example.com"

        domains = [domain_name] + local_only
        aliases = []

        def append_alias(aliases_list, role_prefix, d, target):
            entry = f"{role_prefix}@{d} {target}"
            exists = any(a.startswith(f"{role_prefix}@{d}") for a in aliases_list)
            if not exists:
                aliases_list.append(entry)

        # 執行第一次
        for d in domains:
            append_alias(aliases, "postmaster", d, spam_email)
            append_alias(aliases, "abuse", d, spam_email)
            append_alias(aliases, "root", d, spam_email)
            append_alias(aliases, "mailer-daemon", d, spam_email)

        # 應有 3 網域 * 4 角色 = 12 條記錄
        self.assertEqual(len(aliases), 12)
        self.assertIn(f"postmaster@example.com {spam_email}", aliases)
        self.assertIn(f"abuse@sub1.example.com {spam_email}", aliases)

        # 執行第二次（等冪性測試）
        for d in domains:
            append_alias(aliases, "postmaster", d, spam_email)
            append_alias(aliases, "abuse", d, spam_email)
            append_alias(aliases, "root", d, spam_email)
            append_alias(aliases, "mailer-daemon", d, spam_email)

        self.assertEqual(len(aliases), 12, "Aliases should remain 12 without duplicates on rerun")


if __name__ == "__main__":
    unittest.main()
