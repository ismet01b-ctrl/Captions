// MotionOverlay — the AUTO-OVERLAY composition (v108): the creator's uploaded video plays
// full-frame (OffthreadVideo, original audio kept) and the AI-directed beats animate ON TOP
// at their content-matched timestamps. This is real MOTION DESIGN, not captions: kinetic
// word-by-word type, a drawing-in accent underline, a glow bloom, a burst of accent shards,
// a filling stat bar/ring, staggered glass chips — layered with depth and a clean defocus-out.
// Aspect-aware safe zones (portrait / landscape / square). Pure in t (seekable).

import React from 'react';
import { AbsoluteFill, Img, OffthreadVideo, Sequence, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { OverlayPlan, OverlayBeat, OverlayAnchor, OverlayEnter } from './spec';
import { entrancePose, blurCss } from './lib/motion';
import { hash01 } from './lib/rng';
import { FONT_FAMILY, ensureFont } from './fonts';

const FONT = `'${FONT_FAMILY}', system-ui, -apple-system, sans-serif`;
const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);
const easeOut = (x: number): number => 1 - Math.pow(1 - clamp01(x), 3);

const loaded = new Set<string>();
function ensureUserFont(font?: { family: string; url: string }): void {
  if (!font || typeof document === 'undefined' || loaded.has(font.url)) return;
  loaded.add(font.url);
  const h = delayRender('overlay font');
  try { new FontFace(font.family, `url(${font.url})`, { display: 'block' }).load().then((f) => { document.fonts.add(f); continueRender(h); }).catch(() => continueRender(h)); } catch { continueRender(h); }
}

const glass = (u: number, radius: number, alpha = 0.66): React.CSSProperties => ({
  background: `linear-gradient(180deg, rgba(40,43,55,${alpha + 0.06}) 0%, rgba(18,20,28,${alpha - 0.1}) 100%)`,
  backdropFilter: 'blur(16px) saturate(165%)', WebkitBackdropFilter: 'blur(16px) saturate(165%)',
  border: '1px solid rgba(255,255,255,0.16)', borderRadius: radius,
  boxShadow: `0 ${u * 0.02}px ${u * 0.055}px rgba(0,0,0,0.55), inset 0 1px 1px rgba(255,255,255,0.18)`,
});

// A soft radial glow bloom behind an element (a poor-man's light, but it reads premium).
const Glow: React.FC<{ u: number; color: string; scale?: number; op?: number }> = ({ u, color, scale = 1, op = 0.5 }) => (
  <div style={{ position: 'absolute', left: '50%', top: '50%', width: u * 0.9 * scale, height: u * 0.5 * scale,
    transform: 'translate(-50%,-50%)', borderRadius: '50%', filter: `blur(${u * 0.05}px)`,
    background: `radial-gradient(closest-side, ${color}, transparent)`, opacity: op, pointerEvents: 'none' }} />
);

// A burst of small accent shards that pop out and drift — the "impact" of a punchy beat.
const Shards: React.FC<{ u: number; color: string; t: number; seed: number; n?: number }> = ({ u, color, t, seed, n = 9 }) => (
  <>
    {Array.from({ length: n }, (_, i) => {
      const a = hash01(i, seed) * Math.PI * 2;
      const p = clamp01((t - 0.02) / 0.5);
      const rad = u * (0.12 + hash01(i, seed + 5) * 0.16) * easeOut(p);
      const s = u * (0.008 + hash01(i, seed + 9) * 0.012) * (1 - p * 0.4);
      const rot = (t * 60 + i * 40) * (i % 2 ? 1 : -1);
      const op = clamp01(p * 2) * (1 - p) * 1.4;
      return (
        <div key={i} style={{ position: 'absolute', left: '50%', top: '50%',
          width: s, height: s, borderRadius: i % 3 === 0 ? '50%' : 2,
          transform: `translate(-50%,-50%) translate(${Math.cos(a) * rad}px, ${Math.sin(a) * rad}px) rotate(${rot}deg)`,
          background: i % 2 ? color : '#fff', opacity: op, pointerEvents: 'none',
          boxShadow: `0 0 ${u * 0.02}px ${color}` }} />
      );
    })}
  </>
);

