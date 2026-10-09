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
