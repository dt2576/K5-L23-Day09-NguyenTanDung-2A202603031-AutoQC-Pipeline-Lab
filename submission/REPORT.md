# Báo cáo Day 09 — Nguyễn Tấn Dũng, 2A202603031

## 1. Kết luận trước

Pipeline xử lý 224 ảnh đầu vào, giữ lại 193 ảnh và loại 31 ảnh ở bước intake. Vòng QC đầu phát hiện 36 lỗi bắt buộc và 149 cảnh báo; AutoFix ghi 35 thao tác. Sau khi duyệt mô phỏng 80 ảnh, vòng cuối còn 0 lỗi bắt buộc nhưng có 34/193 ảnh còn cảnh báo (17,62%). Kết luận **Hold** vì vượt ngưỡng 10%; `clean_v1` chỉ được xuất làm bản nháp thử nghiệm, chưa phát hành.

## 2. Lỗi và phân việc

Thống kê theo **216 dòng lỗi/cảnh báo** trong `submission/reports/02_error_list_v1.csv`. Cột số lượng là số dòng báo cáo, không phải số ảnh khác nhau; phân việc là cách xử lý theo quy tắc pipeline, không có nghĩa mọi lỗi đều được sửa xong.

| Mã lỗi | Số dòng | Ai xử lý | Vì sao |
|---|---:|---|---|
| BAD_CLASS_ID | 6 | Máy | Xóa dòng có class ID sai |
| BAD_CLASS_NAME | 2 | Máy | Sửa tên lớp theo cấu hình |
| BAD_FORMAT | 3 | Máy | Xóa dòng sai định dạng |
| BAD_SIZE | 3 | Máy | Loại ảnh không đạt kích thước |
| BOX_HUGE | 3 | Người | Cần xem box có quá rộng so với vật không |
| BOX_OUT_OF_IMAGE | 8 | Máy | Cắt box về phạm vi ảnh; bỏ nếu box không còn diện tích |
| BOX_TINY | 6 | Người | Cần xác nhận vật thể nhỏ |
| BOX_ZERO | 4 | Máy | Xóa dòng box không có diện tích |
| CLASS_RARE | 4 | Người | Cần kiểm tra nhãn thuộc lớp hiếm |
| CORRUPT_IMAGE | 2 | Máy | Loại ảnh hỏng |
| DUP_BOX | 7 | Máy | Bỏ dòng box trùng |
| DUP_IMAGE_EXACT | 8 | Máy | Loại ảnh trùng hoàn toàn |
| DUP_IMAGE_NEAR | 7 | Máy | Loại ảnh nghi trùng gần theo quy tắc intake |
| EMPTY_LABEL | 11 | Người | Phân biệt ảnh nền với ảnh thiếu nhãn |
| LEAK_TEST | 11 | Máy | Loại ảnh rò rỉ sang tập test |
| MISSING_LABEL_FILE | 6 | Người | Không tự tạo nhãn khi chưa có file |
| POSSIBLE_FALSE_POS | 28 | Người | Kiểm tra nhãn có bị thừa không |
| POSSIBLE_LOOSE_BOX | 27 | Người | Kiểm tra box có ôm sát vật thể không |
| POSSIBLE_MISSING | 53 | Người | Kiểm tra vật bị bỏ sót |
| POSSIBLE_WRONG_CLASS | 17 | Người | Kiểm tra có nhầm lớp không |

`05_review_queue.csv` sắp ảnh theo điểm ưu tiên. `img_0020` đứng đầu (11.524) do có `FIXED_DROP_LINE`, `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS`; sáu ảnh thiếu nhãn được xếp tiếp theo với điểm 10. Với ngân sách 80 ảnh, hệ thống duyệt 80/121 ảnh (66,1%). Trong đó 74/80 ảnh có cảnh báo ngữ nghĩa: `POSSIBLE_MISSING` ở 51 ảnh, `POSSIBLE_WRONG_CLASS` ở 17, `POSSIBLE_FALSE_POS` ở 12 và `POSSIBLE_LOOSE_BOX` ở 8. Các số có thể chồng nhau vì một ảnh mang nhiều mã; đây không phải số lỗi thực sự đã được xác nhận.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 16 | DUP_IMAGE_NEAR: 1.00 / 0.50 → 1.00 / 0.83 | Tìm được thêm ảnh gần trùng, không tăng FP trên tập calibration |
| `second_opinion.conf` | 0.25 | 0.60 | POSSIBLE_MISSING: 0.50 / 1.00 → 0.57 / 1.00 | Giảm cảnh báo sai nhưng vẫn bắt đủ 8/8 lỗi thiếu nhãn của tập calibration |

