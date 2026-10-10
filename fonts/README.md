# Fonts

The type cabinet: 167 families, self-hosted Latin subsets, so renders are deterministic and work offline. `engine/typecase.py` is the source of truth (the `SOURCES` list); `python -m engine.typecase` regenerates `fonts.css`, `catalogue.json` (families, for the studio) and `matcher.json` (per-instance metrics, for the harvester). `--fetch DIR` copies faces in from unpacked Fontsource npm packages.

Files come from Google Fonts via Fontsource. Licences: Apache-2.0, OFL-1.1 (SIL Open Font License 1.1: https://openfontlicense.org/open-font-license-official-text/).

| Family | Category | Weights / axes | Italic | Licence |
| --- | --- | --- | --- | --- |
| Inter | Neo-grotesque | wght 100–900 | yes | OFL-1.1 |
| Inter Tight | Neo-grotesque | wght 100–900 | yes | OFL-1.1 |
| Arimo | Neo-grotesque | wght 400–700 | yes | OFL-1.1 |
| Public Sans | Neo-grotesque | wght 100–900 | yes | OFL-1.1 |
| IBM Plex Sans | Neo-grotesque | wght 100–700, wdth 75–100 | yes | OFL-1.1 |
| Geist | Neo-grotesque | wght 100–900 | yes | OFL-1.1 |
| Roboto Flex | Neo-grotesque | wght 100–1000, wdth 25–151 |  | OFL-1.1 |
| Work Sans | Grotesque | wght 100–900 | yes | OFL-1.1 |
| Manrope | Grotesque | wght 200–800 |  | OFL-1.1 |
| Schibsted Grotesk | Grotesque | wght 400–900 | yes | OFL-1.1 |
| Hanken Grotesk | Grotesque | wght 100–900 | yes | OFL-1.1 |
| Instrument Sans | Grotesque | wght 400–700, wdth 75–100 | yes | OFL-1.1 |
| Familjen Grotesk | Grotesque | wght 400–700 | yes | OFL-1.1 |
| Bricolage Grotesque | Grotesque | wght 200–800, wdth 75–100 |  | OFL-1.1 |
| Host Grotesk | Grotesque | wght 300–800 | yes | OFL-1.1 |
| Onest | Grotesque | wght 100–900 |  | OFL-1.1 |
| Red Hat Display | Grotesque | wght 300–900 | yes | OFL-1.1 |
| Space Grotesk | Grotesque | wght 300–700 |  | OFL-1.1 |
| Archivo | Grotesque | wght 100–900, wdth 62–125 | yes | OFL-1.1 |
| Archivo Black | Grotesque | 400 |  | OFL-1.1 |
| Chivo | Grotesque | wght 100–900 | yes | OFL-1.1 |
| Mona Sans | Grotesque | wght 200–900, wdth 75–125 | yes | OFL-1.1 |
| Hubot Sans | Grotesque | wght 200–900, wdth 75–125 | yes | OFL-1.1 |
| Epilogue | Grotesque | wght 100–900 | yes | OFL-1.1 |
| Barlow | Grotesque | wght 100–900 | yes | OFL-1.1 |
| Encode Sans | Grotesque | wght 100–900, wdth 75–125 |  | OFL-1.1 |
| Jost | Geometric | wght 100–900 | yes | OFL-1.1 |
| Figtree | Geometric | wght 300–900 | yes | OFL-1.1 |
| DM Sans | Geometric | wght 100–1000 | yes | OFL-1.1 |
| Albert Sans | Geometric | wght 100–900 | yes | OFL-1.1 |
| Sora | Geometric | wght 100–800 |  | OFL-1.1 |
| Poppins | Geometric | wght 100–900 | yes | OFL-1.1 |
| Montserrat | Geometric | wght 100–900 | yes | OFL-1.1 |
| Outfit | Geometric | wght 100–900 |  | OFL-1.1 |
| Urbanist | Geometric | wght 100–900 | yes | OFL-1.1 |
| League Spartan | Geometric | wght 100–900 |  | OFL-1.1 |
| Raleway | Geometric | wght 100–900 | yes | OFL-1.1 |
| Josefin Sans | Geometric | wght 100–700 | yes | OFL-1.1 |
| Questrial | Geometric | 400 |  | OFL-1.1 |
| Rubik | Geometric | wght 300–900 | yes | OFL-1.1 |
| Tenor Sans | Humanist | 400 |  | OFL-1.1 |
| Oswald | Condensed | wght 200–700 |  | OFL-1.1 |
| Anton | Condensed | 400 |  | OFL-1.1 |
| Bebas Neue | Condensed | 400 |  | OFL-1.1 |
| League Gothic | Condensed | 400, wdth 75–100 |  | OFL-1.1 |
| Archivo Narrow | Condensed | wght 400–700 | yes | OFL-1.1 |
| IBM Plex Sans Condensed | Condensed | wght 100–700 | yes | OFL-1.1 |
| Barlow Condensed | Condensed | wght 100–900 | yes | OFL-1.1 |
| Barlow Semi Condensed | Condensed | wght 100–900 | yes | OFL-1.1 |
| Roboto Condensed | Condensed | wght 100–900 | yes | OFL-1.1 |
| Saira | Condensed | wght 100–900, wdth 50–125 | yes | OFL-1.1 |
| Fjalla One | Condensed | 400 |  | OFL-1.1 |
| Pathway Gothic One | Condensed | 400 |  | OFL-1.1 |
| Antonio | Condensed | wght 100–700 |  | OFL-1.1 |
| Teko | Condensed | wght 300–700 |  | OFL-1.1 |
| Sofia Sans Condensed | Condensed | wght 1–1000 | yes | OFL-1.1 |
| Sofia Sans Extra Condensed | Condensed | wght 1–1000 | yes | OFL-1.1 |
| Mohave | Condensed | wght 300–700 | yes | OFL-1.1 |
| Six Caps | Condensed | 400 |  | OFL-1.1 |
| Big Shoulders Display | Condensed | wght 100–900 |  | OFL-1.1 |
| Unbounded | Wide | wght 200–900 |  | OFL-1.1 |
| Syne | Wide | wght 400–800 |  | OFL-1.1 |
| Krona One | Wide | 400 |  | OFL-1.1 |
| Lexend Zetta | Wide | wght 100–900 |  | OFL-1.1 |
| Michroma | Wide | 400 |  | OFL-1.1 |
| Dela Gothic One | Wide | 400 |  | OFL-1.1 |
| Rubik Mono One | Wide | 400 |  | OFL-1.1 |
| Bowlby One | Wide | 400 |  | OFL-1.1 |
| Syncopate | Wide | wght 400–700 |  | Apache-2.0 |
| Orbitron | Wide | wght 400–900 |  | OFL-1.1 |
| Zen Dots | Wide | 400 |  | OFL-1.1 |
| Tinos | Serif | wght 400–700 | yes | OFL-1.1 |
| Newsreader | Serif | wght 200–800 | yes | OFL-1.1 |
| Source Serif 4 | Serif | wght 200–900 | yes | OFL-1.1 |
| Literata | Serif | wght 200–900 | yes | OFL-1.1 |
| Lora | Serif | wght 400–700 | yes | OFL-1.1 |
| Libre Baskerville | Serif | wght 400–700 | yes | OFL-1.1 |
| Spectral | Serif | wght 200–800 | yes | OFL-1.1 |
| IBM Plex Serif | Serif | wght 100–700 | yes | OFL-1.1 |
| PT Serif | Serif | wght 400–700 | yes | OFL-1.1 |
| Instrument Serif | Serif | 400 | yes | OFL-1.1 |
| Fraunces | Serif | wght 100–900 | yes | OFL-1.1 |
| Young Serif | Serif | 400 |  | OFL-1.1 |
| Libre Caslon Text | Serif | wght 400–700 | yes | OFL-1.1 |
| Libre Caslon Display | Serif | 400 |  | OFL-1.1 |
| EB Garamond | Old-style | wght 400–800 | yes | OFL-1.1 |
| Cormorant | Old-style | wght 300–700 | yes | OFL-1.1 |
| Cormorant Garamond | Old-style | wght 300–700 | yes | OFL-1.1 |
| Crimson Pro | Old-style | wght 200–900 | yes | OFL-1.1 |
| Bodoni Moda | Didone | wght 400–900 | yes | OFL-1.1 |
| Playfair Display | Didone | wght 400–900 | yes | OFL-1.1 |
| DM Serif Display | Didone | 400 | yes | OFL-1.1 |
| Abril Fatface | Didone | 400 |  | OFL-1.1 |
| Gloock | Didone | 400 |  | OFL-1.1 |
| Noto Serif Display | Didone | wght 100–900, wdth 62.5–100 | yes | OFL-1.1 |
| Old Standard TT | Didone | wght 400–700 | yes | OFL-1.1 |
| Bitter | Slab | wght 100–900 | yes | OFL-1.1 |
| Roboto Slab | Slab | wght 100–900 |  | Apache-2.0 |
| Zilla Slab | Slab | wght 300–700 | yes | OFL-1.1 |
| Arvo | Slab | wght 400–700 | yes | OFL-1.1 |
| Josefin Slab | Slab | wght 100–700 | yes | OFL-1.1 |
| Alfa Slab One | Slab | 400 |  | OFL-1.1 |
| Ultra | Slab | 400 |  | Apache-2.0 |
| JetBrains Mono | Mono | wght 100–800 | yes | OFL-1.1 |
| Space Mono | Mono | wght 400–700 | yes | OFL-1.1 |
| IBM Plex Mono | Mono | wght 100–700 | yes | OFL-1.1 |
| DM Mono | Mono | wght 300–500 | yes | OFL-1.1 |
| Geist Mono | Mono | wght 100–900 | yes | OFL-1.1 |
| Fira Code | Mono | wght 300–700 |  | OFL-1.1 |
| Source Code Pro | Mono | wght 200–900 | yes | OFL-1.1 |
| Roboto Mono | Mono | wght 100–700 | yes | OFL-1.1 |
| Martian Mono | Mono | wght 100–800, wdth 75–112.5 |  | OFL-1.1 |
| Azeret Mono | Mono | wght 100–900 | yes | OFL-1.1 |
| Red Hat Mono | Mono | wght 300–700 | yes | OFL-1.1 |
| Spline Sans Mono | Mono | wght 300–700 | yes | OFL-1.1 |
| Chivo Mono | Mono | wght 100–900 | yes | OFL-1.1 |
| Xanh Mono | Mono | 400 | yes | OFL-1.1 |
| Major Mono Display | Mono | 400 |  | OFL-1.1 |
| Share Tech Mono | Mono | 400 |  | OFL-1.1 |
| Anonymous Pro | Mono | wght 400–700 | yes | OFL-1.1 |
| Courier Prime | Typewriter | wght 400–700 | yes | OFL-1.1 |
| Cutive Mono | Typewriter | 400 |  | OFL-1.1 |
| Special Elite | Typewriter | 400 |  | Apache-2.0 |
| VT323 | Pixel | 400 |  | OFL-1.1 |
| Silkscreen | Pixel | wght 400–700 |  | OFL-1.1 |
| Press Start 2P | Pixel | 400 |  | OFL-1.1 |
| Pixelify Sans | Pixel | wght 400–700 |  | OFL-1.1 |
| DotGothic16 | Pixel | 400 |  | OFL-1.1 |
| Doto | Pixel | wght 100–900 |  | OFL-1.1 |
| Jersey 10 | Pixel | 400 |  | OFL-1.1 |
| Big Shoulders Stencil Display | Stencil | wght 100–900 |  | OFL-1.1 |
| Stardos Stencil | Stencil | wght 400–700 |  | OFL-1.1 |
| Allerta Stencil | Stencil | 400 |  | OFL-1.1 |
| Saira Stencil One | Stencil | 400 |  | OFL-1.1 |
| Tilt Warp | Display | 400 |  | OFL-1.1 |
| Bungee | Display | 400 |  | OFL-1.1 |
| Bungee Shade | Display | 400 |  | OFL-1.1 |
| Bungee Inline | Display | 400 |  | OFL-1.1 |
| Monoton | Display | 400 |  | OFL-1.1 |
| Rubik Glitch | Display | 400 |  | OFL-1.1 |
| Climate Crisis | Display | 400 |  | OFL-1.1 |
| Rubik Bubbles | Bubble | 400 |  | OFL-1.1 |
| Bagel Fat One | Bubble | 400 |  | OFL-1.1 |
| Modak | Bubble | 400 |  | OFL-1.1 |
| Titan One | Bubble | 400 |  | OFL-1.1 |
| Shrikhand | Bubble | 400 |  | OFL-1.1 |
| Chango | Bubble | 400 |  | OFL-1.1 |
| UnifrakturMaguntia | Blackletter | 400 |  | OFL-1.1 |
| UnifrakturCook | Blackletter | 700 |  | OFL-1.1 |
| Pirata One | Blackletter | 400 |  | OFL-1.1 |
| Grenze Gotisch | Blackletter | wght 100–900 |  | OFL-1.1 |
| New Rocker | Blackletter | 400 |  | OFL-1.1 |
| Jacquard 24 | Blackletter | 400 |  | OFL-1.1 |
| Mrs Saint Delafield | Script | 400 |  | OFL-1.1 |
| Pinyon Script | Script | 400 |  | OFL-1.1 |
| Great Vibes | Script | 400 |  | OFL-1.1 |
| Herr Von Muellerhoff | Script | 400 |  | OFL-1.1 |
| Monsieur La Doulaise | Script | 400 |  | OFL-1.1 |
| Allura | Script | 400 |  | OFL-1.1 |
| Parisienne | Script | 400 |  | OFL-1.1 |
| Italianno | Script | 400 |  | OFL-1.1 |
| Caveat | Hand | wght 400–700 |  | OFL-1.1 |
| Homemade Apple | Hand | 400 |  | Apache-2.0 |
| Reenie Beanie | Hand | 400 |  | OFL-1.1 |
| Permanent Marker | Hand | 400 |  | Apache-2.0 |
| Rock Salt | Hand | 400 |  | Apache-2.0 |
| La Belle Aurore | Hand | 400 |  | OFL-1.1 |
