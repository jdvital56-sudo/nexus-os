import { useEffect, useRef, useState } from 'react';
import { Radio } from 'lucide-react';
import { CARD, Empty, NUM, PageHeader, Pill, when } from '../components/ui';

// Живая лента событий из шины (/ws). Раньше экран показывал список агентов
// и последних задач — то есть то же, что на других экранах, только мельче.
// Смысл этого экрана в другом: видеть, что система делает прямо сейчас,
// включая то, что она делает сама, пока никто не смотрит.

interface Envelope {
  type: string;
  source: string;
  payload: Record<string, any>;
  ts?: string;
}

const TYPES: Record<string, { label: string; tone: string }> = {
  'chat.message': { label: 'сообщение', tone: 'blue' },
  'memory.fact_added': { label: 'факт в память', tone: 'green' },
  'graph.node_added': { label: 'узел в граф', tone: 'violet' },
  'graph.edge_added': { label: 'связь в граф', tone: 'violet' },
  'agent.run_started': { label: 'агент начал', tone: 'amber' },
  'agent.run_finished': { label: 'агент закончил', tone: 'green' },
  'dream.finding': { label: 'ночная находка', tone: 'amber' },
  'dream.completed': { label: 'прогон завершён', tone: 'green' },
  'system.budget': { label: 'бюджет', tone: 'red' },
  'wallet.alert': { label: 'списание близко', tone: 'amber' },
  connected: { label: 'подключено', tone: 'gray' },
  heartbeat: { label: 'связь жива', tone: 'gray' },
};

const SOURCES: Record<string, string> = {
  hermes: 'Телеграм',
  jarvis: 'Джарвис',
  dream: 'ночной прогон',
  system: 'система',
  web: 'веб',
};

/** Короткая суть события — читать сырой payload человеку незачем. */
function describe(e: Envelope): string {
  const p = e.payload ?? {};
  if (e.type === 'chat.message') {
    const who = p.role === 'user' ? 'ты' : p.persona || 'ассистент';
    return `${who}: ${p.text_preview ?? ''}`;
  }
  if (e.type === 'system.budget') {
    return `потрачено $${p.spent_usd ?? 0} из $${p.budget_usd ?? 0}${p.throttled ? ' — фон остановлен' : ''}`;
  }
  if (e.type === 'dream.finding') return p.title ?? 'находка';
  if (e.type === 'graph.node_added') return p.label ?? p.id ?? '';
  if (e.type === 'memory.fact_added') return (p.content ?? '').slice(0, 120);
  if (e.type === 'agent.run_started' || e.type === 'agent.run_finished') return p.agent ?? p.name ?? '';
  if (e.type === 'wallet.alert') return (p.services ?? []).join(', ');
  const text = Object.entries(p)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 60)}`)
    .join(', ');
  return text.slice(0, 160);
}

// Шина висит в корне (/ws), а не под /api — префикса у её роутера нет
const WS_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8420/api')
  .replace(/^http/, 'ws')
  .replace(/\/api\/?$/, '') + '/ws';

export default function ActivityScreen() {
  const [events, setEvents] = useState<Envelope[]>([]);
  const [live, setLive] = useState(false);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      socket.current = ws;

      ws.onopen = () => setLive(true);
      ws.onmessage = (msg) => {
        if (msg.data === 'pong') return;
        try {
          const envelope = JSON.parse(msg.data) as Envelope;
          // Сердцебиение — служебный сигнал, ленту им засорять незачем
          if (envelope.type === 'heartbeat') return;
          setEvents((prev) => [{ ...envelope, ts: envelope.ts ?? new Date().toISOString() }, ...prev].slice(0, 200));
        } catch {
          /* мусор в потоке не должен ронять экран */
        }
      };
      ws.onclose = () => {
        setLive(false);
        // Бэкенд перезапускают часто — переподключаемся сами
        if (!closed) retry = window.setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      socket.current?.close();
    };
  }, []);

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="События"
        subtitle="Что система делает прямо сейчас — включая то, что она делает сама."
        action={
          <span
            className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
              live ? 'border-primary/40 text-primary' : 'border-gray-800 text-gray-400'
            }`}
          >
            <Radio className={`h-4 w-4 ${live ? 'animate-pulse motion-reduce:animate-none' : ''}`} aria-hidden />
            {live ? 'поток подключён' : 'нет связи'}
          </span>
        }
      />

      {events.length === 0 && (
        <Empty
          title={live ? 'Пока тихо.' : 'Поток событий не подключён.'}
          hint={
            live
              ? 'Напиши боту, запусти скилл или дождись ночного прогона — всё появится здесь сразу.'
              : 'Проверь, запущен ли бэкенд на :8420. Экран переподключится сам.'
          }
        />
      )}

      <div className="space-y-1.5">
        {events.map((e, i) => {
          const type = TYPES[e.type] ?? { label: e.type, tone: 'gray' };
          return (
            <article key={`${e.ts}-${i}`} className={`${CARD} py-3`}>
              <div className="flex flex-wrap items-center gap-2">
                <Pill text={type.label} tone={type.tone} />
                <span className="text-xs text-gray-500">{SOURCES[e.source] ?? e.source}</span>
                <span className={`ml-auto text-[11px] text-gray-500 ${NUM}`}>{when(e.ts)}</span>
              </div>
              <p className="mt-1 break-words text-sm text-gray-200">{describe(e)}</p>
            </article>
          );
        })}
      </div>
    </div>
  );
}
