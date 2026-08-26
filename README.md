# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 Introduction
A full-featured Postfix Mail Server container with Active Directory (LDAP) backend authentication, Rspamd spam filtering, ClamAV antivirus, OpenDKIM signing, and Quota support.

- **GitHub Repository**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **Online Config Generator**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)
- **System Architecture & Technical Guide**: [ARCHITECTURE.md](ARCHITECTURE.md) | [Online Interactive Guide](https://williamfromtw.github.io/docker-Postfix-AD/architecture.html)

---

## 🚀 Key Features
- **Independent Account & Email**: Login account name must be the pure username/employee ID (`sAMAccountName` / `uid`, e.g., account: `520001`, email: `william@smile.taipei`). Logging in with `@domain` or email address is strictly prohibited.
- **Active Directory / OpenLDAP Auth**: Defaults to standard Port 389, with optional `ENABLE_LDAPS=true` for Port 636 LDAPS TLS encryption. Compatible with Windows Server 2008R2~2025, NethServer 8, Synology AD, and OpenLDAP.
- **Postfix Mail Transfer Agent (MTA)**.
- **Dovecot IMAP / POP3 / LMTP Server**.
- **Email-Driven Smart Auto-Reply & Vacation Responder**: Sieve-powered automatic replies triggered via email commands without requiring a Webmail GUI.
- **OpenDKIM**: Email signature verification & signing.
- **Rspamd**: High-performance spam filter with Web UI.
- **ClamAV**: Antivirus scanner integration.
- **Mailbox Quota**: Dovecot quota management (default 20GB, configurable).

---

## 🔌 Supported Protocols & Ports

| Protocol | Port | Encryption |
| :--- | :--- | :--- |
| **SMTP** | `25` | Plain / STARTTLS |
| **SMTPS** | `465` | SSL/TLS |
| **Submission** | `587` | STARTTLS |
| **POP3** | `110` | Plain / STARTTLS |
| **POP3S** | `995` | SSL/TLS |
| **IMAP** | `143` | Plain / STARTTLS |
| **IMAPS** | `993` | SSL/TLS |
| **ManageSieve** | `4190` | TLS |
| **Rspamd Web UI** | `11334` | HTTP (Proxy recommended) |

---

## ⚙️ Quick Start

### Option 1: Online Generator (Recommended)
Visit the [Online Config Generator](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html) to interactively generate your `docker-compose.yaml` or `docker run` command with a single click.

---

### Option 2: Docker Compose (`docker-compose.yaml`)

1. Create a `docker-compose.yaml` file:

```yaml
version: '3.8'

services:
  mailserver:
    image: inmethod/docker-postfix-ad:latest
    container_name: mailserver
    restart: always
    network_mode: host
    environment:
      - DOMAIN_NAME=test.com
      - HOST_NAME=mail.test.com
      - HOST_IP=192.168.1.1
      - SEARCH_BASE=DC=test,DC=com
      - BIND_DN=CN=ldap,CN=Users,DC=test,DC=com
      - BIND_PW='your_bind_dn_password'
      - TZ=Asia/Taipei
      - ENABLE_QUOTA=true
      - SPAM_EMAIL=spam@test.com
      # - ALIASES=OU=aliases,DC=test,DC=com
      # - MY_NETWORKS=192.168.1.0/24
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - mailserver_vmail:/home/vmail
      - mailserver_opendkim:/etc/opendkim
      - mailserver_postfix:/etc/postfix
      - mailserver_dovecot:/etc/dovecot
      - mailserver_rspamd_conf:/etc/rspamd
      - mailserver_rspamd_var:/var/lib/rspamd
      - mailserver_log:/var/log

volumes:
  mailserver_vmail:
  mailserver_opendkim:
  mailserver_postfix:
  mailserver_dovecot:
  mailserver_rspamd_conf:
  mailserver_rspamd_var:
  mailserver_log:
```

2. Start the service:
```bash
docker compose up -d
```

---

### Option 3: Docker CLI Command

1. Create named volumes:
```bash
docker volume create mailserver_vmail
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_log
docker volume create mailserver_opendkim
docker volume create mailserver_rspamd_conf
docker volume create mailserver_rspamd_var
```

2. Run the container:
```bash
docker run --name mailserver \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v mailserver_vmail:/home/vmail \
  -v mailserver_opendkim:/etc/opendkim \
  -v mailserver_postfix:/etc/postfix \
  -v mailserver_dovecot:/etc/dovecot \
  -v mailserver_rspamd_conf:/etc/rspamd \
  -v mailserver_rspamd_var:/var/lib/rspamd \
  -v mailserver_log:/var/log \
  -p 25:25 -p 110:110 -p 143:143 -p 465:465 -p 587:587 -p 993:993 -p 995:995 -p 4190:4190 -p 11334:11334 \
  -e DOMAIN_NAME="test.com" \
  -e HOST_NAME="mail.test.com" \
  -e HOST_IP="192.168.1.1" \
  -e SEARCH_BASE="DC=test,DC=com" \
  -e BIND_DN="CN=ldap,CN=Users,DC=test,DC=com" \
  -e BIND_PW='your_bind_dn_password' \
  -e TZ="Asia/Taipei" \
  -e ENABLE_QUOTA="true" \
  -e SPAM_EMAIL="spam@test.com" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:latest
```

---

## 🏛️ In-Depth Architecture & Operations Guide
For detailed configuration guidelines and Mermaid workflow diagrams, please refer to the dedicated **[System Architecture Guide (ARCHITECTURE.md)](ARCHITECTURE.md)**:
- **Active Directory LDAP Rules**: Account lowercase rule, `mail` attribute, `ALIASES` group, `local_only` restrictions.
- **Mail Security Pipeline**: Postfix + Rspamd + ClamAV + OpenDKIM milter inspection flow.
- **SSL/TLS Certificates**: Out-of-the-box self-signed generator (`make_fake_cert.sh`) & Host Certbot DNS-01 renewal guide.
- **DKIM & SPF Setup**: OpenDKIM activation, `getOpenDKIM.sh` multi-domain key generation, DNS TXT templates.
- **Troubleshooting & Tuning**: Service diagnostics, fail2ban integration, performance caching.

---

## 🛠️ Build Image Locally
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:latest --no-cache .
```
