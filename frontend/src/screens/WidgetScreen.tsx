import { useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Send, Volume2, VolumeX, X } from 'lucide-react';
import { JarvisHudWidget } from '../components/JarvisHudWidget';
import { useJarvisConversation } from '../lib/useJarvisConversation';
import { isElectronWidget } from '../lib/speech';
import { useLang } from '../lib/i18n';
import '../styles/jarvis-hud.css';

// Плавающий виджет поверх рабочего стола (не только вкладки браузера) —
// шаг 1 из договорённости с фаундером 19.08.2026. Тот же хук
// useJarvisConversation, что у полного экрана «Разговор»
// (frontend/src/screens/ChatScreen.tsx) — тот же голос, та же память, та же
// нить: два вида на одно состояние, не отдельная копия.
//
// 19.08.2026, второй заход: фаундер прислал референс — просто светящееся
// кольцо на экране, без тёмной коробки вокруг. Кольцо здесь настоящее (тот
// же компонент, что и в «Разговоре»), не статичная картинка — не стали
// генерировать через Higgsfield, потому что картинка не гаснет и не
// оживает от реального состояния. Окно прозрачное (main.js), панель
// разговора проявляется только при наведении — в покое виден один круг.
//
// Прячется, а не закрывается: крестик и правый клик у main.js вызывают
// win.hide(), страница продолжает жить и слушать «Джарвис, покажись» —
// stopOnHide:false и onCommand ниже. Настоящий выход — только через пункт
// «Выйти совсем» в контекстном меню.
//
// Рендерится отдельным маршрутом /widget без сайдбара (см. App.tsx).

declare global {
  interface Window {
    nexusWidgetAPI?: {
      hide: () => void;
      show: () => void;
      quit: () => void;
      contextMenu: () => void;
    };
  }
}

const SHOW_PHRASE = /покажись|вернись|появись|где ты/i;