// Kinetic type: word-by-word reveal (stagger + spring + blur-in), the hallmark of motion type.
const Kinetic: React.FC<{ text: string; t: number; u: number; size: number; weight?: number; color?: string; stagger?: number; shadow?: string }>
  = ({ text, t, u, size, weight = 900, color = '#fff', stagger = 0.07, shadow }) => (
    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `${size * 0.06}px ${size * 0.28}px`, lineHeight: 1.02 }}>
      {text.split(/\s+/).filter(Boolean).map((w, i) => {
        const p = entrancePose(t - i * stagger, { stiffness: 170, damping: 0.62, delay: 0 }, u * 0.05);
        return (
          <span key={i} style={{ display: 'inline-block', opacity: p.alpha, color, fontWeight: weight, fontSize: size,
            transform: `translate3d(0, ${p.ty.toFixed(1)}px, 0) scale(${p.scale.toFixed(3)})`, filter: blurCss(p.blur),
            textShadow: shadow ?? '0 4px 22px rgba(0,0,0,0.6)', letterSpacing: '-0.01em', willChange: 'transform, opacity, filter' }}>{w}</span>
        );
      })}
    </div>
  );

const enterOffset = (enter: OverlayEnter, k: number, W: number, u: number): { x: number; y: number; s0: number } => {
  switch (enter) {
    case 'pop': return { x: 0, y: 0, s0: 0.62 };
    case 'slide': return { x: (k % 2 ? 1 : -1) * W * 0.14, y: 0, s0: 0.92 };
    case 'wipe': return { x: 0, y: u * 0.04, s0: 0.97 };
    default: return { x: 0, y: u * 0.07, s0: 0.9 }; // rise
  }
};

