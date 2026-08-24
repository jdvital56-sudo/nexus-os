import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import {
  approveContent,
  contentImage,
  contentMediaUrl,
  contentVideo,
  contentVoice,
  createContentPlan,
  deleteContent,
  getContentItems,
  markContentPosted,
  rejectContent,
  scheduleContent,
  sendContentForApproval,
  setContentPlatforms,
} from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Контент-завод: то, что раньше жило только в API и голосовых командах.
// Фаундер сказал прямо (23.08.2026): «мне нужно полностью всё видеть» —
// календарь, статусы, даты публикации, а не переписка с Джарвисом вслепую.
//
// Система НИЧЕГО не публикует сама: площадки здесь — намерение, дата —
// повод напомнить в Telegram, публикует фаундер руками и отмечает это
// кнопкой «опубликовано». Интеграций с Instagram/TikTok/YouTube нет.
//
// Стиль карточек — Пантеон (.n-card в styles/pantheon.css), как на Идеях
// и Задачах: одна тема на все экраны, решение фаундера 23.08.2026.

const STATUS: Record<string, { label: string; tone: string }> = {
  draft: { label: 'черновик', tone: 'neutral' },
  pending_approval: { label: 'ждёт добра', tone: 'warn' },
  approved: { label: 'одобрен', tone: 'good' },
  scheduled: { label: 'в расписании', tone: 'progress' },
  posted: { label: 'опубликован', tone: 'good' },
  rejected: { label: 'отклонён', tone: 'off' },
};

const PLATFORMS = ['instagram', 'tiktok', 'youtube', 'telegram', 'facebook', 'linkedin', 'x'];

const DOW = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

