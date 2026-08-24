import { useEffect, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { createDraft, getDrafts, getGmailStatus, searchMail } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Почта: система готовит черновик, отправляет человек. Отправки нет ни на
// экране, ни в API, ни в сервисе — это решение хартии, а не недоделка,
// поэтому написано прямо на экране, чтобы не искали кнопку «отправить».
//
// Переписано 23.08.2026 на карточки (стиль Пантеона). Фаундер сказал
// «почта пустая» — и это было честно: черновиков у него нет, а входящие
// экран не показывал вообще, только поиск по запросу. Теперь при пустых
// черновиках экран сам показывает последние письма, чтобы было видно,
// что связь с ящиком живая, а не сломана.

function when(raw?: string | null): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.slice(0, 16);
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** «Team Vapi <team@mail.vapi.ai>» → «Team Vapi» */
function senderName(from?: string | null): string {
  if (!from) return 'без отправителя';
  const m = from.match(/^\s*"?([^"<]+?)"?\s*</);
  return (m ? m[1] : from).trim();
}

export default function MailScreen() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [note, setNote] = useState('');
  const [drafts, setDrafts] = useState<any[] | null>(null);
  const [recent, setRecent] = useState<any[] | null>(null);
  const [found, setFound] = useState<any[] | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form, setForm] = useState({ to: '', subject: '', body: '' });
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getGmailStatus()
      .then((s) => {
        setConfigured(s.configured);
        setNote(s.note);
        if (!s.configured) {
          setDrafts([]);
          return;
        }
        getDrafts()
          .then((d) => {
            setDrafts(d);
            // Пустые черновики — не признак поломки. Показываем последние
            // письма, чтобы фаундер видел живую связь с ящиком, а не
            // гадал, сломалось ли (жалоба «почта пустая», 23.08.2026).
            if (d.length === 0) {
              searchMail('newer_than:7d')
                .then(setRecent)
                .catch(() => setRecent([]));
            }
          })
          .catch((e: any) => {
            const detail = e?.response?.data?.detail ?? '';
            setError(
              detail.includes('has not been used') || detail.includes('disabled')
                ? 'Gmail API выключен в Google Cloud. Включите его в консоли — я в ваши аккаунты не захожу.'
                : 'Черновики не загрузились.',
            );
            setDrafts([]);
          });
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const search = async () => {
    if (!query.trim()) return;
    try {
      setFound(await searchMail(query.trim()));
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Поиск не сработал.');
    }
  };

  const save = async () => {
    if (!form.to.trim() || !form.subject.trim()) return;
    try {
      await createDraft(form);
      setForm({ to: '', subject: '', body: '' });
      setShowNew(false);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Черновик не сохранился.');
    }
  };

  const letters = found ?? recent ?? [];
  const lettersTitle = found ? `Найдено: ${found.length}` : 'Последние письма за неделю';

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Почта"
        subtitle="Система готовит черновики — отправляете вы сами. Кнопки «отправить» здесь нет намеренно."
        action={
          <button
            onClick={() => setShowNew(!showNew)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Новый черновик
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {configured === false && (
          <div className="n-empty">
            <p>Почта не подключена.</p>
            <p className="n-sub">{note || 'Нужны доступы Google в настройках.'}</p>
          </div>
        )}

        {configured && (
          <>
            {showNew && (
              <div className="n-newbox">
                <input
                  value={form.to}
                  onChange={(e) => setForm({ ...form, to: e.target.value })}
                  placeholder="Кому"
                  autoFocus
                />
                <input
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder="Тема"
                />
                <textarea
                  value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })}
                  placeholder="Текст письма"
                  rows={5}
                />
                <div className="n-actions">
                  <button
                    className="n-act n-spacer"
                    onClick={save}
                    disabled={!form.to.trim() || !form.subject.trim()}
                  >
                    Сохранить черновик
                  </button>
                  <button className="n-act" onClick={() => setShowNew(false)}>
                    Отмена
                  </button>
                </div>
              </div>
            )}

            <div className="n-newbox" style={{ padding: 10 }}>
              <div className="n-actions">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') search();
                  }}
                  placeholder="Поиск по почте: от кого, тема, слово в письме"
                  style={{
                    flex: '1 1 260px',
                    background: 'var(--panel-2)',
                    border: '1px solid var(--line)',
                    borderRadius: 6,
                    color: 'var(--ink)',
                    padding: '7px 11px',
                    fontFamily: 'var(--p-body)',
                    fontSize: '0.84rem',
                  }}
                />
                <button
                  className="n-act"
                  onClick={search}
                  disabled={!query.trim()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                >
                  <Search className="h-3 w-3" aria-hidden />
                  Искать
                </button>
                {found && (
                  <button
                    className="n-act"
                    onClick={() => {
                      setFound(null);
                      setQuery('');
                    }}
                  >
                    сбросить
                  </button>
                )}
              </div>
            </div>

            {drafts !== null && drafts.length > 0 && (
              <>
                <div className="p-head">
                  <h2>Черновики</h2>
                  <span>{drafts.length} · отправляете вы сами</span>
                </div>
                <div className="n-grid wide">
                  {drafts.map((d) => (
                    <div key={d.draft_id} className="n-card" data-tone="warn">
                      <div className="n-top">
                        <h3 className="n-title">{d.subject || '(без темы)'}</h3>
                        <span className="n-badge" data-tone="warn">
                          черновик
                        </span>
                      </div>
                      <div className="n-foot">
                        <span>кому: {d.to || 'не указан'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {drafts !== null && drafts.length === 0 && !found && (
              <p className="p-note" style={{ marginBottom: 14 }}>
                Черновиков нет — это не поломка, просто система пока ничего не готовила. Связь с ящиком
                живая, ниже последние письма.
              </p>
            )}

            {letters.length > 0 && (
              <>
                <div className="p-head">
                  <h2>{lettersTitle}</h2>
                  <span>только чтение</span>
                </div>
                <div className="n-grid wide">
                  {letters.map((m) => {
                    const open = openId === m.message_id;
                    return (
                      <div
                        key={m.message_id}
                        className={`n-card ${open ? 'open' : ''}`}
                        data-tone="neutral"
                        role="button"
                        tabIndex={0}
                        onClick={() => setOpenId(open ? null : m.message_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setOpenId(open ? null : m.message_id);
                          }
                        }}
                      >
                        <div className="n-top">
                          <h3 className="n-title">{m.subject || '(без темы)'}</h3>
                        </div>
                        <div className="n-foot">
                          <span>{senderName(m.from)}</span>
                          <span>·</span>
                          <span>{when(m.date)}</span>
                          <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                        </div>
                        {open && (
                          <div className="n-body" onClick={(e) => e.stopPropagation()}>
                            <div>
                              <div className="n-label">Начало письма</div>
                              <p className="n-full" style={{ fontSize: '0.84rem' }}>
                                {m.snippet || 'Без превью.'}
                              </p>
                            </div>
                            <div className="n-foot">
                              <span style={{ wordBreak: 'break-all' }}>{m.from}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {found?.length === 0 && (
              <div className="n-empty">
                <p>По запросу ничего не нашлось.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
