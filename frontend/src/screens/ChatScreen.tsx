import { useEffect, useRef, useState } from 'react';
import { Send, Eraser, Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { getChatHistory, getPersonas, getVoiceStatus, resetChat, sendChatMessage, speak } from '../lib/api';
import { listen, listenForWakeWord, speechSupported, type Listener } from '../lib/speech';
import { JarvisHudWidget, type JarvisState } from '../components/JarvisHudWidget';
import { BTN, BTN_GHOST, ErrorBox, INPUT } from '../components/ui';
import type { Persona } from '../types';
import { useLang } from '../lib/i18n';

// Разговор с Джарвисом прямо в системе. Это не второй мозг: экран стучится
// в тот же контур мышления, что и Телеграм, поэтому память, персоны,
// характер и скиллы здесь те же самые. Нить разговора у каналов раздельная —
// начатое в вебе не всплывёт в телефоне посреди дня.
//
// Кольцо наконец живёт по-настоящему: пока идёт ответ — «думаю», как
// пришёл — короткое «говорю», потом покой.

interface Line {
  role: string;
  text: string;
  persona?: string;
  at?: string;
}

export default function ChatScreen() {
  const { t } = useLang();
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState('');
  const [state, setState] = useState<JarvisState>('ONLINE');
  const [error, setError] = useState<string | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<string>('');
  const feed = useRef<HTMLDivElement>(null);

  // Голос: слушаем микрофон браузера, отвечаем файлом с бэкенда
  const [listening, setListening] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const [speakBack, setSpeakBack] = useState(false);
  const recognizer = useRef<Listener | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);

  // Режим «по имени»: микрофон открыт, но наружу ничего не уходит, пока не
  // прозвучало «Джарвис». Разбудили — отвечает и слушает дальше; минута
  // тишины или «Джарвис, отключись» — снова спит.
  const [wakeMode, setWakeMode] = useState(false);
  const [awake, setAwake] = useState(false);
  const awakeRef = useRef(false);
  const sleepTimer = useRef<number | null>(null);
  const wakeListener = useRef<Listener | null>(null);

  useEffect(() => {
    getChatHistory()
      .then((h) => setLines(h.messages))
      .catch(() => setError(t('Бэкенд недоступен. Запущен ли он на :8420?')));
    getPersonas().then(setPersonas).catch(() => {});
    getVoiceStatus()
      .then((v) => setVoiceReady(v.ready))
      .catch(() => setVoiceReady(false));
  }, []);

  // Произносит ответ вслух. Молча ничего не включаем: голос стоит трафика
  const say = async (text: string) => {
    try {
      const blob = await speak(text);
      player.current?.pause();
      const audio = new Audio(URL.createObjectURL(blob));
      player.current = audio;
      setState('SPEAKING');
      audio.onended = () => setState('ONLINE');
      await audio.play();
    } catch {
      setState('ONLINE');
      setError('Не удалось озвучить ответ.');
    }
  };

  // Засыпание: минута тишины возвращает Джарвиса в режим ожидания. Иначе
  // он продолжит отправлять всё, что услышит в комнате
  const armSleep = () => {
    if (sleepTimer.current) window.clearTimeout(sleepTimer.current);
    sleepTimer.current = window.setTimeout(() => {
      awakeRef.current = false;
      setAwake(false);
      setState('ONLINE');
    }, 60_000);
  };

  const wake = (rest: string) => {
    awakeRef.current = true;
    setAwake(true);
    setState('LISTENING');
    armSleep();
    // «Джарвис, поставь встречу завтра» — вопрос сказан сразу за именем
    if (rest.trim()) heard(rest.trim());
  };

  const heard = (said: string) => {
    // «Джарвис, отключись» — уходит спать, не отвечая
    if (/отключись|отбой|спасибо,?\s*всё|хватит|стоп/i.test(said)) {
      awakeRef.current = false;
      setAwake(false);
      setState('ONLINE');
      return;
    }
    armSleep();
    submit(said, true);
  };

  const toggleWakeMode = () => {
    if (wakeMode) {
      wakeListener.current?.stop();
      wakeListener.current = null;
      if (sleepTimer.current) window.clearTimeout(sleepTimer.current);
      awakeRef.current = false;
      setAwake(false);
      setWakeMode(false);
      setState('ONLINE');
      return;
    }

    setError(null);
    wakeListener.current = listenForWakeWord('ru-RU', {
      isAwake: () => awakeRef.current,
      onWake: wake,
      onCommand: heard,
      onError: (reason) => {
        setError(reason);
        setWakeMode(false);
      },
    });
    setWakeMode(Boolean(wakeListener.current));
  };

  const toggleMic = () => {
    if (listening) {
      recognizer.current?.stop();
      setListening(false);
      return;
    }
    setError(null);
    setState('LISTENING');
    setListening(true);
    recognizer.current = listen(
      'ru-RU',
      (final) => {
        setListening(false);
        setState('ONLINE');
        setText((prev) => (prev ? `${prev} ${final}` : final));
      },
      (partial) => setText(partial),
      (reason) => {
        setListening(false);
        setState('ONLINE');
        setError(reason);
      },
    );
  };

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' });
  }, [lines, state]);

  // Уходя с экрана, отпускаем микрофон: он не должен слушать комнату,
  // когда человек ушёл на другую страницу
  useEffect(() => {
    return () => {
      wakeListener.current?.stop();
      recognizer.current?.stop();
      if (sleepTimer.current) window.clearTimeout(sleepTimer.current);
      player.current?.pause();
    };
  }, []);

  const send = async () => {
    await submit(text.trim());
  };

  const submit = async (value: string, speakReply = false) => {
    if (!value || state === 'PROCESSING') return;

    setLines((prev) => [...prev, { role: 'user', text: value }]);
    setText('');
    setState('PROCESSING');
    setError(null);

    try {
      const res = await sendChatMessage(value, persona || undefined);
      setLines((prev) => [...prev, { role: 'assistant', text: res.reply, persona: res.persona }]);
      if ((speakBack || speakReply) && voiceReady) {
        say(res.reply);
      } else {
        // Короткое «говорю» — чтобы было видно, что ответ только что пришёл
        setState('SPEAKING');
        setTimeout(() => setState('ONLINE'), 1600);
      }
    } catch (e: any) {
      setState('ONLINE');
      setError(e?.response?.data?.detail ?? t('Ответ не пришёл.'));
    }
  };

  const clear = async () => {
    try {
      await resetChat();
      setLines([]);
    } catch {
      setError('Не удалось очистить нить.');
    }
  };

  return (
    <div className="-m-8 flex h-screen">
      <div className="flex min-w-0 flex-1 flex-col p-6 lg:p-8">
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white lg:text-3xl">{t('Разговор')}</h1>
            <p className="mt-1 text-sm text-gray-400">
              {t('Тот же Джарвис, что в Телеграме: общая память, общий характер. Нить разговора здесь своя.')}
            </p>
          </div>
          <button onClick={clear} className={BTN_GHOST} title="Память фактов останется">
            <Eraser className="h-4 w-4" aria-hidden />
            {t('Начать заново')}
          </button>
        </header>

        {error && (
          <div className="mb-3">
            <ErrorBox message={error} />
          </div>
        )}

        <div ref={feed} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {lines.length === 0 && (
            <div className="mt-10 text-center text-sm text-gray-500">
              {t('Спроси что угодно. Он помнит прошлые разговоры и твои заметки.')}
            </div>
          )}

          {lines.map((line, i) => {
            const mine = line.role === 'user';
            return (
              <div key={i} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
                    mine
                      ? 'bg-primary/15 text-gray-100'
                      : 'border border-gray-800 bg-dark text-gray-200'
                  }`}
                >
                  {!mine && line.persona && (
                    <div className="mb-1 font-mono text-[11px] uppercase tracking-wider text-gray-500">
                      {line.persona}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap break-words">{line.text}</p>
                  {!mine && voiceReady && (
                    <button
                      onClick={() => say(line.text)}
                      className="mt-2 flex cursor-pointer items-center gap-1 text-[11px] text-gray-500 transition-colors duration-200 hover:text-primary focus:outline-none focus:ring-1 focus:ring-primary"
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
              <div className="rounded-lg border border-gray-800 bg-dark px-4 py-2.5 text-sm text-gray-400">
                {t('думаю…')}
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <select
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="cursor-pointer rounded-md border border-gray-800 bg-darker px-3 py-2 text-sm text-gray-200 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
            title="Кому адресовать. По умолчанию система выбирает сама по смыслу вопроса"
          >
            <option value="">{t('персона по смыслу')}</option>
            {personas.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>

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
            className={`${INPUT} flex-1`}
            autoFocus
          />

          {speechSupported() && (
            <button
              onClick={toggleWakeMode}
              className={`${BTN_GHOST} ${
                wakeMode ? (awake ? 'border-pink-500/60 text-pink-300' : 'border-primary/50 text-primary') : ''
              }`}
              title={
                wakeMode
                  ? 'Скажи «Джарвис» — он проснётся. «Джарвис, отключись» или минута тишины — уснёт'
                  : 'Откликаться на слово «Джарвис»'
              }
            >
              {wakeMode ? <Mic className="h-4 w-4" aria-hidden /> : <MicOff className="h-4 w-4" aria-hidden />}
              {wakeMode ? (awake ? 'Слушаю' : 'Жду «Джарвис»') : 'По имени'}
            </button>
          )}

          {speechSupported() && (
            <button
              onClick={toggleMic}
              className={`${BTN_GHOST} ${listening ? 'border-pink-500/50 text-pink-300' : ''}`}
              title={listening ? 'Слушаю — нажми, чтобы остановить' : 'Говорить голосом'}
            >
              {listening ? <MicOff className="h-4 w-4" aria-hidden /> : <Mic className="h-4 w-4" aria-hidden />}
              {listening ? 'Слушаю…' : 'Голосом'}
            </button>
          )}

          <button
            onClick={() => setSpeakBack(!speakBack)}
            disabled={!voiceReady}
            className={`${BTN_GHOST} ${speakBack ? 'border-primary/50 text-primary' : ''}`}
            title={
              voiceReady
                ? 'Читать ответы вслух'
                : 'Голос выключен: NEXUS_TTS_ENGINE в .env'
            }
          >
            {speakBack ? <Volume2 className="h-4 w-4" aria-hidden /> : <VolumeX className="h-4 w-4" aria-hidden />}
            {speakBack ? 'Вслух' : 'Молча'}
          </button>

          <button onClick={send} className={BTN} disabled={!text.trim() || state === 'PROCESSING'}>
            <Send className="h-4 w-4" aria-hidden />
            {t('Отправить')}
          </button>
        </div>
      </div>

      {/* Кольцо рядом с разговором: видно состояние, а не только текст */}
      <aside className="hidden w-72 shrink-0 flex-col items-center justify-center border-l border-gray-800 bg-darker xl:flex">
        <JarvisHudWidget state={state} activeModel={persona ? persona.toUpperCase() : ''} />
        <p className="mt-6 max-w-[12rem] text-center text-xs leading-relaxed text-gray-500">
          {state === 'PROCESSING'
            ? t('Собирает ответ: смотрит память, заметки и нить разговора.')
            : t('Готов. Память общая с Телеграмом.')}
        </p>
      </aside>
    </div>
  );
}
