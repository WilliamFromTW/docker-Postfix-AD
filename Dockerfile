FROM centos:centos7.9.2009
RUN yum -y install epel-release
RUN yum -y update 
RUN yum -y upgrade
RUN curl https://rspamd.com/rpm-stable/centos-7/rspamd.repo > /etc/yum.repos.d/rspamd.repo # For Centos-7
RUN rpm --import https://rspamd.com/rpm-stable/gpg.key
RUN yum -y update
RUN yum -y install unbound redis rspamd libffi-devel dovecot-pigeonhole ntp opendkim bind-utils net-tools postfix cyrus-sasl cyrus-sasl-plain cyrus-sasl-md5 opendkim clamav clamav-devel clamav-scanner-systemd clamav-update clamav-data clamav-server clamav-server-systemd clamav-scanner dovecot supervisor httpd mod-ssl telnet rsyslog vi vim wget rsync 
EXPOSE 25 143 465 587 993 995 4190
VOLUME ["/etc/postfix","/etc/dovecot/","/etc/letsencrypt","/home/vmail","/var/log","/etc/rspamd"]
COPY rsyslog.conf /etc/rsyslog.conf
COPY listen.conf /etc/rsyslog.d/listen.conf
COPY postfix_config/ /etc/postfix/
COPY sysconfig/ /etc/sysconfig/
COPY dovecot/ /etc/dovecot/
COPY opendkim/ /etc/opendkim/
COPY rspamd/  /etc/rspamd/
COPY clamd/clamd.d/   /etc/clamd.d/
COPY setup.sh /setup.sh
COPY start_dovecot.sh /start_dovecot.sh
RUN usermod -aG clamscan _rspamd
RUN usermod -aG virusgroup _rspamd
RUN chmod +x /start_dovecot.sh;chmod +x /setup.sh;
RUN groupadd vmail -g 1001;useradd vmail -u 1001 -g 1001
RUN /usr/bin/newaliases
RUN mkdir -p /etc/dovecot/sieve/global
COPY supervisord.conf /etc
CMD /setup.sh
