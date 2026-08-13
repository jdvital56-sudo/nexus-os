import { useCallback, useEffect, useState } from 'react';
import { Check, Moon, SkipForward, AlertTriangle, Info, Flame } from 'lucide-react';
import { applyFinding, getDreamBrief, getDreamFindings, skipFinding } from '../lib/api';
import { money, plural } from '../lib/format';
import type { DreamBrief, DreamFinding } from '../types';

// Ночной прогон ничего не меняет сам (I-2) — он только предлагает. Этот
// экран и есть то место, где решение принимает человек: Применить или
// Пропустить. До PR-21 здесь висела заглушка с текстом «Dream Cadence
// написан, но пока не запускается» — она врала, прогон работает с PR-11.

const DIMENSIONS: Record<string, string> = {
  'Cost Intelligence': 'Расходы',
  'Conversation & Context Drift': 'Потеря контекста',
  'Skill Performance': 'Скиллы',
  'Memory Hygiene': 'Гигиена памяти',
  'Workflow Patterns': 'Повторы в работе',
  'Session Hygiene': 'Зависшие сессии',
  'External Opportunities': 'Что нового снаружи',
  'Business Outcomes': 'Движение к целям',
};

const SEVERITY = {
  high: { label: 'важно', color: 'text-red-300', bg: 'bg-red-500/10', ring: 'border-red-500/40', icon: Flame },
  medium: { label: 'стоит взглянуть', color: 'text-amber-300', bg: 'bg-amber-500/10', ring: 'border-amber-500/30', icon: AlertTriangle },
  low: { label: 'мелочь', color: 'text-gray-300', bg: 'bg-gray-500/10', ring: 'border-gray-700', icon: Info },
} as const;

const TABS = [
  { key: 'new', label: 'Новые' },
  { key: 'applied', label: 'Применённые' },
  { key: 'skipped', label: 'Пропущенные' },
  { key: '', label: 'Все' },
] as const;

const CARD = 'rounded-lg border border-gray-800 bg-dark p-5';

function when(iso: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
}

export default function DreamReviewScreen() {
  const [brief, setBrief] = useState<DreamBrief | null>(null);
  const [findings, setFindings] = useState<DreamFinding[]>([]);
  const [tab, setTab] = useState<string>('new');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([getDreamFindings(tab || undefined), getDreamBrief()])
      .then(([f, b]) => {
        setFindings(f);
        setBrief(b);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'))
      .finally(() => setLoading(false));
  }, [tab]);

  useEffect(load, [load]);

  const decide = async (id: string, verdict: 'apply' | 'skip') => {
    setBusy(id);
    try {
      await (verdict === 'apply' ? applyFinding(id) : skipFinding(id));
      load();
    } catch (e: any) {
      // Причину знает бэкенд — «что-то пошло не так» тут бесполезно
      const reason = e?.response?.data?.error ?? e?.response?.data?.detail;
      setError(reason ? `Не удалось: ${reason}` : 'Решение не сохранилось. Попробуй ещё раз.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">Ночной прогон</h1>
          <p className="mt-1 text-sm text-gray-400">
            Система разбирает прошедший день, пока ты спишь. Меняет что-либо — только с твоего согласия.
          </p>
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
          {error}
        </div>
      )}

      {brief ? (
        <section className={`${CARD} mb-6`}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-lg font-bold text-gray-100">
              <Moon className="h-5 w-5 text-secondary" aria-hidden />
              Утренний бриф
            </h2>
            <span className="font-mono text-xs tabular-nums text-gray-400">
              {when(brief.created_at)} · {money(brief.cost_usd)} · {plural(brief.findings_count, 'находка', 'находки', 'находок')}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-200">{brief.brief}</p>
        </section>
      ) : (
        !loading && (
          <section className={`${CARD} mb-6`}>
            <p className="text-sm text-gray-300">Прогон ещё ни разу не отработал.</p>
            <p className="mt-2 text-sm text-gray-400">
              Он запускается ночью по расписанию. Утром здесь появится бриф и находки.
            </p>
          </section>
        )
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
              tab === t.key
                ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-gray-100'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && findings.length === 0 && (
        <div className={`${CARD} h-24 animate-pulse motion-reduce:animate-none`} />
      )}

      {!loading && findings.length === 0 && (
        <div className={`${CARD} text-center`}>
          <p className="text-gray-300">
            {tab === 'new' ? 'Непросмотренных находок нет.' : 'Здесь пока пусто.'}
          </p>
          {tab === 'new' && (
            <p className="mt-2 text-sm text-gray-400">
              Всё, что прогон нашёл, ты уже разобрал. Следующий — сегодня ночью.
            </p>
          )}
        </div>
      )}

      <div className="space-y-3">
        {findings.map((f) => {
          const sev = SEVERITY[f.severity] ?? SEVERITY.medium;
          const Icon = sev.icon;
          const decided = f.status !== 'new';
          return (
            <article key={f.finding_id} className={`rounded-lg border ${sev.ring} bg-dark p-5`}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className={`flex items-center gap-1.5 rounded-full ${sev.bg} px-2 py-0.5 text-xs ${sev.color}`}>
                  <Icon className="h-3 w-3" aria-hidden />
                  {sev.label}
                </span>
                <span className="rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-300">
                  {DIMENSIONS[f.dimension] ?? f.dimension}
                </span>
                {decided && (
                  <span className="text-xs text-gray-400">
                    {f.status === 'applied' ? '✓ применено' : '— пропущено'} {when(f.resolved_at)}
                  </span>
                )}
              </div>

              <h3 className="text-base font-semibold text-gray-100">{f.title}</h3>
              {f.detail && <p className="mt-1 whitespace-pre-wrap text-sm text-gray-300">{f.detail}</p>}

              {f.action ? (
                <p className="mt-3 rounded-md bg-darker p-3 font-mono text-xs text-gray-300">
                  Применить = {JSON.stringify(f.action)}
                </p>
              ) : (
                <p className="mt-3 text-xs text-gray-500">
                  Действия у находки нет — «Применить» просто пометит её разобранной.
                </p>
              )}

              {!decided && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    onClick={() => decide(f.finding_id, 'apply')}
                    disabled={busy === f.finding_id}
                    className="flex cursor-pointer items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-darker transition-colors duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    <Check className="h-4 w-4" aria-hidden />
                    Применить
                  </button>
                  <button
                    onClick={() => decide(f.finding_id, 'skip')}
                    disabled={busy === f.finding_id}
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors duration-200 hover:border-gray-600 hover:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 disabled:opacity-50"
                  >
                    <SkipForward className="h-4 w-4" aria-hidden />
                    Пропустить
                  </button>
                </div>
              )}

              <p className="mt-3 font-mono text-[11px] tabular-nums text-gray-500">
                {when(f.created_at)} · прогон {f.run_id}
              </p>
            </article>
          );
        })}
      </div>
    </div>
  );
}
