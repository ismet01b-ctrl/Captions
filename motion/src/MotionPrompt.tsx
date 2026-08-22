// MotionPrompt — cinematic "assistant → code → website" build sequence, rebuilt faithfully from
// the @mythiqmotion reference (the DETAILED pass): glowing outlined logo with a light-sweep, a row
// of glowing action chips with a cursor that picks "Code", a glowing-edge prompt box that types
// with a trailing accent, a DENSE syntax-highlighted code stream flowing up a converging 3D
// perspective (with console logs), then a website panel that rotates in from 3D and settles flat
// as the glow drifts orange→blue — all under a continuous cinematic camera (push-ins / drift).
//
// Branding is GENERIC (neutral spark + user's brand; no third-party logo/wordmark/model name).
// Prompt + site copy come from the transcript. Pure in `t` (seekable).

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneSpec } from './spec';
import type { Shot } from './MotionShowcase';
import { clamp01, easeOutQuint, easeInOutQuint, easeOutBack, easeInOutCubic, mix } from './lib/easing';
import { themeFor, applyTheme, type Custom } from './showcaseThemes';

export type MotionPromptProps = { readonly spec: SceneSpec; readonly story?: readonly Shot[]; readonly styleId?: string; readonly custom?: Custom };

const FONT = `'Inter', system-ui, -apple-system, sans-serif`;
const MONO = `'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', monospace`;
const lineOf = (s: Shot): string => (s.accentText || [s.a, s.b].filter(Boolean).join(' ') || '').trim();
const PROMPT_DEFAULT = 'I want a portfolio website for my studio';

// ── syntax-highlighted code stream content (dense, like the reference) ───────────────────────
type Tok = { t: string; c: string };
const C = { tag: '#5aa9ff', attr: '#7ee787', str: '#ffb457', txt: '#aeb4c2', kw: '#ff7b9c', num: '#f0a852', ok: '#3ddc84', warn: '#ffcf5a', dim: '#6b7280' };
const codeLines = (head: string, sub: string): Tok[][] => [
  [{ t: '<section ', c: C.tag }, { t: 'class', c: C.attr }, { t: '=', c: C.txt }, { t: '"hero"', c: C.str }, { t: ' data-reveal>', c: C.tag }],
  [{ t: '  <nav ', c: C.tag }, { t: 'class', c: C.attr }, { t: '=', c: C.txt }, { t: '"top">', c: C.str }, { t: '<a>Work</a><a>About</a>', c: C.tag }],
  [{ t: '  <h1 ', c: C.tag }, { t: 'class', c: C.attr }, { t: '=', c: C.txt }, { t: '"display">', c: C.str }, { t: head, c: C.txt }, { t: '</h1>', c: C.tag }],
  [{ t: '  <p ', c: C.tag }, { t: 'class', c: C.attr }, { t: '=', c: C.txt }, { t: '"sub">', c: C.str }, { t: sub, c: C.txt }, { t: '</p>', c: C.tag }],
  [{ t: '  <svg ', c: C.tag }, { t: 'viewBox', c: C.attr }, { t: '=', c: C.txt }, { t: '"0 0 100 20"', c: C.str }, { t: '>', c: C.tag }],
  [{ t: '    <path ', c: C.tag }, { t: 'd', c: C.attr }, { t: '=', c: C.txt }, { t: '"M0,10 Q25,0 50,15 T100,5"', c: C.str }, { t: ' stroke', c: C.attr }, { t: '=', c: C.txt }, { t: '"#ff7a2f"', c: C.str }, { t: '/>', c: C.tag }],
  [{ t: '</section>', c: C.tag }],
  [{ t: '.hero', c: C.kw }, { t: '{', c: C.txt }, { t: 'display', c: C.attr }, { t: ':grid;', c: C.txt }, { t: 'place-items', c: C.attr }, { t: ':center', c: C.txt }, { t: '}', c: C.txt }],
  [{ t: '.display', c: C.kw }, { t: '{', c: C.txt }, { t: 'font-size', c: C.attr }, { t: ':clamp(', c: C.txt }, { t: '48px,8vw,120px', c: C.num }, { t: ')}', c: C.txt }],
  [{ t: 'const ', c: C.kw }, { t: 'app', c: C.txt }, { t: ' = ', c: C.txt }, { t: 'mount', c: C.attr }, { t: '(', c: C.txt }, { t: '"#root"', c: C.str }, { t: ')', c: C.txt }],
  [{ t: '[SYS_INIT] ', c: C.dim }, { t: 'Loading motion vector array…', c: C.txt }],
  [{ t: '[SUCCESS] ', c: C.ok }, { t: 'Graphics pipeline established at 120fps.', c: C.txt }],
  [{ t: '[WARN] ', c: C.warn }, { t: 'Thread pool nearing optimal thresholds.', c: C.txt }],
  [{ t: '</body></html>', c: '#ff7a2f' }],
];

