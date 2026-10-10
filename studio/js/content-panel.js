// The content panel: a form generated from the document's data, labelled by
// the pack's "fields" map. Text edits flow straight to the store; lists can
// be added to, reordered and trimmed.

import { h, clear, clone, getPath } from "./dom.js";
import { ICONS } from "./canvas.js";

export class ContentPanel {
  constructor(root, hooks) {
    this.root = root; // hooks: getDoc, getFields, setValue, commitStructure, focusPath, imagePaths, assetUrl
    this.hooks = hooks;
    this.root.addEventListener("focusin", (e) => {
      const f = e.target.closest("[data-field]");
      if (f) this.hooks.focusPath(f.dataset.field);
    });
  }

  render() {
    const doc = this.hooks.getDoc();
    const keep = this.captureFocus();
    const scroll = this.root.scrollTop;
    clear(this.root);
    if (!doc) return;
    const fields = this.hooks.getFields() || {};
    this.labels = fields.labels || {};
    const keys = Object.keys(doc.data).filter((k) => !k.startsWith("_"));
    const order = (fields.order || []).filter((k) => keys.includes(k)).concat(keys.filter((k) => !(fields.order || []).includes(k)));
    for (const key of order) this.root.append(this.section(key, doc.data[key]));
    this.root.scrollTop = scroll;
    this.restoreFocus(keep);
  }

  // -- labels ------------------------------------------------------------------

  label(path) {
    if (this.labels[path]) return this.labels[path];
    const parts = path.split(".");
    for (const [pattern, text] of Object.entries(this.labels)) {
      const pp = pattern.split(".");
      if (pp.length !== parts.length) continue;
      if (pp.every((p, i) => p === "*" || p === parts[i])) return text;
    }
    const last = parts[parts.length - 1];
    if (/^\d+$/.test(last)) {
      return parts.length > 1 ? `${this.label(parts.slice(0, -1).join("."))} ${+last + 1}` : `${+last + 1}`;
    }
    return last.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  }

  // -- building ------------------------------------------------------------------

  section(key, value) {
    return h("section.content-section", { dataset: { section: key } },
      h("h2.content-heading", this.label(key)),
      this.field(key, value, { top: true }));
  }

  field(path, value, opts = {}) {
    if (this.hooks.imagePaths().has(path)) return this.imageField(path, value);
    if (typeof value === "string") return this.textField(path, value, opts);
    if (typeof value === "number") return this.textField(path, String(value), opts);
    if (Array.isArray(value)) return this.listField(path, value, opts);
    if (value && typeof value === "object") return this.groupField(path, value, opts);
    return h("p.muted", "Empty");
  }

