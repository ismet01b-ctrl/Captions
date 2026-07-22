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
// iOS dark mode: light text on dark surfaces.
const INK = '#f3f5fb';
const GRAY = '#9096a6';

// -------------------------------------------------------------------- chrome & primitives

const StatusBar: React.FC<{ W: number; u: number; color?: string }> = ({ W, u, color = INK }) => {
  const fs = u * 0.031;
  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: W, height: u * 0.06,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: `0 ${u * 0.065}px`, color, fontWeight: 700, fontSize: fs }}>
      <div style={{ letterSpacing: '0.02em' }}>13:39</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: u * 0.016 }}>
        {/* cellular signal */}
        <svg width={fs * 1.15} height={fs} viewBox="0 0 18 12">
          {[0, 1, 2, 3].map((i) => (
            <rect key={i} x={i * 4.5} y={12 - (4 + i * 2.6)} width={3} height={4 + i * 2.6} rx={0.8}
              fill={color} fillOpacity={i < 2 ? 1 : 0.35} />
          ))}
        </svg>
        <span style={{ fontSize: fs * 0.92, fontWeight: 700 }}>5G</span>
        {/* battery + % badge */}
        <svg width={fs * 1.7} height={fs} viewBox="0 0 26 12">
          <rect x="0.5" y="1" width="22" height="10" rx="2.6" fill="none" stroke={color} strokeOpacity="0.5" />
          <rect x="2" y="2.5" width="10" height="7" rx="1.4" fill="#ffcf3f" />
          <rect x="24" y="4" width="1.8" height="4" rx="0.9" fill={color} fillOpacity="0.5" />
        </svg>
      </div>
    </div>
  );
};

// iOS-26 "Liquid Glass": translucent surfaces that blur + saturate what's behind them, with
// a bright specular rim and layered depth. hueFromAccent(accent) tints a colourful liquid
// background so the glass has something to refract — the hallmark of the look.
const LiquidBg: React.FC<{ accent: string; wallpaper?: boolean }> = ({ accent, wallpaper }) => {
  const h = hueFromAccent(accent);
  const blob = (x: string, y: string, w: string, hh: string, hue: number, a: number, b: number, light = 55): React.CSSProperties => ({
    position: 'absolute', left: x, top: y, width: w, height: hh, borderRadius: '50%',
    filter: `blur(${b}px)`, background: `hsla(${((hue % 360) + 360) % 360}, 80%, ${light}%, ${a})`,
  });
  return (
    <AbsoluteFill style={{
      // iOS dark mode: near-black base. Wallpaper screens get a warm cinematic wash
      // (like a real photo lock screen); content screens stay a deep neutral charcoal.
      background: wallpaper
        ? `linear-gradient(165deg, hsl(${(h + 20) % 360},32%,14%) 0%, #14100e 45%, hsl(28,45%,20%) 100%)`
        : 'radial-gradient(130% 100% at 50% 0%, #1c1f27 0%, #121319 55%, #0b0c11 100%)',
    }}>
      <div style={blob('-14%', '2%', '74%', '44%', h, wallpaper ? 0.4 : 0.28, 80, wallpaper ? 42 : 52)} />
      <div style={blob('46%', '42%', '70%', '48%', h + 52, wallpaper ? 0.34 : 0.22, 90, wallpaper ? 40 : 50)} />
      <div style={blob('6%', '72%', '66%', '40%', h + 305, wallpaper ? 0.32 : 0.2, 92, wallpaper ? 44 : 54)} />
      {/* subtle top vignette for depth */}
      <AbsoluteFill style={{ background: 'radial-gradient(120% 80% at 50% -10%, rgba(255,255,255,0.06), transparent 60%)' }} />
    </AbsoluteFill>
  );
};

const Field: React.FC<{ children: React.ReactNode; wallpaper?: boolean; font?: string; accent: string }> = ({ children, wallpaper, font, accent }) => (
  <AbsoluteFill style={{ fontFamily: font ?? FONT }}>
    <LiquidBg accent={accent} wallpaper={!!wallpaper} />
    {children}
  </AbsoluteFill>
);

