// BigQuote — an oversized pull-quote. The quote mark + line spring in together; the
// attribution fades in a beat later so the eye lands on the words first.

import React from 'react';
import type { BigQuote } from '../spec';
import { springStep } from '../lib/spring';
import { FONT_FAMILY } from '../fonts';

interface Props {
  readonly block: BigQuote;
  readonly t: number;
  readonly tIn: number;
  readonly fg: string;
  readonly accent: string;
  readonly muted: string;
  readonly laneH: number;
}

export const BigQuoteBlock: React.FC<Props> = ({ block, t, tIn, fg, accent, muted, laneH }) => {
  const s = springStep(t - tIn, block.spring);
  const fs = Math.round(laneH * 0.19);
  const authorReveal = Math.max(0, (s - 0.6) / 0.4);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        padding: '0 4%',
        boxSizing: 'border-box',
        opacity: Math.min(1, s * 1.6),
        transform: `translate3d(0, ${((1 - s) * laneH * 0.1).toFixed(1)}px, 0)`,
        fontFamily: `'${FONT_FAMILY}', system-ui, sans-serif`,
      }}
    >
      <div style={{ color: accent, fontSize: fs * 1.9, lineHeight: 0.5, fontWeight: 800, marginBottom: fs * 0.15 }}>
        &ldquo;
      </div>
      <div
        style={{
          color: fg,
          fontSize: fs,
          fontWeight: 600,
          fontVariationSettings: `'wght' 600`,
          letterSpacing: '-0.01em',
          lineHeight: 1.12,
        }}
      >
        {block.text}
      </div>
      {block.author ? (
        <div
          style={{
            color: muted,
            fontSize: fs * 0.42,
            fontWeight: 600,
            letterSpacing: '0.04em',
            marginTop: fs * 0.4,
            opacity: authorReveal,
          }}
        >
          &mdash; {block.author}
        </div>
      ) : null}
    </div>
  );
};
