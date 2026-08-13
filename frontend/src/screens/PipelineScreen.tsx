import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { createContent, getPipelineStatus } from '../lib/api';
import { BTN, BTN_GHOST, CARD, ErrorBox, INPUT, NUM, PageHeader, Skeleton } from '../components/ui';

// Путь материала от идеи до метрик. Экран показывает, где что застряло:
// стопка в одной колонке — это и есть узкое место.

const STAGES: Record<string, { label: string; color: string }> = {
  idea: { label: 'идея', color: 'bg-gray-500' },
  draft: { label: 'черновик', color: 'bg-blue-400' },
  review: { label: 'проверка', color: 'bg-amber-400' },
  approve: { label: 'одобрено', color: 'bg-secondary' },
  schedule: { label: 'в расписании', color: 'bg-sky-400' },
  publish: { label: 'опубликовано', color: 'bg-primary' },
  metrics: { label: 'метрики', color: 'bg-pink-400' },
};

const PLATFORMS = ['general', 'telegram', 'instagram', 'youtube', 'x'];

export default function PipelineScreen() {
  const [status, setStatus] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', platform: 'general', description: '' });

  const load = () => {
    getPipelineStatus()
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const create = async () => {
    if (!form.title.trim()) return;
    try {
      await createContent(form);
      setForm({ title: '', platform: 'general', description: '' });
      setShowCreate(false);
      load();
    } catch {
      setError('Материал не создался.');
    }
  };

  const stages: string[] = status?.stages ?? [];
  const counts: Record<string, number> = status?.by_stage ?? {};
  const peak = Math.max(...Object.values(counts).map(Number), 1);

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Контент"
        subtitle={
          status
            ? `${status.total_items ?? 0} материалов в работе. Стопка в одной колонке — это узкое место.`
            : 'Путь материала от идеи до метрик.'
        }
        action={
          <button onClick={() => setShowCreate(!showCreate)} className={BTN}>
            <Plus className="h-4 w-4" aria-hidden />
            Новый материал
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
            placeholder="О чём материал"
            className={INPUT}
            autoFocus
          />
          <input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Подробности"
            className={INPUT}
          />
          <div className="flex flex-wrap items-center gap-2">
            {PLATFORMS.map((p) => (
              <button
                key={p}
                onClick={() => setForm({ ...form, platform: p })}
                className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                  form.platform === p
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-gray-100'
                }`}
              >
                {p === 'general' ? 'без площадки' : p}
              </button>
            ))}
            <button onClick={create} className={`${BTN} ml-auto`} disabled={!form.title.trim()}>
              Создать
            </button>
            <button onClick={() => setShowCreate(false)} className={BTN_GHOST}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {status === null && !error && <Skeleton rows={2} />}

      {stages.length > 0 && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
            {stages.map((stage) => (
              <div key={stage} className={`${CARD} text-center`}>
                <div className="text-[11px] uppercase tracking-wider text-gray-400">
                  {STAGES[stage]?.label ?? stage}
                </div>
                <div className={`mt-1 text-2xl font-bold text-gray-100 ${NUM}`}>{counts[stage] ?? 0}</div>
              </div>
            ))}
          </div>

          <section className={CARD}>
            <h2 className="mb-4 text-lg font-bold text-gray-100">Где сколько лежит</h2>
            <div className="space-y-2">
              {stages.map((stage) => {
                const count = counts[stage] ?? 0;
                return (
                  <div key={stage} className="flex items-center gap-3">
                    <span className="w-28 shrink-0 text-right text-xs text-gray-400">
                      {STAGES[stage]?.label ?? stage}
                    </span>
                    <div className="h-4 flex-1 rounded bg-gray-800">
                      <div
                        className={`h-4 rounded ${STAGES[stage]?.color ?? 'bg-gray-500'} transition-[width] duration-300`}
                        style={{ width: `${Math.max((count / peak) * 100, count > 0 ? 6 : 1.5)}%` }}
                      />
                    </div>
                    <span className={`w-8 text-right text-xs text-gray-200 ${NUM}`}>{count}</span>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
