import { useEffect, useState } from 'react';
import { Mail, Plus, Search } from 'lucide-react';
import { createDraft, getDrafts, getGmailStatus, searchMail } from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, PageHeader, Skeleton } from '../components/ui';

// Почта: система готовит черновик, отправляет человек. Отправки нет ни на
// экране, ни в API, ни в сервисе — это решение хартии, а не недоделка,
// поэтому написано прямо на экране, чтобы не искали кнопку «отправить».

export default function MailScreen() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [note, setNote] = useState('');
  const [drafts, setDrafts] = useState<any[] | null>(null);
  const [found, setFound] = useState<any[] | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ to: '', subject: '', body: '' });

  const load = () => {
    getGmailStatus()
      .then((s) => {
        setConfigured(s.configured);
        setNote(s.note);
        if (s.configured) {
          getDrafts()
            .then(setDrafts)
            .catch(() => setError('Черновики не загрузились.'));
        } else {
          setDrafts([]);
        }
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const search = async () => {
    if (!query.trim()) return;
    try {
      setFound(await searchMail(query.trim()));
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
      setError(e?.response?.data?.detail ?? 'Черновик не создался.');
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Почта"
        subtitle="Система готовит черновик — отправляешь ты. Кнопки «отправить» здесь нет и не будет."
        action={
          configured ? (
            <button onClick={() => setShowNew(!showNew)} className={BTN}>
              <Plus className="h-4 w-4" aria-hidden />
              Новый черновик
            </button>
          ) : undefined
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      {configured === null && !error && <Skeleton rows={2} />}

      {configured === false && (
        <div className={`${CARD} space-y-2`}>
          <div className="flex items-center gap-2 text-gray-200">
            <Mail className="h-5 w-5 text-gray-400" aria-hidden />
            Gmail не подключён
          </div>
          <p className="text-sm text-gray-400">
            Нужен файл доступа <code className="text-gray-300">credentials.json</code> из Google Cloud
            Console, в корне проекта. Календарь ждёт такой же файл, но в другом месте и под другим
            именем — это известная нестыковка, чинится вместе с подключением Google.
          </p>
          <p className="text-xs text-gray-500">{note}</p>
        </div>
      )}

      {configured && (
        <>
          <div className="mb-6 flex flex-wrap gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && search()}
              placeholder="Поиск по почте"
              className={`${INPUT} max-w-md`}
            />
            <button onClick={search} className={BTN_GHOST}>
              <Search className="h-4 w-4" aria-hidden />
              Найти
            </button>
          </div>

          {showNew && (
            <div className={`${CARD} mb-6 space-y-3`}>
              <input
                value={form.to}
                onChange={(e) => setForm({ ...form, to: e.target.value })}
                placeholder="Кому"
                className={INPUT}
                autoFocus
              />
              <input
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="Тема"
                className={INPUT}
              />
              <textarea
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                placeholder="Текст письма"
                rows={8}
                className={INPUT}
              />
              <div className="flex flex-wrap items-center gap-2">
                <button onClick={save} className={BTN} disabled={!form.to.trim() || !form.subject.trim()}>
                  Сохранить черновик
                </button>
                <button onClick={() => setShowNew(false)} className={BTN_GHOST}>
                  Отмена
                </button>
                <span className="text-xs text-gray-500">
                  Ляжет в черновики Gmail — отправишь оттуда сам.
                </span>
              </div>
            </div>
          )}

          {found && (
            <section className="mb-6">
              <h2 className="mb-2 text-sm text-gray-400">Найдено писем: {found.length}</h2>
              <div className="space-y-2">
                {found.map((m) => (
                  <article key={m.id} className={CARD}>
                    <h3 className="text-sm font-semibold text-gray-100">{m.subject || 'без темы'}</h3>
                    <p className="mt-0.5 text-xs text-gray-500">{m.from || m.sender}</p>
                    {m.snippet && <p className="mt-1 text-sm text-gray-300">{m.snippet}</p>}
                  </article>
                ))}
              </div>
            </section>
          )}

          {drafts === null && <Skeleton rows={2} />}
          {drafts?.length === 0 && (
            <Empty
              title="Черновиков нет."
              hint="Их создаёт система, когда просишь написать письмо, — или заведи вручную."
            />
          )}

          <div className="space-y-2">
            {drafts?.map((d) => (
              <article key={d.id} className={CARD}>
                <h3 className="text-sm font-semibold text-gray-100">{d.subject || 'без темы'}</h3>
                <p className="mt-0.5 text-xs text-gray-500">кому: {d.to || '—'}</p>
                {d.snippet && <p className="mt-1 text-sm text-gray-300">{d.snippet}</p>}
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
