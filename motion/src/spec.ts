// spec.ts — the flat, deterministic data contract between the Zero-Timeline UI,
// the AI director and the renderer. Same spec + same frame -> same pixels.
//
// Invariants:
//  - all times are absolute SECONDS (the renderer converts to frames via fps);
//  - no nested scene trees — a scene is a flat list of blocks;
//  - no runtime randomness without `seed`;
//  - every animatable has an explicit trigger + spring, so the render is stateless
//    per frame (required for Remotion seeking and for RAM-flat rendering).

export type Format = '9:16' | '16:9' | '1:1';

export type BlockKind =
  | 'kineticHeadline'
  | 'statCard'
  | 'accentUnderline'
  | 'deviceFrame'
  | 'chipRow'
  | 'bigQuote'
  // Pure-graphic blocks (no text) — the "motion graphics, no words" vocabulary.
  // These are FULL-BLEED: they ignore the lane solver and fill the scene; `slot`
  // becomes their z-order (0 = back). Composited back-to-front for depth.
  | 'gradientMesh'
  | 'glowOrb'
  | 'orbitRings'
  | 'shapeField'
  | 'waveLines';

/** Full-bleed graphic kinds fill the canvas instead of occupying a layout lane. */
export const FULL_BLEED: ReadonlySet<BlockKind> = new Set<BlockKind>([
  'gradientMesh',
  'glowOrb',
  'orbitRings',
  'shapeField',
  'waveLines',
]);

export type TransitionKind = 'rise' | 'whip' | 'fade' | 'scaleIn';

/** A damped spring described by physics, not keyframes. damping<1 => overshoot ("pop"). */
export interface Spring {
  readonly stiffness: number; // ω0² proxy; higher = snappier
  readonly damping: number; // ζ in (0,1]; <1 overshoots
  readonly delay: number; // s, relative to the block/word trigger
}

export interface Transition {
  readonly kind: TransitionKind;
  readonly dur: number; // s — the crossfade half-window
}

/** One Whisper token. The kinetic type snaps to these onsets (optionally beat-quantised). */
export interface WordToken {
  readonly text: string;
  readonly start: number; // s
  readonly end: number; // s
}

export interface BeatGrid {
  readonly bpm: number;
  readonly offset: number; // s, first downbeat
  readonly snapTol: number; // s, max shift allowed when snapping an onset
}

interface BlockBase {
  readonly id: string;
  readonly kind: BlockKind;
  readonly slot: number; // layout lane [0..N); the solver keeps lanes collision-free
  readonly spring: Spring;
}

export interface KineticHeadline extends BlockBase {
  readonly kind: 'kineticHeadline';
  readonly words: readonly WordToken[]; // per-word timing drives the springs
  readonly weight: [number, number]; // variable-font wght axis: [rest, peak]
  readonly beatSync: boolean;
}

export interface StatCard extends BlockBase {
  readonly kind: 'statCard';
  readonly value: number; // final numeric value
  readonly prefix?: string;
  readonly suffix?: string;
  readonly label: string;
  readonly countUp: boolean;
}

export interface AccentUnderline extends BlockBase {
  readonly kind: 'accentUnderline';
  readonly follows: string; // id of the block it underlines
  readonly widthPct: number; // 0..1 of the lane width
}

export interface DeviceFrame extends BlockBase {
  readonly kind: 'deviceFrame';
  readonly src: string; // staticFile() asset name
  readonly depth: number; // 0..1 parallax
}

export interface ChipRow extends BlockBase {
  readonly kind: 'chipRow';
  readonly items: readonly string[]; // 1..5 short pills
}

export interface BigQuote extends BlockBase {
  readonly kind: 'bigQuote';
  readonly text: string;
  readonly author?: string;
}

/** Living mesh-gradient field — soft colour blobs drifting on Lissajous paths. */
export interface GradientMesh extends BlockBase {
  readonly kind: 'gradientMesh';
  readonly colors: readonly string[]; // 2..5 hex; falls back to palette
  readonly speed: number; // drift rate, ~0.2..1.5
}

/** Hero luminous sphere: core + bloom + rotating specular sweep, breathing on the beat. */
export interface GlowOrb extends BlockBase {
  readonly kind: 'glowOrb';
  readonly radiusPct: number; // 0.1..0.6 of min(w,h)
  readonly beatPulse: boolean; // scale spikes on each downbeat
  readonly hueDrift: number; // deg over the scene, subtle (0..60)
}

/** Concentric thin rings with a bright travelling arc + glow node, counter-rotating. */
export interface OrbitRings extends BlockBase {
  readonly kind: 'orbitRings';
  readonly rings: number; // 1..5
  readonly spin: number; // base deg/s (sign alternates per ring)
}

/** Scattered geometric shapes that spring in on a scrambled stagger, then drift + rotate. */
export interface ShapeField extends BlockBase {
  readonly kind: 'shapeField';
  readonly count: number; // 4..40
  readonly shape: 'mixed' | 'dot' | 'ring' | 'triangle' | 'plus' | 'square';
  readonly drift: number; // parallax drift amount, 0..1
}

/** Stacked flowing sine lines — an equaliser/soundwave whose amplitude pulses on the beat. */
export interface WaveLines extends BlockBase {
  readonly kind: 'waveLines';
  readonly lines: number; // 2..12
  readonly amp: number; // 0..1 of half-canvas
}

export type Block =
  | KineticHeadline
  | StatCard
  | AccentUnderline
  | DeviceFrame
  | ChipRow
  | BigQuote
  | GradientMesh
  | GlowOrb
  | OrbitRings
  | ShapeField
  | WaveLines;

