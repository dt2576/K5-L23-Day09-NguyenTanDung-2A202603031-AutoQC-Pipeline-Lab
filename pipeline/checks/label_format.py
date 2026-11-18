"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""

from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    issues = []
    settings = cfg["label_format"]

    for label_file in ds.label_files():
        stem = label_file.stem
        lines = ds.read_label_lines(stem) or []
        image_size = ds.image_size(stem)
        previous_boxes = []

        for line_no, text in lines:
            try:
                class_id, cx, cy, w, h = parse_yolo_line(text)
            except (ValueError, OverflowError):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_FORMAT",
                    stem, "Dòng nhãn không đúng định dạng YOLO",
                    line=line_no
                ))
                continue

            if not 0 <= class_id < len(ds.classes):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_CLASS_ID",
                    stem, f"ID lớp không hợp lệ: {class_id}",
                    line=line_no
                ))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_ZERO",
                    stem, "Bounding Box có chiều rộng hoặc cao <= 0",
                    line=line_no
                ))
                continue

            # Tính các mép của box trong tọa độ chuẩn hóa.
            left = cx - w / 2
            right = cx + w / 2
            top = cy - h / 2
            bottom = cy + h / 2

            overflow = max(
                0.0,
                -left,
                -top,
                right - 1.0,
                bottom - 1.0
            )

            if overflow > settings["overflow_tol"]:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_OUT_OF_IMAGE",
                    stem, "Bounding Box vượt khỏi giới hạn ảnh",
                    line=line_no,
                    extra={"overflow": overflow}
                ))

            # Chỉ so sánh với box cùng lớp ở dòng trước.
            box = (cx, cy, w, h)

            for prev_class, prev_box in previous_boxes:
                if (
                    prev_class == class_id
                    and iou_xywh(box, prev_box)
                    > settings["dup_box_iou"]
                ):
                    issues.append(Issue(
                        "label_format", ERROR, "DUP_BOX",
                        stem, "Bounding Box bị trùng",
                        line=line_no
                    ))
                    break

            previous_boxes.append((class_id, box))

            # Kiểm tra kích thước box theo pixel.
            if image_size is not None:
                img_w, img_h = image_size
                short_side = min(w * img_w, h * img_h)

                if short_side < settings["min_box_px"]:
                    issues.append(Issue(
                        "label_format", WARN, "BOX_TINY",
                        stem, "Bounding Box quá nhỏ",
                        line=line_no
                    ))

            if w * h > settings["max_box_frac"]:
                issues.append(Issue(
                    "label_format", WARN, "BOX_HUGE",
                    stem, "Bounding Box chiếm quá nhiều diện tích ảnh",
                    line=line_no
                ))

    return issues
