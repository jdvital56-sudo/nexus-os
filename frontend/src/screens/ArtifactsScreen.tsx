import { useEffect, useState } from 'react';
import { FolderSearch, Trash2, Undo2 } from 'lucide-react';
import {
  adoptArtifacts,
  cancelArtifactDelete,
  getArtifact,
  getArtifacts,
  requestArtifactDelete,
} from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, NUM, PageHeader, Pill, Skeleton, when } from '../components/ui';

// Артефакты — файлы, которые система создала: отчёты, выгрузки, черновики.
// Ключевое правило (I-2): система их не стирает. Она может только пометить
// файл к удалению и объяснить почему — стирает человек, отдельной кнопкой.

const KINDS: Record<string, { label: string; tone: string }> = {
  report: { label: 'отчёт', tone: 'blue' },
  export: { label: 'выгрузка', tone: 'violet' },
  draft: { label: 'черновик', tone: 'amber' },
  audio: { label: 'аудио', tone: 'green' },
  image: { label: 'картинка', tone: 'green' },
  other: { label: 'файл', tone: 'gray' },
};

export default function ArtifactsScreen() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getArtifacts()
      .then((a) => {
        setItems(a);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const open = async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setContent(null);
    try {
      const res = await getArtifact(id);
      setContent(res.content);
    } catch (e: any) {
      setContent(e?.response?.data?.detail ?? 'Файл не читается — возможно, его удалили мимо системы.');
    }
  };

  const markForDelete = async (id: string) => {
    const reason = window.prompt('Почему этот файл больше не нужен?');
    if (reason == null) return;
    try {
      await requestArtifactDelete(id, reason);
      load();
    } catch {
      setError('Не удалось пометить файл.');
    }
  };

  const adopt = async () => {
    setBusy(true);
    try {
      const res = await adoptArtifacts();
      load();
      if (!res.adopted?.length) setError('Новых файлов в папке не нашлось.');
    } catch {
      setError('Не удалось просмотреть папку.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Артефакты"
        subtitle="Файлы, которые система создала. Сама она их не стирает — только помечает и объясняет почему."
        action={
          <button onClick={adopt} className={BTN_GHOST} disabled={busy}>
            <FolderSearch className="h-4 w-4" aria-hidden />
            {busy ? 'Смотрю папку…' : 'Подобрать файлы из папки'}
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      {items === null && !error && <Skeleton rows={2} />}

      {items?.length === 0 && (
        <Empty
          title="Артефактов пока нет."
          hint="Здесь появятся отчёты и выгрузки, которые система сделает по твоей просьбе."
        />
      )}

      <div className="space-y-2">
        {items?.map((a) => {
          const kind = KINDS[a.kind] ?? KINDS.other;
          const pending = a.status === 'pending_delete';
          return (
            <article key={a.id} className={`${CARD} ${pending ? 'border-amber-500/30' : ''}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <button
                  onClick={() => open(a.id)}
                  className="min-w-0 cursor-pointer text-left focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <h3 className="font-semibold text-white">{a.description || a.filename}</h3>
                  <p className={`mt-0.5 text-xs text-gray-500 ${NUM}`}>
                    {a.filename} · {when(a.created_at)}
                    {a.source && ` · ${a.source}`}
                  </p>
                </button>

                <div className="flex shrink-0 items-center gap-2">
                  <Pill text={kind.label} tone={kind.tone} />
                  {pending ? (
                    <>
                      <Pill text="помечен к удалению" tone="amber" />
                      <button
                        onClick={async () => {
                          await cancelArtifactDelete(a.id);
                          load();
                        }}
                        className={BTN_GHOST}
                      >
                        <Undo2 className="h-4 w-4" aria-hidden />
                        вернуть
                      </button>
                    </>
                  ) : (
                    <button onClick={() => markForDelete(a.id)} className={BTN_GHOST}>
                      <Trash2 className="h-4 w-4" aria-hidden />
                      пометить
                    </button>
                  )}
                </div>
              </div>

              {pending && a.delete_reason && (
                <p className="mt-2 text-xs text-amber-200/80">Причина: {a.delete_reason}</p>
              )}

              {openId === a.id && (
                <pre className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-darker p-3 text-xs leading-relaxed text-gray-200">
                  {content ?? 'Читаю…'}
                </pre>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
