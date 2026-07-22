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

## AI director (built)
`src/director/` — brief → validated `SceneSpec`, same shape as the Python `ai_direct`:
- `vocabulary.ts` — the curated design language + the "senior 2026" system prompt.
- `director.ts` — GPT-4o composes from the vocabulary; falls back to…
- `heuristic.ts` — a deterministic brief→spec composer (works with no key; the offline path).
- `schema.ts` — Zod validator; the renderer only ever sees a schema-valid spec.
- `run.ts` — CLI bridge: `node out/run.mjs "<brief>" > spec.json` → `remotion render --props`.

Proven: two different briefs → two different, valid, deterministic specs, both rendered
(a brief with "3.4M" auto-becomes a count-up stat; a different brief picks a different
palette). Cleaner copy comes from the GPT path (needs OPENAI_API_KEY).

## One-command bridge (built)
```bash
npm run brief -- "5 reasons this blows up. Fast, bold, made for you." out/video.mp4
# brief → director → validated SceneSpec → Remotion render → MP4 (add --codec=prores for 4444)
```
Self-contained: the Python server spawns this exactly like it spawns `gfx_engine.py` today,
then serves the output file through the existing motion job flow. Proven end-to-end on CPU.

## Wiring into the live product — NEEDS SIGN-OFF (touches deploy)
This is the only step that changes the running container, so it is documented, not applied:

1. **Dockerfile** — add Node 22 + `npm ci` in `motion/` + a headless browser:
   ```dockerfile
   RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs
   COPY motion/ /app/motion/
   RUN cd /app/motion && npm ci && npx remotion browser ensure
   ```
2. **web/server.py** — in the motion worker, for a "brief" job spawn:
   ```py
   subprocess.run(["node", "scripts/render-brief.mjs", brief, out_mp4], cwd=ROOT+"/motion")
   ```
   Credits / queue / library / the v101o inline player all stay as-is.
3. **Frontend** — a brief input on the Motion page; optional client-side `@remotion/player`
   live preview (bundle the composition once, mount `<Player>`), zero server cost.

Risk note: the browser download + image size grow the container; a failed `npm ci`/browser
fetch would fail the autodeploy rebuild. Apply behind a check and test the image build once
before the first live deploy.
