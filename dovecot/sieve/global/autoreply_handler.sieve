require ["vnd.dovecot.pipe", "copy", "variables", "envelope", "subaddress"];

# 攔截由本人寄給本人的指令信 (#autoreply / #vacation / #休假 / #不在 / #出差 / #請假)
if allof (
    header :matches "Subject" "*#*",
    header :matches "Subject" ["*#autoreply*", "*#vacation*", "*#休假*", "*#不在*", "*#出差*", "*#請假*"]
) {
    # 安全 Pipe 傳遞給 Python 腳本解析並動態編譯該使用者的 dovecot.sieve 規則
    pipe :copy "handle_autoreply.py";
}
