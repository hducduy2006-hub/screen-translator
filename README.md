# ScreenLens Translate — Phần Mềm Dịch Trực Tiếp Trên Màn Hình

Phần mềm Windows giúp nhận diện chữ (OCR chạy cục bộ bằng ONNX Runtime) và dịch trực tiếp trên màn hình hỗ trợ đầy đủ **Tiếng Anh**, **Tiếng Việt (chuẩn dấu)**, **Tiếng Trung (Giản thể & Phồn thể)** cùng Tiếng Nhật và Tiếng Hàn.

## Tính năng nổi bật

- **Quét vùng & Dịch đè trực tiếp (`Alt + Q`)**: Kéo chọn bất kỳ vùng chữ nào trên trình duyệt, game, phim, truyện tranh, PDF hoặc ứng dụng khác. Bản dịch sẽ hiển thị gọn gàng đè trực tiếp lên vị trí chữ gốc (di chuột xem chữ gốc, nhấn chuột trái vào đoạn bất kỳ để sao chép, nhấn `Esc` hoặc chuột phải để đóng).
- **Dịch trực tiếp liên tục — Live Mode (`Alt + W`)**: Đặt khung màu xanh lên vùng phụ đề video, hội thoại game hoặc khung chat. Phần mềm tự động phát hiện khi nội dung thay đổi và dịch theo thời gian thực lên **Khung phụ đề nổi** (hỗ trợ chế độ **Xuyên chuột** để không cản thao tác) hoặc bật nút **Đè chữ** để dịch đè trực tiếp ngay trong khung quét.
- **Nhận diện OCR đa ngôn ngữ độ chính xác cao (Offline / Local)**:
  - **Tiếng Trung (Giản & Phồn) + Tiếng Nhật + Tiếng Anh**: RapidOCR PP-OCRv6.
  - **Tiếng Việt có dấu đầy đủ + Tiếng Anh**: VieSVTR v7 ONNX.
  - **Chế độ Tự động (Auto)**: Tự động phân loại từng dòng chữ, xử lý mượt ngay cả khi ảnh màn hình pha trộn đồng thời cả tiếng Anh, tiếng Việt và tiếng Trung.
- **Bảng kết quả, dịch nhập tay & lịch sử (`📋`)**: Xem lại tối đa 50 bản dịch gần nhất, chỉnh sửa văn bản OCR hoặc gõ trực tiếp để dịch nhanh.
- **Miễn phí dùng ngay**: Tích hợp sẵn Google Translate không cần API Key, đồng thời hỗ trợ tùy chọn **Gemini AI** trong phần Cài đặt (`⚙`) nếu bạn muốn dịch thông minh theo ngữ cảnh.

## Cách khởi chạy

- **Cách 1 (Không hiện cửa sổ dòng lệnh đen — Khuyên dùng)**: Nhấp đúp vào `Chay_Phan_Mem_Khong_Cua_So_Den.vbs`.
- **Cách 2 (Có cửa sổ log để theo dõi)**: Nhấp đúp vào `Chay_Phan_Mem.bat`.
- **Cách 3 (Qua dòng lệnh)**:
  ```powershell
  uv run python main.py
  ```

## Phím tắt toàn cục

| Phím tắt | Chức năng |
| --- | --- |
| `Alt + Q` | Quét vùng màn hình & dịch đè trực tiếp |
| `Alt + W` | Bật / Tắt chế độ Dịch trực tiếp liên tục (Live Mode) |
| `Alt + S` | Mở khóa chế độ xuyên chuột / Ẩn-Hiện lớp phủ hoặc thanh điều khiển |
| `Esc` | Hủy chọn vùng hoặc đóng nhanh lớp phủ dịch |
