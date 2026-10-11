# Print finish: over-inked, blurred and overprinted type (phase shipped)

The theme: the letterform underneath is a real typeface, but the design's
character is the *finish* - ink gain, blur, photocopy erosion, overprint.

What shipped (see the three "Print finish" commits on `rebuild`):
1. Rip format + renderer: per-style `finish` {gain, blur, rough, threshold,
   ink} rendered as one generated SVG filter per (finish, size), em-relative;
   `blend` on any frame for overprint. `spike.html` (kept here) is the
   original rendering proof.
2. Measurement: `engine/harvest/finish.py` re-fits each size-group with the
   finish applied to candidate tiles in cv2 (dilate, blur, re-threshold),
   covering lighter weights of the group's own family, its clean runners-up
   and the faces a gain-peeled shortlist points at. Emission gates learned
   from the misfires: best >= 0.86 (0.80 for a positively-identified copy:
   thresholded fit wins AND the ref's edge band has no mid-tones), margin
   over clean, gain <= 0.055em. KNOWN6 closes the loop (render 400 + finish,
   recover 400 + finish, clean body earns none).
3. The references were promoted into design-packs/ as eval packs:
   - mr-beams-photocopy-label: the finish FIRES live (Arimo 400, gain +
     blur + threshold on the body group; the xerox look renders from live
     type). 92.2 at promotion.
   - nikelab-chicago-mono: 96.8 at promotion, but the display dodges to
     condensed faces and the finish cannot out-explain them yet (below).
   - obby-jappari-office-card was found to BE the existing
     creative-studio-office-card eval ref (same design), so no new pack.

Known limits, for the next round here:
- OCR misreads on degraded display type poison the samples ('Unicago',
  'MB/20', 'AA-Ceiis'): no candidate can fit a wrong text. The glyph atlas
  (engine/harvest/letters.py) could verify/correct level display reads the
  way rotated.py does for angled ones - but the atlas is uppercase-only and
  these are mixed case.
- The office card's big soft "Office" never becomes a text block at all
  (the red overprint breaks OCR), so live stays 19% there.
- The pixel score mildly prefers a clean soft render over a truthful
  textured one (mr-beams clean would score ~96); texture-aware scoring or
  the planned print-textures phase would close that.
- Severe gain (nikelab display, ~0.08em+, strokes merging) sits beyond
  GAIN_CAP and beyond what grayscale dilation of a clean render explains.
