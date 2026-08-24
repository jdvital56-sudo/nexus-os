import { useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { getAgents, runAgent } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Экран запускал агента со строкой «test task» — то есть кнопка тратила
// деньги на бессмысленный запрос. Теперь задачу пишет человек, и пока она
// не написана, кнопка не работает.
//
// Переписано 23.08.2026 на карточки (стиль Пантеона). Тогда же агенты
// научились делать настоящую работу, а не двигать статусы: с непустой
// задачей Исследователь реально ищет в вебе, Рецензент реально даёт
// вердикт, Строитель предлагает план (кода сам не пишет — правило
// «безопасность важнее самостоятельности»). Поэтому на карточке видно,
// что именно агент делает по директиве и что — при пустом запуске.

const ROLES: Record<string, { label: string; tone: string; directed: string; sweep: string }> = {
  builder: {
    label: 'строитель',
    tone: 'progress',
    directed: 'предложит план реализации — файлы, порядок шагов, риски. Код сам не пишет и не коммитит: план проверяете вы.',
    sweep: 'возьмёт задачи из очереди со словами build/create/implement и пометит их «в работе».',
  },
  librarian: {
    label: 'библиотекарь',
    tone: 'good',
    directed: 'наведёт порядок в графе знаний: свяжет документы, разложит заметки.',
    sweep: 'то же самое — пройдётся по несвязанным документам сам.',
  },
  reviewer: {
    label: 'рецензент',
    tone: 'good',
    directed: 'реально проверит и даст вердикт. Если задача про код — приложит diff незакоммиченного.',
    sweep: 'обойдёт граф и отметит в памяти узлы без единой связи.',
  },
  researcher: {
    label: 'исследователь',
    tone: 'progress',
    directed: 'найдёт ответ в интернете и запишет находку в память с источниками.',
    sweep: 'обойдёт граф и отметит в памяти слабо связанные узлы.',
  },
  monitor: {
    label: 'наблюдатель',
    tone: 'warn',
    directed: 'проверит здоровье системы: процессы, ошибки, живость сервисов.',
    sweep: 'то же самое.',
  },
  curator: {
    label: 'куратор памяти',
    tone: 'neutral',
    directed: 'разберёт память: склеит дубли, понизит достоверность устаревшему, мусор — в архив.',
    sweep: 'то же самое. Ничего не удаляет насовсем.',
  },
  jarvis: {
    label: 'оркестратор',
    tone: 'progress',
    directed: 'решит, кому из агентов передать задачи, и объяснит почему.',
    sweep: 'то же самое по задачам из очереди.',
  },
};

const STATUS: Record<string, { label: string; tone: string }> = {
  idle: { label: 'ждёт', tone: 'neutral' },
  running: { label: 'работает', tone: 'progress' },
  error: { label: 'ошибка', tone: 'off' },
  paused: { label: 'на паузе', tone: 'warn' },
};

function when(iso?: string | null): string {
  if (!iso) return 'ни разу';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return 'ни разу';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function AgentsScreen() {
  const [agents, setAgents] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [task, setTask] = useState<Record<string, string>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<{ id: string; text: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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
      setOutput({ id, text: e?.response?.data?.detail ?? 'Запуск не удался.' });
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Агенты"
        subtitle="Исполнители с ролями. Задачу пишете вы — с ней агент делает настоящую работу, а не отмечает статусы. Запуск стоит денег."
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {agents === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {agents?.length === 0 && (
          <div className="n-empty">
            <p>Агентов пока нет.</p>
            <p className="n-sub">Их заводят через API — на этом экране только запуск.</p>
          </div>
        )}

        <div className="n-grid wide">
          {agents?.map((a) => {
            const role = ROLES[a.role] ?? { label: a.role, tone: 'neutral', directed: '', sweep: '' };
            const status = STATUS[a.status] ?? STATUS.idle;
            const open = openId === a.id;
            const busy = running === a.id;
            const text = (task[a.id] ?? '').trim();
            return (
              <div
                key={a.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={busy ? 'progress' : role.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : a.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : a.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{a.name}</h3>
                  <span className="n-badge" data-tone={busy ? 'progress' : status.tone}>
                    {busy ? 'работает' : status.label}
                  </span>
                </div>

                {a.description && (
                  <p style={{ margin: 0, fontSize: '0.8rem', lineHeight: 1.45, color: 'var(--ink-dim)' }}>
                    {a.description}
                  </p>
                )}

                <div className="n-foot">
                  <span>{role.label}</span>
                  <span>·</span>
                  <span>запускался: {when(a.last_run)}</span>
                  <span className="n-hint">{open ? 'свернуть' : 'поручить'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Что сделает по вашей задаче</div>
                      <p className="n-full" style={{ fontSize: '0.82rem' }}>{role.directed}</p>
                    </div>

                    <div>
                      <div className="n-label">Поручить</div>
                      <div className="n-actions" style={{ marginTop: 6 }}>
                        <input
                          value={task[a.id] ?? ''}
                          onChange={(e) => setTask({ ...task, [a.id]: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && text && !busy) run(a.id);
                          }}
                          placeholder="Что именно сделать"
                          disabled={busy}
                          style={{
                            flex: '1 1 240px',
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
                          onClick={() => run(a.id)}
                          disabled={!text || busy}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                        >
                          <Play className="h-3 w-3" aria-hidden />
                          {busy ? 'работает…' : 'Запустить'}
                        </button>
                      </div>
                      <p className="p-note" style={{ marginTop: 6, fontSize: '0.74rem' }}>
                        Без задачи (пустой запуск) {role.sweep}
                      </p>
                    </div>

                    {output?.id === a.id && (
                      <div>
                        <div className="n-label">Что получилось</div>
                        <p
                          className="n-full"
                          style={{
                            maxHeight: 320,
                            overflow: 'auto',
                            fontFamily: 'var(--p-mono)',
                            fontSize: '0.78rem',
                          }}
                        >
                          {output?.text}
                        </p>
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
