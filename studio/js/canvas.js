// The sheet on the proofing table: renders the Rip, draws millimetre rulers,
// handles selection, inline text editing and repeat-item actions.

import { h, clear, plainText } from "./dom.js";

const PX_PER_MM = 96 / 25.4;
const RULER = 20; // px

export class Canvas {
  constructor(root, hooks) {
    this.hooks = hooks; // onSelect, onEditInput, onEditEnd, onItemAction, onReport, onZoom
    this.zoom = "fit"; // "fit" | number (1 = actual size)
    this.scale = 1;
    this.selected = null; // { path, frame }
    this.editing = null; // { path, el, offset }
    this.report = null;
    this.renderToken = 0;

    this.styleEl = h("style");
    this.host = h("div.sheet-host");
    this.overlay = h("div.sheet-overlay");
    this.outline = h("div.selection-outline", { hidden: true });
    this.itemOutline = h("div.item-outline", { hidden: true });
    this.toolbar = h("div.item-toolbar", { hidden: true, role: "toolbar", "aria-label": "Entry" },
      this.toolButton("add", "Add entry below"),
      this.toolButton("duplicate", "Duplicate"),
      this.toolButton("up", "Move up"),
      this.toolButton("down", "Move down"),
      this.toolButton("remove", "Remove"));
    this.overlay.append(this.itemOutline, this.outline, this.toolbar);
    this.scaler = h("div.sheet-scaler", this.host, this.overlay);
    this.holder = h("div.sheet-holder", this.scaler);
    this.rulerTop = h("canvas.ruler.ruler-top", { "aria-hidden": "true", hidden: true });
    this.rulerLeft = h("canvas.ruler.ruler-left", { "aria-hidden": "true", hidden: true });
    this.mat = h("div.mat", { tabindex: "-1" }, this.holder);
    this.empty = h("div.mat-empty", { hidden: true });
    root.append(this.styleEl, this.rulerTop, this.rulerLeft, this.mat, this.empty);

    this.host.addEventListener("click", (e) => this.onClick(e));
    this.host.addEventListener("dblclick", (e) => this.onDoubleClick(e));
    this.mat.addEventListener("click", (e) => { if (e.target === this.mat || e.target === this.holder) this.select(null); });
    this.mat.addEventListener("scroll", () => this.drawRulers());
    new ResizeObserver(() => this.layout()).observe(root);
    // A face that finishes loading after a render changes every measurement: fit again.
    if (document.fonts) document.fonts.addEventListener("loadingdone", () => this.refit());
  }

  /** Wait until every font the sheet asked for has loaded. */
  async fontsSettled() {
    if (!document.fonts) return;
    void this.sheet.offsetHeight; // layout now, so the browser requests the sheet's faces
    await document.fonts.ready;
  }

  refit() {
    if (!this.sheet || this.editing) return;
    this.report = window.Rip.runFit(this.sheet);
    this.hooks.onReport(this.report);
    this.refreshSelection();
  }

  toolButton(action, label) {
    return h("button.tool", {
      type: "button", title: label, "aria-label": label, dataset: { action },
      onclick: (e) => {
        e.stopPropagation();
        if (this.selected && this.selected.item) this.hooks.onItemAction(action, this.selected.item);
      },
    }, ICONS[action]());
  }

  // -- rendering ---------------------------------------------------------------

  /** Draw the document. `view` = { rip (effective), data, assets, assetBase, hyphenation }. */
  async render(view) {
    const token = ++this.renderToken;
    this.view = view;
    if (!view) {
      clear(this.host);
      this.sheet = null;
      this.page = null;
      this.empty.hidden = false;
      this.rulerTop.hidden = this.rulerLeft.hidden = true;
      this.outline.hidden = this.itemOutline.hidden = this.toolbar.hidden = true;
      return;
    }
    this.empty.hidden = true;
    this.rulerTop.hidden = this.rulerLeft.hidden = false;
    const { rip } = view;
    this.page = rip.page;
    this.styleEl.textContent = window.Rip.pageCss(rip, ".sheet-host");
    let html;
    try {
      html = window.Rip.renderSheet(rip, view.data, {
        editable: true, assets: view.assets, assetBase: view.assetBase, hyphenation: view.hyphenation,
      });
    } catch (e) {
      this.hooks.onReport({ error: e.message });
      return;
    }
    const editing = this.editing;
    this.host.innerHTML = html;
    this.sheet = this.host.querySelector(".page-sheet");
    this.layout();
    await this.fontsSettled();
    if (token !== this.renderToken) return;
    this.report = window.Rip.runFit(this.sheet);
    this.hooks.onReport(this.report);
    if (editing) this.resumeEdit(editing);
    this.refreshSelection();
  }

