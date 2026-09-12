import unittest
import os
import tempfile
import re

class TestQuotaUpgradeLogic(unittest.TestCase):
    def test_quota_upgrade_from_20g_to_50g(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_dir, exist_ok=True)
            quota_conf = os.path.join(conf_dir, "90-quota.conf")
            
            # 模擬舊版 20G 設定檔
            with open(quota_conf, "w", encoding="utf-8") as f:
                f.write("""plugin {
  quota_rule = *:storage=20G
  quota_grace = 10%%
}
""")
            
            # 模擬 setup.sh 中的升級邏輯
            with open(quota_conf, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "quota_rule = *:storage=20G" in content:
                content = content.replace("quota_rule = *:storage=20G", "quota_rule = *:storage=50G")
            
            if "service quota-warning" not in content:
                content += """
plugin {
  quota_warning = storage=95%% quota-warning 95 %u
}

service quota-warning {
  executable = script /usr/lib/dovecot/sieve-pipe/quota_warning.sh
  user = vmail
  unix_listener quota-warning {
    user = vmail
    mode = 0660
  }
}
"""
            with open(quota_conf, "w", encoding="utf-8") as f:
                f.write(content)
            
            with open(quota_conf, "r", encoding="utf-8") as f:
                upgraded = f.read()
            
            self.assertIn("quota_rule = *:storage=50G", upgraded)
            self.assertNotIn("quota_rule = *:storage=20G", upgraded)
            self.assertIn("service quota-warning", upgraded)
            self.assertIn("quota_warning = storage=95%%", upgraded)

    def test_custom_quota_retained(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_dir, exist_ok=True)
            quota_conf = os.path.join(conf_dir, "90-quota.conf")
            
            # 模擬使用者自訂 80G 設定檔
            with open(quota_conf, "w", encoding="utf-8") as f:
                f.write("""plugin {
  quota_rule = *:storage=80G
  quota_grace = 10%%
}
""")
            
            with open(quota_conf, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "quota_rule = *:storage=20G" in content:
                content = content.replace("quota_rule = *:storage=20G", "quota_rule = *:storage=50G")
            
            self.assertIn("quota_rule = *:storage=80G", content)
            self.assertNotIn("quota_rule = *:storage=50G", content)

if __name__ == "__main__":
    unittest.main()
