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
  | 'deviceFrame';

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

export type Block = KineticHeadline | StatCard | AccentUnderline | DeviceFrame;

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
