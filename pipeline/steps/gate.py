"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401

def decide(issues, image_stems, cfg, reviewed=frozenset()):
    # Danh sách ảnh hợp lệ của dataset
    images = set(image_stems)
    reviewed = set(reviewed)

    # 1. Đếm tất cả lỗi bắt buộc
    n_errors = sum(
        1 for issue in issues
        if issue.severity == ERROR
    )

    # 2. Tìm các ảnh còn cảnh báo chưa xử lý
    warn_images = {
        issue.image
        for issue in issues
        if issue.severity == WARN
        and issue.image in images
        and issue.image not in reviewed
    }

    n_images = len(images)
    n_warn_images = len(warn_images)

    # 3. Tính tỷ lệ cảnh báo
    warn_ratio = (
        n_warn_images / n_images
        if n_images > 0 else 0.0
    )

    threshold = cfg["gate"]["warn_ratio_hold"]

    # 4. Quyết định chất lượng dataset
    if n_errors > 0:
        decision = "Rework"
        reasons = [
            f"Còn {n_errors} lỗi bắt buộc chưa xử lý."
        ]

    elif warn_ratio >= threshold:
        decision = "Hold"
        reasons = [
            f"Có {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({warn_ratio:.2%}), đạt hoặc vượt ngưỡng "
            f"{threshold:.2%}."
        ]

    else:
        decision = "Release"
        reasons = [
            f"Không còn lỗi bắt buộc. "
            f"Tỷ lệ ảnh cảnh báo {warn_ratio:.2%} "
            f"thấp hơn ngưỡng {threshold:.2%}."
        ]

    # 5. Trả kết quả về pipeline
    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": round(warn_ratio, 4),
        "reasons": reasons,
    }
