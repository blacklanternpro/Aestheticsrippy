# Fonts

The type cabinet: self-hosted Latin subsets, so renders are deterministic and work offline. `engine/typecase.py` is the source of truth; `python -m engine.typecase` regenerates `fonts.css` and `catalogue.json` (metrics the harvester uses to match type).

All files are licensed under the SIL Open Font License 1.1. The Latin subsets come from Google Fonts via Fontsource.

| Family | File(s) | Axes / weights | Category | Designer |
| --- | --- | --- | --- | --- |
| Inter | Inter-var, Inter-Italic-var | wght 100–900, opsz 14–32 | neo-grotesque | Rasmus Andersson |
| Inter Tight | InterTight-var | wght 100–900 | neo-grotesque | Rasmus Andersson |
| Arimo | Arimo-var | wght 400–700 | neo-grotesque | Steve Matteson |
| Archivo | Archivo-var | wght 100–900, wdth 62–125 | grotesque | Omnibus-Type |
| Archivo Black | ArchivoBlack-Regular | 400 | grotesque | Omnibus-Type |
| Space Grotesk | SpaceGrotesk-var | wght 300–700 | grotesque | Florian Karsten |
| Jost | Jost-var, Jost-Italic-var | wght 100–900 | geometric | indestructible type* |
| Unbounded | Unbounded-var | wght 200–900 | wide | NaN |
| Oswald | Oswald-var | wght 200–700 | condensed | Vernon Adams et al. |
| Anton | Anton-Regular | 400 | condensed | Vernon Adams |
| Big Shoulders Display | BigShouldersDisplay-var | wght 100–900 | condensed | Patric King |
| Big Shoulders Stencil Display | BigShouldersStencilDisplay-var | wght 100–900 | stencil | Patric King |
| Tinos | Tinos-Regular, Tinos-Bold | 400, 700 | serif | Steve Matteson |
| Newsreader | Newsreader-var | wght 200–800, opsz 6–72 | serif | Production Type |
| EB Garamond | EBGaramond-var | wght 400–800 | old-style | Georg Duffner, Octavio Pardo |
| Bodoni Moda | BodoniModa-var | wght 400–900, opsz 6–96 | didone | Owen Earl |
| JetBrains Mono | JetBrainsMono-var | wght 100–800 | mono | JetBrains |
| Space Mono | SpaceMono-Regular, SpaceMono-Bold | 400, 700 | mono | Colophon |
| Courier Prime | CourierPrime-Regular, CourierPrime-Bold | 400, 700 | typewriter | Alan Dague-Greene |
| Mrs Saint Delafield | MrsSaintDelafield-Regular | 400 | script | Sudtipos |

Licence text: https://openfontlicense.org/open-font-license-official-text/
