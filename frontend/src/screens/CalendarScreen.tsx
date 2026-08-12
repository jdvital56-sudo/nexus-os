import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { getCalendarEvents, getCalendarStatus } from '../lib/api';
import { CARD, Empty, ErrorBox, NUM, PageHeader, Pill, Skeleton } from '../components/ui';

// Календарь только читается: система смотрит, что у фаундера в расписании,
// чтобы не предлагать созвон поверх встречи. Создание событий есть в API,
// но кнопки здесь нет намеренно — записать в чужой календарь мимо человека
// это ровно то, чего система делать не должна.

const RANGES = [
  { days: 1, label: 'сегодня' },
  { days: 7, label: 'неделя' },
  { days: 30, label: 'месяц' },
];

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
}

function timeLabel(ev: any): string {
  const start = ev.start ?? ev.start_time;
  if (!start) return '';
  if (!String(start).includes('T')) return 'весь день';
  const d = new Date(start);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

export default function CalendarScreen() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const [events, setEvents] = useState<any[] | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCalendarStatus()
      .then((s) => {
        setConfigured(s.configured);
        setInstructions(s.instructions);
        if (!s.configured) setEvents([]);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  }, []);

  useEffect(() => {
    if (!configured) return;
    setEvents(null);
    getCalendarEvents(days)
      .then((r) => setEvents(r.events))
      .catch(() => setError('События не загрузились.'));
  }, [configured, days]);

  // Группировка по дням: сплошной список встреч читать невозможно
  const byDay = new Map<string, any[]>();
  for (const ev of events ?? []) {
    const key = String(ev.start ?? ev.start_time ?? '').slice(0, 10);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key)!.push(ev);
  }

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Календарь"
        subtitle="Только чтение: система смотрит расписание, чтобы не предлагать созвон поверх встречи."
        action={
          configured ? (
            <div className="flex gap-2">
              {RANGES.map((r) => (
                <button
                  key={r.days}
                  onClick={() => setDays(r.days)}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                    days === r.days
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          ) : undefined
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} />
        </div>
      )}

      {configured === null && !error && <Skeleton rows={2} />}

      {configured === false && (
        <div className={`${CARD} space-y-2`}>
          <div className="flex items-center gap-2 text-gray-200">
            <CalendarDays className="h-5 w-5 text-gray-400" aria-hidden />
            Google Calendar не подключён
          </div>
          <p className="text-sm text-gray-400">
            Нужен файл доступа из Google Cloud Console. Календарь ждёт его в папке данных под
            именем <code className="text-gray-300">google_credentials.json</code> — это не то же
            место, куда его ждёт почта, так что файл придётся положить дважды. Ниже — точный порядок.
          </p>
          {instructions && (
            <pre className="whitespace-pre-wrap rounded-md bg-darker p-3 text-xs leading-relaxed text-gray-300">
              {instructions}
            </pre>
          )}
        </div>
      )}

      {configured && events === null && <Skeleton rows={2} />}

      {configured && events?.length === 0 && (
        <Empty title="В этом промежутке встреч нет." hint="Свободно — можно ставить работу." />
      )}

      <div className="space-y-6">
        {[...byDay.entries()].map(([day, items]) => (
          <section key={day}>
            <h2 className="mb-2 text-sm text-gray-400">{dayLabel(day)}</h2>
            <div className="space-y-2">
              {items.map((ev, i) => (
                <article key={ev.id ?? i} className={`${CARD} flex flex-wrap items-start gap-3`}>
                  <span className={`w-14 shrink-0 text-sm text-gray-300 ${NUM}`}>{timeLabel(ev)}</span>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-white">{ev.summary ?? ev.title ?? 'Без названия'}</h3>
                    {ev.location && <p className="mt-0.5 text-xs text-gray-500">{ev.location}</p>}
                    {ev.description && (
                      <p className="mt-1 line-clamp-2 text-sm text-gray-400">{ev.description}</p>
                    )}
                  </div>
                  {ev.attendees?.length > 0 && (
                    <Pill text={`${ev.attendees.length} участн.`} tone="blue" />
                  )}
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
