// MotionApple — composition host for the Apple / iOS mockup templates (light theme).
// Same SceneSpec contract for canvas/fps/duration; AppleScene reads the payload.

import React from 'react';
import { AbsoluteFill } from 'remotion';
import type { SceneSpec } from './spec';
import { AppleScene } from './apple/AppleScene';

export type MotionAppleProps = {
  readonly spec: SceneSpec;
};

export const MotionApple: React.FC<MotionAppleProps> = ({ spec }) => (
  <AbsoluteFill>
    <AppleScene spec={spec} />
  </AbsoluteFill>
);
