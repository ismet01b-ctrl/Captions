// MotionKinetic — a STRUCTURALLY different composition from MotionShowcase (not a recolour of it).
// No UI cards, no device mockups: this is pure editorial kinetic typography. Each spoken phrase
// becomes its own full-frame type composition with a seeded LAYOUT (centred / left-stacked / one
// giant word / top-bottom split) and a seeded REVEAL (mask-wipe up, scale-punch, alternating
// word slide, line wipe). Transitions are typographic — hard cut or a whip-blur — never the
// camera-glide montage of the card style. Same transcript in, a completely different film out.
//
// Shares the hard rules: text is data (verbatim from the transcript), pure in `t` (seekable).

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec } from './spec';
import type { Shot } from './MotionShowcase';
import { clamp01, easeOutQuint, easeInOutQuint, easeOutBack, mix } from './lib/easing';
import { springStep } from './lib/spring';
import { hash01, mulberry32 } from './lib/rng';
import { themeFor, type Theme } from './showcaseThemes';

export type MotionKineticProps = { readonly spec: SceneSpec; readonly story?: readonly Shot[]; readonly styleId?: string };

const HOLD = 2.2;   // seconds a phrase holds
const CUT = 0.28;   // typographic hand-off window (short — these are cuts/whips, not glides)

// Pull the verbatim line out of a storyboard shot (works for any archetype's payload).
const lineOf = (s: Shot): string =>
  (s.accentText || [s.a, s.b].filter(Boolean).join(' ') || '').trim();

// Split a line into words + mark the strongest word (longest non-trivial) for emphasis.
const STOPish = new Set(['the', 'and', 'for', 'you', 'your', 'that', 'with', 'from', 'a', 'to', 'of', 'in', 'is', 'it']);
function emphasisIndex(words: string[]): number {
  let best = -1, score = 0;
  words.forEach((w, i) => {
    const c = w.replace(/[^\p{L}\p{N}]/gu, '');
    if (c.length > score && !STOPish.has(c.toLowerCase())) { score = c.length; best = i; }
  });
  return best;
}

interface Ctx { text: string; t: number; hold: number; W: number; H: number; S: number; th: Theme; seed: number; }

// ── one word, revealed by the scene's chosen animation ──────────────────────────────────────
type Reveal = 'maskUp' | 'punch' | 'slide' | 'wipe';
const Word: React.FC<{
  w: string; i: number; n: number; t: number; fs: number; color: string; th: Theme; reveal: Reveal; emph: boolean;
}> = ({ w, i, n, t, fs, color, th, reveal, emph }) => {
  const delay = 0.06 + i * 0.075 + hash01(i, 5) * 0.05;
  const e = t - delay;
  const s = springStep(e, { stiffness: 200, damping: reveal === 'punch' ? 0.5 : 0.8, delay: 0 });
  const app = clamp01(e * 4);
  const style: React.CSSProperties = {
    display: 'inline-block', color, fontFamily: th.font, fontWeight: emph ? 900 : th.weight,
    fontSize: emph ? fs * 1.14 : fs, lineHeight: 1.0, letterSpacing: th.tracking,
    textTransform: th.upper ? 'uppercase' : 'none', whiteSpace: 'pre',
  };
  let wrap: React.CSSProperties = { display: 'inline-block', marginRight: fs * 0.24 };
  if (reveal === 'maskUp') {
    wrap = { display: 'inline-block', overflow: 'hidden', verticalAlign: 'bottom', marginRight: fs * 0.24 };
    style.transform = `translateY(${((1 - easeOutQuint(clamp01(e / 0.5))) * fs * 1.1).toFixed(1)}px)`;
  } else if (reveal === 'punch') {
    style.transform = `scale(${(0.6 + 0.4 * s).toFixed(3)})`; style.opacity = app;
  } else if (reveal === 'slide') {
    const dir = i % 2 ? 1 : -1;
    style.transform = `translateX(${((1 - easeOutQuint(clamp01(e / 0.45))) * dir * fs * 1.4).toFixed(1)}px)`; style.opacity = app;
  } else { // wipe: clip-path reveal left→right
    const p = easeInOutQuint(clamp01(e / 0.5));
    style.clipPath = `inset(0 ${((1 - p) * 100).toFixed(1)}% 0 0)`; style.opacity = app > 0 ? 1 : 0;
  }
  return <span style={wrap}><span style={style}>{w}</span></span>;
};

