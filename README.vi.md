# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 Giới thiệu dự án
Đây là container Docker máy chủ Email Postfix hoàn chỉnh và tích hợp sẵn, hỗ trợ xác thực tài khoản qua Microsoft Active Directory (LDAP), bộ lọc thư rác Rspamd, quét virus ClamAV, chữ ký số OpenDKIM và quản lý hạn ngạch hòm thư (Quota).

- **Kho lưu trữ GitHub**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **Công cụ tạo cấu hình trực tuyến**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)
- **Kiến trúc hệ thống & Hướng dẫn kỹ thuật**: [ARCHITECTURE.vi.md](ARCHITECTURE.vi.md) | [Xem biểu đồ tương tác trực tuyến](https://williamfromtw.github.io/docker-Postfix-AD/architecture.html)

---

## 🚀 Tính năng nổi bật
- **Tài khoản đăng nhập độc lập với Email**: Tên đăng nhập có thể khác với địa chỉ email (ví dụ: tài khoản: `520001`, email: `william@smile.taipei`).
- **Xác thực Microsoft Active Directory LDAP**: Tương thích Windows Server 2008R2, 2012R2, 2016, 2019, 2022.
- **Postfix Mail Transfer Agent (MTA)**.
- **Máy chủ Dovecot IMAP / POP3 / LMTP**.
- **Tự động trả lời email thông minh (Auto-Reply / Vacation)**: Hỗ trợ thiết lập báo nghỉ phép và phản hồi tự động bằng lệnh email mà không cần giao diện Webmail.
- **OpenDKIM**: Ký và xác thực chữ ký số email.
- **Rspamd**: Bộ lọc thư rác hiệu suất cao với giao diện Web UI.
- **ClamAV**: Tích hợp quét mã độc/virus.
- **Hạn ngạch hòm thư (Quota)**: Mặc định 20GB (có thể tùy chỉnh).

---

## 🔌 Giao thức & Cổng kết nối (Ports)

| Giao thức | Cổng (Port) | Mã hóa |
| :--- | :--- | :--- |
| **SMTP** | `25` | Văn bản thuần / STARTTLS |
| **SMTPS** | `465` | SSL/TLS |
| **Submission** | `587` | STARTTLS |
| **POP3** | `110` | Văn bản thuần / STARTTLS |
| **POP3S** | `995` | SSL/TLS |
| **IMAP** | `143` | Văn bản thuần / STARTTLS |
| **IMAPS** | `993` | SSL/TLS |
| **ManageSieve** | `4190` | TLS |
| **Rspamd Web UI** | `11334` | HTTP (Khuyến nghị dùng Reverse Proxy) |

---

## ⚙️ Bắt đầu nhanh

### Cách 1: Sử dụng công cụ tạo trực tuyến (Khuyến nghị)
Truy cập [Công cụ tạo cấu hình trực tuyến (Online Generator)](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html) để tạo tệp `docker-compose.yaml` hoặc lệnh `docker run` nhanh chóng chỉ với một cú nhấp chuột.

---

### Cách 2: Sử dụng Docker Compose (`docker-compose.yaml`)

1. Tạo tệp `docker-compose.yaml`:

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

2. Khởi chạy dịch vụ:
```bash
docker compose up -d
```

---

### Cách 3: Sử dụng lệnh Docker CLI

1. Tạo các Volume lưu trữ:
```bash
docker volume create mailserver_vmail
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_log
docker volume create mailserver_opendkim
docker volume create mailserver_rspamd_conf
docker volume create mailserver_rspamd_var
```

2. Khởi chạy container:
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

## 🏛️ Hướng Dẫn Kỹ Thuật & Kiến Trúc Chuyên Sâu
Để tìm hiểu chi tiết về tích hợp Active Directory, quy trình lọc thư và hướng dẫn chứng chỉ Let's Encrypt / DKIM, vui lòng xem tài liệu **[Kiến trúc hệ thống (ARCHITECTURE.vi.md)](ARCHITECTURE.vi.md)**:
- **Quy tắc cấu hình Active Directory**: Quy tắc chữ thường, thuộc tính `mail`, bí danh `ALIASES`, giới hạn `local_only`.
- **Quy trình lọc thư & Bảo mật**: Luồng xử lý Postfix + Rspamd + ClamAV + OpenDKIM.
- **Kiến trúc chứng chỉ SSL/TLS**: Cơ chế tự tạo chứng chỉ tự ký (`make_fake_cert.sh`) và hướng dẫn Certbot DNS-01 trên Host.
- **Hướng dẫn DKIM & SPF**: Kích hoạt OpenDKIM, tạo khóa hàng loạt với `getOpenDKIM.sh`, bản ghi mẫu DNS TXT.
- **Chẩn đoán, tối ưu hiệu năng & Fail2ban**.

---

## 🛠️ Tự Build Image tại máy cục bộ
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:latest --no-cache .
```
