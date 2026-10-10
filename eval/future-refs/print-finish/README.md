# Print finish: over-inked, blurred and overprinted type (planned phase)

Three references for a later phase, kept OUT of `design-packs/` so the eval
stays honest until the phase begins. The theme: the letterform underneath is a
real typeface, but the design's character is the *finish* — ink gain, blur,
photocopy erosion, overprint. Today the engine either mistakes the finish for
a heavier weight, or the trust filter keeps the whole block as pasted art.
The goal is live, editable type that *renders* with the measured finish.

- `obby-jappari-office-card.jpg` — soft over-inked display type with a red
  bespoke script logotype overprinted across it (multiply, slight blur).
- `nikelab-chicago-mono.jpg` — mono type with heavy ink gain: strokes swollen,
  counters part-filled, corners rounded, a few strokes merging.
- `mr-beams-photocopy-label.jpg` — photocopy degradation: gain plus ragged,
  eroded edges and re-thresholded (hard) contours.

`spike.html` (this folder) proves the rendering half: open it in the engine's
Chromium (`engine.render.Renderer.render_file`) and all four finishes come out
of ONE SVG filter chain applied to live text —
`feMorphology dilate` (gain) → `feGaussianBlur` (softness) →
`feTurbulence + feDisplacementMap` (ragged photocopy edges) →
`feComponentTransfer` (alpha gamma for ink darkness, or a discrete table for
the re-thresholded xerox look) — plus `mix-blend-mode: multiply` for
overprint. Both renderer paths are Chromium, so studio and headless agree.

## Plan
1. Rip format: a per-style `finish` block — `{gain, blur, rough: {freq, scale,
   seed}, threshold}` in em-relative units so one finish serves all sizes —
   rendered by `rip-renderer.js` as a generated SVG filter per distinct
   finish; and `blend: "multiply"` on frames (text AND image/mark frames, so
   a bespoke overlay like the red "office" script composites correctly even
   while it stays art).
2. Measurement (the hard half; build test-first against known-answer sheets
   rendered WITH finishes): the type bench must solve face, weight, gain and
   blur jointly — today blur is solved globally (`bench.blur`) and gain
   masquerades as weight. Apply dilate+blur to candidate tiles in cv2 (no
   re-render), and prefer the lighter weight + gain when both explain the ink,
   since weights are discrete and gain fills the gaps between them. Fit the
   finish per size-group, not per block. Roughness = the residual edge
   raggedness after gain+blur fit; the photocopy's hard edges (bimodal edge
   profile after erosion) set `threshold`.
3. Trust filter: finish-aware match scores mean over-inked type that
   previously failed `match.score` stays live instead of becoming art.
4. Known-answer sheet (KNOWN6): render text at weight 400 with a known finish,
   rip it, assert the recovered weight is 400 (not 700), the finish parameters
   come back within tolerance, and the text is live.
5. Only then: move these three references into `design-packs/` as eval packs.
6. This phase merges naturally with the planned print-textures work (riso
   grain, halftone, misregistration): misregistration = per-colour-pass
   offsets on multiply layers, measurable from colour-fringe offsets.
