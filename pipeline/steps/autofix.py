"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""

from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line


DROP_CODES = {
    "BAD_FORMAT",
    "BAD_CLASS_ID",
    "BOX_ZERO",
    "DUP_BOX",
}

REMOVE_CODES = {
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}


def _record(image, line, action, before, after):
    return {
        "image": image,
        "line": line,
        "action": action,
        "before": before,
        "after": after,
    }


def _clip_box(text):
    """Cắt bounding box về trong vùng ảnh [0, 1]."""
    class_id, cx, cy, w, h = parse_yolo_line(text)

    x1 = max(0.0, cx - w / 2)
    y1 = max(0.0, cy - h / 2)
    x2 = min(1.0, cx + w / 2)
    y2 = min(1.0, cy + h / 2)

    # Box nằm hoàn toàn ngoài ảnh.
    if x2 <= x1 or y2 <= y1:
        return None

    new_cx = (x1 + x2) / 2
    new_cy = (y1 + y2) / 2
    new_w = x2 - x1
    new_h = y2 - y1

    return (
        f"{class_id} "
        f"{new_cx:.10g} {new_cy:.10g} "
        f"{new_w:.10g} {new_h:.10g}"
    )


def fix(ds, issues, cfg):
    fixes = []

    # Chỉ xử lý lỗi ERROR.
    errors = [
        issue for issue in issues
        if issue.severity == ERROR
    ]

    # 1. Xóa ảnh lỗi trước.
    removed_images = set()

    for issue in errors:
        if not (
            issue.code in REMOVE_CODES
            or issue.code.startswith("DUP_IMAGE_")
        ):
            continue

        stem = issue.image

        if stem in removed_images:
            continue

        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)

        if image_path is None and not label_path.exists():
            continue

        before = str(image_path) if image_path else str(label_path)

        if image_path is not None:
            image_path.unlink()

        if label_path.exists():
            label_path.unlink()

        ds._size_cache.pop(stem, None)

        removed_images.add(stem)

        fixes.append(_record(
            stem, None, "remove_image",
            before, "(đã xóa)"
        ))

    # 2. Sửa tên class trong data.yaml.
    if any(issue.code == "BAD_CLASS_NAME" for issue in errors):
        if ds.yaml_path.exists():
            data = yaml.safe_load(
                ds.yaml_path.read_text(encoding="utf-8")
            ) or {}

            before = data.get("names")
            expected = list(cfg["classes"])

            if before != expected:
                data["names"] = expected
                data["nc"] = len(expected)

                ds.yaml_path.write_text(
                    yaml.safe_dump(
                        data,
                        allow_unicode=True,
                        sort_keys=False
                    ),
                    encoding="utf-8"
                )

                fixes.append(_record(
                    "data.yaml", None, "rename_classes",
                    str(before), str(expected)
                ))

    # 3. Xử lý ảnh thiếu file nhãn.
    missing_images = set()

    for issue in errors:
        if issue.code != "MISSING_LABEL_FILE":
            continue

        stem = issue.image

        if stem in removed_images or stem in missing_images:
            continue

        if ds.image_path(stem) is None:
            continue

        if not ds.label_path(stem).exists():
            fixes.append(_record(
                stem,
                None,
                "needs_label",
                "(không có file)",
                "chuyển người gán"
            ))
            missing_images.add(stem)

    # 4. Gom lỗi theo file và số dòng GỐC.
    problems = defaultdict(lambda: defaultdict(set))

    for issue in errors:
        if issue.image in removed_images:
            continue

        if issue.line is None:
            continue

        if (
            issue.code in DROP_CODES
            or issue.code == "BOX_OUT_OF_IMAGE"
        ):
            problems[issue.image][issue.line].add(issue.code)

    # 5. Sửa từng file nhãn, chỉ ghi file một lần.
    for stem, line_problems in problems.items():
        path = ds.label_path(stem)

        if not path.exists():
            continue

        original = path.read_text(
            encoding="utf-8"
        ).splitlines()

        output = []
        changed = False

        for line_number, text in enumerate(original, start=1):
            codes = line_problems.get(line_number, set())

            if not codes:
                output.append(text)
                continue

            # Ưu tiên xóa dòng nếu có lỗi cần xóa.
            if codes & DROP_CODES:
                fixes.append(_record(
                    stem, line_number, "drop_line",
                    text, ""
                ))
                changed = True
                continue

            # Cắt box vượt giới hạn.
            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    clipped = _clip_box(text)
                except (ValueError, OverflowError):
                    clipped = None

                if clipped is None:
                    fixes.append(_record(
                        stem, line_number, "drop_line",
                        text, ""
                    ))
                    changed = True
                    continue

                if clipped != text:
                    fixes.append(_record(
                        stem, line_number, "clip_box",
                        text, clipped
                    ))
                    output.append(clipped)
                    changed = True
                else:
                    output.append(text)

                continue

            output.append(text)

        if changed:
            path.write_text(
                "\n".join(output) + ("\n" if output else ""),
                encoding="utf-8"
            )

    return fixes
