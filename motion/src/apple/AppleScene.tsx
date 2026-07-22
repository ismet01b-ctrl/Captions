// AppleScene — the Apple / iOS "mockup" motion look (light gradient, soft embossed UI),
// the style the reference clips use. Starts with the premium PILLS: white 3D-embossed
// keyboard-suggestion pills that spring in on a light field, with little vector sparkles
// drifting around them. Reads items + accent from the SceneSpec so it rides the same
// render pipeline as everything else. Pure in t (Remotion-seekable).

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec } from '../spec';
import { entrancePose, idleFloat, blurCss } from '../lib/motion';
import { springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';
import { FONT_FAMILY } from '../fonts';

/** Pull the pill items out of the spec (templateSpec stores them on a chipRow block). */
function pillItems(spec: SceneSpec): string[] {
  for (const sc of spec.scenes) {
    for (const b of sc.blocks) {
      if (b.kind === 'chipRow') return [...b.items];
      if (b.kind === 'kineticHeadline') return b.words.map((w) => w.text);
    }
  }
  return ['Write', 'Create', 'Solve'];
}

const Sparkle: React.FC<{ x: number; y: number; s: number; c: string; rot: number; o: number }>
  = ({ x, y, s, c, rot, o }) => (
    <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`} opacity={o}>
      {/* 4-point sparkle */}
      <path d="M0,-10 C1.5,-3 3,-1.5 10,0 C3,1.5 1.5,3 0,10 C-1.5,3 -3,1.5 -10,0 C-3,-1.5 -1.5,-3 0,-10 Z"
        fill={c} />
    </g>
  );

export const AppleScene: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const { palette, seed } = spec;
  const acc = palette.accent;
  const items = pillItems(spec).slice(0, 5);
  const unit = Math.min(width, height);
  const pillFs = Math.round(unit * 0.062);

  // A few drifting sparkles at seeded positions (some accent, some warm gold).
  const sparkles = Array.from({ length: 6 }, (_, i) => {
    const sx = (0.14 + hash01(i, seed) * 0.72) * width;
    const sy = (0.16 + hash01(i, seed + 9) * 0.6) * height;
    const size = unit * (0.012 + hash01(i, seed + 3) * 0.02);
    const pop = springStep(t - (0.2 + hash01(i, seed + 5) * 0.8), { stiffness: 140, damping: 0.5, delay: 0 });
    const fx = idleFloat(t, i * 1.7, unit * 0.02);
    const fy = idleFloat(t, i * 2.3 + 1, unit * 0.02);
    const col = i % 2 === 0 ? acc : '#ffb020';
    return { key: i, x: sx + fx, y: sy + fy, s: size * Math.max(0, pop) / 10, c: col,
      rot: t * 40 * (i % 2 ? 1 : -1), o: Math.min(1, pop) * 0.85 };
  });

  return (
    <AbsoluteFill style={{ fontFamily: `'${FONT_FAMILY}', system-ui, sans-serif` }}>
      {/* Light Apple field: soft blue-white gradient. */}
      <AbsoluteFill style={{
        background:
          'radial-gradient(120% 90% at 50% 18%, #ffffff 0%, #eef2f9 46%, #dbe4f3 100%)',
      }} />
      {/* Sparkles behind the pills. */}
      <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`}
        style={{ position: 'absolute', inset: 0 }}>
        {sparkles.map((s) => (
          <Sparkle key={s.key} x={s.x} y={s.y} s={s.s} c={s.c} rot={s.rot} o={s.o} />
        ))}
      </svg>
      {/* Pill stack, centred. */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: unit * 0.03,
          alignItems: 'center', justifyContent: 'center', width: '82%' }}>
          {items.map((it, i) => {
            const stagger = ((i * 3) % Math.max(items.length, 1)) * 0.11;
            const pose = entrancePose(t - 0.1, { stiffness: 150, damping: 0.55, delay: stagger }, unit * 0.05);
            const float = idleFloat(t, i * 1.9, unit * 0.006) * pose.alpha;
            return (
              <div key={i} style={{
                opacity: pose.alpha,
                transform: `translate3d(0, ${(pose.ty + float).toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`,
                filter: blurCss(pose.blur),
                padding: `${pillFs * 0.42}px ${pillFs * 0.9}px`,
                borderRadius: pillFs * 1.1,
                background: 'linear-gradient(180deg, #ffffff 0%, #f3f5fa 100%)',
                color: '#0f1420',
                fontSize: pillFs,
                fontWeight: 800,
                letterSpacing: '-0.01em',
                // embossed: soft drop shadow + crisp inner top highlight + hairline.
                boxShadow: `0 ${pillFs * 0.5}px ${pillFs * 1.1}px rgba(30,50,90,0.18),`
                  + `0 ${pillFs * 0.12}px ${pillFs * 0.3}px rgba(30,50,90,0.12),`
                  + `inset 0 2px 1px rgba(255,255,255,0.9),`
                  + `inset 0 -2px 2px rgba(20,40,80,0.06)`,
                border: '1px solid rgba(255,255,255,0.8)',
                whiteSpace: 'nowrap',
                willChange: 'transform, opacity, filter',
              }}>
                {it}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
