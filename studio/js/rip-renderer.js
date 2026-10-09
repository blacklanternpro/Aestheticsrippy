/*
 * Aestheticsrippy — Rip renderer.
 *
 * The one implementation of the Rip format. The studio uses it to draw the
 * live canvas; headless export (engine/rip.py) loads the same file in
 * Chromium to make PDFs. So what you edit is exactly what prints.
 *
 * A classic script (not an ES module) on purpose: it must also run from a
 * plain file:// page, where browsers refuse module imports.
 *
 *   Rip.renderSheet(rip, data, opts)  -> HTML string for <main class="page-sheet">
 *   Rip.pageCss(rip)                  -> CSS for @page, sheet and base text
 *   Rip.runFit(rootElement)           -> shrink fit-stacks, return {fit, overflow}
 *   Rip.mountPage(document, rip, data, opts)  -> whole standalone page (export)
 *
 * opts: { assets: {ref: url}, assetBase: "url/prefix/", hyphenation: patterns,
 *         editable: bool }   editable adds data-path / data-item hooks for the studio.
 */
(function (root, factory) {
  const Rip = factory();
  if (typeof module === "object" && module.exports) module.exports = Rip;
  else root.Rip = Rip;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MISSING = Symbol("missing");
  const GENERIC = {
    "Inter": "sans-serif", "Inter Tight": "sans-serif", "Archivo": "sans-serif",
    "Jost": "sans-serif", "Mrs Saint Delafield": "cursive",
  };
  const STYLE_KEYS = new Set([
    "font", "size", "weight", "stretch", "italic", "leading", "tracking", "case",
    "align", "align_last", "color", "hyphenate", "wrap", "word_spacing", "numeric",
    "scale_x", "scale_y", "extends", "indent", "opacity",
  ]);
  const NBSP = " ", WJ = "⁠", SHY = "­";

  class RipError extends Error {}

  // ------------------------------------------------------------------ data

  function splitPath(p) {
    return p.split(".").filter((s) => s !== "");
  }

  /** Resolve 'a.b.0.c' against root, or '.c' against the current repeat item. */
  function resolve(path, root, item) {
    if (path === "." || path === "$item") return item === undefined ? MISSING : item;
    let node, parts;
    if (path.startsWith(".")) { node = item; parts = splitPath(path.slice(1)); }
    else { node = root; parts = splitPath(path.replace(/^\$/, "")); }
    for (const part of parts) {
      if (node !== null && typeof node === "object" && !Array.isArray(node)) {
        if (!(part in node)) return MISSING;
        node = node[part];
      } else if (Array.isArray(node) && /^\d+$/.test(part) && +part < node.length) {
        node = node[+part];
      } else {
        return MISSING;
      }
      if (node === undefined) return MISSING;
    }
    return node;
  }

  /** Absolute data path for a bind, given the absolute path of the current item. */
  function absolutePath(bind, itemPath) {
    if (bind === "." || bind === "$item") return itemPath;
    if (bind.startsWith(".")) return itemPath ? `${itemPath}${bind}` : bind.slice(1);
    return bind.replace(/^\$\.?/, "");
  }

  function interpolate(template, root, item) {
    return template.replace(/\{([^{}]+)\}/g, (_, p) => {
      const v = resolve(p.trim(), root, item);
      return v === MISSING || v === null ? "" : String(v);
    });
  }

  function templatePaths(template, itemPath) {
    const out = [];
    template.replace(/\{([^{}]+)\}/g, (_, p) => { out.push(absolutePath(p.trim(), itemPath)); return ""; });
    return out;
  }

  function isEmpty(v) {
    return v === MISSING || v === null || v === undefined || v === "" ||
      (Array.isArray(v) && v.length === 0) ||
      (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0);
  }

  // ---------------------------------------------------------------- styles

  function resolveStyle(styles, names, overrides) {
    const list = Array.isArray(names) ? names : (names ? [names] : []);
    const out = {};
    const apply = (name, seen) => {
      if (seen.includes(name)) throw new RipError(`style cycle at '${name}'`);
      const s = styles[name];
      if (!s) throw new RipError(`unknown style '${name}'`);
      if (s.extends) apply(s.extends, seen.concat(name));
      for (const [k, v] of Object.entries(s)) if (k !== "extends") out[k] = v;
    };
    list.forEach((n) => apply(n, []));
    if (overrides) Object.assign(out, overrides);
    const unknown = Object.keys(out).filter((k) => !STYLE_KEYS.has(k));
    if (unknown.length) throw new RipError(`unknown style keys: ${unknown.sort().join(", ")}`);
    return out;
  }

  const colorValue = (c, tokens) => (c == null ? null : (tokens[c] || c));

  function num(v) {
    // Match Python's str() of floats/ints so both renderers emit identical CSS.
    return Number.isInteger(v) ? String(v) : String(v);
  }

  function styleCss(s, tokens) {
    const css = [];
    if ("font" in s) css.push(`font-family: '${s.font}', ${GENERIC[s.font] || "sans-serif"}`);
    if ("size" in s) css.push(`font-size: calc(${num(s.size)}pt * var(--fit, 1))`);
    if ("weight" in s) css.push(`font-weight: ${s.weight}`);
    if ("stretch" in s) css.push(`font-stretch: ${s.stretch}%`);
    if (s.italic) css.push("font-style: italic");
    if ("leading" in s) css.push(`line-height: ${num(s.leading)}`);
    if ("tracking" in s) css.push(`letter-spacing: ${num(s.tracking)}em`);
    if ("word_spacing" in s) css.push(`word-spacing: ${num(s.word_spacing)}em`);
    if (s.case === "upper" || s.case === "lower") css.push(`text-transform: ${s.case}case`);
    else if (s.case === "title") css.push("text-transform: capitalize");
    if ("align" in s) css.push(`text-align: ${s.align}`);
    if ("align_last" in s) css.push(`text-align-last: ${s.align_last}`);
    if (s.hyphenate) css.push("hyphens: manual");
    if ("wrap" in s) css.push(`text-wrap: ${s.wrap}`);
    if (s.numeric === "tabular") css.push("font-variant-numeric: tabular-nums");
    if ("indent" in s) css.push(`text-indent: ${num(s.indent)}mm`);
    if ("opacity" in s) css.push(`opacity: ${num(s.opacity)}`);
    const col = colorValue(s.color, tokens);
    if (col) css.push(`color: ${col}`);
    return css;
  }

  const mm = (v) => (typeof v === "number" ? `${num(v)}mm` : String(v));

  // ------------------------------------------------------------ typesetting

  /** Dashes never start a line; no one/two-letter orphans at paragraph ends. */
  function typeset(text) {
    return text
      .replace(/ ([–-]) /g, `${NBSP}$1 `)
      .replace(/(\S)—/g, `$1${WJ}—`)
      .replace(/ (\S{1,2}[.,;:!?]?)$/gm, `${NBSP}$1`);
  }

  /** Liang hyphenation from TeX patterns; soft hyphens are shown only at breaks. */
  function createHyphenator(spec) {
    if (!spec || !spec.patterns) return (t) => t;
    const left = spec.left || 3, right = spec.right || 3;
    const table = new Map();
    for (const pat of spec.patterns.split(" ")) {
      const letters = pat.replace(/\d/g, "");
      const points = [];
      let i = 0;
      for (const ch of pat) {
        if (/\d/.test(ch)) points[i] = +ch;
        else { if (points[i] === undefined) points[i] = 0; i++; }
      }
      if (points[i] === undefined) points[i] = 0;
      table.set(letters, points);
    }
    const cache = new Map();
    function hyphenateWord(word) {
      if (word.length < 7) return word;
      if (cache.has(word)) return cache.get(word);
      const w = `.${word.toLowerCase()}.`;
      const points = new Array(w.length + 1).fill(0);
      for (let i = 0; i < w.length; i++) {
        for (let j = i + 1; j <= w.length; j++) {
          const p = table.get(w.slice(i, j));
          if (p) for (let k = 0; k < p.length; k++) points[i + k] = Math.max(points[i + k], p[k]);
        }
      }
      let out = "";
      for (let i = 0; i < word.length; i++) {
        out += word[i];
        const pos = i + 2; // point after word[i] in the dotted string
        if (i + 1 >= left && word.length - (i + 1) >= right && points[pos] % 2 === 1) out += SHY;
      }
      cache.set(word, out);
      return out;
    }
    return (text) => text.replace(/[A-Za-zÀ-ɏ]+/g, hyphenateWord);
  }

  // ---------------------------------------------------------------- escape

  const escapeHtml = (s) => String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");

  // ---------------------------------------------------------------- frames

  function Builder(rip, data, opts) {
    this.rip = rip;
    this.data = data;
    this.opts = opts || {};
    this.styles = rip.styles || {};
    this.tokens = rip.tokens || {};
    this.autoId = 0;
    this.hyphenate = this.opts.hyphenator ||
      createHyphenator(this.opts.hyphenation || null);
  }

  Builder.prototype.nextId = function (kind) {
    this.autoId += 1;
    return `${kind}-${this.autoId}`;
  };

  Builder.prototype.placeCss = function (f, absolute) {
    const css = [];
    if (absolute) {
      css.push("position: absolute");
      if ("x" in f) css.push(`left: ${mm(f.x)}`);
      if ("y" in f) css.push(`top: ${mm(f.y)}`);
      if ("right" in f) css.push(`right: ${mm(f.right)}`);
      if ("bottom" in f) css.push(`bottom: ${mm(f.bottom)}`);
    }
    if ("w" in f) css.push(`width: ${mm(f.w)}`);
    if ("h" in f) css.push(`height: ${mm(f.h)}`);
    if ("z" in f) css.push(`z-index: ${Math.trunc(f.z)}`);
    if ("mt" in f) css.push(`margin-top: ${mm(f.mt)}`);
    if ("mb" in f) css.push(`margin-bottom: ${mm(f.mb)}`);
    if ("pad" in f) css.push(`padding: ${mm(f.pad)}`);
    if ("rotate" in f) css.push(`transform: rotate(${num(f.rotate)}deg)`);
    return css;
  };

  Builder.prototype.boundValue = function (f, ctx) {
    if ("bind" in f) return resolve(f.bind, this.data, ctx.item);
    if ("text" in f) return interpolate(f.text, this.data, ctx.item);
    return MISSING;
  };

  Builder.prototype.attrs = function (f, kind, css, extraClass, ctx, extra) {
    const fid = f.id || this.nextId(kind);
    const cls = `rip-${kind}` + (extraClass ? ` ${extraClass}` : "") + (f.class ? ` ${f.class}` : "");
    let out = `data-frame="${escapeHtml(fid)}" class="${cls}"`;
    if (css.length) out += ` style="${css.join("; ")}"`;
    if (this.opts.editable) {
      if (ctx && ctx.itemRoot) out += ` data-item="${escapeHtml(ctx.itemRoot)}"`;
      if (extra) out += extra;
    }
    return out;
  };

  Builder.prototype.render = function (f, ctx, absolute) {
    const kind = f.type || "text";
    const fn = this[`r_${kind}`];
    if (!fn) throw new RipError(`unknown frame type '${kind}'`);
    return fn.call(this, f, ctx, absolute || f.place === "absolute");
  };

  Builder.prototype.r_text = function (f, ctx, absolute) {
    let value = this.boundValue(f, ctx);
    if (isEmpty(value) && !f.keep) return "";
    const isList = Array.isArray(value);
    if (isList) value = value.filter((v) => !isEmpty(v)).map(String).join(f.join === undefined ? "\n" : f.join);
    let text = isEmpty(value) ? "" : String(value);
    if (f.prefix && text) text = f.prefix + text;
    if (f.suffix && text) text = text + f.suffix;

    const s = resolveStyle(this.styles, f.style, f.with);
    const css = this.placeCss(f, absolute).concat(styleCss(s, this.tokens));
    if (f.typeset !== false) text = typeset(text);
    if (s.hyphenate) text = this.hyphenate(text);
    let body = text.split("\n").map(escapeHtml).join("<br>");

    const sx = s.scale_x, sy = s.scale_y;
    if (sx || sy) {
      const origin = { center: "center", right: "right" }[s.align || "left"] || "left";
      body = `<span class="rip-scaled" style="display:inline-block; transform:scale(${sx || 1}, ${sy || 1}); ` +
        `transform-origin:${origin} bottom">${body}</span>`;
    }

    let extra = "";
    if (this.opts.editable) {
      const style = Array.isArray(f.style) ? f.style.join(" ") : (f.style || "");
      extra += ` data-style="${escapeHtml(style)}"`;
      if ("bind" in f) {
        const path = absolutePath(f.bind, ctx.itemPath);
        extra += ` data-path="${escapeHtml(path)}"` + (isList ? ` data-kind="list"` : "");
      } else if ("text" in f) {
        extra += ` data-paths="${escapeHtml(templatePaths(f.text, ctx.itemPath).join(" "))}"`;
      }
    }
    const tag = f.tag || "div";
    return `<${tag} ${this.attrs(f, "text", css, "", ctx, extra)}>${body}</${tag}>`;
  };

  Builder.prototype.findAsset = function (ref) {
    if (/^(https?:|data:|blob:)/.test(ref)) return ref;
    const assets = this.opts.assets || {};
    if (assets[ref]) return assets[ref];
    if (this.opts.assetBase) return this.opts.assetBase + ref;
    return null;
  };

  Builder.prototype.r_image = function (f, ctx, absolute) {
    const ref = ("bind" in f || "text" in f) ? this.boundValue(f, ctx) : (f.src === undefined ? MISSING : f.src);
    if (isEmpty(ref)) return "";
    const src = this.findAsset(String(ref));
    if (!src) throw new RipError(`image asset not found: ${ref}`);
    const css = this.placeCss(f, absolute);
    const img = [`object-fit: ${f.fit || "cover"}`, `object-position: ${f.position || "center"}`,
      "width: 100%", "height: 100%", "display: block"];
    if (f.filter === "grayscale") img.push("filter: grayscale(1)");
    else if (f.filter) img.push(`filter: ${f.filter}`);
    let extra = "";
    if (this.opts.editable && "bind" in f) extra = ` data-path="${escapeHtml(absolutePath(f.bind, ctx.itemPath))}" data-kind="image"`;
    return `<div ${this.attrs(f, "image", css, "", ctx, extra)}>` +
      `<img src="${escapeHtml(src)}" alt="" style="${img.join("; ")}"></div>`;
  };

  Builder.prototype.r_rule = function (f, ctx, absolute) {
    const g = Object.assign({}, f);
    delete g.w;
    const css = this.placeCss(g, absolute);
    const weight = f.weight === undefined ? 0.5 : f.weight;
    const col = colorValue(f.color === undefined ? "ink" : f.color, this.tokens) || "currentColor";
    css.push(`border-top: ${num(weight)}pt solid ${col}`, "height: 0");
    css.push(f.w !== undefined && f.w !== null ? `width: ${mm(f.w)}` : "width: 100%");
    const align = f.align || "left";
    if (align === "center") css.push("margin-left: auto; margin-right: auto");
    else if (align === "right") css.push("margin-left: auto");
    return `<div ${this.attrs(f, "rule", css, "", ctx)}></div>`;
  };

  Builder.prototype.r_space = function (f) {
    return `<div class="rip-space" style="height: ${mm(f.h === undefined ? 2 : f.h)}; flex: none"></div>`;
  };

  Builder.prototype.children = function (f, ctx) {
    const inner = { item: ctx.item, itemPath: ctx.itemPath };
    let first = true;
    return (f.children || []).map((c) => {
      // The item root marker goes on the first rendered element only.
      const out = this.render(c, first ? ctx : inner);
      if (out) first = false;
      return out;
    }).join("");
  };

  Builder.prototype.containerStyle = function (f) {
    return (f.style || f.with) ? styleCss(resolveStyle(this.styles, f.style, f.with), this.tokens) : [];
  };

  Builder.prototype.r_stack = function (f, ctx, absolute) {
    const inner = this.children(f, { item: ctx.item, itemPath: ctx.itemPath });
    if (!inner && !f.keep) return "";
    const css = this.placeCss(f, absolute).concat(this.containerStyle(f));
    css.push("display: flex", "flex-direction: column", `gap: ${mm(f.gap === undefined ? 0 : f.gap)}`);
    if (f.justify) css.push(`justify-content: ${f.justify}`);
    if (f.items) css.push(`align-items: ${f.items}`);
    let extraClass = "";
    if (f.fit) { css.push("overflow: hidden", "--fit: 1"); extraClass = "rip-fit"; }
    let a = this.attrs(f, "stack", css, extraClass, ctx);
    if (f.fit) {
      const min = f.fit.min === undefined ? 0.85 : f.fit.min;
      a += ` data-fit-min="${pyFloat(min)}"`;
      if (f.fit.group) a += ` data-fit-group="${escapeHtml(String(f.fit.group))}"`;
    }
    return `<div ${a}>${inner}</div>`;
  };

  function pyFloat(v) {
    // Python's float() repr: 1 -> "1.0", 0.85 -> "0.85"
    return Number.isInteger(v) ? `${v}.0` : String(v);
  }

  Builder.prototype.r_row = function (f, ctx, absolute) {
    const inner = this.children(f, { item: ctx.item, itemPath: ctx.itemPath });
    if (!inner && !f.keep) return "";
    const css = this.placeCss(f, absolute).concat(this.containerStyle(f));
    if (f.cols) {
      css.push("display: grid", `grid-template-columns: ${f.cols.map(mm).join(" ")}`,
        `column-gap: ${mm(f.gap === undefined ? 0 : f.gap)}`, `align-items: ${f.align || "start"}`);
    } else {
      css.push("display: flex", `justify-content: ${f.justify || "space-between"}`,
        `align-items: ${f.align || "baseline"}`, `gap: ${mm(f.gap === undefined ? 0 : f.gap)}`);
    }
    return `<div ${this.attrs(f, "row", css, "", ctx)}>${inner}</div>`;
  };

  Builder.prototype.r_repeat = function (f, ctx, absolute) {
    const items = resolve(f.bind, this.data, ctx.item);
    if (isEmpty(items)) return "";
    if (!Array.isArray(items)) throw new RipError(`repeat bind '${f.bind}' is not a list`);
    if (!f.item) throw new RipError("repeat needs an 'item' frame");
    const listPath = absolutePath(f.bind, ctx.itemPath);
    const parts = items.map((entry, i) => {
      const child = JSON.parse(JSON.stringify(f.item));
      delete child.id;
      const itemPath = `${listPath}.${i}`;
      return this.render(child, { item: entry, itemPath, itemRoot: itemPath });
    });
    const css = this.placeCss(f, absolute).concat(["display: flex", "flex-direction: column",
      `gap: ${mm(f.gap === undefined ? 0 : f.gap)}`]);
    const extra = this.opts.editable ? ` data-list="${escapeHtml(listPath)}"` : "";
    return `<div ${this.attrs(f, "repeat", css, "", ctx, extra)}>${parts.join("")}</div>`;
  };

  // -------------------------------------------------------------- variants

  function applyVariant(rip, name) {
    if (!name) return rip;
    const v = (rip.variants || {})[name];
    if (!v) throw new RipError(`unknown variant '${name}'`);
    const out = JSON.parse(JSON.stringify(rip));
    const byId = {};
    out.frames.forEach((f) => { if (f.id) byId[f.id] = f; });
    for (const [fid, patch] of Object.entries(v.frames || {})) {
      if (!byId[fid]) throw new RipError(`variant '${name}' patches unknown frame '${fid}'`);
      Object.assign(byId[fid], patch);
    }
    for (const [sname, patch] of Object.entries(v.styles || {})) {
      out.styles = out.styles || {};
      out.styles[sname] = Object.assign({}, out.styles[sname] || {}, patch);
    }
    out.variant = name;
    return out;
  }

  /** Document-level style overrides (the studio's style edits) on top of the pack. */
  function applyStyleOverrides(rip, overrides) {
    if (!overrides || !Object.keys(overrides).length) return rip;
    const out = JSON.parse(JSON.stringify(rip));
    for (const [name, patch] of Object.entries(overrides)) {
      out.styles[name] = Object.assign({}, out.styles[name] || {}, patch);
    }
    return out;
  }

  /** Document-level colour token overrides (paper, ink, accents). */
  function applyTokenOverrides(rip, tokens) {
    if (!tokens || !Object.keys(tokens).length) return rip;
    const out = JSON.parse(JSON.stringify(rip));
    out.tokens = Object.assign({}, out.tokens || {}, tokens);
    return out;
  }

  /** Pack + variant + the document's own style and token edits = what renders. */
  function effectiveRip(rip, variant, styles, tokens) {
    return applyTokenOverrides(applyStyleOverrides(applyVariant(rip, variant), styles), tokens);
  }

  // -------------------------------------------------------------- document

  /** Sheet CSS. `scope` prefixes every selector so several sheets can share a page. */
  function pageCss(rip, scope) {
    const p = rip.page, tokens = rip.tokens || {};
    const paper = colorValue(p.paper || "#ffffff", tokens);
    const ink = colorValue(p.ink || "ink", tokens) || "#000";
    const base = (rip.styles || {}).base ? styleCss(resolveStyle(rip.styles, "base"), tokens).join("; ") : "";
    const sc = scope ? `${scope} ` : "";
    const page = scope ? "" : `@page { size: ${num(p.width_mm)}mm ${num(p.height_mm)}mm; margin: 0; }\n`;
    return `${page}${sc}.page-sheet, ${sc}.page-sheet * { box-sizing: border-box; margin: 0; padding: 0; }
${sc}.page-sheet { position: relative; width: ${num(p.width_mm)}mm; height: ${num(p.height_mm)}mm; overflow: hidden;
  font-size: 16px; font-weight: 400; font-style: normal; font-stretch: 100%; line-height: normal;
  letter-spacing: normal; word-spacing: normal; text-align: left; text-transform: none; text-indent: 0;
  white-space: normal; font-variation-settings: normal; font-feature-settings: normal;
  background: ${paper}; color: ${ink}; text-rendering: geometricPrecision; -webkit-font-smoothing: antialiased;
  font-kerning: normal; font-optical-sizing: auto; ${base} }
${sc}.page-sheet .rip-text { overflow-wrap: break-word; }
${sc}.page-sheet .rip-image img { user-select: none; }`;
  }

  function renderSheet(rip, data, opts) {
    const b = new Builder(rip, data, opts);
    const frames = (rip.frames || []).map((f) => b.render(f, { item: undefined, itemPath: "" }, true)).join("\n");
    return `<main class="page-sheet" data-rip="${escapeHtml(rip.id || "")}">\n${frames}\n</main>`;
  }

  // ------------------------------------------------------------------- fit

  function overflows(el) {
    return el.scrollHeight > el.clientHeight + 0.5 || el.scrollWidth > el.clientWidth + 0.5;
  }

  /** Shrink each fit-stack's type in 1% steps (shared within a group); report overflow. */
  function runFit(root) {
    const report = { fit: {}, overflow: [] };
    root.querySelectorAll(".rip-fit").forEach((el) => {
      const min = parseFloat(el.dataset.fitMin || "0.85");
      let scale = 1;
      el.style.setProperty("--fit", "1");
      while (overflows(el) && scale - 0.01 >= min - 1e-9) {
        scale = Math.round((scale - 0.01) * 100) / 100;
        el.style.setProperty("--fit", String(scale));
      }
      report.fit[el.dataset.frame] = scale;
    });
    const groups = {};
    root.querySelectorAll(".rip-fit[data-fit-group]").forEach((el) => {
      const g = el.dataset.fitGroup, s = report.fit[el.dataset.frame];
      groups[g] = Math.min(groups[g] === undefined ? 1 : groups[g], s);
    });
    root.querySelectorAll(".rip-fit[data-fit-group]").forEach((el) => {
      const s = groups[el.dataset.fitGroup];
      el.style.setProperty("--fit", String(s));
      report.fit[el.dataset.frame] = s;
    });
    root.querySelectorAll("[data-frame]").forEach((el) => {
      if (el.style.height && overflows(el)) report.overflow.push(el.dataset.frame);
    });
    const sheet = root.classList && root.classList.contains("page-sheet") ? root : root.querySelector(".page-sheet");
    if (sheet && overflows(sheet)) report.overflow.push("page-sheet");
    return report;
  }

  /** Build a whole standalone page (used for headless export). */
  function mountPage(doc, rip, data, opts) {
    opts = opts || {};
    rip = effectiveRip(rip, opts.variant, opts.styles, opts.tokens);
    const style = doc.createElement("style");
    style.textContent = `${pageCss(rip)}
html, body { margin: 0; background: #d9d9d6; }
body { display: flex; justify-content: center; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
@media print { html, body { background: transparent; } body { display: block; } }`;
    doc.head.appendChild(style);
    doc.title = rip.name || rip.id || "Rip";
    doc.documentElement.lang = rip.lang || "en";
    doc.body.innerHTML = renderSheet(rip, data, opts);
    const finish = () => {
      window.__ripReport = runFit(doc.querySelector(".page-sheet"));
      doc.documentElement.dataset.ripReady = "1";
    };
    (doc.fonts ? doc.fonts.ready : Promise.resolve()).then(finish);
  }

  return {
    MISSING, RipError, resolve, absolutePath, interpolate, isEmpty, resolveStyle, styleCss,
    typeset, createHyphenator, applyVariant, applyStyleOverrides, applyTokenOverrides, effectiveRip,
    pageCss, renderSheet,
    runFit, mountPage, STYLE_KEYS: Array.from(STYLE_KEYS),
  };
});