const OverlayItem: React.FC<{ beat: OverlayBeat; idx: number; plan: OverlayPlan; W: number; H: number }> = ({ beat, idx, plan, W, H }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const u = Math.min(W, H);
  const accent = plan.accent;
  const seed = plan.seed + idx * 131;
  const landscape = W > H * 1.2;

  // aspect-aware safe zones: landscape keeps the lower band higher and hugs a tighter column.
  const ANCHOR_Y: Record<OverlayAnchor, number> = landscape
    ? { top: 0.16, upper: 0.28, center: 0.46, lower: 0.8, bottom: 0.9 }
    : { top: 0.14, upper: 0.3, center: 0.46, lower: 0.74, bottom: 0.86 };
  const yPct = ANCHOR_Y[beat.anchor] - (plan.platform && beat.anchor === 'lower' ? 0.06 : 0);

  const off = enterOffset(beat.enter, idx, W, u);
  const pose = entrancePose(t, { stiffness: 150, damping: 0.62, delay: 0 }, off.y);
  const scale = off.s0 + (1 - off.s0) * clamp01(pose.scale);
  const outP = clamp01((t - (beat.dur - 0.42)) / 0.42);
  const alpha = pose.alpha * (1 - outP);
  const blur = pose.blur + outP * 7;
  const tx = off.x * (1 - clamp01(pose.scale));
  const em = beat.emphasis;

  const wrap: React.CSSProperties = {
    position: 'absolute', left: 0, top: `${yPct * 100}%`, width: W, display: 'flex', justifyContent: 'center',
    transform: `translate3d(${tx.toFixed(1)}px, ${pose.ty.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`,
    opacity: alpha, filter: blurCss(blur), fontFamily: plan.font ? `'${plan.font.family}', ${FONT}` : FONT,
    willChange: 'transform, opacity, filter',
  };
  const draw = easeOut((t - 0.18) / 0.45); // underline / bar draw-in progress

  if (beat.kind === 'headline') {
    const size = u * (0.078 + 0.024 * em) * (landscape ? 0.85 : 1);
    return (
      <div style={wrap}>
        <div style={{ position: 'relative', maxWidth: landscape ? '70%' : '88%', textAlign: 'center', padding: `0 ${u * 0.02}px` }}>
          <Glow u={u} color={`${accent}66`} scale={1.3} op={0.45} />
          {em > 0.8 && <Shards u={u} color={accent} t={t} seed={seed} />}
          <Kinetic text={beat.text ?? ''} t={t} u={u} size={size} />
          <div style={{ height: u * 0.012, width: `${18 + 60 * draw}%`, margin: `${u * 0.024}px auto 0`,
            borderRadius: 999, background: `linear-gradient(90deg, ${accent}, #fff)`,
            boxShadow: `0 0 ${u * 0.035}px ${accent}` }} />
        </div>
      </div>
    );
  }
  if (beat.kind === 'keyword') {
    const size = u * (0.078 + 0.026 * em) * (landscape ? 0.85 : 1);
    const slide = easeOut((t - 0.12) / 0.35);
    return (
      <div style={wrap}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Glow u={u} color={`${accent}88`} scale={1.1} op={0.55} />
          <Shards u={u} color={accent} t={t} seed={seed} n={11} />
          <div style={{ position: 'relative', padding: `${u * 0.022}px ${u * 0.052}px`, ...glass(u, 999, 0.6), borderColor: `${accent}99`, overflow: 'hidden' }}>
            {/* accent highlight swiping in behind the word */}
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, ${accent}00, ${accent}55)`,
              transform: `translateX(${(1 - slide) * -100}%)`, opacity: 0.9 }} />
            <span style={{ position: 'relative', color: '#fff', fontSize: size, fontWeight: 900, whiteSpace: 'nowrap',
              textShadow: `0 0 ${u * 0.03}px ${accent}` }}>{beat.text}</span>
          </div>
        </div>
      </div>
    );
  }
  if (beat.kind === 'lowerthird') {
    const barH = u * 0.09;
    return (
      <div style={wrap}>
        <div style={{ display: 'flex', alignItems: 'stretch', gap: u * 0.022, maxWidth: landscape ? '58%' : '90%',
          padding: `${u * 0.02}px ${u * 0.032}px`, ...glass(u, u * 0.028) }}>
          <div style={{ width: u * 0.01, borderRadius: 999, background: `linear-gradient(180deg, ${accent}, ${accent}55)`,
            transform: `scaleY(${clamp01(draw)})`, transformOrigin: 'top', boxShadow: `0 0 ${u * 0.02}px ${accent}` }} />
          <div style={{ minWidth: 0, alignSelf: 'center' }}>
            <div style={{ fontSize: u * 0.042, fontWeight: 800 }}>
              <Kinetic text={beat.text ?? ''} t={t} u={u} size={u * 0.042} weight={800} stagger={0.05} />
            </div>
            {beat.text2 && <div style={{ fontSize: u * 0.028, color: '#c6cbd6', marginTop: u * 0.006, opacity: clamp01((t - 0.35) / 0.4), textAlign: 'center' }}>{beat.text2}</div>}
          </div>
        </div>
      </div>
    );
  }
  if (beat.kind === 'chips') {
    return (
      <div style={{ ...wrap }}>
        <div style={{ display: 'flex', gap: u * 0.02, flexWrap: 'wrap', justifyContent: 'center', maxWidth: landscape ? '70%' : '92%' }}>
          {(beat.items ?? []).map((it, i) => {
            const cp = entrancePose(t - i * 0.1, { stiffness: 175, damping: 0.55, delay: 0 }, u * 0.045);
            return (
              <div key={i} style={{ opacity: cp.alpha, transform: `translateY(${cp.ty.toFixed(1)}px) scale(${cp.scale.toFixed(3)})`, filter: blurCss(cp.blur),
                display: 'flex', alignItems: 'center', gap: u * 0.014, padding: `${u * 0.016}px ${u * 0.03}px`, ...glass(u, 999, 0.6), borderColor: `${accent}66` }}>
                <div style={{ width: u * 0.012, height: u * 0.012, borderRadius: '50%', background: accent, boxShadow: `0 0 ${u * 0.015}px ${accent}` }} />
                <span style={{ color: '#fff', fontSize: u * 0.036, fontWeight: 800, whiteSpace: 'nowrap' }}>{it}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  if (beat.kind === 'stat') {
    const p = easeOut((t - 0.1) / 0.95);
    const shown = Math.round((beat.value ?? 0) * p);
    const size = u * (0.12 + 0.03 * em) * (landscape ? 0.8 : 1);
    return (
      <div style={wrap}>
        <div style={{ position: 'relative', textAlign: 'center', padding: `${u * 0.03}px ${u * 0.055}px`, ...glass(u, u * 0.04) }}>
          <Glow u={u} color={`${accent}66`} scale={1.1} op={0.4} />
          <div style={{ position: 'relative', fontSize: size, fontWeight: 900, color: '#fff', letterSpacing: '-0.02em', lineHeight: 1,
            textShadow: `0 0 ${u * 0.03}px ${accent}55` }}>
            {beat.prefix ?? ''}{shown.toLocaleString()}{beat.suffix ?? ''}
          </div>
          {/* progress bar that fills as the number counts up */}
          <div style={{ height: u * 0.008, width: '82%', margin: `${u * 0.016}px auto 0`, borderRadius: 999, background: 'rgba(255,255,255,0.14)', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${p * 100}%`, background: `linear-gradient(90deg, ${accent}, #fff)`, boxShadow: `0 0 ${u * 0.02}px ${accent}` }} />
          </div>
          {beat.label && <div style={{ fontSize: u * 0.026, color: accent, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: u * 0.01 }}>{beat.label}</div>}
        </div>
      </div>
    );
  }
  // brand
  return (
    <div style={wrap}>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u * 0.02 }}>
        <Glow u={u} color={`${accent}66`} scale={1.4} op={0.45} />
        <Shards u={u} color={accent} t={t} seed={seed} n={12} />
        {plan.logo && (() => { const lp = entrancePose(t, { stiffness: 150, damping: 0.6, delay: 0 }, u * 0.05); return (
          <Img src={plan.logo} style={{ width: u * 0.17, height: u * 0.17, borderRadius: u * 0.045, objectFit: 'cover',
            opacity: lp.alpha, transform: `scale(${lp.scale.toFixed(3)})`, boxShadow: `0 ${u * 0.02}px ${u * 0.05}px rgba(0,0,0,0.55), 0 0 ${u * 0.04}px ${accent}66` }} />
        ); })()}
        <Kinetic text={beat.text ?? 'DouchkoVE'} t={t} u={u} size={u * 0.062} />
        <div style={{ height: u * 0.008, width: `${20 + 45 * draw}%`, borderRadius: 999, background: `linear-gradient(90deg, ${accent}, #fff)`, boxShadow: `0 0 ${u * 0.03}px ${accent}` }} />
        {beat.text2 && <div style={{ fontSize: u * 0.03, color: '#c6cbd6', fontWeight: 700, opacity: clamp01((t - 0.4) / 0.4) }}>{beat.text2}</div>}
      </div>
    </div>
  );
};

export type MotionOverlayProps = { readonly plan: OverlayPlan };

export const MotionOverlay: React.FC<MotionOverlayProps> = ({ plan }) => {
  const { fps } = useVideoConfig();
  ensureFont();
  ensureUserFont(plan.font);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <OffthreadVideo src={staticFile(plan.video.src)} />
      {plan.beats.map((beat, i) => (
        <Sequence key={i} from={Math.round(beat.t * fps)} durationInFrames={Math.max(1, Math.round(beat.dur * fps))} layout="none">
          <OverlayItem beat={beat} idx={i} plan={plan} W={plan.video.w} H={plan.video.h} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
