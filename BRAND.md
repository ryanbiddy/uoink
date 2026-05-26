# Uoink Brand (v3.1)

The canonical brand system is the **v3.1 legibility patch** — see
[`docs/V3.1-LEGIBILITY-PATCH.md`](docs/V3.1-LEGIBILITY-PATCH.md) for the full
rationale. This file is the quick reference for the product repo.

> The magnet logo was always a U. The product name is **Uoink** (capital U);
> the verb is **uoink** (lowercase): "uoink that video." New home: uoink.video.

## Palette (six tokens)

| Token | Hex | Role |
|---|---|---|
| Rust | `#C2410C` | **Primary.** Brand colour on type, surfaces, most headlines. Passes AA on cream (4.7:1). |
| Vermillion | `#FF3D00` | 5% accent only — CTAs, hover, one stamp per viewport, hero italic emphasis. **Dark grounds only.** |
| Acid | `#FFD23F` | Solid shapes only — stamps, magnet-U tips. **Never type.** |
| Cream | `#FFF4EC` | Light ground; magnet-U tips at small sizes (≤32 px). |
| Ink | `#0A0A0A` | Near-black text / dark grounds. |
| Oxblood | `#7B2D0E` | Deep rust for shadows / borders / depth. |

```css
:root {
  --rust:       #C2410C; /* primary type + surface colour */
  --vermillion: #FF3D00; /* 5% accent: CTA / hover / one stamp / hero italic */
  --acid:       #FFD23F; /* solid shapes + magnet tips only — never type */
  --cream:      #FFF4EC; /* light ground */
  --ink:        #0A0A0A; /* text / dark ground */
  --oxblood:    #7B2D0E; /* depth: shadows, borders */
}
```

## Type stack (three families, no serifs)

- **Bungee** — wordmark only.
- **Inter** — 400/500/600/700/800 + italic. Every display and editorial role
  (Inter 800 + Inter italic replaced Fraunces / Instrument Serif).
- **JetBrains Mono** — code, tool names, mono chips.

## Contrast house rules (the traps v3.1 closed)

1. Vermillion only on dark grounds.
2. Rust only on cream / ink — never on vermillion.
3. Acid only as solid shapes (stamps, magnet tips) — **never as type.**

## Magnet-U mark — size-aware tips

- ≤ 32 px (favicon / tray / installer mark at small scale): rust body, **cream
  tips** at 20% glyph height. Acid tips vanish at 16 px — this is the bug v3.1 fixed.
- \> 32 px: rust body, **acid tips** at 14% glyph height.

## Geometry (Discord-lean)

Cards 12 px radius, buttons pill, corpus panels 8 px, stamps circular.

## Voice

- Loud hero (marketing site homepage only): **"Uoink that shit."**
- CWS-safe / polished surfaces (README, installer, store listing): **"Uoink any
  video. Read it like a doc."**
- Tagline: **"The YouTube layer for any AI."**
