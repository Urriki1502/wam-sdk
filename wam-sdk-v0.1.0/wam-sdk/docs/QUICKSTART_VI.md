# WAM SDK + ví dụ tích hợp

Bản 0.1.0 cung cấp SDK Python để ứng dụng nói chuyện với node WAM cục bộ.
SDK có API đọc node, số dư, tạo yêu cầu thanh toán, theo dõi xác nhận/reorg và
gửi coin có hạn mức. Mã nguồn, wheel cài offline, ví dụ, CI và báo cáo kiểm thử
nằm trong cùng gói.

## 1. Cài SDK

Yêu cầu Python 3.11 trở lên. Mở terminal tại thư mục giải nén:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-deps dist/wam_sdk-0.1.0-py3-none-any.whl
```

Trên PowerShell, dùng `.venv\Scripts\Activate.ps1` để kích hoạt môi trường.
Các ví dụ phải chạy từ bộ mã nguồn vì chúng không được đưa vào wheel.

## 2. Chạy thử trọn luồng mà không cần ví cá nhân

Trên Linux x86-64, tải bản daemon đã ghim checksum:

```sh
python scripts/fetch_release.py
python examples/regtest_checkout.py --wamd .tools/wamd --sha256 625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4
```

Nếu dùng Ubuntu 22.04, cài `libevent-2.1-7` và `libevent-pthreads-2.1-7` trước.
Ví dụ tự khởi động node regtest, tạo hai ví giả lập, đào coin thử, tạo yêu cầu
1.25 WAM, gửi và đào hai block xác nhận. Kết quả:

```json
{"network": "regtest", "before": "confirming", "after": "paid", "eligible_for_fulfillment": true}
```

Daemon và dữ liệu thử được dọn khi kết thúc bình thường. Regtest không có giá trị
tiền thật. Demo yêu cầu node ở trạng thái sẵn sàng trước khi gọi API ví của SDK.

## 3. Dùng với một node cục bộ đang chạy

Ví dụ cấu hình shell bên dưới dùng cổng và đường dẫn minh họa; thay bằng cấu hình
node của anh. Ví `merchant` phải đã tồn tại, được load và đồng bộ.

```sh
export WAM_RPC_URL='http://127.0.0.1:18443'
export WAM_NETWORK='regtest'
export WAM_COOKIE_FILE='/absolute/private/datadir/regtest/.cookie'
export WAM_WALLET='merchant'
python examples/read_node.py
python examples/create_payment_request.py --amount 1.25000001 --confirmations 2 --output request.json
python examples/check_payment.py --request request.json
```

`request.json` chứa địa chỉ, số tiền và ID; lưu trong thư mục riêng. Chương trình
tạo file mới, không ghi đè; trên POSIX quyền tạo là `0600`. Trên Windows cần quyền
ACL của thư mục phù hợp. Mỗi lần tạo request là một địa chỉ Taproot mới. SDK dùng
label rỗng để không đưa tên khách hàng/mã đơn vào metadata ví.

Ví dụ gửi tiền chỉ cho phép regtest, dùng ví người trả đã có coin thử:

```sh
export WAM_WALLET='payer'
python examples/send_regtest.py --request request.json --limit 2 --result send-result.json
```

Ví dụ tạo file kết quả trước khi gửi. Chạy lại với cùng file sẽ bị chặn trước
lệnh gửi; đổi tên file vẫn có thể tạo khoản gửi mới. Nếu file đang ở trạng thái
`pending_reconciliation`, bị ghi dở, hoặc lỗi là `mutation_outcome_unknown`, cần
đối soát ví trước khi quyết định gửi lại. Đây là biện pháp chống chạy nhầm đơn
giản, không phải cơ chế idempotency bền vững cho hệ thống thanh toán.

## 4. Tích hợp vào ứng dụng

```python
from wam_sdk import Amount, Config, PaymentTracker, WamClient

sdk = WamClient(Config.from_env(allow_new_addresses=True))
merchant = sdk.wallet("merchant")
request = merchant.create_request(Amount.from_wam("1.25000001"), confirmations=6)
# Lưu request.to_dict() vào cơ sở dữ liệu riêng, rồi hiển thị cho đúng khách hàng.

tracker = PaymentTracker(merchant, request)
receipt = tracker.refresh()
if tracker.eligible_for_fulfillment:
    pass  # Đánh dấu xử lý đơn nguyên tử trong DB trước khi giao hàng.
```

Tiền luôn nhập dưới dạng chuỗi hoặc số nguyên watoshi, không dùng `float`.
`receipt.paid` chỉ mô tả một lần quan sát. Tracker yêu cầu kết quả mới, ngừng cho
phép giao hàng khi polling lỗi và giữ cờ `needs_review` nếu khoản đã đủ xác nhận
sau đó không còn đủ. Tracker nằm trong RAM và không tự phục hồi trạng thái sau
restart; hệ thống thật phải lưu trạng thái đơn, các txid đã biết và cờ review.

SDK mặc định chỉ đọc. Muốn gửi phải cấu hình `send_limit=Amount.from_wam("...")`.
Hạn mức áp dụng cho số tiền mỗi lần gọi, chưa gồm phí; không phải tổng hạn mức
theo ngày và không phải giới hạn quyền RPC của daemon.

## 5. Ranh giới của bản này

Đã kiểm thử thực tế với WAM v0.1.11 trên regtest Linux. Khai báo chain/genesis
main/test có trong SDK, nhưng không có giao dịch mainnet/testnet trong báo cáo.
Bản này chưa phải chứng nhận an toàn production.

Privacy tập trung vào dữ liệu ứng dụng: không telemetry, không log RPC, không
redirect/proxy, mã lỗi cố định, báo cáo CI tối giản. Blockchain vẫn công khai.
Các phát hiện trước đó ở Watchtower/Core không được sửa bởi SDK; trường hợp
header lệch sau `reconsiderblock` được xử lý bằng cách tạm chặn thao tác.

Xem [API](API.md), [privacy](PRIVACY.md) và [bằng chứng kiểm thử](VALIDATION.md)
trước khi đưa vào luồng thanh toán vận hành thật.
