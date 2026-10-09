# Aesthetic Compiler (Aestheticsrippy)

A boutique graphic synthesis and design compiler engine. Compiles Design Packs and structured data payloads into pixel-perfect, publication-grade HTML and vector PDFs using headless Chromium.

## Features

- **Boutique Vision Harvester**: Deconstructs graphic scans, posters, and receipts into print-locked Design Packs via multimodal visual decomposition.
- **Design Pack Architecture**: Modular packs containing schema specifications (`pack.json`), layout templates (`template.html`), and visual assets.
- **Vector PDF Compilation**: High-fidelity vector rendering and typography pipeline via headless Chrome.
- **Studio Interface**: Interactive local studio and preview environment.

## Architecture

- `engine/`: Core compiler, harvester, vectorizers, and glyph generators.
- `design-packs/`: Curated collection of boutique templates (industrial ephemera, tour posters, invoices, receipts, and ledgers).
- `studio/`: Web studio interface and client tools.
- `export/`: Output directory for generated vector PDFs and verification assets.

## Quick Start

1. Start the studio server:
   ```bash
   python server.py
   ```
2. Open your browser to `http://localhost:8080/studio`.
3. Compile packs via CLI:
   ```bash
   python engine/compiler.py --pack manifesto-red
   ```
