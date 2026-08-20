# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 Introduction
A full-featured Postfix Mail Server container with Active Directory (LDAP) backend authentication, Rspamd spam filtering, ClamAV antivirus, OpenDKIM signing, and Quota support.

- **GitHub Repository**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **Online Config Generator**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)

---

## 🚀 Features
- **Independent Account & Email**: Login account name can be distinct from email address (e.g., account: `520001`, email: `william@smile.taipei`).
- **Microsoft Active Directory LDAP Auth**: Compatible with Windows Server 2008R2, 2012R2, 2016, 2019, 2022.
- **Postfix Mail Transfer Agent (MTA)**.
- **Dovecot IMAP / POP3 Server**.
- **OpenDKIM**: Email signature verification & signing.
- **Rspamd**: High-performance spam filter with Web UI.
- **ClamAV**: Antivirus scanner integration.
- **Mailbox Quota**: Dovecot quota management (default 20GB, configurable).
- **Base OS**: Rocky Linux.

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

## 📋 Prerequisites
- Ensure Let's Encrypt certificates are prepared on the **Docker Host** (not inside the container).
- Maps host `/etc/letsencrypt` to container `/etc/letsencrypt`.

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
    image: inmethod/docker-postfix-ad:4.0b1
    container_name: mailserver
    restart: always
    network_mode: host
    environment:
      - DOMAIN_NAME=test.com
      - HOST_NAME=mail.test.com
      - HOST_IP=192.168.1.1
      - SEARCH_BASE=DC=test,DC=com
      - BIND_DN=CN=ldap,CN=Users,DC=test,DC=com
      - BIND_PW=your_bind_dn_password
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
  -e BIND_PW="your_bind_dn_password" \
  -e TZ="Asia/Taipei" \
  -e ENABLE_QUOTA="true" \
  -e SPAM_EMAIL="spam@test.com" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:4.0b1
```

---

## 🛡️ Rspamd Spam Filter Web UI
- **Access Web UI**: `http://<host-ip>:11334` (Recommended: use Apache/Nginx reverse proxy with SSL).
- **Default Password**: `kafeiou.pw`
- **Change Password**:
  1. Generate encrypted password hash inside container:
     ```bash
     docker exec -it mailserver rspamadm pw --encrypt -p <your_new_password>
     ```
  2. Update password hash in `/etc/rspamd/local.d/worker-controller.inc`.

---

## 🔑 Enable OpenDKIM
1. Uncomment milter configuration in `/etc/postfix/main.cf`:
   ```text
   smtpd_milters = inet:127.0.0.1:8891
   non_smtpd_milters = $smtpd_milters
   milter_default_action = accept
   ```
2. Add public key from `/etc/opendkim/keys/default.txt` to your domain DNS TXT record.
3. Configure `domains` in `/getOpenDKIM.sh` if multiple DKIM domains are required.

---

## 🏢 Active Directory Setup Guidelines
- **Username Casing**: Account names in AD must be lower-case (Dovecot queries in lower-case).
- **Email Attribute**: Fill in the `mail` attribute in the AD User or Group object.
- **Aliases**: Create an AD Group, set its `mail` attribute to the alias email address, and add member accounts to this group.
- **Local Domain Only**: Set `description` attribute to `local_only` on a User or Group to restrict messaging within local domain only.

---

## 🔍 Troubleshooting & Verification
1. Enter container shell:
   ```bash
   docker exec -it mailserver bash
   ```
2. Check running processes and services:
   ```bash
   supervisorctl status
   ```
3. Test local ports via telnet/nc:
   ```bash
   telnet localhost 25    # Postfix SMTP
   telnet localhost 143   # Dovecot IMAP
   telnet localhost 8891  # OpenDKIM
   telnet localhost 11334 # Rspamd
   ```

---

## 🛠️ Build Image Locally
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:4.0b1 --no-cache .
```
