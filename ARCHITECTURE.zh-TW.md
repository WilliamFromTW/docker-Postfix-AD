# 系統架構與技術維運指南

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](ARCHITECTURE.md) | [繁體中文](ARCHITECTURE.zh-TW.md) | [简体中文](ARCHITECTURE.zh-CN.md) | [Tiếng Việt](ARCHITECTURE.vi.md)

---

## 📌 簡介
本文件提供 **docker-Postfix-AD** 容器技術架構的深度剖析。詳細說明 Postfix、Dovecot、微軟 Active Directory (LDAP)、Rspamd、ClamAV、OpenDKIM 以及 SSL/TLS 憑證體系之間的協同運作流程。

- **專案首頁**: [README.zh-TW.md](README.zh-TW.md)
- **線上設定產生器**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)
- **線上互動架構圖網頁**: [https://williamfromtw.github.io/docker-Postfix-AD/architecture.html](https://williamfromtw.github.io/docker-Postfix-AD/architecture.html)

---

## 🏛️ 1. 全域架構與 Active Directory / LDAP 整合模型

本容器將 **Postfix** (MTA 傳輸代理) 與 **Dovecot** (IMAP/POP3 服務) 與 **微軟 Windows Active Directory** 或 **OpenLDAP** 深度整合。連線預設採用標準 Port 389，並支援透過 `ENABLE_LDAPS=true` 切換為 Port 636 (LDAPS TLS 加密傳輸)。

```mermaid
graph TD
    RemoteMTA["外部郵件伺服器 (Remote MTA)"] -->|"SMTP :25 (Server-to-Server 傳輸)"| Postfix["Postfix MTA"]
    Client["郵件用戶端 (Client / MUA)"] -->|"SMTPS/Submission :465/:587 (驗證寄信)"| Postfix
    Client -->|"IMAP/POP3 :993/:995 (收信存取)"| Dovecot["Dovecot IMAP/POP3"]
    
    subgraph AD_DC ["Windows Active Directory / OpenLDAP"]
        AD[("AD / LDAP 伺服器 :389 / :636")]
    end

    Postfix -->|ldap-users.cf: 查驗收件人與本地信箱| AD
    Postfix -->|ldap-aliases.cf: 解析群組別名| AD
    Postfix -->|ldap-local_only.cf: 檢查內部網域限制| AD
    Dovecot -->|dovecot-ldap.conf.ext: 帳號密碼認證與信箱查詢| AD
    Dovecot -->|Maildir 儲存 / Quota 配額控管| VMail[("儲存空間 /home/vmail")]
```

### 📋 Active Directory (AD) / OpenLDAP 欄位設定與驗證規範
1. **帳號驗證強制使用純帳號（`sAMAccountName` / `uid`）**：
   - 使用者在收發信軟體（Outlook、Thunderbird、手機）設定帳號時，**帳號欄位必須填寫純工號或 AD/LDAP 帳號**（如 `520001` 或 `john`，全小寫），**嚴格禁止使用含 `@網域` 或 Email 格式登入**。
2. **電子郵件地址（`mail` 屬性）**：
   - 請於 AD/LDAP 使用者屬性中的 `mail` 欄位填寫完整的 Email 地址（例如 `john@smile.taipei`）。
   - 登入帳號名稱與電子郵件地址完全獨立分離。外部來信會依據 `mail` 屬性精準投遞至 `/home/vmail/john@smile.taipei`。
3. **群組別名（`ALIASES`）**：
   - 在 AD 建立「群組」，並將別名 Email 填入群組的 `mail` 屬性（如 `sales@smile.taipei`），接著將成員帳號加入此群組即可。
4. **限制僅限本地網域寄收（`local_only`）**：
   - 在 AD 使用者或群組的 `description` 屬性填入 `local_only`。
   - Postfix 會阻擋此帳號對外部公網寄信或收信，僅允許在內部網域互寄。

---

## 🛡️ 2. 郵件安全過濾管道 (Postfix + Rspamd + ClamAV + OpenDKIM)

所有進出郵件皆經過 Postfix 串接的 Milter 過濾鏈：

```mermaid
sequenceDiagram
    participant Sender as 外部寄件者 / 客戶端
    participant Postfix as Postfix SMTP
    participant Rspamd as Rspamd 垃圾郵件過濾 (:11334)
    participant ClamAV as ClamAV 防毒掃描 (:3310)
    participant DKIM as OpenDKIM 簽章服務 (:8891)
    participant Dovecot as Dovecot LDA / LMTP (:home/vmail)

    Sender->>Postfix: 傳送郵件 (SMTP)
    Postfix->>Rspamd: Milter 串流過濾檢查
    Rspamd->>ClamAV: 掃描附件是否含有惡意程式
    ClamAV-->>Rspamd: 掃描結果 (Clean / Infected)
    Rspamd->>Rspamd: SPF, DMARC, 啟發式規則, 神經網絡評分
    alt 判定為垃圾郵件 (隔離 / 拒收)
        Rspamd-->>Postfix: 標記標頭 / 轉發至 SPAM_EMAIL
    else 正常郵件
        Rspamd-->>Postfix: 允許通過
        Postfix->>DKIM: 簽署 / 驗證 DKIM 數位簽章 (Port 8891)
        DKIM-->>Postfix: 回傳已簽章標頭
        Postfix->>Dovecot: 經由 LMTP 派送至 /home/vmail (檢查 Quota)
    end
```

### 🔧 Rspamd Web 控制台與密碼管理
- **Web UI 網址**: `http://<宿主機IP>:11334`
- **預設管理員密碼**: `kafeiou.pw`
- **產生新加密密碼雜湊**:
  ```bash
  docker exec -it mailserver rspamadm pw --encrypt -p <您的新密碼>
  ```
  將產出的雜湊字串貼入 `/etc/rspamd/local.d/worker-controller.inc`。
- **垃圾郵件轉發 (`SPAM_EMAIL`)**:
  當設定了 `SPAM_EMAIL` 變數時，被判定為垃圾郵件隔離的信件會自動轉發至指定信箱（如 `spam@smile.taipei`）。
- **完整 Rspamd 設定指南**:
  關於黑白名單、關鍵字正則、危險副檔名與隔離郵件救援完整範例，請參閱專屬的 **[Rspamd 防護指南 (RSPAMD.zh-TW.md)](RSPAMD.zh-TW.md)**。

---

## 🔐 3. SSL/TLS 憑證架構與 Let's Encrypt 管理機制

容器具備**開箱即用**的自動補位機制，同時完美支援企業正式 Let's Encrypt 憑證。

```mermaid
graph TD
    subgraph SG1 ["容器啟動階段 (setup.sh)"]
        A{"檢查 /etc/letsencrypt/live/HOST_NAME/fullchain.pem"}
        A -->|不存在| B["自動執行 /make_fake_cert.sh"]
        B --> C["產生自簽 Fake 測試憑證"]
        C --> D["Postfix 與 Dovecot SSL 服務立即無痛啟動"]
        A -->|已存在| E["直接載入正式 Let's Encrypt 憑證"]
        E --> D
    end

    subgraph SG2 ["宿主機維運 (事後透過 DNS-01 申請正式憑證)"]
        F["管理者於宿主機執行 Certbot DNS-01"] --> G["向 Let's Encrypt 取得正式萬用/主機憑證"]
        G --> H["存入宿主機 /etc/letsencrypt"]
        H -->|Volume 映射| I["容器即時讀取最新正式憑證"]
        I --> J["於容器內重新載入服務: postfix & dovecot reload"]
    end
```

### 🚀 零設定即刻啟動機制 (`make_fake_cert.sh`)
- 第一次啟動容器時，若宿主機尚未掛載正式憑證，容器內 `setup.sh` 會自動執行 `/make_fake_cert.sh ${HOST_NAME}`。
- 自動建立符合 Let's Encrypt 目錄結構的自簽憑證（`cert.pem`, `privkey.pem`, `chain.pem`, `fullchain.pem`），讓 Postfix 與 Dovecot 的 SSL/TLS 服務（Port 465, 587, 993, 995）正常啟動而不崩潰。

### 🌐 透過宿主機 Certbot (DNS-01 挑戰) 取得正式憑證
因郵件伺服器通常不建議對外開放 HTTP Port 80，強烈建議在 Docker 宿主機使用 **DNS-01 挑戰**：

1. **宿主機安裝 Certbot**:
   ```bash
   sudo apt install certbot  # Ubuntu / Debian
   # 或 sudo dnf install certbot  # RHEL / Rocky Linux
   ```

2. **透過 DNS 驗證申請憑證**:
   ```bash
   sudo certbot certonly --manual --preferred-challenges dns -d mail.smile.taipei -d smile.taipei
   ```
   依畫面提示至您的 DNS 代管商新增 `_acme-challenge` TXT 記錄。

3. **重新載入容器服務**:
   憑證生成於宿主機 `/etc/letsencrypt/live/mail.smile.taipei/` 後，直接在容器內重新載入：
   ```bash
   docker exec -it mailserver postfix reload
   docker exec -it mailserver dovecot reload
   ```

---

## 🔑 4. DKIM 與 SPF 數位安全設定手冊

### 1. 於容器內啟用 OpenDKIM
1. 進入容器內部：
   ```bash
   docker exec -it mailserver bash
   ```
2. 取消 `/etc/postfix/main.cf` 中的 milter 註解：
   ```text
   smtpd_milters = inet:127.0.0.1:8891
   non_smtpd_milters = $smtpd_milters
   milter_default_action = accept
   ```
3. 重新載入 Postfix：
   ```bash
   postfix reload
   ```

### 2. 批次產生多網域 DKIM 金鑰 (`/getOpenDKIM.sh`)
1. 編輯 `/getOpenDKIM.sh` 填入您的網域名稱：
   ```bash
   domains=( 
     'smile.taipei'
     'example2.com'
   )
   ```
2. 執行腳本：
   ```bash
   /getOpenDKIM.sh
   ```
3. 產生的公鑰內容將存於 `/etc/opendkim/keys/<網域>/default.txt`。

### 3. DNS TXT 記錄配置範例
請在您的 DNS 管理介面新增以下記錄：

#### A. SPF 記錄 (網域主記錄 `@`)
```text
類型: TXT
主機: @ (或 smile.taipei)
值:   v=spf1 ip4:<您的伺服器公網IP> mx ~all
```

#### B. DKIM 記錄 (TXT 記錄)
```text
類型: TXT
主機: default._domainkey
值:   v=DKIM1; k=rsa; p=<default.txt 內的公鑰字串>
```

#### C. DMARC 記錄 (TXT 記錄)
```text
類型: TXT
主機: _dmarc
值:   v=DMARC1; p=quarantine; rua=mailto:postmaster@smile.taipei
```

---

## 🤖 5. Email 驅動之智慧自動回覆 (Auto-Reply / Vacation Responder)

針對無 Webmail 前端介面的環境，本專案提供獨創的 **Email-Driven 智慧自動回信與休假應答系統**（由 Postfix LMTP、Dovecot Pigeonhole Sieve 與 Sieve Extprograms 驅動）。

```mermaid
graph TD
    User["使用者 (寄信給自己: From == To)"] -->|"# 指令或四語系口語關鍵字"| Postfix["Postfix MTA"]
    Postfix -->|"LMTP 派送"| Dovecot["Dovecot LMTP + Sieve Engine"]
    
    Dovecot -->|"autoreply_handler.sieve"| Handler["解析腳本 (handle_autoreply.py)"]
    Handler --> CheckOllama{"是否有設定 OLLAMA_HOST 且連線正常？"}
    
    CheckOllama -->|"是"| Ollama["Ollama 區網 GPU 伺服器 (JSON 意圖辨識)"]
    CheckOllama -->|"否 / 超時"| FallbackRegex["傳統 Regex 解析器 (# 指令)"]
    
    Ollama --> ResultCheck{"AI 解析結果"}
    ResultCheck -->|"action: disable"| DoDisable["清除 Sieve 並寄送停用通知信"]
    ResultCheck -->|"成功辨識起訖日"| ApplyConfig["生成 dovecot.sieve 與 config.json"]
    ResultCheck -->|"日期模糊/無日期"| NotifyUnclear["寄送補充日期提醒信"]
    
    FallbackRegex --> ApplyConfig
    ApplyConfig --> Sievec["sievec 編譯 (.svbin 二進位規則)"]
    Sievec --> SendSuccess["發送設定結果確認信給本人"]

    RemoteSender["外部寄件者"] -->|"發送信件"| Postfix
    Postfix -->|"LMTP 派送"| Dovecot
    Dovecot -->|"檢查 dovecot.sieve 與 15 秒延遲"| CheckDate{"是否在生效區間內？"}
    CheckDate -->|"是 (且 24 小時內未回過)"| AutoReply["自動發送標準固定樣板回覆 (非 AI 生成)"]
    CheckDate -->|"否"| Inbox["正常存入 Maildir 收件匣"]
```

### 📩 如何啟用 / 停用自動回覆

使用者只需在任何電腦或手機郵件 App 中**寄一封信給自己（From == To）**：

#### 0. 🤖 區網獨立 GPU Ollama 本機端 AI 口語請假模式 (支援 4 語系)
當環境變數設定了 `OLLAMA_HOST`（例如：`http://192.168.1.100:11434`）且 AI 服務正常時，同仁可直接隨手用日常口語發信給自己：
- **繁體中文**：主旨填寫「`我下週三到五休假去日本`」、「`明天下午請假去看牙醫`」
- **簡體中文**：主旨填寫「`我下周一到周三出差北京`」、「`明天请假一天`」
- **越南文**：主旨填寫「`Tôi xin nghỉ phép từ thứ 4 đến thứ 6 tuần sau`」、「`Ngày mai tôi đi công tác`」
- **英文**：主旨填寫「`Out of office until next Monday`」、「`I will be on vacation tomorrow`」
- **口頭銷假 / 取消回覆**：隨手發信「`我銷假了`」、「`取消這次休假`」、「`Tôi đã đi làm lại`」或「`Cancel out of office`」，系統立即停用自動回信！
- **零 AI 幻覺保障**：AI 僅負責解析時間區間與意圖，對外自動回覆信件堅持採用公司標準樣板（若同仁信件內文有撰寫代理人資訊，則採用同仁撰寫內容）。
- **無縫降級保護**：若 GPU 主機離線或超時（預設 5 秒），自動降級回傳統 Regex 處理；純口語時主動寄信提醒同仁改用 `#autoreply`。

##### ⚙️ 如何更換 Ollama 模型與環境變數設定
您可以隨時更換 Ollama 執行的模型（例如換成 `qwen2.5:7b`、`qwen2.5:3b` 或 `qwen3.6:27b-q8_0`），只需在 `docker-compose.yaml` 或容器啟動參數中指定：

| 環境變數 | 預設值 | 說明 |
| :--- | :--- | :--- |
| `OLLAMA_HOST` | *(未設定)* | Ollama API 位址（如 `http://10.192.130.184:11434`） |
| `OLLAMA_MODEL` | *(未設定 / 自動探測)* | **欲使用的模型名稱**（例如 `qwen3.8-200k:latest`、`qwen2.5:7b`）。無寫死預設值，未填寫時系統將自動連線 Ollama 探測當前運行或已下載模型。 |
| `OLLAMA_TIMEOUT` | `180` | 超時時間（秒，預設 180 秒）。即使為 CPU 運算或 27B 大模型亦有充分時間推論。 |

* **模型推薦**：
  * **GPU 首選 `qwen3.8-200k:latest` 或 `qwen2.5:7b`**：GPU 顯存全載入，推論約 1~3 秒，4 語系日期解析極為精準。
  * **輕量首選 `qwen2.5:3b`**：約 1.9 GB，即使伺服器無 GPU 純 CPU 運算，亦能在 1~2 秒內完成解析。
  * **大模型與純 CPU 運算**：預設的 180 秒超時保護機制可確保 27B 等大模型或 CPU 運算能完整執行推論完畢。

#### 1. 指定日期區間（傳統 `#` 指令模式，預設時區：台灣 UTC+8 台北時間）
- **收件人**：自己 (`your_email@example.com`)
- **主旨**：`#autoreply 2026-08-25 ~ 2026-08-30 外出開會 / 休假`（亦支援 `#vacation`、`#休假`、`#不在`、`#出差`、`#請假`）
- **內文**：填寫您要回覆給對方的信件內容（可自訂職務代理人、緊急電話等）。
- *系統將於 2026-08-25 00:00:00 自動生效，並於 2026-08-30 23:59:59 (UTC+8) 自動過期失效，完全無需手動關閉。*

#### 2. 常開模式（直到手動關閉）
- **主旨**：`#autoreply on 出差中`
- **內文**：自訂回信內容。

#### 3. 立即停用 / 取消
- **主旨**：`#autoreply off`（或 `#autoreply cancel`、`#autoreply 停用`）

#### 4. 即時確認信與防洗版保護
- 設定成功或取消後，系統會在數秒內**自動回寄確認信**給使用者本人，清楚列出生效區間與回信內文預覽。
- **防洗版機制 (`:days 1`)**：同一外部寄件者在 24 小時內寄多封信時，Sieve 最多僅會回覆 1 次，徹底避免信件迴圈與轟炸。

---

## ⚡ 6. 效能調校、日誌檢視與 Fail2ban 實務

### 1. Fail2ban 與真實 IP 取得
為了讓宿主機上的 fail2ban 能直接讀取 `/var/log/maillog` 進行阻擋，強烈建議啟動容器時使用 **`--net=host`**（或 Compose 中的 `network_mode: host`）。

### 2. 容器重要調校設定檔
- `/etc/dovecot/conf.d/10-auth.conf`（快取容量與效能優化）
- `/etc/dovecot/conf.d/10-master.conf`（VSZ 記憶體限制）
- `/etc/dovecot/conf.d/90-quota.conf`（預設信箱配額規則）

### 3. 服務健康檢查與除錯指令
```bash
# 檢查 supervisor 管理的所有子服務狀態
docker exec -it mailserver supervisorctl status

# 測試本機 Port 監聽狀態
docker exec -it mailserver telnet localhost 25    # Postfix SMTP
docker exec -it mailserver telnet localhost 143   # Dovecot IMAP
docker exec -it mailserver telnet localhost 8891  # OpenDKIM
docker exec -it mailserver telnet localhost 11334 # Rspamd
docker exec -it mailserver telnet localhost 12340 # Quota 服務
```

---

## 📬 7. 企業級雙層郵件收回系統 (Two-Tier Message Recall System)

本系統具備原生相容 Microsoft Outlook「收回此郵件」與行動裝置 `#recall` 回覆之企業級雙層收回機制，解決傳統 IMAP 無法收回郵件與造成收件者好奇點閱之歷史痛點。

### 🔄 系統架構流程圖

```mermaid
flowchart TD
    subgraph Client ["寄件者 (Sender Client)"]
        A1["Outlook (PC) 寄出郵件"]
        A2["行動裝置 / 其它客戶端寄出郵件"]
    end

    subgraph Layer1 ["第一層：Postfix 出站佇列暫存 (Layer 1: Delay Buffer)"]
        B["Postfix Submission / SMTPS (:587 / :465)"]
        C["立即回傳 250 OK (寄件無延遲感)"]
        D["進入 Hold 佇列 (預設 HOLD 10 秒)"]
        E{"是否在 10 秒內<br/>收到收回請求？"}
        F["背景常駐精靈<br/>delayed_queue_daemon.py"]
        G["postsuper -d (佇列中強制刪除)"]
        H["postsuper -H (釋放佇列正常遞送)"]
    end

    subgraph Layer2 ["第二層：Dovecot Sieve 信箱強制抹除 (Layer 2: Mailbox Expunge)"]
        I["收件者信箱 (同網域)"]
        J["Sieve 全域過濾器<br/>(autoreply_handler.sieve / 90-recall.sieve)"]
        K{"觸發條件判斷<br/>1. Outlook 原生收回<br/>2. 主旨 #recall"}
        L["Sieve Pipe 腳本<br/>handle_recall.py"]
        M{"時效判定<br/>時差 <= 2 小時？"}
        N["doveadm expunge<br/>強制抹除信件 (無論已讀/未讀)"]
        O["拒絕抹除 (逾時記錄)"]
        P["靜默丟棄 (discard)<br/>徹底不打擾收件者"]
    end

    subgraph Report ["狀態回報 (Status Report)"]
        Q["產生四國語言報表<br/>(zh-TW / zh-CN / en / vi)"]
        R["寄送報告給原寄件者"]
    end

    A1 --> B
    A2 --> B
    B --> C
    B --> D
    D --> F
    F --> E
    E -- "是 (10s 內收回)" --> G
    G --> Q
    E -- "否 (超過 10s)" --> H
    H --> I

    %% 收回觸發流程
    S1["寄件者發動收回:<br/>1. Outlook 點擊「收回此郵件」<br/>2. Sent Items 回覆 #recall"]
    S1 --> J
    J --> K
    K -- "是" --> L
    L --> M
    M -- "符合時效 (<= 2h)" --> N
    M -- "已逾時 (> 2h)" --> O
    N --> P
    O --> P
    N --> Q
    O --> Q
    Q --> R
```

### 🎯 雙層核心運作原理

1. **第一層：出站佇列暫存緩衝 (Layer 1 Delay Buffer)**：
   - 凡透過認證 Port 587 (Submission) 或 Port 465 (SMTPS) 寄出的郵件，Postfix 會立即回應 `250 OK: queued` 給寄件者，並將郵件暫留於 Hold 佇列 `RECALL_DELAY_SECONDS`（預設 10 秒）。
   - 若寄件者在 10 秒內發起收回，系統透過 `postsuper -d` 直接在佇列中銷毀郵件，內部同仁與外部收件人皆不會收到任何信件。
   - 若 10 秒內未收回，背景精靈 `delayed_queue_daemon.py` 自動執行 `postsuper -H` 放行信件正常遞送。
   - **0 延遲旁路**：若管理者設定 `RECALL_DELAY_SECONDS=0`，系統自動切換為 direct bypass，出站信件直接即時發出，完全不進入 Hold 佇列。

2. **第二層：同網域信箱強制抹除 (Layer 2 Forced Expunge)**：
   - 當信件已送達同網域內部信箱，在 `RECALL_MAX_HOURS`（預設 2 小時）時限內發動收回，系統透過 `doveadm expunge` 鎖定 Message-ID 強制抹除該信件。
   - **已讀/未讀一律抹除**：無論收件者是否已開啟或點閱過（`SEEN`），信件一律自信箱中徹底移除。
   - **收回通知信徹底靜默**：系統自動攔截並丟棄 Outlook 產生的收回信（`discard`），收件者完全不會收到任何尷尬通知。
   - **時效逾期保護**：超過 2 小時之收回請求將被系統拒絕，且維持靜默不打擾收件者。
   - **外部收件者保護**：對已出站之外部收件人（如 Gmail 等），系統會攔截對外發送的收回通知，並於回報中提示外部信箱無法強制抹除。

### 📱 雙軌發動收回方式

| 用戶端環境 | 操作方式 | 辨識機制 |
| :--- | :--- | :--- |
| **PC 端 Microsoft Outlook** | 開啟已傳送信件，點選功能表「檔案」/「動作」➜ **「收回此郵件」** | 辨識 `X-MS-Exchange-Organization-Recall-Action` 標頭或 `Recall:`/`撤回:` 主旨 |
| **手機端 / Webmail (iOS, Android, 網頁郵件)** | 前往「寄件備份 (Sent Items)」，點擊該信件**回覆 (Reply)**，於**主旨開頭加上 `#recall`** 送出 | 透過 `In-Reply-To` / `References` 標頭鎖定原始 Message-ID |

### 🛠️ 容器內部參數調整指南 (`/etc/dovecot/recall.env`)

本功能之參數存於容器內部設定檔，網頁產生器維持乾淨不變。若需調整時限或關閉功能，管理者可隨時 `docker exec` 進入修改：

```bash
# 進入容器
docker exec -it mailserver vi /etc/dovecot/recall.env
```

檔案預設內容：
```ini
ENABLE_RECALL="yes"        # 是否啟用收回系統 (yes / no)
RECALL_DELAY_SECONDS=10    # 第一層佇列暫存秒數 (設為 0 代表直接直發，完全關閉暫存)
RECALL_MAX_HOURS=2         # 第二層同網域強制抹除有效時限 (小時)
```
修改存檔後，背景守護程式與 Sieve 腳本會**自動即時重新讀取生效**，無需重啟容器。

### 💡 通訊協定特性與注意事項 (POP3 vs IMAP)

- **IMAP / Webmail 用戶端**：雙向即時同步，伺服器執行 `doveadm expunge` 後，收件者螢幕上的信件會立即消失。
- **POP3 用戶端**：
  - 第一層 10 秒暫存期間，信件尚未進信箱，POP3 絕對收不到（100% 成功攔截）。
  - 若已超過暫存期且對方已使用 POP3 將信件收取下載至本地端電腦硬碟（.pst 檔案），伺服器端會抹除備份，但無法遠端刪除其電腦本機檔案（此時系統會在收回報告中向寄件者備註說明）。