export interface Scene {
  readonly id: string;
  readonly tStart: number; // s, absolute
  readonly tLen: number; // s, hold duration (excludes transitions)
  readonly in: Transition;
  readonly out: Transition;
  readonly blocks: readonly Block[];
}

export interface Palette {
  readonly bg: string;
  readonly fg: string;
  readonly accent: string;
  readonly muted: string;
}

/** Payload for the UI-mockup templates (rendered by the MotionApple composition). */
export type UiTemplate = 'pills' | 'appcard' | 'search' | 'homescreen' | 'chat' | 'notify';
export interface UiSpec {
  readonly template: UiTemplate;
  readonly title?: string;
  readonly subtitle?: string;
  readonly lines: readonly string[]; // pills / chat messages / notify lines
  readonly accent: string;
  // User-supplied brand image (data URI). When set it replaces the generated app icon /
  // chat avatar / featured tile so the mockup carries the user's own logo. Pillar 2.
  readonly logo?: string;
}

/**
 * The elaborate cross-transitions the sequencer can play at a boundary. 'auto' lets the
 * engine pick a varied, non-repeating sequence deterministically from the seed.
 */
export type TransId = 'push' | 'panv' | 'cover' | 'dolly' | 'swoosh' | 'tilt';

/** One segment of a chained sequence: a UI mockup shown for `dur` seconds. */
export interface SeqSegment {
  readonly ui: UiSpec;
  readonly dur: number; // seconds on screen (incl. its half of each transition)
  // The transition PLAYED INTO this segment (i.e. the boundary before it). Undefined =
  // auto-varied by the engine. Ignored for the first segment (nothing precedes it).
  readonly transition?: TransId;
}

export interface SceneSpec {
  readonly version: 1;
  readonly seed: number; // seeds all procedural jitter -> deterministic
  readonly canvas: { readonly format: Format; readonly w: number; readonly h: number };
  readonly fps: number;
  readonly duration: number; // s
  readonly grain: number; // 0..10
  readonly palette: Palette;
  readonly beat: BeatGrid;
  readonly scenes: readonly Scene[];
  readonly ui?: UiSpec; // set for UI-mockup templates; MotionApple renders it
  readonly sequence?: readonly SeqSegment[]; // set for chained sequences; MotionSequence renders it
  // Transition-SFX keys whose audio assets are actually present (fs-checked by the director).
  // MotionSequence only mounts <Audio> for keys listed here — no asset -> silent (never a
  // cheap synthetic beep). Undefined/empty = the sequence renders silent.
  readonly sfx?: readonly string[];
  // User-supplied custom font (data URI + family name). When set, all mockup text renders
  // in the user's own typeface. Loaded via FontFace under delayRender. Pillar 2.
  readonly font?: { readonly family: string; readonly url: string };
}

// ---------------------------------------------------------------------------------------
// AUTO-OVERLAY (v108): a full uploaded video + AI-directed motion graphics laid ON TOP of it
// at content-matched timestamps. The AI (GPT-5 vision + transcript) emits a plan of beats;
// deterministic guardrails enforce density/safe-zones/timing; MotionOverlay composites the
// video (OffthreadVideo) with the beats. Everything is pure in t (seekable, deterministic).

// Text-carrying kinds + PURE-GRAPHIC kinds (no text): burst (impact shards + ring), sweep
// (accent band wipes across), pulse (full-frame accent energy hit), brackets (focus corners).
export type OverlayKind = 'headline' | 'lowerthird' | 'keyword' | 'chips' | 'stat' | 'brand'
  | 'burst' | 'sweep' | 'pulse' | 'brackets';
export type OverlayAnchor = 'top' | 'upper' | 'center' | 'lower' | 'bottom';
export type OverlayEnter = 'rise' | 'pop' | 'slide' | 'wipe';

/** One motion-graphic moment placed over the video. */
export interface OverlayBeat {
  readonly t: number;        // start, seconds (absolute video time)
  readonly dur: number;      // on-screen duration, seconds
  readonly kind: OverlayKind;
  readonly text?: string;    // main line (headline/lowerthird/keyword/brand)
  readonly text2?: string;   // second line (lowerthird sub, brand tagline)
  readonly items?: readonly string[]; // chips
  readonly value?: number;   // stat count-up target
  readonly prefix?: string;
  readonly suffix?: string;
  readonly label?: string;   // stat label
  readonly anchor: OverlayAnchor;
  readonly enter: OverlayEnter;
  readonly emphasis: number; // 0..1 → scale / weight / glow
}

export interface OverlayVideo {
  readonly src: string;      // staticFile-relative name under public/
  readonly w: number; readonly h: number; readonly fps: number; readonly duration: number;
}

export interface OverlayPlan {
  readonly version: 1;
  readonly seed: number;
  readonly video: OverlayVideo;
  readonly accent: string;
  readonly logo?: string;    // brand image data URI (Pillar 2, in overlays too)
  readonly font?: { readonly family: string; readonly url: string };
  readonly platform?: 'tiktok' | 'reels' | 'shorts' | 'none'; // safe-zone masks
  readonly beats: readonly OverlayBeat[];
}

/** Runtime guard: the AI director's JSON is validated before it ever reaches the renderer. */
export function isSceneSpec(x: unknown): x is SceneSpec {
  if (typeof x !== 'object' || x === null) return false;
  const s = x as Partial<SceneSpec>;
  return (
    s.version === 1 &&
    typeof s.fps === 'number' &&
    typeof s.duration === 'number' &&
    Array.isArray(s.scenes) &&
    typeof s.canvas === 'object' &&
    s.canvas !== null
  );
}
