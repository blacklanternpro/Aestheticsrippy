from pathlib import Path
import re

gizmo_css = """
/* Visual Object Gizmo Overlay */
.vo-gizmo {
  position: absolute;
  pointer-events: none;
  border: 2px dashed #3b82f6;
  border-radius: 2px;
  z-index: 9999;
  box-sizing: border-box;
  transform-origin: center center;
}

.vo-gizmo .vo-toolbar {
  position: absolute;
  top: -44px;
  left: 50%;
  transform: translateX(-50%);
  background: #11141a;
  border: 1px solid #3b82f6;
  border-radius: 24px;
  padding: 4px 10px;
  display: flex;
  gap: 8px;
  pointer-events: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
}

.vo-gizmo .vo-btn {
  background: transparent;
  border: none;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  transition: all 0.15s ease;
}

.vo-gizmo .vo-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.vo-gizmo .vo-btn.vo-delete:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.vo-gizmo .vo-rotate-stem {
  position: absolute;
  top: -18px;
  left: 50%;
  width: 1px;
  height: 18px;
  background: #3b82f6;
  pointer-events: none;
}

.vo-gizmo .vo-rotate-handle {
  position: absolute;
  top: -30px;
  left: 50%;
  transform: translateX(-50%);
  width: 22px;
  height: 22px;
  background: #3b82f6;
  border: 2px solid #ffffff;
  border-radius: 50%;
  cursor: grab;
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.vo-gizmo .vo-rotate-handle:active {
  cursor: grabbing;
  background: #2563eb;
}

.vo-gizmo .vo-resize-handle {
  position: absolute;
  bottom: -6px;
  right: -6px;
  width: 14px;
  height: 14px;
  background: #3b82f6;
  border: 2px solid #ffffff;
  border-radius: 3px;
  cursor: nwse-resize;
  pointer-events: auto;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.vo-gizmo .vo-drag-surface {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  cursor: move;
  pointer-events: auto;
}

@media print {
  .vo-gizmo {
    display: none !important;
  }
}
"""

packs_dir = Path(r"c:\Users\edtli\aesthetic-compiler\design-packs")
for p in packs_dir.iterdir():
    css_file = p / "styles.css"
    if css_file.exists():
        content = css_file.read_text(encoding="utf-8")
        # remove old vo styles if present
        content = re.sub(r'/\* Visual Object Gizmo \*/.*', '', content, flags=re.DOTALL)
        css_file.write_text(content.strip() + "\n" + gizmo_css, encoding="utf-8")
        print(f"Updated {css_file}")
