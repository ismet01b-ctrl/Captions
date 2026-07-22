// SceneRenderer — turns the overlap manager's active scenes into positioned, animated
// blocks. Each scene gets ONE compositing layer (affine transform + opacity from the
// overlap envelope), so an outgoing scene physically slides/fades as a whole while the
// incoming one flies in — continuous flow, zero manual timeline.

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Block, SceneSpec } from './spec';
import { FULL_BLEED } from './spec';
import { activeScenes, affineToCss } from './lib/overlap';
import { laneRect } from './lib/layout';
import { KineticHeadlineBlock } from './blocks/KineticHeadline';
import { StatCardBlock } from './blocks/StatCard';
import { AccentUnderlineBlock } from './blocks/AccentUnderline';
import { DeviceFrameBlock } from './blocks/DeviceFrame';
import { ChipRowBlock } from './blocks/ChipRow';
import { BigQuoteBlock } from './blocks/BigQuote';
import { GradientMeshBlock } from './blocks/GradientMesh';
import { GlowOrbBlock } from './blocks/GlowOrb';
import { OrbitRingsBlock } from './blocks/OrbitRings';
import { ShapeFieldBlock } from './blocks/ShapeField';
import { WaveLinesBlock } from './blocks/WaveLines';

interface Props {
  readonly spec: SceneSpec;
}

/** Full-bleed graphic blocks — fill the scene, positioned by the block itself. */
function renderGraphic(
  block: Block,
  t: number,
  tIn: number,
  spec: SceneSpec,
  w: number,
  h: number,
): React.ReactNode {
  const { palette, beat, seed } = spec;
  switch (block.kind) {
    case 'gradientMesh':
      return <GradientMeshBlock block={block} t={t} tIn={tIn} palette={palette} />;
    case 'glowOrb':
      return <GlowOrbBlock block={block} t={t} tIn={tIn} w={w} h={h} palette={palette} beat={beat} />;
    case 'orbitRings':
      return <OrbitRingsBlock block={block} t={t} tIn={tIn} w={w} h={h} palette={palette} seed={seed} />;
    case 'shapeField':
      return <ShapeFieldBlock block={block} t={t} tIn={tIn} w={w} h={h} palette={palette} seed={seed} />;
    case 'waveLines':
      return <WaveLinesBlock block={block} t={t} tIn={tIn} w={w} h={h} palette={palette} beat={beat} />;
    default:
      return null;
  }
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
          style={{
            transform: affineToCss(a.xf),
            opacity: a.xf.alpha,
            filter: a.xf.blur > 0.15 ? `blur(${a.xf.blur.toFixed(2)}px)` : undefined,
            willChange: 'transform, opacity, filter',
          }}
        >
          {a.scene.blocks.map((block) => {
            // Full-bleed graphics fill the canvas; `slot` is their back-to-front z-order.
            if (FULL_BLEED.has(block.kind)) {
              return (
                <div
                  key={block.id}
                  style={{ position: 'absolute', inset: 0, zIndex: block.slot }}
                >
                  {renderGraphic(block, t, a.scene.tStart, spec, width, height)}
                </div>
              );
            }
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
                  zIndex: 10 + block.slot, // text sits above graphics
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
