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

if [ -n "${SPAM_EMAIL}" ]; then
 sed -i "s/SPAM_EMAIL/${SPAM_EMAIL}/g" /etc/postfix/milter_header_checks
 sed -i "s/SPAM_EMAIL/${SPAM_EMAIL}/g" /etc/rspamd/local.d/quarantine_redirect.lua
else
 sed -i "s/SPAM_EMAIL/postmaster/g" /etc/postfix/milter_header_checks
 sed -i "s/SPAM_EMAIL/postmaster/g" /etc/rspamd/local.d/quarantine_redirect.lua
fi


if [[ "${ENABLE_QUOTA}" == "true" ]]; then
  sed -i "s/QUOTA_MAIN/check_policy_service inet\:localhost\:12340/g" /etc/postfix/main.cf
  sed -i "s/QUOTA_MAIL/quota/g" /etc/dovecot/conf.d/10-mail.conf
  sed -i "s/QUOTA_IMAP/imap_quota/g" /etc/dovecot/conf.d/20-imap.conf
else
  sed -i "s/QUOTA_MAIN/#check_policy_service inet\:localhost\:12340/g" /etc/postfix/main.cf
  sed -i "s/QUOTA_MAIL/ /g" /etc/dovecot/conf.d/10-mail.conf
  sed -i "s/QUOTA_IMAP/ /g" /etc/dovecot/conf.d/20-imap.conf  
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

if [ ! -f "/etc/dovecot/dh.pem" ];  then
  /usr/bin/openssl dhparam 4096 > /etc/dovecot/dh.pem
fi

/usr/bin/chown -R vmail:vmail /home/vmail&
chown -R opendkim:opendkim /etc/opendkim
postmap /etc/postfix/local_only_domains
postmap /etc/postfix/local_only2_domains
postmap /etc/postfix/helo_check
postmap /etc/postfix/sender_bcc
postmap /etc/postfix/recipient_bcc

chown -R _rspamd:_rspamd /etc/rspamd/local.d
chown -R _rspamd:_rspamd /etc/rspamd/override.d  
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

mkdir -p /etc/dovecot/sieve/global
if [ -f "/etc/dovecot/sieve/global/autoreply_handler.sieve" ]; then
  /usr/bin/sievec /etc/dovecot/sieve/global/autoreply_handler.sieve 2>/dev/null || /usr/sbin/sievec /etc/dovecot/sieve/global/autoreply_handler.sieve 2>/dev/null
  chown -R vmail:vmail /etc/dovecot/sieve
fi

# 導出 Ollama 與時區設定供 Sieve 外部腳本讀取（Dovecot sieve_extprograms 預設隔離環境變數）
cat << EOF > /etc/dovecot/ollama.env
OLLAMA_HOST="${OLLAMA_HOST}"
OLLAMA_MODEL="${OLLAMA_MODEL}"
OLLAMA_TIMEOUT="${OLLAMA_TIMEOUT:-180}"
DEFAULT_LANG="${DEFAULT_LANG}"
TZ="${TZ}"
EOF
chmod 644 /etc/dovecot/ollama.env

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