Ở ngưỡng pHash 16, F1 của `DUP_IMAGE_NEAR` tăng từ 0.67 lên 0.91. Với confidence 0.60, `POSSIBLE_WRONG_CLASS` tăng Precision từ 0.56 lên 0.62, Recall giữ ở 0.83. Tuy nhiên, calibration vẫn có thể gây hiểu nhầm: `POSSIBLE_FALSE_POS` đạt Recall 1.00 nhưng có 11 FP so với 5 TP (Precision 0.31). Khi thử `phash_dist = 20`, Recall `DUP_IMAGE_NEAR` lại giảm còn 0.50. Vì vậy, không thể chỉ nhìn Recall hoặc cho rằng tăng ngưỡng luôn tốt hơn.

## 4. Cửa chặn và điều pipeline không bắt được

Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: sau AutoFix vẫn còn 6 lỗi bắt buộc, không có người duyệt, Gate kết luận **Rework**; mã thoát **20** và không có thư mục `work/exp_nb`. Khi cho duyệt 80 ảnh, vòng cuối có 0 ERROR nhưng còn 34/193 ảnh cảnh báo nên kết luận **Hold**. Hai kết quả cho thấy Gate không cho phát hành khi chưa đạt điều kiện.

Hai hạn chế được thấy trên calibration: (1) `POSSIBLE_LOOSE_BOX` ở cấu hình ban đầu chỉ phát hiện 2/5 lỗi (Recall 0.40), nên có thể bỏ sót box chưa khít; (2) `POSSIBLE_FALSE_POS` có 11 cảnh báo sai/16 cảnh báo, khiến người duyệt phải kiểm tra thêm. Đây là kết quả đo trên tập calibration, chưa phải ví dụ được xác nhận qua xem từng ảnh.

## 5. Train: raw vs clean

Đã chạy **2 seed mỗi biến thể**; số liệu lấy từ `submission/results/comparison.md` và lệnh `python scripts/summarize_results.py`. Sử dụng model YOLO26n (yolo26n.pt), huấn luyện 20 epoch cho mỗi lần chạy. Thực hiện trên hai bộ dữ liệu Raw (224 ảnh) và Clean (193 ảnh), mỗi bộ chạy hai seed là 0 và 1. Tổng cộng có 4 lượt huấn luyện

| Biến thể | Số ảnh train | Seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | Precision (TB ± độ lệch) | Recall (TB ± độ lệch) |
|---|---:|---:|---:|---:|---:|---:|
| Raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| Clean | 193 | 2 | 0.729 ± 0.002 | 0.500 ± 0.000 | 0.794 ± 0.028 | 0.619 ± 0.005 |

Script tổng hợp báo chênh mAP50 (Clean − Raw) **+0.004** (chênh theo số làm tròn trong bảng là +0.003). Chênh lệch rất nhỏ, gần mức biến động giữa các seed; trong khi đó mAP50-95 giảm 0.012 và Recall giảm 0.030. Vì vậy, chưa có cơ sở khẳng định Clean tốt hơn Raw. Có thể do (1) Clean chỉ còn 193 so với 224 ảnh nên mất cả dữ liệu có ích; cần kiểm tra các ảnh bị loại và thử cân bằng lượng ảnh train; (2) bản Clean vẫn Hold với 34 ảnh cảnh báo nên chưa sạch hết; cần duyệt tiếp và train lại. Số seed còn ít, nên kết quả chỉ là tham khảo trong bài lab.

## 6. Quyết định và ghi chú AI

Quyết định cuối là **Hold**. Muốn Release cần kiểm tra tiếp các ảnh còn cảnh báo, bổ sung/sửa nhãn thực sự sai, chạy lại QC và xác nhận không còn ERROR, tỷ lệ ảnh cảnh báo còn lại dưới ngưỡng 10%; không tự tăng ngưỡng chỉ để đạt Release.

Có dùng ChatGPT để tham khảo cách viết các module QC và lệnh chạy. Đã kiểm code bằng `pytest` (79/79 passed), chạy calibration, pipeline và phép thử Gate không có người duyệt. Một lần hướng dẫn AI dự kiến `gate.py` có 9 test, nhưng repo thực tế có 10 test; đã kiểm tra lại bằng pytest. 
