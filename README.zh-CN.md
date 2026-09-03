# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 项目简介
这是一个功能完整且经过整合的 Postfix 邮件服务器 Docker 容器，具备 Microsoft Active Directory (LDAP) 账号后端认证、Rspamd 垃圾邮件过滤、ClamAV 病毒扫描、OpenDKIM 数字签名以及邮箱配额 (Quota) 管理支持。

- **GitHub 项目库**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **在线配置生成器**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)
- **系统架构与运维指南**: [ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md) | [在线互动架构图](https://williamfromtw.github.io/docker-Postfix-AD/architecture.html)

---

## 🚀 主要特性
- **账号与邮箱可独立分离**：登录账号名称必须为纯账号/工号（`sAMAccountName` / `uid`，例如：账号 `520001`，邮箱 `william@smile.taipei`），严格禁止使用含 `@域名` 或 Email 地址登录。
- **Active Directory / OpenLDAP 认证**：默认采用标准 Port 389，支持配置 `ENABLE_LDAPS=true` 切换为 Port 636 (LDAPS TLS 加密)，兼容 Windows Server 2008R2~2025、NethServer 8、群晖 AD 与 OpenLDAP。
- **Postfix 邮件传输代理 (MTA)**。
- **Dovecot IMAP / POP3 / LMTP 服务器**。
- **Email 驱动智能自动回复 (Auto-Reply / Vacation)**：支持通过传统邮件指令或局域网独立 GPU Ollama 本地端 AI 口语设置休假/销假（支持简中、繁中、越文、英文），无 Webmail 亦可轻松使用。
- **OpenDKIM**：邮件数字签名与验证。
- **Rspamd**：高性能垃圾邮件过滤引擎与 Web 控制台。
- **ClamAV**：内置防病毒扫描。
- **邮箱配额限制 (Quota)**：默认 20GB（可灵活调整）。

---

## 🔌 支持协议与端口 (Ports)

| 通信协议 | 端口 (Port) | 加密方式 |
| :--- | :--- | :--- |
| **SMTP** | `25` | 明文 / STARTTLS |
| **SMTPS** | `465` | SSL/TLS |
| **Submission** | `587` | STARTTLS |
| **POP3** | `110` | 明文 / STARTTLS |
| **POP3S** | `995` | SSL/TLS |
| **IMAP** | `143` | 明文 / STARTTLS |
| **IMAPS** | `993` | SSL/TLS |
| **ManageSieve** | `4190` | TLS |
| **Rspamd Web UI** | `11334` | HTTP (建议配合反向代理使用) |

---

## ⚙️ 快速开始

### 方式一：使用在线生成器（强烈推荐）
访问 [在线配置生成器 (Online Generator)](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)，可以在浏览器中图形化填写并一键生成 `docker-compose.yaml` 或 `docker run` 命令。

---

### 方式二：使用 Docker Compose (`docker-compose.yaml`)

1. 创建 `docker-compose.yaml` 文件：

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
      # - OLLAMA_HOST=http://192.168.1.100:11434  # 局域网独立 GPU Ollama 服务器 (支持 4 语系口语请假)
      # - OLLAMA_MODEL=qwen2.5:7b
      # - OLLAMA_TIMEOUT=5
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

2. 启动服务：
```bash
docker compose up -d
```

#### 🤖 如何配置与更换 Ollama AI 模型 (Ollama Model Selection)
若欲启用口语请假或更换 AI 模型（例如切换为 `qwen2.5:7b`、`qwen2.5:3b`、`qwen3.6:27b-q8_0`），直接于 `docker-compose.yaml` 的 `environment` 调整以下参数即可生效（无需重新 Build 镜像）：

| 环境变量 | 默认值 | 说明与建议 |
| :--- | :--- | :--- |
| `OLLAMA_HOST` | *(未配置)* | Ollama 服务器端点，例如 `http://10.192.130.184:11434`。未配置则停用 AI 功能。 |
| `OLLAMA_MODEL` | `qwen2.5:7b` | **欲更换的模型名称**。可填入服务器已下载之模型（如 `qwen2.5:3b`、`qwen3.6:27b-q8_0`）。 |
| `OLLAMA_TIMEOUT` | `5` | AI 推理超时时间（秒）。若使用 27B 等超大模型或纯 CPU 运算，建议加大至 `60`~`180`。 |

**更换模型范例**：
```yaml
    environment:
      - OLLAMA_HOST=http://10.192.130.184:11434
      - OLLAMA_MODEL=qwen3.6:27b-q8_0   # <-- 直接在此填入欲使用的模型名称
      - OLLAMA_TIMEOUT=150             # 大模型推理耗时较长，调大超时保护避免 timeout
```
修改保存后，执行 `docker compose up -d` 即可立即套用新模型！

---

### 方式三：使用 Docker CLI 命令

1. 创建持久化 Volumes：
```bash
docker volume create mailserver_vmail
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_log
docker volume create mailserver_opendkim
docker volume create mailserver_rspamd_conf
docker volume create mailserver_rspamd_var
```

2. 启动容器：
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
  -e OLLAMA_HOST="http://192.168.1.100:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -e OLLAMA_TIMEOUT="5" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:latest
```

---

## 🛡️ Rspamd 邮件安全防护与 Web 控制台指南
如需了解 Rspamd 垃圾邮件过滤、Web 控制台操作（`http://<IP>:11334`，默认密码 `kafeiou.pw`）、零退信隔离（`SPAM_EMAIL` 救援）、黑白名单名册与危险附件过滤，请参阅专属性的 **[Rspamd 防护指南 (RSPAMD.zh-CN.md)](RSPAMD.zh-CN.md)**。

---

## 🏛️ 深度系统架构与技术运维指南
如需深入了解 Active Directory 整合细节、邮件安全过滤流程图与 DKIM/Let's Encrypt 配置手册，请参阅专属的 **[系统架构指南 (ARCHITECTURE.zh-CN.md)](ARCHITECTURE.zh-CN.md)**：
- **Active Directory LDAP 配置规范**：账号小写规范、`mail` 属性、`ALIASES` 组别名、`local_only` 限制。
- **邮件过滤与安全管道**：Postfix + Rspamd + ClamAV + OpenDKIM 处理流程。
- **SSL/TLS 证书架构**：测试自签证书自动补位机制 (`make_fake_cert.sh`) 与宿主机 Certbot DNS-01 申请教学。
- **DKIM & SPF 配置指南**：OpenDKIM 启用、`getOpenDKIM.sh` 批量多域名密钥生成、DNS TXT 记录模板。
- **排错、性能调优与 Fail2ban 实务**。

---

## 🛠️ 本地构建镜像
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:latest --no-cache .
```
