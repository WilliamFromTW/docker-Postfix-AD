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
            "回收:*", "回收：*", "Re: 回收:*", "RE: 回收:*", "Fwd: 回收:*", "FW: 回收:*",
            "取り消し:*", "取り消し：*", "Re: 取り消し:*", "RE: 取り消し:*", "Fwd: 取り消し:*", "FW: 取り消し:*",
            "取消:*", "取消：*", "Re: 取消:*", "RE: 取消:*", "Fwd: 取消:*", "FW: 取消:*",
            "Thu hồi:*", "Thu hồi：*", "Re: Thu hồi:*", "RE: Thu hồi:*", "Fwd: Thu hồi:*", "FW: Thu hồi:*"
        ],
        # 雙重保險：支援 RFC 2047 MIME Base64 原始字串匹配 (繁中Big5/簡中GBK/日文CP932/越南文UTF-8，嚴格開頭比對無前置 *)
        # 繁中 Big5: pl6mr (回收:), pqymX (收回:), uk2mX (撤回:)
        # 簡中 GBK/GB2312: s7e72 (撤回:), ytW72 (收回:), u9jK1 (回收:)
        # 日文 UTF-8: 5Y+W44KK5raI44GX (取り消し:), 5Y+W5raI (取消:)
        # 日文 CP932: juaC6I (取り消し:), juaPw (取消:)
        # 日文 ISO-2022-JP: GyRCPGg
        # 越南文 UTF-8: VGh1IGjhu5Np (Thu hồi:)
        # 萬國 UTF-8: 5Zue5pS2 (回收:), 5pS25Zue (收回:), 5pKk5Zue (撤回:)
        header :matches "Subject" [
            # 繁中 Big5
            "=?*?B?pl6mr*", "=?*?b?pl6mr*", "Re: =?*?B?pl6mr*", "RE: =?*?B?pl6mr*", "Fwd: =?*?B?pl6mr*", "FW: =?*?B?pl6mr*",
            "=?*?B?pqymX*", "=?*?b?pqymX*", "Re: =?*?B?pqymX*", "RE: =?*?B?pqymX*", "Fwd: =?*?B?pqymX*", "FW: =?*?B?pqymX*",
            "=?*?B?uk2mX*", "=?*?b?uk2mX*", "Re: =?*?B?uk2mX*", "RE: =?*?B?uk2mX*", "Fwd: =?*?B?uk2mX*", "FW: =?*?B?uk2mX*",
            # 簡中 GB2312 / GBK / GB18030
            "=?*?B?s7e72*", "=?*?b?s7e72*", "Re: =?*?B?s7e72*", "RE: =?*?B?s7e72*", "Fwd: =?*?B?s7e72*", "FW: =?*?B?s7e72*",
            "=?*?B?ytW72*", "=?*?b?ytW72*", "Re: =?*?B?ytW72*", "RE: =?*?B?ytW72*", "Fwd: =?*?B?ytW72*", "FW: =?*?B?ytW72*",
            "=?*?B?u9jK1*", "=?*?b?u9jK1*", "Re: =?*?B?u9jK1*", "RE: =?*?B?u9jK1*", "Fwd: =?*?B?u9jK1*", "FW: =?*?B?u9jK1*",
            # 日文 UTF-8 / CP932 / ISO-2022-JP
            "=?*?B?5Y+W44KK5raI44GX*", "=?*?b?5Y+W44KK5raI44GX*", "Re: =?*?B?5Y+W44KK5raI44GX*", "RE: =?*?B?5Y+W44KK5raI44GX*",
            "=?*?B?5Y+W5raI*", "=?*?b?5Y+W5raI*", "Re: =?*?B?5Y+W5raI*", "RE: =?*?B?5Y+W5raI*",
            "=?*?B?juaC6I*", "=?*?b?juaC6I*", "Re: =?*?B?juaC6I*", "RE: =?*?B?juaC6I*",
            "=?*?B?juaPw*", "=?*?b?juaPw*", "Re: =?*?B?juaPw*", "RE: =?*?B?juaPw*",
            "=?*?B?GyRCPGg*", "=?*?b?GyRCPGg*", "Re: =?*?B?GyRCPGg*", "RE: =?*?B?GyRCPGg*",
            # 越南文 UTF-8
            "=?*?B?VGh1IGjhu5Np*", "=?*?b?VGh1IGjhu5Np*", "Re: =?*?B?VGh1IGjhu5Np*", "RE: =?*?B?VGh1IGjhu5Np*", "Fwd: =?*?B?VGh1IGjhu5Np*", "FW: =?*?B?VGh1IGjhu5Np*",
            # UTF-8 中文
            "=?*?B?5Zue5pS2*", "=?*?b?5Zue5pS2*", "Re: =?*?B?5Zue5pS2*", "RE: =?*?B?5Zue5pS2*", "Fwd: =?*?B?5Zue5pS2*", "FW: =?*?B?5Zue5pS2*",
            "=?*?B?5pS25Zue*", "=?*?b?5pS25Zue*", "Re: =?*?B?5pS25Zue*", "RE: =?*?B?5pS25Zue*", "Fwd: =?*?B?5pS25Zue*", "FW: =?*?B?5pS25Zue*",
            "=?*?B?5pKk5Zue*", "=?*?b?5pKk5Zue*", "Re: =?*?B?5pKk5Zue*", "RE: =?*?B?5pKk5Zue*", "Fwd: =?*?B?5pKk5Zue*", "FW: =?*?B?5pKk5Zue*"
        ]
    ) {
        pipe :copy "handle_recall.py";
        discard;
        stop;
    }
}
