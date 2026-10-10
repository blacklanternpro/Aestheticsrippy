// Aestheticsrippy studio: wires the store, the sheet, the content panel and
// the inspector together.

import { h, clear, debounce, getPath, setPath, parentPath, lastKey, clone } from "./dom.js";
import { Store } from "./store.js";
import { Canvas, ICONS } from "./canvas.js";
import { ContentPanel, blankLike } from "./content-panel.js";
import { Inspector, fontsReady } from "./inspector.js";
import * as api from "./api.js";

const Rip = window.Rip;
const store = new Store();
const state = { packs: new Map(), selection: null, report: null, view: null };

const $ = (sel) => document.querySelector(sel);

// ---------------------------------------------------------------- view model

function currentPack() {
  return store.doc ? state.packs.get(store.doc.pack) : null;
}

function buildView() {
  const doc = store.doc, pack = currentPack();
  if (!doc || !pack) return null;
  return {
    rip: Rip.effectiveRip(pack.rip, doc.variant, doc.styles, doc.tokens),
    data: doc.data,
    assets: doc.assets || {},
    assetBase: doc.source ? "/content/private/" : pack.assetBase,
    packBase: pack.assetBase,
    hyphenation: window.RIP_HYPH_EN_GB,
  };
}

function imagePaths() {
  const pack = currentPack(), out = new Set();
  if (!pack) return out;
  const walk = (f) => {
    if (!f) return;
    if (f.type === "image" && f.bind && !f.bind.startsWith(".")) out.add(f.bind);
    (f.children || []).forEach(walk);
    if (f.item) walk(f.item);
    if (f.header) walk(f.header);
  };
  pack.rip.frames.forEach(walk);
  return out;
}

function assetUrl(ref) {
  const v = buildView();
  if (!v) return null;
  if (/^(data:|https?:|blob:)/.test(ref)) return ref;
  return v.assets[ref] || `${v.assetBase}${ref}`;
}

// ---------------------------------------------------------------- the sheet

const canvas = new Canvas($("#sheet-area"), {
  onSelect(sel, opts = {}) {
    state.selection = sel;
    inspector.setSelection(sel);
    if (!opts.fromPanel && sel) panel.reveal(sel.path || (sel.paths || [])[0]);
  },
  getValue: (path) => store.get(path),
  onEditInput(path, text) {
    store.setValue(path, text, { source: "canvas", label: `Edit ${panel.label(path).toLowerCase()}` });
  },
  onEditEnd() {
    store.seal();
    renderNow();
  },
  onItemAction: (action, itemPath) => itemAction(action, itemPath),
  onReport(report) {
    state.report = report;
    showStatus();
  },
  onZoom(scale) {
    $("#zoom-value").textContent = `${Math.round(scale * 100)}%`;
  },
});

function renderNow() {
  renderSoon.cancel();
  reflowSoon.cancel();
  state.view = buildView();
  canvas.render(state.view);
  if (!state.view) canvas.empty.replaceChildren(emptyState());
}
const renderSoon = debounce(renderNow, 120);
const reflowSoon = debounce(() => { state.view = buildView(); canvas.render(state.view); }, 450);

// ---------------------------------------------------------------- panels

const panel = new ContentPanel($("#content-panel"), {
  getDoc: () => store.doc,
  getFields: () => (currentPack() ? currentPack().rip.fields : null),
  setValue: (path, value, label) => store.setValue(path, value,
    { source: "panel", label: `Edit ${(label || "text").toLowerCase()}` }),
  focusPath: (path) => { canvas.selectPath(path); },
  itemAction: (action, path, opts) => itemAction(action, path, opts),
  imagePaths,
  assetUrl,
  replaceImage,
});

