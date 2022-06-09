Docker-Postfix-AD
=========================
Github
----------
https://github.com/WilliamFromTW/docker-Postfix-AD/tree/rspamd    

Feature
----------
* Authentication account can diferent with email. e.g. account: 520001 , email: william@smile.taipei    
* postfix mail server    
* User Account backend with Microsoft Active Directory(2008R2,2012R2,2016)    
* OpenDKIM    
* Rspamd(spam filter)    
* Clamav(antivirus)    
* Quota (default 20G)

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


Prerequisites
----    
* Make let\'sencrypt ready in your docker host(not container).     
Mapping host's /etc/letsencrypt to container        

Steps
-----------
**Create Volume**

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    
    docker volume create postfixldap_dovecot    
    docker volume create postfixldap_log    
    docker volume create postfixldap_rspamd    

**parameters**

    <AD_HOST_IP> : active directory ip
    <SEARCH_BASE> : active directory ldap search base
    <BIND_DN> : active directory ldap bind dn
    <BIND_PW> : active directory ldap bind password
    <EMAIL_DOMAIN_NAME> :  mail domain name
    <MAIL_HOST_NAME> :  mail server host name
    <PERMIT_NETWORKS> :  permit network (optional)
    <ALIASES> : active directory ldap aliase (optional)
    <TZ>: time zone default is Asia/Taipei (optional)        

**docker command**

    docker run --name postfixldap -v /etc/letsencrypt:/etc/letsencrypt  \
    -v postfixldap_vmail:/home/vmail 
	-v postfixldap_postfix:/etc/postfix  
	-v postfixldap_dovecot:/etc/dovecot 
	-v postfixldap_rspamd:/etc/rspamd \
    -v postfixldap_log:/var/log \
    -p 25:25 -p 110:110 -p 143:143 -p 465:465 -p 587:587  -p 993:993 -p 995:995 -p 4190:4190 -p 11334:11334 \
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
    --restart always -d inmethod/docker-postfix-ad:tag

Example
-----
**Microsfot AD**    

    <AD_HOST_IP> : 192.1.0.227
    <SEARCH_BASE> : "cn=Users,dc=test,dc=com" or "dc=test,dc=com"
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
    docker volume create postfixldap_rspamd    
    
    docker run --name postfixldap \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v postfixldap_vmail:/home/vmail \
    -v postfixldap_postfix:/etc/postfix \
    -v postfixldap_dovecot:/etc/dovecot \
	-v postfixldap_rspamd:/etc/rspamd \
    -v postfixldap_log:/var/log \
    -p 25:25 -p 110:110 -p 143:143 -p 465:465 -p 587:587  -p 993:993 -p 995:995 -p 4190:4190 -p 11334:11334 \
    -e DOMAIN_NAME="test.com" \
    -e HOST_NAME="mail.test.com" \
    -e HOST_IP="192.1.0.227" \
    -e SEARCH_BASE="cn=Users,dc=test,dc=com" \
    -e BIND_DN="cn=ldap,cn=Users,dc=test,dc=com" \
    -e BIND_PW="password" \
    -e TZ="Asia/Taipei" \
    --restart always -d --net=host inmethod/docker-postfix-ad:1.9
    

Rspamd spam filter WEB UI     
--    
*  ACCESS WEB UI    
    
   use httpd reverse proxy to access localhost:11334    

*  change login password      
    
	default password : kafeiou.pw    
	command(container) to generate new crypt password     
	>  rspamadm pw --encrypt -p \<new password\>      
	
	change new crypt password in /etc/rspamd/local.d/worker-controller.inc      

*  whitelist and blacklist    

    login web to edit file list in tab Configuration, or manual edit /etc/rspamd/override.d in container    
	

Enable DKIM 
----    
* uncomment parameter in /etc/postfix/main.cf    
    
    smtpd_milters = inet:127.0.0.1:8891    
    non_smtpd_milters = $smtpd_milters    
    milter_default_action = accept    

* add /etc/opendkim/keys/default.txt content to DNS TXT record    

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


Trouble Shotting
----
**Checking service**

     1. login container 
    docker exec -it <container name> bash
     2. testing service
    telnet localhost 143 (dovecot)
    telnet localhost 25(postfix)
    telnet localhost 8891(dkim service)
    telnet localhost 12340 (quota)
    telnet localhost 2424 (lmtp)
    telnet localhost 11334 (rspamd)
    3. any service above is not working
    more /etc/supervisord.conf and find the launch command of the stoped service
    execute command to see error messages .
    
**Performance Tunning**

    1. /etc/dovecot/conf.d/10-auth.conf
      auth_cache_size = 256M    
      auth_cache_verify_password_with_worker = yes
      auth_cache_ttl = xxx
      auth_cache_negative_ttl = xxx
    2. /etc/dovecot/conf.d/10-master.conf
      default_vsz_limit = 256M
      service_count = 0
    3. /etc/dovecot/dovecot.conf , 15-lda.conf , 20-lmtp.conf
       mail_fsync = never
       protocol lda {
         mail_fsync = optimized
       }
       protocol lmtp {
         mail_fsync = optimized
       }
      
**fail2ban**    

    * add --net=host in docker launch command to get real remote ip from log(strong recommended)      
             
**quota**    

     * modify /etc/dovecot/conf.d/90-quota.cf to change quota limit    

**rip=::1, lip=::1, secured, session problem**    

     * this problem occurred offen , i don't known why , suggest imap and pop3 by listening ipv4 only , add "address" for ip(ipv4) interface in /etc/dovecot/conf.d/ 10-master.conf    


**multiple domain**    

check the following files    
postfix    
1.main.cf(ldap file)    
2.helo_check  
3.domain    

dovecot     
auth-ldap.conf.ext (add mutiple userdb, passdb )    

