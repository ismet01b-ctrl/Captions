// Root.tsx — composition registry. calculateMetadata derives canvas/fps/duration straight
// from the incoming SceneSpec, so one composition renders any spec the AI director emits.

import React from 'react';
import { Composition, type CalculateMetadataFunction } from 'remotion';
import { MotionVideo, type MotionProps } from './MotionVideo';
import { demoProps } from './demo-spec';

const calculateMetadata: CalculateMetadataFunction<MotionProps> = ({ props }) => {
  const { spec } = props;
  return {
    width: spec.canvas.w,
    height: spec.canvas.h,
    fps: spec.fps,
    durationInFrames: Math.max(1, Math.round(spec.duration * spec.fps)),
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MotionVideo"
      component={MotionVideo}
      defaultProps={demoProps}
      calculateMetadata={calculateMetadata}
      // Fallbacks; calculateMetadata overrides these from the spec at render time.
      durationInFrames={252}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
