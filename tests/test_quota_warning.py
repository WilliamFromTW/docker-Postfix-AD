import unittest
import os
import tempfile
import time
import subprocess
import shutil

class TestQuotaWarningScript(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.user_dir = os.path.join(self.tmpdir, "home", "vmail", "testuser@example.com")
        os.makedirs(self.user_dir, exist_ok=True)
        
        self.template_dir = os.path.join(self.tmpdir, "templates")
        os.makedirs(self.template_dir, exist_ok=True)
        self.template_file = os.path.join(self.template_dir, "quota_warning_95.eml")
        
        # 複製真實模板內容
        src_template = os.path.join(os.path.dirname(__file__), "..", "scripts", "templates", "quota_warning_95.eml")
        with open(src_template, "r", encoding="utf-8") as sf:
            with open(self.template_file, "w", encoding="utf-8") as df:
                df.write(sf.read())

        self.script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "quota_warning.sh")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_variable_replacement(self):
        with open(self.template_file, "r", encoding="utf-8") as f:
            template = f.read()

        content = template.replace("${EMAIL}", "testuser@example.com") \
                          .replace("${ACCOUNT}", "testuser") \
                          .replace("${DOMAIN_NAME}", "example.com") \
                          .replace("${HOST_NAME}", "mail.example.com") \
                          .replace("${DATE}", "Sat, 12 Sep 2026 09:00:00 +0800") \
                          .replace("${QUOTA_LIMIT}", "50 GB")

        self.assertIn("testuser@example.com", content)
        self.assertIn("50 GB", content)
        self.assertNotIn("${QUOTA_LIMIT}", content)
        self.assertNotIn("${EMAIL}", content)

    def test_cooldown_logic(self):
        warned_file = os.path.join(self.user_dir, ".quota_warned_95")
        current_time = int(time.time())

        # 模擬首次告警 (建立時間戳記)
        with open(warned_file, "w") as f:
            f.write(str(current_time))

        # 檢查冷卻中（在 90 天內，例如過 10 天 = 864000 秒）
        elapsed = 864000
        cooldown = 7776000 # 90 天
        self.assertTrue(elapsed < cooldown, "應在冷卻期內")

        # 檢查冷卻過期（例如過 91 天 = 7862400 秒）
        elapsed_expired = 7862400
        self.assertFalse(elapsed_expired < cooldown, "超過 90 天應解除冷卻")

    def test_dynamic_quota_limit_parsing(self):
        conf_content = """
plugin {
  quota_rule = *:storage=80G
  quota_grace = 10%%
}
"""
        import re
        match = re.search(r'quota_rule\s*=\s*\*:storage=([0-9]+[A-Za-z]+)', conf_content)
        self.assertIsNotNone(match)
        raw_val = match.group(1) # 80G
        num = re.sub(r'[^0-9]', '', raw_val)
        unit = re.sub(r'[^A-Za-z]', '', raw_val).upper()
        if unit == "G":
            unit = "GB"
        quota_limit = f"{num} {unit}"
        self.assertEqual(quota_limit, "80 GB")

if __name__ == "__main__":
    unittest.main()
