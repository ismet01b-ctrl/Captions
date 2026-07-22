// @ts-nocheck — React-Three-Fiber's JSX intrinsics (mesh/…Geometry/…Material) are
// runtime-augmented; strict TS typing of them is brittle and adds no safety to a render
// that esbuild bundles anyway. The rest of the stack stays fully typed.
//
// Scene3D — the HIGH-END 3D PRODUCT PROMO (Pillar 3). A hero phone floats centre-stage with
// two supporting phones fanned behind it; each phone carries a REAL dark-mode iOS screen
// (drawn to a canvas texture: status bar, app grid / WhatsApp chat / notification centre) so
// actual UI flies through space, not empty tiles. Glowing accent glass blobs + an additive
// bloom halo sit behind for depth; a cinematic camera dollies in and breathes. Deterministic
// (seed + absolute time, no useFrame → seekable) and software-GL safe (Standard/Basic
// materials + canvas textures only, no transmission/render-targets → renders via --gl=angle).

import React from 'react';
import { useThree } from '@react-three/fiber';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import * as THREE from 'three';
import type { SceneSpec } from '../spec';
import { beatPulse, springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const ease = (x) => 1 - Math.pow(1 - clamp01(x), 3);
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

// ------------------------------------------------------------ studio environment (reflections)

/** A procedural studio HDRI-lite (equirectangular canvas): dark room with bright vertical
 *  softbox strips + a warm floor. Assigned to scene.environment so the glass and phone glass
 *  actually REFLECT light — the single biggest step toward a real product-render look.
 *  (No PMREM: that needs a GPU render-target; raw equirect reflections still read as studio.) */
const studioEnv = (accent) => {
  const W = 1024, Hh = 512; const c = document.createElement('canvas'); c.width = W; c.height = Hh;
  const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, Hh);
  sky.addColorStop(0, '#20242e'); sky.addColorStop(0.5, '#14161d'); sky.addColorStop(0.55, '#0c0d12'); sky.addColorStop(1, '#050608');
  g.fillStyle = sky; g.fillRect(0, 0, W, Hh);
  // bright softboxes (key + fills)
  const box = (x, w, a, col) => { const gr = g.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(0.5, col.replace('A', String(a))); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(x, 20, w, Hh * 0.42); };
  box(W * 0.10, W * 0.14, 0.9, 'rgba(255,255,255,A)');
  box(W * 0.62, W * 0.10, 0.7, 'rgba(255,255,255,A)');
  box(W * 0.40, W * 0.08, 0.5, 'rgba(255,240,220,A)');
  // warm accent wash low
  const warm = g.createLinearGradient(0, Hh * 0.55, 0, Hh); warm.addColorStop(0, 'rgba(0,0,0,0)'); warm.addColorStop(1, accent + '55');
  g.fillStyle = warm; g.fillRect(0, Hh * 0.55, W, Hh * 0.45);
  const tex = new THREE.CanvasTexture(c); tex.mapping = THREE.EquirectangularReflectionMapping; tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
};

const EnvRig: React.FC<any> = ({ accent }) => {
  const { scene } = useThree();
  const tex = React.useMemo(() => studioEnv(accent), [accent]);
  scene.environment = tex;
  return null;
};

/** A soft dark contact shadow (radial canvas sprite) laid flat under a device. */
const shadowTex = (() => { let t = null; return () => { if (t) return t; const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d'); const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64); grd.addColorStop(0, 'rgba(0,0,0,0.55)'); grd.addColorStop(0.6, 'rgba(0,0,0,0.28)'); grd.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = grd; g.fillRect(0, 0, 128, 128); t = new THREE.CanvasTexture(c); return t; }; })();

// -------------------------------------------------------------- screen textures (canvas UI)

const hexToHsl = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '') ;
  const n = m ? parseInt(m[1], 16) : 0x3574ff;
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const l = (mx + mn) / 2; const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d) { if (mx === r) h = ((g - b) / d) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4; }
  return [((h * 60) + 360) % 360, s, l];
};

const rr = (g, x, y, w, h, r) => { g.beginPath(); g.roundRect(x, y, w, h, r); };

