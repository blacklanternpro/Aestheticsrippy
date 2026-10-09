import cv2
import numpy as np

img = cv2.imread('export/crop_lsd_exact.png')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
black_mask = (gray < 85).astype(np.uint8) * 255
contours, hierarchy = cv2.findContours(black_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

components = []
for i, c in enumerate(contours):
    area = cv2.contourArea(c)
    parent = hierarchy[0][i][3]
    if parent != -1 and 5 < area < 400:
        x, y, w, h = cv2.boundingRect(c)
        M = cv2.moments(c)
        if M['m00'] > 0:
            cx = M['m10'] / M['m00']
            cy = M['m01'] / M['m00']
            components.append({
                'cx': cx, 'cy': cy, 'x': x, 'y': y, 'w': w, 'h': h,
                'pct_x': round((cx / 190.0) * 100, 1),
                'pct_y': round((cy / 91.0) * 100, 1),
                'area': area
            })

print("=== L (LAST) ===")
# L: cx < 60
l_chars = sorted([c for c in components if c['cx'] < 60], key=lambda c: (c['cy'] if c['cx'] < 30 else 100))
l_letters = ['L', 'A', 'S', 'T']
l_rot = [0, -90, 0, 0]
for l, c, rot in zip(l_letters, l_chars, l_rot):
    px = c['pct_x']
    py = c['pct_y']
    print(f"{l}: left: {px}%, top: {py}%, cx={c['cx']:.1f}, cy={c['cy']:.1f}, rot={rot}deg")

print("\n=== S (SATURDAY) ===")
# S chars:
s_map = [
    ('S', 75.6, 72.8, -25),
    ('A', 95.2, 80.5, 0),
    ('T', 111.3, 71.9, 35),
    ('U', 108.5, 53.9, -150),
    ('R', 86.6, 48.5, -45),
    ('D', 74.5, 34.0, -90),
    ('A', 92.4, 21.2, 0),
    ('Y', 113.1, 26.5, 30),
]
for item in s_map:
    char, cx, cy, rot = item
    px = round(cx / 190.0 * 100, 1)
    py = round(cy / 91.0 * 100, 1)
    print(f"{char}: left: {px}%, top: {py}%, rot: {rot}deg")

print("\n=== D (DANCE) ===")
d_map = [
    ('D', 149.6, 20.9, 0),
    ('A', 173.5, 35.7, 45),
    ('N', 173.3, 66.1, 80),
    ('C', 150.0, 79.4, 0),
    ('E', 141.4, 49.5, 0),
]
for item in d_map:
    char, cx, cy, rot = item
    px = round(cx / 190.0 * 100, 1)
    py = round(cy / 91.0 * 100, 1)
    print(f"{char}: left: {px}%, top: {py}%, rot: {rot}deg")
