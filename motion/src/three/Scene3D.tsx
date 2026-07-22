// @ts-nocheck — React-Three-Fiber's JSX intrinsics (mesh/…Geometry/…Material) are
// runtime-augmented; strict TS typing of them is brittle and adds no safety to a render
// that esbuild bundles anyway. The rest of the stack stays fully typed.
//
// Scene3D — the HIGH-END 3D PROMO look (Pillar 3): glowing accent GLASS BLOBS breathing at
// the centre, a fan of FLOATING DEVICE PANELS (app slabs with emissive UI hints) that fly in
// from depth on a staggered spring, dramatic three-point + rim lighting, a soft bloom halo,
// and a cinematic camera push-in with a gentle orbit. Deterministic (positions from the spec
// seed, motion from absolute time — no useFrame, so Remotion can seek any frame). Software-GL
// friendly: no transmission/render-targets, only Standard/Basic materials + transparency, so
// it renders headless on a GPU-less server via `remotion render … --gl=angle`.

import React from 'react';
import { useThree } from '@react-three/fiber';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import * as THREE from 'three';
import type { SceneSpec } from '../spec';
import { beatPulse, springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const ease = (x) => 1 - Math.pow(1 - clamp01(x), 3);

/** Cinematic camera: a slow dolly-in over the intro, then a gentle breathing orbit that
 *  always frames the origin. Pure function of the frame (set every render → seekable). */
const CameraRig: React.FC<{ t: number }> = ({ t }) => {
  const { camera } = useThree();
  const dolly = ease(t / 2.2); // push in during the first ~2.2s
  const z = 9.2 - 3.1 * dolly - Math.sin(t * 0.2) * 0.35;
  camera.position.set(Math.sin(t * 0.16) * 1.15, 0.3 + Math.cos(t * 0.12) * 0.5, z);
  camera.lookAt(0, 0.1, 0);
  camera.updateProjectionMatrix();
  return null;
};

/** A glowing "glass" blob: a translucent emissive shell over a bright inner core, with a
 *  faint wireframe rim for edge definition — reads as lit glass without transmission. */
const GlassBlob: React.FC<{ pos; scale; color; t; phase }>
  = ({ pos, scale, color, t, phase }) => {
    const breathe = 1 + 0.06 * Math.sin(t * 0.9 + phase);
    const drift = [Math.sin(t * 0.3 + phase) * 0.12, Math.cos(t * 0.26 + phase) * 0.12, 0];
    return (
      <group position={[pos[0] + drift[0], pos[1] + drift[1], pos[2]]}
        rotation={[t * 0.12 + phase, t * 0.16, 0]} scale={scale * breathe}>
        {/* translucent outer shell */}
        <mesh>
          <icosahedronGeometry args={[1, 1]} />
          <meshStandardMaterial color={color} transparent opacity={0.26}
            metalness={0.1} roughness={0.08} emissive={color} emissiveIntensity={0.4}
            depthWrite={false} />
        </mesh>
        {/* bright inner core (the glow source) */}
        <mesh scale={0.6}>
          <icosahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.6}
            metalness={0.2} roughness={0.3} />
        </mesh>
        {/* wire rim */}
        <mesh scale={1.02}>
          <icosahedronGeometry args={[1, 1]} />
          <meshBasicMaterial color={color} wireframe transparent opacity={0.12} />
        </mesh>
      </group>
    );
  };

/** A floating device panel: a thin dark slab with an emissive accent face and a few glowing
 *  UI bars, flying in from depth on a spring with a slight perspective tilt. */