// ── one phrase as a full-frame type scene, layout + reveal chosen by seed ────────────────────
const TypeScene: React.FC<Ctx> = ({ text, t, hold, W, H, S, th, seed }) => {
  const rng = mulberry32(seed);
  const layout = Math.floor(rng() * 4);      // 0 centred · 1 left-stack · 2 giant word · 3 split
  const reveals: Reveal[] = ['maskUp', 'punch', 'slide', 'wipe'];
  const reveal = reveals[Math.floor(rng() * reveals.length)]!;
  const words = text.split(/\s+/).filter(Boolean);
  const emph = emphasisIndex(words);
  const ink = th.ground === 'dark' ? th.ink : th.ink;

  // a moving accent bar/underline gives graphic energy without any card
  const barP = easeOutQuint(clamp01((t - 0.15) / 0.6));
  const bar = (
    <div style={{ height: 10 * S, background: th.accent, borderRadius: 6 * S,
      width: `${(barP * (layout === 1 ? 40 : 26)).toFixed(1)}%`, transformOrigin: 'left' }} />
  );

  const renderWords = (fs: number): React.ReactNode =>
    words.map((w, i) => (
      <Word key={i} w={w} i={i} n={words.length} t={t} fs={fs} color={i === emph ? th.accent : ink} th={th} reveal={reveal} emph={i === emph} />
    ));

  if (layout === 2 && words.length >= 2) {
    // GIANT WORD: the emphasis word huge, the rest small above it
    const big = words[emph] ?? words[0]!;
    const rest = words.filter((_, i) => i !== emph).join(' ');
    const bigFs = Math.min(340 * S, (W * 0.9) / Math.max(3, big.length) * 1.7);
    return (
      <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20 * S }}>
        <div style={{ color: ink, opacity: clamp01((t - 0.1) * 3), fontFamily: th.font, fontWeight: th.weight,
          fontSize: 46 * S, letterSpacing: th.tracking, textTransform: th.upper ? 'uppercase' : 'none' }}>{rest}</div>
        <div><Word w={big} i={0} n={1} t={t} fs={bigFs} color={th.accent} th={th} reveal={reveal} emph /></div>
        {bar}
      </AbsoluteFill>
    );
  }
  if (layout === 1) {
    // LEFT STACK: big, left-aligned, one word per line
    const fs = Math.min(150 * S, 900 * S / Math.max(1, words.length));
    return (
      <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'flex-start', justifyContent: 'center', paddingLeft: W * 0.12, gap: 8 * S }}>
        {bar}
        {words.map((w, i) => (
          <div key={i}><Word w={w} i={i} n={words.length} t={t} fs={fs} color={i === emph ? th.accent : ink} th={th} reveal={reveal} emph={i === emph} /></div>
        ))}
      </AbsoluteFill>
    );
  }
  if (layout === 3 && words.length >= 3) {
    // SPLIT: first half top, accent bar, second half bottom
    const mid = Math.ceil(words.length / 2);
    const fs = 118 * S;
    const half = (ws: string[], off: number): React.ReactNode => ws.map((w, i) => (
      <Word key={i} w={w} i={i + off} n={words.length} t={t} fs={fs} color={(i + off) === emph ? th.accent : ink} th={th} reveal={reveal} emph={(i + off) === emph} />
    ));
    return (
      <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 26 * S }}>
        <div style={{ maxWidth: '82%', textAlign: 'center' }}>{half(words.slice(0, mid), 0)}</div>
        <div style={{ width: '46%' }}>{bar}</div>
        <div style={{ maxWidth: '82%', textAlign: 'center' }}>{half(words.slice(mid), mid)}</div>
      </AbsoluteFill>
    );
  }
  // CENTRED (default)
  const fs = Math.min(150 * S, (W * 1.4) / Math.max(6, text.length));
  return (
    <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 24 * S }}>
      <div style={{ maxWidth: '82%', textAlign: 'center', lineHeight: 1.05 }}>{renderWords(fs)}</div>
      {bar}
    </AbsoluteFill>
  );
};

const KineticBody: React.FC<{ spec: SceneSpec; story: readonly Shot[]; styleId: string | undefined }> = ({ spec, story, styleId }) => {
  const { fps, width: W, height: H } = useVideoConfig();
  const t = useCurrentFrame() / fps;
  const S = H / 1080;
  const th = themeFor(styleId);
  const phrases = story.map(lineOf).filter(Boolean);

  const starts: number[] = [];
  let cur = 0;
  for (let i = 0; i < phrases.length; i++) { starts.push(cur); cur += HOLD - CUT; }

  return (
    <AbsoluteFill style={{ background: th.ground === 'dark' ? th.bgDark : th.bg }}>
      {phrases.map((text, i) => {
        const start = starts[i]!;
        const local = t - start;
        if (local < -0.02 || local > HOLD + 0.02) return null;
        // typographic transition: whip-blur + slight scale on the cut edges, or hard cut (mono).
        const tin = clamp01(local / CUT);
        const tout = clamp01((local - (HOLD - CUT)) / CUT);
        const hard = th.shutter < 0.05;
        const whip = hard ? 0 : (1 - tin) * 60 + tout * 60;    // px of directional blur at edges
        const alpha = hard ? (local >= 0 && local <= HOLD - CUT * 0.2 ? 1 : clamp01(Math.min(tin * 3, (1 - tout) * 3)))
          : clamp01(Math.min(tin * 2, (1 - tout) * 2));
        const scale = mix(0.98, 1, easeOutBack(tin)) * mix(1, 1.03, tout);
        return (
          <AbsoluteFill key={i} style={{ opacity: alpha, transform: `scale(${scale.toFixed(4)})`,
            filter: whip > 1 ? `blur(${(whip * 0.05).toFixed(2)}px)` : undefined }}>
            <TypeScene text={text} t={local} hold={HOLD} W={W} H={H} S={S} th={th} seed={(i + 1) * 2654435761 >>> 0} />
          </AbsoluteFill>
        );
      })}
      {th.vignette > 0.001 && (
        <AbsoluteFill style={{ background: `radial-gradient(120% 90% at 50% 45%, transparent 55%, rgba(0,0,0,${th.vignette}) 100%)`, pointerEvents: 'none' }} />
      )}
    </AbsoluteFill>
  );
};

export const MotionKinetic: React.FC<MotionKineticProps> = ({ spec, story, styleId }) =>
  <KineticBody spec={spec} story={story && story.length ? story : []} styleId={styleId} />;

export const kineticDuration = (story: readonly Shot[]): number => {
  const n = story.map(lineOf).filter(Boolean).length;
  return Math.max(1, n * (HOLD - CUT) + CUT);
};
