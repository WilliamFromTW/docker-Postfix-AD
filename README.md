Docker-Postfix-MailServer
=========================

Feature
----------
* Login account can diferent with account email. e.g. account: 520001 , email: william@test.com
* postfix mail server    
* User Account backend with Microsoft Active Directory(2008R2,2012R2,2016)    
* OpenDKIM    
* managesieve    
* user email quota (default 20G)

Support
----------
* SMTP    
port 25    
port 465(SSL)
port 587(TLS)

* POP3    
port 995(SSL)    

* imap    
port 143(TLS),993(TLS)    

* amavisd+clamav    

* Microsoft AD(only one domain)    


Prerequisites
----    
* Make let\'sencrypt ready in your docker host.     
e.g. mail.test.com(lets encrypt) , must the same with \<MAIL_HOST_NAME\>                
Mapping host's /etc/letsencrypt to this docker images       


Start Steps
-----------

**Create Volume**

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    
    docker volume create postfixldap_dovecot    
    docker volume create postfixldap_log    

**parameters**

    <AD_HOST_IP> : active directory ip
    <SEARCH_BASE> : active directory ldap search base
    <BIND_DN> : active directory ldap bind dn
    <BIND_PW> : active directory ldap bind password
    <ALIASES> : active directory ldap aliase (optional)
    <EMAIL_DOMAIN_NAME> :  mail domain name
    <MAIL_HOST_NAME> :  mail server host name
    <PERMIT_NETWORKS> :  permit network (optional)
    <TZ>: time zone ( optional , default is Asia/Taipei , reference /usr/share/zoneinfo/ )        

**docker command**

    docker run --name postfixldap -v /etc/letsencrypt:/etc/letsencrypt  \
    -v postfixldap_vmail:/home/vmail -v postfixldap_postfix:/etc/postfix  -v postfixldap_dovecot:/etc/dovecot \
    -v postfixldap_log:/var/log \
    -p 25:25 -p 110:110 -p 143:143 -p 465:465 -p 587:587  -p 993:993 -p 995:995 -p 4190:4190 \
    -e DOMAIN_NAME="<EMAIL_DOMAIN_NAME>"  \
    -e HOST_NAME="<MAIL_HOST_NAME>"  \
    -e HOST_IP="<AD_HOST_IP>"  \
    -e SEARCH_BASE="<SEARCH_BASE>"  \
    -e BIND_DN="<BIND_DN>"  \
    -e BIND_PW="<BIND_PW>"  \
    -e ALIASES="<ALIASES>"  \
    -e MY_NETWORKS="<PERMIT_NETWORKS>"  \
    -e TZ="<TZ>" \
    -e ENABLE_QUOTA="true" \
    --restart always -d inmethod/centos-7_postfix_amavisd_active-directory

Example
-----
**Microsfot AD**    

    <AD_HOST_IP> : 192.1.0.227
    <SEARCH_BASE> : "cn=Users,dc=test,dc=com" or "dc=test,dc=com" for whole zone
    <BIND_DN> : cn=ldap,cn=Users,dc=test,dc=com
    <BIND_PW> : password
  
**Mail server(docker)**    

    <EMAIL_DOMAIN_NAME> : test.com 
    <MAIL_HOST_NAME> : mail.test.com

**TimeZone**

    <TZ>:Asia/Taipei

**docker launch command**

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    
    docker volume create postfixldap_dovecot    
    docker volume create postfixldap_log    
    
    docker run --name postfixldap \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v postfixldap_vmail:/home/vmail \
    -v postfixldap_postfix:/etc/postfix \
    -v postfixldap_dovecot:/etc/dovecot \
    -v postfixldap_log:/var/log \
    -p 25:25 -p 143:143 -p 465:465 -p 587:587 -p 993:993 -p 995:995 \
    -e DOMAIN_NAME="test.com" \
    -e HOST_NAME="mail.test.com" \
    -e HOST_IP="192.1.0.227" \
    -e SEARCH_BASE="cn=Users,dc=test,dc=com" \
    -e BIND_DN="cn=ldap,cn=Users,dc=test,dc=com" \
    -e BIND_PW="password" \
    -e TZ="Asia/Taipei" \
    --restart always -d --net=host inmethod/centos-7_postfix_amavisd_active-directory
    