  layout() {
    if (!this.page) return;
    const wPx = this.page.width_mm * PX_PER_MM, hPx = this.page.height_mm * PX_PER_MM;
    const pad = 48;
    const availW = Math.max(100, this.mat.clientWidth - pad * 2);
    const availH = Math.max(100, this.mat.clientHeight - pad * 2);
    this.scale = this.zoom === "fit" ? Math.min(availW / wPx, availH / hPx) : this.zoom;
    this.scaler.style.width = `${wPx}px`;
    this.scaler.style.height = `${hPx}px`;
    this.scaler.style.transform = `scale(${this.scale})`;
    this.holder.style.width = `${wPx * this.scale}px`;
    this.holder.style.height = `${hPx * this.scale}px`;
    this.hooks.onZoom && this.hooks.onZoom(this.scale);
    this.drawRulers();
    this.refreshSelection();
  }

  setZoom(z) {
    this.zoom = z;
    this.layout();
  }

  zoomBy(f) {
    this.setZoom(Math.min(4, Math.max(0.2, this.scale * f)));
  }

  drawRulers() {
    if (!this.page || !this.sheet) return;
    const dpr = window.devicePixelRatio || 1;
    const matRect = this.mat.getBoundingClientRect();
    const sheetRect = this.scaler.getBoundingClientRect();
    const mmPx = PX_PER_MM * this.scale;
    const ink = getComputedStyle(document.documentElement).getPropertyValue("--ruler-ink").trim() || "#555";
    const draw = (cv, horizontal) => {
      const len = horizontal ? matRect.width : matRect.height;
      cv.width = Math.round((horizontal ? len : RULER) * dpr);
      cv.height = Math.round((horizontal ? RULER : len) * dpr);
      cv.style.width = `${horizontal ? len : RULER}px`;
      cv.style.height = `${horizontal ? RULER : len}px`;
      const g = cv.getContext("2d");
      g.scale(dpr, dpr);
      g.strokeStyle = ink;
      g.fillStyle = ink;
      g.lineWidth = 1;
      g.font = "9px Archivo, sans-serif";
      const origin = horizontal ? sheetRect.left - matRect.left : sheetRect.top - matRect.top;
      const total = horizontal ? this.page.width_mm : this.page.height_mm;
      const step = mmPx < 2 ? 5 : 1;
      for (let m = 0; m <= total; m += step) {
        const p = Math.round(origin + m * mmPx) + 0.5;
        if (p < 0 || p > len) continue;
        const tick = m % 10 === 0 ? 9 : m % 5 === 0 ? 6 : 3;
        g.beginPath();
        if (horizontal) { g.moveTo(p, RULER); g.lineTo(p, RULER - tick); }
        else { g.moveTo(RULER, p); g.lineTo(RULER - tick, p); }
        g.stroke();
        const every = mmPx < 1.5 ? 50 : mmPx < 3 ? 20 : 10;
        if (m % every === 0) {
          if (horizontal) g.fillText(String(m), p + 2, 9);
          else { g.save(); g.translate(9, p + 2); g.rotate(Math.PI / 2); g.fillText(String(m), 0, 0); g.restore(); }
        }
      }
    };
    draw(this.rulerTop, true);
    draw(this.rulerLeft, false);
  }

  // -- selection ---------------------------------------------------------------

  targetFrom(e) {
    const el = e.target.closest(".rip-text, .rip-image");
    return el && this.host.contains(el) ? el : null;
  }

  onClick(e) {
    if (this.editing && this.editing.el.contains(e.target)) return;
    const el = this.targetFrom(e);
    if (!el) { this.select(null); return; }
    if (this.selected && this.selectedElement() === el && this.canEdit(el)) {
      this.startEdit(el, e.clientX, e.clientY);
    } else {
      this.select(el);
    }
  }

