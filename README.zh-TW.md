# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 專案簡介
這是一個功能完整且經過整合的 Postfix 郵件伺服器 Docker 容器，具備 Microsoft Active Directory (LDAP) 帳號後端驗證、Rspamd 垃圾郵件過濾、ClamAV 病毒掃描、OpenDKIM 數位簽章以及信箱配額 (Quota) 管理支援。

- **GitHub 專案庫**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **線上設定產生器**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)

---

## 🚀 主要特色
- **帳號與信箱可獨立分離**：登入帳號名稱可與電子郵件地址不同（例如：帳號 `520001`，信箱 `william@smile.taipei`）。
- **微軟 Active Directory LDAP 認證**：相容 Windows Server 2008R2、2012R2、2016、2019、2022。
- **Postfix 郵件傳輸代理 (MTA)**。
- **Dovecot IMAP / POP3 伺服器**。
- **OpenDKIM**：郵件數位簽章與驗證。
- **Rspamd**：高效能垃圾郵件過濾引擎與 Web 控制台。
- **ClamAV**：內建防毒掃描。
- **信箱配額限制 (Quota)**：預設 20GB（可彈性調整）。
- **底層系統**：Rocky Linux。

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

## 📋 事前準備
- 請確保 Docker 宿主機（Host）已準備好 Let's Encrypt 憑證。
- 將宿主機之 `/etc/letsencrypt` 掛載對應至容器內的 `/etc/letsencrypt`。

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
  -e BIND_PW="your_bind_dn_password" \
  -e TZ="Asia/Taipei" \
  -e ENABLE_QUOTA="true" \
  -e SPAM_EMAIL="spam@test.com" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:4.0b1
```

---

## 🛡️ Rspamd 垃圾郵件過濾器 Web 控制台
- **登入 Web 介面**：`http://<宿主機IP>:11334`（建議設定反向代理並掛載 SSL）。
- **預設密碼**：`kafeiou.pw`
- **修改管理員密碼**：
  1. 於容器內產生加密雜湊：
     ```bash
     docker exec -it mailserver rspamadm pw --encrypt -p <您的新密碼>
     ```
  2. 將產生出的加密字串更新至 `/etc/rspamd/local.d/worker-controller.inc`。

---

## 🔑 啟用 OpenDKIM 數位簽章
1. 取消 `/etc/postfix/main.cf` 中的 milter 註解：
   ```text
   smtpd_milters = inet:127.0.0.1:8891
   non_smtpd_milters = $smtpd_milters
   milter_default_action = accept
   ```
2. 將 `/etc/opendkim/keys/default.txt` 的公鑰內容新增至您網域的 DNS TXT 記錄中。
3. 若有多網域需求，可編輯 `/getOpenDKIM.sh` 中的 `domains` 參數批次產生金鑰。

---

## 🏢 Active Directory (AD) 設定規範
- **帳號大小寫**：AD 中的使用者登入帳號必須為**小寫**（因 Dovecot 預設均轉為小寫查詢）。
- **Email 屬性**：請於 AD 使用者或群組物件中的 `mail` 屬性填入電子郵件地址。
- **群組別名 (Aliases)**：建立群組並在 `mail` 屬性填寫別名信箱，並將成員帳號加入群組。
- **限制僅限本地網域寄收 (local_only)**：在 AD 使用者或群組的 `description` 屬性填寫 `local_only` 即可限制僅限內部收發。

---

## 🔍 服務檢查與除錯
1. 進入容器內部：
   ```bash
   docker exec -it mailserver bash
   ```
2. 檢查各服務執行狀態：
   ```bash
   supervisorctl status
   ```
3. 測試服務 Port 是否正常監聽：
   ```bash
   telnet localhost 25    # Postfix SMTP
   telnet localhost 143   # Dovecot IMAP
   telnet localhost 8891  # OpenDKIM
   telnet localhost 11334 # Rspamd
   ```

---

## 🛠️ 本地建置映像檔
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:4.0b1 --no-cache .
```