const drawStatus = (g, W, hue) => {
  g.fillStyle = '#f3f5fb'; g.font = '700 26px system-ui, sans-serif'; g.textBaseline = 'middle';
  g.textAlign = 'left'; g.fillText('13:39', 34, 40);
  g.textAlign = 'right'; g.font = '700 24px system-ui, sans-serif'; g.fillText('5G', W - 78, 40);
  // signal
  for (let i = 0; i < 4; i++) { g.globalAlpha = i < 2 ? 1 : 0.4; g.fillRect(W - 150 + i * 9, 48 - (8 + i * 4), 6, 8 + i * 4); }
  g.globalAlpha = 1;
  // battery
  g.strokeStyle = 'rgba(243,245,251,0.5)'; g.lineWidth = 2; rr(g, W - 64, 30, 40, 20, 5); g.stroke();
  g.fillStyle = '#ffcf3f'; rr(g, W - 60, 34, 20, 12, 3); g.fill();
};

/** Draw a full dark-mode iOS screen to a canvas → CanvasTexture. Rounded phone with a small
 *  transparent margin so the plane reads as an actual device. */
const makeScreen = (variant, accent) => {
  const W = 480, H = 1010; const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'); const [hue] = hexToHsl(accent);
  const pad = 10, r = 62;
  // device body (rounded), transparent outside
  rr(g, pad, pad, W - pad * 2, H - pad * 2, r); g.save(); g.clip();

  if (variant === 'chat') {
    g.fillStyle = '#0b141a'; g.fillRect(0, 0, W, H);
    drawStatus(g, W, hue);
    // nav
    g.fillStyle = 'rgba(30,33,42,0.85)'; g.fillRect(0, 60, W, 96);
    g.fillStyle = `hsl(${hue},55%,50%)`; g.beginPath(); g.arc(96, 116, 30, 0, 7); g.fill();
    g.fillStyle = '#eaf0f2'; g.font = '700 30px system-ui'; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText('Mervenur', 140, 104);
    g.fillStyle = '#8aa0a8'; g.font = '400 22px system-ui'; g.fillText('online', 140, 132);
    // bubbles
    const bub = (x, y, w, h, col) => { g.fillStyle = col; rr(g, x, y, w, h, 26); g.fill(); };
    bub(40, 210, 300, 92, '#1f2c33'); bub(W - 330, 330, 290, 78, '#075e54');
    bub(40, 430, 340, 78, '#1f2c33'); bub(W - 300, 530, 260, 78, '#075e54');
    g.fillStyle = '#e9edef'; g.font = '400 24px system-ui';
    g.fillText('Das sieht cute aus', 62, 256); g.fillText('Mein Favorit', W - 312, 369);
    g.fillText('So besser?', 62, 469); g.fillText('Ja perfekt', W - 282, 569);
    // input bar
    g.fillStyle = '#1f2c33'; rr(g, 30, H - 108, W - 130, 74, 37); g.fill();
    g.fillStyle = '#25d366'; g.beginPath(); g.arc(W - 62, H - 71, 34, 0, 7); g.fill();
  } else if (variant === 'notify') {
    const grd = g.createLinearGradient(0, 0, W, H);
    grd.addColorStop(0, `hsl(${(hue + 20) % 360},32%,15%)`); grd.addColorStop(0.5, '#14100e'); grd.addColorStop(1, 'hsl(28,45%,20%)');
    g.fillStyle = grd; g.fillRect(0, 0, W, H); drawStatus(g, W, hue);
    g.fillStyle = '#f3f5fb'; g.textAlign = 'center'; g.font = '600 24px system-ui'; g.fillText('Wednesday, 22 July', W / 2, 150);
    g.font = '700 120px system-ui'; g.fillText('13:39', W / 2, 250);
    const card = (y, t1, t2) => {
      g.fillStyle = 'rgba(44,47,58,0.72)'; rr(g, 34, y, W - 68, 130, 34); g.fill();
      g.fillStyle = `hsl(${hue},75%,55%)`; rr(g, 60, y + 30, 66, 66, 18); g.fill();
      g.fillStyle = '#f3f5fb'; g.textAlign = 'left'; g.font = '800 26px system-ui'; g.fillText(t1, 150, y + 52);
      g.fillStyle = '#c2c7d2'; g.font = '400 23px system-ui'; g.fillText(t2, 150, y + 90);
    };
    card(430, 'DouchkoVE', 'Your clip is ready'); card(590, 'DouchkoVE', 'Tap to see what’s new');
  } else { // home
    const grd = g.createLinearGradient(0, 0, W, H);
    grd.addColorStop(0, `hsl(${(hue + 15) % 360},34%,16%)`); grd.addColorStop(0.5, '#14110f'); grd.addColorStop(1, 'hsl(26,42%,19%)');
    g.fillStyle = grd; g.fillRect(0, 0, W, H); drawStatus(g, W, hue);
    const cols = 4, gap = 30, m = 44, cell = (W - m * 2 - gap * (cols - 1)) / cols;
    for (let i = 0; i < 16; i++) {
      const cx = m + (i % cols) * (cell + gap), cy = 120 + Math.floor(i / cols) * (cell + gap + 22);
      const hh = (i * 47 + hue) % 360; g.fillStyle = `hsl(${hh},68%,55%)`; rr(g, cx, cy, cell, cell, cell * 0.26); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.85)'; g.fillRect(cx + cell * 0.32, cy + cell * 0.32, cell * 0.36, cell * 0.1);
      g.fillStyle = 'rgba(255,255,255,0.6)'; g.font = '600 18px system-ui'; g.textAlign = 'center'; g.fillText('App', cx + cell / 2, cy + cell + 18);
    }
    // dock
    g.fillStyle = 'rgba(60,64,76,0.5)'; rr(g, 40, H - 150, W - 80, 118, 40); g.fill();
    for (let i = 0; i < 4; i++) { const dx = 78 + i * ((W - 160) / 3 - 6); g.fillStyle = `hsl(${(i * 80 + 200) % 360},65%,55%)`; rr(g, dx, H - 132, 82, 82, 22); g.fill(); }
  }
  g.restore();
  // bezel highlight
  g.strokeStyle = 'rgba(255,255,255,0.16)'; g.lineWidth = 3; rr(g, pad + 1.5, pad + 1.5, W - pad * 2 - 3, H - pad * 2 - 3, r - 2); g.stroke();

  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  return { tex, aspect: (W - pad * 2) / (H - pad * 2) };
};

