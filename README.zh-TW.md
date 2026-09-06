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
- **Active Directory / OpenLDAP 認證**：預設採用標準 Port 389，支援設定 `ENABLE_LDAPS=true` 切換為 Port 636 (LDAPS TLS 加密)，相容 Windows Server 2008R2~2025、NethServer 8、群暉 AD 與 OpenLDAP。
- **Postfix 郵件傳輸代理 (MTA)**。
- **Dovecot IMAP / POP3 / LMTP 伺服器**。
- **Email 驅動智慧自動回覆 (Auto-Reply / Vacation)**：支援透過傳統郵件指令或區網獨立 GPU Ollama 本機端 AI 口語設定休假/銷假（支援繁中、簡中、越文、英文），無 Webmail 亦可輕鬆使用。
- **OpenDKIM**：郵件數位簽章與驗證。
- **Rspamd**：高效能垃圾郵件過濾引擎與 Web 控制台。
- **ClamAV**：內建防毒掃描。
- **信箱配額限制 (Quota)**：預設 20GB（可彈性調整）。
- **新帳號首次登入歡迎信 (First-Login Localized Welcome Email)**：新進同仁首次以收信軟體（Outlook、Thunderbird、iOS、Android）連線時，系統自動依據 Active Directory 的 `preferredLanguage` 屬性（支援繁中、簡中、越文、英文保底）將包含伺服器參數與設定教學的專屬歡迎信投遞至收件匣。

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
      # - OLLAMA_HOST=http://192.168.1.100:11434  # 區網獨立 GPU Ollama 伺服器 (支援 4 語系口語請假)
      # - OLLAMA_MODEL=qwen2.5:7b
      # - OLLAMA_TIMEOUT=180
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - mailserver_vmail:/home/vmail
      - mailserver_opendkim:/etc/opendkim
      - mailserver_postfix:/etc/postfix
      - mailserver_dovecot:/etc/dovecot
      - mailserver_welcome:/etc/dovecot/welcome_templates
      - mailserver_rspamd_conf:/etc/rspamd
      - mailserver_rspamd_var:/var/lib/rspamd
      - mailserver_log:/var/log

volumes:
  mailserver_vmail:
  mailserver_opendkim:
  mailserver_postfix:
  mailserver_dovecot:
  mailserver_welcome:
  mailserver_rspamd_conf:
  mailserver_rspamd_var:
  mailserver_log:
```

2. 啟動服務：
```bash
docker compose up -d
```

#### 🤖 如何設定與更換 Ollama AI 模型 (Ollama Model Selection)
若欲啟用口語請假或更換 AI 模型（例如切換為 `qwen2.5:7b`、`qwen2.5:3b`、`qwen3.6:27b-q8_0`），直接於 `docker-compose.yaml` 的 `environment` 調整以下參數即可生效（無需重新 Build 映像檔）：

| 環境變數 | 預設值 | 說明與建議 |
| :--- | :--- | :--- |
| `OLLAMA_HOST` | *(未設定)* | Ollama 伺服器端點，例如 `http://10.192.130.184:11434`。未設定則停用 AI 功能。 |
| `OLLAMA_MODEL` | *(未設定 / 自動探測)* | **欲使用的模型名稱**（例如 `qwen3.8-200k:latest`、`qwen2.5:7b`）。無硬編碼預設值；若留空系統會自動探測 Ollama 伺服器中正在運行或已安裝之模型。 |
| `OLLAMA_TIMEOUT` | `180` | AI 推論超時時間（秒，預設 180 秒）。若使用 GPU 推論通常 3~5 秒即可完成，若為純 CPU 或 27B 大模型建議保留預設 180 秒。 |

**更換模型範例**：
```yaml
    environment:
      - OLLAMA_HOST=http://10.192.130.184:11434
      - OLLAMA_MODEL=qwen3.8-200k:latest   # <-- 直接在此填入欲使用的模型名稱
      - OLLAMA_TIMEOUT=180                # 預設 180 秒超時保護
```
修改存檔後，執行 `docker compose up -d` 即可立即套用新模型！

---

#### 📬 新帳號首次登入歡迎信與 AD 語系設定 (Active Directory preferredLanguage)
系統在使用者首次成功通過 IMAP/POP3 登入時，會讀取 AD 帳號的 `preferredLanguage` 屬性，自動將符合其母語的歡迎信（含連線參數與 Outlook、Thunderbird、iOS、Android 四大客戶端圖文教學）投遞至收件匣。

**Active Directory `preferredLanguage` 屬性設定對照表**：

| 目標語系 | 建議標準填法 | 系統容錯支援值 (大小寫不拘) | 投遞範本檔案 |
| :--- | :--- | :--- | :--- |
| **繁體中文** | `zh-TW` | `tw`, `zh-Hant`, `Hant`, `zh-HK` | `welcome.zh-TW.eml` |
| **簡體中文** | `zh-CN` | `cn`, `zh-Hans`, `Hans`, `zh-SG` | `welcome.zh-CN.eml` |
| **越南文** | `vi` | `vi-VN`, `vn` | `welcome.vi.eml` |
| **英文** | `en` | `en-US`, `en-GB` | `welcome.en.eml` |
| **未設定 / 留空 / 其他語言** | *(空白)* 或如 `ja`, `ko` | 任何不在上述清單中的代碼 | **自動保底英文 (`welcome.en.eml`)** |

> **💡 AD 管理員設定步驟**：
> 1. 開啟 Windows Server「Active Directory 使用者和電腦」(dsa.msc)。
> 2. 上方功能表點選「檢視 (View)」➔ 勾選 **「進階功能 (Advanced Features)」**。
> 3. 雙擊該名使用者 ➔ 切換至 **「屬性編輯器 (Attribute Editor)」** 分頁。
> 4. 找到 `preferredLanguage` 屬性，點擊編輯填入代碼（例如 `zh-TW` 或 `vi`）並儲存即可。

---

### 方式三：使用 Docker CLI 指令

1. 建立持久化 Volumes：
```bash
docker volume create mailserver_vmail
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_welcome
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
  -v mailserver_welcome:/etc/dovecot/welcome_templates \
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
  -e OLLAMA_HOST="http://192.168.1.100:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -e OLLAMA_TIMEOUT=180 \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:latest
```

---

## 🛡️ Rspamd 郵件安全防護與 Web 控制台指南
如需了解 Rspamd 垃圾郵件過濾、Web 控制台操作（`http://<IP>:11334`，預設密碼 `kafeiou.pw`）、零退信隔離（`SPAM_EMAIL` 救援）、黑白名單名冊與危險附件過濾，請參閱專屬的 **[Rspamd 防護指南 (RSPAMD.zh-TW.md)](RSPAMD.zh-TW.md)**。

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
