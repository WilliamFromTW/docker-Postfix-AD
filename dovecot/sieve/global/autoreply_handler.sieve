require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# 1. 攔截由本人寄給本人的指令信 (#autoreply / #vacation / #休假 / #不在 / #出差 / #請假)
if allof (
    header :matches "Subject" "*#*",
    header :matches "Subject" ["*#autoreply*", "*#vacation*", "*#休假*", "*#不在*", "*#出差*", "*#請假*"],
    not header :matches "Subject" ["*【自動回覆通知】*", "*[Auto-Reply Notification]*", "*Re: *", "*Fwd: *"]
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
