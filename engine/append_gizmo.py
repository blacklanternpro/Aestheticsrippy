from pathlib import Path

gizmo_css = """
/* Visual Object Gizmo */
.visual-object {
  user-select: none;
  transition: box-shadow 0.15s ease;
}

.vo-selected {
  outline: 2px dashed #3b82f6 !important;
  outline-offset: 4px !important;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.2);
}

.vo-toolbar {
  position: absolute;
  top: -36px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(18, 20, 24, 0.95);
  border: 1px solid #3b82f6;
  border-radius: 20px;
  padding: 3px 8px;
  display: flex;
  gap: 6px;
  z-index: 1000;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
  white-space: nowrap;
}

.vo-btn {
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
}

.vo-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.vo-btn.vo-delete:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}
"""

packs_dir = Path(r"c:\Users\edtli\aesthetic-compiler\design-packs")
for p in packs_dir.iterdir():
    css_file = p / "styles.css"
    if css_file.exists():
        content = css_file.read_text(encoding="utf-8")
        if ".vo-toolbar" not in content:
            css_file.write_text(content + "\n" + gizmo_css, encoding="utf-8")
            print(f"Appended gizmo CSS to {css_file}")