White and Black list
----
**First priority amavisd**    
  modify /etc/postfix/amavisd_whitelist    
  modify /etc/postfix/amavisd_whitelist_ip    
  modify /etc/postfix/amavisd_blacklist    

**Sencond priority postfix sender access**    
  modify /etc/postfix/sender_access and use postmap to build hash file    


Enable DKIM 
----    
* uncomment parameter in /etc/postfix/main.cf    
    
    smtpd_milters = inet:127.0.0.1:8891    
    non_smtpd_milters = $smtpd_milters    
    milter_default_action = accept    

* add the description of /etc/opendkim/keys/default.txt to DNS TXT record    

Enable lmtp sieve( filter and vacation)  
----    
* uncomment parameter in /etc/postfix/main.cf    
    
    dovecot_destination_recipient_limit = 1    
    virtual_transport = lmtp:inet:127.0.0.1:2424    
    
* Modify config.inc.php in roundcubemail    
    $config['plugins'] = array(    
      'archive',    
      'zipdownload',    
      'managesieve',    
    );
  
    * for roundcube and mail are the same host    
      $config['managesieve_host'] = 'localhost';    
    * for roundcube and mail are the different host    
      $config['managesieve_port'] = 4190;    
      $config['managesieve_host'] = 'tls://\<mail server name\>';    
    * general    
    $config['managesieve_default'] = '/etc/dovecot/sieve/global';    
    $config['managesieve_vacation'] = 1;    
    $config['managesieve_vacation_interval'] = 1;    
    
Enable Quota    
--    
**launch docker with -e ENABLE_QUOTA="true"**    
    
Active Directory Notice
----
* Login Name can different with email name    

* Login Name must be created lower case (because dovecot always use lower case)    

* ALIASES    
    Create Group and give an aliases email in attribute "mail" ,  and include account in group    

* Account    
    Create User and give email in attribute "mail" , account must be lower case    

* local_only    
    Write "local_only" attribute "description" in user or group to restrict the use in local domain only    

* restricted and granted     
    Write "restricted" attribute "description" in user or group that can only received from user that write "granted" in attribute "description"


Trouble Shotting
----
**Checking service**

     1. login container 
    docker exec -it <container name> bash
     2. testing service
    telnet localhost 10024 (amavisd)
    telnet localhost 143 (dovecot)
    telnet localhost 25(postfix)
    telnet localhost 8891(dkim service)
    telnet localhost 12340 (quota)
    telnet localhost 2424 (lmtp)
    3. any service above is not working
    more /etc/supervisord.conf and find the launch command of the stoped service
    execute command to see error messages .
    
**Performance Tunning**

    1. /etc/dovecot/conf.d/10-auth.conf
      auth_cache_size = 256M    
      auth_cache_verify_password_with_worker = yes
    2. /etc/dovecot/conf.d/10-master.conf
      default_vsz_limit = 256M
      service_count = 0
    3. /etc/amavisd/amavisd.conf
      $max_servers = 15;  
    4. /etc/dovecot/dovecot.conf , 15-lda.conf , 20-lmtp.conf
       mail_fsync = never
       protocol lda {
         mail_fsync = optimized
       }
       protocol lmtp {
         mail_fsync = optimized
       }
      
**fail2ban**    

    * add --net=host in docker launch command to get real remote ip from log(strong recommended)      
      
**amavisd**     

     * command "amavisd-release" can restore quarantine file back  
	 
     * modify /etc/amavisd/amavisd.conf     
	 change "$final_spam_destiny" from D_DISCARD to D_PASS if you don't want to block spam    
	 
      
**quota**    

     * modify /etc/dovecot/conf.d/90-quota.cf to change quota limit    

**rip=::1, lip=::1, secured, session problem**    

     * this problem occurred offen , i don't known why , suggest imap and pop3 by listening ipv4 only , add "address" for ip(ipv4) interface in /etc/dovecot/conf.d/ 10-master.conf    

