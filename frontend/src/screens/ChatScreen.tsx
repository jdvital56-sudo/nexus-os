import { useEffect, useRef, useState } from 'react';
import { Send, Eraser } from 'lucide-react';
import { getChatHistory, getPersonas, resetChat, sendChatMessage } from '../lib/api';
import { JarvisHudWidget, type JarvisState } from '../components/JarvisHudWidget';
import { BTN, BTN_GHOST, ErrorBox, INPUT } from '../components/ui';
import type { Persona } from '../types';

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
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState('');
  const [state, setState] = useState<JarvisState>('ONLINE');
  const [error, setError] = useState<string | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<string>('');
  const feed = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getChatHistory()
      .then((h) => setLines(h.messages))
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
    getPersonas().then(setPersonas).catch(() => {});
  }, []);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' });
  }, [lines, state]);

  const send = async () => {
    const value = text.trim();
    if (!value || state === 'PROCESSING') return;

    setLines((prev) => [...prev, { role: 'user', text: value }]);
    setText('');
    setState('PROCESSING');
    setError(null);

    try {
      const res = await sendChatMessage(value, persona || undefined);
      setLines((prev) => [...prev, { role: 'assistant', text: res.reply, persona: res.persona }]);
      // Короткое «говорю» — чтобы было видно, что ответ только что пришёл
      setState('SPEAKING');
      setTimeout(() => setState('ONLINE'), 1600);
    } catch (e: any) {
      setState('ONLINE');
      setError(e?.response?.data?.detail ?? 'Ответ не пришёл.');
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
            <h1 className="text-2xl font-bold text-white lg:text-3xl">Разговор</h1>
            <p className="mt-1 text-sm text-gray-400">
              Тот же Джарвис, что в Телеграме: общая память, общий характер. Нить разговора здесь своя.
            </p>
          </div>
          <button onClick={clear} className={BTN_GHOST} title="Память фактов останется">
            <Eraser className="h-4 w-4" aria-hidden />
            Начать заново
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
              Спроси что угодно. Он помнит прошлые разговоры и твои заметки.
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
                </div>
              </div>
            );
          })}

          {state === 'PROCESSING' && (
            <div className="flex justify-start">
              <div className="rounded-lg border border-gray-800 bg-dark px-4 py-2.5 text-sm text-gray-400">
                думаю…
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
            <option value="">персона по смыслу</option>
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
            placeholder="Сообщение…"
            className={`${INPUT} flex-1`}
            autoFocus
          />

          <button onClick={send} className={BTN} disabled={!text.trim() || state === 'PROCESSING'}>
            <Send className="h-4 w-4" aria-hidden />
            Отправить
          </button>
        </div>
      </div>

      {/* Кольцо рядом с разговором: видно состояние, а не только текст */}
      <aside className="hidden w-72 shrink-0 flex-col items-center justify-center border-l border-gray-800 bg-darker xl:flex">
        <JarvisHudWidget state={state} activeModel={persona ? persona.toUpperCase() : ''} />
        <p className="mt-6 max-w-[12rem] text-center text-xs leading-relaxed text-gray-500">
          {state === 'PROCESSING'
            ? 'Собирает ответ: смотрит память, заметки и нить разговора.'
            : 'Готов. Память общая с Телеграмом.'}
        </p>
      </aside>
    </div>
  );
}
