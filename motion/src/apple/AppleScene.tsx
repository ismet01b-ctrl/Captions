// AppleScene — the iOS-style UI-mockup templates (light theme), detailed enough to read as
// a real device screen: a status bar, dock, chat nav + input + receipts, an app-store card
// with a screenshot strip, a search suggestions list, a lock-screen notification. Six
// templates driven by the spec's `ui` payload. Pure in t, all vector (no emoji) so it
// renders headless.

import React from 'react';
import { AbsoluteFill, Img, continueRender, delayRender, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec, UiSpec } from '../spec';
import { entrancePose, idleFloat, blurCss } from '../lib/motion';
import { springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';
import { FONT_FAMILY } from '../fonts';

const FONT = `'${FONT_FAMILY}', system-ui, -apple-system, sans-serif`;

// Pillar 2: load a user-supplied font (data URI) once, blocking the render until it is
// ready (same delayRender discipline as the bundled Inter). Idempotent per url.
const loadedUserFonts = new Set<string>();
function ensureUserFont(font?: { family: string; url: string }): void {
  if (!font || typeof document === 'undefined' || loadedUserFonts.has(font.url)) return;
  loadedUserFonts.add(font.url);
  const handle = delayRender('Loading user font');
  const done = (): void => continueRender(handle);
  try {
    new FontFace(font.family, `url(${font.url})`, { display: 'block' })
      .load().then((f) => { document.fonts.add(f); done(); }).catch(done);
  } catch { done(); }
}
const fontStack = (spec: SceneSpec): string => (spec.font ? `'${spec.font.family}', ${FONT}` : FONT);
const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);
const INK = '#0f1420';
const GRAY = '#8a90a0';

// -------------------------------------------------------------------- chrome & primitives

const StatusBar: React.FC<{ W: number; u: number; color?: string }> = ({ W, u, color = INK }) => {
  const fs = u * 0.03;
  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: W, height: u * 0.06,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: `0 ${u * 0.06}px`, color, fontWeight: 700, fontSize: fs }}>
      <div style={{ letterSpacing: '0.02em' }}>9:41</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.014 }}>
        {/* signal */}
        <svg width={fs * 1.1} height={fs} viewBox="0 0 18 12">
          {[0, 1, 2, 3].map((i) => (
            <rect key={i} x={i * 4.5} y={12 - (4 + i * 2.6)} width={3} height={4 + i * 2.6} rx={0.8} fill={color} />
          ))}
        </svg>
        {/* wifi */}
        <svg width={fs * 1.1} height={fs} viewBox="0 0 16 12" fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round">
          <path d="M1 4a10 10 0 0 1 14 0M3.5 6.5a6.4 6.4 0 0 1 9 0" />
          <circle cx="8" cy="9.5" r="0.9" fill={color} stroke="none" />
        </svg>
        {/* battery */}
        <svg width={fs * 1.7} height={fs} viewBox="0 0 26 12">
          <rect x="0.5" y="1" width="22" height="10" rx="2.6" fill="none" stroke={color} strokeOpacity="0.5" />
          <rect x="2" y="2.5" width="16" height="7" rx="1.4" fill={color} />
          <rect x="24" y="4" width="1.8" height="4" rx="0.9" fill={color} fillOpacity="0.5" />
        </svg>
      </div>
    </div>
  );
};

const Field: React.FC<{ children: React.ReactNode; wallpaper?: boolean; font?: string }> = ({ children, wallpaper, font }) => (
  <AbsoluteFill style={{ fontFamily: font ?? FONT }}>
    <AbsoluteFill style={{
      background: wallpaper
        ? 'linear-gradient(160deg, #b9d0ff 0%, #e7ecfb 42%, #f3e9ff 100%)'
        : 'radial-gradient(120% 90% at 50% 16%, #ffffff 0%, #eef2f9 46%, #dbe4f3 100%)',
    }} />
    {children}
  </AbsoluteFill>
);