const inspector = new Inspector($("#inspector"), {
  getDoc: () => store.doc,
  getPack: currentPack,
  countStyleUsers: (name) => (canvas.sheet ? canvas.sheet.querySelectorAll(`[data-style~="${CSS.escape(name)}"]`).length : 0),
  setVariant: (variant) => store.commit(variant ? `Switch to ${variant} layout` : "Switch to the referenced layout",
    (d) => { d.variant = variant; }),
  setStyle: (name, key, value) => store.commit(`Change ${name} ${key}`, (d) => {
    d.styles = d.styles || {};
    d.styles[name] = Object.assign({}, d.styles[name], { [key]: value });
  }, { merge: `style:${name}:${key}` }),
  resetStyle: (name, key) => store.commit(`Reset ${name} ${key}`, (d) => {
    if (d.styles && d.styles[name]) {
      delete d.styles[name][key];
      if (!Object.keys(d.styles[name]).length) delete d.styles[name];
    }
  }),
  setToken: (t, value) => store.commit(`Change ${t} colour`, (d) => { d.tokens = Object.assign({}, d.tokens, { [t]: value }); },
    { merge: `token:${t}` }),
  resetToken: (t) => store.commit(`Reset ${t} colour`, (d) => { if (d.tokens) delete d.tokens[t]; }),
});
fontsReady.then(() => inspector.render());

// ---------------------------------------------------------------- store events

store.subscribe((change) => {
  if (change.kind === "error") return toast(change.message, "error");
  updateChrome();
  if (change.kind === "value") {
    if (change.source === "canvas") {
      reflowSoon();
      const sel = state.selection;
      if (sel && sel.path) panel.syncValue(sel.path, store.get(sel.path));
    } else {
      renderSoon();
    }
    return;
  }
  // structure, history, doc
  renderNow();
  panel.render();
  inspector.render();
});

// ---------------------------------------------------------------- list actions

function itemAction(action, itemPath, opts = {}) {
  const listPath = parentPath(itemPath), i = +lastKey(itemPath);
  const list = getPath(store.doc.data, listPath);
  if (!Array.isArray(list)) return;
  const noun = "entry";
  let focusIndex = i;
  const labels = { add: `Add ${noun}`, duplicate: `Duplicate ${noun}`, up: `Move ${noun} up`,
    down: `Move ${noun} down`, remove: `Remove ${noun}` };
  store.commit(labels[action], (d) => {
    const l = getPath(d.data, listPath);
    if (action === "add") {
      const template = opts.empty ? "" : blankLike(l[i]);
      l.splice(opts.empty ? 0 : i + 1, 0, template);
      focusIndex = opts.empty ? 0 : i + 1;
    } else if (action === "duplicate") {
      l.splice(i + 1, 0, clone(l[i]));
      focusIndex = i + 1;
    } else if (action === "up" && i > 0) {
      [l[i - 1], l[i]] = [l[i], l[i - 1]];
      focusIndex = i - 1;
    } else if (action === "down" && i < l.length - 1) {
      [l[i + 1], l[i]] = [l[i], l[i + 1]];
      focusIndex = i + 1;
    } else if (action === "remove") {
      l.splice(i, 1);
      focusIndex = Math.min(i, l.length - 1);
    }
  });
  // Keep the selection on the entry the writer is working on.
  requestAnimationFrame(() => {
    const target = `${listPath}.${focusIndex}`;
    const el = canvas.sheet && canvas.sheet.querySelector(`[data-item="${CSS.escape(target)}"]`);
    const text = el && (el.matches("[data-path]") ? el : el.querySelector("[data-path]"));
    if (text) canvas.select(text); else canvas.select(null);
    if (action === "add" && text) panel.reveal(text.dataset.path, { focus: true });
  });
}

async function replaceImage(path, file) {
  if (file.size > 12 * 1024 * 1024) return toast("That image is over 12 MB. Use a smaller copy.", "error");
  const dataUrl = await new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
  const ref = store.addAsset(dataUrl);
  store.commit("Replace photo", (d) => setPath(d.data, path, ref));
}

// ---------------------------------------------------------------- chrome

function updateChrome() {
  const doc = store.doc;
  $("#doc-name").textContent = doc ? doc.name : "No document";
  const undo = $("#undo"), redo = $("#redo");
  undo.disabled = !store.canUndo;
  redo.disabled = !store.canRedo;
  undo.title = store.canUndo ? `Undo: ${store.undoLabel}` : "Nothing to undo";
  redo.title = store.canRedo ? `Redo: ${store.redoLabel}` : "Nothing to redo";
  $("#export").disabled = !doc;
  $("#save-file").hidden = !doc;
  $("#save-file").textContent = doc && doc.source ? "Save to file" : "Save as file…";
  document.title = doc ? `${doc.name} — Aestheticsrippy` : "Aestheticsrippy";
}

