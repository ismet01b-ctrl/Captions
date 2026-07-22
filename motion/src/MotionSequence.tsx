// MotionSequence — chains several UI-mockup segments into ONE continuous video with a set
// of DIFFERENT, elaborate cross-transitions (see lib/transitions.ts): clean pushes, whip
// pans with real directional motion blur, glass card slides with an elastic land, iris
// app-opens, subtle 3D swooshes. The engine auto-varies them so no two adjacent boundaries
// repeat; a scene can also pin its own. Each segment runs on its own local time via Remotion
// <Sequence>, so its internal animations play from zero. Pure in t (seekable).
//
// A matching transition SFX rides on each boundary — but ONLY when its CC0 asset actually
// exists (spec.sfx, fs-probed by the director). No asset -> silent, never a cheap synth beep.

import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec, SeqSegment, TransId } from './spec';
import { AppleScene } from './apple/AppleScene';
import { clamp01 } from './lib/easing';
import {
  TRANSITIONS, IDENTITY, composeAffine, pickTransitions, type Affine,
} from './lib/transitions';

const TRANSITION = 0.55; // s — must match SEQ_TRANSITION in templates.ts

export type MotionSequenceProps = { readonly spec: SceneSpec };

/** Build the CSS transform + filter for one segment layer from its composed affine. */
const layerStyle = (a: Affine, filterId: string | null): React.CSSProperties => {
  const parts: string[] = [];
  if (a.persp > 0) parts.push(`perspective(${a.persp}px)`);
  parts.push(`translate3d(${a.x.toFixed(2)}px, ${a.y.toFixed(2)}px, 0)`);
  parts.push(`scale(${a.scale.toFixed(4)})`);
  if (Math.abs(a.rotateY) > 0.01) parts.push(`rotateY(${a.rotateY.toFixed(3)}deg)`);
  const filters: string[] = [];
  if (a.blur > 0.2) filters.push(`blur(${a.blur.toFixed(2)}px)`);
  if (filterId) filters.push(`url(#${filterId})`); // directional motion blur (feGaussianBlur)
  return {
    opacity: clamp01(a.alpha),
    transform: parts.join(' '),
    transformOrigin: '50% 50%',
    filter: filters.length ? filters.join(' ') : undefined,
    willChange: 'transform, opacity, filter',
    backfaceVisibility: 'hidden',
  };
};

export const MotionSequence: React.FC<MotionSequenceProps> = ({ spec }) => {
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

        // Entrance uses the boundary BEFORE this segment; exit uses the boundary AFTER it.
        // The first segment gets a calm intro, the last a calm outro (blurzoom bookends).
        const enterDef = i > 0 ? TRANSITIONS[boundary[i - 1]!] : TRANSITIONS.blurzoom;
        const exitDef = i < n - 1 ? TRANSITIONS[boundary[i]!] : TRANSITIONS.blurzoom;

        const tin = clamp01(local / tf);
        const tout = clamp01((local - (durF - tf)) / tf);
        const enterAff = tin < 1 ? enterDef.enter(tin, spec.canvas.w, spec.canvas.h) : IDENTITY;
        const exitAff = tout > 0 ? exitDef.exit(tout, spec.canvas.w, spec.canvas.h) : IDENTITY;
        const aff = composeAffine(enterAff, exitAff);

        // Directional (horizontal) motion blur — an SVG filter whose stdDeviation tracks the
        // whip velocity. Only mounted when there's meaningful blurX, so clean cuts stay sharp.
        const useHBlur = aff.blurX > 0.4;
        const filterId = useHBlur ? `seqhb-${i}` : null;

        const segSpec: SceneSpec = { ...spec, ui: seg.ui, seed: spec.seed + i * 97, sequence: undefined as never };

        return (
          <Sequence key={i} from={startF} durationInFrames={durF} layout="none">
            {useHBlur && (
              <svg width={0} height={0} style={{ position: 'absolute' }} aria-hidden>
                <defs>
                  <filter id={filterId!} x="-30%" y="-5%" width="160%" height="110%">
                    <feGaussianBlur stdDeviation={`${aff.blurX.toFixed(2)} 0`} />
                  </filter>
                </defs>
              </svg>
            )}
            <AbsoluteFill style={layerStyle(aff, filterId)}>
              <AppleScene spec={segSpec} />
            </AbsoluteFill>
          </Sequence>
        );
      })}

      {/* Transition SFX — one hit per boundary, landing just as the swipe peaks. Mounted only
          when the CC0 asset for that transition exists; otherwise the sequence is silent. */}
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
