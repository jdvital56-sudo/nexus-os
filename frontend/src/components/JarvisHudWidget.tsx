import React, { useEffect, useState } from 'react';

interface JarvisHudWidgetProps {
  state?: 'ONLINE' | 'LISTENING' | 'SPEAKING' | 'PROCESSING';
  activeModel?: string;
}

export const JarvisHudWidget: React.FC<JarvisHudWidgetProps> = ({
  state = 'ONLINE',
  activeModel = 'GEMINI-2.0',
}) => {
  const [rotation, setRotation] = useState(0);
  const [pulseScale, setPulseScale] = useState(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setRotation((prev) => (prev + (state === 'LISTENING' || state === 'SPEAKING' ? 2 : 0.5)) % 360);
    }, 50);
    return () => clearInterval(interval);
  }, [state]);

  useEffect(() => {
    if (state === 'LISTENING' || state === 'SPEAKING') {
      const pulseInterval = setInterval(() => {
        setPulseScale((prev) => (prev === 1 ? 1.15 : 1));
      }, 400);
      return () => clearInterval(pulseInterval);
    } else {
      setPulseScale(1);
    }
  }, [state]);

  const getCoreColors = () => {
    switch (state) {
      case 'LISTENING':
        return { bg: 'rgba(255, 42, 133, 0.2)', border: '#FF2A85', glow: '#FF2A85' };
      case 'SPEAKING':
      case 'PROCESSING':
        return { bg: 'rgba(0, 242, 254, 0.25)', border: '#00F2FE', glow: '#00F2FE' };
      default:
        return { bg: 'rgba(0, 242, 254, 0.1)', border: 'rgba(0, 242, 254, 0.4)', glow: '#00F2FE' };
    }
  };

  const colors = getCoreColors();

  return (
    <div className="relative flex flex-col items-center justify-center select-none p-4">
      {/* Outer Container */}
      <div className="relative w-40 h-40 flex items-center justify-center">
        {/* Outer Arc Shell - Track Ring */}
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox="0 0 100 100"
          style={{ filter: `drop-shadow(0 0 8px ${colors.glow})` }}
        >
          {/* Main dashed ring */}
          <circle
            cx="50"
            cy="50"
            r="46"
            fill="none"
            stroke="#00F2FE"
            strokeWidth="1.5"
            strokeDasharray="60 15 30 15"
            className="opacity-80"
            style={{ transform: `rotate(${rotation}deg)`, transformOrigin: 'center' }}
          />
          
          {/* Secondary tick marks ring */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="rgba(0, 242, 254, 0.3)"
            strokeWidth="0.8"
            strokeDasharray="3 5"
            style={{ transform: `rotate(${-rotation * 0.5}deg)`, transformOrigin: 'center' }}
          />

          {/* Bracket notches at 0°, 90°, 180°, 270° */}
          {[0, 90, 180, 270].map((angle) => (
            <g key={angle} style={{ transform: `rotate(${angle + rotation}deg)`, transformOrigin: 'center' }}>
              <line
                x1="50"
                y1="8"
                x2="50"
                y2="14"
                stroke="rgba(0, 242, 254, 0.6)"
                strokeWidth="1.5"
              />
              <line
                x1="50"
                y1="86"
                x2="50"
                y2="92"
                stroke="rgba(0, 242, 254, 0.6)"
                strokeWidth="1.5"
              />
            </g>
          ))}
        </svg>

        {/* Rotating Tech Ring */}
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox="0 0 100 100"
          style={{ 
            animation: state === 'LISTENING' || state === 'SPEAKING' 
              ? 'spin 4s linear infinite' 
              : 'spin 12s linear infinite'
          }}
        >
          <circle
            cx="50"
            cy="50"
            r="38"
            fill="none"
            stroke="rgba(0, 242, 254, 0.2)"
            strokeWidth="1"
            strokeDasharray="20 40 10 40"
          />
        </svg>

        {/* Inner Glowing Core */}
        <div
          className="w-28 h-28 rounded-full flex items-center justify-center transition-all duration-300 border-2"
          style={{
            backgroundColor: colors.bg,
            borderColor: colors.border,
            boxShadow: `0 0 ${state === 'LISTENING' ? '30px' : '20px'} ${colors.glow}, inset 0 0 20px rgba(0, 242, 254, 0.2)`,
            transform: `scale(${pulseScale})`,
          }}
        >
          {/* Center Brand Text */}
          <span
            className="font-mono text-xs tracking-[0.35em] font-bold pl-1"
            style={{
              color: '#FFFFFF',
              textShadow: `0 0 10px ${colors.glow}`,
            }}
          >
            J.A.R.V.I.S.
          </span>
        </div>

        {/* Radial tick marks around outer edge */}
        {Array.from({ length: 36 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-px h-2 bg-cyan-400/30"
            style={{
              top: '4px',
              left: '50%',
              transformOrigin: '50% 76px',
              transform: `translateX(-50%) rotate(${i * 10}deg)`,
            }}
          />
        ))}
      </div>

      {/* State Text Indicator */}
      <div className="mt-4 flex items-center gap-2 font-mono text-xs tracking-widest">
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            state === 'ONLINE' ? 'bg-emerald-400' : 'bg-pink-500 animate-pulse'
          }`}
          style={{
            boxShadow: state === 'ONLINE' 
              ? '0 0 10px #00FF9D' 
              : `0 0 15px ${colors.glow}`,
          }}
        />
        <span
          className={`${
            state === 'ONLINE' 
              ? 'text-emerald-400' 
              : state === 'LISTENING'
              ? 'text-pink-400'
              : 'text-cyan-400'
          }`}
          style={{
            textShadow: `0 0 8px ${
              state === 'ONLINE' ? '#00FF9D' : colors.glow
            }`,
          }}
        >
          {state === 'ONLINE' && '● ONLINE'}
          {state === 'LISTENING' && '🎙 LISTENING, sir...'}
          {state === 'SPEAKING' && '🔊 SPEAKING'}
          {state === 'PROCESSING' && '⚙ PROCESSING'}
        </span>
      </div>

      {/* Active Model Pill */}
      <div
        className="mt-3 px-4 py-1 rounded-full border text-[10px] font-mono tracking-wide"
        style={{
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          borderColor: 'rgba(0, 242, 254, 0.3)',
          color: '#67E8F9',
          boxShadow: '0 0 10px rgba(0, 242, 254, 0.1)',
        }}
      >
        ◈ {activeModel}
      </div>
    </div>
  );
};
