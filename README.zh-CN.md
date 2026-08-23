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
- **微软 Active Directory LDAP 认证**：兼容 Windows Server 2008R2、2012R2、2016、2019、2022。
- **Postfix 邮件传输代理 (MTA)**。
- **Dovecot IMAP / POP3 / LMTP 服务器**。
- **Email 驱动智能自动回复 (Auto-Reply / Vacation)**：支持通过邮件指令设置休假与公出自动回复，无 Webmail 亦可轻松使用。
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

2. 启动服务：
```bash
docker compose up -d
```

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
  -e BIND_PW="your_bind_dn_password" \
  -e TZ="Asia/Taipei" \
  -e ENABLE_QUOTA="true" \
  -e SPAM_EMAIL="spam@test.com" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:latest
```

---

## 🏛️ 深度系统架构与技术运维指南
如需深入了解 Active Directory 配置细节、邮件安全过滤流程图与 DKIM/Let's Encrypt 设置手册，请参阅专属的 **[系统架构指南 (ARCHITECTURE.zh-CN.md)](ARCHITECTURE.zh-CN.md)**：
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
