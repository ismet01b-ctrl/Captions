// KineticHeadline — variable-weight kinetic typography. Each word is driven by the
// closed-form spring in lib/spring.ts, fired at its (optionally beat-snapped) Whisper
// onset. The wght axis briefly spikes on the "pop", then settles — the same emphasis
// typography the Python caption engine does, but live-previewable.

import React, { useMemo } from 'react';
import type { BeatGrid, KineticHeadline } from '../spec';
import { buildTriggers, wordPose } from '../lib/spring';
import { FONT_FAMILY } from '../fonts';

interface Props {
  readonly block: KineticHeadline;
  readonly t: number; // absolute seconds
  readonly beat: BeatGrid;
  readonly fg: string;
  readonly laneH: number; // px, for normalised lift
}

export const KineticHeadlineBlock: React.FC<Props> = ({ block, t, beat, fg, laneH }) => {
  const triggers = useMemo(() => buildTriggers(block, beat), [block, beat]);
  const size = Math.round(laneH * 0.42);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        gap: `${size * 0.06}px ${size * 0.28}px`,
        width: '100%',
        height: '100%',
        padding: `0 6%`,
        boxSizing: 'border-box',
        fontFamily: `'${FONT_FAMILY}', system-ui, sans-serif`,
        lineHeight: 0.98,
      }}
    >
      {triggers.map((tr, i) => {
        const pose =
          wordPose(tr, t, block.weight) ??
          { text: tr.text, scale: 0.86, alpha: 0, lift: 0.06, wght: block.weight[0] };
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              color: fg,
              fontSize: size,
              fontWeight: pose.wght,
              fontVariationSettings: `'wght' ${pose.wght}`,
              letterSpacing: '-0.02em',
              opacity: pose.alpha,
              transform: `translate3d(0, ${(pose.lift * laneH).toFixed(2)}px, 0) scale(${pose.scale.toFixed(4)})`,
              transformOrigin: '50% 60%',
              willChange: 'transform, opacity',
            }}
          >
            {pose.text}
          </span>
        );
      })}
    </div>
  );
};
