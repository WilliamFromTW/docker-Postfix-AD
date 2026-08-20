#!/bin/bash

# 檢查是否輸入主機名稱
if [ -z "$1" ]; then
    echo "錯誤: 請提供主機名稱/網域。"
    echo "用法: $0 <domain_name>"
    exit 1
fi

DOMAIN=$1
TARGET_DIR="/etc/letsencrypt/live/$DOMAIN"

echo "正在為 $DOMAIN 建立測試憑證目錄..."
mkdir -p "$TARGET_DIR"

# 1. 產生私鑰 (privkey.pem) 與 終端憑證 (cert.pem)
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$TARGET_DIR/privkey.pem" \
    -out "$TARGET_DIR/cert.pem" \
    -days 365 \
    -subj "/CN=$DOMAIN" 2>/dev/null

# 2. 建立偽造的中繼憑證 (chain.pem)
# 模擬 Let's Encrypt R3 中繼憑證的結構
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout /tmp/fake_ca.key \
    -out "$TARGET_DIR/chain.pem" \
    -days 365 \
    -subj "/CN=Let's Encrypt R3 Fake CA" 2>/dev/null

# 3. 合併成完整憑證鏈 (fullchain.pem)
# 順序必須為：終端憑證 -> 中繼憑證
cat "$TARGET_DIR/cert.pem" "$TARGET_DIR/chain.pem" > "$TARGET_DIR/fullchain.pem"

# 清理暫存檔
rm -f /tmp/fake_ca.key

# 設定安全權限 (模擬 Let's Encrypt 的權限設定)
chmod 700 "/etc/letsencrypt/live" "/etc/letsencrypt" 2>/dev/null
chmod 644 "$TARGET_DIR"/*.pem

echo "成功！憑證已產生至: $TARGET_DIR"
ls -l "$TARGET_DIR"

