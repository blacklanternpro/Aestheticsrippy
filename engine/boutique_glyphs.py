"""
Aesthetic Compiler - Boutique Display Glyph & Vector Lockup Engine
Generates publication-grade, chunky screenprint vector glyphs with
parametric ribbon text distribution and dual-layer chromatic screenprint registration.
"""

from typing import Dict, List, Tuple, Any, Optional
import math

# Centerline spline landmark paths for contoured acronym glyphs
# Each point is: (left_pct, top_pct, tangent_rot_deg)
GLYPH_SKELETONS: Dict[str, List[Tuple[float, float, float]]] = {
    "L": [
        (7.3, 21.6, 0.0),      # Top stem
        (7.5, 43.0, 0.0),      # Upper-mid stem
        (7.5, 64.0, 0.0),      # Lower-mid stem
        (8.0, 85.7, 0.0),      # Bottom corner
        (16.0, 85.4, 0.0),     # Foot mid
        (23.9, 85.1, 0.0),     # Foot right tip
    ],
    "S": [
        (39.8, 80.0, -30.0),   # Bottom-left hook
        (50.1, 88.5, 0.0),     # Bottom curve apex
        (58.6, 79.0, 35.0),    # Lower right turn
        (57.1, 59.2, 35.0),    # Lower waist entry
        (45.6, 53.3, -45.0),   # Center waist
        (39.2, 37.4, -90.0),   # Upper left turn
        (48.6, 23.3, 0.0),     # Top curve apex
        (59.5, 29.1, 30.0),    # Top right hook
    ],
    "D": [
        (78.7, 23.0, 0.0),     # Top left corner
        (86.0, 27.0, -30.0),   # Upper bowl entry
        (91.3, 39.2, -45.0),   # Upper right bowl apex
        (91.2, 72.6, -45.0),   # Lower right bowl apex
        (86.0, 84.0, 45.0),    # Lower bowl curve
        (78.9, 87.3, 90.0),    # Bottom curve meeting spine
        (74.4, 70.0, 0.0),     # Lower spine
        (74.4, 54.4, 0.0),     # Mid spine
        (74.4, 38.0, 0.0),     # Upper spine
    ]
}

# Vector paths for LSD display header in 190x91 coordinate space
LSD_VECTOR_PATHS = {
    "viewBox": "0 0 190 91",
    "paths": {
        "L": "M 8 14 L 7 25 L 8 44 L 7 77 L 8 78 L 8 86 L 59 86 L 59 72 L 24 71 L 24 14 Z",
        "S": "M 84 15 L 73 21 L 68 27 L 66 32 L 67 43 L 69 47 L 77 53 L 104 60 L 108 67 L 102 73 L 90 73 L 85 71 L 80 64 L 64 64 L 65 70 L 68 77 L 78 85 L 85 87 L 104 87 L 116 81 L 122 73 L 122 56 L 112 47 L 85 40 L 82 36 L 82 33 L 84 30 L 90 27 L 101 27 L 107 32 L 108 35 L 122 34 L 119 23 L 111 16 L 96 13 Z",
        "D": "M 165 16 L 159 14 L 148 13 L 135 14 L 136 60 L 135 85 L 136 87 L 153 87 L 159 86 L 170 82 L 178 75 L 182 68 L 184 60 L 184 47 L 182 36 L 177 26 L 175 24 L 171 24 L 172 21 Z M 149 29 L 155 29 L 159 30 L 162 32 L 166 36 L 169 42 L 170 49 L 170 55 L 168 63 L 166 66 L 162 70 L 158 72 L 154 73 L 147 72 Z"
    }
}

