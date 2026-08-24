import { useEffect, useState } from 'react';
import { RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react';
import { getHealthReport, type HealthReport } from '../lib/api';
import { ErrorBox } from '../components/ui';
import '../styles/pantheon.css';

// Экран Сторожа (Анубис). Сам сторож (backend/services/watchdog.py) работал
// с самого начала — каждый час проверяет, жива ли система, и пишет в
// Telegram при смене состояния. А показать это было негде: вкладка Анубиса
// в сайдбаре висела неактивной, потому что маршрута у неё не существовало.
// Фаундер спросил прямо: «почему Анубис до сих пор не активен» (24.08.2026).
//
// Сторож намеренно не трогает модель: он обязан работать и тогда, когда
// кончился бюджет или отвалился ключ — то есть ровно в тот момент, когда
// всё остальное молчит и понять причину больше неоткуда.

function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function GuardScreen() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    setLoading(true);
    getHealthReport()
      .then((r) => {
        setReport(r);
        setError(null);
      })
      .catch(() => setError('Сторож не отвечает. Запущен ли бэкенд на :8420?'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // Раз в минуту — сторож на бэкенде и так ходит по кругу каждый час,
    // здесь просто чаще перечитываем, пока экран открыт.
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const broken = report?.checks.filter((c) => !c.ok) ?? [];
  const fine = report?.checks.filter((c) => c.ok) ?? [];

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">Анубис — сторож</h1>
          <p className="mt-1 text-sm text-gray-400">
            Следит, что всё живо. Работает без модели — чтобы отвечать даже когда кончился бюджет
            или отвалился ключ.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden />
          Проверить сейчас
        </button>
      </header>

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {report && (
          <div className="n-panel">
            <div className="n-panel-head">
              <span className="n-panel-title">
                {report.healthy ? (
                  <ShieldCheck className="h-4 w-4" aria-hidden />
                ) : (
                  <ShieldAlert className="h-4 w-4" aria-hidden />
                )}
                {report.healthy ? 'Всё живо' : `Сломано: ${report.broken_count}`}
              </span>
              <span className="n-panel-meta">проверено {when(report.checked_at)}</span>
            </div>
            <p className="n-full">
              {report.healthy
                ? `Все ${report.checks.length} проверок прошли. Сторож ходит по кругу каждый час и напишет в Telegram, если что-то отвалится.`
                : report.critical_count > 0
                  ? `Критичных поломок: ${report.critical_count}. Это то, из-за чего система может молчать.`
                  : 'Есть некритичные замечания — система работает, но не всё в порядке.'}
            </p>
          </div>
        )}

        {!report && !error && (
          <div className="n-empty">
            <p>Опрашиваю систему…</p>
          </div>
        )}

        {/* Сломанное — первым и всегда раскрытым: прятать поломку за клик
            значит надеяться, что человек до неё долистает. */}
        {broken.length > 0 && (
          <div className="n-grid wide" style={{ marginBottom: 12 }}>
            {broken.map((c) => (
              <div key={c.id} className="n-card open" data-tone={c.critical ? 'off' : 'warn'}>
                <div className="n-top">
                  <h3 className="n-title">{c.label}</h3>
                  <span className="n-badge" data-tone={c.critical ? 'off' : 'warn'}>
                    {c.critical ? 'критично' : 'сломано'}
                  </span>
                </div>
                {c.detail && (
                  <div className="n-body">
                    <p className="n-full">{c.detail}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {fine.length > 0 && (
          <div className="n-feed">
            {fine.map((c) => (
              <div key={c.id} className="n-row" data-tone="good">
                <div className="n-row-line">
                  <span className="n-badge" data-tone="good">
                    в порядке
                  </span>
                  <span className="n-row-text">{c.label}</span>
                  <span className="n-row-meta">{c.detail}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
