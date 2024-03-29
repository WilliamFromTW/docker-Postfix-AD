FROM rockylinux:8.8
RUN dnf -y install epel-release
RUN dnf config-manager --set-enabled powertools
RUN dnf -y  update 
RUN dnf -y  upgrade
RUN curl https://rspamd.com/rpm-stable/centos-8/rspamd.repo > /etc/yum.repos.d/rspamd.repo # For Centos-8
RUN rpm --import https://rspamd.com/rpm-stable/gpg.key
RUN dnf update -y
RUN dnf -y install git man sudo chrony crontabs postfix-* htop procps-ng ca-certificates unbound redis rspamd libffi-devel dovecot-pigeonhole  opendkim-tools opendkim bind-utils net-tools postfix cyrus-sasl cyrus-sasl-plain cyrus-sasl-md5 clamav clamd clamav-update clamav-devel clamav-scanner-systemd clamav-data clamav-server clamav-server-systemd dovecot supervisor httpd mod_ssl telnet rsyslog vi vim wget rsync 
EXPOSE 25 143 465 587 993 995 4190
VOLUME ["/etc/postfix","/etc/dovecot/","/etc/letsencrypt","/home/vmail","/var/log","/etc/rspamd","/etc/opendkim","/var/lib/rspamd"]
RUN rm -rf /etc/logrotate.d/*
COPY rsyslog.conf /etc/rsyslog.conf
COPY listen.conf /etc/rsyslog.d/listen.conf
COPY postfix_config/ /etc/postfix/
COPY sysconfig/ /etc/sysconfig/
COPY dovecot/ /etc/dovecot/
COPY opendkim/ /etc/opendkim/
COPY rspamd/  /etc/rspamd/
COPY clamd/clamd.d/   /etc/clamd.d/
COPY redis/ /etc/redis/
COPY setup.sh /setup.sh
COPY start_dovecot.sh /start_dovecot.sh
COPY logrotate.d/ /etc/logrotate.d/
COPY getOpenDKIM.sh /getOpenDKIM.sh
RUN /usr/sbin/unbound-anchor -a /var/lib/unbound/root.key -c /etc/unbound/icannbundle.pem
RUN unbound-control-setup
RUN chown -R _rspamd:_rspamd /etc/rspamd/maps.d
RUN chown -R _rspamd:_rspamd /etc/rspamd/override.d
RUN chown -R _rspamd:_rspamd /var/lib/rspamd
RUN usermod -aG clamscan _rspamd
RUN usermod -aG virusgroup _rspamd
RUN chmod +x /start_dovecot.sh;chmod +x /setup.sh;
RUN chmod +x /getOpenDKIM.sh
RUN groupadd vmail -g 1001;useradd vmail -u 1001 -g 1001
RUN mkdir -p /etc/dovecot/sieve/global
COPY supervisord.conf /etc
CMD /setup.sh
