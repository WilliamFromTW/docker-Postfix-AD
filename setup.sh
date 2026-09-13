#!/bin/bash 

if [ -n "${DOMAIN_NAME}" ]; then
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/main.cf
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/local-host-names
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/helo_check 
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/domains
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/local_only_domains
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/local_only2_domains
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/opendkim/opendkim.conf
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/opendkim/TrustedHosts
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/opendkim/SigningTable
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/opendkim/KeyTable
fi

if [ -n "${HOST_NAME}" ]; then
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/postfix/main.cf
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/postfix/local-host-names
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/dovecot/conf.d/10-ssl.conf
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/opendkim/TrustedHosts
 if [ ! -f "/etc/letsencrypt/live/${HOST_NAME}/fullchain.pem" ];  then
  /make_fake_cert.sh ${HOST_NAME}
 fi
fi

if [ -n "${SEARCH_BASE}" ]; then
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-users.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/saslauthd.conf 
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/dovecot/dovecot-ldap.conf.ext 
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/dovecot/dovecot-ldap2.conf.ext 
fi
# -------------------------------------------------------------
# LDAP / LDAPS (Port 389 / 636 TLS) 連線模式配置
# -------------------------------------------------------------
ENABLE_LDAPS=${ENABLE_LDAPS:-false}

if [ "${ENABLE_LDAPS,,}" = "true" ] || [ "${ENABLE_LDAPS}" = "1" ]; then
  echo "Enabling LDAPS (Port 636 / TLS)..."
  # 1. Postfix LDAP 改為 LDAPS 636 + tls_require_cert = no
  sed -i "s/server_host = HOST_IP/server_host = ldaps:\/\/HOST_IP:636\ntls_require_cert = no/g" /etc/postfix/ldap-users.cf
  sed -i "s/server_host = HOST_IP/server_host = ldaps:\/\/HOST_IP:636\ntls_require_cert = no/g" /etc/postfix/ldap-aliases.cf
  sed -i "s/server_host = HOST_IP/server_host = ldaps:\/\/HOST_IP:636\ntls_require_cert = no/g" /etc/postfix/ldap-local_only.cf
  sed -i "s/server_host = HOST_IP/server_host = ldaps:\/\/HOST_IP:636\ntls_require_cert = no/g" /etc/postfix/ldap-local_only2.cf
  
  # 2. Dovecot LDAP 改為 uris = ldaps://HOST_IP:636 + tls_require_cert = never
  sed -i "s/hosts = HOST_IP:389/uris = ldaps:\/\/HOST_IP:636\ntls_require_cert = never/g" /etc/dovecot/dovecot-ldap.conf.ext
  sed -i "s/hosts = HOST_IP:389/uris = ldaps:\/\/HOST_IP:636\ntls_require_cert = never/g" /etc/dovecot/dovecot-ldap2.conf.ext
  
  # 3. SASL 改為 ldaps://HOST_IP:636/ + ldap_ssl: yes + ldap_tls_check_peer: no
  sed -i "s/ldap_servers: ldap:\/\/HOST_IP:389\//ldap_servers: ldaps:\/\/HOST_IP:636\/\nldap_ssl: yes\nldap_tls_check_peer: no/g" /etc/postfix/saslauthd.conf
fi

if [ -n "${HOST_IP}" ]; then
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-users.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/saslauthd.conf 
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/dovecot/dovecot-ldap.conf.ext 
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/dovecot/dovecot-ldap2.conf.ext 
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/crontab
 
fi

if [ -n "${BIND_DN}" ]; then
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-users.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/saslauthd.conf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/dovecot/dovecot-ldap.conf.ext 
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/dovecot/dovecot-ldap2.conf.ext 
fi

if [ -n "${BIND_PW}" ]; then
 SAFE_BIND_PW=$(printf '%s\n' "${BIND_PW}" | sed -e 's/[\/&]/\\&/g')
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/postfix/ldap-users.cf
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/postfix/saslauthd.conf
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/dovecot/dovecot-ldap.conf.ext 
 sed -i "s/BIND_PW/${SAFE_BIND_PW}/g" /etc/dovecot/dovecot-ldap2.conf.ext 
fi

if [ -n "${ALIASES}" ]; then
 sed -i "s/ALIASES/${ALIASES}/g" /etc/postfix/ldap-aliases.cf
else
 sed -i "s/\,ldap\:\/etc\/postfix\/ldap-aliases\.cf/ /g" /etc/postfix/main.cf
fi

if [ -n "${MY_NETWORKS}" ]; then
 SAFE_MY_NETWORKS=$(printf '%s\n' "${MY_NETWORKS}" | sed -e 's/[\/&]/\\&/g')
 sed -i "s/MY_NETWORKS/${SAFE_MY_NETWORKS}/g" /etc/postfix/main.cf
else
 sed -i "s/\,MY_NETWORKS/ /g" /etc/postfix/main.cf
