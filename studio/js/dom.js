// Tiny DOM helpers. h("button.primary", {onclick}, "Export PDF")

export function h(spec, attrs, ...children) {
  if (attrs === null || typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs)) {
    if (attrs !== undefined && attrs !== null) children.unshift(attrs);
    attrs = {};
  }
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = [el.className, v].filter(Boolean).join(" ");
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k in el && k !== "list" && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function debounce(fn, ms) {
  let t;
  const d = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  d.flush = (...args) => { clearTimeout(t); fn(...args); };
  d.cancel = () => clearTimeout(t);
  return d;
}

/** Path helpers for "a.b.0.c" style data paths. */
export function getPath(obj, path) {
  if (!path) return obj;
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

export function setPath(obj, path, value) {
  const keys = path.split(".");
  let o = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (o[k] === undefined || o[k] === null) o[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
    o = o[k];
  }
  const last = keys[keys.length - 1];
  if (value === undefined) {
    if (Array.isArray(o)) o.splice(+last, 1); else delete o[last];
  } else {
    o[last] = value;
  }
}

export function parentPath(path) {
  const i = path.lastIndexOf(".");
  return i < 0 ? "" : path.slice(0, i);
}

export function lastKey(path) {
  return path.slice(path.lastIndexOf(".") + 1);
}

export const clone = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));

/** Visible text -> data text: drop soft hyphens and word joiners, restore plain spaces. */
export function plainText(s) {
  return s.replace(/[­⁠]/g, "").replace(/ /g, " ");
}
