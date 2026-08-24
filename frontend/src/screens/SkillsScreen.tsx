import { useCallback, useEffect, useState } from 'react';
import { Play } from 'lucide-react';
import { getSkill, getSkills, runSkill, setSkillEnabled } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import { plural } from '../lib/format';
import '../styles/pantheon.css';

// Скиллы — это записанный порядок действий: создать задачу, положить узел в
// граф, отметить в журнале. Система выполнит его точно так, как записано —
// без модели и без импровизации.
//
// Главное, что здесь должно быть видно: что именно скилл сделает, если его
// запустить. Кнопка «выполнить» без этого — прыжок в темноту.
//
// Переписано 24.08.2026 на карточки (стиль Пантеона, восьмой экран).

interface SkillStep {
  action: string;
  params?: Record<string, any>;
  condition?: string;
}

/** Список отдаёт число шагов, подробности — сами шаги. Это разные формы. */
interface Skill {
  id: string;
  name: string;
  description: string;
  category?: string;
  steps: number;
  /** Выключенный скилл остаётся на диске, но не запускается */
  enabled?: boolean;
}

interface SkillDetail {
  name: string;
  description: string;
  category?: string;
  steps: SkillStep[];
}

interface RunEntry {
  action: string;
  status: string;
  result?: Record<string, any>;
  error?: string;
}

const ACTIONS: Record<string, string> = {
  create_task: 'создать задачу',
  add_graph_node: 'добавить узел в граф',
  add_graph_edge: 'связать узлы',
  add_memory_fact: 'записать факт в память',
  create_document: 'создать документ',
  log: 'отметить в журнале',
};

/** Плейсхолдеры вида {topic} — это и есть параметры скилла. */
function paramsOf(detail: SkillDetail | undefined): string[] {
  const found = new Set<string>();
  for (const step of detail?.steps ?? []) {
    const text = JSON.stringify(step.params ?? {});
    for (const m of text.matchAll(/\{(\w+)\}/g)) found.add(m[1]);
  }
  return [...found];
}

