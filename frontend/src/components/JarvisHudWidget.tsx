import React from 'react';

export type JarvisState = 'ONLINE' | 'LISTENING' | 'SPEAKING' | 'PROCESSING';

interface JarvisHudWidgetProps {
  state?: JarvisState;
  activeModel?: string;
  /** Размер кольца в пикселях. По умолчанию — как на дашборде. */
  size?: number;
}

// Кольцо собрано слоями, как приборная шкала: неподвижная дорожка, четыре
// стальных сегмента, светлая дуга, которая бежит по кругу всегда, и
// внутренние риски, ползущие в обратную сторону. Когда Джарвис говорит,
// дуга ускоряется, а кольцо и ядро мелко дрожат.
//
// Всё движение — на CSS-анимациях. Прошлая версия крутила кольцо через
// setInterval(50ms) и перерисовывала React двадцать раз в секунду просто
// потому, что дашборд открыт.

// Джарвис намеренно выпадает из египетского стиля всей системы: он не бог
// из этой мифологии, и графит вместо бронзы показывает это глазом, без
// подписи. Решение фаундера 13.08.2026 — не рассогласование, а замысел.
const STEEL = '#8e979d';   // основной металл кольца
const SPARK = '#c6ced3';   // бегущая дуга — светлее фона, но не белая

// Состояние — единственное место, где допущен цвет. Он несёт смысл
// (жив / слушает / говорит), поэтому не подчиняется графиту.
const STATE_COLOR: Record<JarvisState, string> = {
  ONLINE: '#6fb38c',
  LISTENING: '#c98fa8',
  SPEAKING: '#7fa8c4',
  PROCESSING: '#c2a06a',
};

const CAPTION: Record<JarvisState, [string, string]> = {
  ONLINE: ['НА СВЯЗИ', 'жду команды, сэр'],
  LISTENING: ['СЛУШАЮ', 'слушаю, сэр…'],
  SPEAKING: ['ГОВОРЮ', 'отвечаю…'],
  PROCESSING: ['ДУМАЮ', 'считаю, сэр…'],
};

const R = 44;
const CIRC = 2 * Math.PI * R;

/** Четыре сегмента шкалы: длинный, короткий, длинный, короткий. */
const SEGMENTS = `${CIRC * 0.28} ${CIRC * 0.06} ${CIRC * 0.14} ${CIRC * 0.06} ${CIRC * 0.28} ${CIRC * 0.06} ${CIRC * 0.06} ${CIRC * 0.06}`;

export const JarvisHudWidget: React.FC<JarvisHudWidgetProps> = ({
  state = 'ONLINE',
  activeModel = '',
  size = 170,
}) => {
  const accent = STATE_COLOR[state];
  const lively = state !== 'ONLINE';
  // Секунд на оборот. Втрое медленнее прежнего: фаундер сказал, что
  // движение «чересчур быстрое». Ускорение оставлено только там, где оно
  // что-то значит — когда Джарвис действительно занят.
  const orbit = state === 'SPEAKING' ? 9 : state === 'PROCESSING' ? 14 : lively ? 18 : 30;
  const arc = CIRC * (state === 'SPEAKING' ? 0.26 : 0.18);
  const [caption, subtitle] = CAPTION[state];

  return (
    <div className="flex select-none flex-col items-center">
      <div
        className={state === 'SPEAKING' ? 'jarvis-animated' : undefined}
        style={{
          width: size,
          height: size,
          position: 'relative',
          animation: state === 'SPEAKING' ? 'jarvis-tremor 0.18s linear infinite' : undefined,
        }}
        role="img"
        aria-label={`Джарвис: ${caption.toLowerCase()}${activeModel ? `, модель ${activeModel}` : ''}`}
      >
        <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full">
          {/* Внешний тонкий обод */}
          <circle cx="50" cy="50" r="48" fill="none" stroke={STEEL} strokeWidth="0.5" opacity="0.25" />

          {/* Сегменты шкалы — медленно против часовой */}
          <g
            className="jarvis-animated"
            style={{ transformOrigin: 'center', animation: `jarvis-orbit-reverse ${orbit * 8}s linear infinite` }}
          >
            <circle
              cx="50"
              cy="50"
              r={R}
              fill="none"
              stroke={STEEL}
              strokeWidth="2"
              strokeDasharray={SEGMENTS}
              opacity="0.75"
            />
          </g>

          {/* Та самая янтарная полоска, бегущая по кругу */}
          <g
            className="jarvis-animated"
            style={{
              transformOrigin: 'center',
              animation: `jarvis-orbit ${orbit}s linear infinite`,
              filter: `drop-shadow(0 0 3px ${SPARK})`,
            }}
          >
            <circle
              cx="50"
              cy="50"
              r={R}
              fill="none"
              stroke={SPARK}
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeDasharray={`${arc} ${CIRC - arc}`}
            />
          </g>

          {/* Внутренние риски — в обратную сторону, дают ощущение механизма */}
          <g
            className="jarvis-animated"
            style={{ transformOrigin: 'center', animation: `jarvis-orbit-reverse ${orbit * 3}s linear infinite` }}
          >
            <circle cx="50" cy="50" r="37" fill="none" stroke={STEEL} strokeWidth="0.8" strokeDasharray="1 5" opacity="0.5" />
          </g>

          {/* Скобки сверху и снизу — рамка прицела, стоит на месте */}
          <path d="M 34 17 A 34 34 0 0 1 66 17" fill="none" stroke={STEEL} strokeWidth="1.2" opacity="0.55" />
          <path d="M 34 83 A 34 34 0 0 0 66 83" fill="none" stroke={STEEL} strokeWidth="1.2" opacity="0.55" />

          {/* Кольцо ядра */}
          <circle cx="50" cy="50" r="29" fill="rgba(142, 151, 157, 0.06)" stroke={STEEL} strokeWidth="0.8" opacity="0.7" />
        </svg>

        <div
          className={`absolute inset-0 m-auto flex items-center justify-center rounded-full ${lively ? 'jarvis-animated' : ''}`}
          style={{
            width: '52%',
            height: '52%',
            boxShadow: `0 0 ${lively ? 26 : 14}px rgba(142, 151, 157, 0.30), inset 0 0 22px rgba(142, 151, 157, 0.14)`,
            borderRadius: '50%',
            animation: lively ? 'jarvis-breathe 2.4s ease-in-out infinite' : undefined,
            transition: 'box-shadow 300ms ease',
          }}
        >
          <span
            className="font-mono text-[0.6rem] font-bold tracking-[0.28em]"
            style={{ color: SPARK, textShadow: `0 0 10px ${STEEL}`, paddingLeft: '0.28em' }}
          >
            J.A.R.V.I.S.
          </span>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 font-mono text-[0.7rem] tracking-[0.2em]" style={{ color: accent }}>
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: accent, boxShadow: `0 0 8px ${accent}` }} />
        {caption}
      </div>

      <div className="mt-1 font-mono text-[0.6rem] tracking-wide text-gray-500">{subtitle}</div>

      {activeModel && (
        <div
          className="mt-2 rounded-full border px-3 py-1 font-mono text-[0.6rem] tracking-wide"
          style={{ borderColor: 'rgba(142, 151, 157, 0.32)', color: '#a3abb0', backgroundColor: 'rgba(20, 23, 26, 0.9)' }}
        >
          ◈ {activeModel}
        </div>
      )}
    </div>
  );
};
