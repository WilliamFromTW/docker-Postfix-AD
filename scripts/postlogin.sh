#!/bin/bash
# ==============================================================================
# Dovecot Post-Login Hook: First-Login Welcome Email Delivery
# ==============================================================================

# 1. 快速防呆：若無 USER 變數直接放行
if [ -z "$USER" ]; then
  exec "$@"
fi

# 2. 定位使用者主目錄
USER_DIR="${HOME}"
if [ -z "$USER_DIR" ] || [ ! -d "$USER_DIR" ]; then
  for d in "/home/vmail/${USER}" "/home/vmail/${USER%%@*}"; do
    if [ -d "$d" ]; then
      USER_DIR="$d"
      break
    fi
  done
fi
[ -z "$USER_DIR" ] && USER_DIR="/home/vmail/${USER}"

# 3. 快速檢查：若已發送過歡迎信，立即極速放行 (<0.1ms)
if [ -f "${USER_DIR}/.welcomed" ]; then
  exec "$@"
fi

# 4. 非同步背景派送歡迎信，避免阻塞客戶端連線
(
  # 原子鎖防併發連線重複派送
  LOCK_DIR="${USER_DIR}/.welcoming_lock"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

  # 再次雙重檢查
  if [ -f "${USER_DIR}/.welcomed" ]; then
    exit 0
  fi

  # 解析帳號與網域名稱
  USER_ID="$USER"
  if [[ "$USER_ID" == *"@"* ]]; then
    USER_EMAIL="$USER_ID"
    ACCOUNT="${USER_ID%%@*}"
    DOMAIN_NAME="${USER_ID#*@}"
  else
    ACCOUNT="$USER_ID"
    DOMAIN_NAME="${DOMAIN_NAME:-example.com}"
    USER_EMAIL="${ACCOUNT}@${DOMAIN_NAME}"
  fi

  # 5. 判定使用者語系 (8 國語言，保底英文)
  LANG_CODE="${user_lang:-${USER_LANG}}"
  if [ -z "$LANG_CODE" ] && command -v ldapsearch >/dev/null 2>&1; then
    HOST_IP="${HOST_IP:-127.0.0.1}"
    SEARCH_BASE="${SEARCH_BASE:-}"
    BIND_DN="${BIND_DN:-}"
    BIND_PW="${BIND_PW:-}"
    if [ -n "$SEARCH_BASE" ]; then
      LDAP_CMD=("ldapsearch" "-x" "-h" "$HOST_IP" "-b" "$SEARCH_BASE" "(|(sAMAccountName=${ACCOUNT})(mail=${USER_EMAIL}))" "preferredLanguage")
      [ -n "$BIND_DN" ] && [ -n "$BIND_PW" ] && LDAP_CMD+=("-D" "$BIND_DN" "-w" "$BIND_PW")
      LANG_CODE=$("${LDAP_CMD[@]}" 2>/dev/null | grep -i "^preferredLanguage:" | awk '{print $2}' | tr -d '\r\n')
    fi
  fi

  LANG_LOWER=$(echo "$LANG_CODE" | tr '[:upper:]' '[:lower:]')
  CHOSEN_LANG="en"
  if [[ "$LANG_LOWER" == *"zh-tw"* ]] || [[ "$LANG_LOWER" == *"tw"* ]] || [[ "$LANG_LOWER" == *"hant"* ]]; then
    CHOSEN_LANG="zh-TW"
  elif [[ "$LANG_LOWER" == *"zh-cn"* ]] || [[ "$LANG_LOWER" == *"cn"* ]] || [[ "$LANG_LOWER" == *"hans"* ]]; then
    CHOSEN_LANG="zh-CN"
  elif [[ "$LANG_LOWER" == *"vi"* ]] || [[ "$LANG_LOWER" == *"vn"* ]]; then
    CHOSEN_LANG="vi"
  elif [[ "$LANG_LOWER" == *"fr"* ]] || [[ "$LANG_LOWER" == *"fra"* ]]; then
    CHOSEN_LANG="fr"
  elif [[ "$LANG_LOWER" == *"de"* ]] || [[ "$LANG_LOWER" == *"deu"* ]] || [[ "$LANG_LOWER" == *"ger"* ]]; then
    CHOSEN_LANG="de"
  elif [[ "$LANG_LOWER" == *"ja"* ]] || [[ "$LANG_LOWER" == *"jp"* ]] || [[ "$LANG_LOWER" == *"jpn"* ]]; then
    CHOSEN_LANG="ja"
  elif [[ "$LANG_LOWER" == *"es"* ]] || [[ "$LANG_LOWER" == *"spa"* ]]; then
    CHOSEN_LANG="es"
  else
    CHOSEN_LANG="en"
  fi

  # 尋找對應語系範本檔案
  TEMPLATE="/etc/dovecot/welcome_templates/welcome.${CHOSEN_LANG}.eml"
  if [ ! -f "$TEMPLATE" ]; then
    TEMPLATE="/usr/lib/dovecot/sieve-pipe/templates/welcome.${CHOSEN_LANG}.eml"
  fi
  if [ ! -f "$TEMPLATE" ]; then
    # 保底英文範本
    TEMPLATE="/etc/dovecot/welcome_templates/welcome.en.eml"
    [ ! -f "$TEMPLATE" ] && TEMPLATE="/usr/lib/dovecot/sieve-pipe/templates/welcome.en.eml"
  fi

  if [ ! -f "$TEMPLATE" ]; then
    exit 0
  fi

  # 6. 動態提取配額上限 ${QUOTA_LIMIT}
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

  # 7. 主機名稱與日期
  HOST_NAME="${HOST_NAME:-mail.${DOMAIN_NAME}}"
  if [ -f "/etc/postfix/main.cf" ]; then
    MY_HOST=$(grep -E '^\s*myhostname\s*=' /etc/postfix/main.cf 2>/dev/null | awk -F'=' '{print $2}' | tr -d ' ')
    [ -n "$MY_HOST" ] && [ "$MY_HOST" != "HOST_NAME" ] && HOST_NAME="$MY_HOST"
  fi
  DATE=$(date -R 2>/dev/null || date)

  # 8. 變數置換
  CONTENT=$(sed -e "s/\${EMAIL}/${USER_EMAIL}/g" \
                -e "s/\${ACCOUNT}/${ACCOUNT}/g" \
                -e "s/\${DOMAIN_NAME}/${DOMAIN_NAME}/g" \
                -e "s/\${HOST_NAME}/${HOST_NAME}/g" \
                -e "s/\${DATE}/${DATE}/g" \
                -e "s/\${QUOTA_LIMIT}/${QUOTA_LIMIT}/g" "$TEMPLATE")

  # 9. 透過 Dovecot 原生工具存入 INBOX
  SAVE_STATUS=0
  if command -v doveadm >/dev/null 2>&1; then
    printf "%s" "$CONTENT" | doveadm save -u "$USER_ID" -m INBOX
    SAVE_STATUS=$?
  fi

  # 10. 寫入成功後建立標記
  if [ $SAVE_STATUS -eq 0 ]; then
    mkdir -p "$USER_DIR" 2>/dev/null || true
    date +%s > "${USER_DIR}/.welcomed" 2>/dev/null || true
  fi
) &

# 繼續執行 Dovecot 的後續處理 (imap / pop3)
exec "$@"
