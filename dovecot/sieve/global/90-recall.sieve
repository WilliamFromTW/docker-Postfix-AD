require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# -------------------------------------------------------------
# 企業級雙層郵件收回 (Two-Tier Message Recall) 全域攔截過濾器
# 支援 Outlook 原生收回按鈕與行動端 #recall 關鍵字回覆
# 排除系統回報信與自動回信，具備四重防呆防誤殺與防自觸發迴圈機制
# -------------------------------------------------------------
if exists "X-Recall-Processed" {
    keep;
    stop;
}

if not anyof (
    header :matches "Subject" ["*郵件收回狀態報告*", "*Message Recall Status*"],
    header :matches "Auto-Submitted" ["auto-generated", "auto-replied"],
    header :matches "From" ["*postmaster*", "*mailer-daemon*", "*vmail*"]
) {
    if anyof (
        exists "X-MS-Exchange-Organization-Recall-Action",
        header :matches "Subject" ["*#recall*", "*#RECALL*"],
        allof (
            header :matches "Subject" [
                "Recall:*", "Recall：*", "Re: Recall:*", "RE: Recall:*", "Fwd: Recall:*", "FW: Recall:*",
                "撤回:*", "撤回：*", "Re: 撤回:*", "RE: 撤回:*", "Fwd: 撤回:*", "FW: 撤回:*",
                "收回:*", "收回：*", "Re: 收回:*", "RE: 收回:*", "Fwd: 收回:*", "FW: 收回:*",
                "回收:*", "回收：*", "Re: 回收:*", "RE: 回收:*", "Fwd: 回收:*", "FW: 回收:*",
                "回顧:*", "回顧：*", "Re: 回顧:*", "RE: 回顧:*", "Fwd: 回顧:*", "FW: 回顧:*"
            ],
            anyof (
                exists "In-Reply-To",
                exists "References"
            )
        )
    ) {
        pipe :copy "handle_recall.py";
        discard;
        stop;
    }
}
