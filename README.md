# Aestheticsrippy

A lab for ripping high-end typographic print design — posters, receipts, invoices, résumés — into documents you can edit and print at full fidelity.

The plan for the rebuild lives in the project doc *Aestheticsrippy — Review & Build Plan*. This branch is **Phase 0: clean and measure.**

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Optional: put `GEMINI_API_KEY=...` in a `.env` file in the project root for the harvester.

## Commands

| What | Command |
| --- | --- |
| Studio (editor) | `python server.py` → http://127.0.0.1:8080/studio/ |
| Compile one pack to PDF | `python -m engine.compiler --pack studio-neue --png` |
| Compile every pack | `python -m engine.compiler --all` |
| Score every pack against its reference | `python -m eval.run` |
| Record new baseline scores | `python -m eval.run --save-baseline` |
| Harvest a new reference | `python -m engine.harvester --image path/to/scan.jpg --name "My Poster"` |
| Tests | `python -m pytest -q` |

The server binds to `127.0.0.1` by default; set `AC_HOST` / `AC_PORT` to change it.

## Fidelity score

`eval.run` renders each pack with headless Chromium, crops the reference to the printed sheet if it was photographed on a background, and scores the match from 0 to 100:

- **0** means no better than blank paper in the right colour; **100** means identical.
- Sub-scores explain the miss: **layout** (where the ink sits), **structure** (edges, rules, letterforms), **tone** (paper and ink palette), **aspect** (proportions).
- Each pack gets a diff image in `eval/out/`: reference, render, and an ink overlay where red is ink the render is missing and blue is ink it added.

The Phase 0 baseline is in `eval/baseline.json` (mean **21.4**). Every later phase is judged against it.

## Layout

```
engine/
  render.py       Playwright renderer: PNG + PDF + page count, any OS
  compiler.py     CLI over the renderer
  harvester.py    Vision harvest of a reference into a Design Pack
  primitives.css  Scoped typographic primitives (tall, wide, bunched, spread, warp, shadow…)
  mark_vectorizer.py  Trace bitmap marks to SVG (kept for Phase 3)
  schema.py       pack.json spec
eval/
  fidelity.py     The score and the diff image
  run.py          The harness
design-packs/<id>/  pack.json · template.html · styles.css · default-data.json · assets/reference.*
studio/           The current editor (rebuilt in Phase 2)
archive/          Legacy code kept for reference, not imported
```
