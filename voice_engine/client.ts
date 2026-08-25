/**
 * Клиент общего голоса Piper — скопировать в любой Node/TypeScript-проект.
 *
 * Как и client.py, файл намеренно самодостаточный: ни одной зависимости
 * сверх встроенного fetch (Node 18+). Смысл общего сервиса в том, чтобы
 * новый проект получал голос копированием одного файла.
 *
 *   import { speak, say } from "./voiceClient";
 *
 *   await speak("Сборка прошла");        // вслух на этой машине
 *   const wav = await say("Привет");     // ArrayBuffer — отдать браузеру
 *
 * Сервис не поднят — функции бросают ошибку с адресом и командой запуска
 * в тексте, а не возвращают тишину: тишину не отличить от «нечего сказать».
 */

const SERVER = process.env.PIPER_SERVER ?? "http://127.0.0.1:8424";

// Синтез редко дольше секунды, но первая фраза после запуска ждёт загрузки
// модели — там счёт идёт на десяток секунд.
const TIMEOUT_MS = Number(process.env.PIPER_TIMEOUT_MS ?? 30_000);

export class VoiceUnavailable extends Error {}

async function post(path: string, payload: unknown): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${SERVER}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (cause) {
    throw new VoiceUnavailable(
      `Сервис голоса не отвечает на ${SERVER}. Запускается вместе с остальным ` +
        `через start_all.ps1, вручную: python voice_engine/piper_server.py`,
      { cause },
    );
  }
  if (!response.ok) {
    throw new VoiceUnavailable(`Голос ответил ${response.status}: ${await response.text()}`);
  }
  return response;
}

/** Озвучивает текст и возвращает WAV — то, что отдают браузеру. */
export async function say(text: string, voice?: string): Promise<ArrayBuffer> {
  const response = await post("/say", voice ? { text, voice } : { text });
  return response.arrayBuffer();
}

/** Говорит вслух на колонках этой машины. Не ждёт конца фразы. */
export async function speak(text: string, voice?: string): Promise<{ seconds: number }> {
  const response = await post("/speak", voice ? { text, voice } : { text });
  return response.json();
}

/** Оборвать текущую фразу. */
export async function shutUp(): Promise<void> {
  await post("/stop", {});
}

export async function health(): Promise<{ ready: boolean; voices: string[] }> {
  const response = await fetch(`${SERVER}/health`, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new VoiceUnavailable(`Голос ответил ${response.status}`);
  return response.json();
}
