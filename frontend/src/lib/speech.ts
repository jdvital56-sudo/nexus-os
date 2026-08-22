// Распознавание речи в браузере. Встроено в Chrome и Edge, ничего не весит
// и ничего не стоит — поэтому для ввода голосом в вебе берём его, а не
// отправляем звук на бэкенд.
//
// Telegram-канал устроен иначе: там голосовое приходит файлом и
// расшифровывается на сервере через Gemini. Это разные пути намеренно —
// в браузере уже есть готовое ухо, гонять байты незачем.
//
// 19.08.2026: у плавающего виджета (Electron) готового уха на самом деле
// нет — webkitSpeechRecognition в Electron физически не работает:
// облачная служба Google проверяет API-ключ, зашитый только в настоящую
// сборку Chrome, у Chromium внутри Electron его нет. Симптом на экране
// фаундера — «Распознавание не смогло выйти в сеть» и полная тишина на
// «Джарвис, ты слышишь меня?». API существует и не бросает ошибку сразу
// (speechSupported() честно отвечает true), падает только в момент самого
// распознавания — поэтому этот случай не отличить проверкой типа заранее,
// определяем среду явно (см. record() ниже) и в Electron идём путём
// Telegram: пишем звук, шлём файл на /api/voice/transcribe, там Gemini.

type Recognition = any;

export function speechSupported(): boolean {
  return typeof window !== 'undefined' &&
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

/** true — мы внутри Electron-виджета, где облачное распознавание Chrome не работает. */
export function isElectronWidget(): boolean {
  return typeof window !== 'undefined' && Boolean((window as any).nexusWidgetAPI);
}

export interface Listener {
  stop: () => void;
  /** Заглушить распознавание, не останавливая поток — например, пока играет TTS. */
  mute?: () => void;
  unmute?: () => void;
}

// «Джарвис», «джарвиса», «джарвес» — распознавание слышит имя по-разному.
// Модульная область, не внутри одной функции: тот же регексп нужен и
// listenForWakeWord() (браузер), и listenForWakeWordElectron() (Electron,
// см. ниже) — один источник правды для того, что считается именем, а не
// два независимых определения, которые могут разойтись.
const WAKE = /дж[аяе]рв[иеё]с\w*/i;

// Сколько ждём после unmute(), прежде чем реально снова слушать — против
// хвоста собственной озвучки Джарвиса, см. комментарий в mute()/unmute()
// listenForWakeWord() ниже. Общая константа — то же соображение обязано
// работать одинаково что в браузере, что через wakeword/server.py.
const UNMUTE_DELAY_MS = 500;

/**
 * Непрерывное слушание с пробуждением по слову.
 *
 * Микрофон открыт всё время, но наружу ничего не уходит: пока не прозвучало
 * «Джарвис», распознанное просто выбрасывается. Это важная разница — «всегда
 * слушает» и «всегда отправляет» не одно и то же.
 *
 * Браузер сам обрывает распознавание каждые несколько секунд — поэтому
 * перезапускаем его, пока режим включён.
 */
export function listenForWakeWord(
  lang: string,
  handlers: {
    onWake: (rest: string) => void;
    onCommand: (text: string) => void;
    onPartial?: (text: string) => void;
    onError?: (reason: string) => void;
    isAwake: () => boolean;
  },
): Listener | null {
  const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!Ctor) {
    handlers.onError?.('Браузер не умеет распознавать речь. Chrome или Edge умеют.');
    return null;
  }

  let stopped = false;
  // Пока Джарвис говорит сам, микрофон физически продолжает слушать браузерное
  // распознавание — иначе поток приходится пересоздавать. Но результат, пока
  // muted, просто выбрасывается: иначе колонки эхом уходят обратно в диалог,
  // и Джарвис отвечает сам себе.
  //
  // 19.08.2026, найдено фаундером вживую: этого флага одного было мало —
  // Джарвис слышал хвост собственной озвучки и отвечал сам себе, потом
  // отвечал уже на СВОЙ новый хвост, и так по кругу. Причина — задержка
  // распознавания: onresult с результатом озвучки Джарвиса иногда прилетает
  // уже ПОСЛЕ audio.onended, когда unmute() успел снять флаг. Одного
  // булева флага мало против этой гонки — здесь ещё и по-настоящему
  // останавливаем распознавание на время речи (abort(), не просто
  // игнорируем results) и возвращаем его с небольшой задержкой, чтобы
  // отдать хвосту шанс долететь и быть отброшенным, пока muted ещё true.
  let muted = false;
  let intentionalStop = false;
  let unmuteTimer: number | null = null;
  const rec: Recognition = new Ctor();
  rec.lang = lang;
  rec.continuous = true;
  rec.interimResults = true;

  rec.onresult = (event: any) => {
    if (muted) return;
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const said = String(result[0].transcript).trim();
      if (!result.isFinal) {
        handlers.onPartial?.(said);
        continue;
      }

      if (handlers.isAwake()) {
        handlers.onCommand(said);
        continue;
      }

      const match = said.match(WAKE);
      if (match) {
        // Всё, что сказано после имени, — уже вопрос
        const rest = said.slice((match.index ?? 0) + match[0].length).replace(/^[\s,.!?—-]+/, '');
        handlers.onWake(rest);
      }
    }
  };

  rec.onerror = (event: any) => {
    if (event.error === 'no-speech' || event.error === 'aborted') return;
    const reasons: Record<string, string> = {
      'not-allowed': 'Микрофон запрещён в настройках браузера.',
      'audio-capture': 'Микрофон не найден.',
      network: 'Распознавание не смогло выйти в сеть.',
    };
    handlers.onError?.(reasons[event.error] ?? `Распознавание сломалось: ${event.error}`);
  };

  // Браузер обрывает поток сам — поднимаем обратно, пока режим включён.
  // intentionalStop — это НАШ abort() на время речи Джарвиса (см. mute()
  // ниже), не естественный обрыв потока браузером: тут авто-restart не
  // нужен, unmute() поднимет распознавание сам, с задержкой.
  rec.onend = () => {
    if (stopped || intentionalStop) return;
    try {
      rec.start();
    } catch {
      /* уже слушает — ничего страшного */
    }
  };

  try {
    rec.start();
  } catch {
    handlers.onError?.('Микрофон уже слушает.');
    return null;
  }

  return {
    stop: () => {
      stopped = true;
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      rec.stop();
    },
    mute: () => {
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      muted = true;
      intentionalStop = true;
      // abort(), не stop(): stop() всё ещё пытается вернуть результат из
      // уже захваченного буфера — ровно то, чего мы хотим избежать
      // (хвост собственного голоса). abort() бросает буфер без попытки
      // распознать его.
      try {
        rec.abort();
      } catch {
        /* уже остановлен — не страшно */
      }
    },
    unmute: () => {
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      unmuteTimer = window.setTimeout(() => {
        muted = false;
        intentionalStop = false;
        try {
          rec.start();
        } catch {
          /* уже слушает — не страшно */
        }
      }, UNMUTE_DELAY_MS);
    },
  };
}

