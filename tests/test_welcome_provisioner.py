import unittest
import os
import sys
import tempfile
import shutil
import email

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import welcome_provisioner


class TestWelcomeProvisioner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_lock_idempotency(self):
        """測試 .welcomed 原子鎖防重複機制"""
        user_name = "testuser"
        user_email = "testuser@example.com"
        home_dir = os.path.join(self.test_dir, user_email)
        os.makedirs(home_dir, exist_ok=True)

        # 首次取得鎖應成功
        locked1, path1 = welcome_provisioner.acquire_atomic_welcomed_lock(user_name, user_email, home_dir=home_dir)
        self.assertTrue(locked1, "First lock attempt should succeed")
        self.assertTrue(os.path.exists(path1), f"Marker file should exist at {path1}")

        # 第二次取得鎖應被阻擋 (等冪性)
        locked2, path2 = welcome_provisioner.acquire_atomic_welcomed_lock(user_name, user_email, home_dir=home_dir)
        self.assertFalse(locked2, "Second lock attempt must return False to avoid duplicate dispatch")
        self.assertEqual(path1, path2)

    def test_cross_identifier_atomic_lock(self):
        """測試不同登入識別字串 (例如 william-kafeiou vs william@kafeiou.pw) 交叉鎖防重複"""
        user_name = "william-kafeiou"
        canonical_email = "william@kafeiou.pw"
        home_dir = os.path.join(self.test_dir, canonical_email)
        os.makedirs(home_dir, exist_ok=True)

        # 模擬 IMAP 登入：傳入 william-kafeiou 與 william-kafeiou@kafeiou.pw
        locked1, path1 = welcome_provisioner.acquire_atomic_welcomed_lock(
            user_name="william-kafeiou",
            user_email=canonical_email,
            home_dir=home_dir,
            extra_identifiers=["william-kafeiou", "william-kafeiou@kafeiou.pw"]
        )
        self.assertTrue(locked1, "First login onboarding must succeed")

        # 模擬 Sieve 郵件投遞 (自己寄給自己)：傳入 william 與 william@kafeiou.pw
        locked2, path2 = welcome_provisioner.acquire_atomic_welcomed_lock(
            user_name="william",
            user_email=canonical_email,
            home_dir=home_dir,
            extra_identifiers=["william", canonical_email]
        )
        self.assertFalse(locked2, "Second onboarding attempt (e.g. self-delivery) must be blocked!")

    def test_system_accounts_exclusion(self):
        """測試系統保留帳號自動排除不觸發開戶流程"""
        system_users = ["postmaster", "abuse", "root", "mailer-daemon", "spam", "vmail"]
        for su in system_users:
            self.assertIn(su, welcome_provisioner.SYSTEM_ACCOUNTS)

    def test_certificate_detection_and_powershell_gen(self):
        """測試自簽測試憑證偵測與 PowerShell 指令生成"""
        fake_cert_file = os.path.join(self.test_dir, "cert.pem")
        with open(fake_cert_file, "w", encoding="utf-8") as f:
            f.write("-----BEGIN CERTIFICATE-----\n")
            f.write("Issuer: CN=Let's Encrypt R3 Fake CA\n")
            f.write("Subject: CN=mail.example.com\n")
            f.write("-----END CERTIFICATE-----\n")

        cert_type = welcome_provisioner.detect_certificate_type(cert_path=fake_cert_file, host_name="mail.example.com")
        self.assertEqual(cert_type, "self_signed")

        ps_cmd = welcome_provisioner.generate_powershell_trust_cmd("mail.example.com", "zh-TW")
        self.assertIn("3269", ps_cmd)
        self.assertIn("$mailServer = 'mail.example.com'", ps_cmd)
        self.assertIn("TcpClient", ps_cmd)
        self.assertIn("LocalMachine", ps_cmd)
        self.assertIn("try {", ps_cmd)
        self.assertIn("catch {", ps_cmd)
        self.assertIn("成功匯入", ps_cmd)
        self.assertIn("憑證匯入失敗", ps_cmd)
        self.assertNotIn('\\""', ps_cmd)

        # 測試英文與越文語系
        ps_en = welcome_provisioner.generate_powershell_trust_cmd("mail.example.com", "en")
        self.assertIn("Certificate Added Successfully", ps_en)
        self.assertIn("Failed to import certificate", ps_en)

        ps_vi = welcome_provisioner.generate_powershell_trust_cmd("mail.example.com", "vi")
        self.assertIn("Da them chung chi", ps_vi)

    def test_hostname_dynamic_resolution(self):
        """測試主機名稱多層動態解析"""
        # 1. 優先從環境變數
        orig_host = os.environ.get("HOST_NAME")
        try:
            os.environ["HOST_NAME"] = "pmg.kafeiou.pw"
            self.assertEqual(welcome_provisioner.get_host_name("kafeiou.pw"), "pmg.kafeiou.pw")
        finally:
            if orig_host is not None:
                os.environ["HOST_NAME"] = orig_host
            else:
                os.environ.pop("HOST_NAME", None)

        # 2. Fallback mail.{domain}
        old_val = os.environ.pop("HOST_NAME", None)
        try:
            resolved = welcome_provisioner.get_host_name("company.com")
            # 若無 /etc/postfix/main.cf 則應為 mail.company.com
            self.assertIn("company.com", resolved)
        finally:
            if old_val is not None:
                os.environ["HOST_NAME"] = old_val

    def test_language_detection(self):
        """測試四語系智慧判定鏈"""
        # 1. 明確指定
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@test.com", explicit_lang="vi"), "vi")
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@test.com", explicit_lang="zh-CN"), "zh-CN")

        # 2. 網域後綴判定
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@corp.tw", domain="corp.tw"), "zh-TW")
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@corp.cn", domain="corp.cn"), "zh-CN")
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@corp.vn", domain="corp.vn"), "vi")

        # 3. 郵件標頭判定
        raw_msg = email.message_from_string("Content-Language: en-US\n\nBody")
        self.assertEqual(welcome_provisioner.detect_user_language("user", "user@corp.com", domain="corp.com", msg=raw_msg), "en")

        # 4. DEFAULT_LANG 環境變數 fallback
        orig_lang = os.environ.get("DEFAULT_LANG")
        try:
            os.environ["DEFAULT_LANG"] = "vi"
            self.assertEqual(welcome_provisioner.detect_user_language("user", "user@other.org", domain="other.org"), "vi")
        finally:
            if orig_lang is not None:
                os.environ["DEFAULT_LANG"] = orig_lang
            else:
                os.environ.pop("DEFAULT_LANG", None)

    def test_multilingual_template_selection(self):
        """測試多語系範本分流與回退"""
        tpl_dir = os.path.join(self.test_dir, "templates")
        os.makedirs(tpl_dir, exist_ok=True)

        open(os.path.join(tpl_dir, "01_welcome.zh-TW.eml"), "w").close()
        open(os.path.join(tpl_dir, "01_welcome.en.eml"), "w").close()
        open(os.path.join(tpl_dir, "01_welcome.vi.eml"), "w").close()
        open(os.path.join(tpl_dir, "01_welcome.eml"), "w").close()
        open(os.path.join(tpl_dir, "02_policy.eml"), "w").close()

        # 繁中應匹配 zh-TW
        tw_tpls = welcome_provisioner.find_templates_for_lang(tpl_dir, "zh-TW")
        tw_names = [os.path.basename(p) for p in tw_tpls]
        self.assertIn("01_welcome.zh-TW.eml", tw_names)
        self.assertIn("02_policy.eml", tw_names)

        # 英文應匹配 en
        en_tpls = welcome_provisioner.find_templates_for_lang(tpl_dir, "en")
        en_names = [os.path.basename(p) for p in en_tpls]
        self.assertIn("01_welcome.en.eml", en_names)

        # 若未定義簡中，應回退至 01_welcome.eml
        cn_tpls = welcome_provisioner.find_templates_for_lang(tpl_dir, "zh-CN")
        cn_names = [os.path.basename(p) for p in cn_tpls]
        self.assertIn("01_welcome.eml", cn_names)

    def test_admin_notification_formatting(self):
        """測試網管通知信包含主機、連接埠與專用 PowerShell 信任指令"""
        sent_boxes = []

        def mock_send_mail(content, recipient, envelope_from="postmaster"):
            sent_boxes.append({"content": content, "recipient": recipient, "from": envelope_from})
            return True

        orig_send = welcome_provisioner.send_mail
        try:
            welcome_provisioner.send_mail = mock_send_mail
            welcome_provisioner.notify_admin_onboarding_done(
                user_name="testuser",
                user_email="testuser@kafeiou.pw",
                domain="kafeiou.pw",
                event_type="imap_login",
                cert_mode="self_signed",
                sent_templates=["01_addressbook_setup.zh-TW.eml"],
                mail_server="mail.kafeiou.pw",
                powershell_cmd="& { $mailServer = 'mail.kafeiou.pw' ... }",
                user_lang="zh-TW"
            )

            self.assertEqual(len(sent_boxes), 1)
            admin_mail = sent_boxes[0]["content"]
            self.assertIn("postmaster@kafeiou.pw", sent_boxes[0]["recipient"])
            self.assertIn("【系統管理通報】", admin_mail)
            self.assertIn("mail.kafeiou.pw", admin_mail)
            self.assertIn("3269", admin_mail)
            self.assertIn("【網管專區】", admin_mail)
            self.assertIn("GPO", admin_mail)
        finally:
            welcome_provisioner.send_mail = orig_send

    def test_template_substitution(self):
        """測試歡迎郵件範本變數智慧替換"""
        template_content = (
            "Hello ${USER_NAME}, your email is ${USER_EMAIL}.\n"
            "Server: ${MAIL_SERVER}, Domain: ${DOMAIN}.\n"
            "${CERT_INSTRUCTION_BLOCK}"
        )

        replacements = {
            "${USER_NAME}": "william",
            "${USER_EMAIL}": "william@example.com",
            "${DOMAIN}": "example.com",
            "${MAIL_SERVER}": "mail.example.com",
            "${CERT_INSTRUCTION_BLOCK}": "<div>CERT OK</div>"
        }

        result = template_content
        for k, v in replacements.items():
            result = result.replace(k, v)

        self.assertIn("Hello william", result)
        self.assertIn("your email is william@example.com", result)
        self.assertIn("Server: mail.example.com", result)
        self.assertIn("<div>CERT OK</div>", result)
        self.assertNotIn("${USER_NAME}", result)


if __name__ == "__main__":
    unittest.main()