  onDoubleClick(e) {
    const el = this.targetFrom(e);
    if (el && this.canEdit(el) && !(this.editing && this.editing.el === el)) this.startEdit(el, e.clientX, e.clientY);
  }

  canEdit(el) {
    return el.classList.contains("rip-text") && el.dataset.path && el.dataset.kind !== "list" &&
      typeof this.hooks.getValue(el.dataset.path) === "string";
  }

  describe(el) {
    if (!el) return null;
    const item = el.closest("[data-item]");
    return {
      frame: el.dataset.frame,
      path: el.dataset.path || null,
      paths: el.dataset.paths ? el.dataset.paths.split(" ") : (el.dataset.path ? [el.dataset.path] : []),
      style: el.dataset.style || null,
      kind: el.classList.contains("rip-image") ? "image" : (el.dataset.kind || "text"),
      item: item ? item.dataset.item : null,
      editable: this.canEdit(el),
    };
  }

  select(el) {
    if (this.editing && (!el || el !== this.editing.el)) this.endEdit();
    this.selected = this.describe(el);
    this.refreshSelection();
    this.hooks.onSelect(this.selected);
  }

  /** Select whatever renders the data at `path` (used when the content panel takes focus). */
  selectPath(path) {
    const el = this.findByPath(path);
    if (el) {
      this.selected = this.describe(el);
      this.refreshSelection();
      this.hooks.onSelect(this.selected, { fromPanel: true });
    }
  }

  findByPath(path) {
    if (!path || !this.sheet) return null;
    const esc = CSS.escape(path);
    return this.sheet.querySelector(`[data-path="${esc}"]`) ||
      Array.from(this.sheet.querySelectorAll("[data-paths]")).find((n) => n.dataset.paths.split(" ").includes(path)) ||
      null;
  }

  selectedElement() {
    if (!this.selected || !this.sheet) return null;
    if (this.selected.path) return this.findByPath(this.selected.path);
    return this.sheet.querySelector(`[data-frame="${CSS.escape(this.selected.frame)}"]`);
  }

  rectOf(el) {
    const s = this.scaler.getBoundingClientRect(), r = el.getBoundingClientRect();
    return { x: (r.left - s.left) / this.scale, y: (r.top - s.top) / this.scale,
      w: r.width / this.scale, h: r.height / this.scale };
  }

  refreshSelection() {
    const el = this.selectedElement();
    const place = (box, r, pad) => {
      box.hidden = false;
      Object.assign(box.style, { left: `${r.x - pad}px`, top: `${r.y - pad}px`,
        width: `${r.w + pad * 2}px`, height: `${r.h + pad * 2}px` });
    };
    if (!el) {
      this.outline.hidden = this.itemOutline.hidden = this.toolbar.hidden = true;
      return;
    }
    const inv = 1 / this.scale;
    this.overlay.style.setProperty("--inv", inv);
    place(this.outline, this.rectOf(el), 2 * inv);
    const item = this.selected.item ? this.sheet.querySelector(`[data-item="${CSS.escape(this.selected.item)}"]`) : null;
    if (item) {
      const r = this.rectOf(item.closest("[data-item]"));
      place(this.itemOutline, r, 4 * inv);
      this.toolbar.hidden = false;
      this.toolbar.style.left = `${r.x}px`;
      this.toolbar.style.top = `${r.y - 4 * inv}px`;
    } else {
      this.itemOutline.hidden = this.toolbar.hidden = true;
    }
  }

  // -- inline editing ------------------------------------------------------------

  caretOffsetFromPoint(el, x, y) {
    const range = document.caretRangeFromPoint ? document.caretRangeFromPoint(x, y) : null;
    if (!range || !el.contains(range.startContainer)) return null;
    const pre = document.createRange();
    pre.selectNodeContents(el);
    pre.setEnd(range.startContainer, range.startOffset);
    // Count in data text: <br> is a newline, soft hyphens and joiners don't exist in the data.
    const frag = pre.cloneContents();
    frag.querySelectorAll && frag.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
    return plainText(frag.textContent).length;
  }

