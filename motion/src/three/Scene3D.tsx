// @ts-nocheck — R3F intrinsics are runtime-augmented; strict typing adds no safety here.
//
// Scene3D — the 3D PROMO, rebuilt to reference REAL THINGS (per Ismet's refs @refined.motion /
// @_movitools_): premium iOS-style WIDGET CARDS — a calendar, a battery/charge, a clock, an
// activity ring, an app-store card — float in depth as glossy tiles with soft shadows, gentle
// motion and a slow camera. Real, recognisable content, not abstract glass. Widgets are drawn
// to canvas textures (deterministic); software-GL safe (Standard materials only). Pure in t.

import React from 'react';
import { useThree } from '@react-three/fiber';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import * as THREE from 'three';
import type { SceneSpec } from '../spec';
import { hash01 } from '../lib/rng';

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const rr = (g, x, y, w, h, r) => { g.beginPath(); g.roundRect(x, y, w, h, r); };

// bright neutral studio env so the glossy cards catch soft highlights.
const studioEnv = () => {
  const W = 512, H = 256; const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, H); sky.addColorStop(0, '#ffffff'); sky.addColorStop(0.6, '#eef0f4'); sky.addColorStop(1, '#d8dce3');
  g.fillStyle = sky; g.fillRect(0, 0, W, H);
  const box = (x, w, a) => { const gr = g.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(0.5, `rgba(255,255,255,${a})`); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(x, 0, w, H); };
  box(W * 0.1, W * 0.14, 1); box(W * 0.62, W * 0.1, 0.85);
  const t = new THREE.CanvasTexture(c); t.mapping = THREE.EquirectangularReflectionMapping; t.colorSpace = THREE.SRGBColorSpace; return t;
};
const EnvRig = () => { const { scene } = useThree(); const tex = React.useMemo(() => studioEnv(), []); scene.environment = tex; scene.environmentIntensity = 1; return null; };

