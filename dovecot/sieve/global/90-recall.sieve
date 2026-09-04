require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# -------------------------------------------------------------
# 企業級雙層郵件收回 (Two-Tier Message Recall) 全域攔截過濾器
# 支援 Outlook 原生收回按鈕與行動端 #recall 關鍵字回覆
# -------------------------------------------------------------
if anyof (
    exists "X-MS-Exchange-Organization-Recall-Action",
    header :matches "Subject" ["*#recall*", "*#RECALL*", "*Recall:*", "*Recall：*", "*撤回:*", "*撤回：*", "*收回:*", "*收回：*"]
) {
    pipe :copy "handle_recall.py";
    discard;
    stop;
}