const DevicePanel: React.FC<{ i; n; acc; fg; t; seed }>
  = ({ i, n, acc, fg, t, seed }) => {
    const spread = (i - (n - 1) / 2);
    const inSpring = springStep(t - 0.35 - i * 0.18, { stiffness: 90, damping: 0.72, delay: 0 });
    const s = clamp01(inSpring);
    const x = spread * 2.35;
    const y = Math.sin(t * 0.4 + i) * 0.18 + spread * 0.12;
    const z = -1.4 - Math.abs(spread) * 0.6 + (1 - s) * -7; // fly in from far
    const tilt = spread * 0.26;
    const w = 1.35, h = 2.75, d = 0.12;
    const col = i % 2 ? fg : acc;
    return (
      <group position={[x, y, z]} rotation={[Math.sin(t * 0.3 + i) * 0.06, -tilt, spread * 0.04]}
        scale={0.5 + 0.5 * s}>
        {/* body */}
        <mesh>
          <boxGeometry args={[w, h, d]} />
          <meshStandardMaterial color="#14161d" metalness={0.6} roughness={0.35}
            emissive={col} emissiveIntensity={0.06} />
        </mesh>
        {/* emissive screen face */}
        <mesh position={[0, 0, d / 2 + 0.001]}>
          <planeGeometry args={[w * 0.9, h * 0.92]} />
          <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.9}
            metalness={0.1} roughness={0.5} transparent opacity={0.92} />
        </mesh>
        {/* glowing UI bars */}
        {[0, 1, 2, 3].map((k) => (
          <mesh key={k} position={[-w * 0.16, h * (0.28 - k * 0.16), d / 2 + 0.01]}>
            <boxGeometry args={[w * (0.5 - k * 0.06), h * 0.05, 0.02]} />
            <meshStandardMaterial color="#ffffff" emissive="#ffffff"
              emissiveIntensity={0.6} transparent opacity={0.85} />
          </mesh>
        ))}
      </group>
    );
  };

/** Soft additive bloom halo behind the hero — a big camera-facing gradient sprite. */
const Halo: React.FC<{ color; t }> = ({ color, t }) => {
  const tex = React.useMemo(() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, 'rgba(255,255,255,0.9)');
    grd.addColorStop(0.25, 'rgba(255,255,255,0.5)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
    const texture = new THREE.CanvasTexture(c);
    return texture;
  }, []);
  const pulse = 1 + 0.08 * Math.sin(t * 1.1);
  return (
    <mesh position={[0, 0, -3.2]} scale={6 * pulse}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={tex} color={color} transparent opacity={0.3}
        blending={THREE.AdditiveBlending} depthWrite={false} />
    </mesh>
  );
};

export const Scene3D: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const { palette, beat, seed } = spec;
  const acc = palette.accent;
  const fg = palette.fg;
  const pulse = beatPulse(t, beat);

  // A small cluster of glass blobs at the centre, sizes/offsets from the seed.
  const blobs = Array.from({ length: 3 }, (_, i) => ({
    pos: [(hash01(i, seed) - 0.5) * 1.5, (hash01(i, seed + 7) - 0.5) * 1.0 - 0.1, 0.6 + hash01(i, seed + 13) * 0.7],
    scale: (0.52 + hash01(i, seed + 3) * 0.5) * (1 + 0.05 * pulse),
    phase: i * 2.1,
  }));

  return (
    <>
      <CameraRig t={t} />
      <ambientLight intensity={0.4} />
      <pointLight position={[5, 6, 6]} intensity={140} color="#ffffff" />
      <pointLight position={[-6, -2, 4]} intensity={90} color={acc} />
      <pointLight position={[0, 5, -6]} intensity={70} color={fg} />
      {/* bright key rim from behind for a glossy edge */}
      <pointLight position={[0, 0, -4]} intensity={60} color={acc} />

      <Halo color={acc} t={t} />

      {/* floating device panels fanned behind/around the hero */}
      {Array.from({ length: 3 }, (_, i) => (
        <DevicePanel key={i} i={i} n={3} acc={acc} fg={fg} t={t} seed={seed} />
      ))}

      {/* hero: cluster of glowing glass blobs */}
      {blobs.map((b, i) => (
        <GlassBlob key={i} pos={b.pos} scale={b.scale} color={acc} t={t} phase={b.phase} />
      ))}

      <fog attach="fog" args={[palette.bg, 8, 18]} />
    </>
  );
};
