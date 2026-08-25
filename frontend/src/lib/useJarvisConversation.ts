import { useEffect, useRef, useState } from 'react';
import { getChatHistory, getPersonas, getVoiceStatus, resetChat, sendChatMessageStream, speakStreamUrl } from './api';
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

// Режет уже пришедший (но ещё не отправленный на озвучку) хвост текста на
// законченные предложения. Требует НАСТОЯЩИЙ пробел/перенос после точки —
// не достраиваем конец по концу текущего буфера ($ здесь нарочно нет):
// поток ещё не закончился, и то, что сейчас выглядит как конец фразы,
// может оказаться серединой следующего куска. Последний обрывок без
// пробела после — забота вызывающего кода, досказать в конце потока.
function extractReadySentences(buffer: string): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  let rest = buffer;
  const boundary = /[.!?…]+[)"'»]?\s+/;
  for (;;) {
    const m = rest.match(boundary);
    if (!m || m.index === undefined) break;
    const end = m.index + m[0].length;
    const piece = rest.slice(0, end).trim();
    rest = rest.slice(end);
    if (piece) sentences.push(piece);
  }
  return { sentences, rest };
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

  // Очередь озвучки — 23.08.2026, вместе со стримингом: ответ теперь может
  // озвучиваться по предложениям, готовым ещё до того, как модель дописала
  // остальное, а не одним куском в самом конце. speaking — идёт ли сейчас
  // реальное воспроизведение; очередь просто ждёт своего audio.onended.
  const speechQueue = useRef<string[]>([]);
  const speaking = useRef(false);

  const stopSpeech = () => {
    speechQueue.current = [];
    speaking.current = false;
    player.current?.pause();
  };

  const pumpSpeech = () => {
    if (speaking.current) return;
    const next = speechQueue.current.shift();
    if (!next) return;
    speaking.current = true;
    const resume = () => {
      speaking.current = false;
      if (speechQueue.current.length > 0) {
        pumpSpeech();
      } else {
        wakeListener.current?.unmute?.();
        setState('ONLINE');
      }
    };
    try {
      // audio.src, а не blob целиком: браузер грузит поток сам, начинает
      // играть по первым пришедшим байтам, не ждёт синтеза всей фразы.
      const audio = new Audio(speakStreamUrl(next));
      player.current = audio;
      setState('SPEAKING');
      wakeListener.current?.mute?.();
      audio.onended = resume;
      audio.onerror = resume;
      audio.play().catch(() => {
        setError('Не удалось озвучить ответ.');
        resume();
      });
    } catch {
      setError('Не удалось озвучить ответ.');
      resume();
    }
  };

  const enqueueSpeech = (piece: string) => {
    if (!piece.trim()) return;
    speechQueue.current.push(piece);
    pumpSpeech();
  };

  /** Одна законченная фраза вне очереди стрима — например, «Джарвис,
   * покажись» подтверждает голосом сам себя. Сбрасывает то, что играло. */
  const say = (text: string) => {
    stopSpeech();
    enqueueSpeech(text);
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

  // Перебили Джарвиса, пока она говорила — «стоп» (rest === null, просто
  // замолкаем) или «Джарвис[, вопрос]» поверх её речи (rest — как обычное
  // пробуждение, wake() сам решит, ждать команду дальше или сразу её
  // выполнить). До 23.08.2026 такого пути не было вообще: пока играл звук,
  // микрофон был полностью глух — фаундер вживую пожаловался, что она не
  // останавливается ни на «стоп», ни когда он просто начинает говорить.
  const onInterrupt = (rest: string | null) => {
    stopSpeech();
    if (rest === null) {
      awakeRef.current = false;
      setAwake(false);
      setState('ONLINE');
      if (sleepTimer.current) window.clearTimeout(sleepTimer.current);
      return;
    }
    wake(rest);
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
          onInterrupt,
          onError: setError,
        })
      : listenForWakeWord('ru-RU', {
          isAwake: () => awakeRef.current,
          onWake: wake,
          onCommand: heard,
          onInterrupt,
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
    // Взялись за микрофон — Джарвис замолкает немедленно. 24.08.2026:
    // фаундер жаловался, что тот не останавливается, когда он начинает
    // говорить. Перебивание было, но только в режиме «по имени» — кнопка
    // «Голосом» его не прерывала, и человек говорил поверх чужой речи.
    stopSpeech();
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
      stopSpeech();
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
    // Новый вопрос — то, что ещё доигрывало от прошлого ответа, больше не
    // актуально (тот же случай, что и say(): не смешивать очереди).
    stopSpeech();

    const wantsVoice = (speakBack || speakReply) && voiceReady;
    let assistantIndex = -1;
    let full = '';
    let unspoken = '';

    setLines((prev) => {
      assistantIndex = prev.length;
      return [...prev, { role: 'assistant', text: '', persona: undefined }];
    });

    try {
      for await (const ev of sendChatMessageStream(value, persona || undefined)) {
        if (ev.error) throw new Error(ev.error);

        if (ev.delta) {
          full += ev.delta;
          unspoken += ev.delta;
          const idx = assistantIndex;
          setLines((prev) => {
            const next = [...prev];
            next[idx] = { ...next[idx], text: full };
            return next;
          });

          if (wantsVoice) {
            const { sentences, rest } = extractReadySentences(unspoken);
            unspoken = rest;
            sentences.forEach(enqueueSpeech);
          }
        }

        if (ev.done && ev.persona) {
          const idx = assistantIndex;
          setLines((prev) => {
            const next = [...prev];
            next[idx] = { ...next[idx], persona: ev.persona };
            return next;
          });
        }
      }

      if (wantsVoice) {
        // Последний обрывок без завершающей пунктуации — поток кончился,
        // достраивать больше нечего, озвучиваем как есть.
        if (unspoken.trim()) enqueueSpeech(unspoken);
        if (!speaking.current && speechQueue.current.length === 0) {
          setState('ONLINE');
        }
      } else {
        setState('SPEAKING');
        setTimeout(() => setState('ONLINE'), 1600);
      }
    } catch (e: any) {
      setState('ONLINE');
      setError(e?.response?.data?.detail ?? e?.message ?? t('Ответ не пришёл.'));
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