// Локальный сервер слова-будильника (wakeword/server.py, Vosk, офлайн) —
// единственный путь получить непрерывное «слушает Джарвис» в Electron:
// браузерное распознавание там не работает вообще (шапка файла). Сервер
// не решает сам, что такое имя — просто транскрибирует и рассылает текст;
// вся логика (WAKE-регексп, mute/unmute против эха) — здесь же, общая с
// listenForWakeWord() выше, не задублирована.
const WAKEWORD_SERVER_URL = 'ws://127.0.0.1:8422';

/**
 * То же самое, что listenForWakeWord(), но источник звука — не браузер,
 * а wakeword/server.py по WebSocket. Тот же контракт (Listener), та же
 * реакция на «Джарвис» — вызывающему (useJarvisConversation.ts) не нужно
 * знать, откуда на самом деле пришёл текст.
 */
export function listenForWakeWordElectron(handlers: {
  onWake: (rest: string) => void;
  onCommand: (text: string) => void;
  onPartial?: (text: string) => void;
  onError?: (reason: string) => void;
  isAwake: () => boolean;
}): Listener {
  let stopped = false;
  let muted = false;
  let unmuteTimer: number | null = null;
  let ws: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let everConnected = false;

  const handle = (text: string, isFinal: boolean) => {
    if (muted || !text) return;
    if (!isFinal) {
      handlers.onPartial?.(text);
      return;
    }
    if (handlers.isAwake()) {
      handlers.onCommand(text);
      return;
    }
    const match = text.match(WAKE);
    if (match) {
      const rest = text.slice((match.index ?? 0) + match[0].length).replace(/^[\s,.!?—-]+/, '');
      handlers.onWake(rest);
    }
  };

  const connect = () => {
    if (stopped) return;
    ws = new WebSocket(WAKEWORD_SERVER_URL);
    ws.onopen = () => {
      everConnected = true;
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'final') handle(String(msg.text ?? ''), true);
        else if (msg.type === 'partial') handle(String(msg.text ?? ''), false);
      } catch {
        /* мусор в кадре — пропускаем, не роняем разговор */
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      handlers.onError?.(
        everConnected
          ? 'Сервер слова-будильника отключился — переподключаюсь.'
          : 'Сервер слова-будильника не отвечает. Запусти wakeword/start.ps1.',
      );
      reconnectTimer = window.setTimeout(connect, 5000);
    };
  };

  connect();

  return {
    stop: () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      ws?.close();
    },
    mute: () => {
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      muted = true;
    },
    unmute: () => {
      if (unmuteTimer) window.clearTimeout(unmuteTimer);
      unmuteTimer = window.setTimeout(() => {
        muted = false;
      }, UNMUTE_DELAY_MS);
    },
  };
}

