# Docker-Postfix-AD

🌐 **Language / 語言 / Ngôn ngữ**:  
[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [Tiếng Việt](README.vi.md)

---

## 📌 Giới thiệu dự án
Đây là container Docker máy chủ Email Postfix hoàn chỉnh và tích hợp sẵn, hỗ trợ xác thực tài khoản qua Microsoft Active Directory (LDAP), bộ lọc thư rác Rspamd, quét virus ClamAV, chữ ký số OpenDKIM và quản lý hạn ngạch hòm thư (Quota).

- **Kho lưu trữ GitHub**: [https://github.com/WilliamFromTW/docker-Postfix-AD](https://github.com/WilliamFromTW/docker-Postfix-AD)
- **Công cụ tạo cấu hình trực tuyến**: [https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html](https://williamfromtw.github.io/docker-Postfix-AD/genLaunchCommand.html)

---

## 🚀 Tính năng nổi bật
- **Tài khoản đăng nhập độc lập với Email**: Tên đăng nhập có thể khác với địa chỉ email (ví dụ: tài khoản: `520001`, email: `william@smile.taipei`).
- **Xác thực Microsoft Active Directory LDAP**: Tương thích Windows Server 2008R2, 2012R2, 2016, 2019, 2022.
- **Postfix Mail Transfer Agent (MTA)**.
- **Máy chủ Dovecot IMAP / POP3**.
- **OpenDKIM**: Ký và xác thực chữ ký số email.
- **Rspamd**: Bộ lọc thư rác hiệu suất cao với giao diện Web UI.
- **ClamAV**: Tích hợp quét mã độc/virus.
- **Hạn ngạch hòm thư (Quota)**: Mặc định 20GB (có thể tùy chỉnh).
- **Hệ điều hành nền tảng**: Rocky Linux.

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

## 📋 Yêu cầu chuẩn bị
- Đảm bảo chứng chỉ Let's Encrypt đã được thiết lập sẵn trên **máy chủ Docker Host** (không phải bên trong container).
- Ánh xạ thư mục `/etc/letsencrypt` từ máy chủ vào `/etc/letsencrypt` của container.

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
  inmethod/docker-postfix-ad:4.0b1
```

---

## 🛡️ Giao diện Web bộ lọc thư rác Rspamd
- **Truy cập Web UI**: `http://<IP-may-chu>:11334` (Khuyến nghị dùng Reverse Proxy với chứng chỉ SSL).
- **Mật khẩu mặc định**: `kafeiou.pw`
- **Đổi mật khẩu quản trị viên**:
  1. Tạo mã băm mật khẩu trong container:
     ```bash
     docker exec -it mailserver rspamadm pw --encrypt -p <mat_khau_moi>
     ```
  2. Cập nhật chuỗi băm vào tệp `/etc/rspamd/local.d/worker-controller.inc`.

---

## 🔑 Kích hoạt chữ ký số OpenDKIM
1. Bỏ chú thích cấu hình milter trong `/etc/postfix/main.cf`:
   ```text
   smtpd_milters = inet:127.0.0.1:8891
   non_smtpd_milters = $smtpd_milters
   milter_default_action = accept
   ```
2. Thêm khóa công khai từ `/etc/opendkim/keys/default.txt` vào bản ghi DNS TXT của tên miền.
3. Chỉnh sửa tham số `domains` trong `/getOpenDKIM.sh` nếu cần tạo nhiều tên miền DKIM.

---

## 🏢 Hướng dẫn thiết lập Active Directory (AD)
- **Quy tắc chữ thường**: Tên tài khoản đăng nhập trong AD bắt buộc phải viết bằng **chữ thường** (Dovecot luôn truy vấn bằng chữ thường).
- **Thuộc tính Email**: Nhập địa chỉ email vào thuộc tính `mail` của User hoặc Group trong AD.
- **Bí danh nhóm (Aliases)**: Tạo Group và điền địa chỉ email bí danh vào thuộc tính `mail`, sau đó thêm các tài khoản thành viên vào nhóm.
- **Chỉ gửi nhận nội bộ (local_only)**: Đặt thuộc tính `description` của User hoặc Group thành `local_only` để giới hạn chỉ liên lạc trong nội bộ tên miền.

---

## 🔍 Kiểm tra dịch vụ & Khắc phục sự cố
1. Truy cập vào bên trong container:
   ```bash
   docker exec -it mailserver bash
   ```
2. Kiểm tra trạng thái các tiến trình dịch vụ:
   ```bash
   supervisorctl status
   ```
3. Kiểm tra cổng mạng bằng telnet/nc:
   ```bash
   telnet localhost 25    # Postfix SMTP
   telnet localhost 143   # Dovecot IMAP
   telnet localhost 8891  # OpenDKIM
   telnet localhost 11334 # Rspamd
   ```

---

## 🛠️ Tự Build Image tại máy cục bộ
```bash
git clone https://github.com/WilliamFromTW/docker-Postfix-AD.git
cd docker-Postfix-AD
docker build -t inmethod/docker-postfix-ad:4.0b1 --no-cache .
```
