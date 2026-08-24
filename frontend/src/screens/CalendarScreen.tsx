import { useEffect, useState } from 'react';
import { getCalendarEvents, getCalendarStatus } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Календарь только читается: система смотрит, что у фаундера в расписании,
// чтобы не предлагать созвон поверх встречи. Создание событий есть в API,
// но кнопки здесь нет намеренно — записать в чужой календарь мимо человека
// это ровно то, чего система делать не должна.
//
// Переписано 23.08.2026 на карточки (стиль Пантеона). Тогда же выяснилось,
// почему экран был пуст: токен Google оказался отозван, а сервис глотал
// ошибку и молча отдавал пустой кэш — то есть «нет доступа» выглядело как
// «нет встреч». Теперь бэкенд отвечает 503 с причиной, и экран показывает
// её отдельно от честной пустоты.

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

function isToday(iso?: string): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

export default function CalendarScreen() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const [events, setEvents] = useState<any[] | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);
  const [authExpired, setAuthExpired] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getCalendarStatus()
      .then((s) => {
        setConfigured(s.configured);
        setInstructions(s.instructions);
        if (!s.configured) {
          setEvents([]);
          return;
        }
        getCalendarEvents(days)
          .then((r) => {
            setEvents(r.events ?? []);
            setAuthExpired(null);
            setError(null);
          })
          .catch((e: any) => {
            const detail = e?.response?.data?.detail ?? '';
            if (e?.response?.status === 503) {
              // Не «нет встреч», а «нет доступа» — разные вещи, и человек
              // должен видеть разницу (23.08.2026)
              setAuthExpired(detail || 'Доступ к Google Календарю истёк.');
              setEvents([]);
            } else {
              setError('События не загрузились.');
              setEvents([]);
            }
          });
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, [days]);

  const grouped = (events ?? []).reduce((acc: Record<string, any[]>, ev: any) => {
    const start = ev.start ?? ev.start_time ?? '';
    const key = String(start).slice(0, 10);
    (acc[key] ??= []).push(ev);
    return acc;
  }, {});

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Календарь"
        subtitle="Только чтение: система смотрит расписание, чтобы не предлагать созвон поверх встречи. Создать событие можно голосом — «поставь встречу в четверг в 15:00»."
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        <div className="n-filters">
          {RANGES.map((r) => (
            <button key={r.days} className={days === r.days ? 'active' : ''} onClick={() => setDays(r.days)}>
              {r.label}
            </button>
          ))}
        </div>

        {authExpired && (
          <div className="n-empty" style={{ borderColor: 'var(--torch)' }}>
            <p style={{ color: 'var(--torch)' }}>Доступ к Google Календарю истёк.</p>
            <p className="n-sub">
              {authExpired} Пока доступ не восстановлен, экран будет пустым — это не значит, что у вас
              нет встреч.
            </p>
          </div>
        )}

        {configured === false && (
          <div className="n-empty">
            <p>Календарь не подключён.</p>
            <p className="n-sub">{instructions || 'Нужны доступы Google в настройках.'}</p>
          </div>
        )}

        {configured && events === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {configured && !authExpired && events?.length === 0 && (
          <div className="n-empty">
            <p>Встреч не запланировано.</p>
            <p className="n-sub">
              Связь с календарём живая — просто на выбранный период ничего нет. Скажите Джарвису
              «поставь встречу в четверг в 15:00», и она появится здесь.
            </p>
          </div>
        )}

        {Object.entries(grouped).map(([day, list]) => (
          <div key={day}>
            <div className="p-head">
              <h2>{dayLabel(day)}</h2>
              <span>
                {list.length} {list.length === 1 ? 'встреча' : 'встреч'}
                {isToday(day) ? ' · сегодня' : ''}
              </span>
            </div>
            <div className="n-grid wide">
              {list.map((ev: any) => {
                const id = ev.id ?? `${day}-${ev.summary}`;
                const open = openId === id;
                return (
                  <div
                    key={id}
                    className={`n-card ${open ? 'open' : ''}`}
                    data-tone={isToday(day) ? 'good' : 'neutral'}
                    role="button"
                    tabIndex={0}
                    onClick={() => setOpenId(open ? null : id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setOpenId(open ? null : id);
                      }
                    }}
                  >
                    <div className="n-top">
                      <h3 className="n-title">{ev.summary || '(без названия)'}</h3>
                      <span className="n-badge" data-tone={isToday(day) ? 'good' : 'neutral'}>
                        {timeLabel(ev)}
                      </span>
                    </div>
                    {(ev.attendees?.length ?? 0) > 0 && (
                      <div className="n-foot">
                        <span>{ev.attendees.length} участник(ов)</span>
                        <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                      </div>
                    )}
                    {open && (
                      <div className="n-body" onClick={(e) => e.stopPropagation()}>
                        {ev.description && (
                          <div>
                            <div className="n-label">Описание</div>
                            <p className="n-full" style={{ fontSize: '0.84rem' }}>{ev.description}</p>
                          </div>
                        )}
                        {(ev.attendees?.length ?? 0) > 0 && (
                          <div>
                            <div className="n-label">Кто будет</div>
                            <div className="n-foot" style={{ marginTop: 4 }}>
                              {ev.attendees.map((a: any, i: number) => (
                                <span key={i} className="n-badge">
                                  {typeof a === 'string' ? a : a.email ?? '?'}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
