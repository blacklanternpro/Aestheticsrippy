"""
Aesthetic Compiler - Boutique Mark & Display Typography Vectorizer
Autonomously extracts, cleans, and vectorizes bespoke display logotypes,
pixel fonts, monogram flourishes, and ornamental stamps from scanned references
into scale-independent, crisp publication-grade SVGs.
"""

import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

def extract_and_vectorize_display_mark(
    image_path_or_bytes,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    threshold_val: Optional[int] = 150,
    invert: bool = True,
    min_area: int = 40,
    color_hex: str = "currentColor"
) -> Dict[str, Any]:
    """
    Extracts a region of interest from an image, thresholds it, and converts
    its contours into crisp, scalable SVG paths with evenodd fill rule.
    
    bbox format: (ymin_ratio, xmin_ratio, ymax_ratio, xmax_ratio) in 0.0 - 1.0.
    """
    if isinstance(image_path_or_bytes, np.ndarray):
        img = image_path_or_bytes
    elif isinstance(image_path_or_bytes, (str, Path)):
        img = cv2.imread(str(image_path_or_bytes))
    else:
        nparr = np.frombuffer(image_path_or_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("Could not decode image for mark vectorization.")

    h_img, w_img = img.shape[:2]

    if bbox is not None:
        ymin, xmin, ymax, xmax = bbox
        y1, y2 = max(0, int(ymin * h_img)), min(h_img, int(ymax * h_img))
        x1, x2 = max(0, int(xmin * w_img)), min(w_img, int(xmax * w_img))
        crop = img[y1:y2, x1:x2]
    else:
        crop = img

    h_crop, w_crop = crop.shape[:2]
    if h_crop == 0 or w_crop == 0:
        return {"width": 0, "height": 0, "path_count": 0, "svg": "", "paths": []}

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Use Otsu or manual threshold
    if threshold_val is None or threshold_val <= 0:
        thresh_flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        _, thresh = cv2.threshold(gray, 0, 255, thresh_flag + cv2.THRESH_OTSU)
    else:
        thresh_flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        _, thresh = cv2.threshold(gray, threshold_val, 255, thresh_flag)

    # Find contours with 2-level hierarchy: external contours and inner holes
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    svg_paths = []
    if hierarchy is not None:
        hierarchy = hierarchy[0]
        for idx, (cnt, hier) in enumerate(zip(contours, hierarchy)):
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            parent = hier[3]
            # External contour
            if parent == -1:
                # Build SVG path with subpaths
                subpaths = []
                d = "M " + " L ".join([f"{pt[0][0]},{pt[0][1]}" for pt in cnt]) + " Z"
                subpaths.append(d)

                # Collect direct hole children
                child_idx = hier[2]
                while child_idx != -1:
                    child_cnt = contours[child_idx]
                    if cv2.contourArea(child_cnt) >= 6:
                        hole_d = "M " + " L ".join([f"{pt[0][0]},{pt[0][1]}" for pt in child_cnt]) + " Z"
                        subpaths.append(hole_d)
                    child_idx = hierarchy[child_idx][0]

                full_d = " ".join(subpaths)
                svg_paths.append(f'<path d="{full_d}" fill="{color_hex}" fill-rule="evenodd"/>')

    svg_markup = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_crop} {h_crop}" width="100%" height="auto" style="display:block;max-width:100%;">
  {' '.join(svg_paths)}
</svg>'''

    return {
        "width": w_crop,
        "height": h_crop,
        "path_count": len(svg_paths),
        "svg": svg_markup,
        "paths": svg_paths
    }

def auto_detect_and_vectorize_header(
    image_path_or_bytes,
    max_top_ratio: float = 0.48,
    threshold_val: int = 145,
    min_mark_width_ratio: float = 0.35,
    color_hex: str = "currentColor"
) -> Optional[Dict[str, Any]]:
    """
    Scans the upper region of an image to automatically detect large custom logotypes,
    pixel fonts, or boutique marks, isolates their bounding box, and returns
    the vectorized SVG.
    """
    if isinstance(image_path_or_bytes, (str, Path)):
        img = cv2.imread(str(image_path_or_bytes))
    else:
        nparr = np.frombuffer(image_path_or_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return None

    h_img, w_img = img.shape[:2]
    top_h = int(h_img * max_top_ratio)
    top_crop = img[0:top_h, :]

    gray = cv2.cvtColor(top_crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold_val, 255, cv2.THRESH_BINARY_INV)

    # Morphological dilation to group adjacent letter elements of the logo
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated = cv2.dilate(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Find the most prominent candidate cluster
    candidates = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w >= int(w_img * min_mark_width_ratio) and h >= int(h_img * 0.10):
            # Check centrality: header is usually roughly horizontally centered
            center_x = x + w / 2.0
            dist_from_center = abs(center_x - (w_img / 2.0))
            if dist_from_center < (w_img * 0.25):
                candidates.append((w * h, (x, y, w, h)))

    if not candidates:
        return None

    # Take the largest central mark
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, (bx, by, bw, bh) = candidates[0]

    # Add 4% padding
    pad_x = int(bw * 0.04)
    pad_y = int(bh * 0.04)
    x1 = max(0, bx - pad_x)
    y1 = max(0, by - pad_y)
    x2 = min(w_img, bx + bw + pad_x)
    y2 = min(top_h, by + bh + pad_y)

    bbox_ratio = (y1 / float(h_img), x1 / float(w_img), y2 / float(h_img), x2 / float(w_img))
    
    return extract_and_vectorize_display_mark(
        img,
        bbox=bbox_ratio,
        threshold_val=threshold_val,
        color_hex=color_hex
    )

if __name__ == "__main__":
    test_img = "C:/Users/edtli/.gemini/antigravity/brain/97c85a98-ec5e-498d-ae9c-22bef916c1db/.user_uploaded/media_1790387773618.jpg"
    res = auto_detect_and_vectorize_header(test_img)
    if res:
        print(f"Auto-detected header: {res['width']}x{res['height']}, {res['path_count']} paths!")
        Path("export/auto_header.svg").write_text(res["svg"], encoding="utf-8")
    else:
        print("No header detected.")
