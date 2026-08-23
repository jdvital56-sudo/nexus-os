import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { createTask, deleteTask, getTasks, updateTask } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Задачи заводит и человек, и система: скиллы и агенты создают их сами.
//
// Карточки вместо списка строк — просьба фаундера 23.08.2026 («что это за
// задача, которую нужно сделать, я не понимаю»): навёл — подсветилось,
// нажал — раскрылось целиком с описанием и действиями. Стиль тот же, что
// у Пантеона и Идей (.pantheon-theme + .n-card в styles/pantheon.css).
//
// Тогда же выяснилось, что экран был непонятен не только из-за вёрстки: из
// 16 задач 15 оказались автомусором плановых обходов агентов («Link orphan
// node: Без Названия»). Генератор мусора починен в agent_engine.py
// (_note_sweep_findings — одна заметка в память вместо N мёртвых задач).

const STATUS: Record<string, { label: string; tone: string }> = {
  todo: { label: 'сделать', tone: 'neutral' },
  in_progress: { label: 'в работе', tone: 'progress' },
  done: { label: 'сделано', tone: 'good' },
  blocked: { label: 'застряла', tone: 'off' },
};

const PRIORITY: Record<string, { label: string; tone: string }> = {
  low: { label: 'не срочно', tone: 'neutral' },
  medium: { label: 'обычная', tone: 'neutral' },
  high: { label: 'важная', tone: 'warn' },
  critical: { label: 'горит', tone: 'off' },
};

const FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'все' },
  { value: 'todo', label: 'сделать' },
  { value: 'in_progress', label: 'в работе' },
  { value: 'done', label: 'сделано' },
  { value: 'blocked', label: 'застряли' },
];

function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function TasksScreen() {
  const [tasks, setTasks] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium' });
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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

  const setStatus = async (id: string, status: string) => {
    try {
      await updateTask(id, { status });
      load();
    } catch {
      setError('Не удалось обновить задачу.');
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteTask(id);
      if (openId === id) setOpenId(null);
      load();
    } catch {
      setError('Не удалось удалить задачу.');
    }
  };

  const visible = (tasks ?? []).filter((t) => !filter || t.status === filter);
  const counts = FILTERS.map((f) => ({
    ...f,
    n: f.value ? (tasks ?? []).filter((t) => t.status === f.value).length : (tasks ?? []).length,
  }));

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Задачи"
        subtitle="Свои и те, что система завела сама. Скажите «создай задачу X» — появится здесь."
        action={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
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

      <div className="pantheon-theme" data-palette={palette}>
        {showCreate && (
          <div className="n-newbox">
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Что нужно сделать"
              autoFocus
            />
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Подробности, если нужны"
              rows={3}
            />
            <div className="n-actions">
              {Object.entries(PRIORITY).map(([key, p]) => (
                <button
                  key={key}
                  className={`n-act ${form.priority === key ? 'active' : ''}`}
                  onClick={() => setForm({ ...form, priority: key })}
                >
                  {p.label}
                </button>
              ))}
              <button className="n-act n-spacer" onClick={create} disabled={!form.title.trim()}>
                Создать
              </button>
              <button className="n-act" onClick={() => setShowCreate(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        {tasks !== null && tasks.length > 0 && (
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

        {tasks === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {tasks?.length === 0 && (
          <div className="n-empty">
            <p>Задач пока нет.</p>
            <p className="n-sub">Заведите первую кнопкой выше — или скажите Джарвису «создай задачу X».</p>
          </div>
        )}

        {visible.length === 0 && (tasks?.length ?? 0) > 0 && (
          <div className="n-empty">
            <p>В этой категории пусто.</p>
          </div>
        )}

        <div className="n-grid wide">
          {visible.map((t) => {
            const status = STATUS[t.status] ?? STATUS.todo;
            const priority = PRIORITY[t.priority] ?? PRIORITY.medium;
            const open = openId === t.id;
            const auto = (t.tags ?? []).includes('auto');
            return (
              <div
                key={t.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={status.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : t.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : t.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{t.title}</h3>
                  <span className="n-badge" data-tone={status.tone}>
                    {status.label}
                  </span>
                </div>

                <div className="n-foot">
                  <span>{when(t.created_at)}</span>
                  {t.priority !== 'medium' && (
                    <>
                      <span>·</span>
                      <span>{priority.label}</span>
                    </>
                  )}
                  {auto && (
                    <>
                      <span>·</span>
                      <span>завела система</span>
                    </>
                  )}
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Что сделать</div>
                      <p className="n-full">{t.title}</p>
                    </div>
                    {t.description && (
                      <div>
                        <div className="n-label">Подробности</div>
                        <p className="n-full">{t.description}</p>
                      </div>
                    )}
                    <div className="n-foot">
                      <span>важность: {priority.label}</span>
                      {t.assigned_agent && <span>· исполнитель: {t.assigned_agent}</span>}
                    </div>
                    <div>
                      <div className="n-label">Перевести в</div>
                      <div className="n-actions" style={{ marginTop: 6 }}>
                        {Object.keys(STATUS).map((s) => (
                          <button
                            key={s}
                            className={`n-act ${t.status === s ? 'active' : ''}`}
                            onClick={() => setStatus(t.id, s)}
                          >
                            {STATUS[s].label}
                          </button>
                        ))}
                        <button className="n-act danger n-spacer" onClick={() => remove(t.id)}>
                          удалить
                        </button>
                      </div>
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
