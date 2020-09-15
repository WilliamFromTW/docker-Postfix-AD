docker-Postfix-AD
===================


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

Active Directory Notice
----
* Login Name can different with email name    
* Login Name must be created lower case (because dovecot always use lower case)    

Prerequisite
----    
* Make Mail Server  let\'sencrypt ready .     
e.g. mail.test.com , must the same with \<MAIL_HOST_NAME\>                
Mapping host's /etc/letsencrypt to this docker images       

Enable DKIM Feature
----    
* add the following settings to /etc/postfix/main.cf    

    smtpd_milters = inet:127.0.0.1:8891    
    non_smtpd_milters = $smtpd_milters    
    milter_default_action = accept    

* add the description of /etc/opendkim/keys/default.txt to DNS TXT record    

Active Directory 
----
* ALIASES    
    Create Group and give an aliases email in attribute "mail" ,  and include account in group    

* Account    
    Create User and give email in attribute "mail" , account must be lower case    

* local_only    
    write "local_only" in attribute "description" of user account to restrict use in local domain only    

Usage
-----

**Create Volume**

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    

**Prepare parameter**

    <AD_HOST_IP> : active directory ip
    <SEARCH_BASE> : active directory ldap search base
    <BIND_DN> : active directory ldap bind dn
    <BIND_PW> : active directory ldap bind password
    <ALIASES> : active directory ldap aliase
    <EMAIL_DOMAIN_NAME> :  email domain name
    <MAIL_HOST_NAME> :  mail host name
    <PERMIT_NETWORKS> :  permit network (intranet)

**TimeZone**

    <TZ>: time zone ( reference /usr/share/zoneinfo/ )        

**docker command**

    docker run --name postfixldap -v /etc/letsencrypt:/etc/letsencrypt  \
    -v postfixldap_vmail:/home/vmail -v postfixldap_postfix:/etc/postfix  \
    -p 25:25 -p 143:143 -p 465:465 -p 587:587  -p 993:993 -p 995:995  \
    -e DOMAIN_NAME=<EMAIL_DOMAIN_NAME>  \
    -e HOST_NAME=<MAIL_HOST_NAME>  \
    -e HOST_IP=<AD_HOST_IP>  \
    -e SEARCH_BASE=<SEARCH_BASE>  \
    -e BIND_DN=<BIND_DN>  \
    -e BIND_PW=<BIND_PW>  \
    -e ALIASES=<ALIASES>  \
    -e MY_NETWORKS="<PERMIT_NETWORKS>"  \
    -e TZ="<TZ>" \
    --restart always -d inmethod/centos-7_postfix_amavisd_active-directory

Example
-----
**Microsfot AD**    

    <AD_HOST_IP> : 192.1.0.227
    <SEARCH_BASE> : cn=Users,dc=test,dc=com
    <BIND_DN> : cn=ldap,cn=Users,dc=test,dc=com
    <BIND_PW> : password
    <ALIASES> : OU=aliases,DC=test,DC=com
  
**Mail server(docker)**    

    <EMAIL_DOMAIN_NAME> : test.com
    <MAIL_HOST_NAME> : mail.test.com
    
**permit networks**    

    <PERMIT_NETWORKS> : 192.1.0.0\/24    

**TimeZone**

    <TZ>:Asia/Taipei

**docker launch command**

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    
    
    docker run --name postfixldap \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v postfixldap_vmail:/home/vmail \
    -v postfixldap_postfix:/etc/postfix \
    -p 25:25 -p 143:143 -p 465:465 -p 587:587 -p 993:993 -p 995:995 \
    -e DOMAIN_NAME=test.com \
    -e HOST_NAME=mail.test.com \
    -e HOST_IP=192.1.0.227 \
    -e SEARCH_BASE=cn=Users,dc=test,dc=com \
    -e BIND_DN=cn=ldap,cn=Users,dc=test,dc=com \
    -e BIND_PW=password \
    -e ALIASES=OU=aliases,DC=hlmt,DC=com \
    -e MY_NETWORKS="192.1.0.0\/24" \
    -e TZ="Asia/Taipei" \
    --restart always -d inmethod/centos-7_postfix_amavisd_active-directory


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
    3. any service above is not working
    more /etc/supervisord.conf and find the launch command of the stoped service
    execute command to see error messages .
    