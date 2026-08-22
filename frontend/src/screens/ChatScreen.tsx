import { useEffect, useMemo, useRef, useState } from 'react';
import { Send, Eraser, Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { getGraphMap } from '../lib/api';
import { JarvisHudWidget } from '../components/JarvisHudWidget';
import JarvisGraphBackdrop from '../components/JarvisGraphBackdrop';
import { ErrorBox } from '../components/ui';
import { colorOfType, labelOfType } from '../lib/graphColors';
import { links as linksWord, nodes as nodesWord } from '../lib/format';
import { useJarvisConversation } from '../lib/useJarvisConversation';
import type { GraphMap } from '../types';
import { useLang } from '../lib/i18n';
import '../styles/jarvis-hud.css';

// Визуал — из одобренного макета (artifact 07699535, «Джарвис — граф +
// кольцо», см. nexus-os-canonical-design), перенесён построчно 18.08.2026
// на этот, уже настоящий экран разговора (не выдуманный заново): фон-граф,
// топ-узлы и легенда — реальные данные с /api/graph/map, а не выдуманные
// числа макета. Кольцо — настоящий JarvisHudWidget, просто крупнее и справа,
// как в макете, а не перерисованный SVG с нуля.

// Разговор с Джарвисом прямо в системе. Это не второй мозг: экран стучится
// в тот же контур мышления, что и Телеграм, поэтому память, персоны,
// характер и скиллы здесь те же самые. Нить разговора у каналов раздельная —
// начатое в вебе не всплывёт в телефоне посреди дня.
//
// Кольцо наконец живёт по-настоящему: пока идёт ответ — «думаю», как
// пришёл — короткое «говорю», потом покой.

export default function ChatScreen() {
  const { t } = useLang();
  const {
    lines, text, setText, state, error, setError, personas, persona, setPersona,
    listening, voiceReady, speakBack, setSpeakBack,
    wakeMode, awake,
    say, toggleWakeMode, toggleMic, send, clear,
    speechSupported,
  } = useJarvisConversation(t);
  const feed = useRef<HTMLDivElement>(null);

  // Фон-граф и его боковые панели — второй мозг настоящий, не решает
  // ничего в разговоре, просто виден позади него
  const [graph, setGraph] = useState<GraphMap | null>(null);

  useEffect(() => {
    getGraphMap(400).then(setGraph).catch(() => {});
  }, []);

  // Топ-узлы по числу связей — те же вычисления, что на /graph, только
  // на своих пяти строчках для боковой панели, не на весь экран
  const topHubs = useMemo(() => {
    if (!graph) return [];
    const degree = new Map<string, number>();
    for (const e of graph.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    return graph.nodes
      .map((n) => ({ id: n.id, label: n.label, degree: degree.get(n.id) ?? 0 }))
      .filter((n) => n.degree > 0)
      .sort((a, b) => b.degree - a.degree)
      .slice(0, 5);
  }, [graph]);

  const legend = useMemo(() => {
    if (!graph) return [];
    return Object.entries(graph.stats.node_types).sort((a, b) => b[1] - a[1]);
  }, [graph]);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' });
  }, [lines, state]);

  return (
    <div className="jarvis-theme relative -m-8 h-screen overflow-hidden">
      {graph && <JarvisGraphBackdrop nodes={graph.nodes} edges={graph.edges} />}

      <div className="relative z-10 flex h-full">
        <div className="flex min-w-0 flex-1 flex-col p-6 lg:p-8">
          <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold lg:text-3xl" style={{ color: 'var(--ink)' }}>{t('Разговор')}</h1>
              <p className="mt-1 text-sm" style={{ color: 'var(--ink-dimmer)' }}>
                {t('Тот же Джарвис, что в Телеграме: общая память, общий характер. Нить разговора здесь своя.')}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {graph && (
                <span className="j-stat-chip">
                  {nodesWord(graph.stats.nodes)} · {linksWord(graph.stats.edges)}
                </span>
              )}
              <button onClick={clear} className="j-btn-ghost" title="Память фактов останется">
                <Eraser className="h-4 w-4" aria-hidden />
                {t('Начать заново')}
              </button>
            </div>
          </header>

          {error && (
            <div className="mb-3">
              <ErrorBox message={error} />
            </div>
          )}

          <div ref={feed} className="j-feed min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {lines.length === 0 && (
              <div className="mt-10 text-center text-sm" style={{ color: 'var(--ink-dimmer)' }}>
                {t('Спроси что угодно. Он помнит прошлые разговоры и твои заметки.')}
              </div>
            )}

            {lines.map((line, i) => {
              const mine = line.role === 'user';
              return (
                <div key={i} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
                      mine ? 'j-bubble-user' : 'j-bubble-bot'
                    }`}
                  >
                    {!mine && line.persona && (
                      <div className="j-bubble-persona mb-1 text-[11px] uppercase tracking-wider">
                        {line.persona}
                      </div>
                    )}
                    <p className="whitespace-pre-wrap break-words">{line.text}</p>
                    {!mine && voiceReady && (
                      <button
                        onClick={() => say(line.text)}
                        className="mt-2 flex cursor-pointer items-center gap-1 text-[11px] transition-colors duration-200 focus:outline-none"
                        style={{ color: 'var(--ink-dimmer)' }}
                      >
                        <Volume2 className="h-3 w-3" aria-hidden />
                        озвучить
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {state === 'PROCESSING' && (
              <div className="flex justify-start">
                <div className="j-bubble-bot rounded-lg px-4 py-2.5 text-sm">
                  {t('думаю…')}
                </div>
              </div>
            )}
          </div>

          {/* Персона и голосовые переключатели — с подписью текстом, не
              только значком, на своей строке. Раньше это были круглые
              значки без видимого текста, а потом всё это вместе с полем
              ввода стояло в одной строке с flex-wrap — на узком экране не
              хватало места, инпутбар схлопывался до нескольких пикселей и
              кнопка «Отправить» визуально наезжала на панель справа, хотя
              кликабельной там уже не была (заметка фаундера 19.08.2026:
              «джарвис не активна, не могу поговорить» — обе причины разом). */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <select
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              className="j-select"
              title="Кому адресовать. По умолчанию система выбирает сама по смыслу вопроса"
            >
              <option value="">{t('персона по смыслу')}</option>
              {personas.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>

            {speechSupported() && (
              <button
                onClick={toggleWakeMode}
                className={`j-btn-ghost ${wakeMode ? 'active' : ''}`}
                title={
                  wakeMode
                    ? 'Скажи «Джарвис» — он проснётся. «Джарвис, отключись» или минута тишины — уснёт'
                    : 'Откликаться на слово «Джарвис» — микрофон слушает постоянно, но ничего не отправляет, пока не услышит имя'
                }
              >
                {wakeMode ? <Mic className="h-4 w-4" aria-hidden /> : <MicOff className="h-4 w-4" aria-hidden />}
                {wakeMode ? (awake ? 'Слушаю — выключить' : 'Жду «Джарвис» — выключить') : 'Включить микрофон'}
              </button>
            )}

            {speechSupported() && (
              <button
                onClick={toggleMic}
                className={`j-btn-ghost ${listening ? 'active' : ''}`}
                title={listening ? 'Слушаю — нажми, чтобы остановить' : 'Сказать один раз голосом, без режима «по имени»'}
              >
                {listening ? <MicOff className="h-4 w-4" aria-hidden /> : <Mic className="h-4 w-4" aria-hidden />}
                {listening ? 'Слушаю…' : 'Голосом'}
              </button>
            )}

            <button
              onClick={() => setSpeakBack(!speakBack)}
              disabled={!voiceReady}
              className={`j-btn-ghost ${speakBack ? 'active' : ''}`}
              title={voiceReady ? 'Читать ответы вслух' : 'Голос выключен: NEXUS_TTS_ENGINE в .env'}
            >
              {speakBack ? <Volume2 className="h-4 w-4" aria-hidden /> : <VolumeX className="h-4 w-4" aria-hidden />}
              {speakBack ? 'Вслух' : 'Молча'}
            </button>
          </div>

          {/* Ввод — всегда на своей строке, во всю ширину */}
          <div className="j-inputbar mt-2 w-full">
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
              autoFocus
            />

            <button
              onClick={send}
              className="j-iconbtn send"
              disabled={!text.trim() || state === 'PROCESSING'}
              aria-label={t('Отправить')}
              title={t('Отправить') as string}
            >
              <Send className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>

        {/* Кольцо и второй мозг рядом с разговором — из макета «Джарвис»,
            позиция и размер кольца оттуда, содержимое панелей настоящее */}
        <aside
          className="relative hidden w-80 shrink-0 flex-col items-center justify-center gap-5 overflow-y-auto border-l p-6 xl:flex"
          style={{ borderColor: 'var(--line)' }}
        >
          {legend.length > 0 && (
            <div className="j-panel w-full">
              <h4>Слои</h4>
              {legend.map(([type, count]) => (
                <div key={type} className="j-row">
                  <span className="flex items-center gap-2">
                    <span className="j-dot" style={{ background: colorOfType(type), color: colorOfType(type) }} />
                    {labelOfType(type)}
                  </span>
                  <b>{count}</b>
                </div>
              ))}
            </div>
          )}

          <div className="my-2">
            <JarvisHudWidget state={state} activeModel={persona ? persona.toUpperCase() : ''} size={260} />
          </div>

          {topHubs.length > 0 && (
            <div className="j-panel w-full">
              <h4>Топ-узлы</h4>
              {topHubs.map((h) => (
                <div key={h.id} className="j-row">
                  <span className="truncate">{h.label}</span>
                  <b>{h.degree}</b>
                </div>
              ))}
            </div>
          )}

          <div
            className={`mt-1 flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs ${
              wakeMode ? 'border-pink-500/40 text-pink-300' : ''
            }`}
            style={wakeMode ? undefined : { borderColor: 'var(--line)', color: 'var(--ink-dimmer)' }}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                wakeMode ? 'bg-pink-400 animate-pulse motion-reduce:animate-none' : ''
              }`}
              style={wakeMode ? undefined : { background: 'var(--ink-dimmer)' }}
            />
            {wakeMode ? 'микрофон включён' : 'микрофон выключен'}
          </div>

          {wakeMode && (
            <p className="mt-2 max-w-[13rem] text-center text-[11px] leading-relaxed" style={{ color: 'var(--ink-dimmer)' }}>
              Слушает на твоём компьютере. Наружу ничего не уходит, пока не скажешь «Джарвис».
            </p>
          )}

          <p className="mt-4 max-w-[12rem] text-center text-xs leading-relaxed" style={{ color: 'var(--ink-dimmer)' }}>
            {state === 'PROCESSING'
              ? t('Собирает ответ: смотрит память, заметки и нить разговора.')
              : t('Готов. Память общая с Телеграмом.')}
          </p>
        </aside>
      </div>
    </div>
  );
}
