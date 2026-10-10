// Unit tests for the Rip renderer: node --test "studio/tests/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const Rip = require("../js/rip-renderer.js");
const patterns = require("../js/hyph-en-gb.js");

const RIP = {
  id: "t", page: { width_mm: 100, height_mm: 100 },
  styles: { body: { font: "Inter", size: 9 }, just: { extends: "body", align: "justify", hyphenate: true } },
  frames: [
    { id: "name", type: "text", style: "body", text: "{person.first} {person.last}", x: 5, y: 5 },
    { id: "list", type: "stack", x: 5, y: 20, w: 90, h: 70, fit: { min: 0.8, group: "g" }, children: [
      { type: "repeat", bind: "items", item: { type: "stack", children: [
        { type: "text", style: "body", bind: ".title" },
        { type: "text", style: "just", bind: ".note" } ] } } ] },
  ],
  variants: { wide: { frames: { list: { w: 95 } }, styles: { body: { size: 10 } } } },
};
const DATA = { person: { first: "Ada", last: "Lovelace" },
  items: [{ title: "One", note: "first" }, { title: "Two" }] };

test("resolve and absolute paths", () => {
  assert.equal(Rip.resolve("person.first", DATA), "Ada");
  assert.equal(Rip.resolve(".title", DATA, DATA.items[1]), "Two");
  assert.equal(Rip.resolve("items.0.note", DATA), "first");
  assert.equal(Rip.resolve("nope.x", DATA), Rip.MISSING);
  assert.equal(Rip.absolutePath(".title", "items.1"), "items.1.title");
  assert.equal(Rip.absolutePath(".", "items.1"), "items.1");
  assert.equal(Rip.absolutePath("summary", "items.1"), "summary");
});

test("interpolation, repeat, and dropped empty fields", () => {
  const html = Rip.renderSheet(RIP, DATA, {});
  assert.match(html, /Ada Lovelace/);
  assert.equal((html.match(/>One</g) || []).length, 1);
  assert.equal((html.match(/>first</g) || []).length, 1);
  assert.match(html, /data-fit-min="0.8" data-fit-group="g"/);
  assert.doesNotMatch(html, /data-path/); // editor hooks only when asked
});

test("editable mode adds data paths and item markers", () => {
  const html = Rip.renderSheet(RIP, DATA, { editable: true });
  assert.match(html, /data-path="items\.0\.title"/);
  assert.match(html, /data-item="items\.1"/);
  assert.match(html, /data-list="items"/);
  assert.match(html, /data-paths="person\.first person\.last"/);
});

test("variants patch frames and styles without mutating the pack", () => {
  const v = Rip.applyVariant(RIP, "wide");
  assert.equal(v.frames[1].w, 95);
  assert.equal(v.styles.body.size, 10);
  assert.equal(RIP.frames[1].w, 90);
  assert.throws(() => Rip.applyVariant(RIP, "nope"));
});

test("style overrides layer over pack styles", () => {
  const o = Rip.applyStyleOverrides(RIP, { body: { weight: 500 } });
  assert.equal(o.styles.body.weight, 500);
  assert.equal(o.styles.body.size, 9);
  assert.equal(RIP.styles.body.weight, undefined);
});

test("typeset binds dashes and prevents short orphans", () => {
  const out = Rip.typeset("Licence (LF – Forklift) and work—resolving it a");
  assert.ok(out.includes("LF – Forklift"));
  assert.ok(out.includes("work⁠—resolving"));
  assert.ok(out.endsWith("it a"));
});

test("hyphenation inserts soft hyphens at TeX pattern points", () => {
  const h = Rip.createHyphenator(patterns);
  assert.equal(h("specifically").replace(/­/g, "-"), "spe-cific-ally");
  assert.equal(h("short"), "short");
});

