// MotionShowcase — a full 1:1 rebuild of the reference-style "UI motion montage": a chain of
// hand-designed shots (kinetic typography, floating dark UI cards, iMessage bubbles, a widget
// stage with a cursor, pill buttons with a device, an NLE timeline) on a clean studio ground,
// 16:9. The point Ismet cares about: the TRANSITIONS, the INTERACTIVE moments, and how SMOOTH
// it reads. So every hand-off is camera-driven (slide with real motion-blur echoes, a
// scale-morph through a dot, a dolly push) — nothing ever blur-DISSOLVES out — and each shot
// has a live interaction (a search is submitted, a cursor taps, a playhead sweeps, a message
// sends) that drives the move into the next shot.
//
// Pure in `t` (seekable, RAM-flat): every value is a closed-form function of the frame. No
// useFrame, no Math.random in the render path. All text is data (a storyboard the AI director
// can emit from a transcript) — the component invents nothing.

import React from 'react';
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig,
} from 'remotion';
import type { SceneSpec } from './spec';
import { clamp01, easeOutQuint, easeInOutCubic, easeInOutQuint, easeOutBack, mix } from './lib/easing';
import { springStep } from './lib/spring';
import { hash01 } from './lib/rng';
import { FONT_FAMILY } from './fonts';
import { themeFor, type Theme } from './showcaseThemes';

const FONT = `'${FONT_FAMILY}', system-ui, -apple-system, "SF Pro Display", sans-serif`;

// The storyboard can come from props (per-user, generated from a transcript by the director) —
// falling back to the built-in demo storyboard when none is supplied.
export type MotionShowcaseProps = { readonly spec: SceneSpec; readonly story?: readonly Shot[]; readonly styleId?: string };

// ───────────────────────────────────────────────────────────────────────────── storyboard
// Each shot names an archetype + its (transcript-sourced) copy + how long it holds. The
// order and copy mirror the reference montage's message so the rebuild is 1:1 in feel.

export type ShotKind =
  | 'ktypo' | 'timer' | 'notes' | 'searchbar' | 'imessage'
  | 'widgets' | 'pill' | 'timeline' | 'signoff';
export type TransKind = 'slideL' | 'morph' | 'push' | 'slideUp';

export interface Shot {
  readonly kind: ShotKind;
  readonly dur: number;              // seconds held (incl. its half of each transition)
  readonly into: TransKind;          // the transition PLAYED INTO this shot
  readonly dark?: boolean;           // dark studio ground instead of light
  readonly accentText?: string;      // headline / accent copy (verbatim, from transcript)
  readonly a?: string; readonly b?: string; readonly c?: string; // per-shot payload
  readonly v?: number;               // 0..1 per-shot motion-variation knob (seeded per video):
                                     // flips camera direction + scales magnitude so two videos
                                     // never move identically, even with the same archetype.
}

// ONE coherent script, read top to bottom, is the through-line — a senior never ships a bag of
// disconnected frames. Each shot illustrates its own line; the on-screen text is a verbatim
// phrase from that line (so it also honours v110: words only ever come from the transcript).
// Reads as: "Your story deserves better motion. Not another template pack — real, hand-made
// design. Buttery smooth, Apple-style motion. Search your transcript: every word. Never
// invented. The mechanics: real UI. Rendered frame by frame. Perfectly timed to your voice.
// Sixty frames a second. Made with DouchkoVE."
const STORY: readonly Shot[] = [
  { kind: 'ktypo',    dur: 3.0, into: 'slideL', accentText: 'Your story deserves better motion' },
  { kind: 'notes',    dur: 3.2, into: 'push',   dark: true, accentText: 'Not another template pack', b: 'Real, hand-made design' },
  { kind: 'searchbar',dur: 2.9, into: 'slideUp',dark: true, accentText: 'your transcript', b: 'Every word' },
  { kind: 'imessage', dur: 3.0, into: 'slideL', a: 'Buttery smooth', b: 'Apple-style motion' },
  { kind: 'pill',     dur: 2.6, into: 'morph',  accentText: 'Never invented' },
  { kind: 'widgets',  dur: 3.4, into: 'push',   accentText: 'the mechanics' },
  { kind: 'timer',    dur: 2.8, into: 'slideL', accentText: 'Frame by frame' },
  { kind: 'timeline', dur: 3.4, into: 'push',   accentText: 'Perfectly timed to your voice' },
  { kind: 'ktypo',    dur: 2.6, into: 'morph',  accentText: 'Sixty frames a second', c: 'warm' },
  { kind: 'signoff',  dur: 3.0, into: 'morph',  accentText: 'made with DouchkoVE' },
];

// The active theme for this render job. ShowcaseBody sets it once (styleId is constant per job,
// so this stays deterministic) and every shot component reads it — the four styles share nothing.
let TH: Theme = themeFor(undefined);

// ───────────────────────────────────────────────────────────────────────────── helpers

/** A camera-style layer transform for one shot: pure POSITION (x/y/scale/alpha). Motion blur is
 *  no longer baked here — it is MEASURED from how this transform changes frame-to-frame, so every
 *  move (entrances, idle drift, hand-offs) smears continuously and correctly, like the reference. */
