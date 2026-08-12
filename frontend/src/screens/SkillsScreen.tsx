import { useCallback, useEffect, useState } from 'react';
import { Play, Sparkles, ChevronDown, ChevronRight } from 'lucide-react';
import { getSkill, getSkills, runSkill } from '../lib/api';
import { plural } from '../lib/format';

// Скиллы — это записанный порядок действий: создать задачу, положить узел в
// граф, отметить в журнале. Бэкенд их исполняет с PR-6, а экран до сих пор
// был заглушкой с текстом «интерфейс подключается в PR-21».
//
// Главное, что здесь должно быть видно: что именно скилл сделает, если его
// запустить. Кнопка «выполнить» без этого — прыжок в темноту.

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

const CARD = 'rounded-lg border border-gray-800 bg-dark p-5';

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
  const [result, setResult] = useState<{ id: string; log: RunEntry[]; name: string } | null>(null);

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

  if (error && skills.length === 0) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="mb-4 text-2xl font-bold text-white">Скиллы</h1>
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-100">{error}</div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white lg:text-3xl">Скиллы</h1>
        <p className="mt-1 text-sm text-gray-400">
          Записанный порядок действий. Система выполнит его точно так, как здесь написано —
          без модели и без импровизации.
        </p>
      </header>

      {loading && skills.length === 0 && (
        <div className={`${CARD} h-24 animate-pulse motion-reduce:animate-none`} />
      )}

      {!loading && skills.length === 0 && (
        <div className={`${CARD} text-center text-gray-300`}>Скиллов пока нет.</div>
      )}

      <div className="space-y-3">
        {skills.map((skill) => {
          const open = openId === skill.id;
          const detail = details[skill.id];
          const params = paramsOf(detail);
          return (
            <article key={skill.id} className={CARD}>
              <button
                onClick={() => toggle(skill)}
                className="flex w-full cursor-pointer items-start gap-3 text-left focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <span className="mt-0.5 rounded-md bg-primary/10 p-2">
                  <Sparkles className="h-4 w-4 text-primary" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-semibold text-white">{skill.name}</span>
                    {skill.category && (
                      <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-gray-400">
                        {skill.category}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-sm text-gray-400">{skill.description}</span>
                  <span className="mt-1 block font-mono text-[11px] text-gray-500">
                    {plural(skill.steps ?? 0, 'шаг', 'шага', 'шагов')}
                    {params.length > 0 && ` · нужны: ${params.join(', ')}`}
                  </span>
                </span>
                {open ? (
                  <ChevronDown className="h-4 w-4 shrink-0 text-gray-500" aria-hidden />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0 text-gray-500" aria-hidden />
                )}
              </button>

              {open && (
                <div className="mt-4 border-t border-gray-800 pt-4">
                  {/* Что произойдёт — до того, как нажал */}
                  <h3 className="mb-2 text-xs uppercase tracking-wider text-gray-500">Что сделает</h3>
                  <ol className="mb-4 space-y-1">
                    {(detail?.steps ?? []).map((step, i) => (
                      <li key={i} className="flex gap-2 text-sm text-gray-300">
                        <span className="font-mono text-gray-600">{i + 1}.</span>
                        <span>
                          {ACTIONS[step.action] ?? step.action}
                          {step.condition && step.condition !== 'always' && (
                            <span className="text-gray-500"> — если {step.condition}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ol>

                  {params.length > 0 && (
                    <div className="mb-4 grid gap-2 sm:grid-cols-2">
                      {params.map((p) => (
                        <label key={p} className="text-xs text-gray-400">
                          {p}
                          <input
                            value={values[skill.id]?.[p] ?? ''}
                            onChange={(e) =>
                              setValues((prev) => ({
                                ...prev,
                                [skill.id]: { ...(prev[skill.id] ?? {}), [p]: e.target.value },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-800 bg-darker px-3 py-1.5 text-sm text-gray-100 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        </label>
                      ))}
                    </div>
                  )}

                  <button
                    onClick={() => run(skill)}
                    disabled={busy === skill.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-darker transition-colors duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    <Play className="h-4 w-4" aria-hidden />
                    {busy === skill.id ? 'Выполняю…' : 'Выполнить'}
                  </button>

                  {result?.id === skill.id && (
                    <div className="mt-4 rounded-md bg-darker p-3">
                      <h4 className="mb-2 text-xs text-gray-400">Выполнено: {result.name}</h4>
                      <ul className="space-y-1 text-xs">
                        {result.log.map((entry, i) => (
                          <li key={i} className="flex gap-2">
                            <span
                              className={
                                entry.status === 'ok'
                                  ? 'text-primary'
                                  : entry.status === 'skipped'
                                    ? 'text-gray-500'
                                    : 'text-red-400'
                              }
                            >
                              {entry.status === 'ok' ? '✓' : entry.status === 'skipped' ? '–' : '✕'}
                            </span>
                            <span className="text-gray-300">
                              {ACTIONS[entry.action] ?? entry.action}
                              {entry.error && <span className="text-red-400"> — {entry.error}</span>}
                              {entry.result && Object.keys(entry.result).length > 0 && (
                                <span className="text-gray-500">
                                  {' '}
                                  ({Object.entries(entry.result)
                                    .map(([k, v]) => `${k}=${String(v).slice(0, 40)}`)
                                    .join(', ')})
                                </span>
                              )}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
