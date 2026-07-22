// GlowOrb — a hero luminous sphere: a bright core, an outer bloom halo, and a slow
// rotating specular sweep, breathing gently and spiking on the beat. Screen-blended so it
// reads as emitted light over the mesh, not a pasted circle.

import React from 'react';
import { AbsoluteFill } from 'remotion';
import type { GlowOrb, Palette, BeatGrid } from '../spec';
import { springStep, beatPulse } from '../lib/spring';

interface Props {
  readonly block: GlowOrb;
  readonly t: number;
  readonly tIn: number;
  readonly w: number;
  readonly h: number;
  readonly palette: Palette;
  readonly beat: BeatGrid;
}

export const GlowOrbBlock: React.FC<Props> = ({ block, t, tIn, w, h, palette, beat }) => {
  const s = springStep(t - tIn, block.spring);
  const e = t - tIn;
  const R = Math.min(w, h) * block.radiusPct;
  const breathe = 1 + 0.025 * Math.sin(e * 1.4);
  const pulse = block.beatPulse ? 1 + 0.07 * beatPulse(t, beat) : 1;
  const scale = (0.55 + 0.45 * s) * breathe * pulse;
  const sweep = e * 42; // deg/s
  const hue = block.hueDrift * (e / 6);
  const acc = palette.accent;

  return (
    <AbsoluteFill
      style={{
        alignItems: 'center',
        justifyContent: 'center',
        mixBlendMode: 'screen',
        opacity: Math.min(1, s * 1.5),
        filter: hue ? `hue-rotate(${hue.toFixed(1)}deg)` : undefined,
      }}
    >
      <div
        style={{
          position: 'relative',
          width: R * 2,
          height: R * 2,
          transform: `scale(${scale.toFixed(4)})`,
          willChange: 'transform',
        }}
      >
        {/* Outer bloom */}
        <div
          style={{
            position: 'absolute',
            inset: -R * 0.9,
            borderRadius: '50%',
            background: `radial-gradient(circle, ${acc}55 0%, ${acc}18 34%, transparent 68%)`,
          }}
        />
        {/* Core */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background: `radial-gradient(circle at 42% 38%, #ffffff 0%, ${acc} 30%, ${acc}00 72%)`,
          }}
        />
        {/* Rotating specular sweep */}
        <div
          style={{
            position: 'absolute',
            inset: R * 0.06,
            borderRadius: '50%',
            background: `conic-gradient(from ${sweep.toFixed(1)}deg, transparent 0deg, #ffffffcc 26deg, transparent 70deg, transparent 360deg)`,
            mixBlendMode: 'screen',
            opacity: 0.5,
            maskImage: 'radial-gradient(circle, #000 58%, transparent 72%)',
            WebkitMaskImage: 'radial-gradient(circle, #000 58%, transparent 72%)',
          }}
        />
        {/* Rim light */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            boxShadow: `inset 0 0 ${R * 0.5}px ${acc}, 0 0 ${R * 0.7}px ${acc}66`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
