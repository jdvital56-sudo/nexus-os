import { useEffect, useState } from 'react';
import { FolderSearch } from 'lucide-react';
import {
  adoptArtifacts,
  cancelArtifactDelete,
  getArtifact,
  getArtifacts,
  requestArtifactDelete,
} from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Артефакты — файлы, которые система создала: отчёты, выгрузки, черновики.
// Ключевое правило (I-2): система их не стирает. Она может только пометить
// файл к удалению и объяснить почему — стирает человек, отдельной кнопкой.
//
// Карточки того же образца, что Идеи/Задачи/Контент (23-24.08.2026): клик
// раскрывает — и здесь раскрытие ещё и подгружает содержимое файла, чтобы
// не тянуть все тексты сразу.

const KINDS: Record<string, { label: string; tone: string }> = {
  report: { label: 'отчёт', tone: 'progress' },
  export: { label: 'выгрузка', tone: 'progress' },
  draft: { label: 'черновик', tone: 'neutral' },
  audio: { label: 'аудио', tone: 'good' },
  image: { label: 'картинка', tone: 'good' },
  other: { label: 'файл', tone: 'neutral' },
};

const FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'все' },
  { value: 'report', label: 'отчёты' },
  { value: 'export', label: 'выгрузки' },
  { value: 'draft', label: 'черновики' },
  { value: 'pending_delete', label: 'к удалению' },
];

function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function ArtifactsScreen() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('');
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getArtifacts()
      .then((a) => {
        setItems(a);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const toggle = async (id: string) => {
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

  const visible = (items ?? []).filter((a) => {
    if (!filter) return true;
    if (filter === 'pending_delete') return a.status === 'pending_delete';
    return a.kind === filter;
  });
  const counts = FILTERS.map((f) => ({
    ...f,
    n: !f.value
      ? (items ?? []).length
      : f.value === 'pending_delete'
        ? (items ?? []).filter((a) => a.status === 'pending_delete').length
        : (items ?? []).filter((a) => a.kind === f.value).length,
  }));

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Артефакты"
        subtitle="Файлы, которые система создала. Сама она их не стирает — только помечает и объясняет почему."
        action={
          <button
            onClick={adopt}
            disabled={busy}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600 disabled:opacity-50"
          >
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

      <div className="pantheon-theme" data-palette={palette}>
        {items !== null && items.length > 0 && (
          <div className="n-filters">
            {counts.map((f) => (
              <button
                key={f.value || 'all'}
                className={filter === f.value ? 'active' : ''}
                onClick={() => setFilter(f.value)}
              >
                {f.label} · {f.n}
              </button>
            ))}
          </div>
        )}

        {items === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {items?.length === 0 && (
          <div className="n-empty">
            <p>Артефактов пока нет.</p>
            <p className="n-sub">
              Здесь появятся отчёты и выгрузки, которые система сделает по вашей просьбе.
            </p>
          </div>
        )}

        {visible.length === 0 && (items?.length ?? 0) > 0 && (
          <div className="n-empty">
            <p>В этой категории пусто.</p>
          </div>
        )}

        <div className="n-grid wide">
          {visible.map((a) => {
            const kind = KINDS[a.kind] ?? KINDS.other;
            const pending = a.status === 'pending_delete';
            const open = openId === a.id;
            return (
              <div
                key={a.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={pending ? 'warn' : kind.tone}
                role="button"
                tabIndex={0}
                onClick={() => toggle(a.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggle(a.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{a.description || a.filename}</h3>
                  <span className="n-badge" data-tone={pending ? 'warn' : kind.tone}>
                    {pending ? 'к удалению' : kind.label}
                  </span>
                </div>

                <div className="n-foot">
                  <span>{a.filename}</span>
                  <span>·</span>
                  <span>{when(a.created_at)}</span>
                  {a.source && (
                    <>
                      <span>·</span>
                      <span>{a.source}</span>
                    </>
                  )}
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {pending && a.delete_reason && (
                  <div className="n-foot" style={{ color: 'var(--torch)' }}>
                    Причина: {a.delete_reason}
                  </div>
                )}

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Содержимое</div>
                      <pre className="n-pre">{content ?? 'Читаю…'}</pre>
                    </div>
                    <div className="n-actions">
                      {pending ? (
                        <button
                          className="n-act active"
                          onClick={async () => {
                            await cancelArtifactDelete(a.id);
                            load();
                          }}
                        >
                          вернуть из удаления
                        </button>
                      ) : (
                        <button className="n-act danger" onClick={() => markForDelete(a.id)}>
                          пометить к удалению
                        </button>
                      )}
                    </div>
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
