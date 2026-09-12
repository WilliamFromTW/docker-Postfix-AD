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
- **Tài khoản đăng nhập độc lập với Email**: Tên đăng nhập phải là tên tài khoản/mã nhân viên thuần túy (`sAMAccountName` / `uid`, ví dụ: tài khoản: `520001`, email: `william@smile.taipei`). Nghiêm cấm đăng nhập bằng địa chỉ email hoặc tên miền `@domain`.
- **Xác thực Active Directory / OpenLDAP**: Mặc định cổng 389, hỗ trợ tùy chọn `ENABLE_LDAPS=true` để mã hóa TLS qua cổng LDAPS 636. Tương thích Windows Server 2008R2~2025, NethServer 8, Synology AD, và OpenLDAP.
- **Postfix Mail Transfer Agent (MTA)**.
- **Máy chủ Dovecot IMAP / POP3 / LMTP**.
- **Tự động trả lời email thông minh (Auto-Reply / Vacation)**: Hỗ trợ thiết lập báo nghỉ phép và phản hồi tự động bằng lệnh email truyền thống hoặc ngôn ngữ tự nhiên qua Ollama AI cục bộ (4 ngôn ngữ: Tiếng Việt, Tiếng Anh, Tiếng Trung phồn thể/giản thể) mà không cần giao diện Webmail.
- **OpenDKIM**: Ký và xác thực chữ ký số email.
- **Rspamd**: Bộ lọc thư rác hiệu suất cao với giao diện Web UI.
- **ClamAV**: Tích hợp quét mã độc/virus.
- **Hạn ngạch hòm thư (Quota)**: Mặc định 50GB (hệ thống luôn bật, tự động gửi cảnh báo khi dung lượng vượt quá 95%, có thể tùy chỉnh linh hoạt).
- **Email chào mừng bản địa hóa khi đăng nhập lần đầu (First-Login Localized Welcome Email)**: Khi nhân viên mới đăng nhập lần đầu qua ứng dụng email (Outlook, Thunderbird, iOS, Android), hệ thống tự động đọc thuộc tính `preferredLanguage` trong Active Directory (hỗ trợ Tiếng Việt, Tiếng Trung phồn thể/giản thể, Tiếng Anh, Tiếng Pháp, Tiếng Đức, Tiếng Nhật, Tiếng Tây Ban Nha, dự phòng Tiếng Anh) để gửi thông số máy chủ, hạn ngạch dung lượng động và hướng dẫn cấu hình chi tiết vào Hộp thư đến (INBOX).

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
      - BIND_PW='your_bind_dn_password'
      - TZ=Asia/Taipei
      - SPAM_EMAIL=spam@test.com
      # - ALIASES=OU=aliases,DC=test,DC=com
      # - MY_NETWORKS=192.168.1.0/24
      # - OLLAMA_HOST=http://192.168.1.100:11434  # Máy chủ GPU Ollama LAN (hỗ trợ xin nghỉ phép bằng văn nói)
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

2. Khởi chạy dịch vụ:
```bash
docker compose up -d
```

#### 🤖 Cách Cấu Hình & Thay Đổi Mô Hình Ollama AI (Ollama Model Selection)
Nếu bạn muốn kích hoạt tính năng xin nghỉ bằng văn nói hoặc thay đổi mô hình AI (ví dụ: chuyển sang `qwen2.5:7b`, `qwen2.5:3b`, `qwen3.6:27b-q8_0`), chỉ cần chỉnh sửa các tham số sau trong phần `environment` của `docker-compose.yaml` (không cần rebuild image):

