// MotionPrompt — a cinematic "prompt → code → website" build sequence, rebuilt faithfully from
// the @mythiqmotion reference LOOK (dark stage + volumetric accent glow, a glowing-edge prompt
// box that types a prompt with a trailing accent character, streaming glowing code in perspective,
// then a website panel that rotates in from 3D and settles flat). This is the "dynamic, expensive"
// typography treatment — glow, typewriter, depth — not flat text.
//
// Branding is GENERIC on purpose: a neutral spark mark + the user's brand name (never a third
// party's logo/wordmark). Prompt text + site copy come from the transcript/brand, so it stays
// per-user and never invents words. Pure in `t` (seekable).

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec } from './spec';
import type { Shot } from './MotionShowcase';
import { clamp01, easeOutQuint, easeInOutQuint, easeOutBack, mix } from './lib/easing';
import { themeFor } from './showcaseThemes';

export type MotionPromptProps = { readonly spec: SceneSpec; readonly story?: readonly Shot[]; readonly styleId?: string };

const FONT = `'Inter', system-ui, -apple-system, sans-serif`;
const MONO = `'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', monospace`;
const lineOf = (s: Shot): string => (s.accentText || [s.a, s.b].filter(Boolean).join(' ') || '').trim();

const PROMPT_DEFAULT = 'I want a portfolio website for my studio';
const CODE_LINES = [
  '<section class="hero" data-reveal>',
  '  <nav class="top"><a>Home</a><a>Work</a><a>About</a></nav>',
  '  <h1 class="display">{{HEAD}}</h1>',
  '  <p class="sub">{{SUB}}</p>',
  '  <div class="cta"><button>Get in touch</button></div>',
  '  <svg viewBox="0 0 100 20" class="spark">',
  '    <path d="M0,10 Q25,0 50,15 T100,5" stroke="#ff7a2f"/>',
  '  </svg>',
  '</section>',
  '.hero{display:grid;place-items:center;min-height:100vh}',
  '.display{font-size:clamp(48px,8vw,120px);letter-spacing:-.03em}',
];

// A rounded panel with an animated glowing gradient edge (the reference's signature).
const GlowEdge: React.FC<{ w: number; h: number; r: number; t: number; accent: string; bw: number; bg?: string; children?: React.ReactNode; style?: React.CSSProperties }>
  = ({ w, h, r, t, accent, bw, bg = '#0c0d11', children, style }) => (
  <div style={{
    position: 'relative', width: w, height: h, borderRadius: r, padding: bw,
    background: `conic-gradient(from ${((t * 90) % 360).toFixed(1)}deg, ${accent}, #ff9a4d, ${accent}22, ${accent}, #ffb36b, ${accent})`,
    boxShadow: `0 0 ${bw * 6}px ${accent}aa, 0 0 ${bw * 14}px ${accent}55, inset 0 0 ${bw}px ${accent}`,
    ...style,
  }}>
    <div style={{ width: '100%', height: '100%', borderRadius: r - bw, background: bg, overflow: 'hidden', position: 'relative' }}>
      {children}
    </div>
  </div>
);

const Spark: React.FC<{ size: number; color: string; glow?: number }> = ({ size, color, glow = 0 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ filter: glow ? `drop-shadow(0 0 ${glow}px ${color})` : undefined }}>
    {Array.from({ length: 8 }, (_, i) => {
      const a = (i / 8) * Math.PI * 2;
      return <rect key={i} x={11.2} y={2.5} width={1.6} height={7} rx={0.8} fill={color}
        transform={`rotate(${(a * 180 / Math.PI).toFixed(1)} 12 12)`} />;
    })}
  </svg>
);

