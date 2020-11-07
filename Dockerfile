FROM centos:7
RUN yum -y install epel-release
RUN yum -y update 
RUN yum -y upgrade
RUN yum -y install fail2ban dovecot-pigeonhole ntp opendkim bind-utils net-tools postfix cyrus-sasl cyrus-sasl-plain cyrus-sasl-md5 opendkim clamav clamav-devel clamav-scanner-systemd clamav-update clamav-data clamav-server clamav-server-systemd clamav-scanner amavisd-new dovecot supervisor httpd mod-ssl telnet rsyslog vi vim wget rsync 
EXPOSE 25 110 143 465 587 993 995 4190
VOLUME ["/etc/postfix","/etc/letsencrypt","/home/vmail"]
COPY rsyslog.conf /etc/rsyslog.conf
COPY listen.conf /etc/rsyslog.d/listen.conf
COPY postfix_config/ /etc/postfix/
COPY amavisd/ /etc/amavisd/
COPY sysconfig/ /etc/sysconfig/
COPY dovecot/ /etc/dovecot/
COPY opendkim/ /etc/opendkim/
COPY setup.sh /setup.sh
COPY start_dovecot.sh /start_dovecot.sh
RUN chmod +x /start_dovecot.sh;chmod +x /setup.sh;
RUN groupadd vmail -g 1001;useradd vmail -u 1001 -g 1001
RUN /usr/bin/newaliases
RUN mkdir -p /etc/dovecot/sieve/global
COPY supervisord.conf /etc
CMD /setup.sh
