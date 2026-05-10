# Protocol v1 — Smart Robot Car Control Protocol

## 1. Mục đích
Tài liệu này định nghĩa giao thức giao tiếp chuẩn giữa:

- **Frontend React**
- **Backend FastAPI**
- **ESP32 firmware**

Protocol v1 được dùng cho:
- điều khiển thủ công
- telemetry
- assisted driving
- kiểm tra an toàn
- logging và debug

Mục tiêu của protocol này là:
- đơn giản
- dễ debug bằng serial monitor
- dễ parse ở backend
- ổn định để dùng cho toàn bộ giai đoạn baseline của đề tài

---

## 2. Phạm vi áp dụng

Protocol v1 áp dụng cho kênh:

- **Backend → ESP32** qua Serial
- **ESP32 → Backend** qua Serial

Frontend **không nói chuyện trực tiếp với ESP32**.  
Frontend chỉ gọi API/WebSocket của FastAPI.

---

## 3. Kiến trúc vai trò

### 3.1 Frontend
Chức năng:
- gửi lệnh điều khiển đến FastAPI
- hiển thị telemetry
- hiển thị camera / perception
- hiển thị mode, logs, mission state

### 3.2 Backend FastAPI
Chức năng:
- xác thực và giới hạn lệnh
- chuyển lệnh thành command serial
- parse telemetry / ACK / ERR
- log sự kiện
- thực thi safety rule
- làm cầu nối cho UI và các thành phần AI/CV về sau

### 3.3 ESP32
Chức năng:
- nhận command
- điều khiển motor / servo
- phản hồi ACK / ERR
- phát telemetry định kỳ
- thực thi watchdog / stop an toàn

---

## 4. Quy ước truyền thông

### 4.1 Transport
- Serial UART
- Baudrate mặc định: `115200`
- Encoding: `UTF-8`
- Mỗi command hoặc message nằm trên **một dòng**
- Ký tự kết thúc dòng: `\n`

### 4.2 Format chung
Mỗi dòng là một bản tin text, ví dụ:

```text
DRIVE 120 90
STOP
TEL MODE=MANUAL MOTOR=120 ANGLE=90 ESTOP=0 PCA=1 WD_MS=82 UPTIME=12000
ACK DRIVE
ERR INVALID_MODE