// ---- real widget faces drawn to canvas → {tex, aspect} ----
const WIDGETS = {
  calendar: () => {
    const W = 480, H = 600, c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
    g.fillStyle = '#0f1114'; rr(g, 0, 0, W, H, 60); g.fill();
    g.fillStyle = '#fff'; g.font = '800 32px system-ui'; g.textBaseline = 'top'; g.fillText('Daily Activity', 44, 50);
    g.fillStyle = '#22252c'; rr(g, 312, 42, 128, 48, 24); g.fill(); g.fillStyle = '#cfd3db'; g.font = '600 24px system-ui'; g.fillText('July 2025', 328, 54);
    const days = ['S', 'M', 'T', 'W', 'T', 'F', 'S']; g.fillStyle = '#6b7180'; g.font = '600 24px system-ui';
    const gx = 40, gw = (W - 80) / 7; days.forEach((d, i) => g.fillText(d, gx + i * gw + gw / 2 - 8, 130));
    g.font = '700 26px system-ui';
    for (let i = 0; i < 31; i++) { const col = i % 7, row = Math.floor(i / 7); const x = gx + col * gw + gw / 2, y = 190 + row * 66;
      const hot = [3, 4, 5, 6, 9, 15]; const on = hot.includes(i);
      if (on) { g.fillStyle = i === 6 ? '#ff8a3d' : '#3ad07a'; g.beginPath(); g.arc(x, y + 12, 22, 0, 7); g.fill(); g.fillStyle = '#06210f'; }
      else g.fillStyle = '#c7ccd6';
      g.textAlign = 'center'; g.fillText(String(i + 1), x, y); g.textAlign = 'left'; }
    return { c, aspect: W / H };
  },
  battery: () => {
    const S = 480, c = document.createElement('canvas'); c.width = c.height = S; const g = c.getContext('2d');
    g.fillStyle = '#fbfcfe'; rr(g, 0, 0, S, S, 60); g.fill();
    g.fillStyle = '#ff8a3d'; g.beginPath(); g.moveTo(70, 70); g.lineTo(96, 70); g.lineTo(84, 104); g.lineTo(110, 104); g.lineTo(74, 150); g.lineTo(86, 116); g.lineTo(64, 116); g.closePath(); g.fill();
    g.fillStyle = '#12151b'; g.font = '900 96px system-ui'; g.textBaseline = 'top'; g.fillText('57%', 130, 66);
    const bx = 70, bw = (S - 140) / 4 - 10; const hs = [120, 200, 150, 90];
    hs.forEach((h, i) => { g.fillStyle = i < 2 ? '#ff8a3d' : '#ffd3ad'; rr(g, bx + i * (bw + 13), 360 - h, bw, h, 18); g.fill(); });
    g.fillStyle = '#8a90a0'; g.font = '600 30px system-ui'; g.fillText('~ 2 hours', 70, 400);
    return { c, aspect: 1 };
  },
  clock: () => {
    const S = 480, c = document.createElement('canvas'); c.width = c.height = S; const g = c.getContext('2d');
    g.fillStyle = '#fbfcfe'; rr(g, 0, 0, S, S, 60); g.fill(); const cx = S / 2, cy = S / 2, R = 170;
    g.strokeStyle = '#e6e9ef'; g.lineWidth = 4; g.beginPath(); g.arc(cx, cy, R, 0, 7); g.stroke();
    g.fillStyle = '#12151b'; g.font = '700 34px serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    [['XII', 0], ['III', 90], ['VI', 180], ['IX', 270]].forEach(([n, a]) => { const rad = (a - 90) * Math.PI / 180; g.fillText(n, cx + Math.cos(rad) * (R - 34), cy + Math.sin(rad) * (R - 34)); });
    const hand = (ang, len, w, col) => { const rad = (ang - 90) * Math.PI / 180; g.strokeStyle = col; g.lineWidth = w; g.lineCap = 'round'; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(rad) * len, cy + Math.sin(rad) * len); g.stroke(); };
    hand(300, 90, 12, '#12151b'); hand(120, 130, 8, '#12151b'); hand(210, 150, 4, '#ff5647');
    g.fillStyle = '#12151b'; g.beginPath(); g.arc(cx, cy, 10, 0, 7); g.fill(); g.textAlign = 'left'; g.textBaseline = 'top';
    return { c, aspect: 1 };
  },
  activity: () => {
    const S = 480, c = document.createElement('canvas'); c.width = c.height = S; const g = c.getContext('2d');
    g.fillStyle = '#0f1114'; rr(g, 0, 0, S, S, 60); g.fill(); const cx = S / 2, cy = S / 2;
    const ring = (r, frac, col) => { g.strokeStyle = '#23262e'; g.lineWidth = 30; g.beginPath(); g.arc(cx, cy, r, 0, 7); g.stroke(); g.strokeStyle = col; g.lineCap = 'round'; g.beginPath(); g.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + frac * Math.PI * 2); g.stroke(); };
    ring(150, 0.78, '#ff2d55'); ring(110, 0.62, '#a8ff2d'); ring(70, 0.45, '#2dd0ff');
    g.fillStyle = '#fff'; g.font = '800 34px system-ui'; g.textBaseline = 'top'; g.fillText('Move', 44, 40);
    return { c, aspect: 1 };
  },
  appcard: (accent) => {
    const W = 480, H = 600, c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
    g.fillStyle = '#0f1114'; rr(g, 0, 0, W, H, 60); g.fill();
    const gr = g.createLinearGradient(48, 56, 168, 176); gr.addColorStop(0, accent); gr.addColorStop(1, '#111'); g.fillStyle = gr; rr(g, 48, 56, 120, 120, 30); g.fill();
    g.fillStyle = '#fff'; g.font = '800 30px system-ui'; g.textBaseline = 'top'; g.fillText('DouchkoVE', 190, 66);
    g.fillStyle = '#8a90a0'; g.font = '500 24px system-ui'; g.fillText('Productivity', 190, 108);
    g.fillStyle = accent; rr(g, 190, 150, 120, 46, 23); g.fill(); g.fillStyle = '#fff'; g.font = '800 24px system-ui'; g.fillText('Open', 218, 160);
    for (let i = 0; i < 3; i++) { const sg = g.createLinearGradient(48 + i * 140, 240, 48 + i * 140, 500); sg.addColorStop(0, `hsl(${i * 40 + 200},60%,55%)`); sg.addColorStop(1, `hsl(${i * 40 + 220},60%,42%)`); g.fillStyle = sg; rr(g, 48 + i * 140, 240, 120, 250, 22); g.fill(); }
    return { c, aspect: W / H };
  },
};
const widgetTex = (() => { const cache = {}; return (kind, accent) => { const k = kind + accent; if (cache[k]) return cache[k]; const { c, aspect } = WIDGETS[kind](accent); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; cache[k] = { tex: t, aspect }; return cache[k]; }; })();

