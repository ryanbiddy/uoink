# `assets/store/`: Chrome Web Store Assets

Generated placeholder assets for the Chrome Web Store listing. Regenerate them from `assets/build_store_assets.py`, then replace screenshots with real product captures before submission.

## Files

| File | Dimensions | Web Store role | Required? |
| --- | --- | --- | --- |
| `promo-small-440x280.png` | 440 x 280 | Small promo tile, used in search and category cards | Required |
| `promo-large-920x680.png` | 920 x 680 | Large promo tile, used in featured placements | Recommended |
| `promo-marquee-1400x560.png` | 1400 x 560 | Marquee promo tile, used at the top of category pages | Optional |

Capture screenshots from the live product. See `docs/screenshot-list.md` for the required 1280x800 set.

## Composition

All three placeholder tiles use the v3.1 Uoink brand direction:

- Cream ground with rust and ink type
- UOINK wordmark text drawn by the generator
- Tagline: "Local corpus for AI writing."
- Sub-line: "Videos, podcasts, articles. Your disk."
- Mock Uoink pill button in the YouTube actions row position
- Hint below the button: "Capture the source. Keep the credit."

## What To Replace Before Submission

1. Use a real screenshot in the right pane once the store listing screenshots are captured.
2. Confirm the promo set matches the final Chrome Web Store screenshot order.
3. Re-run the generator after any brand asset changes.
4. Verify the rendered tiles at 100% size. Small-promo text should stay readable.

## Regenerating The Placeholders

```powershell
python assets/build_store_assets.py
```

The script also regenerates `extension/icons/icon-{16,32,48,128}.png` from `assets/logo-mark-dark.png`.

## Asset Sources

- **Mark**: `assets/logo-mark-dark.png`, used for extension icon sizes
- **Full logo**: `assets/logo.png`, available for manual redesigns
- **Legacy wordmark images**: kept in `assets/` for historical reference; generated promo tiles draw UOINK text directly