  startEdit(el, x, y) {
    const path = el.dataset.path;
    const raw = this.hooks.getValue(path);
    if (typeof raw !== "string") return;
    const offset = x === undefined ? raw.length : (this.caretOffsetFromPoint(el, x, y) ?? raw.length);
    if (!this.selected || this.selected.path !== path) {
      this.selected = this.describe(el);
      this.hooks.onSelect(this.selected);
    }
    this.enterEdit(el, path, raw, offset);
  }

  enterEdit(el, path, raw, offset) {
    const scaled = el.querySelector(".rip-scaled");
    (scaled || el).textContent = raw;
    el.classList.add("is-editing");
    try { el.contentEditable = "plaintext-only"; } catch { el.contentEditable = "true"; }
    if (el.contentEditable !== "plaintext-only") el.contentEditable = "true";
    el.spellcheck = true;
    this.editing = { path, el, offset };
    el.addEventListener("input", this.onInput = () => {
      const text = (scaled || el).innerText.replace(/\n$/, "");
      this.editing.offset = this.currentOffset(el);
      this.hooks.onEditInput(path, text);
    });
    el.addEventListener("keydown", this.onKey = (e) => {
      if (e.key === "Escape" || (e.key === "Enter" && (e.metaKey || e.ctrlKey))) { e.preventDefault(); this.endEdit(); }
      e.stopPropagation();
    });
    el.addEventListener("blur", this.onBlur = () => setTimeout(() => {
      if (this.editing && this.editing.el === el && !this.resuming) this.endEdit();
    }, 0));
    el.focus({ preventScroll: true });
    this.setOffset(scaled || el, offset);
    this.refreshSelection();
  }

  currentOffset(el) {
    const sel = window.getSelection();
    if (!sel.rangeCount) return 0;
    const r = sel.getRangeAt(0), pre = document.createRange();
    pre.selectNodeContents(el);
    pre.setEnd(r.startContainer, r.startOffset);
    return pre.toString().length;
  }

  setOffset(el, offset) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node, left = offset;
    while ((node = walker.nextNode())) {
      if (left <= node.length) {
        const r = document.createRange();
        r.setStart(node, left);
        r.collapse(true);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        return;
      }
      left -= node.length;
    }
  }

  /** After a reflow render, put the caret back where the writer left it. */
  resumeEdit(prev) {
    const el = this.findByPath(prev.path);
    if (!el) { this.editing = null; return; }
    this.resuming = true;
    this.enterEdit(el, prev.path, this.hooks.getValue(prev.path) ?? "", prev.offset);
    this.resuming = false;
  }

  endEdit() {
    if (!this.editing) return;
    const { el, path } = this.editing;
    el.removeEventListener("input", this.onInput);
    el.removeEventListener("keydown", this.onKey);
    el.removeEventListener("blur", this.onBlur);
    el.contentEditable = "false";
    el.classList.remove("is-editing");
    this.editing = null;
    this.hooks.onEditEnd(path);
  }
}

// Line icons, drawn at 16px on a 16 grid.
const svg = (d) => {
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("viewBox", "0 0 16 16");
  s.setAttribute("width", "16");
  s.setAttribute("height", "16");
  s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", d);
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", "1.4");
  p.setAttribute("stroke-linecap", "round");
  p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
};

export const ICONS = {
  add: () => svg("M8 3.5v9M3.5 8h9"),
  duplicate: () => svg("M5.5 5.5h7v7h-7zM3.5 10.5v-7h7"),
  up: () => svg("M8 12.5v-9M4.5 7 8 3.5 11.5 7"),
  down: () => svg("M8 3.5v9M4.5 9 8 12.5 11.5 9"),
  remove: () => svg("M3.5 4.5h9M6.5 4.5v-1h3v1M5 4.5l.6 8h4.8l.6-8"),
  undo: () => svg("M5.5 6.5H10a3 3 0 0 1 0 6H7M5.5 6.5 8 4M5.5 6.5 8 9"),
  redo: () => svg("M10.5 6.5H6a3 3 0 0 0 0 6h3M10.5 6.5 8 4M10.5 6.5 8 9"),
  minus: () => svg("M3.5 8h9"),
};
