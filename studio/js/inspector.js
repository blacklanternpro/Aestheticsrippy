// The inspector: layout variant, paper and ink, and the type style of
// whatever is selected. A style edit changes every text that uses the style,
// which is how a type system stays consistent.

import { h, clear } from "./dom.js";

const FONTS = [
  { family: "Inter", axes: [] },
  { family: "Inter Tight", axes: [] },
  { family: "Archivo", axes: ["stretch"] },
  { family: "Jost", axes: [] },
  { family: "Mrs Saint Delafield", axes: [], fixedWeight: 400 },
];

const CASES = [["", "As typed"], ["upper", "Capitals"], ["lower", "Lowercase"], ["title", "Title case"]];
const ALIGNS = [["left", "Left"], ["center", "Centre"], ["right", "Right"], ["justify", "Justified"]];

export class Inspector {
  constructor(root, hooks) {
    this.root = root; // hooks: getDoc, getPack, setVariant, setStyle, resetStyle, setToken, resetToken
    this.hooks = hooks;
    this.selection = null;
  }

  setSelection(sel) {
    this.selection = sel;
    this.render();
  }

  render() {
    const keep = document.activeElement && this.root.contains(document.activeElement)
      ? document.activeElement.dataset.prop : null;
    clear(this.root);
    const doc = this.hooks.getDoc(), pack = this.hooks.getPack();
    if (!doc || !pack) return;
    this.root.append(this.layoutSection(doc, pack));
    const style = this.selection && this.selection.style ? this.selection.style.split(" ")[0] : null;
    if (style) this.root.append(this.styleSection(doc, pack, style));
    else this.root.append(h("p.inspector-hint", "Select text on the sheet to adjust its type style."));
    this.root.append(this.colourSection(doc, pack));
    if (keep) {
      const el = this.root.querySelector(`[data-prop="${keep}"]`);
      if (el) el.focus({ preventScroll: true });
    }
  }

  layoutSection(doc, pack) {
    const variants = Object.entries(pack.rip.variants || {});
    if (!variants.length) return h("div");
    const choose = (value) => () => this.hooks.setVariant(value);
    const option = (value, name, description) => h("label.choice",
      h("input", { type: "radio", name: "variant", checked: (doc.variant || "") === value, onchange: choose(value || null) }),
      h("span.choice-text", h("span.choice-name", name), description ? h("span.choice-desc", description) : null));
    return h("section.inspector-section",
      h("h2.inspector-heading", "Layout"),
      option("", "As referenced", "The reference's own arrangement."),
      variants.map(([name, v]) => option(name, name.replace(/^\w/, (c) => c.toUpperCase()), v.description)));
  }

  styleSection(doc, pack, name) {
    const base = resolve(pack.rip.styles, name);
    const over = (doc.styles || {})[name] || {};
    const eff = Object.assign({}, base, over);
    const users = this.hooks.countStyleUsers(name);
    const font = FONTS.find((f) => f.family === eff.font) || FONTS[0];
    const changed = (k) => k in over && over[k] !== base[k];
    const row = (key, label, control) => h("div.prop" + (changed(key) ? ".is-changed" : ""),
      h("label.prop-label", { for: `p-${key}` }, label), control,
      changed(key) ? h("button.reset", { type: "button", title: "Back to the pack's value",
        "aria-label": `Reset ${label}`, onclick: () => this.hooks.resetStyle(name, key) }, "↺") : h("span.reset-space"));
    const number = (key, { step, min, max, unit }) => {
      const input = h("input.prop-input", { id: `p-${key}`, type: "number", step, min, max,
        value: eff[key] ?? "", dataset: { prop: key },
        onchange: () => { if (input.value !== "") this.hooks.setStyle(name, key, +input.value); } });
      return h("span.prop-field", input, h("span.unit", unit));
    };
    const select = (key, options, value) => {
      const s = h("select.prop-input", { id: `p-${key}`, dataset: { prop: key },
        onchange: () => this.hooks.setStyle(name, key, s.value === "" ? null : s.value) },
      options.map(([v, l]) => h("option", { value: v, selected: (value ?? "") === v }, l)));
      return s;
    };
    return h("section.inspector-section",
      h("h2.inspector-heading", "Type style"),
      h("p.style-name", h("strong", name), `, used by ${users} ${users === 1 ? "text" : "texts"} on this sheet`),
      row("font", "Typeface", select("font", FONTS.map((f) => [f.family, f.family]), eff.font)),
      row("size", "Size", number("size", { step: 0.1, min: 3, max: 400, unit: "pt" })),
      font.fixedWeight ? null : row("weight", "Weight", number("weight", { step: 10, min: 100, max: 900, unit: "" })),
      font.axes.includes("stretch") ? row("stretch", "Width", number("stretch", { step: 1, min: 62, max: 125, unit: "%" })) : null,
      row("tracking", "Tracking", number("tracking", { step: 0.005, min: -0.2, max: 1, unit: "em" })),
      row("leading", "Leading", number("leading", { step: 0.01, min: 0.6, max: 3, unit: "×" })),
      row("case", "Case", select("case", CASES, eff.case)),
      row("align", "Alignment", select("align", ALIGNS, eff.align || "left")));
  }

  colourSection(doc, pack) {
    const tokens = pack.rip.tokens || {};
    const names = Object.keys(tokens);
    if (!names.length) return h("div");
    return h("section.inspector-section",
      h("h2.inspector-heading", "Colour"),
      names.map((t) => {
        const value = (doc.tokens || {})[t] || tokens[t];
        const changed = (doc.tokens || {})[t] && doc.tokens[t] !== tokens[t];
        const input = h("input.colour-input", { type: "color", id: `t-${t}`, value: toHex(value),
          onchange: () => this.hooks.setToken(t, input.value) });
        return h("div.prop" + (changed ? ".is-changed" : ""),
          h("label.prop-label", { for: `t-${t}` }, t.replace(/^\w/, (c) => c.toUpperCase())),
          h("span.prop-field", input, h("span.colour-value", value)),
          changed ? h("button.reset", { type: "button", "aria-label": `Reset ${t}`,
            onclick: () => this.hooks.resetToken(t) }, "↺") : h("span.reset-space"));
      }));
  }
}

function resolve(styles, name, seen = []) {
  const s = styles[name] || {};
  if (s.extends && !seen.includes(name)) return Object.assign({}, resolve(styles, s.extends, seen.concat(name)), s, { extends: undefined });
  return Object.assign({}, s);
}

function toHex(c) {
  if (/^#[0-9a-f]{6}$/i.test(c)) return c;
  if (/^#[0-9a-f]{3}$/i.test(c)) return "#" + c.slice(1).split("").map((x) => x + x).join("");
  return "#000000";
}
