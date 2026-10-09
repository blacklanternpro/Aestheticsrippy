import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.harvester import normalize_typographic_structures

sample_html = """<!DOCTYPE html><html><head></head><body>
<main class="page-sheet">
  <div class="header">L S D<br>LAST SATURDAY DANCE</div>
  <p>3 26 16</p>
</main>
</body></html>"""

sample_css = ".page-sheet { background: #ff2a8d; }"

out_html, out_css = normalize_typographic_structures(sample_html, sample_css)
assert 'glyph-lockup' in out_html, 'glyph-lockup missing from HTML'
assert 'glyph-vector' in out_html, 'glyph-vector missing from HTML'
assert 'inner-chars' in out_html, 'inner-chars missing from HTML'
assert 'date-triptych' in out_html, 'date-triptych missing from HTML'
assert 'Boutique Vector Glyph Lockup' in out_css, 'CSS rules missing'
print('[PASS] Normalizer successfully transformed naive harvest into Vector Boutique Lockup!')
