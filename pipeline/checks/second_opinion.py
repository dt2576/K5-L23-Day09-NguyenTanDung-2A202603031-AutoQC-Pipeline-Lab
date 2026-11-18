"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""

from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    settings = cfg["second_opinion"]

    conf = settings["conf"]
    min_area_px = settings["min_area_px"]
    fp_conf = settings["fp_conf"]
    iou_missing = settings["iou_missing"]
    iou_match = settings["iou_match"]
    iou_loose = settings["iou_loose"]

    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []

    for image_path in ds.image_files():
        stem = image_path.stem

        # Không có dự đoán hoặc chưa có file nhãn:
        # module khác sẽ phụ trách kiểm tra.
        if stem not in preds:
            continue

        label_lines = ds.read_label_lines(stem)
        if label_lines is None:
            continue

        size = ds.image_size(stem)
        if size is None:
            continue

        image_w, image_h = size

        # Đọc nhãn hợp lệ và giữ số dòng gốc.
        labels = []

        for line_no, text in label_lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except (ValueError, OverflowError):
                continue

            if not 0 <= cls < len(ds.classes):
                continue

            labels.append(
                (line_no, cls, (cx, cy, w, h))
            )

        all_preds = preds[stem]

        # 1. Kiểm tra các dự đoán có độ tin cậy
        # và diện tích đạt ngưỡng.
        for prediction in all_preds:
            pred_class, score, cx, cy, w, h = prediction
            pred_box = (cx, cy, w, h)

            area_px = w * image_w * h * image_h

            if score < conf or area_px < min_area_px:
                continue

            # Tìm tất cả nhãn có IoU đủ lớn.
            candidates = []

            for line_no, cls, label_box in labels:
                overlap = iou_xywh(pred_box, label_box)

                if overlap >= iou_missing:
                    candidates.append(
                        (cls, overlap)
                    )

            # Trường hợp 1: Model thấy vật,
            # nhưng không có nhãn tương ứng.
            if not candidates:
                issues.append(Issue(
                    "second_opinion",
                    WARN,
                    "POSSIBLE_MISSING",
                    stem,
                    "AI phát hiện vật thể có thể chưa được gán nhãn",
                    extra={
                        "conf": score,
                        "class_id": pred_class
                    }
                ))
                continue

            # Tìm nhãn cùng class.
            same_class = [
                overlap
                for cls, overlap in candidates
                if cls == pred_class
            ]

            # Trường hợp 2: Có nhãn cùng class.
            if same_class:
                best_iou = max(same_class)

                if best_iou < iou_loose:
                    issues.append(Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_LOOSE_BOX",
                        stem,
                        "Bounding Box có thể chưa khít vật thể",
                        extra={
                            "conf": score,
                            "iou": best_iou
                        }
                    ))

                # Nhãn cùng class được ưu tiên,
                # không xét WRONG_CLASS nữa.
                continue

            # Trường hợp 3: Chỉ có nhãn khác class.
            best_iou = max(
                overlap
                for cls, overlap in candidates
            )

            if best_iou >= iou_match:
                issues.append(Issue(
                    "second_opinion",
                    WARN,
                    "POSSIBLE_WRONG_CLASS",
                    stem,
                    "AI và nhãn có thể không cùng class",
                    extra={
                        "conf": score,
                        "iou": best_iou,
                        "class_id": pred_class
                    }
                ))

        # 2. Kiểm tra nhãn có thể là False Positive.
        # Phần này dùng fp_conf và KHÔNG lọc diện tích.
        fp_predictions = [
            (p[2], p[3], p[4], p[5])
            for p in all_preds
            if p[1] >= fp_conf
        ]

        for line_no, cls, label_box in labels:
            matched = any(
                iou_xywh(label_box, pred_box)
                >= iou_missing
                for pred_box in fp_predictions
            )

            if not matched:
                issues.append(Issue(
                    "second_opinion",
                    WARN,
                    "POSSIBLE_FALSE_POS",
                    stem,
                    "Nhãn không khớp với dự đoán AI nào",
                    line=line_no
                ))

    return issues

