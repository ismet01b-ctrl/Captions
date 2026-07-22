// Root.tsx — composition registry. calculateMetadata derives canvas/fps/duration straight
// from the incoming SceneSpec, so one composition renders any spec the AI director emits.

import React from 'react';
import { Composition, type CalculateMetadataFunction } from 'remotion';
import { MotionVideo, type MotionProps } from './MotionVideo';
import { Motion3D } from './Motion3D';
import { MotionApple } from './MotionApple';
import { MotionSequence } from './MotionSequence';
import { MotionShowcase, showcaseDuration } from './MotionShowcase';
import { MotionOverlay, type MotionOverlayProps } from './MotionOverlay';
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

// Showcase: a fixed hand-designed storyboard. Canvas comes from the spec (16:9), duration
// from the storyboard itself — not spec.duration.
const showcaseMetadata: CalculateMetadataFunction<React.ComponentProps<typeof MotionShowcase>> = ({ props }) => {
  const { spec, story } = props;
  return {
    width: spec.canvas.w,
    height: spec.canvas.h,
    fps: spec.fps,
    durationInFrames: Math.max(1, Math.round(showcaseDuration(story) * spec.fps)),
  };
};

// Auto-overlay derives canvas + duration straight from the source video.
const overlayMetadata: CalculateMetadataFunction<MotionOverlayProps> = ({ props }) => {
  const { plan } = props;
  return {
    width: plan.video.w,
    height: plan.video.h,
    fps: plan.video.fps,
    durationInFrames: Math.max(1, Math.round(plan.video.duration * plan.video.fps)),
  };
};

const overlayDemo: MotionOverlayProps = {
  plan: { version: 1, seed: 1, accent: '#e0483d', video: { src: 'demo.mp4', w: 1080, h: 1920, fps: 30, duration: 6 }, beats: [] },
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
      {/* v111: MotionShowcase - 1:1-Nachbau des Referenz-Montage-Looks (Kinetik-Typo + UI-Cards
          + Widget-Stage + Timeline) mit kamerageführten, motion-geblurrten Übergängen, 16:9. */}
      <Composition
        id="MotionShowcase"
        component={MotionShowcase}
        defaultProps={demoProps}
        calculateMetadata={showcaseMetadata}
        durationInFrames={900}
        fps={30}
        width={1920}
        height={1080}
      />
      {/* v108: Auto-Overlay - hochgeladenes Video + KI-gesteuerte Motion-Beats obendrauf. */}
      <Composition
        id="MotionOverlay"
        component={MotionOverlay}
        defaultProps={overlayDemo}
        calculateMetadata={overlayMetadata}
        durationInFrames={180}
        fps={30}
        width={1080}
        height={1920}
      />
    </>
  );
};