interface Cam { x: number; y: number; scale: number; alpha: number; }
const IDENT: Cam = { x: 0, y: 0, scale: 1, alpha: 1 };

/** enter side of a boundary transition (progress 0→1 as the shot arrives). Camera-grade eases. */
function enterCam(kind: TransKind, e: number, W: number, H: number): Cam {
  const o = easeInOutQuint(e);
  switch (kind) {
    case 'slideL':  return { x: (1 - o) * W * 0.92, y: 0, scale: 1, alpha: clamp01(e * 2.4) };
    case 'slideUp': return { x: 0, y: (1 - o) * H * 0.88, scale: 1, alpha: clamp01(e * 2.4) };
    case 'push':    return { x: 0, y: 0, scale: mix(0.8, 1, easeOutBack(e)), alpha: clamp01(e * 2.4) };
    case 'morph':   return { x: 0, y: 0, scale: mix(0.05, 1, easeInOutQuint(e)), alpha: clamp01(e * 3.2) };
  }
}
/** exit side (progress 0→1 as the shot leaves). Mirror of the NEXT shot's transition. */
function exitCam(kind: TransKind, x: number, W: number, H: number): Cam {
  const o = easeInOutQuint(x);
  switch (kind) {
    case 'slideL':  return { x: -o * W * 0.92, y: 0, scale: 1, alpha: clamp01((1 - x) * 2.4) };
    case 'slideUp': return { x: 0, y: -o * H * 0.88, scale: 1, alpha: clamp01((1 - x) * 2.4) };
    case 'push':    return { x: 0, y: 0, scale: mix(1, 1.18, o), alpha: clamp01((1 - x) * 2.4) };
    case 'morph':   return { x: 0, y: 0, scale: mix(1, 0.05, easeInOutQuint(x)), alpha: clamp01((1 - x) * 3.2) };
  }
}
const composeCam = (en: Cam, ex: Cam): Cam => ({
  x: en.x + ex.x, y: en.y + ex.y, scale: en.scale * ex.scale, alpha: Math.min(en.alpha, ex.alpha),
});

/** A held shot never freezes: a slow, seed-varied float + breathing scale keeps it alive (and
 *  feeds a whisper of continuous motion blur so even the "still" moments read smooth). */
const idleDrift = (t: number, phase: number): Cam => ({
  x: Math.sin(t * 0.7 + phase) * 5, y: Math.cos(t * 0.55 + phase * 1.3) * 4,
  scale: 1 + Math.sin(t * 0.5 + phase) * 0.004, alpha: 1,
});

const easeInOutSine = (x: number): number => -(Math.cos(Math.PI * clamp01(x)) - 1) / 2;

/**
 * The INTERACTIVE camera: a motivated move that lives INSIDE each shot (not just at the
 * boundaries). It starts at neutral when the shot arrives (so it never fights the entrance)
 * and glides through the hold — the way an operator tracks the subject: pan ALONG the opening
 * headline, push INTO a punchline, crane with a conversation, and literally FOLLOW the timeline
 * playhead. `p` is progress 0→1 through the shot. Because the layer's velocity is measured for
 * motion blur, every one of these camera moves smears on its own — buttery, for free.
 */
const shotCam = (kind: ShotKind, warm: boolean, p: number, W: number, H: number, v = 0.5): Cam => {
  const e = easeInOutSine(p);
  const base = { x: 0, y: 0, scale: 1, alpha: 1 };
  const dir = v < 0.5 ? -1 : 1;          // seeded left/right (or up/down) flip
  const m = 0.65 + v * 0.8;              // seeded magnitude 0.65..1.45 — no two videos move alike
  switch (kind) {
    case 'ktypo':   // glide along the type — direction + amount seeded, kept small so long
                    // headlines never leave the frame
      return { ...base, x: (warm ? -dir : dir) * e * W * 0.06 * m, scale: 1 + e * 0.05 * m };
    case 'timer':   return { ...base, x: dir * e * W * 0.05 * m, scale: 1 + e * 0.06 * m };
    case 'notes':   return { ...base, y: e * H * 0.06 * m, scale: 1 + e * 0.05 * m };   // crane down with the typing
    case 'searchbar': return { ...base, y: e * H * 0.03 * m, scale: 1 + e * 0.08 * m }; // push onto the link
    case 'imessage': return { ...base, y: -e * H * 0.07 * m, scale: 1 + e * 0.03 * m }; // crane up with the reply
    case 'widgets': return { ...base, x: dir * e * W * 0.03 * m, y: e * H * 0.025 * m, scale: 1 + e * 0.09 * m }; // push toward the tap
    case 'pill':    return { ...base, scale: 1 + e * (0.05 + 0.03 * v) };
    case 'timeline': return { ...base, x: -e * W * 0.14 * (0.8 + 0.4 * v), scale: 1 + e * 0.05 }; // FOLLOW the playhead (dir fixed, amount seeded)
    case 'signoff': return { ...base, scale: 1 + e * 0.05 };
    default:        return base;
  }
};

