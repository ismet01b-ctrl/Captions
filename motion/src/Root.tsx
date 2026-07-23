// Root.tsx — composition registry. Since v118 only the Studio Showcase engine remains:
// three structurally distinct compositions (card montage / kinetic type / prompt build),
// each deriving canvas + duration from the incoming SceneSpec / storyboard.

import React from 'react';
import { Composition, type CalculateMetadataFunction } from 'remotion';
import { MotionShowcase, showcaseDuration, DEMO_STORY } from './MotionShowcase';
import { MotionKinetic, kineticDuration } from './MotionKinetic';
import { MotionPrompt, promptDuration } from './MotionPrompt';
import { demoProps } from './demo-spec';

// Showcase: a fixed hand-designed storyboard. Canvas comes from the spec (16:9), duration
// from the storyboard itself — not spec.duration.
const showcaseMetadata: CalculateMetadataFunction<React.ComponentProps<typeof MotionShowcase>> = ({ props }) => {
  const { spec, story, styleId } = props;
  return {
    width: spec.canvas.w,
    height: spec.canvas.h,
    fps: spec.fps,
    durationInFrames: Math.max(1, Math.round(showcaseDuration(story, styleId) * spec.fps)),
  };
};

// Kinetic — a structurally different composition (pure typography). Same spec/story contract.
const kineticMetadata: CalculateMetadataFunction<React.ComponentProps<typeof MotionKinetic>> = ({ props }) => {
  const { spec, story } = props;
  return {
    width: spec.canvas.w,
    height: spec.canvas.h,
    fps: spec.fps,
    durationInFrames: Math.max(1, Math.round(kineticDuration(story && story.length ? story : DEMO_STORY) * spec.fps)),
  };
};

// Prompt — cinematic "prompt → code → website" build sequence.
const promptMetadata: CalculateMetadataFunction<React.ComponentProps<typeof MotionPrompt>> = ({ props }) => {
  const { spec } = props;
  return {
    width: spec.canvas.w,
    height: spec.canvas.h,
    fps: spec.fps,
    durationInFrames: Math.max(1, Math.round(promptDuration() * spec.fps)),
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* v111: MotionShowcase - kamerageführte UI-Card-Montage (Kinetik-Typo + Cards
          + Widget-Stage + Timeline) mit motion-geblurrten Übergängen, 16:9. */}
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
      {/* v114: MotionKinetic - strukturell ANDERE Komposition (reine Typografie, keine Cards). */}
      <Composition
        id="MotionKinetic"
        component={MotionKinetic}
        defaultProps={demoProps}
        calculateMetadata={kineticMetadata}
        durationInFrames={600}
        fps={30}
        width={1920}
        height={1080}
      />
      {/* v115: MotionPrompt - cinematischer Prompt→Code→Website-Build (glühend, 3D). */}
      <Composition
        id="MotionPrompt"
        component={MotionPrompt}
        defaultProps={demoProps}
        calculateMetadata={promptMetadata}
        durationInFrames={396}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
