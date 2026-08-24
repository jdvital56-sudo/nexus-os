import { useEffect, useRef, useState } from 'react';
import { Radio } from 'lucide-react';
import { PageHeader, when } from '../components/ui';
import { authToken } from '../lib/api';
import '../styles/pantheon.css';

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
  'chat.message': { label: 'сообщение', tone: 'progress' },
  'memory.fact_added': { label: 'факт в память', tone: 'good' },
  'graph.node_added': { label: 'узел в граф', tone: 'progress' },
  'graph.edge_added': { label: 'связь в граф', tone: 'progress' },
  'agent.run_started': { label: 'агент начал', tone: 'warn' },
  'agent.run_finished': { label: 'агент закончил', tone: 'good' },
  'dream.finding': { label: 'ночная находка', tone: 'warn' },
  'dream.completed': { label: 'прогон завершён', tone: 'good' },
  'system.budget': { label: 'бюджет', tone: 'off' },
  'wallet.alert': { label: 'списание близко', tone: 'warn' },
  connected: { label: 'подключено', tone: 'neutral' },
  heartbeat: { label: 'связь жива', tone: 'neutral' },
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
  // summary, не content: eventbus кладёт в payload именно его (см.
//   memory.add_fact). Читали не то поле — описание всегда было пустым,
//   и в ленте висел голый заголовок «факт в память» (найдено живым
//   прогоном 24.08.2026, тестами не ловилось: у фронтенда их нет).
  if (e.type === 'memory.fact_added') return (p.summary ?? p.content ?? '').slice(0, 120);
  // Тот же класс промаха, что и с фактами памяти: agent_engine кладёт
  // agent_id/trigger/summary, а не agent/name — строка была пустой.
  if (e.type === 'agent.run_started') return `${p.agent_id ?? ''}${p.trigger ? ` · ${p.trigger}` : ''}`;
  if (e.type === 'agent.run_finished') {
    const cost = p.cost_usd ? ` · $${p.cost_usd}` : '';
    return `${p.agent_id ?? ''}: ${p.summary ?? 'готово'}${cost}`;
  }
  if (e.type === 'wallet.alert') return (p.services ?? []).join(', ');
  const text = Object.entries(p)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 60)}`)
    .join(', ');
  return text.slice(0, 160);
}

// Шина висит в корне (/ws), а не под /api — префикса у её роутера нет.
// Токен — в строке запроса: браузерный WebSocket API не умеет слать
// Authorization при подключении (найдено код-ревью 20.08.2026: ручка
// раньше вообще не проверяла токен, слушать мог кто угодно).
const WS_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8420/api')
  .replace(/^http/, 'ws')
  .replace(/\/api\/?$/, '') + '/ws' + (authToken ? `?token=${encodeURIComponent(authToken)}` : '');

export default function ActivityScreen() {
  const [events, setEvents] = useState<Envelope[]>([]);
  const [live, setLive] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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

      <div className="pantheon-theme" data-palette={palette}>
        {events.length === 0 && (
          <div className="n-empty">
            <p>{live ? 'Пока тихо.' : 'Поток событий не подключён.'}</p>
            <p className="n-sub">
              {live
                ? 'Напишите боту, запустите скилл или дождитесь ночного прогона — всё появится здесь сразу.'
                : 'Проверьте, запущен ли бэкенд на :8420. Экран переподключится сам.'}
            </p>
          </div>
        )}

        {/* Лента, а не сетка: события короткие и их много — раскрытие
            показывает сырое содержимое, когда описания мало. */}
        <div className="n-feed">
          {events.map((e, i) => {
            const type = TYPES[e.type] ?? { label: e.type, tone: 'neutral' };
            const key = `${e.ts}-${i}`;
            const open = openKey === key;
            return (
              <div
                key={key}
                className={`n-row ${open ? 'open' : ''}`}
                data-tone={type.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenKey(open ? null : key)}
                onKeyDown={(ev) => {
                  if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault();
                    setOpenKey(open ? null : key);
                  }
                }}
              >
                <div className="n-row-line">
                  <span className="n-badge" data-tone={type.tone}>
                    {type.label}
                  </span>
                  <span className="n-row-text">{describe(e)}</span>
                  <span className="n-row-meta">
                    {SOURCES[e.source] ?? e.source} · {when(e.ts)}
                  </span>
                </div>
                {open && (
                  <pre className="n-pre" onClick={(ev) => ev.stopPropagation()}>
                    {JSON.stringify(e.payload ?? {}, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