| Biến môi trường | Mặc định | Mô tả & Khuyến nghị |
| :--- | :--- | :--- |
| `OLLAMA_HOST` | *(Chưa cấu hình)* | Địa chỉ máy chủ Ollama, ví dụ: `http://10.192.130.184:11434`. Để trống sẽ tắt AI. |
| `OLLAMA_MODEL` | *(Chưa cấu hình / Tự phát hiện)* | **Tên mô hình muốn sử dụng** (ví dụ: `qwen3.8-200k:latest`, `qwen2.5:7b`). Không có giá trị mặc định cố định; nếu để trống hệ thống sẽ tự động phát hiện mô hình đang chạy hoặc có sẵn trên Ollama. |
| `OLLAMA_TIMEOUT` | `180` | Thời gian chờ suy luận AI (giây, mặc định: 180s). Nếu dùng GPU thường chỉ mất 3~5 giây, nếu chạy bằng CPU hoặc mô hình 27B+ nên giữ mặc định 180 giây. |

**Ví dụ cấu hình (`docker-compose.yaml`)**:
```yaml
    environment:
      - OLLAMA_HOST=http://10.192.130.184:11434
      - OLLAMA_MODEL=qwen3.8-200k:latest   # <-- Điền tên mô hình bạn muốn dùng tại đây
      - OLLAMA_TIMEOUT=180                # Bảo vệ timeout mặc định 180 giây
```
Sau khi lưu, chạy `docker compose up -d` để áp dụng ngay lập tức!

---

#### 📬 Email Chào Mừng Lần Đầu & Cấu Hình Ngôn Ngữ AD (Active Directory preferredLanguage)
Khi người dùng đăng nhập lần đầu tiên qua IMAP/POP3, hệ thống sẽ đọc thuộc tính `preferredLanguage` của tài khoản AD và tự động gửi email chào mừng bằng ngôn ngữ tương ứng (kèm thông số kết nối và hướng dẫn cài đặt Outlook, Thunderbird, iOS, Android) vào Hộp thư đến (INBOX).

**Bảng tra cứu cấu hình thuộc tính Active Directory `preferredLanguage`**:

| Ngôn ngữ mục tiêu | Giá trị chuẩn khuyến nghị | Giá trị tương thích (Không phân biệt hoa thường) | Tệp mẫu gửi đi |
| :--- | :--- | :--- | :--- |
| **Tiếng Việt** | `vi` | `vi-VN`, `vn` | `welcome.vi.eml` |
| **Tiếng Trung phồn thể** | `zh-TW` | `tw`, `zh-Hant`, `Hant`, `zh-HK` | `welcome.zh-TW.eml` |
| **Tiếng Trung giản thể** | `zh-CN` | `cn`, `zh-Hans`, `Hans`, `zh-SG` | `welcome.zh-CN.eml` |
| **Tiếng Anh** | `en` | `en-US`, `en-GB`, `eng` | `welcome.en.eml` |
| **Tiếng Pháp** | `fr` | `fr-FR`, `fra` | `welcome.fr.eml` |
| **Tiếng Đức** | `de` | `de-DE`, `deu`, `ger` | `welcome.de.eml` |
| **Tiếng Nhật** | `ja` | `ja-JP`, `jp`, `jpn` | `welcome.ja.eml` |
| **Tiếng Tây Ban Nha** | `es` | `es-ES`, `spa` | `welcome.es.eml` |
| **Chưa thiết lập / Để trống / Khác** | *(Để trống)* hoặc ví dụ `ko` | Bất kỳ mã ngôn ngữ nào chưa được hỗ trợ | **Tự động dùng Tiếng Anh dự phòng (`welcome.en.eml`)** |

> **💡 Các bước thiết lập cho Quản trị viên AD**:
> 1. Mở Windows Server **Active Directory Users and Computers** (`dsa.msc`).
> 2. Trên thanh menu trên cùng, chọn **View** ➔ tích chọn **Advanced Features**.
> 3. Nhấp đúp vào tài khoản người dùng ➔ chuyển sang tab **Attribute Editor**.
> 4. Tìm thuộc tính `preferredLanguage`, nhấp Edit, nhập mã ngôn ngữ mong muốn (ví dụ: `vi`, `en` hoặc `ja`) và nhấn lưu.