fi

if [ -z "${SPAM_EMAIL}" ]; then
  echo "ERROR: SPAM_EMAIL environment variable is required! Exiting..." >&2
  exit 1
fi

sed -i "s/SPAM_EMAIL/${SPAM_EMAIL}/g" /etc/postfix/milter_header_checks
sed -i "s/SPAM_EMAIL/${SPAM_EMAIL}/g" /etc/rspamd/kafeiou.d/quarantine_redirect.lua
sed -i "s/SPAM_EMAIL/${SPAM_EMAIL}/g" /etc/postfix/aliases


# -------------------------------------------------------------
# Quota 儲存配額防護一律啟用 (預設 50GB 與 Volume 平滑升級)
# -------------------------------------------------------------
sed -i "s/QUOTA_MAIN/check_policy_service inet\:localhost\:12340/g" /etc/postfix/main.cf
sed -i "s/QUOTA_MAIL/quota/g" /etc/dovecot/conf.d/10-mail.conf
sed -i "s/QUOTA_IMAP/imap_quota/g" /etc/dovecot/conf.d/20-imap.conf

# Volume 掛載舊版 20G 自動平滑升級至 50G（保留管理者自訂非 20G 數值）
if [ -f "/etc/dovecot/conf.d/90-quota.conf" ]; then
  if grep -q "quota_rule = \*:storage=20G" /etc/dovecot/conf.d/90-quota.conf; then
    sed -i "s/quota_rule = \*:storage=20G/quota_rule = \*:storage=50G/g" /etc/dovecot/conf.d/90-quota.conf
  fi
  # 確保 Volume 內的 90-quota.conf 具備 quota-warning 設定
  if ! grep -q "service quota-warning" /etc/dovecot/conf.d/90-quota.conf; then
    cat << 'EOF' >> /etc/dovecot/conf.d/90-quota.conf

plugin {
  quota_warning = storage=95%% quota-warning 95 %u
}

service quota-warning {
  executable = script /usr/lib/dovecot/sieve-pipe/quota_warning.sh
  user = vmail
  unix_listener quota-warning {
    user = vmail
    mode = 0660
  }
}
EOF
  fi
fi

if [ -n "${TZ}" ] ; then
 TZ="${TZ}"; export TZ ;
else
 TZ="Asia/Taipei"; export TZ ;
fi 

if [ ! -f "/etc/opendkim/keys/default.private" ];  then
  /usr/sbin/opendkim-genkey -d "${DOMAIN_NAME}" ;
  /usr/bin/cp default.* /etc/opendkim/keys
  /usr/bin/mkdir -p  /var/lib/rspamd/dkim
  /usr/bin/cp default.private /var/lib/rspamd/dkim/${DOMAIN_NAME}.dkim.key
fi

if [ ! -f "/etc/dovecot/dh.pem" ]; then
  echo "Generating 2048-bit Diffie-Hellman parameters for TLS (takes ~10s)..."
  /usr/bin/openssl dhparam 2048 > /etc/dovecot/dh.pem
fi

/usr/bin/chown -R vmail:vmail /home/vmail&
chown -R opendkim:opendkim /etc/opendkim
postmap /etc/postfix/local_only_domains
postmap /etc/postfix/local_only2_domains
postmap /etc/postfix/helo_check
postmap /etc/postfix/sender_bcc
postmap /etc/postfix/recipient_bcc

chown -R _rspamd:_rspamd /etc/rspamd/local.d
chown -R _rspamd:_rspamd /etc/rspamd/kafeiou.d
chown -R _rspamd:_rspamd /var/lib/rspamd
/usr/sbin/postmap /etc/postfix/aliases
/usr/sbin/postalias lmdb:/etc/aliases
# -------------------------------------------------------------
# 智慧自動回覆 (Email-Driven Auto-Reply / Sieve) 啟動防呆初始化
# -------------------------------------------------------------
mkdir -p /var/spool/postfix/private
chown postfix:postfix /var/spool/postfix/private
chmod 700 /var/spool/postfix/private

mkdir -p /usr/lib/dovecot/sieve-pipe
chown -R vmail:vmail /usr/lib/dovecot/sieve-pipe
chmod -R 755 /usr/lib/dovecot/sieve-pipe

# -------------------------------------------------------------
# 首次登入歡迎信 (First-Login Welcome Email) 初始化
# -------------------------------------------------------------
mkdir -p /etc/dovecot/welcome_templates
chown -R vmail:vmail /etc/dovecot/welcome_templates
chmod -R 755 /etc/dovecot/welcome_templates

if [ -f "/usr/lib/dovecot/sieve-pipe/postlogin.sh" ]; then
  cp -f /usr/lib/dovecot/sieve-pipe/postlogin.sh /usr/lib/dovecot/postlogin.sh
  chmod 755 /usr/lib/dovecot/postlogin.sh
  chown vmail:vmail /usr/lib/dovecot/postlogin.sh