// ── a rounded panel with an animated glowing gradient edge ───────────────────────────────────
const GlowEdge: React.FC<{ w: number; h: number; r: number; t: number; accent: string; bw: number; bg?: string; children?: React.ReactNode }>
  = ({ w, h, r, t, accent, bw, bg = '#0c0d11', children }) => (
  <div style={{
    position: 'relative', width: w, height: h, borderRadius: r, padding: bw,
    background: `conic-gradient(from ${((t * 80) % 360).toFixed(1)}deg, ${accent}, ${accent}dd, ${accent}22, ${accent}, ${accent}cc, ${accent})`,
    boxShadow: `0 0 ${bw * 6}px ${accent}aa, 0 0 ${bw * 16}px ${accent}55`,
  }}>
    <div style={{ width: '100%', height: '100%', borderRadius: r - bw, background: bg, overflow: 'hidden', position: 'relative' }}>{children}</div>
  </div>
);

// glowing OUTLINE spark (stroked petals), optionally with a moving specular sweep
const Spark: React.FC<{ size: number; color: string; glow?: number; fill?: boolean }> = ({ size, color, glow = 0, fill = true }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ filter: glow ? `drop-shadow(0 0 ${glow}px ${color})` : undefined }}>
    {Array.from({ length: 8 }, (_, i) => {
      const a = (i / 8) * 360;
      return <rect key={i} x={11.1} y={2.3} width={1.8} height={7.4} rx={0.9}
        fill={fill ? color : 'none'} stroke={fill ? 'none' : color} strokeWidth={fill ? 0 : 1.2}
        transform={`rotate(${a} 12 12)`} />;
    })}
  </svg>
);

