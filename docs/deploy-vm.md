# Hướng dẫn Triển khai Hệ thống Whybi AI lên Máy ảo VM (C2-04)

> Tài liệu hướng dẫn thiết lập hạ tầng máy ảo (VM), cấu hình Nginx TLS/HTTPS, nâng cấp WebSocket, quản lý nhật ký JSON tập trung và thiết lập tự động hóa CI/CD qua GitHub Actions (theo mục 5.7, 7.1; NFR-07, NFR-10).

---

## 1. Tổng quan Kiến trúc Triển khai

Trên máy chủ VM chạy Linux (Ubuntu 22.04 LTS / 24.04 LTS), hệ thống Whybi AI được đóng gói thành các dịch vụ Docker và điều phối bằng Docker Compose:

```
[ Người dùng / Trình duyệt ]
            │
    (Cổng 80: HTTP ──> 301 Redirect)
    (Cổng 443: HTTPS / TLS 1.3 / WSS)
            ▼
     [ Nginx Reverse Proxy ]
     ├── Cấp SSL/TLS bằng Let's Encrypt (Certbot)
     ├── Nâng cấp giao thức WebSockets (/ws, /api/v1/sessions/.../ws)
     ├── Cân bằng tải & phân phối tĩnh Frontend (SPA React)
     └── Định tuyến API (/api/v1/*) sang Backend FastAPI
            │
     [ Backend FastAPI ] ──> [ Redis Pub/Sub & Cache ]
            │                   │
            ▼                   ▼
    [ PostgreSQL + pgvector ] [ Celery Workers (Trích xuất & Tổng hợp) ]
```

---

## 2. Chuẩn bị Máy ảo VM

### 2.1. Cài đặt Docker & Docker Compose
```bash
# Cập nhật package index
sudo apt update && sudo apt upgrade -y

# Cài đặt Docker Engine
sudo apt install -y ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Cấp quyền cho user hiện tại (ví dụ: ubuntu)
sudo usermod -aG docker $USER
newgrp docker
```

### 2.2. Cấu hình Firewall (UFW)
Mở các cổng cần thiết cho web và SSH:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 3. Cấu hình Chứng chỉ SSL/TLS (HTTPS)

### 3.1. Trỏ tên miền về IP của VM
Tạo bản ghi DNS A trỏ tên miền (ví dụ: `whybi.sgu.edu.vn` hoặc `whybi.example.com`) về địa chỉ IP công khai của VM.

### 3.2. Cấp chứng chỉ bằng Let's Encrypt Certbot
```bash
sudo apt install -y certbot

# Chạy standalone khi stack chưa chiếm cổng 80:
sudo certbot certonly --standalone -d <DOMAIN>
# Ví dụ: sudo certbot certonly --standalone -d whybi.example.com
```

Chứng chỉ sẽ được lưu tại `/etc/letsencrypt/live/<DOMAIN>/`.

### 3.3. Tự động gia hạn chứng chỉ
Thêm hook để Nginx tạm giải phóng cổng 80 trong vài giây khi Certbot gia hạn:
```bash
sudo certbot renew --dry-run
```
Cấu hình hook trong `/etc/letsencrypt/cli.ini` hoặc lệnh cron:
```bash
sudo certbot renew \
  --pre-hook "docker compose -f ~/whybi-ai/docker-compose.yml -f ~/whybi-ai/docker-compose.tls.yml stop nginx" \
  --post-hook "docker compose -f ~/whybi-ai/docker-compose.yml -f ~/whybi-ai/docker-compose.tls.yml start nginx"
```

---

## 4. Thiết lập Repo và Môi trường trên VM

### 4.1. Clone repo về thư mục người dùng
```bash
cd ~
git clone https://github.com/dangpham-work/whybi-ai.git
cd ~/whybi-ai
```

