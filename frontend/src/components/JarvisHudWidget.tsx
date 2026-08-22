import React from 'react';

export type JarvisState = 'ONLINE' | 'LISTENING' | 'SPEAKING' | 'PROCESSING';

interface JarvisHudWidgetProps {
  state?: JarvisState;
  activeModel?: string;
  /** Размер кольца в пикселях. По умолчанию — как на дашборде. */
  size?: number;
  /**
   * 'graphite' (по умолчанию) — тусклый металл, решение фаундера 13.08.2026
   * для основного интерфейса. 'vivid' — яркая бирюза с сильным свечением,
   * попросил фаундер 19.08.2026 для плавающего виджета: на живом рабочем
   * столе поверх произвольного фона тусклое кольцо просто не читается как
   * круг, нужен реальный глоу, как на присланном референсе.
   */
  palette?: 'graphite' | 'vivid';
  /**
   * Внешний обод горит красным вместо зелёного — настоящий сигнал (связь
   * с бэкендом/голосом оборвана), не декоративный цвет. Просил добавить
   * красный/зелёный фаундер 19.08.2026, но красить кольцо цветом без
   * смысла — значит просто испортить приборную шкалу шумом; вместо этого
   * это единственное новое место, где цвет действительно что-то говорит,
   * как и STATE_COLOR ниже.
   */
  alert?: boolean;
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

// Яркий вариант ('vivid') — та же холодная бирюза, что уже на фоне экрана
// «Разговор» (jarvis-hud.css: --gold #22d3ee, --torch #f5b642), не новая
// придуманная палитра.
const VIVID_RING = '#22d3ee';
const VIVID_SPARK = '#67e8f9';
const VIVID_TORCH = '#f5b642';
const RIM_GOOD = '#4ade80';   // внешний обод, всё в порядке
const RIM_ALERT = '#f04747'; // внешний обод, alert=true

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
  palette = 'graphite',
  alert = false,
}) => {
  const vivid = palette === 'vivid';
  const ring = vivid ? VIVID_RING : STEEL;
  const spark = vivid ? VIVID_SPARK : SPARK;
  const glowRGB = vivid ? '34, 211, 238' : '142, 151, 157';
  const rim = vivid ? (alert ? RIM_ALERT : RIM_GOOD) : ring;
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
        {vivid && (
          // Почти сплошной тёмный диск позади кольца — первая версия была
          // полупрозрачной тенью (0.34 альфы), а полупрозрачное всегда
          // светлеет и блёкнет на белом фоне (законы смешивания цвета, не
          // починить прозрачностью). Диск делает фон под кольцом одинаковым
          // всегда, вне зависимости от того, что реально на рабочем столе —
          // второй багрепорт фаундера 19.08.2026, скриншоты чёрный/белый фон
          // рядом: на белом кольцо «совсем плохо».
          <div
            className="absolute inset-0 m-auto rounded-full"
            style={{ width: '98%', height: '98%', background: 'rgba(9, 13, 17, 0.94)', boxShadow: '0 2px 10px rgba(0,0,0,0.35)' }}
          />
        )}
        {vivid && (
          // Мягкое цветное свечение поверх тёмной подложки — на реальном
          // рабочем столе, поверх произвольного фона, без этого кольцо тонет
          <div
            className="absolute inset-0 m-auto rounded-full"
            style={{
              width: '92%',
              height: '92%',
              background: `radial-gradient(circle, rgba(${glowRGB}, 0.20) 0%, rgba(${glowRGB}, 0) 70%)`,
              filter: 'blur(4px)',
            }}
          />
        )}
        <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full">
          {/* Внешний обод — зелёный в порядке, красный при alert (настоящий
              сигнал, не декорация: голос/бэкенд оборвались) */}
          <circle
            cx="50" cy="50" r="48" fill="none" stroke={rim}
            strokeWidth={vivid ? 1.4 : 0.5} opacity={vivid ? 0.85 : 0.25}
            style={vivid ? { filter: `drop-shadow(0 0 3px ${rim})` } : undefined}
          />

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
              stroke={ring}
              strokeWidth={vivid ? 2.6 : 2}
              strokeDasharray={SEGMENTS}
              opacity={vivid ? 0.95 : 0.75}
              style={vivid ? { filter: `drop-shadow(0 0 4px ${ring})` } : undefined}
            />
          </g>

          {/* Та самая полоска, бегущая по кругу */}
          <g
            className="jarvis-animated"
            style={{
              transformOrigin: 'center',
              animation: `jarvis-orbit ${orbit}s linear infinite`,
              filter: `drop-shadow(0 0 ${vivid ? 6 : 3}px ${vivid ? VIVID_TORCH : spark})`,
            }}
          >
            <circle
              cx="50"
              cy="50"
              r={R}
              fill="none"
              stroke={vivid ? VIVID_TORCH : spark}
              strokeWidth={vivid ? 3 : 2.4}
              strokeLinecap="round"
              strokeDasharray={`${arc} ${CIRC - arc}`}
            />
          </g>

          {/* Внутренние риски — в обратную сторону, дают ощущение механизма */}
          <g
            className="jarvis-animated"
            style={{ transformOrigin: 'center', animation: `jarvis-orbit-reverse ${orbit * 3}s linear infinite` }}
          >
            <circle cx="50" cy="50" r="37" fill="none" stroke={ring} strokeWidth={vivid ? 1 : 0.8} strokeDasharray="1 5" opacity={vivid ? 0.7 : 0.5} />
          </g>

          {/* Скобки сверху и снизу — рамка прицела, стоит на месте */}
          <path d="M 34 17 A 34 34 0 0 1 66 17" fill="none" stroke={ring} strokeWidth={vivid ? 1.6 : 1.2} opacity={vivid ? 0.75 : 0.55} />
          <path d="M 34 83 A 34 34 0 0 0 66 83" fill="none" stroke={ring} strokeWidth={vivid ? 1.6 : 1.2} opacity={vivid ? 0.75 : 0.55} />

          {/* Кольцо ядра */}
          <circle cx="50" cy="50" r="29" fill={`rgba(${glowRGB}, ${vivid ? 0.12 : 0.06})`} stroke={ring} strokeWidth={vivid ? 1.2 : 0.8} opacity={vivid ? 0.9 : 0.7} />
        </svg>

        <div
          className={`absolute inset-0 m-auto flex items-center justify-center rounded-full ${lively ? 'jarvis-animated' : ''}`}
          style={{
            width: '52%',
            height: '52%',
            boxShadow: `0 0 ${lively ? (vivid ? 40 : 26) : (vivid ? 24 : 14)}px rgba(${glowRGB}, ${vivid ? 0.55 : 0.30}), inset 0 0 22px rgba(${glowRGB}, ${vivid ? 0.28 : 0.14})`,
            borderRadius: '50%',
            animation: lively ? 'jarvis-breathe 2.4s ease-in-out infinite' : undefined,
            transition: 'box-shadow 300ms ease',
          }}
        >
          <span
            className="font-mono text-[0.6rem] font-bold tracking-[0.28em]"
            style={{ color: spark, textShadow: `0 0 ${vivid ? 14 : 10}px ${ring}`, paddingLeft: '0.28em' }}
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