function frameLabel(id) {
  const pack = currentPack();
  const labels = (pack && pack.rip.fields && pack.rip.fields.frames) || {};
  return labels[id] || id.replace(/^col-/, "").replace(/-/g, " ");
}

function showStatus() {
  const r = state.report, el = $("#fit-status");
  clear(el);
  el.className = "fit-status";
  if (!r) return;
  if (r.error) {
    el.classList.add("is-problem");
    el.append(`The pack couldn't render: ${r.error}`);
    return;
  }
  const scales = Object.values(r.fit || {});
  const min = scales.length ? Math.min(...scales) : 1;
  if (r.overflow && r.overflow.length) {
    el.classList.add("is-problem");
    const where = r.overflow.filter((f) => f !== "page-sheet").map(frameLabel);
    el.append(`Doesn't fit: ${where.join(", ") || "the sheet"} runs over, even with type at ${Math.round(min * 100)}%.`);
    const pack = currentPack();
    const other = pack && Object.keys(pack.rip.variants || {}).find((v) => v !== store.doc.variant);
    if (other) {
      el.append(" ", h("button.text-button.inline", { type: "button",
        onclick: () => store.commit(`Switch to ${other} layout`, (d) => { d.variant = other; }) },
      `Try the ${other} layout`));
    } else {
      el.append(" Shorten the text or remove an entry.");
    }
  } else if (min < 1) {
    el.append(`Fits on one page, with type at ${Math.round(min * 100)}% to make room.`);
  } else {
    el.append("Fits on one page at full size.");
  }
}

let toastTimer;
function toast(message, kind = "info") {
  const t = $("#toast");
  t.textContent = message;
  t.className = `toast is-${kind}`;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, kind === "error" ? 7000 : 3500);
}

function emptyState() {
  return h("div.empty-card",
    h("h2", "Start a document"),
    h("p", "Pick a pack to start from its reference content, rip a new one from an image, or open one of your files from content/private."),
    h("div.empty-actions",
      h("button.button.primary", { type: "button", onclick: openNewDialog }, "New from a pack"),
      h("button.button", { type: "button", onclick: openRipDialog }, "Rip an image"),
      h("button.button", { type: "button", onclick: openFileDialog }, "Open a file")));
}

// ---------------------------------------------------------------- documents

async function openDocMenu() {
  const menu = $("#doc-menu");
  if (!menu.hidden) { menu.hidden = true; return; }
  const docs = await store.list();
  clear(menu);
  const item = (label, fn, opts = {}) => h("button.menu-item" + (opts.current ? ".is-current" : ""), {
    type: "button", role: "menuitem", onclick: () => { menu.hidden = true; fn(); } }, label,
  opts.meta ? h("span.menu-meta", opts.meta) : null);
  if (docs.length) {
    menu.append(h("div.menu-label", "In this browser"));
    docs.slice(0, 12).forEach((d) => menu.append(item(d.name, () => store.open(d.id),
      { current: store.doc && store.doc.id === d.id, meta: (state.packs.get(d.pack) || {}).name || d.pack })));
    menu.append(h("hr.menu-rule"));
  }
  menu.append(item("New from a pack…", openNewDialog), item("Rip an image…", openRipDialog),
    item("Open a file…", openFileDialog));
  if (store.doc) {
    menu.append(h("hr.menu-rule"),
      item(store.doc.source ? "Save to file" : "Save as file…", saveToFile),
      item("Rename…", renameDoc), item("Duplicate", duplicateDoc), item("Delete from this browser…", deleteDoc));
  }
  menu.hidden = false;
  menu.querySelector("button").focus();
}

function previewOf(pack) {
  const scope = `preview-${pack.id}`;
  const style = h("style", Rip.pageCss(pack.rip, `[data-preview="${pack.id}"]`));
  const inner = h("div.preview-sheet", { dataset: { preview: pack.id } });
  inner.innerHTML = Rip.renderSheet(pack.rip, pack.defaultData, {
    assetBase: pack.assetBase, hyphenation: window.RIP_HYPH_EN_GB });
  const box = h("div.preview", { "aria-hidden": "true", id: scope }, style, inner);
  const fit = () => {
    const sheetPx = pack.rip.page.width_mm * 96 / 25.4;
    inner.style.transform = `scale(${box.clientWidth / sheetPx})`;
  };
  new ResizeObserver(fit).observe(box);
  requestAnimationFrame(() => {
    const sheet = inner.querySelector(".page-sheet");
    if (sheet) Rip.runFit(sheet);
    fit();
  });
  return box;
}