fi

if [ -f "/etc/dovecot/conf.d/10-master.conf" ]; then
  if ! grep -q "imap-postlogin" /etc/dovecot/conf.d/10-master.conf; then
    cat << 'EOF' >> /etc/dovecot/conf.d/10-master.conf

service imap {
  executable = imap imap-postlogin
}

service imap-postlogin {
  executable = script-login /usr/lib/dovecot/postlogin.sh
  user = vmail
  unix_listener imap-postlogin {
    user = vmail
    mode = 0660
  }
}

service pop3 {
  executable = pop3 pop3-postlogin
}

service pop3-postlogin {
  executable = script-login /usr/lib/dovecot/postlogin.sh
  user = vmail
  unix_listener pop3-postlogin {
    user = vmail
    mode = 0660
  }
}
EOF
  fi
fi


if [ -d "/etc/dovecot/sieve/global" ]; then
  for sf in /etc/dovecot/sieve/global/*.sieve; do
    [ -f "$sf" ] && (/usr/bin/sievec "$sf" 2>/dev/null || /usr/sbin/sievec "$sf" 2>/dev/null || true)
  done
  chown -R vmail:vmail /etc/dovecot/sieve
fi

# 導出 Ollama 與時區設定供 Sieve 外部腳本讀取（Dovecot sieve_extprograms 預設隔離環境變數）
cat << EOF > /etc/dovecot/ollama.env
OLLAMA_HOST="${OLLAMA_HOST}"
OLLAMA_MODEL="${OLLAMA_MODEL}"
OLLAMA_TIMEOUT="${OLLAMA_TIMEOUT:-20}"
DEFAULT_LANG="${DEFAULT_LANG}"
TZ="${TZ}"
EOF
chmod 644 /etc/dovecot/ollama.env

# 導出環境變數供 Dovecot postlogin 與 quota 腳本讀取（Dovecot script-login 預設隔離環境變數）
cat << EOF > /etc/dovecot/postlogin.env
DOMAIN_NAME="${DOMAIN_NAME}"
HOST_NAME="${HOST_NAME}"
HOST_IP="${HOST_IP}"
SEARCH_BASE="${SEARCH_BASE}"
BIND_DN="${BIND_DN}"
BIND_PW="${BIND_PW}"
ENABLE_LDAPS="${ENABLE_LDAPS}"
EOF
chown vmail:vmail /etc/dovecot/postlogin.env
chmod 640 /etc/dovecot/postlogin.env

# -------------------------------------------------------------
# 企業級雙層郵件收回 (Two-Tier Message Recall) 初始化
# -------------------------------------------------------------
RECALL_ENV="/etc/dovecot/recall.env"
if [ ! -f "$RECALL_ENV" ]; then
  cat << EOF > "$RECALL_ENV"
ENABLE_RECALL="yes"
RECALL_DELAY_SECONDS=10
RECALL_MAX_HOURS=2
EOF
  chmod 644 "$RECALL_ENV"
fi

if [ -f "$RECALL_ENV" ]; then
  # shellcheck source=/dev/null
  . "$RECALL_ENV"
fi

mkdir -p /etc/postfix
if [ "${ENABLE_RECALL}" = "yes" ] && [ "${RECALL_DELAY_SECONDS:-10}" -gt 0 ] 2>/dev/null; then
  echo "/^/ HOLD Delay buffer for message recall (${RECALL_DELAY_SECONDS}s)" > /etc/postfix/submission_hold
else
  echo "/^/ DUNNO" > /etc/postfix/submission_hold
fi
chmod 644 /etc/postfix/submission_hold

mkdir -p /var/spool/postfix/hold
chown postfix:postfix /var/spool/postfix/hold
chmod 700 /var/spool/postfix/hold

# -------------------------------------------------------------
# OpenLDAP 用戶端全域 TLS 憑證相容性配置 (支援 AD / NethServer 8 自簽憑證)
# -------------------------------------------------------------
mkdir -p /etc/openldap
if [ -f "/etc/openldap/ldap.conf" ]; then
  grep -q "TLS_REQCERT" /etc/openldap/ldap.conf || echo "TLS_REQCERT never" >> /etc/openldap/ldap.conf
else
  echo "TLS_REQCERT never" > /etc/openldap/ldap.conf
fi

if [ -n "$TZ" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
  ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
  echo "$TZ" > /etc/timezone
elif [ -n "$TZ" ]; then
  echo "$TZ" > /etc/timezone
fi
chown clamupdate:clamupdate /var/lib/clamav
chmod 755 /var/lib/clamav
sudo mkdir -p /run/clamd.scan
sudo chown clamscan:clamscan /run/clamd.scan
freshclam
/usr/bin/supervisord -c /etc/supervisord.conf