/** Cinematic camera choreography: a fast-then-settle dolly-in, a slow arc around the hero,
 *  and a gentle vertical breathe. Eased so it reads hand-keyed, not linear. */
const CameraRig: React.FC<{ t: number }> = ({ t }) => {
  const { camera } = useThree();
  const d = easeInOut(clamp01(t / 2.6));         // push in and settle
  const arc = easeInOut(clamp01((t - 1.2) / 6)); // slow orbit after the push
  const z = 10.5 - 3.6 * d - Math.sin(t * 0.14) * 0.25;
  const x = Math.sin(-0.5 + arc * 0.9) * 1.5 + Math.sin(t * 0.11) * 0.25;
  camera.position.set(x, 0.4 + Math.cos(t * 0.1) * 0.3, z);
  camera.lookAt(0, 0.12, 0);
  camera.updateProjectionMatrix();
  return null;
};

/** Glossy studio floor + a warm accent glow pool, so the devices sit in a real space. */
const Floor: React.FC<any> = ({ accent, t }) => (
  <group position={[0, -2.5, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[46, 46]} />
      <meshStandardMaterial color="#080910" metalness={0.75} roughness={0.32} envMapIntensity={0.7} />
    </mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 1]}>
      <planeGeometry args={[14, 14]} />
      <meshBasicMaterial map={shadowTex()} color={accent} transparent opacity={0.35 + 0.05 * Math.sin(t * 1.1)}
        blending={THREE.AdditiveBlending} depthWrite={false} />
    </mesh>
  </group>
);

const GlassBlob: React.FC<any> = ({ pos, scale, color, t, phase }) => {
  const breathe = 1 + 0.06 * Math.sin(t * 0.9 + phase);
  return (
    <group position={[pos[0] + Math.sin(t * 0.3 + phase) * 0.1, pos[1] + Math.cos(t * 0.26 + phase) * 0.1, pos[2]]}
      rotation={[t * 0.1 + phase, t * 0.14, 0]} scale={scale * breathe}>
      <mesh><icosahedronGeometry args={[1, 1]} />
        <meshStandardMaterial color={color} transparent opacity={0.3} metalness={0.5} roughness={0.06}
          emissive={color} emissiveIntensity={0.3} envMapIntensity={1.6} depthWrite={false} /></mesh>
      <mesh scale={0.55}><icosahedronGeometry args={[1, 0]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.5} metalness={0.3} roughness={0.25} envMapIntensity={1.2} /></mesh>
    </group>
  );
};

/** A floating phone carrying a real dark-mode screen texture. Flies in from depth on a
 *  spring, then floats + sways smoothly. */
