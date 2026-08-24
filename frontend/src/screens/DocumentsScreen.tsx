import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { createDocument, getDocuments } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Документы — то, на что система ссылается как на доказательство, в отличие
// от фактов памяти, которым она просто доверяет. Сюда же попадают заметки
// Obsidian при синхронизации, поэтому их много и нужен поиск.
//
// Переписано 23.08.2026 на карточки: фаундер сказал «что-то пишет, я не
// понимаю, что это». Причина непонятности была не только в вёрстке —
// заметки из Obsidian приходят с датой в начале имени файла («2026 07 10
// Ua Лендинг Ai Роб…»), и по одному заголовку правда не разобрать, что
// внутри. Поэтому на карточке видно превью первых строк, а по клику
// раскрывается текст целиком.
//
// Секреты в содержимом режет бэкенд (api/documents.py:_safe), не экран.

const TYPE_TONE: Record<string, string> = {
  markdown: 'neutral',
  text: 'neutral',
  csv: 'progress',
  json: 'progress',
  other: 'neutral',
};

// «2026 07 13   Serenity Crm Fix Permission» → дата отдельно, название отдельно
const DATE_PREFIX = /^(\d{4})[\s.-](\d{2})[\s.-](\d{2})\s+(.*)$/;

function splitTitle(raw: string): { date: string | null; title: string } {
  const m = (raw || '').trim().match(DATE_PREFIX);
  if (!m) return { date: null, title: raw || 'Без названия' };
  return { date: `${m[3]}.${m[2]}.${m[1]}`, title: m[4].trim() || 'Без названия' };
}

function preview(content: string): string {
  if (!content) return '';
  // Frontmatter и markdown-шапки в превью только мешают понять суть
  const body = content
    .replace(/^---[\s\S]*?---\s*/m, '')
    .split('\n')
    .map((l) => l.replace(/^#{1,6}\s*/, '').trim())
    .filter((l) => l && !/^[-*=_]{3,}$/.test(l))
    .join(' ');
  return body.slice(0, 220);
}

function sourceLabel(source?: string | null): string {
  if (!source) return 'заведён вручную';
  if (source.startsWith('obsidian:')) return 'из Obsidian';
  if (source.startsWith('http')) return 'из интернета';
  return source.slice(0, 40);
}

export default function DocumentsScreen() {
  const [docs, setDocs] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', content: '', doc_type: 'markdown' });
  const [hideEmpty, setHideEmpty] = useState(true);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getDocuments()
      .then((d) => {
        setDocs(d);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const emptyCount = useMemo(
    () => (docs ?? []).filter((d) => !(d.content || '').trim()).length,
    [docs],
  );

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = docs ?? [];
    if (hideEmpty) list = list.filter((d) => (d.content || '').trim());
    if (q) {
      list = list.filter(
        (d) => d.title?.toLowerCase().includes(q) || d.content?.toLowerCase().includes(q),
      );
    }
    return list.slice(0, 100);
  }, [docs, query, hideEmpty]);

  const create = async () => {
    if (!form.title.trim() || !form.content.trim()) return;
    try {
      await createDocument(form);
      setForm({ title: '', content: '', doc_type: 'markdown' });
      setShowCreate(false);
      load();
    } catch {
      setError('Документ не создался.');
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Документы"
        subtitle="То, на что система ссылается как на источник. Большинство — заметки, затянутые из вашего Obsidian."
        action={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Новый документ
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
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Название"
              autoFocus
            />
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              placeholder="Содержимое"
              rows={5}
            />
            <div className="n-actions">
              <button
                className="n-act n-spacer"
                onClick={create}
                disabled={!form.title.trim() || !form.content.trim()}
              >
                Создать
              </button>
              <button className="n-act" onClick={() => setShowCreate(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        {docs !== null && docs.length > 0 && (
          <div className="n-newbox" style={{ padding: 10 }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Поиск среди ${docs.length} документов — по названию и содержимому`}
            />
            {emptyCount > 0 && (
              <div className="n-actions">
                <button
                  className={`n-act ${hideEmpty ? 'active' : ''}`}
                  onClick={() => setHideEmpty(!hideEmpty)}
                >
                  {hideEmpty ? `пустые скрыты (${emptyCount})` : `показаны пустые (${emptyCount})`}
                </button>
                <span style={{ fontSize: '0.74rem', color: 'var(--ink-dimmer)' }}>
                  пустые — файлы, которые синхронизация затянула без содержимого
                </span>
              </div>
            )}
          </div>
        )}

        {docs === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {docs?.length === 0 && (
          <div className="n-empty">
            <p>Документов пока нет.</p>
            <p className="n-sub">Заведите первый кнопкой выше или подключите Obsidian в настройках.</p>
          </div>
        )}

        {shown.length === 0 && (docs?.length ?? 0) > 0 && (
          <div className="n-empty">
            <p>Ничего не нашлось.</p>
          </div>
        )}

        <div className="n-grid wide">
          {shown.map((d) => {
            const open = openId === d.id;
            const { date, title } = splitTitle(d.title);
            const text = (d.content || '').trim();
            const tone = TYPE_TONE[d.doc_type] ?? 'neutral';
            return (
              <div
                key={d.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : d.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : d.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{title}</h3>
                  {date && (
                    <span className="n-badge" data-tone={tone}>
                      {date}
                    </span>
                  )}
                </div>

                {!open && text && (
                  <p
                    style={{
                      margin: 0,
                      fontSize: '0.8rem',
                      lineHeight: 1.45,
                      color: 'var(--ink-dim)',
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {preview(d.content)}
                  </p>
                )}

                <div className="n-foot">
                  <span>{sourceLabel(d.source)}</span>
                  <span>·</span>
                  <span>{text ? `${text.length} симв.` : 'пустой'}</span>
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    {(d.tags ?? []).length > 0 && (
                      <div className="n-foot">
                        {d.tags.map((t: string) => (
                          <span key={t} className="n-badge">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                    <div>
                      <div className="n-label">Содержимое</div>
                      <p
                        className="n-full"
                        style={{ maxHeight: 420, overflow: 'auto', fontFamily: 'var(--p-mono)', fontSize: '0.8rem' }}
                      >
                        {text || 'Файл пустой — синхронизация затянула его без содержимого.'}
                      </p>
                    </div>
                    {d.source?.startsWith('obsidian:') && (
                      <div className="n-foot">
                        <span style={{ wordBreak: 'break-all' }}>{d.source.slice('obsidian:'.length)}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
