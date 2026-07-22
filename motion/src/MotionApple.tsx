// MotionApple — composition host for the Apple / iOS mockup templates (light theme).
// Same SceneSpec contract for canvas/fps/duration; AppleScene reads the payload.

import React from 'react';
import { AbsoluteFill } from 'remotion';
import type { SceneSpec } from './spec';
import { AppleScene } from './apple/AppleScene';
import { DeviceStage } from './apple/DeviceStage';

export type MotionAppleProps = {
  readonly spec: SceneSpec;
};

export const MotionApple: React.FC<MotionAppleProps> = ({ spec }) => (
  <AbsoluteFill>
    <DeviceStage W={spec.canvas.w} H={spec.canvas.h} accent={spec.ui?.accent ?? spec.palette.accent}
      render={(vw, vh) => <AppleScene spec={spec} vw={vw} vh={vh} />} />
  </AbsoluteFill>
);