test("shipped packs render with their default data and every variant", () => {
  for (const pack of ["saraiva-resume", "dupont-letter"]) {
    const dir = path.join(__dirname, "..", "..", "design-packs", pack);
    const rip = JSON.parse(fs.readFileSync(path.join(dir, "rip.json"), "utf8"));
    const data = JSON.parse(fs.readFileSync(path.join(dir, "default-data.json"), "utf8"));
    const opts = { assetBase: "assets/", hyphenation: patterns, editable: true };
    assert.match(Rip.renderSheet(rip, data, opts), new RegExp(`data-rip="${pack}"`));
    for (const v of Object.keys(rip.variants || {})) Rip.renderSheet(Rip.applyVariant(rip, v), data, opts);
  }
});

test("a repeat's header row renders once, above the items, outside the item context", () => {
  const rip = { id: "h", page: { width_mm: 80, height_mm: 60 }, styles: { head: { font: "Inter", weight: 700 }, row: { font: "Inter" } },
    frames: [{ id: "list", type: "repeat", bind: "rows", x: 5, y: 5, header_gap: 1.5,
      header: { type: "row", cols: [40, 20], children: [
        { type: "text", style: "head", bind: "rows_head.c1" }, { type: "text", style: "head", bind: "rows_head.c2" }] },
      item: { type: "row", cols: [40, 20], children: [
        { type: "text", style: "row", bind: ".c1" }, { type: "text", style: "row", bind: ".c2" }] } }] };
  const data = { rows_head: { c1: "Item", c2: "Price" }, rows: [{ c1: "Oak table", c2: "1,200" }, { c1: "Lamp", c2: "650" }] };
  const html = Rip.renderSheet(rip, data, { editable: true });
  assert.equal((html.match(/>Item</g) || []).length, 1);
  assert.ok(html.indexOf(">Item<") < html.indexOf(">Oak table<"));
  assert.match(html, /data-path="rows_head\.c1"/);
  assert.match(html, /margin-bottom: 1\.5mm/);
  // No rows, no header: an empty list leaves nothing behind.
  assert.doesNotMatch(Rip.renderSheet(rip, { rows_head: data.rows_head, rows: [] }), />Item</);
});