const layerCss = (c: Cam): React.CSSProperties => ({
  position: 'absolute', inset: 0, opacity: clamp01(c.alpha),
  transform: `translate3d(${c.x.toFixed(2)}px,${c.y.toFixed(2)}px,0) scale(${c.scale.toFixed(4)})`,
  transformOrigin: '50% 50%', willChange: 'transform, opacity', backfaceVisibility: 'hidden',
});

/** Real per-frame motion blur: sample the layer's motion vector (dx,dy) + zoom rate for THIS
 *  frame and lay a fan of ghost copies along it — trailing AND leading (a symmetric shutter),
 *  so fast moves smear like a real camera and slow drifts get a soft edge. Continuous, not gated. */
const MotionSmear: React.FC<{ dx: number; dy: number; iso: number; children: React.ReactNode }> = ({ dx, dy, iso, children }) => {
  const mag = Math.hypot(dx, dy);
  if (mag < 1.1 && iso < 0.4) return <>{children}</>;
  const N = 8;
  return (
    <>
      {Array.from({ length: N }, (_, i) => {
        const f = (i / (N - 1)) - 0.5; // -0.5..+0.5 → symmetric smear around the true position
        return (
          <div key={i} style={{
            position: 'absolute', inset: 0, opacity: 1 / N,
            transform: `translate3d(${(dx * f).toFixed(2)}px,${(dy * f).toFixed(2)}px,0)`,
            filter: iso > 0.4 ? `blur(${iso.toFixed(2)}px)` : undefined, pointerEvents: 'none',
          }}>{children}</div>
        );
      })}
    </>
  );
};

/** Big kinetic word-by-word headline with a spring-in per word (scrambled stagger). Each word
 *  carries its own vertical motion blur during the pop (sampled from the spring's velocity), so
 *  the type glides in buttery-smooth instead of stepping frame to frame. */
const Kinetic: React.FC<{ text: string; t: number; fs: number; color: string; weight?: number }>
  = ({ text, t, fs, color, weight }) => {
  const wght = weight ?? TH.weight;
  const words = text.split(' ');
  const spring = { stiffness: 150, damping: 0.7, delay: 0 };
  const dt = 1 / 60;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `0 ${fs * 0.28}px`, maxWidth: '78%' }}>
      {words.map((w, i) => {
        const delay = 0.05 + hash01(i, 7) * 0.18 + i * 0.05;
        const e = t - delay;
        const s = springStep(e, spring);
        const sPrev = springStep(e - dt, spring);
        const y = (1 - s) * fs * 0.5;
        const dyFrame = (s - sPrev) * fs * 0.5;           // per-frame vertical travel
        const smear = Math.min(fs * 0.5, Math.abs(dyFrame) * TH.shutter);
        const appear = clamp01(e * 3);
        const base: React.CSSProperties = {
          display: 'inline-block', color, fontFamily: TH.font, fontWeight: wght,
          fontSize: fs, lineHeight: 1.05, letterSpacing: TH.tracking,
          textTransform: TH.upper ? 'uppercase' : 'none',
        };
        const word = (
          <span style={{ ...base, transform: `translateY(${y.toFixed(1)}px) scale(${(0.9 + 0.1 * s).toFixed(3)})` }}>{w}</span>
        );
        return (
          <div key={i} style={{ position: 'relative', opacity: appear, filter: appear < 1 ? `blur(${((1 - appear) * 5).toFixed(1)}px)` : undefined }}>
            {smear > 1.5 && Array.from({ length: 6 }, (_, k) => {
              const f = (k / 5) - 0.5;
              return <span key={k} style={{ ...base, position: 'absolute', left: 0, top: 0, opacity: 1 / 6,
                transform: `translateY(${(y - dyFrame * TH.shutter * f).toFixed(1)}px) scale(${(0.9 + 0.1 * s).toFixed(3)})` }}>{w}</span>;
            })}
            <span style={{ visibility: smear > 1.5 ? 'hidden' : 'visible', ...base, transform: `translateY(${y.toFixed(1)}px) scale(${(0.9 + 0.1 * s).toFixed(3)})` }}>{w}</span>
          </div>
        );
      })}
    </div>
  );
};

/** The Apple mark (vector) — a real logo, not a placeholder blob. */
const AppleMark: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size * 1.2} viewBox="0 0 24 28" fill={color} style={{ display: 'block' }}>
    <path d="M17.5 14.9c0-3 2.4-4.4 2.5-4.5-1.4-2-3.5-2.3-4.2-2.3-1.8-.2-3.5 1-4.4 1-.9 0-2.3-1-3.8-1-1.9 0-3.7 1.1-4.7 2.9-2 3.5-.5 8.6 1.4 11.4.9 1.4 2 2.9 3.5 2.8 1.4-.1 1.9-.9 3.6-.9 1.7 0 2.1.9 3.6.9 1.5 0 2.4-1.4 3.3-2.7 1-1.5 1.5-3 1.5-3.1-.1 0-2.8-1.1-2.8-4.4z" />
    <path d="M14.9 6.2c.8-1 1.3-2.3 1.2-3.7-1.1.1-2.5.8-3.3 1.7-.7.8-1.4 2.2-1.2 3.5 1.2.1 2.5-.6 3.3-1.5z" />
  </svg>
);

