// fonts.ts — variable-font loading, gated through Remotion's delayRender so the first
// frame never rasterises before the wght axis is ready. Inter Variable is BUNDLED under
// public/fonts (offline, deterministic, no CDN/CA dependency at render time), so
// `font-variation-settings:'wght'` animates continuously — the same variable-weight
// typography the Python caption engine uses.

import { continueRender, delayRender, staticFile } from 'remotion';

export const FONT_FAMILY = 'Inter';

let started = false;

/** Idempotent. Call from the composition body; blocks the render until the font is ready. */
export function ensureFont(): void {
  if (started || typeof document === 'undefined') return;
  started = true;
  const handle = delayRender('Loading Inter Variable');
  const done = () => continueRender(handle);
  try {
    const face = new FontFace(
      FONT_FAMILY,
      `url(${staticFile('fonts/InterVariable.ttf')}) format('truetype')`,
      { weight: '100 900', display: 'block' },
    );
    face
      .load()
      .then((loaded) => {
        document.fonts.add(loaded);
        done();
      })
      .catch(done); // never hang a render on a font hiccup
  } catch {
    done();
  }
}
