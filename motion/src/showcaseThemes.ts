// showcaseThemes.ts — four COMPLETELY different visual systems for the same transcript→shots
// engine. Same storyboard, four looks that share nothing: colour, typography, card treatment AND
// motion character (some glide + blur, one hard-cuts with no blur at all). Picked by `styleId`.

export interface ThemeCard {
  readonly bg: string;
  readonly ink: string;
  readonly sub: string;
  readonly radius: number;   // px @1080 authoring scale
  readonly border: string;   // css border, '' for none
  readonly shadow: string;   // css box-shadow at S=1 (scaled by caller), '' for none
}

export interface Theme {
  readonly id: string;
  readonly label: string;
  readonly bg: string;              // studio ground (light shots)
  readonly bgDark: string;          // ground for shots flagged dark
  readonly ground: 'light' | 'dark';
  readonly ink: string;             // primary text on the ground
  readonly sub: string;             // muted text
  readonly accent: string;
  readonly font: string;            // font family stack
  readonly upper: boolean;          // uppercase headings
  readonly weight: number;          // heading weight
  readonly tracking: string;        // heading letter-spacing
  readonly card: ThemeCard;
  readonly trans: number;           // transition seconds (small = hard cut)
  readonly shutter: number;         // motion-blur amount (0 = none)
  readonly cameraMult: number;      // camera-move intensity (0 = locked off)
  readonly overshoot: number;       // entrance overshoot (0 = hard snap)
  readonly grain: number;
  readonly vignette: number;        // 0..1
}

const INTER = `'Inter', system-ui, -apple-system, sans-serif`;
const MONO = `'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', monospace`;

export const THEMES: Record<string, Theme> = {
  // 1) EDITORIAL — clean light studio, glassy real-UI cards, warm accent, smooth camera + blur.
  editorial: {
    id: 'editorial', label: 'Editorial',
    bg: 'radial-gradient(130% 110% at 50% 32%, #fbfbfd 0%, #eef0f3 58%, #e3e6eb 100%)',
    bgDark: 'radial-gradient(130% 110% at 50% 30%, #202634 0%, #141821 60%, #0c0f16 100%)',
    ground: 'light', ink: '#14161c', sub: '#8b8f98', accent: '#f0813a',
    font: INTER, upper: false, weight: 820, tracking: '-0.02em',
    card: { bg: '#ffffff', ink: '#14161c', sub: '#8b8f98', radius: 44, border: '', shadow: '0 30px 70px rgba(20,24,34,0.20), 0 6px 16px rgba(20,24,34,0.10)' },
    trans: 0.85, shutter: 0.62, cameraMult: 1.0, overshoot: 1.0, grain: 2, vignette: 0.10,
  },
  // 2) BOLD — near-black stage, huge electric type dominates, punchy fast cuts, heavy blur.
  bold: {
    id: 'bold', label: 'Bold',
    bg: 'radial-gradient(130% 120% at 50% 40%, #16181f 0%, #0c0e13 60%, #050609 100%)',
    bgDark: 'radial-gradient(130% 120% at 50% 40%, #101218 0%, #070810 100%)',
    ground: 'dark', ink: '#f6f8ff', sub: '#7f8698', accent: '#d7ff2e',
    font: INTER, upper: true, weight: 900, tracking: '-0.03em',
    card: { bg: '#14161d', ink: '#f6f8ff', sub: '#8891a3', radius: 26, border: '2px solid rgba(215,255,46,0.55)', shadow: '0 40px 90px rgba(0,0,0,0.55)' },
    trans: 0.5, shutter: 0.95, cameraMult: 1.35, overshoot: 1.25, grain: 5, vignette: 0.42,
  },
  // 3) SOFT — warm pastel gradient, rounded friendly cards, calm floaty slow camera, no grain.
  soft: {
    id: 'soft', label: 'Soft',
    bg: 'radial-gradient(120% 110% at 50% 30%, #ffeef0 0%, #f3ecff 55%, #e7f0ff 100%)',
    bgDark: 'radial-gradient(120% 110% at 50% 30%, #f7e6ff 0%, #e9e2ff 100%)',
    ground: 'light', ink: '#5a4d63', sub: '#a99fb4', accent: '#ff8fb0',
    font: INTER, upper: false, weight: 680, tracking: '-0.005em',
    card: { bg: '#fffdff', ink: '#5a4d63', sub: '#a99fb4', radius: 60, border: '', shadow: '0 34px 80px rgba(150,120,170,0.22), 0 8px 22px rgba(150,120,170,0.12)' },
    trans: 1.05, shutter: 0.42, cameraMult: 0.7, overshoot: 0.9, grain: 0, vignette: 0.06,
  },
  // 4) MONO — brutalist black on white, monospace, sharp bordered cards, HARD CUTS, NO blur/camera.
  mono: {
    id: 'mono', label: 'Mono',
    bg: '#ffffff', bgDark: '#0a0a0a', ground: 'light', ink: '#000000', sub: '#666666', accent: '#ff3b30',
    font: MONO, upper: true, weight: 700, tracking: '0em',
    card: { bg: '#ffffff', ink: '#000000', sub: '#666666', radius: 0, border: '3px solid #000000', shadow: '' },
    trans: 0.2, shutter: 0.0, cameraMult: 0.0, overshoot: 0.0, grain: 0, vignette: 0.0,
  },
};

export const themeFor = (styleId?: string): Theme => THEMES[styleId ?? 'editorial'] ?? THEMES['editorial']!;
export const STYLE_IDS = Object.keys(THEMES);

// ── Full customization ───────────────────────────────────────────────────────
// Every visual knob is overridable. `Custom` carries per-render overrides the UI produces; the
// compositions resolve their theme via applyTheme(themeFor(style), custom), so ANY setting the
// user changes flows through everything. `text`/`brand`/`logo` override content; the rest override
// the look + motion character. Undefined fields fall back to the chosen style's defaults.
export interface Custom {
  readonly style?: string;
  readonly accent?: string;
  readonly ink?: string;
  readonly sub?: string;
  readonly bg?: string;
  readonly bgDark?: string;
  readonly font?: string;
  readonly upper?: boolean;
  readonly weight?: number;
  readonly tracking?: string;
  readonly grain?: number;
  readonly vignette?: number;
  readonly shutter?: number;      // motion-blur amount
  readonly cameraMult?: number;   // camera-move intensity
  readonly trans?: number;        // transition length
  readonly brand?: string;
  readonly logo?: string;         // data URI
  readonly text?: readonly string[]; // override the on-screen lines
}

const ov = <T,>(v: T | undefined, base: T): T => (v === undefined ? base : v);

/** Resolve the effective theme: the chosen style's defaults with the user's overrides on top. */
export function applyTheme(base: Theme, c?: Custom): Theme {
  if (!c) return base;
  return {
    ...base,
    accent: ov(c.accent, base.accent),
    ink: ov(c.ink, base.ink),
    sub: ov(c.sub, base.sub),
    bg: ov(c.bg, base.bg),
    bgDark: ov(c.bgDark, base.bgDark),
    font: ov(c.font, base.font),
    upper: ov(c.upper, base.upper),
    weight: ov(c.weight, base.weight),
    tracking: ov(c.tracking, base.tracking),
    grain: ov(c.grain, base.grain),
    vignette: ov(c.vignette, base.vignette),
    shutter: ov(c.shutter, base.shutter),
    cameraMult: ov(c.cameraMult, base.cameraMult),
    trans: ov(c.trans, base.trans),
    card: base.card,
  };
}