/** A cursor (pointing-hand) that moves to a target and taps (press dips it). */
const Cursor: React.FC<{ x: number; y: number; press: number; s: number }> = ({ x, y, press, s }) => (
  <svg width={54 * s} height={54 * s} viewBox="0 0 54 54" style={{
    position: 'absolute', left: x, top: y, transform: `scale(${1 - press * 0.14})`,
    transformOrigin: '30% 30%', filter: 'drop-shadow(0 6px 10px rgba(0,0,0,0.25))',
  }}>
    <path d="M14 6 L14 40 L21 33 L26 45 L31 43 L26 31 L36 31 Z" fill="#fff" stroke="#111" strokeWidth="2.4" strokeLinejoin="round" />
  </svg>
);

// ───────────────────────────────────────────────────────────────────────────── shot renderers
// Each gets local time `t` (s from shot start), the shot's total `hold` seconds, the studio
// dims, the accent, and `press` (0→1 in the last ~0.3s: the interaction that fires the hand-off).

interface ShotCtx { shot: Shot; t: number; hold: number; W: number; H: number; S: number; accent: string; press: number; }

const cardShadow = (_s: number): string => TH.card.shadow || 'none';
const cardBorder = (): string | undefined => TH.card.border || undefined;

/** Shot: full-frame kinetic typography (+ optional Apple mark) on the studio ground. */
const ShotKtypo: React.FC<ShotCtx> = ({ shot, t, W, H, S, accent }) => {
  const warm = shot.c === 'warm';
  const color = warm ? accent : TH.ink;
  // auto-fit: long headlines shrink so they never clip the frame (and never collide with the
  // camera glide). Bucketed by character count — robust for whatever copy the director emits.
  const chars = shot.accentText!.length;
  const fit = chars > 30 ? 0.6 : chars > 22 ? 0.72 : chars > 14 ? 0.86 : 1;
  const fs = 128 * S * fit;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: fs * 0.24 }}>
        <Kinetic text={shot.accentText!} t={t} fs={fs} color={color} />
        {shot.b === 'apple' && (
          <div style={{ opacity: clamp01((t - 0.45) * 2.4), transform: `scale(${(0.7 + 0.3 * easeOutBack(clamp01((t - 0.45) * 1.6))).toFixed(3)})` }}>
            <AppleMark size={fs * 0.92} color="#4a4f5a" />
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** Shot: a floating dark render-progress card — a ring that FILLS while the centre percentage
 *  counts up in lockstep (internally consistent), a label from the script. "Frame by frame." */
const ShotTimer: React.FC<ShotCtx> = ({ shot, t, hold, S, accent }) => {
  const cw = 820 * S, ch = 300 * S;
  const app = easeOutBack(clamp01((t - 0.1) * 1.4));
  const prog = easeInOutCubic(clamp01((t - 0.35) / Math.max(0.6, hold - 0.7))); // 0 → 1 over the hold
  const pct = Math.round(prog * 100);
  const R = 96 * S, C = 2 * Math.PI * R;
  const cx = 150 * S, cy = ch / 2;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: cw, height: ch, borderRadius: 44 * S, background: '#0e0f12',
        boxShadow: cardShadow(S), transform: `scale(${app.toFixed(3)})`, position: 'relative' }}>
        <svg width={cw} height={ch} style={{ position: 'absolute', inset: 0 }}>
          <circle cx={cx} cy={cy} r={R} fill="none" stroke="#26282e" strokeWidth={12 * S} />
          <circle cx={cx} cy={cy} r={R} fill="none" stroke={accent} strokeWidth={12 * S}
            strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - prog)}
            transform={`rotate(-90 ${cx} ${cy})`} />
        </svg>
        {/* percentage counts up EXACTLY with the ring — one truth, not two */}
        <div style={{ position: 'absolute', left: cx - R, top: cy - 30 * S, width: R * 2, textAlign: 'center',
          color: '#fff', fontFamily: TH.font, fontWeight: 700, fontSize: 56 * S, letterSpacing: '-0.03em' }}>{pct}%</div>
        <div style={{ position: 'absolute', left: 320 * S, top: cy - 46 * S, right: 40 * S,
          color: '#fff', fontFamily: TH.font, fontWeight: 700, fontSize: 60 * S, letterSpacing: '-0.02em', lineHeight: 1.05 }}>
          {shot.accentText}
          <div style={{ color: '#8b8f98', fontWeight: 600, fontSize: 30 * S, marginTop: 8 * S }}>Rendering…</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Shot: dark notes/reader with a nav chrome — a note being written live: line 1 is there,
 *  line 2 types in behind a blinking caret. (No search magnifier here — this is a reader, not a
 *  search field; the magnifier lives only in the searchbar shot, where it's logical.) */
const ShotNotes: React.FC<ShotCtx> = ({ shot, t, W, H, S, accent }) => {
  const line1 = shot.accentText!, line2 = shot.b!;
  const type2 = Math.round(clamp01((t - 0.7) / 1.1) * line2.length);
  const caretOn = Math.floor(t * 1.6) % 2 === 0;
  const cw = 1180 * S, ch = 620 * S;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: cw, height: ch, borderRadius: 40 * S, background: '#000', boxShadow: cardShadow(S),
        position: 'relative', overflow: 'hidden' }}>
        {/* nav chrome */}
        <div style={{ position: 'absolute', top: 34 * S, left: 40 * S, width: 74 * S, height: 74 * S, borderRadius: '50%',
          background: '#1c1d22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={26 * S} height={26 * S} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </div>
        <div style={{ position: 'absolute', top: 34 * S, right: 150 * S, width: 150 * S, height: 74 * S, borderRadius: 40 * S,
          background: '#1c1d22', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 22 * S }}>
          <svg width={24 * S} height={24 * S} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4"><path d="M12 3v11M12 3l-4 4M12 3l4 4M5 14v5h14v-5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <span style={{ color: '#fff', fontSize: 30 * S, letterSpacing: 2 }}>•••</span>
        </div>
        <div style={{ position: 'absolute', top: 34 * S, right: 40 * S, width: 74 * S, height: 74 * S, borderRadius: '50%',
          background: '#e7b73a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={30 * S} height={30 * S} viewBox="0 0 24 24" fill="none" stroke="#111" strokeWidth="3.4"><path d="M5 13l4 4 10-11" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </div>
        {/* body text — line 2 types in behind a blinking caret */}
        <div style={{ position: 'absolute', left: 60 * S, top: 180 * S, right: 60 * S, color: '#fff',
          fontFamily: TH.font, fontWeight: 500, fontSize: 68 * S, lineHeight: 1.28, letterSpacing: '-0.01em' }}>
          <div style={{ opacity: clamp01(t * 3) }}>{line1}</div>
          <div>{line2.slice(0, type2)}<span style={{ color: accent, opacity: caretOn ? 0.95 : 0.1,
            fontWeight: 300 }}>|</span></div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Shot: a white search field dropping in over black, with a blue result link (chromatic hit). */
const ShotSearchbar: React.FC<ShotCtx> = ({ shot, t, W, H, S, press }) => {
  const drop = easeOutBack(clamp01((t - 0.05) * 1.4));
  const linkApp = clamp01((t - 0.8) * 2.4);
  const glitch = Math.max(0, 1 - Math.abs(t - 1.1) * 5) * 6 * S; // brief chromatic split on reveal
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center' }}>
      {/* search field pinned near the top, dropping in */}
      <div style={{ marginTop: 40 * S, width: 1500 * S, height: 150 * S, borderRadius: '0 0 60px 60px',
        background: '#fff', boxShadow: cardShadow(S), display: 'flex', alignItems: 'center', paddingLeft: 70 * S,
        transform: `translateY(${((drop - 1) * 200 * S).toFixed(1)}px)`, color: TH.ink, fontFamily: TH.font,
        fontWeight: 600, fontSize: 66 * S }}>{shot.accentText}</div>
      {/* the blue result link, with a momentary RGB split. All three layers are nowrap + exactly
          overlaid so the split never reflows the words (was doubling onto a 2nd line). */}
      <div style={{ marginTop: 150 * S, position: 'relative', opacity: linkApp, whiteSpace: 'nowrap' }}>
        {glitch > 0.4 && <>
          <span style={{ position: 'absolute', top: 0, left: -glitch, whiteSpace: 'nowrap', color: '#ff2d55', fontFamily: TH.font, fontWeight: 700, fontSize: 96 * S }}>{shot.b}</span>
          <span style={{ position: 'absolute', top: 0, left: glitch, whiteSpace: 'nowrap', color: '#00e5ff', fontFamily: TH.font, fontWeight: 700, fontSize: 96 * S }}>{shot.b}</span>
        </>}
        <span style={{ position: 'relative', whiteSpace: 'nowrap', color: '#2b6cff', fontFamily: TH.font, fontWeight: 700, fontSize: 96 * S,
          textDecoration: 'underline', textUnderlineOffset: 12 * S }}>{shot.b}</span>
      </div>
    </AbsoluteFill>
  );
};

/** Shot: two iMessage bubbles (received green + sent blue) popping in with tails. */
const ShotImessage: React.FC<ShotCtx> = ({ shot, t, S }) => {
  const b1 = easeOutBack(clamp01((t - 0.15) * 1.5));
  const b2 = easeOutBack(clamp01((t - 0.9) * 1.5));
  const fs = 60 * S;
  const bubble = (text: string, sent: boolean, k: number): React.ReactNode => (
    <div style={{ alignSelf: sent ? 'flex-start' : 'flex-end', transform: `scale(${k.toFixed(3)})`,
      transformOrigin: sent ? '0% 50%' : '100% 50%', opacity: clamp01(k * 2), position: 'relative',
      background: sent ? '#2b6cff' : '#28c93f', color: '#fff', fontFamily: TH.font, fontWeight: 600, fontSize: fs,
      padding: `${26 * S}px ${40 * S}px`, borderRadius: 46 * S, boxShadow: cardShadow(S),
      maxWidth: 800 * S }}>{text}</div>
  );
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 30 * S, width: 1200 * S }}>
        {bubble('🧈 ' + shot.a!, false, b1) /* green, right: 'Buttery Smooth' (matches reference) */}
        {bubble(shot.b!, true, b2) /* blue, left: 'Apple Style Animations' */}
      </div>
    </AbsoluteFill>
  );
};