function openNewDialog() {
  const dlg = $("#dialog");
  clear(dlg);
  const packs = Array.from(state.packs.values());
  dlg.append(
    h("form.dialog-body", { method: "dialog" },
      h("h2", "New from a pack"),
      h("p.muted", "Each pack starts with its reference content. Replace it with yours."),
      h("div.pack-grid", packs.map((p) => h("button.pack-card", { type: "button",
        onclick: async () => {
          dlg.close();
          await store.create({ name: `${p.name} draft`, pack: p.id, data: p.defaultData });
          toast(`Started ${p.name}. Click any text on the sheet to edit it.`);
        } },
      previewOf(p), h("span.pack-name", p.name), h("span.pack-desc", p.category)))),
      h("div.dialog-actions",
        h("button.button", { type: "button", onclick: () => { dlg.close(); openRipDialog(); } }, "Rip an image instead…"),
        h("button.button", { value: "cancel" }, "Cancel"))));
  dlg.showModal();
}

// ---------------------------------------------------------------- ripping

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

function openRipDialog() {
  const dlg = $("#dialog");
  clear(dlg);
  let image = null;
  const thumb = h("img.rip-thumb", { alt: "" });
  const name = h("input.field-input", { id: "rip-name", type: "text", placeholder: "Name for the new pack" });
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true,
    onchange: () => file.files[0] && choose(file.files[0]) });
  const go = h("button.button.primary", { type: "submit", disabled: true }, "Rip it");
  const drop = h("label.rip-drop", { tabindex: 0 },
    file, thumb, h("span.rip-drop-text", h("strong", "Choose an image"), " or drop it here"),
    h("span.muted", "A photo, scan or screenshot of one printed sheet. PNG, JPEG or WebP."));
  async function choose(f) {
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { toast("Use a PNG, JPEG or WebP image.", "error"); return; }
    image = await readAsDataUrl(f);
    thumb.src = image;
    drop.classList.add("has-image");
    if (!name.value) name.value = f.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    go.disabled = false;
  }
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("is-over");
    if (e.dataTransfer.files[0]) choose(e.dataTransfer.files[0]);
  });
  const form = h("form.dialog-body.rip-form", {
    onsubmit: (e) => {
      e.preventDefault();
      if (!image || go.disabled) return;
      go.disabled = true;
      startRip(image, name.value.trim() || "Ripped reference").finally(() => { go.disabled = false; });
    } },
  h("h2", "Rip an image"),
  h("p.muted", "The harvester finds the sheet, reads the text, matches the type against the cabinet, keeps the art, " +
    "then renders the result and corrects it until it stops improving. It takes a minute or so."),
  drop,
  h("div.field", h("label.field-label", { for: "rip-name" }, "Name"), name),
  h("div.dialog-actions",
    h("button.button", { type: "button", onclick: () => dlg.close() }, "Cancel"), go));
  dlg.append(form);
  dlg.showModal();

  async function startRip(img, title) {
    let job;
    try {
      job = await api.startRip(img, title);
    } catch (e) {
      toast(`Couldn't start: ${e.message}`, "error");
      return;
    }
    const steps = h("ol.rip-steps");
    const clock = h("span.muted", "0 s");
    const body = h("div.dialog-body.rip-progress",
      h("h2", `Ripping ${title}`),
      h("div.rip-work", h("img.rip-thumb", { src: img, alt: "" }), h("div", steps, clock)),
      h("div.dialog-actions", h("button.button", { type: "button", onclick: () => dlg.close() },
        "Keep working; tell me when it's done")));
    clear(dlg);
    dlg.append(body);
    const t0 = Date.now();
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      let st;
      try { st = await api.ripStatus(job.job); } catch (e) { toast(`Lost track of the rip: ${e.message}`, "error"); return; }
      clear(steps);
      st.steps.forEach((label, i) => steps.append(h("li" + (i === st.steps.length - 1 && st.state === "running" ? ".is-now" : ""), label)));
      clock.textContent = `${Math.round((Date.now() - t0) / 1000)} s`;
      if (st.state === "error") {
        if (body.isConnected) steps.append(h("li.is-error", st.error || "Something went wrong."));
        else toast(`The rip of ${title} failed: ${st.error || "something went wrong"}.`, "error");
        return;
      }
      if (st.state === "done") {
        try {
          const packs = await api.ripPacks();
          packs.forEach((p) => state.packs.set(p.id, p));
        } catch (e) { /* fall through: reported below */ }
        const pack = state.packs.get(st.pack);
        if (!pack) {
          if (body.isConnected) steps.append(h("li.is-error", "The pack was written but could not be loaded. Reload the studio."));
          else toast("A rip finished but its pack could not be loaded. Reload the studio.", "error");
          return;
        }
        const open = async () => {
          if (dlg.open && ready.isConnected) dlg.close();
          await store.create({ name: `${pack.name} draft`, pack: pack.id, data: pack.defaultData });
          toast(`Opened ${pack.name}. Its text is yours to edit; the type styles are in the inspector.`);
        };
        // Only take over the dialog if it still shows this rip (not another dialog opened since).
        const ready = h("div.dialog-body.rip-progress",
            h("h2", `${pack.name} is ready`),
            h("div.rip-work", previewOf(pack), h("div",
              h("p.rip-score", h("strong", `${st.score}`), " / 100 against the reference"),
              h("p", `${st.live}% of the ink is live type and shapes; the rest is kept as images.`),
              h("p.muted", `${Object.keys(pack.rip.styles).length} type styles, ` +
                `${pack.rip.frames.filter((f) => f.type === "text").length} texts, ${st.seconds} s.`),
              ...(st.notes || []).map((n) => h("p.muted", n)))),
            h("div.dialog-actions",
              h("button.button", { type: "button", onclick: () => dlg.close() }, "Close"),
              h("button.button.primary", { type: "button", onclick: open }, "Open it")));
        if (dlg.open && body.isConnected) {
          clear(dlg);
          dlg.append(ready);
        } else {
          toast(`${pack.name} is ripped (${st.score} / 100). Find it under New from a pack.`);
        }
        return;
      }
    }
  }
}

