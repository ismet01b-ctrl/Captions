// Root.tsx — composition registry. calculateMetadata derives canvas/fps/duration straight
// from the incoming SceneSpec, so one composition renders any spec the AI director emits.

import React from 'react';
import { Composition, type CalculateMetadataFunction } from 'remotion';
import { MotionVideo, type MotionProps } from './MotionVideo';
import { Motion3D } from './Motion3D';
import { MotionApple } from './MotionApple';
import { MotionSequence } from './MotionSequence';
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
    <>
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
      {/* v101w: echtes 3D (Three.js) - gleicher Spec-Vertrag, gerendert mit --gl=angle. */}
      <Composition
        id="Motion3D"
        component={Motion3D}
        defaultProps={demoProps}
        calculateMetadata={calculateMetadata}
        durationInFrames={252}
        fps={30}
        width={1080}
        height={1920}
      />
      {/* v102: Apple/iOS-Mockup-Look (light theme) - Referenz-Stil (embossed pills …). */}
      <Composition
        id="MotionApple"
        component={MotionApple}
        defaultProps={demoProps}
        calculateMetadata={calculateMetadata}
        durationInFrames={252}
        fps={30}
        width={1080}
        height={1920}
      />
      {/* v103: mehrere Mockups zu EINEM Video verkettet (seamless Transitions). */}
      <Composition
        id="MotionSequence"
        component={MotionSequence}
        defaultProps={demoProps}
        calculateMetadata={calculateMetadata}
        durationInFrames={252}
        fps={30}
        width={1080}
        height={1920}
      />
    </>
  );
};
