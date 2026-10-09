# Aestheticsrippy

A lab for ripping high-end typographic print design — posters, receipts, invoices, résumés — into documents you can edit and print at full fidelity.

The plan for the rebuild lives in the project doc *Aestheticsrippy — Review & Build Plan*. Phases 0–2 (clean and measure, the Rip core, the studio) are on the `rebuild` branch.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Optional: put `GEMINI_API_KEY=...` in a `.env` file in the project root for the harvester.

## Commands

| What | Command |
| --- | --- |
| Studio | `python server.py` → http://127.0.0.1:8080/studio/ (old editor: `/studio/legacy/`) |
| Render a Rip pack with your own content | `python -m engine.rip render saraiva-resume --data content/private/me.json --out export/me.pdf --png` |
| …with a layout variant | add `--variant dense` |
| Rebuild Rip packs' previews | `python -m engine.rip build --all` |
| Compile one pack to PDF | `python -m engine.compiler --pack studio-neue --png` |
| Compile every pack | `python -m engine.compiler --all` |
| Score every pack against its reference | `python -m eval.run` |
| Record new baseline scores | `python -m eval.run --save-baseline` |
| Harvest a new reference | `python -m engine.harvester --image path/to/scan.jpg --name "My Poster"` |
| Tests | `python -m pytest -q` (runs the renderer's node tests and a browser test of the studio) |

The server binds to `127.0.0.1` by default; set `AC_HOST` / `AC_PORT` to change it.

## Studio

The studio edits Rip documents directly. Click any text on the sheet to select it and click again to type. The page reflows as you write, and every text keeps its pack's type style.

- **Content panel:** every field in the document, labelled by the pack. Add, reorder, duplicate or remove entries here or from the toolbar that appears over a selected entry.
- **Inspector:** switch layout variants, and adjust the selected text's type style (typeface, size, weight, width, tracking, leading, case, alignment) or the paper and ink colours. A style edit changes every text that uses that style.
- **Fit status:** under the sheet, in plain words, with a one-click switch to a denser layout when something runs over.
- **Undo and redo:** every change, kept in the browser with the document, so it survives a reload.
- **Export PDF:** renders on the server with the same renderer as the canvas, so the PDF matches what you see.
- **Files:** open your files from `content/private/`, and **Save to file** (Ctrl/Cmd+S) writes them back, including any style edits under `_rip`. Photos you add are kept with the document.

On a phone the three panes become tabs.

## Rip packs

A Rip pack (`rip.json`) separates a design into **styles** (named type styles in pt, em and mm), **frames** (millimetre-placed boxes with flowing stacks, rows and repeats) and **data** (plain JSON the frames bind to). Swap the data and the design holds. See the header of `studio/js/rip-renderer.js` for the frame vocabulary.

- Stacks with a fixed height shrink their type to fit, never below a declared minimum; frames in the same fit group share one scale so body text stays one size. Anything that still overflows is reported, never silently clipped.
- Variants re-arrange the same type system for different amounts of content (`"variants"` in `rip.json`).
- There is one renderer, `studio/js/rip-renderer.js`, used by the studio canvas and by headless export. Justified text is hyphenated with British English TeX patterns, so output is identical on every machine.
- Fonts are self-hosted in `fonts/` (all SIL OFL).
- `engine/fit.py` solves point sizes from widths and from a reference's line breaks; that is how the shipped packs were sized.

Current Rip packs: `saraiva-resume` (78.2) and `dupont-letter` (85.8).

Personal content goes in `content/private/`, which git ignores.

## Fidelity score

`eval.run` renders each pack with headless Chromium, crops the reference to the printed sheet if it was photographed on a background, and scores the match from 0 to 100:

- **0** means no better than blank paper in the right colour; **100** means identical.
- Sub-scores explain the miss: **layout** (where the ink sits), **structure** (edges, rules, letterforms), **tone** (paper and ink palette), **aspect** (proportions).
- Each pack gets a diff image in `eval/out/`: reference, render, and an ink overlay where red is ink the render is missing and blue is ink it added.

Baseline scores live in `eval/baseline.json`: the 15 original harvests averaged **21.4** at Phase 0, and the two Rip packs were added at Phase 1. Every later change is judged against it.

## Layout

```
engine/
  rip.py          Drives the shared renderer headlessly: build, render, CLI
  fit.py          Solve type sizes from measured widths and line breaks
  render.py       Playwright renderer: PNG + PDF + page count + fit report, any OS
  compiler.py     CLI over the renderer
  harvester.py    Vision harvest of a reference into a Design Pack
  primitives.css  Scoped typographic primitives (tall, wide, bunched, spread, warp, shadow…)
  mark_vectorizer.py  Trace bitmap marks to SVG (kept for Phase 3)
  schema.py       pack.json spec
eval/
  fidelity.py     The score and the diff image
  run.py          The harness
design-packs/<id>/  rip.json (Rip packs) or template.html + styles.css (legacy) · pack.json · default-data.json · assets/
fonts/            Self-hosted variable fonts + fonts.css
content/private/  Your own content and renders (git-ignored)
studio/           The studio: index.html, studio.css, js/ (renderer, store, canvas, panels); legacy/ is the old editor
archive/          Legacy code kept for reference, not imported
```
