// Распознавание речи в браузере. Встроено в Chrome и Edge, ничего не весит
// и ничего не стоит — поэтому для ввода голосом в вебе берём его, а не
// отправляем звук на бэкенд.
//
// Telegram-канал устроен иначе: там голосовое приходит файлом и
// расшифровывается на сервере через Gemini. Это разные пути намеренно —
// в браузере уже есть готовое ухо, гонять байты незачем.

type Recognition = any;

export function speechSupported(): boolean {
  return typeof window !== 'undefined' &&
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

export interface Listener {
  stop: () => void;
  /** Заглушить распознавание, не останавливая поток — например, пока играет TTS. */
  mute?: () => void;
  unmute?: () => void;
}

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
  let muted = false;
  const rec: Recognition = new Ctor();
  rec.lang = lang;
  rec.continuous = true;
  rec.interimResults = true;

  // «Джарвис», «джарвиса», «джарвес» — распознавание слышит имя по-разному
  const WAKE = /дж[аяе]рв[иеё]с\w*/i;

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

  // Браузер обрывает поток сам — поднимаем обратно, пока режим включён
  rec.onend = () => {
    if (stopped) return;
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
      rec.stop();
    },
    mute: () => {
      muted = true;
    },
    unmute: () => {
      muted = false;
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