/** Shot: the widget stage — a YouTube-style content card + a wrench row ("the mechanics") on a
 *  glass card, with a cursor that moves in and taps. Real UI objects, not abstract shapes. */
const ShotWidgets: React.FC<ShotCtx> = ({ shot, t, W, H, S, accent, press }) => {
  const app = easeOutBack(clamp01((t - 0.1) * 1.3));
  const cw = 900 * S, ch = 560 * S;
  const cardX = (W - cw) / 2, cardY = (H - ch) / 2;
  // cursor travels from lower-right to the card, then taps near the end (press)
  const travel = easeInOutCubic(clamp01((t - 0.5) / 1.4));
  const cx = mix(W * 0.72, cardX + cw * 0.62, travel);
  const cy = mix(H * 0.82, cardY + ch * 0.66, travel);
  return (
    <AbsoluteFill>
      <div style={{ position: 'absolute', left: cardX, top: cardY, width: cw, height: ch, borderRadius: 48 * S,
        background: 'rgba(255,255,255,0.86)', backdropFilter: 'blur(20px)', boxShadow: cardShadow(S),
        transform: `scale(${app.toFixed(3)})`, transformOrigin: '50% 60%', border: '1px solid rgba(255,255,255,0.9)' }}>
        {/* video content row */}
        <div style={{ position: 'absolute', top: 48 * S, left: 48 * S, right: 48 * S, height: 150 * S,
          display: 'flex', gap: 30 * S, alignItems: 'center' }}>
          <div style={{ width: 240 * S, height: 140 * S, borderRadius: 20 * S, background: '#0b0b0d', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', bottom: 0, left: 0, height: 8 * S, width: `${(30 + 55 * clamp01(t / 2)).toFixed(0)}%`, background: accent }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: TH.ink, fontFamily: TH.font, fontWeight: 700, fontSize: 40 * S }}>Real UI, real depth</div>
            <div style={{ color: '#8b8f98', fontFamily: TH.font, fontSize: 28 * S, marginTop: 6 * S }}>built by hand</div>
            <div style={{ color: '#8b8f98', fontFamily: TH.font, fontSize: 24 * S, marginTop: 4 * S }}>vector · light · motion
              <span style={{ marginLeft: 14 * S, background: '#e6e8ec', color: '#4a4f5a', padding: `${4 * S}px ${12 * S}px`, borderRadius: 8 * S, fontWeight: 700 }}>LIVE</span></div>
          </div>
        </div>
        {/* section label */}
        <div style={{ position: 'absolute', top: 260 * S, left: 0, right: 0, textAlign: 'center',
          color: '#9aa0ab', fontFamily: TH.font, fontWeight: 700, fontSize: 66 * S, letterSpacing: '-0.02em' }}>{shot.accentText}</div>
        {/* wrench row */}
        <div style={{ position: 'absolute', top: 380 * S, left: 0, right: 0, display: 'flex', justifyContent: 'center', gap: 60 * S }}>
          {[0, 1, 2].map((i) => {
            const w = easeOutBack(clamp01((t - 0.6 - i * 0.14) * 1.6));
            return (
              <svg key={i} width={90 * S} height={90 * S} viewBox="0 0 40 40" style={{ transform: `scale(${w.toFixed(3)}) rotate(${(45 + i * 0).toFixed(0)}deg)`, opacity: clamp01(w * 2) }}>
                <path d="M28 6a8 8 0 0 0-9.6 10.4L6 28.8 11.2 34l12.4-12.4A8 8 0 0 0 34 12l-4.2 4.2-3.6-.9-.9-3.6L29.5 7.5A8 8 0 0 0 28 6z" fill="#9096a2" stroke="#6b7280" strokeWidth="1" />
              </svg>
            );
          })}
        </div>
      </div>
      <Cursor x={cx} y={cy} press={press} s={S} />
    </AbsoluteFill>
  );
};

/** Shot: a pill button (label + a mini device), scaling in; presses at hand-off. */
const ShotPill: React.FC<ShotCtx> = ({ shot, t, S, accent, press }) => {
  const dark = shot.c === 'warm';
  const app = easeOutBack(clamp01((t - 0.05) * 1.4));
  const bg = dark ? '#0e0f12' : '#2b6cff';
  const fg = dark ? accent : '#fff';
  const ph = 170 * S;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ height: ph, borderRadius: ph / 2, background: bg, boxShadow: cardShadow(S),
        display: 'inline-flex', alignItems: 'center', paddingLeft: 30 * S, paddingRight: 56 * S, gap: 30 * S,
        whiteSpace: 'nowrap', transform: `scale(${(app * (1 - press * 0.08)).toFixed(3)})` }}>
        {/* a verified check — reads as "true / accurate", matching the claim */}
        <div style={{ width: 104 * S, height: 104 * S, borderRadius: '50%', background: 'rgba(255,255,255,0.18)',
          display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={56 * S} height={56 * S} viewBox="0 0 24 24" fill="none" stroke={fg} strokeWidth="3.2">
            <path d="M4 12.5l5 5 11-12" strokeLinecap="round" strokeLinejoin="round"
              strokeDasharray="34" strokeDashoffset={(34 * (1 - clamp01((t - 0.35) * 2.4))).toFixed(1)} />
          </svg>
        </div>
        <div style={{ color: fg, fontFamily: TH.font, fontWeight: 700, fontSize: 68 * S, letterSpacing: '-0.02em' }}>{shot.accentText}</div>
      </div>
    </AbsoluteFill>
  );
};

/** Shot: an NLE timeline card — a ruler + stacked colored clips + a sweeping playhead, with the
 *  script line captioned above it so this beat carries its words like every other. */
const ShotTimeline: React.FC<ShotCtx> = ({ shot, t, hold, S }) => {
  const app = easeOutBack(clamp01((t - 0.1) * 1.3));
  const titleApp = clamp01((t - 0.2) * 2.4);
  const cw = 980 * S, ch = 480 * S;
  const inner = { x: 40 * S, y: 74 * S, w: cw - 80 * S, h: ch - 156 * S };
  const clips = [
    { row: 0, x0: 0.18, x1: 0.55, col: '#22d3ee' },
    { row: 1, x0: 0.0, x1: 0.38, col: '#22c55e' }, { row: 1, x0: 0.4, x1: 0.78, col: '#f472b6' },
    { row: 2, x0: 0.22, x1: 0.5, col: '#f59e0b' }, { row: 2, x0: 0.52, x1: 0.86, col: '#f59e0b' },
    { row: 3, x0: 0.05, x1: 0.82, col: '#a855f7' },
  ];
  const rowH = inner.h / 4;
  const play = easeInOutCubic(clamp01((t - 0.5) / Math.max(0.8, hold - 1.0)));
  const px = inner.x + inner.w * mix(0.1, 0.92, play);
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 52 * S }}>
      <div style={{ opacity: titleApp, transform: `translateY(${((1 - titleApp) * 20 * S).toFixed(1)}px)`,
        color: TH.ink, fontFamily: TH.font, fontWeight: 800, fontSize: 62 * S, letterSpacing: '-0.02em', textAlign: 'center', maxWidth: cw }}>
        {shot.accentText}
      </div>
      <div style={{ width: cw, height: ch, borderRadius: 44 * S, background: '#fff', boxShadow: cardShadow(S),
        transform: `scale(${app.toFixed(3)})`, position: 'relative', padding: 30 * S }}>
        <div style={{ position: 'absolute', inset: 30 * S, borderRadius: 30 * S, background: '#0a0a0c', overflow: 'hidden' }}>
          {/* ruler */}
          <div style={{ position: 'absolute', top: 22 * S, left: inner.x, right: inner.x, display: 'flex', justifyContent: 'space-between',
            color: '#6b7280', fontFamily: TH.font, fontWeight: 600, fontSize: 26 * S }}>
            {['00:00f', '01:00f', '02:00f', '03:00f', '04:00f'].map((s) => <span key={s}>{s}</span>)}
          </div>
          {/* clips */}
          {clips.map((c, i) => {
            const grow = easeOutQuint(clamp01((t - 0.3 - i * 0.08) * 2));
            const x = inner.x + inner.w * c.x0;
            const w = inner.w * (c.x1 - c.x0) * grow;
            const y = inner.y + c.row * rowH + 8 * S;
            return <div key={i} style={{ position: 'absolute', left: x, top: y, width: w, height: rowH - 16 * S,
              borderRadius: 14 * S, background: c.col, opacity: clamp01(grow * 2) }} />;
          })}
          {/* playhead */}
          <div style={{ position: 'absolute', top: 60 * S, bottom: 16 * S, left: px, width: 3 * S, background: '#3b82f6' }}>
            <div style={{ position: 'absolute', top: -22 * S, left: -13 * S, width: 28 * S, height: 22 * S, borderRadius: 5 * S, background: '#3b82f6' }} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Shot: the brand sign-off — our mark, never the source video's watermark. */
