// SceneRenderer — turns the overlap manager's active scenes into positioned, animated
// blocks. Each scene gets ONE compositing layer (affine transform + opacity from the
// overlap envelope), so an outgoing scene physically slides/fades as a whole while the
// incoming one flies in — continuous flow, zero manual timeline.

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Block, SceneSpec } from './spec';
import { activeScenes, affineToCss } from './lib/overlap';
import { laneRect } from './lib/layout';
import { KineticHeadlineBlock } from './blocks/KineticHeadline';
import { StatCardBlock } from './blocks/StatCard';
import { AccentUnderlineBlock } from './blocks/AccentUnderline';
import { DeviceFrameBlock } from './blocks/DeviceFrame';
import { ChipRowBlock } from './blocks/ChipRow';
import { BigQuoteBlock } from './blocks/BigQuote';

interface Props {
  readonly spec: SceneSpec;
}

function renderBlock(
  block: Block,
  t: number,
  tIn: number,
  spec: SceneSpec,
  laneH: number,
): React.ReactNode {
  const { palette, beat } = spec;
  switch (block.kind) {
    case 'kineticHeadline':
      return (
        <KineticHeadlineBlock block={block} t={t} beat={beat} fg={palette.fg} laneH={laneH} />
      );
    case 'statCard':
      return (
        <StatCardBlock
          block={block}
          t={t}
          tIn={tIn}
          fg={palette.fg}
          accent={palette.accent}
          muted={palette.muted}
          laneH={laneH}
        />
      );
    case 'accentUnderline':
      return (
        <AccentUnderlineBlock block={block} t={t} tIn={tIn} accent={palette.accent} laneH={laneH} />
      );
    case 'deviceFrame':
      return <DeviceFrameBlock block={block} t={t} tIn={tIn} laneH={laneH} />;
    case 'chipRow':
      return (
        <ChipRowBlock
          block={block}
          t={t}
          tIn={tIn}
          fg={palette.fg}
          accent={palette.accent}
          bg={palette.bg}
          laneH={laneH}
        />
      );
    case 'bigQuote':
      return (
        <BigQuoteBlock
          block={block}
          t={t}
          tIn={tIn}
          fg={palette.fg}
          accent={palette.accent}
          muted={palette.muted}
          laneH={laneH}
        />
      );
    default:
      return null;
  }
}

export const SceneRenderer: React.FC<Props> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const live = activeScenes(spec, t);

  return (
    <>
      {live.map((a) => (
        <AbsoluteFill
          key={a.scene.id}
          style={{ transform: affineToCss(a.xf), opacity: a.xf.alpha, willChange: 'transform, opacity' }}
        >
          {a.scene.blocks.map((block) => {
            const r = laneRect(block.slot, spec.canvas.format, width, height);
            return (
              <div
                key={block.id}
                style={{
                  position: 'absolute',
                  left: `${r.leftPct}%`,
                  width: `${r.widthPct}%`,
                  top: r.top,
                  height: r.height,
                }}
              >
                {renderBlock(block, t, a.scene.tStart, spec, r.height)}
              </div>
            );
          })}
        </AbsoluteFill>
      ))}
    </>
  );
};
