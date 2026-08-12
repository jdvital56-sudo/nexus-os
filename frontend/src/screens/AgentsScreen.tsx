import { useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { getAgents, runAgent } from '../lib/api';
import { BTN, CARD, Empty, ErrorBox, INPUT, PageHeader, Pill, Skeleton, when } from '../components/ui';

// Экран запускал агента со строкой «test task» — то есть кнопка тратила
// деньги на бессмысленный запрос. Теперь задачу пишет человек, и пока она
// не написана, кнопка не работает.

const ROLES: Record<string, { label: string; tone: string }> = {
  builder: { label: 'строитель', tone: 'blue' },
  librarian: { label: 'библиотекарь', tone: 'amber' },
  reviewer: { label: 'ревизор', tone: 'green' },
  researcher: { label: 'исследователь', tone: 'violet' },
  monitor: { label: 'наблюдатель', tone: 'red' },
  curator: { label: 'куратор памяти', tone: 'amber' },
  jarvis: { label: 'Джарвис', tone: 'blue' },
};

const STATUS: Record<string, { label: string; tone: string }> = {
  idle: { label: 'ждёт', tone: 'gray' },
  running: { label: 'работает', tone: 'blue' },
  error: { label: 'ошибка', tone: 'red' },
  paused: { label: 'на паузе', tone: 'amber' },
};

export default function AgentsScreen() {
  const [agents, setAgents] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [task, setTask] = useState<Record<string, string>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<{ id: string; text: string } | null>(null);

  const load = () => {
    getAgents()
      .then((a) => {
        setAgents(a);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const run = async (id: string) => {
    const text = (task[id] ?? '').trim();
    if (!text) return;
    setRunning(id);
    setOutput(null);
    try {
      const result = await runAgent(id, text);
      setOutput({ id, text: result.output ?? 'Агент отработал молча.' });
      load();
    } catch (e: any) {
      setOutput({ id, text: e?.response?.data?.error ?? 'Агент не отработал.' });
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Агенты"
        subtitle="Исполнители с ролями. Запуск стоит денег — задачу пишешь ты, наугад система её не придумывает."
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      {agents === null && !error && <Skeleton rows={2} />}
      {agents?.length === 0 && <Empty title="Агентов пока нет." />}

      <div className="grid gap-4 lg:grid-cols-2">
        {agents?.map((a) => {
          const role = ROLES[a.role] ?? { label: a.role, tone: 'gray' };
          const status = STATUS[a.status] ?? STATUS.idle;
          return (
            <article key={a.id} className={CARD}>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold text-white">{a.name}</h3>
                <div className="flex items-center gap-2">
                  <Pill text={role.label} tone={role.tone} />
                  <Pill text={status.label} tone={status.tone} />
                </div>
              </div>
              <p className="text-sm text-gray-400">{a.description || 'Без описания'}</p>
              {a.last_run && (
                <p className="mt-1 text-[11px] text-gray-500">последний запуск: {when(a.last_run)}</p>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  value={task[a.id] ?? ''}
                  onChange={(e) => setTask((prev) => ({ ...prev, [a.id]: e.target.value }))}
                  placeholder="Что поручить"
                  className={`${INPUT} flex-1`}
                />
                <button
                  onClick={() => run(a.id)}
                  disabled={running === a.id || !(task[a.id] ?? '').trim()}
                  className={BTN}
                >
                  <Play className="h-4 w-4" aria-hidden />
                  {running === a.id ? 'Работает…' : 'Запустить'}
                </button>
              </div>

              {output?.id === a.id && (
                <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-darker p-3 text-xs leading-relaxed text-gray-200">
                  {output?.text}
                </pre>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
