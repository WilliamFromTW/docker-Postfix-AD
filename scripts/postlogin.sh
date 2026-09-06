#!/bin/bash
# -------------------------------------------------------------
# Dovecot Post-login Hook for first IMAP/Webmail login onboarding
# -------------------------------------------------------------
[ -f /etc/mail_env ] && . /etc/mail_env
if [ -n "$USER" ]; then
  /usr/bin/python3 /usr/lib/dovecot/sieve-pipe/welcome_provisioner.py --event imap_login --recipient "$USER" >/dev/null 2>&1 &
fi
exec "$@"
