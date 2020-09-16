#!/bin/bash 

if [ -n "${DOMAIN_NAME}" ]; then
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/main.cf
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/local-host-names
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/postfix/helo_check 
 sed -i "s/DOMAIN_NAME/${DOMAIN_NAME}/g" /etc/amavisd/amavisd.conf
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
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/amavisd/amavisd.conf
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/dovecot/conf.d/10-ssl.conf
 sed -i "s/HOST_NAME/${HOST_NAME}/g" /etc/opendkim/TrustedHosts

fi

if [ -n "${SEARCH_BASE}" ]; then
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-users.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/postfix/saslauthd.conf 
 sed -i "s/SEARCH_BASE/${SEARCH_BASE}/g" /etc/dovecot/dovecot-ldap.conf.ext 
fi

if [ -n "${HOST_IP}" ]; then
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-users.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/postfix/saslauthd.conf 
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/dovecot/dovecot-ldap.conf.ext 
 sed -i "s/HOST_IP/${HOST_IP}/g" /etc/crontab
 
fi

if [ -n "${BIND_DN}" ]; then
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-users.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/postfix/saslauthd.conf
 sed -i "s/BIND_DN/${BIND_DN}/g" /etc/dovecot/dovecot-ldap.conf.ext 
fi

if [ -n "${BIND_PW}" ]; then
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/postfix/ldap-users.cf
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/postfix/ldap-aliases.cf
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/postfix/ldap-local_only.cf
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/postfix/ldap-local_only2.cf
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/postfix/saslauthd.conf
 sed -i "s/BIND_PW/${BIND_PW}/g" /etc/dovecot/dovecot-ldap.conf.ext 
fi

if [ -n "${ALIASES}" ]; then
 sed -i "s/ALIASES/${ALIASES}/g" /etc/postfix/ldap-aliases.cf
fi

if [ -n "${MY_NETWORKS}" ]; then
 sed -i "s/MY_NETWORKS/${MY_NETWORKS}/g" /etc/amavisd/amavisd.conf
 sed -i "s/MY_NETWORKS/${MY_NETWORKS}/g" /etc/postfix/main.cf
fi

TZ="${TZ}"; export TZ

if [ ! -f "/etc/opendkim/keys/default.private" ];  then
  /usr/sbin/opendkim-genkey -d "${DOMAIN_NAME}" ;
  /usr/bin/cp default.* /etc/opendkim/keys
fi

/usr/bin/chown -R vmail:vmail /home/vmail
chown -R opendkim:opendkim /etc/opendkim
postmap /etc/postfix/local_only_domains
postmap /etc/postfix/local_only2_domains
postmap /etc/postfix/helo_check
echo "0 0 * * * root /usr/bin/freshclam" >> /etc/crontab
echo "0 1 * * * root /usr/sbin/ntpdate -s ${HOST_IP}" >> /etc/crontab
/usr/bin/crontab /etc/crontab
/usr/bin/supervisord -c /etc/supervisord.conf