  textField(path, value, opts) {
    const id = `f-${path.replace(/\W/g, "-")}`;
    const multiline = value.includes("\n") || value.length > 48;
    const input = multiline
      ? h("textarea.field-input", { id, rows: 1, dataset: { field: path }, spellcheck: true })
      : h("input.field-input", { id, type: "text", dataset: { field: path }, spellcheck: true });
    input.value = value;
    const grow = () => {
      if (input.tagName === "TEXTAREA") { input.style.height = "auto"; input.style.height = `${input.scrollHeight + 2}px`; }
    };
    input.addEventListener("input", () => {
      this.hooks.setValue(path, input.value, this.label(path));
      grow();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && input.tagName === "INPUT" && e.shiftKey) {
        e.preventDefault();
        const pos = input.selectionStart;
        this.hooks.setValue(path, `${input.value.slice(0, pos)}\n${input.value.slice(pos)}`);
        this.render();
      }
    });
    requestAnimationFrame(grow);
    if (opts.bare) return input;
    // A top-level text sits under its section heading, which already names it.
    if (opts.top) { input.setAttribute("aria-label", this.label(path)); return h("div.field", input); }
    return h("div.field", h("label.field-label", { for: id }, this.label(path)), input);
  }

  groupField(path, obj, opts) {
    const rows = Object.keys(obj).filter((k) => !k.startsWith("_")).map((k) => this.field(`${path}.${k}`, obj[k]));
    return opts.top ? h("div.field-group", rows) : h("fieldset.field-group.nested", h("legend", this.label(path)), rows);
  }

  listField(path, list, opts = {}) {
    const allText = list.every((v) => typeof v === "string");
    const box = h("div.list", { dataset: { list: path } });
    const label = opts.top ? null : h("div.field-label", this.label(path));
    list.forEach((item, i) => {
      const ip = `${path}.${i}`;
      const controls = this.itemControls(path, i, list.length);
      if (allText) {
        box.append(h("div.list-line", this.textField(ip, item, { bare: true }), controls));
      } else {
        const summary = this.summary(item) || `${this.label(path)} ${i + 1}`;
        const details = h("details.list-item", { open: list.length <= 4, dataset: { item: ip } },
          h("summary", h("span.item-summary", summary), controls),
          this.field(ip, item, { top: true }));
        box.append(details);
      }
    });
    const add = h("button.text-button", { type: "button", onclick: () => this.addItem(path) },
      ICONS.add(), allText ? "Add line" : "Add entry");
    return h("div.field.field-list", label, box, add);
  }

  summary(item) {
    if (!item || typeof item !== "object") return "";
    for (const k of ["title", "name", "when", "label", "text"]) {
      if (typeof item[k] === "string" && item[k].trim()) return item[k].split("\n")[0];
    }
    const first = Object.values(item).find((v) => typeof v === "string" && v.trim());
    return first ? first.split("\n")[0] : "";
  }

  itemControls(listPath, i, n) {
    const b = (action, label, disabled) => h("button.tool", {
      type: "button", title: label, "aria-label": label, disabled,
      onclick: (e) => { e.preventDefault(); e.stopPropagation(); this.hooks.itemAction(action, `${listPath}.${i}`); },
    }, ICONS[action]());
    return h("span.item-controls", b("up", "Move up", i === 0), b("down", "Move down", i === n - 1),
      b("duplicate", "Duplicate"), b("remove", "Remove"));
  }

  addItem(listPath) {
    const list = getPath(this.hooks.getDoc().data, listPath);
    this.hooks.itemAction("add", `${listPath}.${Math.max(0, list.length - 1)}`, { empty: list.length === 0 });
  }

  imageField(path, value) {
    const url = value ? this.hooks.assetUrl(value) : null;
    const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true,
      onchange: () => { if (file.files[0]) this.hooks.replaceImage(path, file.files[0]); } });
    return h("div.field.field-image", h("div.field-label", this.label(path)),
      h("div.image-row",
        url ? h("img.image-thumb", { src: url, alt: "" }) : h("div.image-thumb.empty"),
        h("button.text-button", { type: "button", dataset: { field: path }, onclick: () => file.click() },
          value ? "Replace photo" : "Choose photo"),
        file));
  }

  // -- focus round-trip --------------------------------------------------------------

  captureFocus() {
    const a = document.activeElement;
    if (!a || !this.root.contains(a) || !a.dataset.field) return null;
    return { path: a.dataset.field, start: a.selectionStart, end: a.selectionEnd };
  }

  restoreFocus(keep) {
    if (!keep) return;
    const el = this.root.querySelector(`[data-field="${CSS.escape(keep.path)}"]`);
    if (!el) return;
    el.focus({ preventScroll: true });
    if (el.setSelectionRange && keep.start != null) el.setSelectionRange(keep.start, keep.end);
  }

  /** Reveal the field for `path` (when the sheet selects something). */
  reveal(path, { focus = false } = {}) {
    this.root.querySelectorAll(".field-active").forEach((n) => n.classList.remove("field-active"));
    if (!path) return;
    const el = this.root.querySelector(`[data-field="${CSS.escape(path)}"]`);
    if (!el) return;
    let p = el.parentElement;
    while (p && p !== this.root) { if (p.tagName === "DETAILS") p.open = true; p = p.parentElement; }
    (el.closest(".field") || el).classList.add("field-active");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    if (focus) el.focus({ preventScroll: true });
  }

  /** Keep a field's value in step when the sheet edits it. */
  syncValue(path, value) {
    const el = this.root.querySelector(`[data-field="${CSS.escape(path)}"]`);
    if (el && "value" in el && el !== document.activeElement && el.value !== value) el.value = value;
  }
}

/** A blank copy of an entry: same shape, empty text. */
export function blankLike(v) {
  if (typeof v === "string") return "";
  if (Array.isArray(v)) return v.length && typeof v[0] === "string" ? [""] : [];
  if (v && typeof v === "object") {
    const o = {};
    for (const [k, x] of Object.entries(v)) o[k] = blankLike(x);
    return o;
  }
  return clone(v);
}
