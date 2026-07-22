// @ts-nocheck — React-Three-Fiber's JSX intrinsics (mesh/…Geometry/…Material) are
// runtime-augmented; strict TS typing of them is notoriously brittle and adds no safety
// to a render that esbuild bundles anyway. The rest of the stack stays fully typed.
//
// Scene3D — the real 3D motion-graphics scene: a faceted hero solid with a PBR metal
// surface, a ring of depth-scattered shards orbiting it, three-point lighting and a
// slowly drifting camera. Beat-reactive (breathes on the downbeat), deterministic
// (positions from the spec seed, motion from absolute time — no useFrame, so Remotion
// can seek any frame). Software-GL friendly (renders headless via --gl=angle).

import React from 'react';
import { useThree } from '@react-three/fiber';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import * as THREE from 'three';
import type { SceneSpec } from '../spec';
import { beatPulse, springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';

const HERO_GEOMS = ['ico', 'knot', 'octa', 'dodeca'] as const;

/** Camera drifts on a slow Lissajous path and always frames the origin. Imperative so
 *  it's a pure function of the frame (set every render → seekable). */
const CameraRig: React.FC<{ t: number }> = ({ t }) => {
  const { camera } = useThree();
  camera.position.set(Math.sin(t * 0.18) * 0.9, Math.cos(t * 0.14) * 0.6,
    6.2 - Math.sin(t * 0.22) * 0.5);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  return null;
};

const Shard: React.FC<{ i: number; seed: number; acc: string; fg: string; t: number }>
  = ({ i, seed, acc, fg, t }) => {
    const a = hash01(i, seed) * Math.PI * 2;
    const rad = 2.6 + hash01(i, seed + 11) * 1.9;
    const depth = -1.5 + hash01(i, seed + 23) * 3.0;
    const sp = 0.12 + hash01(i, seed + 31) * 0.22;
    const ang = a + t * sp * (i % 2 ? 1 : -1);
    const x = Math.cos(ang) * rad;
    const y = Math.sin(ang * 0.9 + i) * (rad * 0.5) + Math.sin(t * 0.4 + i) * 0.3;
    const s = 0.13 + hash01(i, seed + 41) * 0.22;
    const col = i % 3 === 0 ? fg : acc;
    return (
      <mesh position={[x, y, depth]} rotation={[t * sp + i, t * sp * 1.3, 0]} scale={s}>
        {i % 2 ? <octahedronGeometry args={[1, 0]} /> : <tetrahedronGeometry args={[1, 0]} />}
        <meshStandardMaterial color={col} metalness={0.7} roughness={0.3}
          emissive={acc} emissiveIntensity={0.12} />
      </mesh>
    );
  };

export const Scene3D: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const { palette, beat, seed, scenes } = spec;
  const acc = palette.accent;

  // Movement index (which hero solid) advances with the spec's scenes.
  const nScenes = Math.max(1, scenes.length);
  const per = spec.duration / nScenes;
  const mv = Math.min(nScenes - 1, Math.floor(t / Math.max(per, 0.1)));
  const geom = HERO_GEOMS[(seed + mv) % HERO_GEOMS.length];

  const intro = springStep(t, { stiffness: 90, damping: 0.7, delay: 0 });
  const pulse = beatPulse(t, beat);
  const heroScale = (0.5 + 0.5 * intro) * (1.5 + 0.09 * pulse);
  const shardN = 16;

  return (
    <>
      <CameraRig t={t} />
      <ambientLight intensity={0.35} />
      <pointLight position={[5, 5, 6]} intensity={120} color="#ffffff" />
      <pointLight position={[-6, -3, 3]} intensity={80} color={acc} />
      <pointLight position={[0, 6, -5]} intensity={55} color={palette.fg} />

      <group rotation={[Math.sin(t * 0.25) * 0.25, t * 0.28, Math.sin(t * 0.2) * 0.1]}>
        <mesh scale={heroScale}>
          {geom === 'ico' && <icosahedronGeometry args={[1, 0]} />}
          {geom === 'knot' && <torusKnotGeometry args={[0.8, 0.28, 180, 32]} />}
          {geom === 'octa' && <octahedronGeometry args={[1.2, 0]} />}
          {geom === 'dodeca' && <dodecahedronGeometry args={[1.1, 0]} />}
          <meshStandardMaterial
            color={acc}
            metalness={0.85}
            roughness={0.18 + 0.06 * Math.sin(t * 0.5)}
            emissive={acc}
            emissiveIntensity={0.18 + 0.12 * pulse}
            flatShading={geom !== 'knot'}
          />
        </mesh>
        {/* faint wireframe shell around the hero for a technical, premium read */}
        <mesh scale={heroScale * 1.35}>
          <icosahedronGeometry args={[1, 1]} />
          <meshBasicMaterial color={acc} wireframe transparent opacity={0.08} />
        </mesh>
      </group>

      {Array.from({ length: shardN }, (_, i) => (
        <Shard key={i} i={i} seed={seed} acc={acc} fg={palette.fg} t={t} />
      ))}

      <fog attach="fog" args={[palette.bg, 6, 13]} />
    </>
  );
};