/** Dark liquid-glass surface: translucent charcoal, backdrop blur+saturate, faint specular
 *  rim + top highlight, deep drop shadow — the iOS-26 dark-mode material. */
const glass = (u: number, opts: { radius?: number; alpha?: number; blur?: number; strong?: boolean; tint?: string } = {}): React.CSSProperties => {
  const { radius = u * 0.055, alpha = 0.5, blur = 26, strong = false, tint } = opts;
  const bf = `blur(${blur}px) saturate(160%) brightness(1.05)`;
  return {
    background: tint
      ? `linear-gradient(180deg, ${tint}, ${tint})`
      : `linear-gradient(180deg, rgba(58,62,74,${Math.min(0.8, alpha + 0.12)}) 0%, rgba(30,33,42,${Math.max(0.3, alpha - 0.04)}) 100%)`,
    backdropFilter: bf,
    WebkitBackdropFilter: bf,
    borderRadius: radius,
    border: '1px solid rgba(255,255,255,0.14)',
    boxShadow: `0 ${u * (strong ? 0.05 : 0.03)}px ${u * (strong ? 0.14 : 0.09)}px rgba(0,0,0,0.45), `
      + `inset 0 1px 1px rgba(255,255,255,0.16), inset 0 -${u * 0.006}px ${u * 0.012}px rgba(0,0,0,0.3)`,
  } as React.CSSProperties;
};

// Retained name; now a liquid-glass surface so existing call sites pick up the new look.
const softCard = (u: number, strong = false): React.CSSProperties => glass(u, { strong, alpha: 0.5 });

/** A quick press feedback: expanding ripple ring at the tapped control. */
const Ripple: React.FC<{ press: number; size: number; color: string }> = ({ press, size, color }) => {
  if (press <= 0.001) return null;
  const p = press;
  return (
    <div style={{ position: 'absolute', left: '50%', top: '50%', width: size, height: size, borderRadius: '50%',
      transform: `translate(-50%,-50%) scale(${(0.3 + p * 1.5).toFixed(3)})`, border: `2px solid ${color}`,
      opacity: (1 - p) * 0.7, pointerEvents: 'none' }} />
  );
};

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

const Pills: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number; press: number }> = ({ ui, t, W, H, seed, press }) => {
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
                transform: `translate3d(0, ${(pose.ty + float).toFixed(1)}px, 0) scale(${(pose.scale * (1 - 0.04 * press)).toFixed(3)})`,
                filter: blurCss(pose.blur), padding: `${fs * 0.42}px ${fs * 0.9}px`, color: INK, fontSize: fs, fontWeight: 800,
                whiteSpace: 'nowrap', willChange: 'transform, opacity, filter', ...glass(u, { radius: fs * 1.1, alpha: 0.58, blur: 22 }) }}>{it}</div>
            );
          })}
        </div>
      </AbsoluteFill>
    </>
  );
};

