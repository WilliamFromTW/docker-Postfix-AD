require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# -------------------------------------------------------------
# 0. 企業級雙層郵件收回 (Two-Tier Message Recall) 全域攔截處理
# 支援 Outlook 原生收回 (X-MS-Exchange 標頭, Recall:, 撤回:) 與行動端 (#recall)
# -------------------------------------------------------------
if anyof (
    exists "X-MS-Exchange-Organization-Recall-Action",
    header :matches "Subject" ["*#recall*", "*#RECALL*", "*Recall:*", "*Recall：*", "*撤回:*", "*撤回：*", "*收回:*", "*收回：*"]
) {
    pipe :copy "handle_recall.py";
    discard;
    stop;
}

# 1. 攔截本人寄給本人的指令信或口語休假信 (交由 handle_autoreply.py 進行完整 MIME 解碼與分析)
# 排除系統自動回覆確認信與回信轉發
if not header :matches "Subject" [
    "*【自動回覆通知】*", "*【自动回复通知】*",
    "*[Auto-Reply Notification]*", "*[Thông báo tự động trả lời]*",
    "*Re: *", "*Fwd: *"
] {
    # 情況 A：主旨包含 # 指令 (ASCII 格式永遠不被 MIME 編碼)
    if header :matches "Subject" "*#*" {
        pipe :copy "handle_autoreply.py";
        keep;
        stop;
    }
    # 情況 B：Envelope 信封寄收件人相同 (From == To，徹底解決客戶端 RFC 2047 MIME 編碼問題)
    elsif envelope :matches "from" "*" {
        set "env_from" "${1}";
        if envelope :matches "to" "*" {
            set "env_to" "${1}";
            if string :is "${env_from}" "${env_to}" {
                pipe :copy "handle_autoreply.py";
                keep;
                stop;
            }
        }
    }
    # 情況 C：Header Address 由本人寄給本人 (From == To)
    elsif address :matches "from" "*" {
        set "addr_from" "${1}";
        if address :matches "to" "*" {
            set "addr_to" "${1}";
            if string :is "${addr_from}" "${addr_to}" {
                pipe :copy "handle_autoreply.py";
                keep;
                stop;
            }
        }
    }
}

# 2. 外部一般來信（全域攔截交由 15 秒非同步延遲發信器處理）
if not anyof (
    header :matches "From" ["*noreply*", "*no-reply*", "*donotreply*", "*mailer-daemon*", "*postmaster*", "*dmarc*", "*bounce*", "*notification*"],
    header :matches "Sender" ["*noreply*", "*no-reply*", "*donotreply*", "*mailer-daemon*", "*postmaster*", "*dmarc*", "*bounce*", "*notification*"],
    header :matches "Precedence" ["bulk", "list", "junk", "auto_reply"],
    header :matches "Auto-Submitted" ["auto-generated", "auto-replied"],
    header :contains "Content-Type" "multipart/report"
) {
    pipe :copy "send_delayed_vacation.py";
}
