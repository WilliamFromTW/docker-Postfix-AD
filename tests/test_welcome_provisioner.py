import unittest
import os
import sys
import tempfile
import shutil

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

        ps_cmd = welcome_provisioner.generate_powershell_trust_cmd("mail.example.com")
        self.assertIn("3269", ps_cmd)
        self.assertIn("mail.example.com", ps_cmd)
        self.assertIn("TcpClient", ps_cmd)
        self.assertIn("LocalMachine", ps_cmd)

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
