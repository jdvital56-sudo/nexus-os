import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { createDocument, getDocuments } from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, PageHeader, Pill, Skeleton, when } from '../components/ui';

// Документы — то, на что система ссылается как на доказательство, в отличие
// от фактов памяти, которым она просто доверяет. Сюда же попадают заметки
// Obsidian при синхронизации, поэтому их много и нужен поиск.

export default function DocumentsScreen() {
  const [docs, setDocs] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', content: '', doc_type: 'markdown' });

  const load = () => {
    getDocuments()
      .then((d) => {
        setDocs(d);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = docs ?? [];
    if (!q) return list.slice(0, 100);
    return list
      .filter((d) => d.title?.toLowerCase().includes(q) || d.content?.toLowerCase().includes(q))
      .slice(0, 100);
  }, [docs, query]);

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
        subtitle="То, на что система ссылается как на источник. Заметки Obsidian попадают сюда при синхронизации."
        action={
          <button onClick={() => setShowCreate(!showCreate)} className={BTN}>
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

      {showCreate && (
        <div className={`${CARD} mb-6 space-y-3`}>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Название"
            className={INPUT}
            autoFocus
          />
          <textarea
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            placeholder="Текст документа"
            rows={8}
            className={INPUT}
          />
          <div className="flex gap-2">
            <button onClick={create} className={BTN} disabled={!form.title.trim() || !form.content.trim()}>
              Создать
            </button>
            <button onClick={() => setShowCreate(false)} className={BTN_GHOST}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {docs && docs.length > 0 && (
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Поиск среди ${docs.length}`}
          className={`${INPUT} mb-4 max-w-md`}
        />
      )}

      {docs === null && !error && <Skeleton />}

      {docs?.length === 0 && (
        <Empty
          title="Документов пока нет."
          hint="Они появляются сами при синхронизации базы знаний Obsidian — или заведи первый вручную."
        />
      )}

      {docs && docs.length > 0 && shown.length === 0 && (
        <Empty title={`По запросу «${query}» ничего не нашлось.`} />
      )}

      <div className="space-y-2">
        {shown.map((d) => {
          const open = openId === d.id;
          return (
            <article key={d.id} className={CARD}>
              <button
                onClick={() => setOpenId(open ? null : d.id)}
                className="w-full cursor-pointer text-left focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="font-semibold text-gray-100">{d.title}</h3>
                  <div className="flex shrink-0 items-center gap-2">
                    {d.source?.startsWith('obsidian:') && <Pill text="из Obsidian" tone="violet" />}
                    <Pill text={d.doc_type ?? 'текст'} />
                  </div>
                </div>
                {!open && (
                  <p className="mt-1 line-clamp-2 text-sm text-gray-400">
                    {(d.content ?? '').slice(0, 200)}
                  </p>
                )}
              </button>

              {open && (
                <pre className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-darker p-3 text-xs leading-relaxed text-gray-200">
                  {d.content}
                </pre>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-1">
                {d.tags?.slice(0, 8).map((t: string) => (
                  <span key={t} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-300">
                    {t}
                  </span>
                ))}
                <span className="ml-auto text-[11px] text-gray-500">{when(d.created_at)}</span>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
