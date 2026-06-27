# design-sync notes — dev-hive-web

This repo is a **Next.js app**, not a component library — design-sync runs in its package shape's
synth-entry mode. Quirks a re-sync must know:

- **Self-package symlink (required).** The converter expects `node_modules/<pkg>` to exist. This repo
  doesn't self-install, so before building create: `ln -sfn "$(pwd)" node_modules/dev-hive-web`
  (from `web/`). It's gitignored (node_modules) → **recreate on every fresh clone** or the build
  dies with `ENOENT … node_modules/dev-hive-web/package.json`.
- **No dist build** → synth-entry (`[NO_DIST]`, weaker `.d.ts` contracts). Adding a real component
  build would improve type fidelity. Run from `web/`:
  `node .ds-sync/package-build.mjs --config .design-sync/config.json --node-modules ./node_modules --out ./ds-bundle`
- **CSS**: single global stylesheet `app/globals.css` (cssEntry) — class-based system (rec-card, pill,
  path-*, cur-*, …) + `var(--*)` tokens, indigo `--accent` #4E68C7. Shipped as `_ds_bundle.css`.

## Scope (first sync, 2026-06-27)
- Synced **5 pure presentational components**: ContentCard, StateView, ComingSoon, RouteError, Heatmap.
- **Floor cards** (no authored previews) + `--no-render-check` (renders NOT machine-verified — no
  chromium installed). Lean first pass.

## Re-sync risks / next steps
- **Excluded nav components** (RecommendationCard→FeedbackButtons, FilterBar, SearchBar, Pagination,
  TopBar, ReadModal, LeftRail, AuthForm, UploadForm, GraphCanvas): they import `next/navigation` /
  `next/link` (or canvas for GraphCanvas). To include them, shim next/* → stubs via a build-only
  tsconfig `paths` (e.g. `"next/navigation": ["./.design-sync/shims/next-navigation.ts"]`) so esbuild
  aliases them; otherwise they render blank in the DS pane and throw in designs.
- **Fonts**: Pretendard + Apple SD Gothic Neo are declared `runtimeFontPrefixes` (host-app serves
  them). The DS pane renders these in a system fallback — to ship them, add woff2 + @font-face via
  `cfg.extraFonts`.
- **Authored previews**: none yet (floor cards). Author `.design-sync/previews/<Name>.tsx` on any
  re-sync for richer cards — ContentCard especially needs realistic `content` props to render well.
- **Render verification**: never run (no chromium). Install playwright+chromium and drop
  `--no-render-check` to machine-verify.
