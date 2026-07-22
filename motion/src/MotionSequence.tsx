// MotionSequence — chains several UI-mockup segments into ONE continuous video with a set of
// INTERACTIVE, camera-style transitions (see lib/transitions.ts): horizontal/vertical camera
// pans, a slide-over cover, a dolly push-through, and 3D swing/flip hand-offs. One scene is
// fully shown, then the next is physically pushed in while a virtual camera moves between
// them. BOTH scenes stay razor-sharp — nothing ever defocuses/blurs out. The engine
// auto-varies the transitions so no two adjacent boundaries repeat; a scene can pin its own.
// Each segment runs on its own local time via Remotion <Sequence>. Pure in t (seekable).
//
// A matching transition SFX rides on each boundary — but ONLY when its designed asset exists
// (spec.sfx, fs-probed by the director). No asset -> silent.

import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec, SeqSegment, TransId } from './spec';
import { AppleScene } from './apple/AppleScene';
import { DeviceStage } from './apple/DeviceStage';
import { clamp01, easeOutQuint, easeInOutCubic } from './lib/easing';
import {
  TRANSITIONS, IDENTITY, composeAffine, pickTransitions, type Affine,
} from './lib/transitions';

const TRANSITION = 0.55; // s — must match SEQ_TRANSITION in templates.ts

export type MotionSequenceProps = { readonly spec: SceneSpec };

// The first scene's entrance and the last scene's exit have no neighbour, so they get a clean
// scale+fade bookend (sharp — no blur), not a camera hand-off.
const introAff = (e: number): Affine => {
  const o = easeOutQuint(e);
  return { x: 0, y: 0, scale: 0.94 + 0.06 * o, rotateX: 0, rotateY: 0, alpha: clamp01(e * 1.6), persp: 0 };
};
const outroAff = (e: number): Affine => {
  const o = easeInOutCubic(e);
  return { x: 0, y: 0, scale: 1 + 0.04 * o, rotateX: 0, rotateY: 0, alpha: 1 - o, persp: 0 };
};

/** Build the CSS transform + opacity for one segment layer from its composed affine. */
const layerStyle = (a: Affine): React.CSSProperties => {
  const parts: string[] = [];
  if (a.persp > 0) parts.push(`perspective(${a.persp}px)`);
  parts.push(`translate3d(${a.x.toFixed(2)}px, ${a.y.toFixed(2)}px, 0)`);
  parts.push(`scale(${a.scale.toFixed(4)})`);
  if (Math.abs(a.rotateX) > 0.01) parts.push(`rotateX(${a.rotateX.toFixed(3)}deg)`);
  if (Math.abs(a.rotateY) > 0.01) parts.push(`rotateY(${a.rotateY.toFixed(3)}deg)`);
  return {
    opacity: clamp01(a.alpha),
    transform: parts.join(' '),
    transformOrigin: '50% 50%',
    willChange: 'transform, opacity',
    backfaceVisibility: 'hidden',
  };
};

const SeqBody: React.FC<{ spec: SceneSpec; W: number; H: number }> = ({ spec, W, H }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const segs: readonly SeqSegment[] = spec.sequence ?? [];
  const tf = Math.max(1, Math.round(TRANSITION * fps));
  const n = segs.length;

  // Each segment starts where the previous ends MINUS the transition overlap.
  const starts: number[] = [];
  let cursor = 0;
  for (const s of segs) {
    starts.push(cursor);
    cursor += Math.round(s.dur * fps) - tf;
  }

  // One transition per boundary (n-1 of them), auto-varied unless a scene pins its own.
  const overrides: (TransId | undefined)[] = segs.slice(1).map((s) => s.transition);
  const boundary = pickTransitions(Math.max(0, n - 1), spec.seed, overrides);
  const sfxSet = new Set(spec.sfx ?? []);

  return (
    <AbsoluteFill style={{ backgroundColor: '#ffffff' }}>
      {segs.map((seg, i) => {
        const startF = starts[i]!;
        const durF = Math.round(seg.dur * fps);
        const local = frame - startF;

        const tin = clamp01(local / tf);
        const tout = clamp01((local - (durF - tf)) / tf);

        // Entrance uses the boundary BEFORE this segment; exit uses the boundary AFTER it.
        // First segment => clean intro; last segment => clean outro (sharp scale+fade).
        const enterAff = tin >= 1 ? IDENTITY
          : i > 0 ? TRANSITIONS[boundary[i - 1]!].enter(tin, W, H)
            : introAff(tin);
        const exitAff = tout <= 0 ? IDENTITY
          : i < n - 1 ? TRANSITIONS[boundary[i]!].exit(tout, W, H)
            : outroAff(tout);
        const aff = composeAffine(enterAff, exitAff);

        // The transition is INTERACTIVE: just before a scene hands off, its own control is
        // "pressed" (search submitted, Open tapped, message sent…), and that press drives the
        // camera move. press ramps to 1 in the ~0.2s BEFORE the exit, then the motion follows.
        const pressLead = Math.round(0.22 * fps);
        const pressDur = Math.max(1, Math.round(0.14 * fps));
        const press = i < n - 1 ? clamp01((local - (durF - tf - pressLead)) / pressDur) : 0;

        const segSpec: SceneSpec = { ...spec, ui: seg.ui, seed: spec.seed + i * 97, sequence: undefined as never };

        return (
          <Sequence key={i} from={startF} durationInFrames={durF} layout="none">
            <AbsoluteFill style={layerStyle(aff)}>
              <AppleScene spec={segSpec} press={press} vw={W} vh={H} />
            </AbsoluteFill>
          </Sequence>
        );
      })}

      {/* Transition SFX — one hit per boundary, landing just as the camera move peaks. Mounted
          only when the asset for that transition exists; otherwise the sequence is silent. */}
      {boundary.map((tid, b) => {
        const key = TRANSITIONS[tid].sound;
        if (!sfxSet.has(key)) return null;
        const hitFrame = Math.max(0, starts[b + 1]! + Math.round(tf * 0.35));
        return (
          <Sequence key={`sfx-${b}`} from={hitFrame} durationInFrames={Math.round(0.8 * fps)} layout="none">
            <Audio src={staticFile(`sfx/${key}.wav`)} volume={0.7} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

// For 16:9 / 1:1 output the whole sequence plays inside a centred portrait device on a
// liquid-glass stage; for 9:16 it fills the frame. Transitions + mockups use the stage dims.
export const MotionSequence: React.FC<MotionSequenceProps> = ({ spec }) => (
  <DeviceStage W={spec.canvas.w} H={spec.canvas.h} accent={spec.palette.accent}
    render={(vw, vh) => <SeqBody spec={spec} W={vw} H={vh} />} />
);