### 4.2. Cấu hình file `.env`
Tạo file `.env` trên VM từ `.env.example`:
```bash
cp .env.example .env
```
Cập nhật các biến quan trọng:
```env
# Môi trường chạy
APP_ENV=production
DEBUG=false
DEMO_MODE=0
LLM_MODE=real

# Cấu hình HTTPS & Tên miền
DOMAIN=whybi.example.com
COMPOSE_FILE=docker-compose.yml:docker-compose.tls.yml

# Bảo mật JWT (BẮT BUỘC sinh khóa ngẫu nhiên dài ít nhất 32 ký tự)
# Lệnh sinh: openssl rand -hex 32
JWT_SECRET=c1f4e8b39a475d2903847291aebdc49103948572019384729103948572910394
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Cơ sở dữ liệu PostgreSQL & Redis
POSTGRES_DB=whybi
POSTGRES_USER=whybi
POSTGRES_PASSWORD=<MAT_KHAU_MANH_CHO_DB>
DATABASE_URL=postgresql+asyncpg://whybi:<MAT_KHAU_MANH_CHO_DB>@postgres:5432/whybi
REDIS_URL=redis://redis:6379/0

# Cổng AI & Model (Gemini / Claude / OpenAI)
GEMINI_API_KEY=<KHOA_GEMINI_THAT>
AI_PRIMARY_MODEL=gemini-2.5-flash
AI_FALLBACK_MODEL=gemini-1.5-flash
```

### 4.3. Chạy stack lần đầu
```bash
docker compose up -d --build
docker compose ps
curl -fsS http://localhost/health
```

---

## 5. Tự động hóa CI/CD với GitHub Actions

Hệ thống đã có sẵn 2 workflow triển khai và theo dõi:

### 5.1. Workflow Triển khai Tự động (`.github/workflows/deploy.yml`)
Khi một Pull Request được merge vào nhánh `main`, GitHub Actions sẽ tự động SSH vào VM, kéo mã nguồn mới nhất, build lại containers và kiểm tra `/health`.

Cấu hình Secrets trong repo GitHub (`Settings -> Secrets and variables -> Actions -> Secrets`):
- `VM_HOST`: Địa chỉ IP công khai hoặc hostname của VM (vd: `203.0.113.10`).
- `VM_USER`: Tên tài khoản SSH trên VM (vd: `ubuntu`).
- `VM_SSH_KEY`: Private SSH Key (OpenSSH format) có quyền đăng nhập vào VM.

Cấu hình Variables trong repo GitHub (`Settings -> Secrets and variables -> Actions -> Variables`):
- `PUBLIC_URL`: URL công khai của hệ thống có HTTPS (vd: `https://whybi.example.com`).

### 5.2. Workflow Theo dõi Uptime (`.github/workflows/uptime.yml`)
- Tự động chạy mỗi 5 phút (`*/5 * * * *`).
- Gửi HTTP GET request tới `${PUBLIC_URL}/health`.
- Nếu endpoint trả về mã lỗi hoặc timeout quá 15 giây, workflow sẽ báo đỏ và GitHub sẽ lập tức gửi email cảnh báo cho đội ngũ quản trị.

---

## 6. Nhật Ký JSON Tập Trung (Centralized JSON Logging)

Theo yêu cầu mục 5.7 và NFR-07:
- Mọi service backend xuất log dưới định dạng JSON chuẩn qua `backend/app/core/logging.py` (`JsonFormatter`).
- Các trường chuẩn bao gồm: `timestamp`, `level`, `logger`, `message`, `module`, `latency_ms` (đối với các lời gọi LLM / STT).
- Dễ dàng tích hợp với các công cụ thu thập log tập trung như Vector, Fluentbit, Grafana Loki hoặc ELK Stack:
```bash
# Xem log thời gian thực của backend
docker compose logs -f api
```
Ví dụ cấu trúc bản ghi log:
```json
{
  "timestamp": "2026-11-05T22:15:00.123456Z",
  "level": "INFO",
  "logger": "app.services.session_orchestrator",
  "message": "Turn processed successfully",
  "latency_ms": 842.5,
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "turn_type": "ANSWER"
}
```

---

## 7. Kiểm tra và Nghiệm thu Hệ thống

Sau khi triển khai thành công, các kiểm tra sau phải có kết quả đạt:

1. **HTTP sang HTTPS redirect:**
   ```bash
   curl -I http://whybi.example.com/
   # Kết quả: HTTP/1.1 301 Moved Permanently
   # Location: https://whybi.example.com/
   ```
2. **Endpoint `/health` công khai:**
   ```bash
   curl -fsS https://whybi.example.com/health
   # Kết quả trả về JSON: {"status":"ok","app":"whybi-ai"}
   ```
3. **Nâng cấp kết nối WebSocket:**
   ```bash
   wscat -c "wss://whybi.example.com/ws?token=<VALID_TOKEN>"
   # Kết nối thành công, nhận chào mừng và lắng nghe sự kiện Redis
   ```
4. **HSTS Header:**
   Phản hồi từ cổng 443 luôn kèm `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
