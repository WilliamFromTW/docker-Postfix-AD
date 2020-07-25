docker-Postfix-AD
===================

Mail server on CentOS 7 with Microsoft AD backend

Support
----------
* SMTP    
port 25    
port 587(TLS)

* POP3    
port 110    
port 995(SSL)    

* imap    
port 143    
port 143(TLS),993(TLS)    

* amavisd+clamav    

* Microsoft AD(only one domain)

Notice
----
* Login Name can different with email name    
Login name must be created lower case (because dovecot always use lower case login name)    

* Mapping /etc/letsencrypt     
just mapping host's /etc/letsencrypt to this docker images     

Usage
-----

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    

    docker run --name postfixldap -v /etc/letsencrypt:/etc/letsencrypt 
    -v postfixldap_vmail:/home/vmail -v postfixldap_postfix:/etc/postfix 
    -p 25:25 -p 587:587 -p 143:143 -p 993:993 -p 995:995 
    -e DOMAIN_NAME=<DOMAIN_NAME> 
    -e HOST_NAME=<HOST_NAME> 
    -e HOST_IP=<HOST_IP> 
    -e SEARCH_BASE=<SEARCH_BASE> 
    -e BIND_DN=<BIND_DN> 
    -e BIND_PW=<BIND_PW> 
    -e ALIASES=<ALIASES> 
    -e MY_NETWORKS="<PERMIT_NETWORKS>" 
    --restart always -d inmethod/postfixad

Example
-----
Microsfot AD    

    <HOST_IP> : 192.1.0.227
    <DOMAIN_NAME> : test.com
    <SEARCH_BASE> : cn=Users,dc=test,dc=com
    <BIND_DN> : cn=ldap,cn=Users,dc=test,dc=com
    <BIND_PW> : password
    <ALIASES> : OU=aliases,DC=test,DC=com
  
Mail server(docker)

    <HOST_NAME> : mail.test.com
    
permit networks

    <PERMIT_NETWORKS> : 192.1.0.0/24    

docker launch command

    docker volume create postfixldap_vmail    
    docker volume create postfixldap_postfix    
    
    docker run --name postfixldap \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v postfixldap_vmail:/home/vmail \
    -v postfixldap_postfix:/etc/postfix \
    -p 25:25 -p 587:587 -p 143:143 -p 993:993 -p 995:995 \
    -e DOMAIN_NAME=test.com \
    -e HOST_NAME=mail.test.com \
    -e HOST_IP=192.1.0.227 \
    -e SEARCH_BASE=cn=Users,dc=test,dc=com \
    -e BIND_DN=cn=ldap,cn=Users,dc=test,dc=com \
    -e BIND_PW=password \
    -e ALIASES=OU=aliases,DC=hlmt,DC=com \
    -e MY_NETWORKS="192.1.0.0\/24" \
    --restart always -d inmethod/postfixad 