/**
 * Слушает микрофон и отдаёт распознанный текст.
 * onPartial — то, что слышно прямо сейчас, чтобы человек видел процесс.
 */
export function listen(
  lang: string,
  onFinal: (text: string) => void,
  onPartial?: (text: string) => void,
  onError?: (reason: string) => void,
): Listener | null {
  const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!Ctor) {
    onError?.('Браузер не умеет распознавать речь. Chrome или Edge умеют.');
    return null;
  }

  const rec: Recognition = new Ctor();
  rec.lang = lang;
  rec.interimResults = Boolean(onPartial);
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onresult = (event: any) => {
    let partial = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) {
        onFinal(String(result[0].transcript).trim());
      } else {
        partial += result[0].transcript;
      }
    }
    if (partial) onPartial?.(partial.trim());
  };

  rec.onerror = (event: any) => {
    const reasons: Record<string, string> = {
      'not-allowed': 'Микрофон запрещён в настройках браузера.',
      'no-speech': 'Ничего не услышал.',
      'audio-capture': 'Микрофон не найден.',
      network: 'Распознавание не смогло выйти в сеть.',
    };
    onError?.(reasons[event.error] ?? `Распознавание сломалось: ${event.error}`);
  };

  try {
    rec.start();
  } catch (e) {
    onError?.('Микрофон уже слушает.');
    return null;
  }

  return { stop: () => rec.stop() };
}

/**
 * Запись одной реплики через микрофон и распознавание на бэкенде (Gemini) —
 * путь для Electron-виджета, где браузерное распознавание не работает
 * (см. комментарий вверху файла). Разовая запись, не непрерывное
 * слушание — так же, как listen(), не listenForWakeWord(): голосовая
 * команда «по имени» через этот путь пока не покрыта, только кнопка
 * «Голосом» (push-to-talk). Честно, не молча: постоянное «слушаю
 * Джарвис» через запись+Gemini стоило бы денег на каждые несколько
 * секунд — отдельное решение, не сделано заодно.
 */
export async function record(
  onFinal: (text: string) => void,
  onError?: (reason: string) => void,
): Promise<Listener | null> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    onError?.('Микрофон запрещён или не найден.');
    return null;
  }

  const mime = (window as any).MediaRecorder?.isTypeSupported?.('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';
  const chunks: Blob[] = [];
  const recorder = new MediaRecorder(stream, { mimeType: mime });

  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    if (chunks.length === 0) return;
    try {
      const { transcribe } = await import('./api');
      const text = await transcribe(new Blob(chunks, { type: mime }));
      if (text.trim()) onFinal(text.trim());
      else onError?.('Ничего не услышал.');
    } catch (e: any) {
      onError?.(e?.response?.data?.detail ?? 'Распознавание не удалось.');
    }
  };

  try {
    recorder.start();
  } catch {
    stream.getTracks().forEach((t) => t.stop());
    onError?.('Не удалось начать запись.');
    return null;
  }

  return { stop: () => recorder.stop() };
}
