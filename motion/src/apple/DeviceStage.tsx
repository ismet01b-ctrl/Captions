// DeviceStage — lets the portrait iOS mockups (AppleScene / MotionSequence) render into any
// output format. For a portrait canvas it is a passthrough. For 16:9 / 1:1 it centres the
// phone as a real DEVICE (rounded bezel + drop shadow) on a liquid-glass backdrop and hands
// the inner content the phone's portrait dimensions — so the mockup is never stretched.

import React from 'react';
import { AbsoluteFill } from 'remotion';

export const stageDims = (W: number, H: number): { sw: number; sh: number; framed: boolean } => {
  // Portrait-ish (9:16 and taller) → render full-bleed, no frame.
  if (H / W >= 1.5) return { sw: W, sh: H, framed: false };
  const sh = Math.round(H * 0.94);
  const sw = Math.round(sh * 9 / 16);
  return { sw, sh, framed: true };
};

export const DeviceStage: React.FC<{ W: number; H: number; accent: string; render: (vw: number, vh: number) => React.ReactNode }>
  = ({ W, H, accent, render }) => {
    const { sw, sh, framed } = stageDims(W, H);
    if (!framed) return <>{render(sw, sh)}</>;
    const bezel = Math.max(6, sw * 0.028);
    const u = Math.min(W, H);
    return (
      <AbsoluteFill style={{ background: 'radial-gradient(125% 100% at 50% 28%, #1b1e28 0%, #111219 55%, #0a0b10 100%)' }}>
        <div style={{ position: 'absolute', left: '6%', top: '14%', width: '52%', height: '64%', borderRadius: '50%', filter: `blur(${u * 0.09}px)`, background: `${accent}30` }} />
        <div style={{ position: 'absolute', right: '4%', bottom: '8%', width: '48%', height: '56%', borderRadius: '50%', filter: `blur(${u * 0.1}px)`, background: `${accent}22` }} />
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: sw, height: sh, borderRadius: sw * 0.095, overflow: 'hidden', position: 'relative',
            boxShadow: `0 ${u * 0.05}px ${u * 0.14}px rgba(0,0,0,0.6), 0 0 0 ${bezel}px #0a0b0f, 0 0 0 ${bezel + 1.5}px rgba(255,255,255,0.1)` }}>
            {render(sw, sh)}
          </div>
        </AbsoluteFill>
      </AbsoluteFill>
    );
  };