async function openFileDialog() {
  const dlg = $("#dialog");
  clear(dlg);
  let files = [];
  try { files = await api.contentFiles(); } catch (e) { return toast(`Couldn't list your files: ${e.message}`, "error"); }
  const packs = Array.from(state.packs.values());
  const list = files.length ? h("ul.file-list", files.map((f) => {
    const sel = h("select.prop-input", { "aria-label": `Pack for ${f.name}` },
      packs.map((p) => h("option", { value: p.id, selected: p.id === f.pack }, p.name)));
    return h("li.file-row", h("span.file-name", f.name), sel,
      h("button.button", { type: "button", onclick: async () => {
        try {
          const data = await api.contentFile(f.name);
          const head = data._rip || {};
          dlg.close();
          const same = head.pack === sel.value;
          await store.create({ name: f.name.replace(/\.json$/, ""), pack: sel.value,
            variant: same ? head.variant || null : null, data, source: f.name,
            styles: same ? head.styles || {} : {}, tokens: same ? head.tokens || {} : {} });
          toast(`Opened ${f.name}. Edits save in this browser; use Save to file to write them back.`);
        } catch (e) { toast(`Couldn't open ${f.name}: ${e.message}`, "error"); }
      } }, "Open"));
  })) : h("p.muted", "No files yet. Put JSON content files in content/private/, or save a document there.");
  dlg.append(h("form.dialog-body", { method: "dialog" },
    h("h2", "Open a file"),
    h("p.muted", "Your content files in content/private. They stay on this computer and out of git."),
    list,
    h("div.dialog-actions", h("button.button", { value: "cancel" }, "Cancel"))));
  dlg.showModal();
}

async function renameDoc() {
  const name = prompt("Document name", store.doc.name);
  if (name && name.trim()) store.commit("Rename", (d) => { d.name = name.trim(); });
}

async function duplicateDoc() {
  const d = store.doc;
  await store.create({ name: `${d.name} copy`, pack: d.pack, variant: d.variant, data: d.data,
    styles: d.styles, tokens: d.tokens, assets: d.assets, source: null });
  toast("Duplicated. The copy lives only in this browser until you save it as a file.");
}

