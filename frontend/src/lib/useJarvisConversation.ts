import { useEffect, useRef, useState } from 'react';
import { getChatHistory, getPersonas, getVoiceStatus, resetChat, sendChatMessage, speakStreamUrl } from './api';
import {
  isElectronWidget,
  listen,
  listenForWakeWord,
  listenForWakeWordElectron,
  record,
  speechSupported,
  type Listener,
} from './speech';
import type { JarvisState } from '../components/JarvisHudWidget';
import type { Persona } from '../types';

// Вся логика разговора с Джарвисом — история, отправка, голос, режим «по
// имени» — жила только в ChatScreen.tsx. Вынесена сюда 19.08.2026, когда
// понадобился второй, компактный экран (плавающий виджет поверх рабочего
// стола, см. WidgetScreen.tsx): дублировать двести строк состояния под
// разными экранами значило бы чинить голос в двух местах при каждом баге,
// как уже было с кнопками сегодня. ChatScreen и WidgetScreen — два вида
// на один и тот же хук, не две независимые копии.

export interface Line {
  role: string;
  text: string;
  persona?: string;
  at?: string;
}

export interface JarvisConversationOptions {
  /**
   * Глушить микрофон, когда вкладка/окно скрывается. По умолчанию true —
   * это поведение ChatScreen (ушёл со страницы — микрофон не должен
   * слушать комнату). Плавающий виджет (WidgetScreen) передаёт false: его
   * весь смысл — «спрятался, но отзовётся на голос», окно там прячется
   * (win.hide), а не закрывается, страница продолжает жить и слушать.
   */
  stopOnHide?: boolean;
  /**
   * Перехват произнесённой команды до того, как она уйдёт в чат — вернуть
   * true, если команда обработана и в чат её отправлять не нужно (по
   * образцу уже существующего «отключись»). Виджет ловит здесь «покажись»
   * и подобное, чтобы вернуть спрятанное окно голосом.
   */
  onCommand?: (said: string) => boolean;
}

export function useJarvisConversation(t: (s: string) => string, opts: JarvisConversationOptions = {}) {
  const { stopOnHide = true, onCommand } = opts;
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState('');
  const [state, setState] = useState<JarvisState>('ONLINE');
  const [error, setError] = useState<string | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<string>('');

  const [listening, setListening] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const [speakBack, setSpeakBack] = useState(false);
  const recognizer = useRef<Listener | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);

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

  const say = async (text: string) => {
    const resume = () => {
      wakeListener.current?.unmute?.();
      setState('ONLINE');
    };
    try {
      player.current?.pause();
      // audio.src, а не blob целиком: браузер грузит поток сам, начинает
      // играть по первым пришедшим байтам, не ждёт синтеза всей фразы.
      const audio = new Audio(speakStreamUrl(text));
      player.current = audio;
      setState('SPEAKING');
      wakeListener.current?.mute?.();
      audio.onended = resume;
      audio.onerror = resume;
      await audio.play();
    } catch {
      wakeListener.current?.unmute?.();
      setState('ONLINE');
      setError('Не удалось озвучить ответ.');
    }
  };

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
    if (rest.trim()) heard(rest.trim());
  };

  const heard = (said: string) => {
    if (/отключись|отбой|спасибо,?\s*всё|хватит|стоп/i.test(said)) {
      awakeRef.current = false;
      setAwake(false);
      setState('ONLINE');
      return;
    }
    if (onCommand?.(said)) {
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
    // Electron: браузерное распознавание физически не работает (см.
    // speech.ts) — «по имени» здесь идёт через локальный офлайн-сервер
    // wakeword/server.py (Vosk), не через webkitSpeechRecognition. Тот же
    // Listener-контракт, тот же WAKE-регексп — вызывающему коду (здесь)
    // разницы не видно, найдено и починено 19.08.2026 вечером.
    wakeListener.current = isElectronWidget()
      ? listenForWakeWordElectron({
          isAwake: () => awakeRef.current,
          onWake: wake,
          onCommand: heard,
          onError: setError,
        })
      : listenForWakeWord('ru-RU', {
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

    const onFinal = (final: string) => {
      setListening(false);
      setState('ONLINE');
      if (!final.trim()) return;
      // «Джарвис, покажись» работает и push-to-talk кнопкой, не только
      // режимом «по имени» (которого в Electron нет) — раньше onCommand
      // проверялся только внутри heard(), а сюда вообще не заглядывал,
      // поэтому в виджете эта фраза голосом не срабатывала никак, только
      // Alt+J (найдено код-ревью 19.08.2026)
      if (onCommand?.(final)) return;
      // Раньше только вставляло текст в поле — фаундер жаловался вживую
      // 19.08.2026, что «Голосом» иногда просто молчит: он говорил и не
      // понимал, что нужен ещё один клик «Отправить». Push-to-talk —
      // это разговор, не диктовка: отправляем сразу, как только слово
      // распознано и озвучиваем ответ голосом, тем же путём, что и
      // «по имени».
      submit(final.trim(), true);
    };
    const onError = (reason: string) => {
      setListening(false);
      setState('ONLINE');
      setError(reason);
    };

    // Electron-виджет: браузерное распознавание там не работает (см.
    // speech.ts) — пишем звук и шлём на бэкенд вместо потоковых partial.
    if (isElectronWidget()) {
      // record() асинхронная (спрашивает разрешение на микрофон, поднимает
      // MediaRecorder) — если человек успел нажать «стоп» до того, как это
      // разрешилось, recognizer.current в момент клика ещё null, и старый
      // stop() ничего не остановит; когда промис всё же разрешится, микрофон
      // останется висеть в фоне без ссылки, чтобы его выключить. cancelled
      // ловит именно этот момент (найдено код-ревью 19.08.2026)
      let cancelled = false;
      recognizer.current = { stop: () => { cancelled = true; } };
      record(onFinal, onError).then((listener) => {
        if (cancelled) {
          listener?.stop();
          return;
        }
        recognizer.current = listener;
      });
      return;
    }

    recognizer.current = listen('ru-RU', onFinal, (partial) => setText(partial), onError);
  };

  // Свернул окно/вкладку — микрофон отпускаем. Человек не должен гадать,
  // слушает браузер в фоне или нет. Виджет просит не глушить wake-режим
  // (stopOnHide: false) — его и прячут именно затем, чтобы вернуть потом
  // голосом. Но разовую запись (push-to-talk) это не касается — нет
  // причины продолжать её в свёрнутое окно; раньше это не проверялось
  // вообще (найдено код-ревью 19.08.2026): скрыл виджет посреди фразы —
  // микрофон так и остался бы висеть без остановки.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState !== 'hidden') return;

      if (recognizer.current) {
        recognizer.current.stop();
        recognizer.current = null;
        setListening(false);
      }

      if (!stopOnHide || !wakeListener.current) return;
      wakeListener.current.stop();
      wakeListener.current = null;
      awakeRef.current = false;
      setAwake(false);
      setWakeMode(false);
      setState('ONLINE');
    };
    document.addEventListener('visibilitychange', onHide);
    return () => document.removeEventListener('visibilitychange', onHide);
  }, [stopOnHide]);

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

  return {
    lines, text, setText, state, error, setError, personas, persona, setPersona,
    listening, voiceReady, speakBack, setSpeakBack,
    wakeMode, awake,
    say, toggleWakeMode, toggleMic, send, submit, clear,
    speechSupported,
  };
}
