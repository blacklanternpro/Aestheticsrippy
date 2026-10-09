"""
Harvester v2: rip a reference image into a Rip pack, deterministically.

    sheet    find and rectify the printed sheet, pick its paper size
    ocr      words and lines with tesseract (hOCR), at a scale it reads well
    layout   lines -> runs and blocks, alignment, soft versus hard breaks
    colour   paper and ink tones
    typeface match type against the cabinet by rendering candidates
    art      what is not text: rules, panels, photos, marks
    build    assemble rip.json, default data and field labels
    refine   render, compare frame by frame, correct, repeat

`python -m engine.harvest <image>` runs the lot; see __main__.py.
"""