const softCard = (u: number, strong = false): React.CSSProperties => ({
  background: 'linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%)',
  borderRadius: u * 0.05,
  boxShadow: strong
    ? `0 ${u * 0.04}px ${u * 0.1}px rgba(20,40,80,0.22), 0 ${u * 0.01}px ${u * 0.02}px rgba(20,40,80,0.12)`
    : `0 ${u * 0.03}px ${u * 0.07}px rgba(30,50,90,0.16), 0 ${u * 0.008}px ${u * 0.02}px rgba(30,50,90,0.1)`,
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

const hueFromAccent = (accent: string): number => {
  const m = /^#([0-9a-f]{6})$/i.exec(accent);
  if (!m) return 220;
  const n = parseInt(m[1]!, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min || 1;
  let h = 0;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return ((h * 60) + 360) % 360;
};

const AppIcon: React.FC<{ size: number; hue: number; glyph?: number; badge?: number; radius?: number; logo?: string }>
  = ({ size, hue, glyph = 0, badge, radius, logo }) => {
    const c1 = `hsl(${hue}, 78%, 58%)`;
    const c2 = `hsl(${(hue + 24) % 360}, 82%, 46%)`;
    const r = radius ?? size * 0.24;
    return (
      <div style={{ position: 'relative', width: size, height: size }}>
        <div style={{ width: size, height: size, borderRadius: r, overflow: 'hidden',
          background: logo ? '#fff' : `linear-gradient(150deg, ${c1}, ${c2})`,
          boxShadow: `0 ${size * 0.06}px ${size * 0.16}px rgba(20,40,80,0.22), inset 0 1px 1px rgba(255,255,255,0.5)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {logo ? (
            <Img src={logo} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none" stroke="#fff"
              strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
              {glyph % 5 === 0 && <><circle cx="12" cy="12" r="7" /><path d="M12 8v8M8 12h8" /></>}
              {glyph % 5 === 1 && <rect x="5" y="5" width="14" height="14" rx="3" />}
              {glyph % 5 === 2 && <path d="M4 15l5-6 4 4 7-8" />}
              {glyph % 5 === 3 && <><circle cx="12" cy="12" r="8" /><path d="M12 4v8l5 3" /></>}
              {glyph % 5 === 4 && <path d="M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z" />}
            </svg>
          )}
        </div>
        {badge != null && (
          <div style={{ position: 'absolute', top: -size * 0.08, right: -size * 0.08,
            minWidth: size * 0.34, height: size * 0.34, padding: `0 ${size * 0.06}px`, borderRadius: size * 0.2,
            background: '#ff3b30', color: '#fff', fontWeight: 800, fontSize: size * 0.22,
            display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.25)' }}>{badge}</div>
        )}
      </div>
    );
  };

// -------------------------------------------------------------------- templates

const Pills: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number }> = ({ ui, t, W, H, seed }) => {
  const u = Math.min(W, H);
  const items = (ui.lines.length ? ui.lines : ['Write', 'Create', 'Solve']).slice(0, 5);
  const fs = Math.round(u * 0.062);
  const sparks = Array.from({ length: 7 }, (_, i) => {
    const pop = springStep(t - (0.2 + hash01(i, seed + 5) * 0.8), { stiffness: 140, damping: 0.5, delay: 0 });
    return { key: i,
      x: (0.14 + hash01(i, seed) * 0.72) * W + idleFloat(t, i * 1.7, u * 0.02),
      y: (0.16 + hash01(i, seed + 9) * 0.62) * H + idleFloat(t, i * 2.3 + 1, u * 0.02),
      s: u * (0.012 + hash01(i, seed + 3) * 0.02) * clamp01(pop) / 10,
      c: i % 2 ? '#ffb020' : ui.accent, rot: t * 40 * (i % 2 ? 1 : -1), o: clamp01(pop) * 0.85 };
  });
  return (
    <>
      {/* soft colour glow for depth */}
      <div style={{ position: 'absolute', left: '50%', top: '44%', width: u * 0.9, height: u * 0.9,
        transform: 'translate(-50%,-50%)', borderRadius: '50%', filter: 'blur(60px)',
        background: `radial-gradient(circle, ${ui.accent}22, transparent 70%)` }} />
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
              <div key={i} style={{ opacity: pose.alpha,
                transform: `translate3d(0, ${(pose.ty + float).toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`,
                filter: blurCss(pose.blur), padding: `${fs * 0.42}px ${fs * 0.9}px`, borderRadius: fs * 1.1,
                background: 'linear-gradient(180deg, #ffffff 0%, #f3f5fa 100%)', color: INK, fontSize: fs, fontWeight: 800,
                boxShadow: `0 ${fs * 0.5}px ${fs * 1.1}px rgba(30,50,90,0.18), inset 0 2px 1px rgba(255,255,255,0.9), inset 0 -2px 2px rgba(20,40,80,0.06)`,
                whiteSpace: 'nowrap', willChange: 'transform, opacity, filter' }}>{it}</div>
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
  const rev = (i: number, d = 0.14) => clamp01((t - 0.7 - i * d) / 0.35);
  const iconSz = u * 0.17;
  const title = ui.title || 'DouchkoVE';
  const sub = ui.subtitle || 'Productivity';
  const hue = hueFromAccent(ui.accent);
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: '82%', padding: u * 0.05, ...softCard(u, true), opacity: pose.alpha,
        transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.035 }}>
          <AppIcon size={iconSz} hue={hue} glyph={0} radius={iconSz * 0.26} {...(ui.logo ? { logo: ui.logo } : {})} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: u * 0.044, fontWeight: 800, color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
            <div style={{ fontSize: u * 0.027, color: GRAY, marginTop: u * 0.006 }}>{sub}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.012, marginTop: u * 0.012 }}>
              <Stars size={u * 0.014} color="#f5a623" />
              <span style={{ fontSize: u * 0.022, color: GRAY, fontWeight: 700 }}>289K</span>
            </div>
          </div>
          <div style={{ padding: `${u * 0.015}px ${u * 0.045}px`, borderRadius: 999, background: ui.accent, color: '#fff',
            fontWeight: 800, fontSize: u * 0.03, transform: `scale(${openPulse.toFixed(3)})`,
            boxShadow: `0 ${u * 0.012}px ${u * 0.03}px ${ui.accent}66` }}>Open</div>
        </div>
        {/* screenshot strip */}
        <div style={{ display: 'flex', gap: u * 0.025, marginTop: u * 0.04 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ flex: 1, aspectRatio: '9 / 16', borderRadius: u * 0.03,
              background: `linear-gradient(150deg, hsl(${(hue + i * 30) % 360},70%,72%), hsl(${(hue + i * 30 + 30) % 360},70%,58%))`,
              boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.05)', opacity: rev(i + 1, 0.12),
              transform: `translateY(${(1 - rev(i + 1, 0.12)) * u * 0.03}px)` }}>
              <div style={{ height: '22%', margin: '10% 12% 0', borderRadius: u * 0.02, background: 'rgba(255,255,255,0.55)' }} />
              <div style={{ height: '6%', margin: '8% 20% 0', borderRadius: 999, background: 'rgba(255,255,255,0.5)' }} />
              <div style={{ height: '6%', margin: '6% 28% 0', borderRadius: 999, background: 'rgba(255,255,255,0.4)' }} />
            </div>
          ))}
        </div>
        <div style={{ height: 1, background: '#eceef3', margin: `${u * 0.04}px 0` }} />
        <div style={{ display: 'flex', textAlign: 'center' }}>
          {[{ big: '4.8', star: true, lab: 'RATINGS' }, { big: '12+', lab: 'AGE' }, { big: '#1', lab: (sub.slice(0, 12).toUpperCase() || 'TOP') }].map((s, i) => (
            <div key={i} style={{ flex: 1, opacity: rev(i + 3), transform: `translateY(${(1 - rev(i + 3)) * u * 0.02}px)`,
              borderLeft: i ? '1px solid #eceef3' : 'none' }}>
              <div style={{ fontSize: u * 0.034, fontWeight: 800, color: INK, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u * 0.006 }}>
                {s.big}{s.star && <Stars size={u * 0.012} color="#b7bdca" />}
              </div>
              <div style={{ fontSize: u * 0.019, color: '#a2a8b6', fontWeight: 700, letterSpacing: '0.06em', marginTop: u * 0.008 }}>{s.lab}</div>
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
  const fs = u * 0.038;
  const suggestions = [query, `${query} fast`, `${query} for creators`, `best ${query.toLowerCase()}`].slice(0, 4);
  return (
    <>
      <StatusBar W={W} u={u} />
      <div style={{ position: 'absolute', top: u * 0.1, left: '9%', width: '82%' }}>
        <div style={{ fontSize: u * 0.05, fontWeight: 800, color: INK, marginBottom: u * 0.03 }}>Search</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.022, padding: `${u * 0.026}px ${u * 0.035}px`,
          borderRadius: u * 0.035, background: '#eef1f6', boxShadow: 'inset 0 1px 3px rgba(20,40,80,0.08)',
          opacity: pose.alpha, transform: `translateY(${pose.ty.toFixed(1)}px) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
          <svg width={fs} height={fs} viewBox="0 0 24 24" fill="none" stroke={GRAY} strokeWidth={2.4} strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
          </svg>
          <div style={{ flex: 1, fontSize: fs, color: typed ? INK : '#9aa0ae', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden' }}>
            {typed || 'Ask anything'}{!done && cursorOn ? <span style={{ color: ui.accent }}>|</span> : null}
          </div>
          <svg width={fs * 3} height={fs} viewBox="0 0 60 24">
            {[0, 1, 2, 3, 4].map((i) => { const h = 6 + 9 * (0.5 + 0.5 * Math.sin(t * 6 + i));
              return <rect key={i} x={12 + i * 9} y={12 - h / 2} width={4} height={h} rx={2} fill={ui.accent} />; })}
          </svg>
        </div>
        {/* suggestions dropdown */}
        <div style={{ marginTop: u * 0.02 }}>
          {suggestions.map((s, i) => {
            const rv = clamp01((t - 0.9 - i * 0.12) / 0.3);
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: u * 0.025,
                padding: `${u * 0.022}px ${u * 0.01}px`, borderBottom: '1px solid #e8ebf1',
                opacity: rv, transform: `translateX(${(1 - rv) * u * 0.03}px)` }}>
                <svg width={fs * 0.9} height={fs * 0.9} viewBox="0 0 24 24" fill="none" stroke="#b3b8c4" strokeWidth={2.2} strokeLinecap="round">
                  <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
                </svg>
                <span style={{ fontSize: u * 0.032, color: '#3a3f4b' }}>{s}</span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

const HomeScreen: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number }> = ({ ui, t, W, H, seed }) => {
  const u = Math.min(W, H);
  const cols = 4, rows = 4;
  const gap = W * 0.055;
  const size = (W * 0.78 - gap * (cols - 1)) / cols;
  const startX = W * 0.11, startY = H * 0.14;
  const labels = ['Notes', 'Photos', 'Health', 'Clock', 'Store', 'Maps', 'Mail', 'Music', 'News', 'Wallet', 'Files', 'Home', 'Books', 'Cam', 'Docs', 'Chat'];
  const Icon = (i: number, x: number, y: number, badge?: number) => {
    const stagger = (hash01(i, seed) * 0.4) + i * 0.03;
    const pose = entrancePose(t - stagger, { stiffness: 170, damping: 0.55, delay: 0 }, H * 0.02);
    return (
      <div key={`${x}-${y}`} style={{ position: 'absolute', left: x, top: y, width: size, textAlign: 'center',
        opacity: pose.alpha, transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
        <AppIcon size={size} hue={Math.floor(hash01(i, seed + 2) * 360)} glyph={i} radius={size * 0.24}
          {...(badge != null ? { badge } : {})} {...(i === 0 && ui.logo ? { logo: ui.logo } : {})} />
        <div style={{ marginTop: size * 0.1, fontSize: size * 0.17, color: '#243', fontWeight: 600, textShadow: '0 1px 2px rgba(255,255,255,0.6)' }}>{labels[i % labels.length]}</div>
      </div>
    );
  };
  return (
    <>
      <StatusBar W={W} u={u} />
      {Array.from({ length: cols * rows }, (_, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        return Icon(i, startX + c * (size + gap), startY + r * (size + gap * 1.5), i === 6 ? 3 : undefined);
      })}
      {/* page dots */}
      <div style={{ position: 'absolute', bottom: H * 0.165, left: 0, width: W, display: 'flex', justifyContent: 'center', gap: u * 0.02 }}>
        {[0, 1, 2].map((i) => <div key={i} style={{ width: u * 0.014, height: u * 0.014, borderRadius: '50%', background: i === 0 ? '#334' : 'rgba(40,50,70,0.35)' }} />)}
      </div>
      {/* dock */}
      <div style={{ position: 'absolute', bottom: H * 0.04, left: '6%', width: '88%', height: u * 0.2,
        borderRadius: u * 0.06, background: 'rgba(255,255,255,0.45)', backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'space-around', padding: `0 ${u * 0.04}px` }}>
        {[0, 1, 2, 3].map((i) => {
          const pose = entrancePose(t - 0.5 - i * 0.06, { stiffness: 170, damping: 0.55, delay: 0 }, H * 0.02);
          return <div key={i} style={{ opacity: pose.alpha, transform: `scale(${pose.scale.toFixed(3)})` }}>
            <AppIcon size={u * 0.135} hue={(i * 70 + 200) % 360} glyph={i + 1} radius={u * 0.032} />
          </div>;
        })}
      </div>
    </>
  );
};

const Chat: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const msgs = (ui.lines.length ? ui.lines : ['Hey!', 'The new drop is live', 'Check it now']).slice(0, 4);
  const fs = u * 0.038;
  const name = ui.title && ui.title.length < 22 ? ui.title : 'Messages';
  const each = 0.95;
  const lastOutIdx = msgs.reduce((a, _m, i) => (i % 2 === 1 ? i : a), -1);
  return (
    <AbsoluteFill>
      {/* nav bar */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: W, height: u * 0.17,
        background: 'rgba(248,249,252,0.9)', backdropFilter: 'blur(20px)', borderBottom: '1px solid #e6e9f0',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', paddingBottom: u * 0.02 }}>
        <div style={{ width: u * 0.11, height: u * 0.11, borderRadius: '50%', overflow: 'hidden',
          background: ui.logo ? '#fff' : `linear-gradient(150deg, hsl(${hueFromAccent(ui.accent)},70%,60%), hsl(${hueFromAccent(ui.accent) + 30},70%,50%))`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: u * 0.045 }}>
          {ui.logo ? <Img src={ui.logo} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : name.slice(0, 1).toUpperCase()}
        </div>
        <div style={{ fontSize: u * 0.028, fontWeight: 700, color: INK, marginTop: u * 0.008 }}>{name}</div>
        <svg style={{ position: 'absolute', left: u * 0.05, bottom: u * 0.05 }} width={u * 0.04} height={u * 0.04} viewBox="0 0 24 24" fill="none" stroke={ui.accent} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round"><path d="M15 5l-7 7 7 7" /></svg>
      </div>
      <div style={{ position: 'absolute', top: u * 0.19, left: 0, width: W, bottom: u * 0.13,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: u * 0.022, padding: '0 6%' }}>
        {msgs.map((m, i) => {
          const out = i % 2 === 1;
          const t0 = 0.5 + i * each;
          const pose = entrancePose(t - t0, { stiffness: 160, damping: 0.6, delay: 0 }, u * 0.05);
          // Incoming messages are preceded by a typing indicator (3 dots) for ~0.7s.
          const typing = !out && t >= t0 - 0.72 && t < t0;
          return (
            <div key={i}>
              {typing ? (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: fs * 0.28, padding: `${fs * 0.62}px ${fs * 0.8}px`,
                    borderRadius: fs * 1.3, borderBottomLeftRadius: fs * 0.3, background: '#e9ebf0',
                    boxShadow: '0 6px 16px rgba(30,50,90,0.1)' }}>
                    {[0, 1, 2].map((k) => {
                      const s = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(t * 9 - k * 0.9));
                      return <div key={k} style={{ width: fs * 0.42, height: fs * 0.42, borderRadius: '50%',
                        background: '#b3b8c4', transform: `scale(${s.toFixed(2)})`, opacity: 0.5 + 0.5 * s }} />;
                    })}
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: out ? 'flex-end' : 'flex-start', opacity: pose.alpha,
                  transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
                  <div style={{ maxWidth: '74%', padding: `${fs * 0.55}px ${fs * 0.85}px`, borderRadius: fs * 1.3,
                    borderBottomRightRadius: out ? fs * 0.3 : fs * 1.3, borderBottomLeftRadius: out ? fs * 1.3 : fs * 0.3,
                    background: out ? ui.accent : '#e9ebf0', color: out ? '#fff' : INK, fontSize: fs, fontWeight: 600,
                    boxShadow: '0 6px 16px rgba(30,50,90,0.1)' }}>{m}</div>
                </div>
              )}
              {out && i === lastOutIdx && pose.alpha > 0.9 && (
                <div style={{ textAlign: 'right', fontSize: u * 0.022, color: GRAY, marginTop: u * 0.006, paddingRight: '2%' }}>Delivered</div>
              )}
            </div>
          );
        })}
      </div>
      {/* input bar */}
      <div style={{ position: 'absolute', bottom: u * 0.03, left: '5%', width: '90%', display: 'flex', alignItems: 'center', gap: u * 0.02 }}>
        <div style={{ flex: 1, height: u * 0.075, borderRadius: 999, border: '1.5px solid #d8dce6', background: '#fff',
          display: 'flex', alignItems: 'center', paddingLeft: u * 0.03, color: '#a2a8b6', fontSize: u * 0.032 }}>iMessage</div>
        <div style={{ width: u * 0.075, height: u * 0.075, borderRadius: '50%', background: ui.accent, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={u * 0.04} height={u * 0.04} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round"><path d="M12 20V5M6 11l6-6 6 6" /></svg>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Notify: React.FC<{ ui: UiSpec; t: number; W: number; H: number }> = ({ ui, t, W, H }) => {
  const u = Math.min(W, H);
  const title = ui.title || 'DouchkoVE';
  const body = ui.lines[1] || ui.subtitle || 'Your clip is ready to share.';
  const drop = springStep(t - 0.25, { stiffness: 130, damping: 0.62, delay: 0 });
  const drop2 = springStep(t - 0.5, { stiffness: 130, damping: 0.64, delay: 0 });
  const iconSz = u * 0.085;
  const banner = (title2: string, body2: string, dd: number, top: number, z: number, scale: number) => (
    <div style={{ position: 'absolute', top, left: '5%', width: '90%', zIndex: z,
      display: 'flex', alignItems: 'center', gap: u * 0.028, padding: u * 0.032,
      borderRadius: u * 0.05, background: 'rgba(255,255,255,0.82)', backdropFilter: 'blur(24px)',
      boxShadow: `0 ${u * 0.02}px ${u * 0.06}px rgba(20,40,80,0.18)`, border: '1px solid rgba(255,255,255,0.7)',
      transform: `translateY(${(-u * 0.4 * (1 - Math.min(1, dd))).toFixed(1)}px) scale(${scale})`, opacity: Math.min(1, dd * 1.5) }}>
      <AppIcon size={iconSz} hue={hueFromAccent(ui.accent)} glyph={0} radius={iconSz * 0.28} {...(ui.logo ? { logo: ui.logo } : {})} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: u * 0.032, fontWeight: 800, color: INK }}>{title2}</div>
        <div style={{ fontSize: u * 0.028, color: '#4a5060', marginTop: u * 0.004, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{body2}</div>
      </div>
      <div style={{ fontSize: u * 0.022, color: '#a2a8b6', fontWeight: 600, alignSelf: 'flex-start' }}>now</div>
    </div>
  );
  return (
    <>
      <StatusBar W={W} u={u} />
      {/* lock-screen time */}
      <div style={{ position: 'absolute', top: H * 0.1, width: W, textAlign: 'center', color: '#243' }}>
        <div style={{ fontSize: u * 0.03, fontWeight: 600, opacity: 0.75 }}>Tuesday, 22 July</div>
        <div style={{ fontSize: u * 0.17, fontWeight: 700, marginTop: u * 0.005, letterSpacing: '-0.02em' }}>9:41</div>
      </div>
      {banner(title, 'Tap to see what’s new', drop2, H * 0.34, 1, 0.96)}
      {banner(title, body, drop, H * 0.32, 2, 1)}
    </>
  );
};

export const AppleScene: React.FC<{ spec: SceneSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const ui: UiSpec = spec.ui ?? { template: 'pills', lines: ['Write', 'Create', 'Solve'], accent: spec.palette.accent };
  const wallpaper = ui.template === 'homescreen' || ui.template === 'notify';
  ensureUserFont(spec.font); // Pillar 2: block render until the user's font is ready
  return (
    <Field wallpaper={wallpaper} font={fontStack(spec)}>
      {ui.template === 'pills' && <Pills ui={ui} t={t} W={width} H={height} seed={spec.seed} />}
      {ui.template === 'appcard' && <AppCard ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'search' && <Search ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'homescreen' && <HomeScreen ui={ui} t={t} W={width} H={height} seed={spec.seed} />}
      {ui.template === 'chat' && <Chat ui={ui} t={t} W={width} H={height} />}
      {ui.template === 'notify' && <Notify ui={ui} t={t} W={width} H={height} />}
    </Field>
  );
};
