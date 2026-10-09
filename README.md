# Aestheticsrippy

A lab for ripping high-end typographic print design — posters, receipts, invoices, résumés — into documents you can edit and print at full fidelity.

The plan for the rebuild lives in the project doc *Aestheticsrippy — Review & Build Plan*. Phases 0–3 (clean and measure, the Rip core, the studio, the harvester) are on the `rebuild` branch.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

The harvester also needs Tesseract OCR 5 with English: `brew install tesseract` on macOS, `apt install tesseract-ocr` on Debian/Ubuntu, or the UB Mannheim installer on Windows.

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
| Rip a reference into a Rip pack | `python -m engine.harvest path/to/scan.jpg --name "My Poster"` (or **Rip an image** in the studio) |
| Score the harvester on every reference | `python -m eval.harvest_run` (`--save` records `eval/harvest-baseline.json`) |
| Rebuild the font catalogue | `python -m engine.typecase` |
| Tests | `python -m pytest -q` (runs the renderer's node tests and a browser test of the studio) |

The server binds to `127.0.0.1` by default; set `AC_HOST` / `AC_PORT` to change it.

## Studio

The studio edits Rip documents directly. Click any text on the sheet to select it and click again to type. The page reflows as you write, and every text keeps its pack's type style.

- **Content panel:** every field in the document, labelled by the pack. Add, reorder, duplicate or remove entries here or from the toolbar that appears over a selected entry.
- **Inspector:** switch layout variants, and adjust the selected text's type style (typeface from the 167-family cabinet, grouped by kind; size, weight, width, squash, tracking, leading, case, alignment) or the paper and ink colours. A style edit changes every text that uses that style.
- **Fit status:** under the sheet, in plain words, with a one-click switch to a denser layout when something runs over.
- **Undo and redo:** every change, kept in the browser with the document, so it survives a reload.
- **Export PDF:** renders on the server with the same renderer as the canvas, so the PDF matches what you see.
- **Files:** open your files from `content/private/`, and **Save to file** (Ctrl/Cmd+S) writes them back, including any style edits under `_rip`. Photos you add are kept with the document.

On a phone the three panes become tabs.

## The harvester

`engine/harvest/` rips a photo, scan or screenshot of one printed sheet into a Rip pack, with no model and no network. Same image in, same pack out.

1. **Sheet.** Finds the page against its surround, squares it up if it was shot at an angle, and snaps it to a paper size (A4, Letter, square, 4:5…).
2. **Rules and panels.** Long thin lines become rules; flat bars and blocks of colour become boxes, including bars with type knocked out of them.
3. **Text.** Tesseract reads the sheet several ways (whole page, sparse, rules painted out, each panel on its own, then any leftover type-sized patch), and the best reading of each spot wins. Lines are measured from the pixels: baseline, x-height, cap height, ink colour.
4. **Structure.** Words split into runs at column gaps; runs stack into blocks by size, colour, baseline rhythm and a shared edge. Each block gets its alignment, and each line break is judged forced (an address, a centred heading) or a wrap (a paragraph). Poster lines set to one width with different letterspacing become separate frames, each with its own tracking.
5. **Type.** The cabinet holds 167 families (about 660 weight and width instances). For each block, every instance is first scored on paper: the text's predicted width at the size its measured height implies, its predicted amount of ink (weight), and its x-height to cap-height ratio. The 40 most plausible are then rendered at the reference's own pixel scale and softness and compared with the reference, along with their neighbouring weights and widths, the italic, and the face squashed or stretched horizontally to the measured width. The document then settles on a small set of families, paying a price for each one added, and text of one size and colour shares a family. Blocks that share a face and size become one named style (`body`, `display`, `small`…).
6. **Trust.** Text whose best rendering still looks nothing like the reference (a logotype read as letters, a row of ornaments read as words), very large lettering that no face matches closely, and short scraps read with little confidence are not set as type; their pixels are kept as art.
7. **Lists.** Three or more rows that line up column by column, in matching styles, at a steady rhythm (invoice lines, a menu, tour dates) become one repeat frame bound to a list, so a row can be added or removed in the studio.
8. **Angled type.** In what is left, ink that falls into sharp rows at some angle is turned level and read; confident readings become rotated text frames.
9. **Art.** What is left becomes outlines (ellipses, boxes), photos (JPEG) and marks (PNG with true transparency, un-mixed from the paper). If the paper is not flat (a gradient, a tint, a photographed sheet's falloff) it is kept as a paper image under everything.
10. **Verify.** The pack is rendered and scored against the reference; then a diagnostic render paints every text frame in its own colour so each frame can be measured on its own, and frames are moved, re-tracked and re-sized where they miss. Rounds repeat while the score improves.

Each pack's `rip.json` records the harvest: score, how much of the ink is live type and shapes (`live`, versus pasted images), how closely the chosen faces' letters match the reference (`type_match`), notes and the per-round history.

On the 17 references in this repo the harvester averages **90.8** (the original harvests averaged 21.4), with 57% of the ink rebuilt as live type and shapes on average (invoices and letters 89–98%, posters with drawn logotypes and illustrations 20–50%). On the letter it scores 91.4 against the hand-built pack's 85.8. Its limits today: curved type (round a circle) stays art, and so does tilted type it cannot read confidently; a face the cabinet has no relative of is matched to its nearest twin; very small images (x-height under 6 px) read badly, and the pack says so.

## Rip packs

A Rip pack (`rip.json`) separates a design into **styles** (named type styles in pt, em and mm), **frames** (millimetre-placed boxes with flowing stacks, rows and repeats) and **data** (plain JSON the frames bind to). Swap the data and the design holds. See the header of `studio/js/rip-renderer.js` for the frame vocabulary.

- Stacks with a fixed height shrink their type to fit, never below a declared minimum; frames in the same fit group share one scale so body text stays one size. Anything that still overflows is reported, never silently clipped.
- Variants re-arrange the same type system for different amounts of content (`"variants"` in `rip.json`).
- There is one renderer, `studio/js/rip-renderer.js`, used by the studio canvas and by headless export. Justified text is hyphenated with British English TeX patterns, so output is identical on every machine.
- Fonts are self-hosted in `fonts/` (all SIL OFL).
- `engine/fit.py` solves point sizes from widths and from a reference's line breaks; that is how the shipped packs were sized.

Rip packs: the hand-built `saraiva-resume` (78.2) and `dupont-letter` (85.8), plus 15 packs ripped by the harvester from the original references (their earlier HTML versions are in `archive/legacy-packs/`). Four reference-less legacy packs (`buum-industrial`, `manifesto-red`, `studio-neue`, `thermal-artifact`) remain for the old editor at `/studio/legacy/`.

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
  harvest/        The harvester: sheet, ocr, layout, typeface, art, build, refine, pipeline
  typecase.py     The type cabinet: fonts, metrics, fonts.css + catalogue.json
  primitives.css  Scoped typographic primitives for the legacy packs
  schema.py       pack.json spec
eval/
  fidelity.py     The score and the diff image
  run.py          The harness
  harvest_run.py  Rips every reference from scratch and scores the result
design-packs/<id>/  rip.json (Rip packs) or template.html + styles.css (legacy) · pack.json · default-data.json · assets/
fonts/            The type cabinet: 167 self-hosted families, fonts.css, catalogue.json, matcher.json
content/private/  Your own content and renders (git-ignored)
studio/           The studio: index.html, studio.css, js/ (renderer, store, canvas, panels); legacy/ is the old editor
archive/          Legacy code kept for reference, not imported
```