async function deleteDoc() {
  if (!confirm(`Delete “${store.doc.name}” from this browser? Files in content/private are not touched.`)) return;
  await store.remove(store.doc.id);
  const docs = await store.list();
  if (docs.length) await store.open(docs[0].id); else renderNow();
}

async function saveToFile() {
  const doc = store.doc;
  let name = doc.source;
  if (!name) {
    const suggested = `${doc.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "document"}.json`;
    name = prompt("Save to content/private as", suggested);
    if (!name) return;
    if (!name.endsWith(".json")) name += ".json";
  }
  const data = clone(doc.data);
  data._rip = { pack: doc.pack, ...(doc.variant ? { variant: doc.variant } : {}) };
  if (Object.keys(doc.styles || {}).length) data._rip.styles = doc.styles;
  if (Object.keys(doc.tokens || {}).length) data._rip.tokens = doc.tokens;
  try {
    await api.saveContentFile(name, data);
    if (!doc.source) store.commit("Save as file", (d) => { d.source = name; });
    toast(`Saved to content/private/${name}.`);
  } catch (e) {
    toast(`Couldn't save: ${e.message}`, "error");
  }
}

async function exportPdf() {
  const btn = $("#export");
  btn.disabled = true;
  btn.textContent = "Exporting…";
  try {
    const { blob, pages, overflow } = await api.exportPdf(store.doc);
    const a = h("a", { href: URL.createObjectURL(blob), download: `${store.doc.name}.pdf` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    if (overflow.length) toast(`Exported, but ${overflow.map(frameLabel).join(", ")} runs over in the PDF.`, "error");
    else toast(pages === 1 ? "Exported a one-page PDF." : `Exported a ${pages}-page PDF.`);
  } catch (e) {
    toast(`Export failed: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Export PDF";
  }
}

// ---------------------------------------------------------------- wiring

function wire() {
  $("#doc-button").addEventListener("click", openDocMenu);
  document.addEventListener("click", (e) => {
    const menu = $("#doc-menu");
    if (!menu.hidden && !menu.contains(e.target) && !$("#doc-button").contains(e.target)) menu.hidden = true;
  });
  $("#undo").append(ICONS.undo());
  $("#redo").append(ICONS.redo());
  $("#undo").addEventListener("click", () => { const l = store.undo(); if (l) toast(`Undone: ${l}`); });
  $("#redo").addEventListener("click", () => { const l = store.redo(); if (l) toast(`Redone: ${l}`); });
  $("#export").addEventListener("click", exportPdf);
  $("#save-file").addEventListener("click", saveToFile);
  $("#zoom-fit").addEventListener("click", () => canvas.setZoom("fit"));
  $("#zoom-actual").addEventListener("click", () => canvas.setZoom(1));
  $("#zoom-out").addEventListener("click", () => canvas.zoomBy(1 / 1.2));
  $("#zoom-in").addEventListener("click", () => canvas.zoomBy(1.2));

  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable='true'], [contenteditable='plaintext-only']");
    if (mod && e.key.toLowerCase() === "z" && !typing) {
      e.preventDefault();
      e.shiftKey ? $("#redo").click() : $("#undo").click();
    } else if (mod && e.key.toLowerCase() === "y" && !typing) {
      e.preventDefault();
      $("#redo").click();
    } else if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (store.doc) saveToFile();
    } else if (e.key === "Escape" && !typing) {
      canvas.select(null);
    }
  });

  // Phone layout: one pane at a time.
  document.querySelectorAll("[data-pane-tab]").forEach((tab) => tab.addEventListener("click", () => {
    document.body.dataset.pane = tab.dataset.paneTab;
    document.querySelectorAll("[data-pane-tab]").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
    canvas.layout();
  }));
}

async function boot() {
  wire();
  updateChrome();
  try {
    const packs = await api.ripPacks();
    packs.forEach((p) => state.packs.set(p.id, p));
  } catch (e) {
    toast(`The studio server isn't answering (${e.message}). Start it with python server.py.`, "error");
    return;
  }
  const last = localStorage.getItem("rip:lastDoc");
  const docs = await store.list();
  const target = docs.find((d) => d.id === last) || docs[0];
  if (target) {
    try { await store.open(target.id); return; } catch { /* fall through to empty state */ }
  }
  renderNow();
}

boot();
