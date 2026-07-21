// DeviceFrame — a media insert in a rounded "device" with a studio drop-shadow and a
// gentle depth-parallax drift, so an image reads as a 3D object in the scene, not a paste.

import React from 'react';
import { Img, staticFile } from 'remotion';
import type { DeviceFrame } from '../spec';
import { springStep } from '../lib/spring';

interface Props {
  readonly block: DeviceFrame;
  readonly t: number;
  readonly tIn: number;
  readonly laneH: number;
}

export const DeviceFrameBlock: React.FC<Props> = ({ block, t, tIn, laneH }) => {
  const s = springStep(t - tIn, block.spring);
  const drift = Math.sin((t - tIn) * 0.9) * block.depth * laneH * 0.04;
  const radius = Math.round(laneH * 0.06);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        opacity: Math.min(1, s * 1.6),
        transform: `translate3d(0, ${drift.toFixed(2)}px, 0) scale(${(0.9 + 0.1 * s).toFixed(4)})`,
      }}
    >
      <div
        style={{
          position: 'relative',
          height: '84%',
          aspectRatio: '9 / 16',
          borderRadius: radius,
          overflow: 'hidden',
          background: '#0c0d10',
          boxShadow: `0 ${laneH * 0.08}px ${laneH * 0.18}px rgba(0,0,0,0.55)`,
          outline: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <Img
          src={staticFile(block.src)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      </div>
    </div>
  );
};
