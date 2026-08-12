import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { createTask, getTasks } from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, PageHeader, Pill, Skeleton, when } from '../components/ui';

// Задачи заводит и человек, и система: скиллы и агенты создают их сами.
// Поэтому здесь видно, кто задачу поставил — иначе непонятно, откуда она.

const STATUS: Record<string, { label: string; tone: string; border: string }> = {
  todo: { label: 'в очереди', tone: 'gray', border: 'border-l-gray-600' },
  in_progress: { label: 'в работе', tone: 'blue', border: 'border-l-blue-400' },
  done: { label: 'сделано', tone: 'green', border: 'border-l-primary' },
  blocked: { label: 'застряла', tone: 'red', border: 'border-l-red-500' },
};

const PRIORITY: Record<string, { label: string; tone: string }> = {
  low: { label: 'не срочно', tone: 'gray' },
  medium: { label: 'обычная', tone: 'blue' },
  high: { label: 'важная', tone: 'amber' },
  critical: { label: 'горит', tone: 'red' },
};

export default function TasksScreen() {
  const [tasks, setTasks] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium' });

  const load = () => {
    getTasks()
      .then((t) => {
        setTasks(t);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const create = async () => {
    if (!form.title.trim()) return;
    try {
      await createTask(form);
      setForm({ title: '', description: '', priority: 'medium' });
      setShowCreate(false);
      load();
    } catch {
      setError('Задача не создалась.');
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Задачи"
        subtitle="Свои и те, что система завела сама — из скиллов, агентов и ночных находок."
        action={
          <button onClick={() => setShowCreate(!showCreate)} className={BTN}>
            <Plus className="h-4 w-4" aria-hidden />
            Новая задача
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
            placeholder="Что нужно сделать"
            className={INPUT}
            autoFocus
          />
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Подробности, если нужны"
            rows={3}
            className={INPUT}
          />
          <div className="flex flex-wrap items-center gap-2">
            {Object.entries(PRIORITY).map(([key, p]) => (
              <button
                key={key}
                onClick={() => setForm({ ...form, priority: key })}
                className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                  form.priority === key
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
                }`}
              >
                {p.label}
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

      {tasks === null && !error && <Skeleton />}

      {tasks?.length === 0 && (
        <Empty
          title="Задач пока нет."
          hint="Заведи первую кнопкой выше — или попроси бота, он умеет ставить задачи сам."
        />
      )}

      <div className="space-y-2">
        {tasks?.map((t) => {
          const status = STATUS[t.status] ?? STATUS.todo;
          const priority = PRIORITY[t.priority] ?? PRIORITY.medium;
          return (
            <article key={t.id} className={`${CARD} border-l-4 ${status.border}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="font-semibold text-white">{t.title}</h3>
                <div className="flex shrink-0 items-center gap-2">
                  <Pill text={status.label} tone={status.tone} />
                  <Pill text={priority.label} tone={priority.tone} />
                </div>
              </div>
              {t.description && <p className="mt-1 text-sm text-gray-300">{t.description}</p>}
              <p className="mt-2 text-[11px] text-gray-500">
                {when(t.created_at)}
                {t.assigned_agent && ` · исполнитель: ${t.assigned_agent}`}
                {t.source && ` · создано: ${t.source}`}
              </p>
            </article>
          );
        })}
      </div>
    </div>
  );
}