const ChipIcon: React.FC<{ kind: string; s: number; color: string }> = ({ kind, s, color }) => {
  const p: Record<string, string> = {
    create: 'M4 14l7-7 4 4-7 7H4z M13 5l2-2 4 4-2 2',
    write: 'M4 20l3-1 11-11-2-2L5 17z',
    code: 'M9 8l-4 4 4 4M15 8l4 4-4 4',
    plan: 'M4 6h16v14H4z M4 10h16M8 3v4M16 3v4',
    learn: 'M3 8l9-4 9 4-9 4z M7 11v4c0 1 10 1 10 0v-4',
  };
  return <svg width={26 * s} height={26 * s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={p[kind]} /></svg>;
};

const Cursor: React.FC<{ x: number; y: number; press: number; s: number }> = ({ x, y, press, s }) => (
  <svg width={52 * s} height={52 * s} viewBox="0 0 54 54" style={{ position: 'absolute', left: x, top: y, transform: `scale(${1 - press * 0.16})`, transformOrigin: '30% 30%', filter: 'drop-shadow(0 6px 12px rgba(0,0,0,0.4))' }}>
    <path d="M14 6 L14 40 L21 33 L26 45 L31 43 L26 31 L36 31 Z" fill="#fff" stroke="#111" strokeWidth="2.4" strokeLinejoin="round" />
  </svg>
);

const PromptBody: React.FC<{ spec: SceneSpec; story: readonly Shot[]; styleId: string | undefined; custom: Custom | undefined }> = ({ spec, story, styleId, custom }) => {
  const { fps, width: W, height: H } = useVideoConfig();
  const t = useCurrentFrame() / fps;
  const S = H / 1080;
  const th = applyTheme(themeFor(custom?.style ?? styleId), custom);
  const accent = custom?.accent ?? (th.id !== 'mono' && th.id !== 'soft' ? th.accent : '#ff7a2f');
  const lines = (custom?.text && custom.text.length ? custom.text : story.map(lineOf)).filter(Boolean);
  const brand = (custom?.brand || lines.find((l) => /^made with /i.test(l))?.replace(/^made with /i, '') || 'DouchkoVE').trim();
  const prompt = lines[0] || PROMPT_DEFAULT;
  const head = (lines[1] || 'Premium studio').replace(/[.]+$/, '');
  const sub = lines[2] || 'crafted for creatives';
  const bw = Math.max(2, 3 * S);

  // ── timeline ────────────────────────────────────────────────────────────────
  const intro = [0.0, 1.9] as const;
  const chips = [1.7, 3.7] as const;
  const box = [3.5, 7.6] as const;      // longer, so the send-button closeup+press is its own beat
  const code = [6.9, 10.0] as const;    // code fires AFTER the send press (logical causality)
  const reveal = [9.4, 13.8] as const;

  const seg = (a: number, b: number): number => clamp01((t - a) / (b - a));
  const inOut = (a: number, b: number, fin = 0.25): number => {
    const p = seg(a, b); return clamp01(p / (fin)) * (1 - clamp01((p - (1 - fin)) / fin));
  };

  // volumetric glow drift + orange→blue as the site settles
  const rp = easeInOutQuint(seg(reveal[0] + 0.4, reveal[1] - 0.6));
  const glowCol = rp > 0.55 ? '#3f6cff' : accent;
  const gx = 50 + Math.sin(t * 0.5) * 16, gy = 30 + Math.cos(t * 0.4) * 10;

  return (
    <AbsoluteFill style={{ background: '#06070a' }}>
      {/* volumetric accent glow (two layers) */}
      <AbsoluteFill style={{ background: `radial-gradient(55% 45% at ${gx}% ${gy}%, ${glowCol}55 0%, transparent 60%)`, filter: `blur(${44 * S}px)` }} />
      <AbsoluteFill style={{ background: `radial-gradient(38% 30% at ${100 - gx}% ${gy + 24}%, ${accent}2e 0%, transparent 55%)`, filter: `blur(${64 * S}px)` }} />

      {/* ── INTRO: glowing outline spark + light sweep + wordmark, slow push-in ── */}
      {inOut(intro[0], intro[1], 0.28) > 0.01 && (() => {
        const p = seg(intro[0], intro[1]);
        const app = inOut(intro[0], intro[1], 0.28);
        const sc = mix(0.82, 1.05, easeOutBack(clamp01(p * 1.3)));   // push-in
        const sweep = clamp01((p - 0.15) * 2.2);                     // specular sweep across
        return (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: app }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 28 * S, transform: `scale(${sc.toFixed(3)})`, position: 'relative' }}>
              <div style={{ filter: `drop-shadow(0 0 ${24 * S}px ${accent})` }}><Spark size={104 * S} color={accent} glow={16 * S} fill={false} /></div>
              <div style={{ color: '#fff', fontFamily: th.font, fontWeight: 600, fontSize: 100 * S, letterSpacing: '-0.02em', position: 'relative', overflow: 'hidden' }}>
                {brand}
                {/* light sweep */}
                <div style={{ position: 'absolute', top: 0, bottom: 0, width: 120 * S, left: `${(sweep * 140 - 20).toFixed(0)}%`,
                  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.75), transparent)', filter: `blur(${6 * S}px)`, mixBlendMode: 'screen' }} />
              </div>
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* ── CHIPS: glowing action pills, cursor moves to "Code" and presses ── */}
      {inOut(chips[0], chips[1], 0.22) > 0.01 && (() => {
        const app = inOut(chips[0], chips[1], 0.22);
        const p = seg(chips[0], chips[1]);
        const CH = [{ k: 'create', l: 'Create' }, { k: 'write', l: 'Write' }, { k: 'code', l: 'Code' }, { k: 'plan', l: 'Plan' }, { k: 'learn', l: 'Learn' }];
        const camX = mix(30, -10, easeInOutCubic(clamp01(p * 1.2))) * S;   // slow lateral drift
        const travel = easeInOutCubic(clamp01((p - 0.15) / 0.55));
        const cx = mix(W * 0.8, W * 0.5 - 30 * S, travel);
        const cy = mix(H * 0.78, H * 0.52, travel);
        const press = clamp01((p - 0.62) / 0.14);
        return (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: app, transform: `translateX(${camX}px) scale(${mix(1.04, 1, clamp01(p * 1.4)).toFixed(3)})` }}>
            <div style={{ display: 'flex', gap: 26 * S }}>
              {CH.map((c, i) => {
                const on = c.k === 'code';
                const pop = easeOutBack(clamp01((p - 0.05 - i * 0.06) * 2.2));
                const lit = on ? (0.5 + 0.5 * press) : 0.5;
                return (
                  <div key={c.k} style={{ transform: `scale(${(pop * (on ? 1 - press * 0.06 : 1)).toFixed(3)})`, opacity: clamp01(pop * 2),
                    display: 'flex', alignItems: 'center', gap: 14 * S, padding: `${18 * S}px ${28 * S}px`, borderRadius: 22 * S,
                    background: on ? `linear-gradient(180deg, ${accent}, #d95e1e)` : '#14161d',
                    border: `${2 * S}px solid ${on ? accent : '#2a2d36'}`,
                    boxShadow: `0 0 ${(on ? 26 : 10) * S}px ${accent}${on ? 'cc' : '44'}`, color: on ? '#0b0b0d' : '#e7e9ef' }}>
                    <ChipIcon kind={c.k} s={S} color={on ? '#0b0b0d' : '#e7e9ef'} />
                    <span style={{ fontFamily: th.font, fontWeight: 600, fontSize: 38 * S }}>{c.l}</span>
                  </div>
                );
              })}
            </div>
            <Cursor x={cx} y={cy} press={press} s={S} />
          </AbsoluteFill>
        );
      })()}

      {/* ── PROMPT BOX: glowing edge, typewriter with trailing accent, controls, push-in ── */}
      {inOut(box[0], box[1], 0.18) > 0.01 && (() => {
        const app = inOut(box[0], box[1], 0.18);
        const p = seg(box[0], box[1]);
        const dur = box[1] - box[0];
        const typed = Math.max(0, Math.min(prompt.length, Math.round(((t - (box[0] + 0.2)) / (dur - 2.2)) * prompt.length)));
        const caretOn = Math.floor(t * 1.8) % 2 === 0;
        const tin = p * dur;
        // TWO-PHASE CAMERA: (1) a CLOSEUP that FOLLOWS the caret — the view tracks the last typed
        // word as the prompt is written (you read it word by word, not the whole box); (2) pull back
        // to reveal the full box; (3) a CLOSEUP on the send button as the cursor presses it — that
        // press is what fires the code build.
        const typeDone = dur - 2.0;
        const charW = 27 * S;
        const caretX = 52 * S + typed * charW;
        const caretFull = 52 * S + prompt.length * charW;
        let sc = 1, origin = '50% 50%', outerTx = 0;
        if (tin < typeDone) {
          sc = 1.5; outerTx = sc * (760 * S - caretX);            // FOLLOW the caret
        } else if (tin < dur - 1.5) {
          const q = easeInOutQuint((tin - typeDone) / ((dur - 1.5) - typeDone));
          sc = mix(1.5, 1.0, q); outerTx = mix(1.5 * (760 * S - caretFull), 0, q);  // pull to whole box
        } else {
          origin = '95% 74%'; sc = mix(1.0, 2.0, easeInOutQuint((tin - (dur - 1.5)) / 1.5));  // send closeup
        }
        // cursor travels to the send button and presses; the press drives the hand-off to code.
        const sendPress = clamp01((tin - (dur - 1.35)) / 0.25);
        const curT = easeInOutCubic(clamp01((tin - (dur - 1.9)) / 0.55));
        const curShow = clamp01((tin - (dur - 1.9)) * 2);
        const sx = 1441 * S, sy = 207 * S;                         // send-button centre inside the box
        const curX = mix(sx - 150 * S, sx - 8 * S, curT), curY = mix(sy + 150 * S, sy + 26 * S, curT);
        return (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: app }}>
           <div style={{ transform: `translateX(${outerTx.toFixed(1)}px)` }}>
            <div style={{ position: 'relative', transformOrigin: origin, transform: `scale(${sc.toFixed(3)})` }}>
              <GlowEdge w={1520 * S} h={280 * S} r={40 * S} t={t} accent={accent} bw={bw}>
                <div style={{ position: 'absolute', inset: 0, padding: `${46 * S}px ${52 * S}px` }}>
                  <div style={{ fontFamily: th.font, fontWeight: 500, fontSize: 56 * S, lineHeight: 1.25, color: '#f3f4f7' }}>
                    <span>{prompt.slice(0, Math.max(0, typed - 4))}</span>
                    <span style={{ color: accent, textShadow: `0 0 ${20 * S}px ${accent}` }}>{prompt.slice(Math.max(0, typed - 4), typed)}</span>
                    <span style={{ color: accent, opacity: caretOn ? 1 : 0.2, textShadow: `0 0 ${18 * S}px ${accent}` }}>▍</span>
                  </div>
                  <div style={{ position: 'absolute', left: 46 * S, right: 46 * S, bottom: 40 * S, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ width: 62 * S, height: 62 * S, borderRadius: '50%', border: `${2 * S}px solid #3a3c44`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#c9ccd4', fontSize: 40 * S }}>+</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 26 * S }}>
                      <div style={{ color: '#c9ccd4', fontFamily: th.font, fontSize: 32 * S }}>Pro ▾</div>
                      <svg width={26 * S} height={34 * S} viewBox="0 0 24 32" fill="none" stroke="#c9ccd4" strokeWidth="2"><rect x="8" y="2" width="8" height="16" rx="4" /><path d="M5 14a7 7 0 0 0 14 0M12 21v6" strokeLinecap="round" /></svg>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 3 * S, height: 34 * S }}>
                        {[10, 22, 14, 28, 12, 20].map((hh, i) => <div key={i} style={{ width: 3 * S, height: hh * S, background: '#c9ccd4', borderRadius: 2 }} />)}
                      </div>
                      <div style={{ width: 66 * S, height: 66 * S, borderRadius: '50%', background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transform: `scale(${(1 - sendPress * 0.18).toFixed(3)})`,
                        boxShadow: `0 0 ${(20 + sendPress * 34) * S}px ${accent}${sendPress > 0.3 ? 'ff' : 'aa'}` }}>
                        <svg width={30 * S} height={30 * S} viewBox="0 0 24 24" fill="none" stroke="#0b0b0d" strokeWidth="3"><path d="M12 20V5M6 11l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      </div>
                    </div>
                  </div>
                </div>
              </GlowEdge>
              {/* cursor that presses the send button (the interaction that fires the code) */}
              {curShow > 0.01 && (
                <svg width={52 * S} height={52 * S} viewBox="0 0 54 54" style={{ position: 'absolute', left: curX, top: curY, opacity: curShow,
                  transform: `scale(${1 - sendPress * 0.18})`, transformOrigin: '30% 30%', filter: 'drop-shadow(0 6px 12px rgba(0,0,0,0.5))' }}>
                  <path d="M14 6 L14 40 L21 33 L26 45 L31 43 L26 31 L36 31 Z" fill="#fff" stroke="#111" strokeWidth="2.4" strokeLinejoin="round" />
                </svg>
              )}
            </div>
           </div>
          </AbsoluteFill>
        );
      })()}

      {/* ── CODE STREAM: dense syntax-highlighted lines flowing up a converging perspective ── */}
      {inOut(code[0], code[1], 0.2) > 0.01 && (() => {
        const app = inOut(code[0], code[1], 0.2);
        const p = seg(code[0], code[1]);
        const CODE = codeLines(head, sub);
        const scroll = p * CODE.length * 52 * S;
        const czr = easeInOutQuint(clamp01((p * (code[1] - code[0])) / 1.3));   // zoom-out reveal of the code block
        return (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-start', paddingTop: H * 0.24, pointerEvents: 'none', perspective: `${820 * S}px`, opacity: app }}>
            <div style={{ transformStyle: 'preserve-3d', transform: `rotateX(52deg) scale(${mix(1.6, 1, czr).toFixed(3)})`, width: '70%',
              maskImage: 'linear-gradient(to bottom, transparent, #000 22%, #000 72%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 22%, #000 72%, transparent)' }}>
              {CODE.map((ln, i) => {
                const appear = clamp01((p * CODE.length - i) * 2.5);
                const y = i * 52 * S - scroll + H * 0.35;
                if (appear <= 0) return null;
                return (
                  <div key={i} style={{ transform: `translateY(${y.toFixed(1)}px)`, opacity: appear * 0.95, fontFamily: MONO, fontSize: 27 * S, whiteSpace: 'pre', lineHeight: 1.5, textAlign: 'center' }}>
                    {ln.map((tk, j) => <span key={j} style={{ color: tk.c, textShadow: `0 0 ${8 * S}px ${tk.c}88` }}>{tk.t}</span>)}
                  </div>
                );
              })}
            </div>
          </AbsoluteFill>
        );
      })()}

      {/* ── WEBSITE REVEAL: landing panel rotating in from 3D, settling flat, glow orange→blue ── */}
      {seg(reveal[0], reveal[1]) > 0 && seg(reveal[0], reveal[1]) < 1.05 && (() => {
        const app = clamp01((t - reveal[0]) * 1.6);
        // ZOOM-IN → REVEAL: start large + tilted (a glowing fragment, unclear what it is), then
        // pull back and flatten to reveal the whole website.
        const rotY = mix(34, 0, rp), rotX = mix(18, 0, rp), rScale = mix(1.55, 1, rp), rz = mix(-120, 0, rp);
        const camPush = mix(1.0, 1.03, easeInOutCubic(clamp01((seg(reveal[0], reveal[1]) - 0.6) / 0.4)));  // slow push after settle
        // once the page is flat, a cursor reaches the primary CTA and presses it (the button reacts).
        const rt = t - reveal[0];
        const ctaPress = clamp01((rt - 2.9) / 0.3);
        const ctaCurShow = clamp01((rt - 2.2) * 2);
        const ctaCurT = easeInOutCubic(clamp01((rt - 2.2) / 0.6));
        const bx = 190 * S, by = 650 * S;                         // "Connect with us" centre inside the panel
        return (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', perspective: `${1500 * S}px`, opacity: app }}>
            <div style={{ transformStyle: 'preserve-3d', transform: `scale(${camPush.toFixed(3)}) translateZ(${rz.toFixed(0)}px) rotateY(${rotY.toFixed(2)}deg) rotateX(${rotX.toFixed(2)}deg) scale(${rScale.toFixed(3)})` }}>
              <GlowEdge w={1660 * S} h={900 * S} r={30 * S} t={t} accent={glowCol} bw={bw} bg="#0a0c12">
                <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(160deg, #0a0c12 0%, ${glowCol}22 55%, ${glowCol}4a 100%)` }} />
                <div style={{ position: 'absolute', top: 40 * S, left: 50 * S, right: 50 * S, display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#e8eaf0', fontFamily: th.font }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 40 * S }}>
                    <Spark size={40 * S} color="#fff" />
                    {['Home', 'Work', 'Portfolio', 'About', 'FAQ'].map((x) => <span key={x} style={{ fontSize: 26 * S, opacity: 0.85 }}>{x}</span>)}
                  </div>
                  <div style={{ background: '#fff', color: '#0a0c12', fontWeight: 600, fontSize: 26 * S, padding: `${12 * S}px ${26 * S}px`, borderRadius: 40 * S }}>Get in touch</div>
                </div>
                <div style={{ position: 'absolute', left: 62 * S, top: 250 * S, right: 62 * S }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10 * S, background: 'rgba(255,255,255,0.12)', color: '#fff', fontSize: 24 * S, padding: `${8 * S}px ${18 * S}px`, borderRadius: 30 * S, marginBottom: 26 * S }}>
                    <Spark size={22 * S} color="#fff" /> No.1 Studio · 2026
                  </div>
                  <div style={{ color: '#fff', fontFamily: th.font, fontWeight: 600, fontSize: 100 * S, lineHeight: 1.04, letterSpacing: '-0.02em', maxWidth: '72%' }}>{head}</div>
                  <div style={{ color: '#c9ccd6', fontFamily: th.font, fontSize: 34 * S, marginTop: 20 * S }}>{sub}</div>
                  <div style={{ display: 'flex', gap: 20 * S, marginTop: 44 * S }}>
                    <div style={{ background: '#fff', color: '#0a0c12', fontWeight: 600, fontSize: 26 * S, padding: `${14 * S}px ${28 * S}px`, borderRadius: 40 * S,
                      transform: `scale(${(1 - ctaPress * 0.08).toFixed(3)})`, boxShadow: ctaPress > 0.3 ? `0 0 ${24 * S}px #ffffffaa` : 'none' }}>Connect with us</div>
                    <div style={{ background: 'rgba(255,255,255,0.12)', color: '#fff', fontSize: 26 * S, padding: `${14 * S}px ${28 * S}px`, borderRadius: 40 * S }}>Who is {brand}?</div>
                  </div>
                </div>
                {/* cursor presses the primary CTA once the page has settled */}
                {ctaCurShow > 0.01 && (
                  <svg width={50 * S} height={50 * S} viewBox="0 0 54 54" style={{ position: 'absolute',
                    left: mix(bx + 120 * S, bx - 8 * S, ctaCurT), top: mix(by + 150 * S, by - 2 * S, ctaCurT),
                    opacity: ctaCurShow, transform: `scale(${1 - ctaPress * 0.18})`, transformOrigin: '30% 30%', filter: 'drop-shadow(0 6px 12px rgba(0,0,0,0.5))' }}>
                    <path d="M14 6 L14 40 L21 33 L26 45 L31 43 L26 31 L36 31 Z" fill="#fff" stroke="#111" strokeWidth="2.4" strokeLinejoin="round" />
                  </svg>
                )}
              </GlowEdge>
            </div>
          </AbsoluteFill>
        );
      })()}
    </AbsoluteFill>
  );
};

export const MotionPrompt: React.FC<MotionPromptProps> = ({ spec, story, styleId, custom }) =>
  <PromptBody spec={spec} story={story && story.length ? story : []} styleId={styleId} custom={custom} />;

export const promptDuration = (): number => 14.4;