const PromptBody: React.FC<{ spec: SceneSpec; story: readonly Shot[]; styleId: string | undefined }> = ({ spec, story, styleId }) => {
  const { fps, width: W, height: H } = useVideoConfig();
  const t = useCurrentFrame() / fps;
  const S = H / 1080;
  const th = themeFor(styleId);
  const accent = th.accent && th.id !== 'mono' ? th.accent : '#ff7a2f';   // cinematic warm glow
  const lines = story.map(lineOf).filter(Boolean);
  const brand = (lines.find((l) => /^made with /i.test(l))?.replace(/^made with /i, '') || 'Studio').trim();
  const prompt = lines[0] || PROMPT_DEFAULT;
  const head = (lines[1] || 'Premium studio').replace(/[.]+$/, '');
  const sub = lines[2] || 'crafted for creatives';

  // ── timeline ────────────────────────────────────────────────────────────────
  const T_INTRO = 2.2, T_TYPE = 3.4, T_CODE = 3.2, T_REVEAL = 3.6;
  const introEnd = T_INTRO;
  const typeStart = T_INTRO - 0.3, typeEnd = typeStart + T_TYPE;
  const codeStart = typeEnd - 1.2, codeEnd = codeStart + T_CODE;
  const revealStart = codeEnd - 0.6, revealEnd = revealStart + T_REVEAL;

  // volumetric glow drifts
  const gx = 50 + Math.sin(t * 0.5) * 18, gy = 34 + Math.cos(t * 0.4) * 12;

  // intro logo
  const introA = clamp01((t - 0.2) * 1.6) * (1 - clamp01((t - (introEnd - 0.2)) * 2.2));
  const introS = 0.7 + 0.3 * easeOutBack(clamp01((t - 0.2) * 1.2));

  // prompt box appear + type
  const boxA = clamp01((t - (typeStart - 0.2)) * 2.2) * (1 - clamp01((t - (revealStart - 0.1)) * 1.8));
  const boxLift = (1 - easeOutQuint(clamp01((t - (typeStart - 0.2)) / 0.6))) * 40 * S;
  const typed = Math.max(0, Math.min(prompt.length, Math.round(((t - typeStart) / (typeEnd - typeStart)) * prompt.length)));
  const caretOn = Math.floor(t * 1.8) % 2 === 0;

  // website reveal 3D
  const rp = easeInOutQuint(clamp01((t - revealStart) / (revealEnd - revealStart)));
  const siteA = clamp01((t - revealStart) * 1.6);
  const rotY = mix(28, 0, rp), rotX = mix(18, 0, rp), rScale = mix(0.86, 1, rp), rz = mix(-260, 0, rp);
  // color drift orange → cool blue as it settles (like the reference)
  const siteHue = rp; // 0 warm → 1 cool
  const siteAccent = rp < 0.5 ? accent : '#4d8bff';

  const bw = Math.max(2, 3 * S);

  return (
    <AbsoluteFill style={{ background: '#07080b' }}>
      {/* volumetric accent glow */}
      <AbsoluteFill style={{ background: `radial-gradient(55% 45% at ${gx}% ${gy}%, ${(siteHue > 0.6 ? '#2b4a8f' : accent)}66 0%, transparent 60%)`, filter: `blur(${40 * S}px)` }} />
      <AbsoluteFill style={{ background: `radial-gradient(40% 30% at ${100 - gx}% ${gy + 20}%, ${accent}33 0%, transparent 55%)`, filter: `blur(${60 * S}px)` }} />

      {/* INTRO — generic spark + brand wordmark, glowing */}
      {introA > 0.01 && (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: introA }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 26 * S, transform: `scale(${introS.toFixed(3)})`, filter: `drop-shadow(0 0 ${26 * S}px ${accent}aa)` }}>
            <Spark size={92 * S} color={accent} glow={20 * S} />
            <div style={{ color: '#fff', fontFamily: FONT, fontWeight: 600, fontSize: 96 * S, letterSpacing: '-0.02em' }}>{brand}</div>
          </div>
        </AbsoluteFill>
      )}

      {/* PROMPT BOX — glowing edge, typewriter with trailing accent, controls */}
      {boxA > 0.01 && (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: boxA }}>
          <div style={{ transform: `translateY(${boxLift.toFixed(1)}px)` }}>
            <GlowEdge w={1500 * S} h={280 * S} r={40 * S} t={t} accent={accent} bw={bw}>
              <div style={{ position: 'absolute', inset: 0, padding: `${44 * S}px ${52 * S}px` }}>
                <div style={{ fontFamily: FONT, fontWeight: 500, fontSize: 56 * S, lineHeight: 1.25, color: '#f3f4f7' }}>
                  <span>{prompt.slice(0, Math.max(0, typed - 4))}</span>
                  <span style={{ color: accent, textShadow: `0 0 ${20 * S}px ${accent}` }}>{prompt.slice(Math.max(0, typed - 4), typed)}</span>
                  <span style={{ color: accent, opacity: caretOn ? 1 : 0.2, textShadow: `0 0 ${18 * S}px ${accent}` }}>▍</span>
                </div>
                {/* bottom control row */}
                <div style={{ position: 'absolute', left: 46 * S, right: 46 * S, bottom: 40 * S, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ width: 62 * S, height: 62 * S, borderRadius: '50%', border: `${2 * S}px solid #3a3c44`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#c9ccd4', fontSize: 40 * S }}>+</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 26 * S }}>
                    <div style={{ color: '#c9ccd4', fontFamily: FONT, fontSize: 32 * S }}>Pro ▾</div>
                    <svg width={26 * S} height={34 * S} viewBox="0 0 24 32" fill="none" stroke="#c9ccd4" strokeWidth="2"><rect x="8" y="2" width="8" height="16" rx="4" /><path d="M5 14a7 7 0 0 0 14 0M12 21v6" strokeLinecap="round" /></svg>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 * S, height: 34 * S }}>
                      {[10, 22, 14, 28, 12, 20].map((hh, i) => <div key={i} style={{ width: 3 * S, height: hh * S, background: '#c9ccd4', borderRadius: 2 }} />)}
                    </div>
                    <div style={{ width: 66 * S, height: 66 * S, borderRadius: '50%', background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 0 ${20 * S}px ${accent}aa` }}>
                      <svg width={30 * S} height={30 * S} viewBox="0 0 24 24" fill="none" stroke="#0b0b0d" strokeWidth="3"><path d="M12 20V5M6 11l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    </div>
                  </div>
                </div>
              </div>
            </GlowEdge>
          </div>
        </AbsoluteFill>
      )}

      {/* CODE STREAM — glowing monospace flowing up in perspective */}
      {t > codeStart && t < revealStart + 0.8 && (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-start', paddingTop: H * 0.52, pointerEvents: 'none', perspective: `${900 * S}px`,
          opacity: clamp01((t - codeStart) * 2) * (1 - clamp01((t - (revealStart + 0.2)) * 2)) }}>
          <div style={{ transformStyle: 'preserve-3d', transform: `rotateX(42deg)`, maskImage: 'linear-gradient(to bottom, transparent, #000 40%, #000 70%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 40%, #000 70%, transparent)' }}>
            {CODE_LINES.map((ln, i) => {
              const appear = clamp01((t - codeStart - i * 0.18) * 3);
              const scroll = (t - codeStart) * 70 * S;
              const y = i * 46 * S - scroll;
              const filled = ln.replace('{{HEAD}}', head).replace('{{SUB}}', sub);
              return (
                <div key={i} style={{ transform: `translateY(${y.toFixed(1)}px)`, opacity: appear * 0.9, color: accent,
                  fontFamily: MONO, fontSize: 26 * S, whiteSpace: 'pre', textShadow: `0 0 ${10 * S}px ${accent}bb`, lineHeight: 1.4 }}>{filled}</div>
              );
            })}
          </div>
        </AbsoluteFill>
      )}

      {/* WEBSITE REVEAL — a landing panel rotating in from 3D, settling flat */}
      {siteA > 0.01 && (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', perspective: `${1400 * S}px`, opacity: siteA }}>
          <div style={{ transformStyle: 'preserve-3d', transform: `translateZ(${rz.toFixed(0)}px) rotateY(${rotY.toFixed(2)}deg) rotateX(${rotX.toFixed(2)}deg) scale(${rScale.toFixed(3)})` }}>
            <GlowEdge w={1640 * S} h={860 * S} r={30 * S} t={t} accent={siteAccent} bw={bw} bg="#0a0c12" style={{ transition: 'none' }}>
              <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(160deg, #0a0c12 0%, ${siteAccent}22 60%, ${siteAccent}44 100%)` }} />
              {/* nav */}
              <div style={{ position: 'absolute', top: 40 * S, left: 48 * S, right: 48 * S, display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#e8eaf0', fontFamily: FONT }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 40 * S }}>
                  <Spark size={40 * S} color="#fff" />
                  {['Home', 'Work', 'About', 'FAQ'].map((x) => <span key={x} style={{ fontSize: 26 * S, opacity: 0.85 }}>{x}</span>)}
                </div>
                <div style={{ background: '#ffffff', color: '#0a0c12', fontWeight: 600, fontSize: 26 * S, padding: `${12 * S}px ${26 * S}px`, borderRadius: 40 * S }}>Get in touch</div>
              </div>
              {/* hero */}
              <div style={{ position: 'absolute', left: 60 * S, top: 250 * S, right: 60 * S }}>
                <div style={{ display: 'inline-block', background: 'rgba(255,255,255,0.12)', color: '#fff', fontSize: 24 * S, padding: `${8 * S}px ${18 * S}px`, borderRadius: 30 * S, marginBottom: 26 * S }}>No.1 Studio · 2026</div>
                <div style={{ color: '#fff', fontFamily: FONT, fontWeight: 600, fontSize: 96 * S, lineHeight: 1.05, letterSpacing: '-0.02em', maxWidth: '70%' }}>{head}</div>
                <div style={{ color: '#c9ccd6', fontFamily: FONT, fontSize: 34 * S, marginTop: 20 * S }}>{sub}</div>
                <div style={{ display: 'flex', gap: 20 * S, marginTop: 44 * S }}>
                  <div style={{ background: '#fff', color: '#0a0c12', fontWeight: 600, fontSize: 26 * S, padding: `${14 * S}px ${28 * S}px`, borderRadius: 40 * S }}>Connect with us</div>
                  <div style={{ background: 'rgba(255,255,255,0.12)', color: '#fff', fontSize: 26 * S, padding: `${14 * S}px ${28 * S}px`, borderRadius: 40 * S }}>Who is {brand}?</div>
                </div>
              </div>
            </GlowEdge>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

export const MotionPrompt: React.FC<MotionPromptProps> = ({ spec, story, styleId }) =>
  <PromptBody spec={spec} story={story && story.length ? story : []} styleId={styleId} />;

export const promptDuration = (): number => 13.2;