---

#### 💾 Hướng dẫn quản lý và tùy chỉnh dung lượng hộp thư (Mailbox Quota Management)
Hệ thống **mặc định luôn kích hoạt hạn ngạch dung lượng 50GB**, không cần thiết lập bất kỳ biến môi trường nào. Email được kiểm tra tức thì qua Dovecot Quota Policy (Port 12340) trong giai đoạn Postfix SMTP, tự động từ chối khi hòm thư đã đầy để bảo vệ an toàn ổ đĩa.

1. **Cách sửa đổi dung lượng hạn ngạch toàn cục**:
   Gắn kết (mount) hoặc chỉnh sửa trực tiếp tệp `/etc/dovecot/conf.d/90-quota.conf` (tương ứng với Volume `mailserver_dovecot` trên máy chủ):
   ```ini
   plugin {
     quota_rule = *:storage=100G  # Thay đổi 50G thành dung lượng bạn mong muốn (ví dụ: 100G, 20G)
   }
   ```
   Sau khi lưu, chạy lệnh sau trên máy chủ để áp dụng ngay lập tức (không cần khởi động lại container):
   ```bash
   docker exec -it mailserver doveadm reload
   ```

2. **Cách tra cứu dung lượng và hạn ngạch hiện tại của người dùng**:
   ```bash
   docker exec -it mailserver doveadm quota get -u william@smile.taipei
   ```
   Terminal sẽ hiển thị ngay lập tức dung lượng hiện đang sử dụng (KB), giới hạn hạn ngạch và phần trăm đã sử dụng.

3. **Cơ chế cảnh báo tức thì khi đạt 95% dung lượng**:
   Khi dung lượng hòm thư của nhân viên vượt ngưỡng **95%**, công cụ lưu trữ Dovecot sẽ **ngay lập tức kích hoạt sự kiện** để lưu email cảnh báo trực tiếp vào Hộp thư đến (INBOX), nhắc nhở người dùng dọn dẹp thư rác hoặc tệp đính kèm dung lượng lớn; hệ thống tích hợp sẵn **cơ chế làm nguội 90 ngày (3 tháng)** để tránh gửi cảnh báo lặp lại liên tục gây phiền toái cho người dùng.

---

### Cách 3: Sử dụng lệnh Docker CLI

1. Tạo các Volume lưu trữ:
```bash
docker volume create mailserver_vmail
docker volume create mailserver_opendkim
docker volume create mailserver_postfix
docker volume create mailserver_dovecot
docker volume create mailserver_welcome
docker volume create mailserver_rspamd_conf
docker volume create mailserver_rspamd_var
docker volume create mailserver_log
```

2. Khởi chạy container:
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
  -e SPAM_EMAIL="spam@test.com" \
  -e OLLAMA_HOST="http://192.168.1.100:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -e OLLAMA_TIMEOUT="180" \
  -d --restart always --net=host \
  inmethod/docker-postfix-ad:latest
```

---

## 🛡️ Hướng Dẫn Bảo Mật Rspamd & Web UI
Để biết chi tiết về lọc thư rác Rspamd, quản trị Web UI (`http://<IP>:11334`, mật khẩu mặc định: `kafeiou.pw`), cách ly Zero-Bounce (`SPAM_EMAIL`), danh sách trắng/đen và quét tệp đính kèm nén, vui lòng xem **[Hướng dẫn Rspamd (RSPAMD.vi.md)](RSPAMD.vi.md)**.

---

## 🏛️ Kiến Trúc Hệ Thống & Hướng Dẫn Kỹ Thuật
Để tìm hiểu sâu về tích hợp Active Directory, quy trình lọc thư và thiết lập DKIM/Let's Encrypt, vui lòng tham khảo **[Hướng dẫn Kiến trúc Hệ thống (ARCHITECTURE.vi.md)](ARCHITECTURE.vi.md)**:
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
