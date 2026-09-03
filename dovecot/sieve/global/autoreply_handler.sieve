require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# 1. 攔截由本人寄給本人的指令信或四語系口語休假/銷假信
if allof (
    header :matches "Subject" [
        "*#*",
        "*休假*", "*請假*", "*出差*", "*公出*", "*不在*", "*特休*", "*事假*", "*病假*", "*銷假*", "*取消*", "*停用*", "*關閉*",
        "*请假*", "*年假*", "*销假*", "*关闭*",
        "*nghỉ phép*", "*nghỉ*", "*đi công tác*", "*công tác*", "*vắng mặt*", "*nghỉ ốm*", "*hủy*", "*tắt*",
        "*vacation*", "*holiday*", "*leave*", "*out of office*", "*ooo*", "*day off*", "*business trip*", "*cancel*", "*disable*", "*turn off*"
    ],
    not header :matches "Subject" [
        "*【自動回覆通知】*", "*【自动回复通知】*",
        "*[Auto-Reply Notification]*", "*[Thông báo tự động trả lời]*",
        "*Re: *", "*Fwd: *"
    ]
) {
    pipe :copy "handle_autoreply.py";
    keep;
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