def sample_path(points: List[Tuple[float, float, float]], n: int) -> List[Tuple[float, float, float]]:
    """
    Evenly distributes n character positions along a piecewise landmark spline.
    Returns list of (left_pct, top_pct, rot_deg).
    """
    if n <= 1:
        return [points[len(points) // 2]]
    if n == len(points):
        return points

    # Compute segment lengths along the spline
    cum_lens = [0.0]
    total_len = 0.0
    for i in range(len(points) - 1):
        x1, y1, _ = points[i]
        x2, y2, _ = points[i + 1]
        dist = math.hypot(x2 - x1, y2 - y1)
        total_len += dist
        cum_lens.append(total_len)

    sampled = []
    for i in range(n):
        target_dist = (i / (n - 1)) * total_len
        # Find which segment contains target_dist
        seg_idx = 0
        for s in range(len(cum_lens) - 1):
            if cum_lens[s] <= target_dist <= cum_lens[s + 1]:
                seg_idx = s
                break
        
        seg_len = cum_lens[seg_idx + 1] - cum_lens[seg_idx]
        t = 0.0 if seg_len == 0 else (target_dist - cum_lens[seg_idx]) / seg_len
        
        p1 = points[seg_idx]
        p2 = points[seg_idx + 1]
        
        x = p1[0] + t * (p2[0] - p1[0])
        y = p1[1] + t * (p2[1] - p1[1])
        
        # Angle interpolation (accounting for wrap-around if needed)
        r1, r2 = p1[2], p2[2]
        rot = r1 + t * (r2 - r1)
        
        sampled.append((round(x, 1), round(y, 1), round(rot, 1)))

    return sampled

def generate_glyph_lockup(
    words: Dict[str, str] = None,
    shadow_offset: Tuple[float, float] = (-3.5, 3.5),
    shadow_color: str = "#ff6600",
    ink_color: str = "#000000",
    knockout_color: str = "var(--page-bg, #ff2a8d)",
    font_size_px: int = 27
) -> Dict[str, str]:
    """
    Synthesizes a complete boutique vector glyph lockup with:
    1. Dual-layer SVG (screenprint registration shadow + ink plate)
    2. In-DOM inner text spans with subpixel positions and rotations
    3. Self-contained CSS rules for pixel-perfect reproduction
    """
    if words is None:
        words = {"L": "LAST", "S": "SATURDAY", "D": "DANCE"}

    # 1. Build SVG paths
    view_box = LSD_VECTOR_PATHS["viewBox"]
    paths = LSD_VECTOR_PATHS["paths"]
    
    shadow_dx, shadow_dy = shadow_offset
    
    svg_markup = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" width="100%" height="100%">
  <!-- Screenprint Registration Misprint Shadow Layer -->
  <g fill="{shadow_color}" transform="translate({shadow_dx}, {shadow_dy})">
    <path class="shadow-l" d="{paths['L']}" fill-rule="evenodd"/>
    <path class="shadow-s" d="{paths['S']}" fill-rule="evenodd"/>
    <path class="shadow-d" d="{paths['D']}" fill-rule="evenodd"/>
  </g>
  <!-- Primary Ink Layer -->
  <g fill="{ink_color}">
    <path class="main-l" d="{paths['L']}" fill-rule="evenodd"/>
    <path class="main-s" d="{paths['S']}" fill-rule="evenodd"/>
    <path class="main-d" d="{paths['D']}" fill-rule="evenodd"/>
  </g>
</svg>"""

    # 2. Build inner character spans
    inner_chars_markup = []
    inner_css_rules = []

    # Calibrated landmark mappings for default words
    exact_mappings = {
        "LAST": [
            ("L", 7.3, 21.6, 0.0),
            ("A", 7.5, 54.2, -90.0),
            ("S", 8.0, 85.7, 0.0),
            ("T", 23.9, 85.1, 0.0),
        ],
        "SATURDAY": [
            ("S", 39.8, 80.0, -30.0),
            ("A", 50.1, 88.5, 0.0),
            ("T", 58.6, 79.0, 35.0),
            ("U", 57.1, 59.2, 35.0),
            ("R", 45.6, 53.3, -45.0),
            ("D", 39.2, 37.4, -90.0),
            ("A", 48.6, 23.3, 0.0),
            ("Y", 59.5, 29.1, 30.0),
        ],
        "DANCE": [
            ("D", 78.7, 23.0, 0.0),
            ("A", 91.3, 39.2, -45.0),
            ("N", 91.2, 72.6, -45.0),
            ("C", 78.9, 87.3, 90.0),
            ("E", 74.4, 54.4, 0.0),
        ]
    }

    for glyph_key in ["L", "S", "D"]:
        word = words.get(glyph_key, "").upper()
        if not word:
            continue
            
        g_lower = glyph_key.lower()
        inner_chars_markup.append(f'    <div class="inner-chars inner-{g_lower}">')
        
        # Check if we have exact calibrated mapping
        if word in exact_mappings:
            char_data = exact_mappings[word]
        else:
            # Distribute dynamically along skeleton spline
            skeleton = GLYPH_SKELETONS.get(glyph_key, [])
            positions = sample_path(skeleton, len(word))
            char_data = [(char, px, py, rot) for char, (px, py, rot) in zip(word, positions)]

        for idx, (ch, left_pct, top_pct, rot) in enumerate(char_data, 1):
            class_name = f"char-{g_lower}{idx}"
            inner_chars_markup.append(f'      <span class="{class_name}">{ch}</span>')
            
            # CSS rule
            if rot != 0.0:
                inner_css_rules.append(
                    f".inner-{g_lower} .{class_name} {{ left: {left_pct}%; top: {top_pct}%; transform: translate(-50%, -50%) rotate({rot}deg); }}"
                )
            else:
                inner_css_rules.append(
                    f".inner-{g_lower} .{class_name} {{ left: {left_pct}%; top: {top_pct}%; transform: translate(-50%, -50%); }}"
                )
                
        inner_chars_markup.append("    </div>")

    inner_html = "\n".join(inner_chars_markup)
    
    html = f"""  <div class="glyph-lockup visual-object ac-movable">
    <div class="glyph-vector">
      {svg_markup}
    </div>
{inner_html}
  </div>"""

    css = f"""/* === BOUTIQUE VECTOR GLYPH LOCKUP === */
.glyph-lockup {{
  position: relative;
  width: 100%;
  max-width: 570px;
  margin: 0 auto;
  aspect-ratio: 190 / 91;
  display: block;
}}

.glyph-vector {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}}

.glyph-vector svg {{
  width: 100%;
  height: 100%;
  display: block;
}}

.inner-chars {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: auto;
}}

.inner-chars span {{
  position: absolute;
  font-family: 'Inter', 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: {font_size_px}px;
  color: {knockout_color};
  line-height: 1;
  user-select: text;
  cursor: text;
  text-shadow: 0.5px 0.5px 0px rgba(255, 102, 0, 0.7);
  min-width: 1ch;
}}

""" + "\n".join(inner_css_rules)

    return {
        "html": html,
        "css": css,
        "svg": svg_markup
    }

if __name__ == "__main__":
    res = generate_glyph_lockup()
    print("Generated Glyph Lockup:")
    print(res["html"][:300] + "...")
    print("\nCSS Sample:")
    print(res["css"][:300] + "...")