function localDayKey(d: Date): string {
  // Ключ по местному времени, не toISOString(): в UTC+3 вечерний пост
  // 27-го числа уехал бы в ячейку 28-го.
  const m = `${d.getMonth() + 1}`.padStart(2, '0');
  const day = `${d.getDate()}`.padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function parseIso(iso?: string | null): Date | null {
  if (!iso) return null;
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function when(iso?: string | null): string {
  const d = parseIso(iso);
  if (!d) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** Значение для <input type="datetime-local"> — оно живёт в местном времени. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => `${n}`.padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Сетка месяца, дополненная днями соседних месяцев до целых недель. */
function monthGrid(view: Date): Array<{ date: Date; other: boolean }> {
  const first = new Date(view.getFullYear(), view.getMonth(), 1);
  const shift = (first.getDay() + 6) % 7; // неделя с понедельника
  const start = new Date(first);
  start.setDate(first.getDate() - shift);

  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    return { date, other: date.getMonth() !== view.getMonth() };
  });
}

export default function ContentScreen() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [topic, setTopic] = useState('');
  const [view, setView] = useState(() => new Date());
  const [selected, setSelected] = useState<string | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getContentItems()
      .then((i) => {
        setItems(i);
        setError(null);
      })
      .catch(() => {
        // Пустой экран не должен выглядеть как «контента нет»: молчаливая
        // ошибка уже однажды стоила дня разбирательств (урок 24.08.2026).
        setItems(null);
        setError('Бэкенд недоступен. Запущен ли он на :8420?');
      });
  };

  useEffect(load, []);

  /** Обёртка вокруг действий: показывает занятость и не прячет ошибку. */
  const run = async (id: string, what: string, fn: () => Promise<unknown>) => {
    setBusy(`${id}:${what}`);
    try {
      await fn();
      setError(null);
      load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail ? `${what}: ${detail}` : `Не удалось: ${what}`);
    } finally {
      setBusy(null);
    }
  };

  const create = async () => {
    if (!topic.trim()) return;
    setBusy('new');
    try {
      await createContentPlan({ topic: topic.trim(), count: 3 });
      setTopic('');
      setShowCreate(false);
      setError(null);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'План не создался. Проверьте ключ модели.');
    } finally {
      setBusy(null);
    }
  };

  const all = items ?? [];

  const byDay = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const item of all) {
      const d = parseIso(item.scheduled_at);
      if (!d) continue;
      const key = localDayKey(d);
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return map;
  }, [all]);

  const unscheduled = all.filter((i) => !i.scheduled_at);
  const selectedItems = selected ? byDay.get(selected) ?? [] : [];
  const grid = useMemo(() => monthGrid(view), [view]);
  const todayKey = localDayKey(new Date());

  const stats = [
    { key: 'draft', tone: 'neutral' },
    { key: 'pending_approval', tone: 'warn' },
    { key: 'scheduled', tone: 'progress' },
    { key: 'posted', tone: 'good' },
  ].map((s) => ({ ...s, n: all.filter((i) => i.status === s.key).length }));

  const shiftMonth = (delta: number) =>
    setView(new Date(view.getFullYear(), view.getMonth() + delta, 1));

  const card = (item: any) => {
    const status = STATUS[item.status] ?? STATUS.draft;
    const open = openId === item.id;
    const working = busy?.startsWith(`${item.id}:`);
    const scheduledDate = parseIso(item.scheduled_at);

    return (
      <div
        key={item.id}
        className={`n-card ${open ? 'open' : ''}`}
        data-tone={status.tone}
        role="button"
        tabIndex={0}
        onClick={() => setOpenId(open ? null : item.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpenId(open ? null : item.id);
          }
        }}
      >
        <div className="n-top">
          <h3 className="n-title">{item.caption || item.topic}</h3>
          <span className="n-badge" data-tone={status.tone}>
            {status.label}
          </span>
        </div>

        <div className="n-foot">
          <span>{item.scheduled_at ? when(item.scheduled_at) : 'без даты'}</span>
          {item.platforms?.length > 0 && (
            <>
              <span>·</span>
              <span>{item.platforms.join(', ')}</span>
            </>
          )}
          {working && (
            <>
              <span>·</span>
              <span>работаю…</span>
            </>
          )}
          <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
        </div>

        {open && (
          <div className="n-body" onClick={(e) => e.stopPropagation()}>
            <div>
              <div className="n-label">Сценарий</div>
              <p className="n-full">{item.script}</p>
            </div>

            {item.hashtags?.length > 0 && (
              <div>
                <div className="n-label">Хэштеги</div>
                <p className="n-full">{item.hashtags.map((h: string) => `#${h.replace(/^#/, '')}`).join(' ')}</p>
              </div>
            )}

            {(item.voice_file || item.image_file || item.video_file) && (
              <div>
                <div className="n-label">Готовые файлы</div>
                <div className="n-media">
                  {item.image_file && <img src={contentMediaUrl(item.id, 'image')} alt="" />}
                  {item.voice_file && <audio controls src={contentMediaUrl(item.id, 'voice')} />}
                  {item.video_file && <video controls src={contentMediaUrl(item.id, 'video')} />}
                </div>
              </div>
            )}

            <div>
              <div className="n-label">Сделать материалы</div>
              <div className="n-actions" style={{ marginTop: 6 }}>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'озвучка', () => contentVoice(item.id))}>
                  {item.voice_file ? 'переозвучить' : 'озвучить'}
                </button>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'картинка', () => contentImage(item.id))}>
                  {item.image_file ? 'новая картинка' : 'картинка'}
                </button>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'видео', () => contentVideo(item.id))}>
                  {item.video_file ? 'новое видео' : 'видео'}
                </button>
              </div>
            </div>

            <div>
              <div className="n-label">Куда публикуем</div>
              <div className="n-actions" style={{ marginTop: 6 }}>
                {PLATFORMS.map((p) => {
                  const on = item.platforms?.includes(p);
                  return (
                    <button
                      key={p}
                      className={`n-act ${on ? 'active' : ''}`}
                      disabled={working}
                      onClick={() => {
                        const next = on
                          ? item.platforms.filter((x: string) => x !== p)
                          : [...(item.platforms ?? []), p];
                        if (next.length === 0) {
                          setError('Оставьте хотя бы одну площадку.');
                          return;
                        }
                        run(item.id, 'площадки', () => setContentPlatforms(item.id, next));
                      }}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="n-label">Когда публикуем</div>
              <div className="n-when">
                <input
                  type="datetime-local"
                  defaultValue={scheduledDate ? toLocalInput(scheduledDate) : ''}
                  onChange={(e) => {
                    if (!e.target.value) return;
                    // datetime-local отдаёт местное время без зоны —
                    // переводим в UTC, бэкенд хранит всё в UTC.
                    const iso = new Date(e.target.value).toISOString();
                    run(item.id, 'дата', () => scheduleContent(item.id, iso));
                  }}
                />
                <span className="n-sub">напомню в Telegram — публикуете сами</span>
              </div>
            </div>

            <div>
              <div className="n-label">Что дальше</div>
              <div className="n-actions" style={{ marginTop: 6 }}>
                <button
                  className="n-act"
                  disabled={working}
                  onClick={() => run(item.id, 'отправка в Telegram', () => sendContentForApproval(item.id))}
                >
                  прислать мне в Telegram
                </button>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'одобрение', () => approveContent(item.id))}>
                  одобрить
                </button>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'отметка', () => markContentPosted(item.id))}>
                  опубликовано
                </button>
                <button className="n-act" disabled={working} onClick={() => run(item.id, 'отклонение', () => rejectContent(item.id))}>
                  отклонить
                </button>
                <button
                  className="n-act danger n-spacer"
                  disabled={working}
                  onClick={() => run(item.id, 'удаление', () => deleteContent(item.id))}
                >
                  удалить
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Контент"
        subtitle="Сценарий, озвучка, картинка и видео — по датам. Публикуете вы сами: в назначенный час придёт напоминание в Telegram."
        action={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Новый контент
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {showCreate && (
          <div className="n-newbox">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Тема: например, утренние ритуалы"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && create()}
            />
            <div className="n-actions">
              <button className="n-act n-spacer" onClick={create} disabled={!topic.trim() || busy === 'new'}>
                {busy === 'new' ? 'придумываю…' : 'Придумать 3 варианта'}
              </button>
              <button className="n-act" onClick={() => setShowCreate(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        {all.length > 0 && (
          <div className="n-stats">
            {stats.map((s) => (
              <div key={s.key} className="n-stat" data-tone={s.tone}>
                <div className="n-stat-n">{s.n}</div>
                <div className="n-stat-l">{STATUS[s.key].label}</div>
              </div>
            ))}
          </div>
        )}

        <div className="n-cal">
          <div className="n-cal-head">
            <button onClick={() => shiftMonth(-1)}>←</button>
            <span className="n-cal-month">
              {view.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
            </span>
            <button onClick={() => shiftMonth(1)}>→</button>
          </div>

          <div className="n-cal-grid">
            {DOW.map((d) => (
              <div key={d} className="n-cal-dow">
                {d}
              </div>
            ))}
            {grid.map(({ date, other }) => {
              const key = localDayKey(date);
              const dayItems = byDay.get(key) ?? [];
              const classes = [
                'n-cal-day',
                other ? 'other' : '',
                key === todayKey ? 'today' : '',
                key === selected ? 'selected' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <button
                  key={key}
                  className={classes}
                  onClick={() => setSelected(key === selected ? null : key)}
                  title={dayItems.length ? `${dayItems.length} шт.` : 'ничего не назначено'}
                >
                  <span>{date.getDate()}</span>
                  {dayItems.length > 0 && (
                    <span className="n-cal-dots">
                      {dayItems.slice(0, 4).map((i: any) => (
                        <span
                          key={i.id}
                          className="n-cal-dot"
                          data-tone={(STATUS[i.status] ?? STATUS.draft).tone}
                        />
                      ))}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {items === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {items !== null && all.length === 0 && (
          <div className="n-empty">
            <p>Контента пока нет.</p>
            <p className="n-sub">
              Заведите первый кнопкой выше — или скажите Джарвису: «создай контент на тему X на 27 августа,
              выставь на инстаграм и тикток».
            </p>
          </div>
        )}

        {selected && (
          <>
            <div className="n-label" style={{ marginBottom: 8 }}>
              {new Date(`${selected}T12:00:00`).toLocaleDateString('ru-RU', {
                day: 'numeric',
                month: 'long',
              })}
              {selectedItems.length === 0 && ' — ничего не назначено'}
            </div>
            {selectedItems.length > 0 && <div className="n-grid">{selectedItems.map(card)}</div>}
          </>
        )}

        {!selected && unscheduled.length > 0 && (
          <>
            <div className="n-label" style={{ marginBottom: 8 }}>
              Без даты — {unscheduled.length}
            </div>
            <div className="n-grid">{unscheduled.map(card)}</div>
          </>
        )}
      </div>
    </div>
  );
}
