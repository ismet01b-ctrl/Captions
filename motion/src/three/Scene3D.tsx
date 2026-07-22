// @ts-nocheck — R3F intrinsics are runtime-augmented; strict typing adds no safety here.
//
// Scene3D — the HIGH-END 3D PROMO, rebuilt to match the reference (Notion-AI style): a bright
// world of RED GLASS — organic transmissive blobs, glass chips carrying app icons that tumble
// through depth, concentric rings around a hero glass orb — with a camera that flows through
// the space. Real glass via meshPhysicalMaterial (transmission), lit by a bright studio env so
// it refracts and glows; Bloom + DoF (see Motion3D) do the cinematic finish. Deterministic
// (seed + absolute time, no useFrame → seekable).

import React from 'react';
import { useThree } from '@react-three/fiber';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import * as THREE from 'three';
import type { SceneSpec } from '../spec';
import { beatPulse } from '../lib/spring';
import { hash01 } from '../lib/rng';

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

// ---- bright studio environment so the glass refracts light, not a black void ----
const studioEnv = () => {
  const W = 1024, H = 512; const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, '#ffffff'); sky.addColorStop(0.55, '#f2f4f8'); sky.addColorStop(1, '#e6e9f0');
  g.fillStyle = sky; g.fillRect(0, 0, W, H);
  // soft bright rectangles (softboxes) the glass will catch as highlights
  const box = (x, w, a) => { const gr = g.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(0.5, `rgba(255,255,255,${a})`); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(x, 0, w, H); };
  box(W * 0.08, W * 0.12, 1); box(W * 0.6, W * 0.1, 0.9);
  // a warm/red wash low so the glass picks up the accent
  const warm = g.createLinearGradient(0, H * 0.5, 0, H); warm.addColorStop(0, 'rgba(0,0,0,0)'); warm.addColorStop(1, 'rgba(224,72,61,0.25)');
  g.fillStyle = warm; g.fillRect(0, H * 0.5, W, H * 0.5);
  const tex = new THREE.CanvasTexture(c); tex.mapping = THREE.EquirectangularReflectionMapping; tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
};

const EnvRig = ({ intensity }) => {
  const { scene } = useThree();
  const tex = React.useMemo(() => studioEnv(), []);
  scene.environment = tex;
  scene.environmentIntensity = intensity ?? 1;
  return null;
};

// A simple white glyph on a transparent canvas → used as an emissive icon on a glass chip.
const iconTex = (() => {
  const cache = {};
  return (kind) => {
    if (cache[kind]) return cache[kind];
    const s = 128; const c = document.createElement('canvas'); c.width = c.height = s; const g = c.getContext('2d');
    g.strokeStyle = '#ffffff'; g.fillStyle = '#ffffff'; g.lineWidth = 10; g.lineCap = 'round'; g.lineJoin = 'round';
    g.translate(s / 2, s / 2); const r = 34;
    if (kind === 0) { g.beginPath(); g.arc(0, 0, r, 0, 7); g.moveTo(-r * 0.5, 0); g.lineTo(r * 0.5, 0); g.moveTo(0, -r * 0.5); g.lineTo(0, r * 0.5); g.stroke(); }
    else if (kind === 1) { g.strokeRect(-r, -r, r * 2, r * 2); }
    else if (kind === 2) { g.beginPath(); g.moveTo(-r, r * 0.4); g.lineTo(-r * 0.2, -r * 0.3); g.lineTo(r * 0.3, r * 0.2); g.lineTo(r, -r * 0.6); g.stroke(); }
    else if (kind === 3) { g.beginPath(); g.arc(0, 0, r, 0, 7); g.moveTo(0, -r * 0.6); g.lineTo(0, 0); g.lineTo(r * 0.5, r * 0.3); g.stroke(); }
    else { g.beginPath(); for (let i = 0; i < 5; i++) { const a = -Math.PI / 2 + i * Math.PI * 2 / 5; g.lineTo(Math.cos(a) * r, Math.sin(a) * r); const b = a + Math.PI / 5; g.lineTo(Math.cos(b) * r * 0.45, Math.sin(b) * r * 0.45); } g.closePath(); g.stroke(); }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; cache[kind] = t; return t;
  };
})();

// Real red glass (transmission) — translucent + refractive, not a solid ball. Higher
// attenuationDistance keeps it see-through so the bright world reads through the glass.
const RedGlass = ({ rough = 0.04, thickness = 0.7, ior = 1.45 }) => (
  <meshPhysicalMaterial color={'#ff5647'} metalness={0} roughness={rough} transmission={1}
    thickness={thickness} ior={ior} attenuationColor={'#ff4d42'} attenuationDistance={3.6}
    clearcoat={1} clearcoatRoughness={0.06} envMapIntensity={1.8} specularIntensity={1}
    transparent opacity={1} />
);

