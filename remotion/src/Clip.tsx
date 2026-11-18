import React from 'react';
import {loadFont} from '@remotion/fonts';
import {AbsoluteFill, Easing, OffthreadVideo, interpolate, staticFile, useCurrentFrame} from 'remotion';

type Word = {text: string; s: number; e: number; emph?: boolean};
type Group = {start: number; end: number; words: Word[]};

export type ClipProps = {
  src: string;
  fps: number;
  width: number;
  height: number;
  frames: number;
  cam: [number, number, number][];
  captions: Group[];
  caption_style: {font: string; font_file: string; size: number; y: number; outline: number};
  brand: {accent: string; text: string; outline: string};
};

const loaded = new Set<string>();
const useFont = (family: string, file: string) => {
  if (!loaded.has(family)) {
    loaded.add(family);
    loadFont({family, url: staticFile(`fonts/${file}`)});
  }
};

// ------------------------------------------------------------ camera
const Camera: React.FC<{src: string; cam: ClipProps['cam']}> = ({src, cam}) => {
  const f = useCurrentFrame();
  const [s, x, y] = cam[Math.min(f, cam.length - 1)] ?? [1, 540, 960];
  const prev = cam[Math.max(0, Math.min(f - 1, cam.length - 1))] ?? [s, x, y];
  const vel = Math.abs(s - prev[0]);
  const blur = vel > 0.012 && vel < 0.08 ? 1.2 : 0; // light blur only during fast zooms
  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: 'black'}}>
      <div
        style={{
          position: 'absolute',
          left: x - x * s,
          top: y - y * s,
          width: 1080 * s,
          height: 1920 * s,
          filter: blur ? `blur(${blur}px)` : undefined,
        }}
      >
        <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%'}} />
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------ captions
const POP = 0.11; // seconds for a word to pop in
const Captions: React.FC<Pick<ClipProps, 'captions' | 'caption_style' | 'brand' | 'fps'>> = ({
  captions,
  caption_style: st,
  brand,
  fps,
}) => {
  const f = useCurrentFrame();
  const t = f / fps;
  const g = captions.find((c) => t >= c.start - 1 / fps && t < c.end);
  if (!g) return null;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: 60,
          right: 60,
          top: st.y,
          transform: 'translateY(-50%)',
          textAlign: 'center',
          fontFamily: `'${st.font}'`,
          fontSize: st.size,
          lineHeight: 1.15,
          letterSpacing: 1,
          whiteSpace: 'nowrap',
        }}
      >
        {g.words.map((w, i) => {
          const appear = w.s - 1 / fps;
          const next = g.words[i + 1]?.s ?? g.end + 1;
          const shown = t >= appear;
          const p = interpolate(t, [appear, appear + POP], [0.6, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.out(Easing.cubic),
          });
          const active = t >= appear && t < next - 1 / fps;
          const color = active || w.emph ? brand.accent : brand.text;
          return (
            <React.Fragment key={i}>
              <span
                style={{
                  display: 'inline-block',
                  opacity: shown ? 1 : 0,
                  transform: `scaleY(${p})`,
                  transformOrigin: '50% 60%',
                  color,
                  WebkitTextStroke: `${st.outline * 2}px ${brand.outline}`,
                  paintOrder: 'stroke fill',
                  textShadow: '3px 3px 0 rgba(0,0,0,0.4)',
                }}
              >
                {w.text}
              </span>
              {i < g.words.length - 1 ? ' ' : ''}
            </React.Fragment>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const Clip: React.FC<ClipProps> = (p) => {
  useFont(p.caption_style?.font ?? 'Montserrat ExtraBold', p.caption_style?.font_file ?? 'Montserrat-ExtraBold.ttf');
  if (!p.src) return <AbsoluteFill style={{backgroundColor: 'black'}} />;
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <Camera src={p.src} cam={p.cam} />
      <Captions captions={p.captions} caption_style={p.caption_style} brand={p.brand} fps={p.fps} />
    </AbsoluteFill>
  );
};
