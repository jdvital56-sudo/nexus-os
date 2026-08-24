import { useCallback, useEffect, useState } from 'react';
import { Moon } from 'lucide-react';
import { applyFinding, getDreamBrief, getDreamFindings, skipFinding } from '../lib/api';
import { money, plural } from '../lib/format';
import type { DreamBrief, DreamFinding } from '../types';
import '../styles/pantheon.css';

// Ночной прогон ничего не меняет сам (I-2) — он только предлагает. Этот
// экран и есть то место, где решение принимает человек: Применить или
// Пропустить.
//
// Карточки того же образца, что Идеи/Задачи/Контент/Артефакты (24.08.2026):
// находка сворачивается в заголовок с важностью, клик раскрывает подробности
// и само предлагаемое действие — раньше всё это вываливалось сразу и
// длинный список было не окинуть взглядом.

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

const SEVERITY: Record<string, { label: string; tone: string }> = {
  high: { label: 'важно', tone: 'off' },
  medium: { label: 'стоит взглянуть', tone: 'warn' },
  low: { label: 'мелочь', tone: 'neutral' },
};

const TABS = [
  { key: 'new', label: 'Новые' },
  { key: 'applied', label: 'Применённые' },
  { key: 'skipped', label: 'Пропущенные' },
  { key: '', label: 'Все' },
] as const;

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
  const [openId, setOpenId] = useState<string | null>(null);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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
      setError(reason ? `Не удалось: ${reason}` : 'Решение не сохранилось. Попробуйте ещё раз.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">Ночной прогон</h1>
        <p className="mt-1 text-sm text-gray-400">
          Система разбирает прошедший день, пока вы спите. Меняет что-либо — только с вашего согласия.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
          {error}
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {brief ? (
          <div className="n-panel">
            <div className="n-panel-head">
              <span className="n-panel-title">
                <Moon className="h-4 w-4" aria-hidden />
                Утренний бриф
              </span>
              <span className="n-panel-meta">
                {when(brief.created_at)} · {money(brief.cost_usd)} ·{' '}
                {plural(brief.findings_count, 'находка', 'находки', 'находок')}
              </span>
            </div>
            <p className="n-full">{brief.brief}</p>
          </div>
        ) : (
          !loading && (
            <div className="n-empty">
              <p>Прогон ещё ни разу не отработал.</p>
              <p className="n-sub">
                Он запускается ночью по расписанию. Утром здесь появится бриф и находки.
              </p>
            </div>
          )
        )}

        <div className="n-filters">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {loading && findings.length === 0 && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {!loading && findings.length === 0 && (
          <div className="n-empty">
            <p>{tab === 'new' ? 'Непросмотренных находок нет.' : 'Здесь пока пусто.'}</p>
            {tab === 'new' && (
              <p className="n-sub">Всё, что прогон нашёл, вы уже разобрали. Следующий — сегодня ночью.</p>
            )}
          </div>
        )}

        <div className="n-grid wide">
          {findings.map((f) => {
            const sev = SEVERITY[f.severity] ?? SEVERITY.medium;
            const decided = f.status !== 'new';
            const open = openId === f.finding_id;
            return (
              <div
                key={f.finding_id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={decided ? 'neutral' : sev.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : f.finding_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : f.finding_id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{f.title}</h3>
                  <span className="n-badge" data-tone={decided ? 'neutral' : sev.tone}>
                    {decided ? (f.status === 'applied' ? 'применено' : 'пропущено') : sev.label}
                  </span>
                </div>

                <div className="n-foot">
                  <span>{DIMENSIONS[f.dimension] ?? f.dimension}</span>
                  <span>·</span>
                  <span>{when(f.created_at)}</span>
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    {f.detail && (
                      <div>
                        <div className="n-label">Что нашлось</div>
                        <p className="n-full">{f.detail}</p>
                      </div>
                    )}

                    <div>
                      <div className="n-label">Что произойдёт при «Применить»</div>
                      {f.action ? (
                        <pre className="n-pre">{JSON.stringify(f.action, null, 2)}</pre>
                      ) : (
                        <p className="n-full">
                          Действия у находки нет — «Применить» просто пометит её разобранной.
                        </p>
                      )}
                    </div>

                    {decided ? (
                      <div className="n-foot">
                        {f.status === 'applied' ? '✓ применено' : '— пропущено'} {when(f.resolved_at)}
                      </div>
                    ) : (
                      <div className="n-actions">
                        <button
                          className="n-act active"
                          disabled={busy === f.finding_id}
                          onClick={() => decide(f.finding_id, 'apply')}
                        >
                          Применить
                        </button>
                        <button
                          className="n-act"
                          disabled={busy === f.finding_id}
                          onClick={() => decide(f.finding_id, 'skip')}
                        >
                          Пропустить
                        </button>
                      </div>
                    )}

                    <div className="n-foot">прогон {f.run_id}</div>
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
