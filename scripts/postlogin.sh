#!/bin/sh
# Dovecot script-login Post-Login Hook
# Ensures first-login welcome email delivery with zero overhead for subsequent logins.

# If the welcome email has already been sent, immediately proceed to imap/pop3 (<0.1ms)
if [ -n "$HOME" ] && [ -f "$HOME/.welcome_sent" ]; then
  exec "$@"
fi

# Invoke Python provisioning script (handles atomic directory lock and template injection)
if [ -x "/usr/lib/dovecot/sieve-pipe/provision_welcome_email.py" ]; then
  /usr/lib/dovecot/sieve-pipe/provision_welcome_email.py || true
elif [ -x "/usr/lib/dovecot/provision_welcome_email.py" ]; then
  /usr/lib/dovecot/provision_welcome_email.py || true
fi

# Always execute the original command passed by Dovecot (imap or pop3)
exec "$@"
