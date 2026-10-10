"""
Aesthetic Compiler - Harvester CLI
Deconstructs reference images (Pinterest / Are.na / Scans) into portable Design Packs.
Prepares multimodal extraction prompts and scaffolds pack directories.
"""

import os
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

HARVEST_SYSTEM_PROMPT = """
You are an expert typographic deconstructor and print layout engineer.
Analyze this high-end print design reference image. Extract its exact structural DNA.

Return a JSON object with this exact schema:
{
  "id": "kebab-case-pack-id",
  "name": "Human Readable Pack Name",
  "category": "Invoice | Poster | Slip | Receipt | Editorial",
  "description": "2-sentence design summary focusing on typography and spatial tension",
  "target": {
    "dimensions": {
      "format": "A4 | A5 | Letter | Thermal-80mm",
      "width_mm": 210,
      "height_mm": 297,
      "orientation": "portrait"
    },
    "margins_mm": {
      "top": 20,
      "right": 20,
      "bottom": 20,
      "left": 20
    }
  },
  "typography": {
    "primaryFont": "Inter | Space Mono | Playfair Display | etc",
    "displayFont": "Inter Tight | Helvetica Neue | etc",
    "monospaceFont": "Space Mono | Courier Prime | etc",
    "modularScale": 1.25,
    "lineHeightBase": 1.4
  },
  "colorTokens": {
    "background": "#hex",
    "textPrimary": "#hex",
    "textSecondary": "#hex",
    "accent": "#hex"
  },
  "spatialBudget": {
    "strictSinglePage": true
  },
  "seedData": {
    "title": "...",
    "sections": []
  }
}
"""

def scaffold_pack(spec_dict: dict, base_dir: Path = BASE_DIR):
    pack_id = spec_dict["id"]
    pack_dir = base_dir / "design-packs" / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. pack.json
    pack_json_path = pack_dir / "pack.json"
    clean_spec = {k: v for k, v in spec_dict.items() if k != "seedData"}
    with open(pack_json_path, "w", encoding="utf-8") as f:
        json.dump(clean_spec, f, indent=2)
        
    # 2. default-data.json
    seed_data = spec_dict.get("seedData", {})
    data_path = pack_dir / "default-data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, indent=2)
        
    print(f"[OK] Harvested and scaffolded Design Pack at: {pack_dir}")
    return pack_dir

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Design Pack Harvester")
    parser.add_argument("--image", type=str, help="Path to reference image to harvest")
    parser.add_argument("--name", type=str, help="Name of the new design pack")
    args = parser.parse_args()
    
    if args.image:
        print(f"[*] Preparing harvest pipeline for image: {args.image}")
        print("[*] Gemini Vision prompt ready. Scaffolding pack...")
    else:
        print("Usage: python engine/harvester.py --image <path_to_image> --name <pack_name>")
