# ResearchPortal

Bộ khởi đầu để triển khai portal quản lý Kaggle/W&B và nghiên cứu. **Hiện là tài liệu + cấu hình mẫu, chưa có ứng dụng chạy được.** Source BHSD được giữ độc lập; không có credential/dataset/checkpoint thật trong bộ này.

## Bắt đầu

1. Đọc [hướng dẫn tác nhân](AGENTS.md) và [PoC-first](docs/design/poc-first.md).
2. Đọc [Kaggle operations](docs/design/kaggle-operations-spec.md) và [provider capabilities](docs/design/provider-capabilities.md).
3. Bắt đầu Streamlit + Python adapters, read-only/manual refresh; sau đó account editor, build preview và submit theo increment. Các stack cloud/full platform là lựa chọn mở rộng.
4. Dùng [settings mẫu](config/settings.example.toml) để cấu hình checkout BHSD và runtime root bên ngoài repo. Adapter/settings loader chưa triển khai.
5. Xem [implementation handoff](docs/IMPLEMENTATION.md) để triển khai xuyên suốt và [design index](docs/design/README.md) cho toàn bộ phân tích.

Source revision, hashes và trạng thái seed nằm trong [manifest](docs/source-manifest.json). Hướng dẫn BHSD được copy tại [reference index](docs/reference/bhsd/README.md); đây là snapshot tham khảo, không phải implementation của portal.
