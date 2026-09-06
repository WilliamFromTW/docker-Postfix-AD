require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# -------------------------------------------------------------
# 新人首次收信開戶迎新過濾器 (Mailbox Onboarding First-Delivery Hook)
# 排除系統回信、退信與系統通報，防止迴圈
# -------------------------------------------------------------
if not anyof (
    header :matches "Subject" ["*歡迎加入*", "*Welcome*", "*[系統通報]*", "*Message Recall Status*", "*郵件收回狀態報告*"],
    header :matches "Auto-Submitted" ["auto-generated", "auto-replied"],
    header :matches "From" ["*postmaster*", "*mailer-daemon*", "*vmail*"]
) {
    pipe :copy "welcome_provisioner.py" ["--event", "delivery"];
}
