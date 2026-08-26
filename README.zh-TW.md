# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 專案簡介
這是一個功能完整且經過整合的 Postfix 郵件伺服器 Docker 容器，具備 Microsoft Active Directory (LDAP) 帳號後端驗證、Rspamd 垃圾郵件過濾、ClamAV 病毒掃描、OpenDKIM 數位簽章以及信箱配額 (Quota) 管理支援。

- **GitHub 專案庫**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **線上設定產生器**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)
- **系統架構與維運指南**: [ARCHITECTURE.zh-TW.md](ARCHITECTURE.zh-TW.md) | [線上互動架構圖](https://williamfromtw.github.io/docker-Postfix-AD/architecture.html)

---

## 🚀 主要特色
- **帳號與信箱可獨立分離**：登入帳號名稱必須為純帳號/工號（`sAMAccountName` / `uid`，例如：帳號 `520001`，信箱 `william@smile.taipei`），嚴格禁止使用含 `@網域` 或 Email 地址登入。
- **Active Directory / OpenLDAP LDAPS 認證 (Port 636)**：安全 TLS 加密傳輸，相容 Windows Server 2008R2~2025、NethServer 8、群暉 AD 與 OpenLDAP。
- **Postfix 郵件傳輸代理 (MTA)**。
- **Dovecot IMAP / POP3 / LMTP 伺服器**。
- **Email 驅動智慧自動回覆 (Auto-Reply / Vacation)**：支援透過郵件指令設定休假與公出自動回信，無 Webmail 亦可輕鬆使用。
- **OpenDKIM**：郵件數位簽章與驗證。
- **Rspamd**：高效能垃圾郵件過濾引擎與 Web 控制台。
- **ClamAV**：內建防毒掃描。
- **信箱配額限制 (Quota)**：預設 20GB（可彈性調整）。

---

## 🔌 支援通訊協定與通訊埠 (Ports)

| 通訊協定 | Port | 加密方式 |
| :--- | :--- | :--- |
| **SMTP** | `25` | 明碼 / STARTTLS |
| **SMTPS** | `465` | SSL/TLS |
| **Submission** | `587` | STARTTLS |
| **POP3** | `110` | 明碼 / STARTTLS |
| **POP3S** | `995` | SSL/TLS |
| **IMAP** | `143` | 明碼 / STARTTLS |
| **IMAPS** | `993` | SSL/TLS |
| **ManageSieve** | `4190` | TLS |
| **Rspamd Web UI** | `11334` | HTTP (建議搭配 Reverse Proxy) |

---

## ⚙️ 快速開始

### 方式一：使用線上產生器（強烈推薦）
前往 [線上設定產生器 (Online Generator)](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)，可於瀏覽器圖形化填寫並一鍵產出 `docker-compose.yaml` 或 `docker run` 指令。

---

### 方式二：使用 Docker Compose (`docker-compose.yaml`)

1. 建立 `docker-compose.yaml` 檔案：

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

2. 啟動服務：
```bash
docker compose up -d
```

---

### 方式三：使用 Docker CLI 指令

1. 建立持久化 Volumes：
```bash
docker volume create mailserver_vmail
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_log
docker volume create mailserver_opendkim
docker volume create mailserver_rspamd_conf
docker volume create mailserver_rspamd_var
```

2. 啟動容器：
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

## 🏛️ 深度系統架構與技術維運指南
如需深入了解 Active Directory 整合細節、郵件安全過濾流程圖與 DKIM/Let's Encrypt 設定手冊，請參閱專屬的 **[系統架構指南 (ARCHITECTURE.zh-TW.md)](ARCHITECTURE.zh-TW.md)**：
- **Active Directory LDAP 設定規範**：帳號小寫規範、`mail` 屬性、`ALIASES` 群組別名、`local_only` 限制。
- **郵件過濾與安全管道**：Postfix + Rspamd + ClamAV + OpenDKIM 處理流程。
- **SSL/TLS 憑證架構**：測試自簽憑證自動補位機制 (`make_fake_cert.sh`) 與宿主機 Certbot DNS-01 申請教學。
- **DKIM & SPF 設定指南**：OpenDKIM 啟用、`getOpenDKIM.sh` 批次多網域金鑰產生、DNS TXT 記錄範本。
- **除錯、效能調校與 Fail2ban 實務**。

---

## 🛠️ 本地建置映像檔
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:latest --no-cache .
```