const CameraRig = ({ t }) => {
  const { camera } = useThree();
  const d = easeInOut(clamp01(t / 3));
  const z = 13 - 3 * d - Math.sin(t * 0.12) * 0.4; // stay further back → negative space
  camera.position.set(Math.sin(t * 0.14) * 1.8, 0.4 + Math.cos(t * 0.1) * 0.5, z);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  return null;
};

const Blob = ({ pos, scale, t, phase }) => {
  const breathe = 1 + 0.05 * Math.sin(t * 0.8 + phase);
  return (
    <mesh position={[pos[0] + Math.sin(t * 0.25 + phase) * 0.2, pos[1] + Math.cos(t * 0.22 + phase) * 0.2, pos[2]]}
      rotation={[t * 0.15 + phase, t * 0.2, 0]} scale={scale * breathe}>
      <icosahedronGeometry args={[1, 4]} />
      <RedGlass rough={0.05} thickness={1.6} />
    </mesh>
  );
};

// A glass chip: a rounded red-glass disc with a white icon on the face, tumbling through depth.
const Chip = ({ i, seed, t }) => {
  const a = hash01(i, seed) * Math.PI * 2;
  const rad = 2.4 + hash01(i, seed + 5) * 2.2;
  const depth = -2 + hash01(i, seed + 11) * 4;
  const sp = 0.1 + hash01(i, seed + 17) * 0.18;
  const ang = a + t * sp * (i % 2 ? 1 : -1);
  const x = Math.cos(ang) * rad;
  const y = Math.sin(ang * 0.8 + i) * rad * 0.42 + Math.sin(t * 0.4 + i) * 0.25;
  const s = 0.42 + hash01(i, seed + 23) * 0.3;
  return (
    <group position={[x, y, depth]} rotation={[t * sp * 1.4 + i, t * sp * 1.1, i]} scale={s}>
      <mesh>
        <cylinderGeometry args={[1, 1, 0.34, 48]} />
        <RedGlass rough={0.08} thickness={0.8} />
      </mesh>
      {/* white emissive icon just proud of the top face */}
      <mesh position={[0, 0.18, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.1, 1.1]} />
        <meshStandardMaterial map={iconTex(i % 5)} transparent emissive={'#ffffff'} emissiveMap={iconTex(i % 5)} emissiveIntensity={1.6} />
      </mesh>
    </group>
  );
};

// Concentric thin rings around the hero — the "radar / it understands" motif.
const Rings = ({ t }) => (
  <group rotation={[Math.PI / 2.1, 0, t * 0.08]}>
    {[1.6, 2.4, 3.3, 4.3].map((r, i) => (
      <mesh key={i} rotation={[0, 0, t * 0.1 * (i % 2 ? 1 : -1)]}>
        <torusGeometry args={[r, 0.012, 8, 120]} />
        <meshStandardMaterial color={'#c9ccd4'} metalness={0.4} roughness={0.4} transparent opacity={0.5} />
      </mesh>
    ))}
  </group>
);

export const Scene3D: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const { seed, beat } = spec;
  const pulse = beatPulse(t, beat);

  return (
    <>
      <CameraRig t={t} />
      <EnvRig intensity={1.15} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 6, 6]} intensity={2.2} color="#ffffff" />
      <directionalLight position={[-5, 2, 3]} intensity={1.2} color="#ffd7d2" />
      <pointLight position={[0, 0, 4]} intensity={40} color="#ffffff" />

      <Rings t={t} />

      {/* hero glass orb at the centre */}
      <mesh scale={1.15 * (1 + 0.04 * pulse)} rotation={[t * 0.1, t * 0.14, 0]}>
        <sphereGeometry args={[1, 64, 64]} />
        <RedGlass rough={0.02} thickness={0.9} />
      </mesh>

      {/* organic red-glass blobs, spread wide for depth + air */}
      <Blob pos={[-4.2, 1.6, -1]} scale={0.95} t={t} phase={0.4} />
      <Blob pos={[4.4, -1.8, -2]} scale={1.1} t={t} phase={2.1} />
      <Blob pos={[1.2, 3.4, -3.5]} scale={0.8} t={t} phase={4.0} />

      {/* glass chips carrying icons, tumbling through depth */}
      {Array.from({ length: 9 }, (_, i) => <Chip key={i} i={i} seed={seed} t={t} />)}
    </>
  );
};
