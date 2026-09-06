FROM rockylinux/rockylinux:10.2
RUN dnf -y  update
RUN dnf -y install epel-release
RUN dnf config-manager --set-enabled crb
RUN dnf -y  update 
RUN dnf -y  upgrade
RUN curl https://rspamd.com/rpm-stable/centos-10/rspamd.repo > /etc/yum.repos.d/rspamd.repo 
RUN update-crypto-policies --set LEGACY
RUN rpm --import https://rspamd.com/rpm-stable/gpg.key
RUN dnf update -y
RUN dnf -y install git man sudo chrony crontabs postfix-* htop procps-ng ca-certificates unbound valkey rspamd libffi-devel dovecot-pigeonhole python3 opendkim-tools opendkim bind-utils net-tools postfix cyrus-sasl cyrus-sasl-plain cyrus-sasl-md5 clamav clamd clamav-update clamav-devel clamav-scanner-systemd clamav-data clamav-server clamav-server-systemd dovecot supervisor httpd mod_ssl telnet rsyslog vi vim wget rsync glibc-gconv-extra 
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
COPY setup.sh /setup.sh
COPY start_dovecot.sh /start_dovecot.sh
COPY logrotate.d/ /etc/logrotate.d/
COPY getOpenDKIM.sh /getOpenDKIM.sh
COPY make_fake_cert.sh /make_fake_cert.sh
COPY scripts/ /usr/lib/dovecot/sieve-pipe/
RUN chmod 755 /usr/lib/dovecot/sieve-pipe/*.py
RUN /usr/sbin/unbound-anchor -a /var/lib/unbound/root.key -c /etc/unbound/icannbundle.pem
RUN unbound-control-setup
RUN chown -R _rspamd:_rspamd /etc/rspamd/maps.d
RUN chown -R _rspamd:_rspamd /etc/rspamd/kafeiou.d
RUN chown -R _rspamd:_rspamd /var/lib/rspamd
RUN usermod -aG clamscan _rspamd
RUN usermod -aG virusgroup _rspamd
RUN chmod +x /start_dovecot.sh;chmod +x /make_fake_cert.sh;chmod +x /setup.sh;
RUN chmod +x /getOpenDKIM.sh
RUN groupadd vmail -g 1001;useradd vmail -u 1001 -g 1001
RUN mkdir -p /etc/dovecot/sieve/global
RUN /usr/bin/sievec /etc/dovecot/sieve/global/autoreply_handler.sieve 2>/dev/null || true
COPY supervisord.conf /etc
CMD ["/setup.sh"]
