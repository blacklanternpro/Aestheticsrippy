// Document store: the Rip document being edited, its undo history, and
// persistence in IndexedDB (so undo survives a reload).
//
// A document is { id, name, pack, variant, data, styles, tokens, assets, source, updated }.
// `assets` holds uploaded images as data URLs, referenced from data as "asset:<id>";
// it sits outside the undo snapshots so photos aren't copied into every step.
// Every change goes through commit(), which records an undo step. Consecutive
// commits with the same merge key (one typing session in one field) collapse
// into a single step.

import { clone, getPath, setPath } from "./dom.js";

const DB_NAME = "aestheticsrippy";
const DB_STORE = "docs";
const HISTORY_LIMIT = 150;
const MERGE_WINDOW_MS = 1500;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(DB_STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const t = db.transaction(DB_STORE, mode);
    const out = fn(t.objectStore(DB_STORE));
    t.oncomplete = () => resolve(out && "result" in out ? out.result : out);
    t.onerror = () => reject(t.error);
  });
}

const SNAPSHOT_KEYS = ["data", "styles", "tokens", "variant", "name"];

export class Store {
  constructor() {
    this.doc = null;
    this.past = [];
    this.future = [];
    this.listeners = new Set();
    this.lastMerge = null;
    this.saveTimer = null;
    this.storageOk = typeof indexedDB !== "undefined";
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  emit(change) {
    for (const fn of this.listeners) fn(change);
  }

  // -- documents -------------------------------------------------------------

  async list() {
    if (!this.storageOk) return [];
    try {
      const all = await tx("readonly", (s) => s.getAll());
      return all.map((r) => ({ id: r.doc.id, name: r.doc.name, pack: r.doc.pack, updated: r.doc.updated }))
        .sort((a, b) => b.updated - a.updated);
    } catch {
      return [];
    }
  }

  async open(id) {
    const rec = await tx("readonly", (s) => s.get(id));
    if (!rec) throw new Error("That document is no longer saved in this browser.");
    this.doc = rec.doc;
    this.past = rec.past || [];
    this.future = rec.future || [];
    this.lastMerge = null;
    localStorage.setItem("rip:lastDoc", id);
    this.emit({ kind: "doc" });
  }

  async create({ name, pack, variant = null, data, styles = {}, tokens = {}, assets = {}, source = null }) {
    this.doc = {
      id: `doc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      name, pack, variant, data: clone(data), styles: clone(styles), tokens: clone(tokens),
      assets: clone(assets), source, updated: Date.now(),
    };
    this.past = [];
    this.future = [];
    this.lastMerge = null;
    localStorage.setItem("rip:lastDoc", this.doc.id);
    await this.persist();
    this.emit({ kind: "doc" });
    return this.doc;
  }

  async remove(id) {
    await tx("readwrite", (s) => s.delete(id));
    if (this.doc && this.doc.id === id) {
      this.doc = null;
      this.emit({ kind: "doc" });
    }
  }

  persist() {
    if (!this.storageOk || !this.doc) return Promise.resolve();
    const rec = { id: this.doc.id, doc: this.doc, past: this.past, future: this.future };
    return tx("readwrite", (s) => s.put(rec)).catch((e) => {
      this.emit({ kind: "error", message: `Couldn't save to this browser: ${e.message}` });
    });
  }

  schedulePersist() {
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.persist(), 300);
  }

  // -- editing -----------------------------------------------------------------

  snapshot() {
    const s = {};
    for (const k of SNAPSHOT_KEYS) s[k] = clone(this.doc[k]);
    return s;
  }

  restore(s) {
    for (const k of SNAPSHOT_KEYS) this.doc[k] = clone(s[k]);
  }

  /**
   * Apply `mutate(doc)` as one undoable step.
   * opts.merge: steps with the same key within a short window collapse into one.
   * opts.kind: "value" (text only: no structure change) or "structure".
   * opts.source: who made the change, so that view can skip redrawing itself.
   */
  commit(label, mutate, opts = {}) {
    if (!this.doc) return;
    const now = Date.now();
    const merging = opts.merge && this.lastMerge &&
      this.lastMerge.key === opts.merge && now - this.lastMerge.at < MERGE_WINDOW_MS;
    if (!merging) {
      this.past.push({ label, state: this.snapshot() });
      if (this.past.length > HISTORY_LIMIT) this.past.shift();
    }
    this.lastMerge = opts.merge ? { key: opts.merge, at: now } : null;
    this.future = [];
    mutate(this.doc);
    this.doc.updated = now;
    this.schedulePersist();
    this.emit({ kind: opts.kind || "structure", source: opts.source, label });
  }

  /** End a merge run (e.g. when a text field loses focus). */
  seal() {
    this.lastMerge = null;
  }

  setValue(path, value, opts = {}) {
    this.commit(opts.label || "Edit text", (d) => setPath(d.data, path, value),
      { merge: opts.merge === undefined ? `value:${path}` : opts.merge, kind: "value", source: opts.source });
  }

  get(path) {
    return getPath(this.doc.data, path);
  }

  /** Keep an uploaded image with the document; returns the ref to put in data. */
  addAsset(dataUrl) {
    let hash = 0;
    for (let i = 0; i < dataUrl.length; i += 97) hash = (hash * 31 + dataUrl.charCodeAt(i)) >>> 0;
    const ref = `asset:${hash.toString(36)}${dataUrl.length.toString(36)}`;
    this.doc.assets = this.doc.assets || {};
    this.doc.assets[ref] = dataUrl;
    return ref;
  }

  undo() {
    if (!this.past.length) return null;
    const step = this.past.pop();
    this.future.push({ label: step.label, state: this.snapshot() });
    this.restore(step.state);
    this.lastMerge = null;
    this.doc.updated = Date.now();
    this.schedulePersist();
    this.emit({ kind: "history", label: step.label });
    return step.label;
  }

  redo() {
    if (!this.future.length) return null;
    const step = this.future.pop();
    this.past.push({ label: step.label, state: this.snapshot() });
    this.restore(step.state);
    this.lastMerge = null;
    this.doc.updated = Date.now();
    this.schedulePersist();
    this.emit({ kind: "history", label: step.label });
    return step.label;
  }

  get canUndo() { return this.past.length > 0; }
  get canRedo() { return this.future.length > 0; }
  get undoLabel() { return this.past.length ? this.past[this.past.length - 1].label : ""; }
  get redoLabel() { return this.future.length ? this.future[this.future.length - 1].label : ""; }
}
