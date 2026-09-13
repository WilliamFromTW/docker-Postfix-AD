#!/bin/bash
# ==============================================================================
# Dovecot 95% Quota Warning Notification Script
# Triggered by: Dovecot service quota-warning ($1 = percent, $2 = %u)
# Features:
#   - Dynamic ${QUOTA_LIMIT} resolution (doveadm quota get -> 90-quota.conf)
#   - 90-day (3-month) cooldown per user to prevent notification flooding
#   - Native injection via doveadm save with quota:noenforcing
# ==============================================================================

# 確保 PATH 環境變數存在，防止 doveadm 等 C 程式呼叫 t_binary_abspath() 時拋出 PATH undefined 致命錯誤
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

PERCENT="${1:-95}"
USER_ID="$2"

if [ -z "$USER_ID" ]; then
  exit 0
fi

# 1. 解析帳號與網域名稱
if [[ "$USER_ID" == *"@"* ]]; then
  USER_EMAIL="$USER_ID"
  ACCOUNT="${USER_ID%%@*}"
  DOMAIN_NAME="${USER_ID#*@}"
else
  ACCOUNT="$USER_ID"
  if [ -z "$DOMAIN_NAME" ] || [ "$DOMAIN_NAME" = "example.com" ]; then
    if [ -f "/etc/postfix/domains" ]; then
      DOMAIN_NAME=$(head -n 1 /etc/postfix/domains 2>/dev/null | tr -d '\r\n ')
    fi
  fi
  DOMAIN_NAME="${DOMAIN_NAME:-example.com}"
  USER_EMAIL="${ACCOUNT}@${DOMAIN_NAME}"
fi

# 2. 定位使用者目錄
USER_DIR=""
for d in "/home/vmail/${USER_EMAIL}" "/home/vmail/${ACCOUNT}"; do
  if [ -d "$d" ]; then
    USER_DIR="$d"
    break
  fi
done
if [ -z "$USER_DIR" ]; then
  USER_DIR="/home/vmail/${USER_EMAIL}"
fi

# 3. 檢查 90 天（3 個月）冷卻機制
WARNED_FILE="${USER_DIR}/.quota_warned_95"
CURRENT_TIME=$(date +%s)
COOLDOWN_SECONDS=7776000 # 90 days = 90 * 86400

if [ -f "$WARNED_FILE" ]; then
  LAST_WARNED=$(cat "$WARNED_FILE" 2>/dev/null || echo 0)
  if [ -n "$LAST_WARNED" ] && [ "$LAST_WARNED" -eq "$LAST_WARNED" ] 2>/dev/null; then
    ELAPSED=$(( CURRENT_TIME - LAST_WARNED ))
    if [ "$ELAPSED" -lt "$COOLDOWN_SECONDS" ] && [ "$ELAPSED" -ge 0 ]; then
      # 90 天冷卻期內，靜默略過
      exit 0
    fi
  fi
fi

# 4. 動態提取當前生效配額 ${QUOTA_LIMIT}
QUOTA_LIMIT=""
if command -v doveadm >/dev/null 2>&1; then
  RAW_LIMIT=$(doveadm quota get -u "$USER_ID" 2>/dev/null | awk '$2=="STORAGE" {print $4}')
  if [ -n "$RAW_LIMIT" ] && [ "$RAW_LIMIT" -gt 0 ] 2>/dev/null; then
    GB=$(( RAW_LIMIT / 1024 / 1024 ))
    if [ "$GB" -gt 0 ]; then
      QUOTA_LIMIT="${GB} GB"
    else
      MB=$(( RAW_LIMIT / 1024 ))
      QUOTA_LIMIT="${MB} MB"
    fi
  fi
fi

if [ -z "$QUOTA_LIMIT" ] && [ -f "/etc/dovecot/conf.d/90-quota.conf" ]; then
  CONF_RULE=$(grep -E '^\s*quota_rule\s*=' /etc/dovecot/conf.d/90-quota.conf 2>/dev/null | sed -E 's/.*storage=([0-9]+[A-Za-z]+).*/\1/' | head -n 1)
  if [ -n "$CONF_RULE" ]; then
    NUM=$(echo "$CONF_RULE" | tr -dc '0-9')
    UNIT=$(echo "$CONF_RULE" | tr -dc 'A-Za-z' | tr '[:lower:]' '[:upper:]')
    [ -z "$UNIT" ] && UNIT="B"
    [[ "$UNIT" == "G" ]] && UNIT="GB"
    [[ "$UNIT" == "M" ]] && UNIT="MB"
    QUOTA_LIMIT="${NUM} ${UNIT}"
  fi
fi

[ -z "$QUOTA_LIMIT" ] && QUOTA_LIMIT="50 GB"

# 5. 解析主機名稱與日期
HOST_NAME="${HOST_NAME:-mail.${DOMAIN_NAME}}"
if [ -f "/etc/postfix/main.cf" ]; then
  MY_HOST=$(grep -E '^\s*myhostname\s*=' /etc/postfix/main.cf 2>/dev/null | awk -F'=' '{print $2}' | tr -d ' ')
  [ -n "$MY_HOST" ] && [ "$MY_HOST" != "HOST_NAME" ] && HOST_NAME="$MY_HOST"
fi
DATE=$(date -R 2>/dev/null || date)

# 6. 尋找範本檔案
TEMPLATE="/etc/dovecot/welcome_templates/quota_warning_95.eml"
if [ ! -f "$TEMPLATE" ]; then
  TEMPLATE="/usr/lib/dovecot/sieve-pipe/templates/quota_warning_95.eml"
fi
if [ ! -f "$TEMPLATE" ]; then
  # 搜尋相對路徑備用（本地測試支援）
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "${SCRIPT_DIR}/templates/quota_warning_95.eml" ]; then
    TEMPLATE="${SCRIPT_DIR}/templates/quota_warning_95.eml"
  elif [ -f "${SCRIPT_DIR}/../dovecot/welcome_templates/quota_warning_95.eml" ]; then
    TEMPLATE="${SCRIPT_DIR}/../dovecot/welcome_templates/quota_warning_95.eml"
  fi
fi

if [ ! -f "$TEMPLATE" ]; then
  exit 0
fi

# 7. 變數置換
CONTENT=$(sed -e "s/\${EMAIL}/${USER_EMAIL}/g" \
              -e "s/\${ACCOUNT}/${ACCOUNT}/g" \
              -e "s/\${DOMAIN_NAME}/${DOMAIN_NAME}/g" \
              -e "s/\${HOST_NAME}/${HOST_NAME}/g" \
              -e "s/\${DATE}/${DATE}/g" \
              -e "s/\${QUOTA_LIMIT}/${QUOTA_LIMIT}/g" "$TEMPLATE")

# 8. 透過 Dovecot 原生工具存入 INBOX (帶 noenforcing 確保即使已接近額滿仍必達)
SAVE_STATUS=0
if command -v doveadm >/dev/null 2>&1; then
  printf "%s" "$CONTENT" | doveadm -o "plugin/quota=count:User quota:noenforcing" save -u "$USER_ID" -m INBOX
  SAVE_STATUS=$?
fi

# 9. 成功存入後更新時間戳記
if [ $SAVE_STATUS -eq 0 ]; then
  mkdir -p "$USER_DIR" 2>/dev/null || true
  echo "$CURRENT_TIME" > "$WARNED_FILE" 2>/dev/null || true
fi
