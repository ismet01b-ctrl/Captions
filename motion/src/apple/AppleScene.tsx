// AppleScene — the iOS-style UI-mockup templates (light theme), the look the reference
// clips use. Renders six mockups from the spec's `ui` payload: embossed pills, an app
// download card, a search field, a home-screen app grid, chat bubbles, a notification
// banner. Pure in t (Remotion-seekable), no emoji (all vector) so it renders headless.

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec, UiSpec } from '../spec';
import { entrancePose, idleFloat, blurCss } from '../lib/motion';
import { springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';
import { FONT_FAMILY } from '../fonts';

const FONT = `'${FONT_FAMILY}', system-ui, -apple-system, sans-serif`;
const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

/** Light field background shared by every mockup. */
const Field: React.FC<{ children: React.ReactNode; wallpaper?: boolean }> = ({ children, wallpaper }) => (
  <AbsoluteFill style={{ fontFamily: FONT }}>
    <AbsoluteFill style={{
      background: wallpaper
        ? 'linear-gradient(160deg, #cfe0ff 0%, #eaf0fb 40%, #f4ecff 100%)'
        : 'radial-gradient(120% 90% at 50% 16%, #ffffff 0%, #eef2f9 46%, #dbe4f3 100%)',
    }} />
    {children}
  </AbsoluteFill>
);

const softCard = (u: number): React.CSSProperties => ({
  background: 'linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%)',
  borderRadius: u * 0.05,
  boxShadow: `0 ${u * 0.03}px ${u * 0.07}px rgba(30,50,90,0.16), 0 ${u * 0.008}px ${u * 0.02}px rgba(30,50,90,0.1)`,
  border: '1px solid rgba(255,255,255,0.9)',
});

const Stars: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size * 5.6} height={size} viewBox="0 0 56 10">
    {[0, 1, 2, 3, 4].map((i) => (
      <path key={i} transform={`translate(${i * 11.5} 0)`}
        d="M5,0 6.5,3.2 10,3.6 7.3,6 8,9.5 5,7.7 2,9.5 2.7,6 0,3.6 3.5,3.2 Z" fill={color} />
    ))}
  </svg>
);

