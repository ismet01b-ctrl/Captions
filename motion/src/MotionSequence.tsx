// MotionSequence — chains several UI-mockup segments into ONE continuous video with
// seamless blur-zoom cross-transitions (the outgoing segment scales up + defocuses + fades
// while the incoming one resolves out of a blur into place, overlapping so there is never a
// flat cut). Each segment runs on its own local time via Remotion <Sequence>, so its
// internal animations play from zero. Pure in t (seekable).

import React from 'react';
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec, SeqSegment } from './spec';
import { AppleScene } from './apple/AppleScene';
import { easeOutQuint, easeInOutCubic, clamp01 } from './lib/easing';

const TRANSITION = 0.55; // s — must match SEQ_TRANSITION in templates.ts

export type MotionSequenceProps = { readonly spec: SceneSpec };

export const MotionSequence: React.FC<MotionSequenceProps> = ({ spec }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const segs: readonly SeqSegment[] = spec.sequence ?? [];
  const tf = Math.round(TRANSITION * fps);

  // Each segment starts where the previous ends MINUS the transition overlap.
  const starts: number[] = [];
  let cursor = 0;
  for (const s of segs) {
    starts.push(cursor);
    cursor += Math.round(s.dur * fps) - tf;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#ffffff' }}>
      {segs.map((seg, i) => {
        const startF = starts[i]!;
        const durF = Math.round(seg.dur * fps);
        const local = frame - startF; // frames into this segment (global-derived)

        // enter over [0, tf]; exit over [durF - tf, durF]. First seg still gets an intro,
        // last seg still fades at the very end.
        const tin = clamp01(local / tf);
        const tout = clamp01((local - (durF - tf)) / tf);
        const eIn = easeOutQuint(tin);
        const eOut = easeInOutCubic(tout);

        const scale = 1 + 0.1 * (1 - eIn) + 0.1 * eOut; // big -> settle -> grow out
        const blur = 16 * (1 - eIn) + 16 * eOut;
        const opacity = clamp01(eIn * 1.3) * (1 - eOut);

        const segSpec: SceneSpec = { ...spec, ui: seg.ui, seed: spec.seed + i * 97, sequence: undefined as never };

        return (
          <Sequence key={i} from={startF} durationInFrames={durF} layout="none">
            <AbsoluteFill style={{
              opacity,
              transform: `scale(${scale.toFixed(4)})`,
              filter: blur > 0.2 ? `blur(${blur.toFixed(2)}px)` : undefined,
              willChange: 'transform, opacity, filter',
            }}>
              <AppleScene spec={segSpec} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