export default function WidgetScreen() {
  const { t } = useLang();
  const [hovered, setHovered] = useState(false);
  const {
    lines, text, setText, state, error,
    voiceReady, speakBack, setSpeakBack,
    wakeMode, toggleWakeMode, listening, toggleMic, send,
    speechSupported,
  } = useJarvisConversation(t, {
    stopOnHide: false,
    onCommand: (said) => {
      if (SHOW_PHRASE.test(said)) {
        window.nexusWidgetAPI?.show();
        return true;
      }
      return false;
    },
  });
  const feed = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' });
  }, [lines, state]);

  // Убирает сплошной фон body — иначе прозрачность окна Electron не видна
  useEffect(() => {
    document.body.classList.add('widget-transparent');
    return () => document.body.classList.remove('widget-transparent');
  }, []);

  const last = lines.slice(-2);

  const hide = () => {
    if (window.nexusWidgetAPI) window.nexusWidgetAPI.hide();
    else window.close(); // обычная вкладка браузера, не Electron
  };

  return (
    <div
      className="flex h-screen w-screen flex-col items-center justify-start pt-2"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onContextMenu={(e) => {
        e.preventDefault();
        window.nexusWidgetAPI?.contextMenu();
      }}
      style={{ background: 'transparent', WebkitAppRegion: 'drag' } as any}
    >
      {/* В покое — только кольцо на прозрачном фоне, как просил фаундер.
          palette="vivid" — яркая бирюза с сильным свечением, не тусклый
          графит основного интерфейса: на живом рабочем столе поверх
          случайного фона тусклое кольцо не читалось как круг вообще.
          alert — красный обод при настоящей ошибке (голос/бэкенд), зелёный
          в остальное время: цвет несёт смысл, не просто «добавили красный». */}
      <JarvisHudWidget state={state} size={150} palette="vivid" alert={!!error} />

      {hovered && (
        <button
          onClick={hide}
          className="j-iconbtn"
          style={{ position: 'absolute', top: 6, right: 6, width: 24, height: 24, WebkitAppRegion: 'no-drag' } as any}
          aria-label="Спрятать (вернуть — Alt+J)"
          title="Спрятать. Вернуть: Alt+J из любой программы"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}

      {/* Панель разговора — проявляется по наведению, в покое не мешает
          кольцу светиться в одиночестве */}
      <div
        className="jarvis-theme mt-1 w-full flex-1 overflow-hidden rounded-xl p-2.5 transition-opacity duration-200"
        style={{
          background: 'rgba(10,13,16,0.88)',
          opacity: hovered ? 1 : 0,
          pointerEvents: hovered ? 'auto' : 'none',
          WebkitAppRegion: 'no-drag',
        } as any}
      >
        <div ref={feed} className="j-feed max-h-16 overflow-y-auto p-1.5 text-[11px] leading-snug">
          {last.length === 0 && (
            <p style={{ color: 'var(--ink-dimmer)' }}>{t('Спроси что угодно.')}</p>
          )}
          {last.map((line, i) => (
            <p key={i} className={line.role === 'user' ? '' : 'j-bubble-persona'} style={line.role === 'user' ? { color: 'var(--ink)' } : undefined}>
              {line.role === 'user' ? '› ' : ''}{line.text}
            </p>
          ))}
        </div>

        {error && (
          <p className="mt-1 truncate text-[10px]" style={{ color: '#f38ba8' }} title={error}>
            {error}
          </p>
        )}

        <div className="mt-1.5 flex items-center gap-1.5">
          {/* Electron: браузерное распознавание не работает, но с
              19.08.2026 «по имени» здесь всё равно доступно — через
              локальный офлайн-сервер wakeword/server.py (Vosk), а не через
              webkitSpeechRecognition. Кнопка одна и та же, toggleWakeMode()
              сам выбирает путь внутри (см. useJarvisConversation.ts). Если
              сервер не запущен — ошибка увидна в error ниже, не молчит. */}
          {(speechSupported() || isElectronWidget()) && (
            <button
              onClick={toggleWakeMode}
              className={`j-iconbtn ${wakeMode ? 'on' : ''}`}
              style={{ width: 26, height: 26 }}
              aria-label={wakeMode ? 'Откликаться на слово «Джарвис» — выключить' : 'Откликаться на слово «Джарвис»'}
              title={
                wakeMode
                  ? 'Слушаю «Джарвис» — нажми, чтобы выключить'
                  : isElectronWidget()
                    ? 'Откликаться на слово «Джарвис» (нужен запущенный wakeword/start.ps1)'
                    : 'Откликаться на слово «Джарвис»'
              }
            >
              {wakeMode ? <Mic className="h-3 w-3" aria-hidden /> : <MicOff className="h-3 w-3" aria-hidden />}
            </button>
          )}

          {/* Разовая запись голосом («Голосом» на полном экране «Разговор»,
              см. ChatScreen.tsx) — здесь этой кнопки не было вовсе, хотя сам
              хук уже умел записывать и слать на бэкенд для Electron
              (toggleMic → record() → Gemini, см. useJarvisConversation.ts).
              Найдено 19.08.2026 вживую фаундером: «микрофон не работает» —
              кнопки для push-to-talk в самом виджете физически не было. */}
          {(speechSupported() || isElectronWidget()) && (
            <button
              onClick={toggleMic}
              className={`j-iconbtn ${listening ? 'on' : ''}`}
              style={{ width: 26, height: 26 }}
              aria-label={listening ? 'Слушаю — нажми, чтобы остановить' : 'Сказать голосом'}
              title={listening ? 'Слушаю — нажми, чтобы остановить' : 'Сказать один раз голосом'}
            >
              {listening ? <MicOff className="h-3 w-3" aria-hidden /> : <Mic className="h-3 w-3" aria-hidden />}
            </button>
          )}

          <button
            onClick={() => setSpeakBack(!speakBack)}
            disabled={!voiceReady}
            className={`j-iconbtn ${speakBack ? 'on' : ''}`}
            style={{ width: 26, height: 26 }}
            aria-label={speakBack ? 'Читать ответы вслух — выключить' : 'Читать ответы вслух'}
            title={voiceReady ? 'Читать ответы вслух' : 'Голос выключен: NEXUS_TTS_ENGINE в .env'}
          >
            {speakBack ? <Volume2 className="h-3 w-3" aria-hidden /> : <VolumeX className="h-3 w-3" aria-hidden />}
          </button>

          <div className="j-inputbar min-w-0 flex-1" style={{ padding: '3px 3px 3px 8px' }}>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={t('Сообщение…')}
              style={{ fontSize: '0.72rem' }}
            />
            <button
              onClick={send}
              className="j-iconbtn send"
              disabled={!text.trim() || state === 'PROCESSING'}
              style={{ width: 22, height: 22 }}
              aria-label={t('Отправить')}
              title={t('Отправить') as string}
            >
              <Send className="h-3 w-3" aria-hidden />
            </button>
          </div>
        </div>

        {wakeMode && (
          <p className="mt-1 truncate text-[10px]" style={{ color: 'var(--ink-dimmer)' }}>
            {t('Скажи «Джарвис, покажись», если спрячу')}
          </p>
        )}
        {isElectronWidget() && (
          <p className="mt-1 truncate text-[10px]" style={{ color: 'var(--ink-dimmer)' }} title="Окно можно вернуть и без голоса — Alt+J работает из любой программы">
            {t('Скрыл — верни Alt+J')}
          </p>
        )}
      </div>
    </div>
  );
}