export default function SkillsScreen() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, SkillDetail>>({});
  const [values, setValues] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [result, setResult] = useState<{ id: string; log: RunEntry[]; name: string } | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = useCallback(() => {
    setLoading(true);
    getSkills()
      .then((s) => {
        setSkills(s);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  // Шаги подтягиваются, когда карточку раскрыли: список их не отдаёт
  const toggle = async (skill: Skill) => {
    if (openId === skill.id) {
      setOpenId(null);
      return;
    }
    setOpenId(skill.id);
    if (details[skill.id]) return;
    try {
      const detail = await getSkill(skill.id);
      setDetails((prev) => ({ ...prev, [skill.id]: detail }));
    } catch {
      setError('Не удалось прочитать шаги скилла.');
    }
  };

  const toggleEnabled = async (skill: Skill) => {
    const next = skill.enabled === false;
    setToggling(skill.id);
    try {
      await setSkillEnabled(skill.id, next);
      setSkills((prev) => prev.map((s) => (s.id === skill.id ? { ...s, enabled: next } : s)));
      setError(null);
    } catch {
      setError('Не удалось переключить скилл.');
    } finally {
      setToggling(null);
    }
  };

  const run = async (skill: Skill) => {
    setBusy(skill.id);
    setResult(null);
    try {
      const res = await runSkill(skill.id, values[skill.id] ?? {});
      setResult({ id: skill.id, name: res.skill_name ?? skill.name, log: res.log ?? [] });
    } catch (e: any) {
      setError(e?.response?.data?.error ?? 'Скилл не выполнился.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Скиллы"
        subtitle="Записанный порядок действий. Система выполнит его точно так, как здесь написано — без модели и без импровизации."
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {loading && skills.length === 0 && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {!loading && skills.length === 0 && (
          <div className="n-empty">
            <p>Скиллов пока нет.</p>
            <p className="n-sub">Их описывают файлами в папке скиллов — на этом экране только запуск.</p>
          </div>
        )}

        <div className="n-grid wide">
          {skills.map((s) => {
            const open = openId === s.id;
            const detail = details[s.id];
            const off = s.enabled === false;
            const params = paramsOf(detail);
            const running = busy === s.id;
            return (
              <div
                key={s.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={off ? 'off' : running ? 'progress' : 'good'}
                role="button"
                tabIndex={0}
                onClick={() => toggle(s)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggle(s);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{s.name}</h3>
                  <span className="n-badge" data-tone={off ? 'off' : 'good'}>
                    {off ? 'выключен' : 'включён'}
                  </span>
                </div>

                {s.description && (
                  <p style={{ margin: 0, fontSize: '0.8rem', lineHeight: 1.45, color: 'var(--ink-dim)' }}>
                    {s.description}
                  </p>
                )}

                <div className="n-foot">
                  <span>{plural(s.steps, 'шаг', 'шага', 'шагов')}</span>
                  {s.category && (
                    <>
                      <span>·</span>
                      <span>{s.category}</span>
                    </>
                  )}
                  <span className="n-hint">{open ? 'свернуть' : 'что сделает'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Что произойдёт по шагам</div>
                      {!detail && <p className="n-full" style={{ fontSize: '0.82rem' }}>Читаю шаги…</p>}
                      {detail && (
                        <ol style={{ margin: '6px 0 0', paddingLeft: 20, color: 'var(--ink)' }}>
                          {detail.steps.map((step, i) => (
                            <li key={i} style={{ fontSize: '0.84rem', lineHeight: 1.6 }}>
                              {ACTIONS[step.action] ?? step.action}
                              {step.condition && (
                                <span style={{ color: 'var(--ink-dimmer)' }}> — если {step.condition}</span>
                              )}
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>

                    {params.length > 0 && (
                      <div>
                        <div className="n-label">Что нужно указать</div>
                        <div className="n-actions" style={{ marginTop: 6 }}>
                          {params.map((p) => (
                            <input
                              key={p}
                              value={values[s.id]?.[p] ?? ''}
                              onChange={(e) =>
                                setValues((prev) => ({
                                  ...prev,
                                  [s.id]: { ...(prev[s.id] ?? {}), [p]: e.target.value },
                                }))
                              }
                              placeholder={p}
                              style={{
                                flex: '1 1 160px',
                                background: 'var(--panel-2)',
                                border: '1px solid var(--line)',
                                borderRadius: 6,
                                color: 'var(--ink)',
                                padding: '6px 10px',
                                fontFamily: 'var(--p-body)',
                                fontSize: '0.82rem',
                              }}
                            />
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="n-actions">
                      <button
                        className="n-act"
                        onClick={() => run(s)}
                        disabled={off || running}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                        title={off ? 'Скилл выключен' : undefined}
                      >
                        <Play className="h-3 w-3" aria-hidden />
                        {running ? 'выполняю…' : 'Выполнить'}
                      </button>
                      <button
                        className="n-act n-spacer"
                        onClick={() => toggleEnabled(s)}
                        disabled={toggling === s.id}
                      >
                        {off ? 'включить' : 'выключить'}
                      </button>
                    </div>

                    {result?.id === s.id && (
                      <div>
                        <div className="n-label">Что получилось</div>
                        <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                          {result.log.map((entry, i) => (
                            <li
                              key={i}
                              style={{
                                fontSize: '0.8rem',
                                lineHeight: 1.6,
                                color: entry.status === 'error' ? '#d99a9a' : 'var(--ink)',
                              }}
                            >
                              {ACTIONS[entry.action] ?? entry.action} — {entry.status}
                              {entry.error && ` (${entry.error})`}
                            </li>
                          ))}
                          {result.log.length === 0 && (
                            <li style={{ fontSize: '0.8rem', color: 'var(--ink-dimmer)' }}>
                              Скилл отработал молча.
                            </li>
                          )}
                        </ul>
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
