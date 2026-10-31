# ResearchPortal

Portal cá nhân theo phiên cho Kaggle/W&B, dùng **Streamlit + Python worker**. Đã có luồng fixture Accounts → Monitor → Build preview → Submit mô phỏng, cùng adapter live và operation ledger. Training vẫn thuộc checkout BHSD độc lập.

**Trạng thái kiểm chứng:** xem [implementation status](docs/IMPLEMENTATION.md). Kiểm thử offline không chứng minh tương thích online. Live submit mặc định tắt; bản này chưa nghiệm thu vận hành online.

## Cài đặt và chạy

Dùng Python 3.11 trong môi trường riêng, không cài requirements training BHSD:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

Ở terminal thứ hai, cùng môi trường và cấu hình:

```bash
source .venv/bin/activate
python -m research_portal.worker
```

Mở `http://127.0.0.1:8501`. Mặc định **fixture**, có hai connection demo và một notebook. Bấm **Check now**, đợi worker rồi **Refresh stored results**. Có thể build và submit mô phỏng không cần credential/network/GPU. Slug demo `queued`, `complete`, `failed`, `network-error`, `forbidden`, `rate-limited` chọn các tình huống tương ứng.

UI không gọi provider khi render. Worker chỉ xử lý thao tác đã enqueue; không tự polling provider. Ctrl+C dừng worker/UI. Khi worker dừng, UI vẫn đọc cache; không có cam kết đồng bộ sau khi kết thúc phiên.

## Cấu hình live

Copy `config/settings.example.toml` thành `config/settings.toml` (đã gitignore), rồi:

1. Đặt `runtime.root` vào thư mục riêng, bền vững **ngoài repo**, trên filesystem local đã kiểm chứng locking. Đặt `local_filesystem_confirmed=true` khi đã kiểm tra.
2. Cấu hình checkout BHSD và full commit SHA; source liên quan phải khớp commit. Đặt `mode="live"`; giữ `allow_live_submit=false` để bắt đầu chỉ đọc.
3. Tạo connection trong Accounts: Kaggle dùng username/legacy API key; W&B dùng entity/API key. Test connection và attach notebook bằng full references. Không nhập credential qua command args.
4. Mean Teacher hỗ trợ multiclass/binary và resume. Build không push. Chế độ online notebook dùng Kaggle Secret tên `WANDB_API_KEY`, được operator gắn trên Kaggle; portal không nhúng key vào notebook. Nguồn training phải clone được từ Kaggle; private Git authentication chưa hỗ trợ.
5. Chỉ bật `allow_live_submit=true` khi đã nghiệm thu, có chủ đích chạy training và đã xem preview. UI yêu cầu xác nhận account/dataset/source/options trước mỗi submit.

Có thể override `RESEARCH_PORTAL_SETTINGS`, `RESEARCH_PORTAL_MODE`, `RESEARCH_PORTAL_RUNTIME`; UI/worker phải dùng cùng giá trị. Fixture và live tách account/operations theo mode. Demo mặc định dùng thư mục private trong temporary storage, không dùng nó làm nơi lưu dữ liệu live duy nhất.

Kaggle status là latest-version/unverified nếu chưa xác định được version. Tracking heartbeat, iteration progress và kết quả training hiển thị riêng. Không có W&B vẫn dùng được Kaggle monitor/submit mới; resume cần W&B online. PICK, quota, log-follow, auto-poll và multi-user chưa hỗ trợ.

## Kiểm tra và dependency lock

```bash
python -m pytest -q
python -m research_portal.maintenance doctor
python tools/verify_environment.py
```

Script cuối kiểm tra đúng phiên bản, `pip check`, chạy tests rồi mới tạo `requirements.lock` chứa toàn bộ phiên bản đã cài. Trong môi trường hiện tại chưa tải được Streamlit/pytest do DNS/network, vì vậy chưa có lockfile đã kiểm chứng và AppTest chưa chạy. Sau khi có lock, dùng `python -m pip install -r requirements.lock` để tái lập môi trường.

Kiểm thử lõi khi chưa có pytest: `python -m unittest discover -s tests -v`. AppTest được đánh dấu skip nếu chưa có Streamlit. Test source BHSD chạy offline khi checkout/PyYAML có sẵn, không thực thi notebook/training.

## Recovery và backup

Timeout sau dispatch chuyển submission sang `unknown`, giữ khóa đích; restart không push lại. Trong Operations, đọc remote evidence, kiểm tra version/source trên Kaggle rồi ghi kết luận operator. Latest slug status không đủ xác nhận submission. Kết luận `not_sent` chỉ giải phóng khóa; muốn thử lại phải tạo preview mới.

Dừng UI và worker trước maintenance. Backup chứa credential, chỉ lưu trong storage riêng có quyền hạn chế:

```bash
python -m research_portal.maintenance backup /private/storage/portal-backup
python -m research_portal.maintenance cleanup-secrets
```

Restore vào runtime **chưa tồn tại**, cấu hình bằng `RESEARCH_PORTAL_RUNTIME`:

```bash
RESEARCH_PORTAL_RUNTIME=/private/storage/restored-portal python -m research_portal.maintenance restore /private/storage/portal-backup
```

Backup gồm SQLite, credentials đang được tham chiếu và preview bundles, có checksums; không gồm dataset/checkpoints. Restore giữ fence cho operations đã dispatch. Cleanup chỉ xóa credential files không còn được metadata tham chiếu, sau khi các phiên đã dừng. Giữ thêm bản backup ngoài host theo chính sách của đơn vị.

## Cấu trúc và tài liệu

- `app.py`: UI; `research_portal/`: workflows, storage, worker, providers và BHSD bridge.
- `tests/`: synthetic contracts và Streamlit AppTest; `tools/`: kiểm chứng môi trường.
- `config/`: settings mẫu; `docs/design/`: đặc tả; `docs/reference/bhsd/`: snapshot hướng dẫn training.
- [PoC-first](docs/design/poc-first.md), [Kaggle operations](docs/design/kaggle-operations-spec.md), [provider capabilities](docs/design/provider-capabilities.md).

`docs/source-manifest.json` và `docs/seed-checksums.json` ghi nguồn **seed ban đầu**, không phải checksums của implementation hiện tại. `AGENTS.md` được giữ nguyên. Chỉ bind loopback; truy cập HPC qua cơ chế đơn vị cho phép. Không có public hosting, application login hay quyền chạy daemon thường trực được cấp kèm repo này.
