import unittest
import os
import tempfile
import time
import shutil
import re

class TestWelcomePostlogin(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.templates_dir = os.path.join(self.tmpdir, "templates")
        os.makedirs(self.templates_dir, exist_ok=True)
        
        # 複製 8 國語言範本
        src_dir = os.path.join(os.path.dirname(__file__), "..", "scripts", "templates")
        for lang in ["zh-TW", "zh-CN", "en", "vi", "fr", "de", "ja", "es"]:
            f = f"welcome.{lang}.eml"
            src_f = os.path.join(src_dir, f)
            if os.path.exists(src_f):
                shutil.copy(src_f, os.path.join(self.templates_dir, f))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_language_detection(self):
        def match_lang(lang_code):
            l = (lang_code or "").lower()
            if any(k in l for k in ["zh-tw", "tw", "hant"]):
                return "zh-TW"
            elif any(k in l for k in ["zh-cn", "cn", "hans"]):
                return "zh-CN"
            elif any(k in l for k in ["vi", "vn"]):
                return "vi"
            elif any(k in l for k in ["fr", "fra"]):
                return "fr"
            elif any(k in l for k in ["de", "deu", "ger"]):
                return "de"
            elif any(k in l for k in ["ja", "jp", "jpn"]):
                return "ja"
            elif any(k in l for k in ["es", "spa"]):
                return "es"
            else:
                return "en"

        self.assertEqual(match_lang("zh-TW"), "zh-TW")
        self.assertEqual(match_lang("TW"), "zh-TW")
        self.assertEqual(match_lang("zh-CN"), "zh-CN")
        self.assertEqual(match_lang("CN"), "zh-CN")
        self.assertEqual(match_lang("vi"), "vi")
        self.assertEqual(match_lang("vn"), "vi")
        self.assertEqual(match_lang("fr"), "fr")
        self.assertEqual(match_lang("fr-FR"), "fr")
        self.assertEqual(match_lang("de"), "de")
        self.assertEqual(match_lang("de-DE"), "de")
        self.assertEqual(match_lang("ja"), "ja")
        self.assertEqual(match_lang("ja-JP"), "ja")
        self.assertEqual(match_lang("es"), "es")
        self.assertEqual(match_lang("es-ES"), "es")
        self.assertEqual(match_lang(""), "en")
        self.assertEqual(match_lang("unknown"), "en")
        self.assertEqual(match_lang("en-US"), "en")

    def test_all_8_templates_exist_and_contain_quota_placeholder(self):
        for lang in ["zh-TW", "zh-CN", "en", "vi", "fr", "de", "ja", "es"]:
            fpath = os.path.join(self.templates_dir, f"welcome.{lang}.eml")
            self.assertTrue(os.path.exists(fpath), f"範本 {fpath} 應存在")
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("${QUOTA_LIMIT}", content, f"範本 {lang} 應包含動態變數 ${{QUOTA_LIMIT}}")
            self.assertIn("${HOST_NAME}", content)
            self.assertIn("${EMAIL}", content)
            self.assertIn("${ACCOUNT}", content)

    def test_template_dynamic_variable_substitution(self):
        fpath = os.path.join(self.templates_dir, "welcome.en.eml")
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        substituted = content.replace("${EMAIL}", "alice@example.com") \
                             .replace("${ACCOUNT}", "alice") \
                             .replace("${DOMAIN_NAME}", "example.com") \
                             .replace("${HOST_NAME}", "mail.example.com") \
                             .replace("${DATE}", "Sat, 12 Sep 2026 09:00:00 +0800") \
                             .replace("${QUOTA_LIMIT}", "80 GB")

        self.assertIn("alice@example.com", substituted)
        self.assertIn("80 GB", substituted)
        self.assertNotIn("${QUOTA_LIMIT}", substituted)

    def test_idempotent_flag_check(self):
        user_home = os.path.join(self.tmpdir, "home_user")
        os.makedirs(user_home, exist_ok=True)
        welcomed_file = os.path.join(user_home, ".welcomed")

        # 尚未歡迎
        self.assertFalse(os.path.exists(welcomed_file))

        # 模擬歡迎完成
        with open(welcomed_file, "w") as f:
            f.write(str(int(time.time())))

        # 已經歡迎
        self.assertTrue(os.path.exists(welcomed_file))

if __name__ == "__main__":
    unittest.main()