/** rounded-square app icon with a simple vector glyph, colour from seed. */
const AppIcon: React.FC<{ size: number; hue: number; glyph?: number; badge?: number; radius?: number }>
  = ({ size, hue, glyph = 0, badge, radius }) => {
    const c1 = `hsl(${hue}, 78%, 58%)`;
    const c2 = `hsl(${(hue + 24) % 360}, 82%, 46%)`;
    const r = radius ?? size * 0.24;
    return (
      <div style={{ position: 'relative', width: size, height: size }}>
        <div style={{
          width: size, height: size, borderRadius: r,
          background: `linear-gradient(150deg, ${c1}, ${c2})`,
          boxShadow: `0 ${size * 0.06}px ${size * 0.16}px rgba(20,40,80,0.22), inset 0 1px 1px rgba(255,255,255,0.5)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none"
            stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
            {glyph % 4 === 0 && <><circle cx="12" cy="12" r="7" /><path d="M12 8v8M8 12h8" /></>}
            {glyph % 4 === 1 && <rect x="5" y="5" width="14" height="14" rx="3" />}
            {glyph % 4 === 2 && <path d="M4 15l5-6 4 4 7-8" />}
            {glyph % 4 === 3 && <><circle cx="12" cy="12" r="8" /><path d="M12 4v8l5 3" /></>}
          </svg>
        </div>
        {badge != null && (
          <div style={{ position: 'absolute', top: -size * 0.08, right: -size * 0.08,
            minWidth: size * 0.34, height: size * 0.34, padding: `0 ${size * 0.06}px`,
            borderRadius: size * 0.2, background: '#ff3b30', color: '#fff', fontWeight: 800,
            fontSize: size * 0.22, display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 6px rgba(0,0,0,0.25)' }}>{badge}</div>
        )}
      </div>
    );
  };

// ---------------------------------------------------------------- individual mockups

const Pills: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number }>
  = ({ ui, t, W, H, seed }) => {
    const u = Math.min(W, H);
    const items = (ui.lines.length ? ui.lines : ['Write', 'Create', 'Solve']).slice(0, 5);
    const fs = Math.round(u * 0.062);
    const sparks = Array.from({ length: 6 }, (_, i) => {
      const sx = (0.14 + hash01(i, seed) * 0.72) * W;
      const sy = (0.16 + hash01(i, seed + 9) * 0.6) * H;
      const pop = springStep(t - (0.2 + hash01(i, seed + 5) * 0.8), { stiffness: 140, damping: 0.5, delay: 0 });
      return { key: i, x: sx + idleFloat(t, i * 1.7, u * 0.02), y: sy + idleFloat(t, i * 2.3 + 1, u * 0.02),
        s: u * (0.012 + hash01(i, seed + 3) * 0.02) * clamp01(pop) / 10,
        c: i % 2 ? '#ffb020' : ui.accent, rot: t * 40 * (i % 2 ? 1 : -1), o: clamp01(pop) * 0.85 };
    });
    return (
      <>
        <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} style={{ position: 'absolute', inset: 0 }}>
          {sparks.map((s) => (
            <g key={s.key} transform={`translate(${s.x} ${s.y}) rotate(${s.rot}) scale(${s.s})`} opacity={s.o}>
              <path d="M0,-10 C1.5,-3 3,-1.5 10,0 C3,1.5 1.5,3 0,10 C-1.5,3 -3,1.5 -10,0 C-3,-1.5 -1.5,-3 0,-10 Z" fill={s.c} />
            </g>
          ))}
        </svg>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: u * 0.03, alignItems: 'center', justifyContent: 'center', width: '82%' }}>
            {items.map((it, i) => {
              const stagger = ((i * 3) % Math.max(items.length, 1)) * 0.11;
              const pose = entrancePose(t - 0.1, { stiffness: 150, damping: 0.55, delay: stagger }, u * 0.05);
              const float = idleFloat(t, i * 1.9, u * 0.006) * pose.alpha;
              return (
                <div key={i} style={{
                  opacity: pose.alpha,
                  transform: `translate3d(0, ${(pose.ty + float).toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`,
                  filter: blurCss(pose.blur), padding: `${fs * 0.42}px ${fs * 0.9}px`, borderRadius: fs * 1.1,
                  background: 'linear-gradient(180deg, #ffffff 0%, #f3f5fa 100%)', color: '#0f1420', fontSize: fs, fontWeight: 800,
                  boxShadow: `0 ${fs * 0.5}px ${fs * 1.1}px rgba(30,50,90,0.18), inset 0 2px 1px rgba(255,255,255,0.9), inset 0 -2px 2px rgba(20,40,80,0.06)`,
                  whiteSpace: 'nowrap', willChange: 'transform, opacity, filter',
                }}>{it}</div>
              );
            })}
          </div>
        </AbsoluteFill>
      </>
    );
  };

const AppCard: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const pose = entrancePose(t, { stiffness: 140, damping: 0.6, delay: 0 }, u * 0.05);
  const openPulse = 1 + 0.05 * Math.max(0, Math.sin((t - 0.6) * 4));
  const statReveal = (i: number) => clamp01((t - 0.7 - i * 0.14) / 0.35);
  const iconSz = u * 0.165;
  const title = ui.title || 'DouchkoVE';
  const sub = ui.subtitle || 'Productivity';
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        width: '80%', padding: u * 0.05, ...softCard(u), opacity: pose.alpha,
        transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur),
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.04 }}>
          <AppIcon size={iconSz} hue={(Number(ui.accent.replace('#', '0x')) >> 8) % 360 || 220} glyph={0} radius={iconSz * 0.26} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: u * 0.046, fontWeight: 800, color: '#0f1420', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
            <div style={{ fontSize: u * 0.028, color: '#8a90a0', marginTop: u * 0.008 }}>{sub}</div>
          </div>
          <div style={{
            padding: `${u * 0.015}px ${u * 0.042}px`, borderRadius: 999, background: ui.accent, color: '#fff',
            fontWeight: 800, fontSize: u * 0.03, transform: `scale(${openPulse.toFixed(3)})`,
            boxShadow: `0 ${u * 0.012}px ${u * 0.03}px ${ui.accent}66`,
          }}>Open</div>
        </div>
        <div style={{ height: 1, background: '#eceef3', margin: `${u * 0.045}px 0` }} />
        <div style={{ display: 'flex', textAlign: 'center' }}>
          {[
            { big: '4.8', star: true, lab: 'RATINGS' },
            { big: '12+', lab: 'AGE' },
            { big: '#1', lab: sub.slice(0, 12).toUpperCase() || 'TOP' },
          ].map((s, i) => (
            <div key={i} style={{ flex: 1, opacity: statReveal(i), transform: `translateY(${(1 - statReveal(i)) * u * 0.02}px)` }}>
              <div style={{ fontSize: u * 0.036, fontWeight: 800, color: '#0f1420', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u * 0.008 }}>
                {s.big}
                {s.star && <Stars size={u * 0.014} color="#b7bdca" />}
              </div>
              <div style={{ fontSize: u * 0.02, color: '#a2a8b6', fontWeight: 700, letterSpacing: '0.06em', marginTop: u * 0.01 }}>{s.lab}</div>
              {i < 2 && <div style={{ position: 'absolute' }} />}
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Search: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const pose = entrancePose(t, { stiffness: 150, damping: 0.6, delay: 0 }, u * 0.04);
  const query = ui.title || 'Ask anything';
  const shown = Math.max(0, Math.floor((t - 0.5) / 0.055));
  const typed = query.slice(0, shown);
  const done = shown >= query.length;
  const cursorOn = Math.floor(t * 2) % 2 === 0;
  const fs = u * 0.04;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        width: '82%', display: 'flex', alignItems: 'center', gap: u * 0.025,
        padding: `${u * 0.03}px ${u * 0.04}px`, borderRadius: 999, background: '#eef1f6',
        boxShadow: 'inset 0 1px 3px rgba(20,40,80,0.08)', opacity: pose.alpha,
        transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur),
      }}>
        <svg width={fs} height={fs} viewBox="0 0 24 24" fill="none" stroke="#8a90a0" strokeWidth={2.4} strokeLinecap="round">
          <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
        </svg>
        <div style={{ flex: 1, fontSize: fs, color: typed ? '#0f1420' : '#9aa0ae', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden' }}>
          {typed || 'Ask anything'}
          {!done && cursorOn ? <span style={{ color: ui.accent }}>|</span> : null}
        </div>
        {/* mic + waveform */}
        <svg width={fs * 3} height={fs} viewBox="0 0 60 24">
          {[0, 1, 2, 3, 4].map((i) => {
            const hgt = 6 + 9 * (0.5 + 0.5 * Math.sin(t * 6 + i));
            return <rect key={i} x={12 + i * 9} y={12 - hgt / 2} width={4} height={hgt} rx={2} fill={ui.accent} />;
          })}
        </svg>
      </div>
    </AbsoluteFill>
  );
};

const HomeScreen: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number }> = ({ ui, t, W, H, seed }) => {
  const cols = 4, rows = 5;
  const gap = W * 0.05;
  const size = (W * 0.78 - gap * (cols - 1)) / cols;
  const startX = W * 0.11;
  const startY = H * 0.16;
  const badgeIdx = 6;
  return (
    <>
      {Array.from({ length: cols * rows }, (_, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        const x = startX + c * (size + gap);
        const y = startY + r * (size + gap * 1.3);
        const stagger = (hash01(i, seed) * 0.5) + i * 0.03;
        const pose = entrancePose(t - stagger, { stiffness: 170, damping: 0.55, delay: 0 }, H * 0.02);
        const hue = Math.floor(hash01(i, seed + 2) * 360);
        return (
          <div key={i} style={{ position: 'absolute', left: x, top: y, opacity: pose.alpha,
            transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
            <AppIcon size={size} hue={hue} glyph={i} radius={size * 0.24} {...(i === badgeIdx ? { badge: 3 } : {})} />
          </div>
        );
      })}
    </>
  );
};

const Chat: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const msgs = (ui.lines.length ? ui.lines : ['Hey!', 'The new drop is live', 'Check it now']).slice(0, 4);
  const fs = u * 0.04;
  const each = 1.0;
  return (
    <AbsoluteFill style={{ flexDirection: 'column', justifyContent: 'center', gap: u * 0.03, padding: '0 8%' }}>
      {msgs.map((m, i) => {
        const out = i % 2 === 1;
        const pose = entrancePose(t - (0.4 + i * each), { stiffness: 160, damping: 0.6, delay: 0 }, u * 0.05);
        return (
          <div key={i} style={{ display: 'flex', justifyContent: out ? 'flex-end' : 'flex-start',
            opacity: pose.alpha, transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
            <div style={{
              maxWidth: '74%', padding: `${fs * 0.55}px ${fs * 0.85}px`, borderRadius: fs * 1.3,
              borderBottomRightRadius: out ? fs * 0.3 : fs * 1.3, borderBottomLeftRadius: out ? fs * 1.3 : fs * 0.3,
              background: out ? ui.accent : '#e9ebf0', color: out ? '#fff' : '#0f1420', fontSize: fs, fontWeight: 600,
              boxShadow: '0 6px 16px rgba(30,50,90,0.12)',
            }}>{m}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Notify: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const title = ui.title || 'DouchkoVE';
  const body = ui.lines[1] || ui.subtitle || 'Your clip is ready to share.';
  const drop = springStep(t - 0.25, { stiffness: 130, damping: 0.62, delay: 0 });
  const y = -u * 0.4 * (1 - Math.min(1, drop));
  const iconSz = u * 0.09;
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-start', paddingTop: H * 0.14 }} >
      <div style={{
        width: '84%', display: 'flex', alignItems: 'center', gap: u * 0.03, padding: u * 0.035,
        ...softCard(u), transform: `translateY(${y.toFixed(1)}px)`, opacity: Math.min(1, drop * 1.5),
      }}>
        <AppIcon size={iconSz} hue={(Number(ui.accent.replace('#', '0x')) >> 8) % 360 || 220} glyph={0} radius={iconSz * 0.28} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: u * 0.036, fontWeight: 800, color: '#0f1420' }}>{title}</div>
          <div style={{ fontSize: u * 0.03, color: '#5b6270', marginTop: u * 0.006 }}>{body}</div>
        </div>
        <div style={{ fontSize: u * 0.024, color: '#a2a8b6', fontWeight: 600, alignSelf: 'flex-start' }}>now</div>
      </div>
    </AbsoluteFill>
  );
};

export const AppleScene: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const ui: UiSpec = spec.ui ?? { template: 'pills', lines: ['Write', 'Create', 'Solve'], accent: spec.palette.accent };
  const wallpaper = ui.template === 'homescreen' || ui.template === 'notify';

  return (
    <Field wallpaper={wallpaper}>
      {ui.template === 'pills' && <Pills ui={ui} t={t} W={width} H={height} seed={spec.seed} />}
      {ui.template === 'appcard' && <AppCard ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'search' && <Search ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'homescreen' && <HomeScreen ui={ui} t={t} W={width} H={height} seed={spec.seed} />}
      {ui.template === 'chat' && <Chat ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'notify' && <Notify ui={ui} t={t} W={width} H={height} />}
    </Field>
  );
};
