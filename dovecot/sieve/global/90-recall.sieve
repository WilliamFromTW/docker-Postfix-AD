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
        header :matches "Subject" [
            "Recall:*", "Recall：*", "Re: Recall:*", "RE: Recall:*", "Fwd: Recall:*", "FW: Recall:*",
            "撤回:*", "撤回：*", "Re: 撤回:*", "RE: 撤回:*", "Fwd: 撤回:*", "FW: 撤回:*",
            "收回:*", "收回：*", "Re: 收回:*", "RE: 收回:*", "Fwd: 收回:*", "FW: 收回:*",
            "回收:*", "回收：*", "Re: 回收:*", "RE: 回收:*", "Fwd: 回收:*", "FW: 回收:*"
        ],
        # 雙重保險：支援 RFC 2047 MIME Base64 原始字串匹配 (Big5 與 UTF-8，嚴格開頭比對無前置 *)
        # Big5: pl6mr (回收:), pqymX (收回:), uk2mX (撤回:)
        # UTF-8: 5Zue5pS2 (回收:), 5pS25Zue (收回:), 5pKk5Zue (撤回:)
        header :matches "Subject" [
            "=?*?B?pl6mr*", "=?*?b?pl6mr*", "Re: =?*?B?pl6mr*", "RE: =?*?B?pl6mr*", "Fwd: =?*?B?pl6mr*", "FW: =?*?B?pl6mr*",
            "=?*?B?pqymX*", "=?*?b?pqymX*", "Re: =?*?B?pqymX*", "RE: =?*?B?pqymX*",
            "=?*?B?uk2mX*", "=?*?b?uk2mX*", "Re: =?*?B?uk2mX*", "RE: =?*?B?uk2mX*",
            "=?*?B?5Zue5pS2*", "=?*?b?5Zue5pS2*", "Re: =?*?B?5Zue5pS2*", "RE: =?*?B?5Zue5pS2*",
            "=?*?B?5pS25Zue*", "=?*?b?5pS25Zue*", "Re: =?*?B?5pS25Zue*", "RE: =?*?B?5pS25Zue*",
            "=?*?B?5pKk5Zue*", "=?*?b?5pKk5Zue*", "Re: =?*?B?5pKk5Zue*", "RE: =?*?B?5pKk5Zue*"
        ]
    ) {
        pipe :copy "handle_recall.py";
        discard;
        stop;
    }
}
