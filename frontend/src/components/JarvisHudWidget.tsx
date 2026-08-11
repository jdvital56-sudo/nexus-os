import React from 'react';

export type JarvisState = 'ONLINE' | 'LISTENING' | 'SPEAKING' | 'PROCESSING';

interface JarvisHudWidgetProps {
  state?: JarvisState;
  activeModel?: string;
  /** Размер кольца в пикселях. По умолчанию — как на дашборде. */
  size?: number;
}

// Бегущая по кругу дуга — главный элемент: пока она идёт, система жива.
// Когда Джарвис говорит, дуга ускоряется, а кольцо и ядро мелко дрожат.
//
// Всё движение — на CSS-анимациях. Прошлая версия крутила кольцо через
// setInterval(50ms) и перерисовывала React двадцать раз в секунду просто
// потому, что дашборд открыт.

const PALETTE: Record<JarvisState, { arc: string; ring: string; core: string; label: string }> = {
  // Покой — янтарь: тот же акцент, что у бегущей дуги, ничего не мигает
  ONLINE: { arc: '#F5B642', ring: 'rgba(245, 182, 66, 0.25)', core: 'rgba(245, 182, 66, 0.10)', label: 'text-amber-300' },
  LISTENING: { arc: '#FF2A85', ring: 'rgba(255, 42, 133, 0.3)', core: 'rgba(255, 42, 133, 0.15)', label: 'text-pink-400' },
  SPEAKING: { arc: '#00F2FE', ring: 'rgba(0, 242, 254, 0.3)', core: 'rgba(0, 242, 254, 0.18)', label: 'text-cyan-300' },
  PROCESSING: { arc: '#00DC82', ring: 'rgba(0, 220, 130, 0.3)', core: 'rgba(0, 220, 130, 0.12)', label: 'text-primary' },
};

const CAPTION: Record<JarvisState, string> = {
  ONLINE: 'ONLINE',
  LISTENING: 'СЛУШАЮ',
  SPEAKING: 'ГОВОРЮ',
  PROCESSING: 'ДУМАЮ',
};

export const JarvisHudWidget: React.FC<JarvisHudWidgetProps> = ({
  state = 'ONLINE',
  activeModel = '',
  size = 160,
}) => {
  const colors = PALETTE[state];
  const lively = state === 'LISTENING' || state === 'SPEAKING' || state === 'PROCESSING';
  const orbitSeconds = state === 'SPEAKING' ? 1.6 : state === 'PROCESSING' ? 2.4 : lively ? 3 : 6;

  // Дуга — это окружность с пунктиром «кусок штриха, остальное пусто»
  const r = 46;
  const circumference = 2 * Math.PI * r;
  const arcLength = circumference * (state === 'SPEAKING' ? 0.3 : 0.22);

  return (
    <div className="flex select-none flex-col items-center">
      <div
        className={`relative ${state === 'SPEAKING' ? 'jarvis-animated' : ''}`}
        style={{
          width: size,
          height: size,
          // Дрожь всего блока — её видно на кольце и на ядре сразу
          animation: state === 'SPEAKING' ? 'jarvis-tremor 0.18s linear infinite' : undefined,
        }}
        role="img"
        aria-label={`Джарвис: ${CAPTION[state].toLowerCase()}${activeModel ? `, модель ${activeModel}` : ''}`}
      >
        <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full">
          {/* Неподвижная дорожка, по которой бежит дуга */}
          <circle cx="50" cy="50" r={r} fill="none" stroke={colors.ring} strokeWidth="1" />

          {/* Штрихи-риски: дают ощущение шкалы, крутятся медленно в обратную сторону */}
          <g
            className="jarvis-animated"
            style={{
              transformOrigin: 'center',
              animation: `jarvis-orbit-reverse ${orbitSeconds * 6}s linear infinite`,
            }}
          >
            <circle
              cx="50"
              cy="50"
              r="41"
              fill="none"
              stroke={colors.ring}
              strokeWidth="0.7"
              strokeDasharray="1 6"
            />
          </g>

          {/* Та самая бегущая полоска */}
          <g
            className="jarvis-animated"
            style={{
              transformOrigin: 'center',
              animation: `jarvis-orbit ${orbitSeconds}s linear infinite`,
              filter: `drop-shadow(0 0 4px ${colors.arc})`,
            }}
          >
            <circle
              cx="50"
              cy="50"
              r={r}
              fill="none"
              stroke={colors.arc}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeDasharray={`${arcLength} ${circumference - arcLength}`}
            />
          </g>

          {/* Засечки по четырём сторонам — рамка прицела, стоит на месте */}
          {[0, 90, 180, 270].map((angle) => (
            <line
              key={angle}
              x1="50"
              y1="2"
              x2="50"
              y2="7"
              stroke={colors.arc}
              strokeWidth="1.5"
              opacity="0.5"
              style={{ transform: `rotate(${angle}deg)`, transformOrigin: 'center' }}
            />
          ))}
        </svg>

        {/* Ядро */}
        <div
          className={`absolute inset-0 m-auto flex items-center justify-center rounded-full border ${
            lively ? 'jarvis-animated' : ''
          }`}
          style={{
            width: '68%',
            height: '68%',
            backgroundColor: colors.core,
            borderColor: colors.arc,
            boxShadow: `0 0 ${lively ? 28 : 14}px ${colors.ring}, inset 0 0 24px ${colors.core}`,
            animation: lively ? 'jarvis-breathe 2s ease-in-out infinite' : undefined,
            transition: 'box-shadow 300ms ease, background-color 300ms ease',
          }}
        >
          <span
            className="font-mono text-[0.62rem] font-bold tracking-[0.3em] text-white"
            style={{ textShadow: `0 0 10px ${colors.arc}`, paddingLeft: '0.3em' }}
          >
            J.A.R.V.I.S.
          </span>
        </div>
      </div>

      <div className={`mt-3 flex items-center gap-2 font-mono text-[0.7rem] tracking-widest ${colors.label}`}>
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: colors.arc, boxShadow: `0 0 8px ${colors.arc}` }}
        />
        {CAPTION[state]}
      </div>

      {activeModel && (
        <div className="mt-2 rounded-full border border-gray-700 bg-darker px-3 py-1 font-mono text-[0.6rem] tracking-wide text-gray-300">
          {activeModel}
        </div>
      )}
    </div>
  );
};
