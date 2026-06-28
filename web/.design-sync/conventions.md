# Dev-Hive design system — conventions for building UI

Dev-Hive is a developer-learning community ("경험이 곧 커리큘럼"). The look is **airy, borderless, white with an indigo accent** — hairline dividers, generous spacing, no heavy card borders.

## Importing components
All components live on `window.DevHive`. Build with the real exports — e.g. `DevHive.ContentCard`, `DevHive.StateView`, `DevHive.ComingSoon`, `DevHive.RouteError`, `DevHive.Heatmap`.

## Styling idiom — global CSS classes + tokens (NOT Tailwind, NOT style props)
Style your own layout glue with the design system's **CSS classes** (compiled into `_ds_bundle.css`, reachable from `styles.css`) and **CSS custom properties**. Do not invent class names or pull in a utility framework — use the vocabulary below.

### Design tokens (`var(--*)`)
- Color: `--accent` (#4E68C7 indigo, primary), `--accent-ink` (#3D51A8, links / small text), `--accent-wash` (#EEF1FB, active icon / chip bg)
- Surface: `--bg`, `--surface`, `--surface-sunken`; text: `--text`, `--text-muted`, `--text-subtle`
- Lines: `--border`, `--border-strong` (hairline dividers, not boxes); corner: `--radius`
- Difficulty pills: `--diff-intro-{bg,fg}`, `--diff-mid-{bg,fg}`, `--diff-adv-{bg,fg}`; type/tag chips: `--type-{bg,fg}`, `--tag-{bg,fg}`
- Layout: `--feed-max` (content column max width), `--rail-w` (left rail width)

### Key class families
- Cards: `rec-card` / `rec-body` (content & recommendation cards), `modal-card` (read overlay)
- Chips: `pill` (tags / metadata); difficulty & type chips color via the `--diff-*` / `--type-*` / `--tag-*` tokens
- Section headers: `sec-head`, `sec-sub`, `sec-foot`, `sec-note`
- Learning path: `path-list` / `path-step` / `path-node` / `path-name` / `path-meta`
- Mastery rows: `cur-row` / `cur-bar` / `cur-fill` / `cur-name` / `cur-stage`
- Buttons: `btn-ghost`, `read-btn`, `fb-btn` (feedback), `pager-btn`, `link-btn`

## Fonts
Brand font is **Pretendard** (Korean), with Apple SD Gothic Neo fallback — served by the host app at runtime (not shipped in this bundle, so the DS pane renders in a system fallback).

## Where the truth lives
Read `_ds_bundle.css` (compiled component styles, imported by `styles.css`) before styling — it carries the full class + token vocabulary. Per-component API is each `components/<group>/<Name>/<Name>.d.ts`.
