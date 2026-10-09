# Archive

Code kept for reference while the core is rebuilt. Nothing here is imported by the live engine.

- `legacy-engine/archetype_normalizers.py` and `boutique_glyphs.py` — per-reference templates and glyph data that matched specific designs (PangPang, Fidèle, Handshake, LSD) by searching for their words. Useful as hand-tuned fixtures when testing the Phase 3 harvester; not a general method.
- `legacy-engine/append_gizmo.py`, `update_gizmo_css.py` — one-off patch scripts for the studio CSS.
- `legacy-engine/walkthrough_notes.json` — notes from the earlier build (was `server_phase1_backup.py`).
- `scratch/` — restore and verification scripts from the earlier build.
- `export-scripts/` — test and tracing scripts that lived in `export/`.
- `harvester-gemini.py` — the first harvester: one Gemini vision call that wrote template HTML and CSS. Replaced by `engine/harvest/` in Phase 3.
- `mark_vectorizer.py` — contour tracing of marks to SVG from the first harvester.
- `legacy-packs/` — the first harvester's HTML packs for the 15 references, replaced in Phase 3 by Rip packs the new harvester ripped from the same images (same ids, in `design-packs/`).
