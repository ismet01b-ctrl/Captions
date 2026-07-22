// MotionOverlay — the AUTO-OVERLAY composition (v108): the creator's uploaded video plays
// full-frame (OffthreadVideo, original audio kept) and the AI-directed beats animate ON TOP
// at their content-matched timestamps, each in a safe zone with a senior-grade entrance and a
// clean defocus-out. Pure in t (seekable). One shared visual language: dark glass, the brand
// accent, spring motion — never a cheap sticker.

import React from 'react';
import { AbsoluteFill, Img, OffthreadVideo, Sequence, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { OverlayPlan, OverlayBeat, OverlayAnchor, OverlayEnter } from './spec';
import { entrancePose, blurCss } from './lib/motion';
import { FONT_FAMILY, ensureFont } from './fonts';

const FONT = `'${FONT_FAMILY}', system-ui, -apple-system, sans-serif`;
const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

const loaded = new Set<string>();
function ensureUserFont(font?: { family: string; url: string }): void {
  if (!font || typeof document === 'undefined' || loaded.has(font.url)) return;
  loaded.add(font.url);
  const h = delayRender('overlay font');
  try { new FontFace(font.family, `url(${font.url})`, { display: 'block' }).load().then((f) => { document.fonts.add(f); continueRender(h); }).catch(() => continueRender(h)); } catch { continueRender(h); }
}

// safe-zone vertical anchors (fraction of height); platform masks nudge the lower band up.
const ANCHOR_Y: Record<OverlayAnchor, number> = { top: 0.14, upper: 0.3, center: 0.46, lower: 0.74, bottom: 0.86 };

const glass = (accent: string, u: number, radius: number): React.CSSProperties => ({
  background: 'linear-gradient(180deg, rgba(38,41,52,0.72) 0%, rgba(20,22,30,0.6) 100%)',
  backdropFilter: 'blur(14px) saturate(160%)', WebkitBackdropFilter: 'blur(14px) saturate(160%)',
  border: '1px solid rgba(255,255,255,0.14)', borderRadius: radius,
  boxShadow: `0 ${u * 0.02}px ${u * 0.05}px rgba(0,0,0,0.5), inset 0 1px 1px rgba(255,255,255,0.16)`,
});

/** Entrance offset per style; combined with the spring pose. */
const enterOffset = (enter: OverlayEnter, k: number, W: number, u: number): { x: number; y: number; s0: number } => {
  switch (enter) {
    case 'pop': return { x: 0, y: 0, s0: 0.6 };
    case 'slide': return { x: (k % 2 ? 1 : -1) * W * 0.12, y: 0, s0: 0.9 };
    case 'wipe': return { x: 0, y: u * 0.04, s0: 0.96 };
    default: return { x: 0, y: u * 0.06, s0: 0.88 }; // rise
  }
};

const OverlayItem: React.FC<{ beat: OverlayBeat; idx: number; plan: OverlayPlan; W: number; H: number }> = ({ beat, idx, plan, W, H }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;                 // local time within the beat Sequence
  const u = Math.min(W, H);
  const accent = plan.accent;
  const off = enterOffset(beat.enter, idx, W, u);
  const pose = entrancePose(t, { stiffness: 150, damping: 0.6, delay: 0 }, off.y || u * 0.05);
  const scale = off.s0 + (1 - off.s0) * clamp01(pose.scale); // ease scale from s0 → 1
  // clean defocus-out over the last 0.42s
  const durF = beat.dur;
  const outP = clamp01((t - (durF - 0.42)) / 0.42);
  const alpha = pose.alpha * (1 - outP);
  const blur = pose.blur + outP * 6;
  const tx = off.x * (1 - clamp01(pose.scale));
  const em = beat.emphasis;

  const yPct = ANCHOR_Y[beat.anchor] - (plan.platform && beat.anchor === 'lower' ? 0.06 : 0);
  const wrap: React.CSSProperties = {
    position: 'absolute', left: 0, top: `${yPct * 100}%`, width: W, display: 'flex', justifyContent: 'center',
    transform: `translate3d(${tx.toFixed(1)}px, ${pose.ty.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`,
    opacity: alpha, filter: blurCss(blur), fontFamily: plan.font ? `'${plan.font.family}', ${FONT}` : FONT,
    willChange: 'transform, opacity, filter',
  };

  if (beat.kind === 'headline') {
    return (
      <div style={wrap}>
        <div style={{ maxWidth: '86%', textAlign: 'center' }}>
          <div style={{ fontSize: u * (0.072 + 0.02 * em), fontWeight: 900, color: '#fff', lineHeight: 1.05,
            textShadow: '0 4px 24px rgba(0,0,0,0.6)', letterSpacing: '-0.01em' }}>{beat.text}</div>
          <div style={{ height: u * 0.011, width: `${40 + 40 * clamp01((t - 0.15) / 0.4)}%`, margin: `${u * 0.02}px auto 0`,
            borderRadius: 999, background: accent, boxShadow: `0 0 ${u * 0.03}px ${accent}` }} />
        </div>
      </div>
    );
  }
  if (beat.kind === 'keyword') {
    return (
      <div style={wrap}>
        <div style={{ padding: `${u * 0.02}px ${u * 0.05}px`, ...glass(accent, u, 999), color: '#fff',
          fontSize: u * (0.07 + 0.02 * em), fontWeight: 900, whiteSpace: 'nowrap',
          boxShadow: `0 0 ${u * 0.05}px ${accent}66, 0 ${u * 0.02}px ${u * 0.05}px rgba(0,0,0,0.5)`, borderColor: `${accent}88` }}>{beat.text}</div>
      </div>
    );
  }
  if (beat.kind === 'lowerthird') {
    return (
      <div style={wrap}>
        <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.025, maxWidth: '88%', padding: `${u * 0.022}px ${u * 0.035}px`, ...glass(accent, u, u * 0.03) }}>
          <div style={{ width: u * 0.008, alignSelf: 'stretch', borderRadius: 999, background: accent, boxShadow: `0 0 ${u * 0.02}px ${accent}` }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: u * 0.042, fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{beat.text}</div>
            {beat.text2 && <div style={{ fontSize: u * 0.028, color: '#c2c7d2', marginTop: u * 0.004 }}>{beat.text2}</div>}
          </div>
        </div>
      </div>
    );
  }
  if (beat.kind === 'chips') {
    return (
      <div style={{ ...wrap, gap: u * 0.02 }}>
        <div style={{ display: 'flex', gap: u * 0.02, flexWrap: 'wrap', justifyContent: 'center', maxWidth: '90%' }}>
          {(beat.items ?? []).map((it, i) => {
            const cp = entrancePose(t - i * 0.09, { stiffness: 160, damping: 0.55, delay: 0 }, u * 0.04);
            return <div key={i} style={{ opacity: cp.alpha, transform: `translateY(${cp.ty.toFixed(1)}px) scale(${cp.scale.toFixed(3)})`,
              padding: `${u * 0.016}px ${u * 0.032}px`, ...glass(accent, u, 999), color: '#fff', fontSize: u * 0.036, fontWeight: 800, whiteSpace: 'nowrap' }}>{it}</div>;
          })}
        </div>
      </div>
    );
  }
  if (beat.kind === 'stat') {
    const p = clamp01((t - 0.1) / 0.9); const shown = Math.round((beat.value ?? 0) * (1 - Math.pow(1 - p, 3)));
    return (
      <div style={wrap}>
        <div style={{ textAlign: 'center', padding: `${u * 0.03}px ${u * 0.05}px`, ...glass(accent, u, u * 0.04) }}>
          <div style={{ fontSize: u * (0.1 + 0.02 * em), fontWeight: 900, color: '#fff', letterSpacing: '-0.02em' }}>
            {beat.prefix ?? ''}{shown.toLocaleString()}{beat.suffix ?? ''}
          </div>
          {beat.label && <div style={{ fontSize: u * 0.026, color: accent, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: u * 0.006 }}>{beat.label}</div>}
        </div>
      </div>
    );
  }
  // brand
  return (
    <div style={wrap}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u * 0.02 }}>
        {plan.logo && <Img src={plan.logo} style={{ width: u * 0.16, height: u * 0.16, borderRadius: u * 0.04, objectFit: 'cover', boxShadow: `0 ${u * 0.02}px ${u * 0.05}px rgba(0,0,0,0.5)` }} />}
        <div style={{ fontSize: u * 0.06, fontWeight: 900, color: '#fff', textShadow: '0 4px 20px rgba(0,0,0,0.6)' }}>{beat.text}</div>
        {beat.text2 && <div style={{ fontSize: u * 0.03, color: accent, fontWeight: 700 }}>{beat.text2}</div>}
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
