# DouchkoVE Motion (Remotion PoC)

Separate TypeScript/Remotion stack for **motion graphics only**. The caption pipeline
stays Python (`render.py`, `gfx_engine.py`, `web/server.py`) — untouched. The two are
connected only by a flat, deterministic JSON contract (`src/spec.ts` → `SceneSpec`).

## Why this exists
Live 60fps preview + GPU compositing + variable-weight kinetic type — the things PIL/numpy
can't give the "senior motion designer 2026" bar. This is a **proof of concept**: one
data-driven composition that renders any `SceneSpec` the AI director will emit.

## Architecture
```
src/spec.ts            flat, deterministic data contract (SceneSpec)
src/lib/spring.ts      closed-form damped spring + Whisper→beat trigger binding
src/lib/overlap.ts     continuous-flow overlap manager (scene A eases out / B flies in)
src/lib/layout.ts      collision-free lane solver inside a platform safe zone
src/lib/{easing,rng}   pure curves + deterministic PRNG (no Math.random in render)
src/blocks/*           KineticHeadline, StatCard, AccentUnderline, DeviceFrame, Grain
src/SceneRenderer.tsx  overlap → positioned, animated blocks
src/MotionVideo.tsx    composition root (bg depth + scenes + grain)
src/Root.tsx           registers "MotionVideo"; calculateMetadata derives canvas from spec
src/demo-spec.json     sample spec (single source; used by defaultProps and --props)
```

Determinism is a hard requirement: Remotion renders frames out of order (seek + parallel
workers), so every animation is a **pure function of the frame**. The spring is closed-form
(no Euler stepping, no accumulated state) precisely for this reason.

## Commands
```bash
npm install
npm run typecheck        # tsc --noEmit — CI gate
npm run dev              # Remotion Studio: live preview + scrub
npm run render           # MP4  → out/video.mp4   (uses src/demo-spec.json)
npm run render:prores    # ProRes 4444 → out/video.mov
```

## Contract with the Python side
The AI director (Python or a small Node service) produces a `SceneSpec` JSON. This engine
renders it. Whisper word tokens (`{text,start,end}`) flow straight into
`KineticHeadline.words` and drive the beat-snapped springs — same timing data the caption
engine already produces.

## Status / honesty
- `tsc --noEmit` clean.
- **Rendered for real** in the build sandbox (headless-shell): 252 frames → 1080×1920
  h264 MP4, deterministic, no font errors.
- Visual quality (the actual "senior designer" bar) is only judgeable on a GPU box /
  Studio — a CPU sandbox render proves the pipeline, not the taste.

Font: **Inter Variable is bundled** at `public/fonts/InterVariable.ttf` and loaded via
`staticFile` (offline, no CDN/CA dependency). Inter is licensed under the SIL Open Font
License 1.1 (redistribution permitted).

## Next layers (not built yet)
1. AI director: brief → validated `SceneSpec` (reuses the caption `ai_direct` pattern).
2. More blocks + a curated vocabulary (the 70% that decides "senior" vs "template").
3. Wire into the web product: brief field on the Motion page → Studio-grade live preview →
   server render (this engine) → the existing inline player.