const shadowTex = (() => { let t = null; return () => { if (t) return t; const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d'); const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, 'rgba(0,0,0,0.5)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); t = new THREE.CanvasTexture(c); return t; }; })();

/** A premium floating widget card: glossy tile with the widget face, thin edge, soft shadow. */
const WidgetCard = ({ kind, accent, pos, baseScale, rotY, t, phase, delay }) => {
  const { tex, aspect } = React.useMemo(() => widgetTex(kind, accent), [kind, accent]);
  const spring = clamp01(easeInOut(clamp01((t - delay) / 1.1)));
  const H = 2.7, W = H * aspect;
  const y = pos[1] + Math.sin(t * 0.5 + phase) * 0.12;
  const z = pos[2] + (1 - spring) * -6;
  const tilt = Math.sin(t * 0.32 + phase) * 0.05;
  return (
    <group position={[pos[0], y, z]} rotation={[tilt * 0.6, rotY + tilt, tilt * 0.3]} scale={baseScale * (0.75 + 0.25 * spring)}>
      <mesh position={[0, -H * 0.6, 0.1]} rotation={[-Math.PI / 2.1, 0, 0]}>
        <planeGeometry args={[W * 2, W * 1.4]} />
        <meshBasicMaterial map={shadowTex()} transparent opacity={0.5 * spring} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0, -0.05]}>
        <boxGeometry args={[W * 1.005, H * 1.005, 0.1]} />
        <meshStandardMaterial color="#0a0b0e" metalness={0.5} roughness={0.35} envMapIntensity={0.6} transparent opacity={spring} />
      </mesh>
      <mesh position={[0, 0, 0.051]}>
        <planeGeometry args={[W, H]} />
        <meshStandardMaterial map={tex} emissiveMap={tex} emissive={'#ffffff'} emissiveIntensity={0.18}
          roughness={0.26} metalness={0.0} envMapIntensity={0.5} transparent opacity={clamp01(spring * 1.4)} />
      </mesh>
    </group>
  );
};

const CameraRig = ({ t }) => {
  const { camera } = useThree();
  const d = easeInOut(clamp01(t / 2.6));
  const z = 10 - 2.6 * d - Math.sin(t * 0.12) * 0.3;
  camera.position.set(Math.sin(t * 0.13) * 1.1, 0.3 + Math.cos(t * 0.1) * 0.35, z);
  camera.lookAt(0, 0.05, 0);
  camera.updateProjectionMatrix();
  return null;
};

export const Scene3D: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const accent = spec.palette.accent;
  return (
    <>
      <CameraRig t={t} />
      <EnvRig />
      <ambientLight intensity={0.7} />
      <directionalLight position={[4, 6, 6]} intensity={2.4} color="#ffffff" />
      <directionalLight position={[-5, 1, 3]} intensity={1} color="#dfe6ff" />

      {/* hero widget centre-front, supporting widgets fanned into depth */}
      <WidgetCard kind="calendar" accent={accent} pos={[0, 0.1, 0.6]} baseScale={1.0} rotY={0} t={t} phase={0} delay={0.1} />
      <WidgetCard kind="battery" accent={accent} pos={[-3.1, 1.1, -1.2]} baseScale={0.72} rotY={0.5} t={t} phase={1.3} delay={0.35} />
      <WidgetCard kind="clock" accent={accent} pos={[3.2, -1.3, -1.4]} baseScale={0.72} rotY={-0.5} t={t} phase={2.6} delay={0.5} />
      <WidgetCard kind="activity" accent={accent} pos={[-2.7, -1.7, -2.4]} baseScale={0.62} rotY={0.42} t={t} phase={3.7} delay={0.65} />
      <WidgetCard kind="appcard" accent={accent} pos={[3.0, 1.7, -2.8]} baseScale={0.6} rotY={-0.42} t={t} phase={4.6} delay={0.8} />

      <fog attach="fog" args={['#eef0f4', 9, 20]} />
    </>
  );
};