test("path frames set text along a curve, editable and styled", () => {
  const rip = { id: "p", page: { width_mm: 80, height_mm: 80 }, tokens: { ink: "#112233" },
    styles: { arc: { font: "Inter", size: 12, weight: 700, tracking: 0.1, case: "upper", color: "ink" } },
    frames: [{ id: "ring", type: "path", style: "arc", bind: "ring", x: 10, y: 10, w: 40, h: 40,
      points: [[0, 20], [20, 0], [40, 20]], offset: 2.5 }] };
  const html = Rip.renderSheet(rip, { ring: "Last Saturday" }, { editable: true });
  assert.match(html, /data-frame="ring" class="rip-path"/);
  assert.match(html, /<svg[^>]*overflow: visible/);
  // Points in mm become CSS px (96 per inch) in the path.
  assert.match(html, /<path id="[^"]+" d="M0 75\.59 L75\.59 0 L151\.18 75\.59"/);
  assert.match(html, /<textPath href="#[^"]+" startOffset="9\.45">LAST SATURDAY<\/textPath>/);
  assert.match(html, /letter-spacing: 0\.1em/);
  assert.match(html, /color: #112233/);
  assert.match(html, /data-path="ring"/);
  // Two path frames on one sheet get distinct path ids.
  const two = Rip.renderSheet({ ...rip, frames: [rip.frames[0], { ...rip.frames[0], id: "ring2" }] }, { ring: "A" });
  const ids = [...two.matchAll(/<path id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, 2);
});

test("pitched path frames place letters at even steps, upright or along the curve", () => {
  const base = { id: "stem", type: "path", style: "s", bind: "t", x: 0, y: 0, w: 10, h: 40,
    points: [[5, 0], [5, 40]], offset: 5, pitch: 10 };
  const rip = { id: "q", page: { width_mm: 50, height_mm: 50 }, styles: { s: { font: "Inter", size: 20 } },
    frames: [base] };
  const html = Rip.renderSheet(rip, { t: "LAS" });
  const glyphs = [...html.matchAll(/<text x="([\d.]+)" y="([\d.]+)"[^>]*>(.)<\/text>/g)];
  assert.deepEqual(glyphs.map((m) => m[3]), ["L", "A", "S"]);
  // Down a vertical stem: same x, y every 10 mm starting 5 mm in.
  assert.deepEqual(glyphs.map((m) => +m[2]), [18.9, 56.69, 94.49]);
  assert.ok(glyphs.every((m) => m[1] === "18.9"));
  assert.match(html, /text-anchor="middle"/);
  // Along the curve the letters turn with it (90deg on a downward stem); upright they don't.
  assert.match(html, /rotate\(90 18\.9 18\.9\)/);
  const up = Rip.renderSheet({ ...rip, frames: [{ ...base, upright: true }] }, { t: "LAS" });
  assert.doesNotMatch(up, /rotate\(/);
});

test("a pitched path frame can turn each letter by its own angle", () => {
  const rip = { id: "r", page: { width_mm: 60, height_mm: 60 }, styles: { s: { font: "Inter", size: 18 } },
    frames: [{ id: "rn", type: "path", style: "s", bind: "t", x: 0, y: 0, w: 60, h: 20,
      points: [[5, 10], [55, 10]], pitch: 12, upright: true, angles: [14, -80, 0, 95] }] };
  const html = Rip.renderSheet(rip, { t: "LAST" });
  const turns = [...html.matchAll(/rotate\(([-\d.]+) ([\d.]+) ([\d.]+)\)/g)].map((m) => +m[1]);
  assert.deepEqual(turns, [14, -80, 95]);     // 0 needs no transform
  const glyphs = [...html.matchAll(/>(.)<\/text>/g)].map((m) => m[1]);
  assert.deepEqual(glyphs, ["L", "A", "S", "T"]);
});

test("stops place each letter at its own distance along the path, pitch carries on past them", () => {
  const rip = { id: "st", page: { width_mm: 60, height_mm: 60 }, styles: { s: { font: "Inter", size: 18 } },
    frames: [{ id: "sp", type: "path", style: "s", bind: "t", x: 0, y: 0, w: 60, h: 10,
      points: [[0, 5], [60, 5]], pitch: 10, upright: true, stops: [2, 7, 30] }] };
  // A fourth letter (the text was edited longer) continues at the pitch after the last stop.
  const html = Rip.renderSheet(rip, { t: "LAST" });
  const xs = [...html.matchAll(/<text x="([\d.]+)"/g)].map((m) => +m[1]);
  const px = (mmv) => Math.round(mmv * 96 / 25.4 * 100) / 100;
  assert.deepEqual(xs, [px(2), px(7), px(30), px(40)]);
  // A letter a rounding hair past the path's end still lands, at the end.
  const end = Rip.renderSheet({ ...rip, frames: [{ ...rip.frames[0], stops: [0, 60.004] }] }, { t: "LA" });
  assert.equal([...end.matchAll(/<text x="([\d.]+)"/g)].length, 2);
});

test("box frames draw fills, outlines and ellipses", () => {
  const rip = { id: "b", page: { width_mm: 50, height_mm: 50 }, tokens: { accent: "#ff0066" }, styles: {},
    frames: [
      { id: "panel", type: "box", x: 1, y: 2, w: 10, h: 5, fill: "accent" },
      { id: "ring", type: "box", x: 5, y: 5, w: 8, h: 4, stroke: "#000", stroke_weight: 1, radius: "ellipse", rotate: -4 },
    ] };
  const html = Rip.renderSheet(rip, {});
  assert.match(html, /data-frame="panel" class="rip-box" style="[^"]*background: #ff0066/);
  assert.match(html, /data-frame="ring"[^>]*border: 1pt solid #000[^>]*border-radius: 50%/);
  assert.match(html, /transform: rotate\(-4deg\)/);
});
