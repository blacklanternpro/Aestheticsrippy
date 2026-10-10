import cv2
import numpy as np

im = cv2.imread('export/crop_lsd_exact.png')
gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
h, w = gray.shape

# Threshold black ink inside y=10..88
raw_mask = (gray[10:88, :] < 75).astype(np.uint8) * 255

# Glyphs:
# L: x=0..61
# S: x=62..130
# D: x=130..w
masks = {
    'l': (raw_mask[:, :62], 0, 10),
    's': (raw_mask[:, 62:130], 62, 10),
    'd': (raw_mask[:, 130:], 130, 10)
}

glyph_svgs = {}
for name, (submask, offset_x, offset_y) in masks.items():
    contours, hier = cv2.findContours(submask, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)
    
    path_strings = []
    if hier is not None:
        for i, cnt in enumerate(contours):
            parent = hier[0][i][3]
            area = cv2.contourArea(cnt)
            
            # If outer contour (parent == -1): keep it if area > 500
            # If inner hole (parent != -1): ONLY keep if area > 350 (i.e. the true counter hole of D, not tiny letter cuts)
            if parent == -1 and area > 500:
                pass
            elif parent != -1 and area > 350:
                pass
            else:
                continue
                
            cnt_shifted = cnt.copy()
            cnt_shifted[:, :, 0] += offset_x
            cnt_shifted[:, :, 1] += offset_y
            
            # Smooth contour slightly
            peri = cv2.arcLength(cnt_shifted, True)
            approx = cv2.approxPolyDP(cnt_shifted, 0.003 * peri, True)
            pts = approx.reshape(-1, 2)
            
            d = f'M {pts[0][0]} {pts[0][1]} '
            for p in pts[1:]:
                d += f'L {p[0]} {p[1]} '
            d += 'Z'
            path_strings.append(d)
            print(f'Glyph {name}: kept contour {i}, area={area:.1f}, parent={parent}, pts={len(pts)}')
            
    glyph_svgs[name] = ' '.join(path_strings)

# Build SVG
svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 190 91" width="100%" height="100%">
  <!-- Orange Screenprint Registration Shadow Layer -->
  <g fill="#ff6600" transform="translate(-3.5, 3.5)">
    <path class="shadow-l" d="{glyph_svgs['l']}" fill-rule="evenodd"/>
    <path class="shadow-s" d="{glyph_svgs['s']}" fill-rule="evenodd"/>
    <path class="shadow-d" d="{glyph_svgs['d']}" fill-rule="evenodd"/>
  </g>
  <!-- Black Ink Layer -->
  <g fill="#000000">
    <path class="main-l" d="{glyph_svgs['l']}" fill-rule="evenodd"/>
    <path class="main-s" d="{glyph_svgs['s']}" fill-rule="evenodd"/>
    <path class="main-d" d="{glyph_svgs['d']}" fill-rule="evenodd"/>
  </g>
</svg>'''

with open('export/lsd_traced.svg', 'w') as f:
    f.write(svg_content)
print('Successfully generated clean vector SVG with D counter hole!')