const PhonePanel: React.FC<any> = ({ variant, accent, t, delay, x, baseZ, baseScale, rotY, phase }) => {
  const { tex, aspect } = React.useMemo(() => makeScreen(variant, accent), [variant, accent]);
  const s = clamp01(springStep(t - delay, { stiffness: 80, damping: 0.82, delay: 0 }));
  const H = 3.15, Wd = H * aspect;
  const z = baseZ + (1 - s) * -8;
  const y = 0.12 + Math.sin(t * 0.5 + phase) * 0.09;
  const sway = Math.sin(t * 0.35 + phase) * 0.05;
  return (
    <group position={[x, y, z]} rotation={[sway * 0.5, rotY + sway, sway * 0.3]} scale={baseScale * (0.7 + 0.3 * s)}>
      {/* contact shadow on the floor beneath the device */}
      <mesh position={[0, -H * 0.62, -0.2]} rotation={[-Math.PI / 2.1, 0, 0]}>
        <planeGeometry args={[Wd * 2.2, Wd * 1.6]} />
        <meshBasicMaterial map={shadowTex()} transparent opacity={0.7 * s} depthWrite={false} />
      </mesh>
      {/* device back / edge (glossy, catches the environment) */}
      <mesh position={[0, 0, -0.06]}>
        <planeGeometry args={[Wd * 1.04, H * 1.02]} />
        <meshStandardMaterial color="#05060a" metalness={0.7} roughness={0.35} envMapIntensity={0.8} transparent opacity={0.94 * s} />
      </mesh>
      {/* glossy screen: emissive UI + a real environment reflection on the glass */}
      <mesh>
        <planeGeometry args={[Wd, H]} />
        <meshStandardMaterial map={tex} emissiveMap={tex} emissive={'#ffffff'} emissiveIntensity={0.5}
          roughness={0.16} metalness={0.1} envMapIntensity={0.7} transparent opacity={clamp01(s * 1.4)} />
      </mesh>
    </group>
  );
};

const Halo: React.FC<any> = ({ color, t }) => {
  const tex = React.useMemo(() => {
    const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
    const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, 'rgba(255,255,255,0.9)'); grd.addColorStop(0.28, 'rgba(255,255,255,0.45)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
  }, []);
  return (
    <mesh position={[0, 0, -3.5]} scale={8 * (1 + 0.07 * Math.sin(t * 1.1))}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={tex} color={color} transparent opacity={0.28} blending={THREE.AdditiveBlending} depthWrite={false} />
    </mesh>
  );
};

export const Scene3D: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const { palette, beat, seed } = spec;
  const acc = palette.accent;
  const pulse = beatPulse(t, beat);

  return (
    <>
      <CameraRig t={t} />
      <EnvRig accent={acc} />
      <ambientLight intensity={0.4} />
      <pointLight position={[5, 6, 7]} intensity={150} color="#ffffff" />
      <pointLight position={[-6, -2, 4]} intensity={95} color={acc} />
      <pointLight position={[0, 5, -6]} intensity={70} color={palette.fg} />
      <pointLight position={[0, 0, -4]} intensity={55} color={acc} />

      <Floor accent={acc} t={t} />
      <Halo color={acc} t={t} />

      {/* background glass blobs for depth + colour */}
      {Array.from({ length: 3 }, (_, i) => (
        <GlassBlob key={i} color={acc} t={t} phase={i * 2.1}
          pos={[(hash01(i, seed) - 0.5) * 4.4, (hash01(i, seed + 7) - 0.5) * 2.4, -2.2 - hash01(i, seed + 3) * 1.5]}
          scale={(0.5 + hash01(i, seed + 5) * 0.5) * (1 + 0.05 * pulse)} />
      ))}

      {/* supporting phones fan in behind, then the hero rises in front */}
      <PhonePanel variant="chat" accent={acc} t={t} delay={0.35} x={-2.35} baseZ={-1.3} baseScale={0.74} rotY={0.42} phase={1.2} />
      <PhonePanel variant="notify" accent={acc} t={t} delay={0.55} x={2.35} baseZ={-1.3} baseScale={0.74} rotY={-0.42} phase={2.7} />
      <PhonePanel variant="home" accent={acc} t={t} delay={0.15} x={0} baseZ={0.5} baseScale={1.0} rotY={0} phase={0} />

      <fog attach="fog" args={[palette.bg, 9, 20]} />
    </>
  );
};