const AppCard: React.FC<{ ui: UiSpec; t: number; W: number; H: number; press: number }> = ({ ui, t, W, H, press }) => {
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
          <div style={{ position: 'relative', padding: `${u * 0.015}px ${u * 0.045}px`, borderRadius: 999, background: ui.accent, color: '#fff',
            fontWeight: 800, fontSize: u * 0.03, transform: `scale(${(openPulse * (1 - 0.1 * press)).toFixed(3)})`,
            boxShadow: `0 ${u * 0.012}px ${u * 0.03}px ${ui.accent}${press > 0.3 ? 'aa' : '66'}`, filter: press > 0.3 ? 'brightness(1.12)' : undefined }}>
            Open<Ripple press={press} size={u * 0.12} color="#fff" />
          </div>
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
        <div style={{ height: 1, background: 'rgba(255,255,255,0.1)', margin: `${u * 0.04}px 0` }} />
        <div style={{ display: 'flex', textAlign: 'center' }}>
          {[{ big: '4.8', star: true, lab: 'RATINGS' }, { big: '12+', lab: 'AGE' }, { big: '#1', lab: (sub.slice(0, 12).toUpperCase() || 'TOP') }].map((s, i) => (
            <div key={i} style={{ flex: 1, opacity: rev(i + 3), transform: `translateY(${(1 - rev(i + 3)) * u * 0.02}px)`,
              borderLeft: i ? '1px solid rgba(255,255,255,0.1)' : 'none' }}>
              <div style={{ fontSize: u * 0.034, fontWeight: 800, color: INK, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u * 0.006 }}>
                {s.big}{s.star && <Stars size={u * 0.012} color="#6b7180" />}
              </div>
              <div style={{ fontSize: u * 0.019, color: '#8b91a0', fontWeight: 700, letterSpacing: '0.06em', marginTop: u * 0.008 }}>{s.lab}</div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Search: React.FC<{ ui: UiSpec; t: number; W: number; H: number; press: number }> = ({ ui, t, W, H, press }) => {
  const u = Math.min(W, H);
  const pose = entrancePose(t, { stiffness: 150, damping: 0.6, delay: 0 }, u * 0.04);
  const query = ui.title || 'Ask anything';
  const shown = Math.max(0, Math.floor((t - 0.5) / 0.055));
  const typed = query.slice(0, shown);
  const done = shown >= query.length;
  const cursorOn = Math.floor(t * 2) % 2 === 0;
  const fs = u * 0.038;
  const suggestions = [query, `${query} fast`, `${query} for creators`, `best ${query.toLowerCase()}`].slice(0, 4);
  // The interaction that drives the hand-off: as the scene ends the user "presses Search" —
  // the field lights up with the accent, a ripple fires and the suggestions collapse away.
  const submit = clamp01(press);
  return (
    <>
      <StatusBar W={W} u={u} />
      <div style={{ position: 'absolute', top: u * 0.1, left: '9%', width: '82%' }}>
        <div style={{ fontSize: u * 0.05, fontWeight: 800, color: INK, marginBottom: u * 0.03 }}>Search</div>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: u * 0.022, padding: `${u * 0.026}px ${u * 0.035}px`,
          ...glass(u, { radius: u * 0.04, alpha: 0.5, blur: 22 }),
          border: submit > 0.2 ? `1.5px solid ${ui.accent}` : '1px solid rgba(255,255,255,0.6)',
          boxShadow: submit > 0.2 ? `0 ${u * 0.02}px ${u * 0.05}px ${ui.accent}55, inset 0 1px 1px rgba(255,255,255,0.8)` : glass(u).boxShadow,
          opacity: pose.alpha, transform: `translateY(${pose.ty.toFixed(1)}px) scale(${(pose.scale * (1 - 0.03 * submit)).toFixed(3)})`, filter: blurCss(pose.blur) }}>
          <svg width={fs} height={fs} viewBox="0 0 24 24" fill="none" stroke={submit > 0.2 ? ui.accent : GRAY} strokeWidth={2.4} strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
          </svg>
          <div style={{ flex: 1, fontSize: fs, color: typed ? INK : '#9aa0ae', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden' }}>
            {typed || 'Ask anything'}{!done && cursorOn ? <span style={{ color: ui.accent }}>|</span> : null}
          </div>
          <svg width={fs * 3} height={fs} viewBox="0 0 60 24" style={{ opacity: 1 - submit }}>
            {[0, 1, 2, 3, 4].map((i) => { const h = 6 + 9 * (0.5 + 0.5 * Math.sin(t * 6 + i));
              return <rect key={i} x={12 + i * 9} y={12 - h / 2} width={4} height={h} rx={2} fill={ui.accent} />; })}
          </svg>
          <Ripple press={submit} size={fs * 2.6} color={ui.accent} />
        </div>
        {/* suggestions dropdown — collapses as Search is pressed */}
        <div style={{ marginTop: u * 0.02, opacity: 1 - submit, transform: `translateY(${(-submit * u * 0.02).toFixed(1)}px)` }}>
          {suggestions.map((s, i) => {
            const rv = clamp01((t - 0.9 - i * 0.12) / 0.3);
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: u * 0.025,
                padding: `${u * 0.022}px ${u * 0.01}px`, borderBottom: '1px solid rgba(180,190,210,0.35)',
                opacity: rv, transform: `translateX(${(1 - rv) * u * 0.03}px)` }}>
                <svg width={fs * 0.9} height={fs * 0.9} viewBox="0 0 24 24" fill="none" stroke="#7a8090" strokeWidth={2.2} strokeLinecap="round">
                  <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
                </svg>
                <span style={{ fontSize: u * 0.032, color: '#cdd2de' }}>{s}</span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

const HomeScreen: React.FC<{ ui: UiSpec; t: number; W: number; H: number; seed: number; press: number }> = ({ ui, t, W, H, seed, press }) => {
  const u = Math.min(W, H);
  const cols = 4, rows = 4;
  const gap = W * 0.055;
  const size = (W * 0.78 - gap * (cols - 1)) / cols;
  const startX = W * 0.11, startY = H * 0.14;
  const labels = ['Notes', 'Photos', 'Health', 'Clock', 'Store', 'Maps', 'Mail', 'Music', 'News', 'Wallet', 'Files', 'Home', 'Books', 'Cam', 'Docs', 'Chat'];
  const Icon = (i: number, x: number, y: number, badge?: number) => {
    const stagger = (hash01(i, seed) * 0.4) + i * 0.03;
    const pose = entrancePose(t - stagger, { stiffness: 170, damping: 0.55, delay: 0 }, H * 0.02);
    const pr = i === 0 ? press : 0; // the user "opens" the first (brand) app -> hand-off
    return (
      <div key={`${x}-${y}`} style={{ position: 'absolute', left: x, top: y, width: size, textAlign: 'center',
        opacity: pose.alpha, transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${(pose.scale * (1 - 0.12 * pr)).toFixed(3)})`, filter: blurCss(pose.blur) }}>
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <AppIcon size={size} hue={Math.floor(hash01(i, seed + 2) * 360)} glyph={i} radius={size * 0.24}
            {...(badge != null ? { badge } : {})} {...(i === 0 && ui.logo ? { logo: ui.logo } : {})} />
          {pr > 0 && <Ripple press={pr} size={size} color="#fff" />}
        </div>
        <div style={{ marginTop: size * 0.1, fontSize: size * 0.17, color: '#fff', fontWeight: 600, textShadow: '0 1px 3px rgba(0,0,0,0.55)' }}>{labels[i % labels.length]}</div>
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
        {[0, 1, 2].map((i) => <div key={i} style={{ width: u * 0.014, height: u * 0.014, borderRadius: '50%', background: i === 0 ? '#fff' : 'rgba(255,255,255,0.4)' }} />)}
      </div>
      {/* dock */}
      <div style={{ position: 'absolute', bottom: H * 0.04, left: '6%', width: '88%', height: u * 0.2,
        ...glass(u, { radius: u * 0.06, alpha: 0.4, blur: 30 }),
        display: 'flex', alignItems: 'center', justifyContent: 'space-around', padding: `0 ${u * 0.04}px` }}>
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

// WhatsApp-style dark chat: green outgoing bubbles with tails + double read-ticks, dark
// incoming bubbles, a nav bar (back, avatar, name, video + call), a typing indicator, and a
// real input bar (+, field, sticker, camera / mic). Matches the reference dark-mode UI.
const OUT_BG = '#075e54'; // WhatsApp outgoing green (dark)
const IN_BG = '#1f2c33';  // incoming dark bubble
const Tick: React.FC<{ size: number; read?: boolean }> = ({ size, read }) => (
  <svg width={size * 1.6} height={size} viewBox="0 0 20 12" fill="none" stroke={read ? '#53bdeb' : '#8aa0a8'} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 6.5l3 3 6-7" /><path d="M7 9.5l1.5 1.5 7-8" />
  </svg>
);
const Chat: React.FC<{ ui: UiSpec; t: number; W: number; H: number; press: number }> = ({ ui, t, W, H, press }) => {
  const u = Math.min(W, H);
  const msgs = (ui.lines.length ? ui.lines : ['Hey!', 'The new drop is live', 'Check it now']).slice(0, 4);
  const fs = u * 0.036;
  const name = ui.title && ui.title.length < 22 ? ui.title : 'Messages';
  const each = 0.95;
  const lastOutIdx = msgs.reduce((a, _m, i) => (i % 2 === 1 ? i : a), -1);
  const nameHue = hueFromAccent(ui.accent);
  return (
    <AbsoluteFill>
      {/* WhatsApp dark canvas */}
      <AbsoluteFill style={{ background: '#0b141a' }} />
      <AbsoluteFill style={{ background: 'radial-gradient(130% 90% at 50% 0%, rgba(255,255,255,0.04), transparent 55%)' }} />
      {/* nav bar */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: W, height: u * 0.155, zIndex: 3,
        ...glass(u, { radius: 0, alpha: 0.42, blur: 22 }), borderRadius: 0, borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'flex-end', paddingBottom: u * 0.018, paddingLeft: u * 0.05, paddingRight: u * 0.05, gap: u * 0.028 }}>
        <svg width={u * 0.05} height={u * 0.05} viewBox="0 0 24 24" fill="none" stroke="#eaf0f2" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M15 5l-7 7 7 7" /></svg>
        <div style={{ width: u * 0.09, height: u * 0.09, borderRadius: '50%', overflow: 'hidden',
          background: ui.logo ? '#fff' : `linear-gradient(150deg, hsl(${nameHue},60%,52%), hsl(${(nameHue + 30) % 360},60%,42%))`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: u * 0.04 }}>
          {ui.logo ? <Img src={ui.logo} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : name.slice(0, 1).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: u * 0.03, fontWeight: 700, color: '#eaf0f2', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
          <div style={{ fontSize: u * 0.02, color: '#8aa0a8', marginTop: u * 0.002 }}>online</div>
        </div>
        <svg width={u * 0.05} height={u * 0.05} viewBox="0 0 24 24" fill="none" stroke="#eaf0f2" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="6" width="13" height="12" rx="3" /><path d="M22 8l-5 4 5 4z" /></svg>
        <svg width={u * 0.045} height={u * 0.045} viewBox="0 0 24 24" fill="#eaf0f2"><path d="M6.6 2.3l3 .7c.5.1.9.5 1 1l.5 3c.1.5-.1 1-.5 1.3L8.5 11c1 2 2.5 3.5 4.5 4.5l1.7-2.1c.3-.4.8-.6 1.3-.5l3 .5c.5.1.9.5 1 1l.7 3c.1.6-.3 1.2-.9 1.3-9 1.7-16.6-5.9-14.9-14.9.1-.6.7-1 1.3-.9z" /></svg>
      </div>
      <div style={{ position: 'absolute', top: u * 0.175, left: 0, width: W, bottom: u * 0.125, zIndex: 2,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: u * 0.016, padding: '0 5%' }}>
        {msgs.map((m, i) => {
          const out = i % 2 === 1;
          const t0 = 0.5 + i * each;
          const pose = entrancePose(t - t0, { stiffness: 160, damping: 0.6, delay: 0 }, u * 0.05);
          const typing = !out && t >= t0 - 0.72 && t < t0;
          const time = `13:${(32 + i).toString().padStart(2, '0')}`;
          return (
            <div key={i}>
              {typing ? (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: fs * 0.28, padding: `${fs * 0.6}px ${fs * 0.75}px`,
                    borderRadius: fs * 1.2, borderBottomLeftRadius: fs * 0.25, background: IN_BG }}>
                    {[0, 1, 2].map((k) => {
                      const s = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(t * 9 - k * 0.9));
                      return <div key={k} style={{ width: fs * 0.4, height: fs * 0.4, borderRadius: '50%',
                        background: '#8aa0a8', transform: `scale(${s.toFixed(2)})`, opacity: 0.5 + 0.5 * s }} />;
                    })}
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: out ? 'flex-end' : 'flex-start', opacity: pose.alpha,
                  transform: `translate3d(0, ${pose.ty.toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`, filter: blurCss(pose.blur) }}>
                  <div style={{ position: 'relative', maxWidth: '78%', padding: `${fs * 0.5}px ${fs * 0.8}px ${fs * 0.42}px`,
                    borderRadius: fs * 1.0, borderBottomRightRadius: out ? fs * 0.16 : fs * 1.0, borderBottomLeftRadius: out ? fs * 1.0 : fs * 0.16,
                    background: out ? OUT_BG : IN_BG, color: '#e9edef', fontSize: fs, fontWeight: 500, lineHeight: 1.28,
                    boxShadow: '0 1px 1px rgba(0,0,0,0.35)' }}>
                    {/* group-style sender name on incoming, in an accent hue */}
                    {!out && i === 0 && <div style={{ fontSize: fs * 0.82, fontWeight: 800, color: `hsl(${(nameHue + 20) % 360},70%,66%)`, marginBottom: fs * 0.15 }}>{name}</div>}
                    <span>{m}</span>
                    <span style={{ float: 'right', display: 'inline-flex', alignItems: 'center', gap: fs * 0.2, marginLeft: fs * 0.6, marginTop: fs * 0.35, fontSize: fs * 0.6, color: out ? '#8fb7ab' : '#8aa0a8' }}>
                      {time}{out && <Tick size={fs * 0.6} read={t > t0 + 0.6} />}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {/* input bar — the user "sends" (press) which drives the hand-off to the next scene */}
      <div style={{ position: 'absolute', bottom: u * 0.028, left: '4%', width: '92%', display: 'flex', alignItems: 'center', gap: u * 0.022, zIndex: 3 }}>
        <div style={{ flex: 1, height: u * 0.08, borderRadius: 999, background: IN_BG, border: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', gap: u * 0.025, padding: `0 ${u * 0.03}px` }}>
          <svg width={u * 0.045} height={u * 0.045} viewBox="0 0 24 24" fill="none" stroke="#8aa0a8" strokeWidth={2.2} strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          <div style={{ flex: 1, height: u * 0.045, display: 'flex', alignItems: 'center' }}>
            <div style={{ width: 2, height: u * 0.036, background: '#25d366', opacity: Math.floor(t * 2) % 2 === 0 ? 1 : 0.2 }} />
          </div>
          <svg width={u * 0.045} height={u * 0.045} viewBox="0 0 24 24" fill="none" stroke="#8aa0a8" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="9" cy="9" r="1.6" fill="#8aa0a8" stroke="none" /><path d="M8 15c1.5 1.5 6.5 1.5 8 0" /></svg>
          <svg width={u * 0.045} height={u * 0.045} viewBox="0 0 24 24" fill="none" stroke="#8aa0a8" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="6" width="13" height="12" rx="3" /><circle cx="10.5" cy="12" r="2.6" /><path d="M20 8l-3 4 3 4z" /></svg>
        </div>
        <div style={{ position: 'relative', width: u * 0.085, height: u * 0.085, borderRadius: '50%', background: '#25d366',
          display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${(1 - 0.12 * press).toFixed(3)})`,
          filter: press > 0.3 ? 'brightness(1.12)' : undefined, boxShadow: press > 0.3 ? `0 0 ${u * 0.03}px #25d366` : undefined }}>
          {press > 0.15
            ? <svg width={u * 0.042} height={u * 0.042} viewBox="0 0 24 24" fill="none" stroke="#08120c" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round"><path d="M4 12l16-7-7 16-2-7z" /></svg>
            : <svg width={u * 0.042} height={u * 0.042} viewBox="0 0 24 24" fill="none" stroke="#08120c" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M6 11a6 6 0 0 0 12 0M12 17v3" /></svg>}
          <Ripple press={press} size={u * 0.12} color="#25d366" />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Notify: React.FC<{ ui: UiSpec; t: number; W: number; H: number; press: number }> = ({ ui, t, W, H, press }) => {
  const u = Math.min(W, H);
  const title = ui.title || 'DouchkoVE';
  const body = ui.lines[1] || ui.subtitle || 'Your clip is ready to share.';
  const drop = springStep(t - 0.25, { stiffness: 130, damping: 0.62, delay: 0 });
  const drop2 = springStep(t - 0.5, { stiffness: 130, damping: 0.64, delay: 0 });
  const iconSz = u * 0.085;
  const banner = (title2: string, body2: string, dd: number, top: number, z: number, scale: number, pr = 0) => (
    <div style={{ position: 'absolute', top, left: '5%', width: '90%', zIndex: z,
      display: 'flex', alignItems: 'center', gap: u * 0.028, padding: u * 0.032,
      ...glass(u, { radius: u * 0.05, alpha: 0.68, blur: 30, strong: true }),
      filter: pr > 0.3 ? 'brightness(1.06)' : undefined,
      transform: `translateY(${(-u * 0.4 * (1 - Math.min(1, dd))).toFixed(1)}px) scale(${(scale * (1 - 0.03 * pr)).toFixed(3)})`, opacity: Math.min(1, dd * 1.5) }}>
      <AppIcon size={iconSz} hue={hueFromAccent(ui.accent)} glyph={0} radius={iconSz * 0.28} {...(ui.logo ? { logo: ui.logo } : {})} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: u * 0.032, fontWeight: 800, color: INK }}>{title2}</div>
        <div style={{ fontSize: u * 0.028, color: '#c2c7d2', marginTop: u * 0.004, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{body2}</div>
      </div>
      <div style={{ fontSize: u * 0.022, color: '#9096a6', fontWeight: 600, alignSelf: 'flex-start' }}>now</div>
    </div>
  );
  return (
    <>
      <StatusBar W={W} u={u} />
      {/* lock-screen time (light on the dark wallpaper) */}
      <div style={{ position: 'absolute', top: H * 0.1, width: W, textAlign: 'center', color: '#f3f5fb' }}>
        <div style={{ fontSize: u * 0.03, fontWeight: 600, opacity: 0.85 }}>Wednesday, 22 July</div>
        <div style={{ fontSize: u * 0.18, fontWeight: 700, marginTop: u * 0.005, letterSpacing: '-0.02em', textShadow: '0 2px 20px rgba(0,0,0,0.35)' }}>13:39</div>
      </div>
      {banner(title, 'Tap to see what’s new', drop2, H * 0.34, 1, 0.96)}
      {banner(title, body, drop, H * 0.32, 2, 1, press)}
    </>
  );
};

export const AppleScene: React.FC<{ spec: SceneSpec; press?: number }> = ({ spec, press = 0 }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const ui: UiSpec = spec.ui ?? { template: 'pills', lines: ['Write', 'Create', 'Solve'], accent: spec.palette.accent };
  const wallpaper = ui.template === 'homescreen' || ui.template === 'notify';
  ensureUserFont(spec.font); // Pillar 2: block render until the user's font is ready
  const p = clamp01(press);
  return (
    <Field wallpaper={wallpaper} font={fontStack(spec)} accent={ui.accent}>
      {ui.template === 'pills' && <Pills ui={ui} t={t} W={width} H={height} seed={spec.seed} press={p} />}
      {ui.template === 'appcard' && <AppCard ui={ui} t={t} W={width} H={height} press={p} />}
      {ui.template === 'search' && <Search ui={ui} t={t} W={width} H={height} press={p} />}
      {ui.template === 'homescreen' && <HomeScreen ui={ui} t={t} W={width} H={height} seed={spec.seed} press={p} />}
      {ui.template === 'chat' && <Chat ui={ui} t={t} W={width} H={height} press={p} />}
      {ui.template === 'notify' && <Notify ui={ui} t={t} W={width} H={height} press={p} />}
    </Field>
  );
};