const ShotSignoff: React.FC<ShotCtx> = ({ shot, t, S, accent }) => {
  const app = easeOutBack(clamp01((t - 0.1) * 1.3));
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 40 * S }}>
      <div style={{ width: 150 * S, height: 150 * S, borderRadius: 40 * S, transform: `scale(${app.toFixed(3)})`,
        background: `linear-gradient(150deg, ${accent}, #ff8a5c)`, boxShadow: cardShadow(S),
        display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontFamily: TH.font, fontWeight: 800, fontSize: 90 * S }}>D</div>
      <Kinetic text={shot.accentText!} t={t - 0.2} fs={72 * S} color={TH.ink} />
    </AbsoluteFill>
  );
};

const SHOT_RENDER: Record<ShotKind, React.FC<ShotCtx>> = {
  ktypo: ShotKtypo, timer: ShotTimer, notes: ShotNotes, searchbar: ShotSearchbar,
  imessage: ShotImessage, widgets: ShotWidgets, pill: ShotPill, timeline: ShotTimeline, signoff: ShotSignoff,
};

// ───────────────────────────────────────────────────────────────────────────── composition

const ShowcaseBody: React.FC<{ spec: SceneSpec; story: readonly Shot[]; styleId: string | undefined }> = ({ spec, story, styleId }) => {
  const { fps, width: W, height: H } = useVideoConfig();
  const frame = useCurrentFrame();
  const t = frame / fps;
  const S = H / 1080; // everything is authored against a 1080-tall canvas
  const th = themeFor(styleId);
  TH = th;                                   // publish the active theme to all shot components
  const accent = th.accent;

  // lay shots on an overlapping timeline: each starts TRANS before the previous ends.
  const tf = TH.trans;
  const starts: number[] = [];
  let cur = 0;
  for (const s of story) { starts.push(cur); cur += s.dur - tf; }
  const n = story.length;

  // Pure layer transform for shot i at absolute time `at` — enter/exit hand-off composed with a
  // never-freeze idle drift. Sampling this at t and t-1frame gives the true motion vector, which
  // is what drives the continuous motion blur (no hand-tuned blur constants anywhere).
  const layerCam = (i: number, at: number): Cam => {
    const shot = story[i]!;
    const local = at - starts[i]!;
    const tin = clamp01(local / tf);
    const tout = clamp01((local - (shot.dur - tf)) / tf);
    const en = tin >= 1 ? IDENT : enterCam(shot.into, tin, W, H);
    const ex = tout <= 0 ? IDENT
      : (i < n - 1 ? exitCam(story[i + 1]!.into, tout, W, H)
        : { ...IDENT, alpha: 1 - easeInOutQuint(tout), scale: 1 + 0.06 * easeInOutQuint(tout) });
    let cam = composeCam(en, ex);
    // interactive camera: a motivated move that runs through the whole shot (neutral at p=0 so it
    // never fights the entrance). Sampled continuously → it smears via the measured-velocity blur.
    const sc = shotCam(shot.kind, shot.c === 'warm', clamp01(local / shot.dur), W, H, shot.v ?? 0.5);
    const cm = th.cameraMult;                // 0 for the locked-off "mono" style → no camera move
    cam = { x: cam.x + sc.x * cm, y: cam.y + sc.y * cm, scale: cam.scale * (1 + (sc.scale - 1) * cm), alpha: cam.alpha };
    // idle drift only while fully settled (fades in as the entrance completes, out as exit starts)
    const settle = clamp01(tin * 2 - 1) * clamp01((1 - tout) * 2 - 0) * (tout <= 0 ? 1 : 0);
    if (settle > 0) {
      const d = idleDrift(local, hash01(i, 3) * 6.28);
      cam = { x: cam.x + d.x * settle, y: cam.y + d.y * settle, scale: cam.scale * (1 + (d.scale - 1) * settle), alpha: cam.alpha };
    }
    return cam;
  };

  const dt = 1 / fps;

  return (
    <AbsoluteFill style={{ background: TH.bg }}>
      {story.map((shot, i) => {
        const start = starts[i]!;
        const local = t - start;
        if (local < -0.02 || local > shot.dur + 0.02) return null;

        const cam = layerCam(i, t);
        const prev = layerCam(i, t - dt);
        // per-frame motion vector → symmetric shutter smear; scale-rate → a whisper of iso blur.
        const dx = (cam.x - prev.x) * TH.shutter;
        const dy = (cam.y - prev.y) * TH.shutter;
        const iso = Math.abs(cam.scale - prev.scale) * Math.min(W, H) * TH.shutter * 0.5;

        // interaction press: ramps up in the last ~0.3s before this shot hands off.
        const press = i < n - 1 ? clamp01((local - (shot.dur - tf - 0.3)) / 0.22) : 0;
        const ctx: ShotCtx = { shot, t: local, hold: shot.dur, W, H, S, accent, press };
        const Render = SHOT_RENDER[shot.kind];

        return (
          <div key={i} style={layerCss(cam)}>
            {/* per-shot ground: dark shots carry their own backdrop over the light stage */}
            {shot.dark && <AbsoluteFill style={{ background: TH.bgDark }} />}
            <MotionSmear dx={dx} dy={dy} iso={iso}>
              <Render {...ctx} />
            </MotionSmear>
          </div>
        );
      })}
      {/* theme-driven vignette (bold is heavy, soft/mono none) */}
      {th.vignette > 0.001 && (
        <AbsoluteFill style={{ background: `radial-gradient(120% 90% at 50% 42%, transparent 55%, rgba(0,0,0,${th.vignette}) 100%)`, pointerEvents: 'none' }} />
      )}
    </AbsoluteFill>
  );
};

export const MotionShowcase: React.FC<MotionShowcaseProps> = ({ spec, story, styleId }) =>
  <ShowcaseBody spec={spec} story={story && story.length ? story : STORY} styleId={styleId} />;

/** Total storyboard length in seconds (drives calculateMetadata for this composition).
 *  Transition length is theme-dependent (hard-cut styles are shorter). */
export const showcaseDuration = (story: readonly Shot[] = STORY, styleId?: string): number =>
  story.reduce((a, s) => a + s.dur, 0) - themeFor(styleId).trans * Math.max(0, story.length - 1);

/** The built-in demo storyboard (used when props supply none). */
export const DEMO_STORY = STORY;
