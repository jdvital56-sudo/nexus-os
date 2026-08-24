import { useEffect, useState } from 'react';
import { DollarSign, Moon, CreditCard, Bot, AlertCircle, RefreshCw, Check, Minus } from 'lucide-react';
import type { SystemStatusResponse, WalletSummary, SpendDay } from '../types';
import { getSystemStatus, getWalletSummary, setAutopilot } from '../lib/api';
import { days, money, plural } from '../lib/format';
import { JarvisHudWidget } from '../components/JarvisHudWidget';
import '../styles/pantheon.css';

// Ничего придуманного: каждое число на этом экране приходит с бэкенда.
// Раньше здесь стояли зашитые «сэкономлено $8940» и «ROI 3512%» — их никто
// не считал. Сколько система сэкономила времени и денег, она не знает, и
// пока не научится считать честно, таких карточек тут не будет.
//
// Оформление — по правилам ui-ux-pro-max для плотного дашборда: числа
// моноширинные и с табличными цифрами (столбцы не пляшут при обновлении),
// тренд линией, а не столбиками, состояние подписано словом, а не только
// цветом (дальтоники видят то же самое), фокус виден с клавиатуры.

function whenCharged(daysLeft: number): string {
  if (daysLeft === 0) return 'сегодня';
  if (daysLeft > 0) return `через ${days(daysLeft)}`;
  return `просрочено на ${days(-daysLeft)}`;
}

function ago(iso: string | null): string {
  if (!iso) return 'ещё не запускался';
  // Часть сервисов пишет время без зоны (utcnow), часть — со смещением.
  // Пометку UTC дописываем только там, где зоны нет, иначе выходит NaN.
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const then = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(then.getTime())) return 'время неизвестно';
  const hours = Math.floor((Date.now() - then.getTime()) / 3_600_000);
  if (hours < 1) return 'меньше часа назад';
  if (hours < 24) return `${plural(hours, 'час', 'часа', 'часов')} назад`;
  return `${plural(Math.floor(hours / 24), 'день', 'дня', 'дней')} назад`;
}

// Панели, а не карточки: на дашборде нечего раскрывать — это числа и
// графики, а не список объектов. Тема общая с Пантеоном (24.08.2026).
const CARD = 'n-panel';
const NUM = 'font-mono tabular-nums';

/** Линия трат за две недели. SVG вручную: одна кривая не стоит библиотеки. */
function SpendTrend({ history }: { history: SpendDay[] }) {
  const width = 100;
  const height = 32;
  const peak = Math.max(...history.map((d) => d.spent_usd), 0.0001);
  const step = width / Math.max(history.length - 1, 1);
  const points = history.map((d, i) => [i * step, height - (d.spent_usd / peak) * height]);
  const line = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const area = `0,${height} ${line} ${width},${height}`;

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-28 w-full"
        role="img"
        aria-label={`Траты по дням за ${history.length} дней, максимум ${money(peak)}`}
      >
        <polygon points={area} className="fill-primary/15" />
        <polyline
          points={line}
          fill="none"
          className="stroke-primary"
          strokeWidth={1.2}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
        />
        {points.map(([x, y], i) => (
          <circle key={history[i].date} cx={x} cy={y} r={1.4} className="fill-primary" vectorEffect="non-scaling-stroke">
            <title>{`${history[i].date}: ${money(history[i].spent_usd)}`}</title>
          </circle>
        ))}
      </svg>

      {/* Значения текстом, а не только на графике: наводить мышь, чтобы
          узнать цифру, — плохая замена подписи */}
      <div className="mt-2 flex justify-between text-xs text-gray-400">
        <span className={NUM}>{history[0]?.date.slice(5)}</span>
        <span>
          пик за день <span className={`${NUM} text-gray-200`}>{money(peak)}</span>
        </span>
        <span className={NUM}>{history[history.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="p-8">
      <div className="mb-8 h-8 w-48 animate-pulse rounded bg-gray-800 motion-reduce:animate-none" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`${CARD} h-32 animate-pulse motion-reduce:animate-none`} />
        ))}
      </div>
    </div>
  );
}

export default function HomeScreen() {
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [wallet, setWallet] = useState<WalletSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);

  // Включённый автопилот тратит деньги сам (R-2), поэтому переключатель
  // подписан словом и показывает, что именно сейчас мешает прогону —
  // «выключен» и «включён, но тихие часы» это разные состояния.
  const toggleAutopilot = (next: boolean) => {
    setSwitching(true);
    setAutopilot(next)
      .then(state =>
        setStatus(prev => (prev ? { ...prev, autopilot: state } : prev)),
      )
      .catch(() => setError('Не удалось переключить автопилот'))
      .finally(() => setSwitching(false));
  };

  const load = () => {
    setLoading(true);
    Promise.all([getSystemStatus(), getWalletSummary()])
      .then(([s, w]) => {
        setStatus(s);
        setWallet(w);
        setError(null);
      })
      // Пустой дашборд честнее, чем дашборд с числами из воздуха
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // Траты меняются от каждого сообщения — раз в минуту достаточно
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, []);

  if (error) {
    return (
      <div className="p-8">
        <h1 className="mb-2 text-3xl font-bold text-gray-100">Дашборд</h1>
        <div className="mt-6 flex items-center gap-3 rounded-lg border border-red-500/40 bg-red-500/10 p-5">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
          <span className="text-red-100">{error}</span>
          <button
            onClick={load}
            className="ml-auto cursor-pointer rounded px-3 py-1 text-sm text-red-100 underline transition-colors duration-200 hover:text-gray-100 focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            Повторить
          </button>
        </div>
      </div>
    );
  }

  if (!status || !wallet) return <Skeleton />;

  const { spend, integrations, dream, autopilot } = status;
  const model = integrations.find((i) => i.key === 'llm')?.detail ?? '';
  const share = spend.budget_usd > 0 ? Math.min(spend.spent_usd / spend.budget_usd, 1) : 0;

  const cards = [
    {
      title: 'Потрачено сегодня',
      value: money(spend.spent_usd),
      // «0% лимита» при реальных тратах выглядит как поломка счётчика
      hint: `${share > 0 && share < 0.01 ? '<1' : (share * 100).toFixed(0)}% дневного лимита ${money(spend.budget_usd)}`,
      icon: DollarSign,
      tone: spend.throttled ? 'text-red-400' : 'text-primary',
      bg: spend.throttled ? 'bg-red-400/10' : 'bg-primary/10',
    },
    {
      title: 'Ночной прогон',
      value:
        dream.new_findings > 0
          ? plural(dream.new_findings, 'находка', 'находки', 'находок')
          : 'нет новых',
      hint: ago(dream.last_run_at),
      icon: Moon,
      tone: 'text-secondary',
      bg: 'bg-secondary/10',
    },
    {
      title: 'Подписки',
      value: `${money(wallet.monthly_total_usd)}/мес`,
      hint: `активных: ${wallet.active_count}`,
      icon: CreditCard,
      tone: 'text-blue-400',
      bg: 'bg-blue-400/10',
    },
    {
      title: 'Автопилот Jarvis',
      value: autopilot.enabled ? 'включён' : 'выключен',
      hint: autopilot.enabled
        ? `каждые ${autopilot.interval_min} мин, до ${autopilot.max_runs_per_day} раз в сутки`
        : 'работает только по твоей команде',
      icon: Bot,
      tone: autopilot.enabled ? 'text-amber-400' : 'text-gray-400',
      bg: autopilot.enabled ? 'bg-amber-400/10' : 'bg-gray-700/40',
      action: (
        <div className="mt-3 flex flex-col gap-1.5">
          <button
            onClick={() => toggleAutopilot(!autopilot.enabled)}
            disabled={switching}
            aria-pressed={autopilot.enabled}
            className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary disabled:cursor-wait disabled:opacity-60 ${
              autopilot.enabled
                ? 'border-amber-500/40 text-amber-200 hover:border-amber-400'
                : 'border-gray-700 text-gray-300 hover:border-gray-600 hover:text-gray-100'
            }`}
          >
            {switching ? 'Переключаю…' : autopilot.enabled ? 'Выключить' : 'Включить'}
          </button>
          {/* «Выключен» и «включён, но сейчас тихие часы» — разные
              состояния, и человек не должен их угадывать */}
          {autopilot.enabled && autopilot.blocked_by && (
            <span className="text-xs text-gray-500">сейчас не пойдёт: {autopilot.blocked_by}</span>
          )}
        </div>
      ),
    },
  ];

  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  return (
    <div className="p-6 lg:p-8 pantheon-theme" data-palette={palette}>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">Дашборд</h1>
          <p className="mt-1 text-sm text-gray-400">Что система знает о себе прямо сейчас</p>
        </div>
        <div className="flex items-center gap-4">
          {/* Раньше здесь было просто «Обновить» рядом с индикатором
              Jarvis, и это читалось как «обновить Jarvis». Кнопка всего
              лишь перезапрашивает числа — теперь так и подписана. */}
          <button
            onClick={load}
            title="Перезапросить данные с бэкенда. Автопилот это не запускает."
            className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-800 px-3 py-2 text-sm text-gray-300 transition-colors duration-200 hover:border-gray-700 hover:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <RefreshCw
              className={`h-4 w-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`}
              aria-hidden
            />
            Обновить данные
          </button>
          <JarvisHudWidget
            state={autopilot.enabled ? 'PROCESSING' : 'ONLINE'}
            activeModel={model.toUpperCase()}
          />
        </div>
      </header>

      {spend.throttled && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-red-500/40 bg-red-500/10 p-4">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" aria-hidden />
          <p className="text-sm text-red-100">
            Дневной бюджет исчерпан. Фоновые задачи остановлены до полуночи UTC,
            диалог продолжает работать.
          </p>
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <article key={card.title} className={CARD}>
              <div className="flex items-center gap-3">
                <span className={`${card.bg} rounded-md p-2`}>
                  <Icon className={`h-5 w-5 ${card.tone}`} aria-hidden />
                </span>
                <h3 className="text-sm text-gray-400">{card.title}</h3>
              </div>
              <p className={`mt-3 text-2xl font-bold text-gray-100 ${NUM}`}>{card.value}</p>
              <p className="mt-1 text-xs text-gray-400">{card.hint}</p>
              {'action' in card && card.action}
            </article>
          );
        })}
      </div>

      <section className={`${CARD} mb-6`}>
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-bold text-gray-100">Траты на модели, 14 дней</h2>
          <span className="text-sm text-gray-400">
            сегодня <span className={`${NUM} text-gray-100`}>{money(spend.spent_usd)}</span> из{' '}
            <span className={NUM}>{money(spend.budget_usd)}</span>
          </span>
        </div>

        <div
          className="mb-5 h-1.5 w-full overflow-hidden rounded-full bg-gray-800"
          role="progressbar"
          aria-valuenow={Math.round(share * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Расход дневного бюджета"
        >
          <div
            className={`h-full rounded-full transition-[width] duration-300 ${
              spend.throttled ? 'bg-red-500' : 'bg-primary'
            }`}
            style={{ width: `${share * 100}%` }}
          />
        </div>

        <SpendTrend history={spend.history} />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className={CARD}>
          <h2 className="mb-4 text-lg font-bold text-gray-100">Что подключено</h2>
          <ul className="space-y-2">
            {integrations.map((item) => (
              <li key={item.key} className="flex items-start gap-3 rounded-md bg-darker p-3">
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                    item.connected ? 'bg-primary/15 text-primary' : 'bg-gray-700/60 text-gray-400'
                  }`}
                  aria-hidden
                >
                  {item.connected ? <Check className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                </span>
                <div className="min-w-0">
                  <div className="text-sm text-gray-100">
                    {item.label}{' '}
                    <span className={item.connected ? 'text-primary' : 'text-gray-400'}>
                      — {item.connected ? 'подключено' : 'нет'}
                    </span>
                  </div>
                  <div className="truncate text-xs text-gray-400" title={item.detail}>
                    {item.detail}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <div className="space-y-6">
          <section className={CARD}>
            <h2 className="mb-3 text-lg font-bold text-gray-100">Ночной прогон</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-gray-400">Расписание</dt>
                <dd className={`${NUM} text-gray-100`}>{dream.cron}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-gray-400">Последний прогон</dt>
                <dd className="text-gray-100">{ago(dream.last_run_at)}</dd>
              </div>
              {dream.last_cost_usd != null && (
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-400">Стоил</dt>
                  <dd className={`${NUM} text-gray-100`}>{money(dream.last_cost_usd)}</dd>
                </div>
              )}
            </dl>
            {dream.new_findings > 0 && (
              <p className="mt-4 rounded-md border border-primary/25 bg-primary/10 p-3 text-sm text-primary">
                {plural(dream.new_findings, 'находка ждёт', 'находки ждут', 'находок ждут')} решения
                в Dream Review
              </p>
            )}
          </section>

          <section className={CARD}>
            <h2 className="mb-3 text-lg font-bold text-gray-100">Ближайшие списания</h2>
            {wallet.due_soon.length === 0 ? (
              <p className="text-sm text-gray-400">В ближайшие дни ничего не списывается.</p>
            ) : (
              <ul className="space-y-2">
                {wallet.due_soon.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between gap-3 rounded-md bg-darker p-3"
                  >
                    <span className="text-sm text-gray-100">{s.name}</span>
                    <span
                      className={`text-sm ${NUM} ${
                        s.days_left < 0 ? 'text-red-400' : 'text-gray-300'
                      }`}
                    >
                      {money(s.cost)} · {whenCharged(s.days_left)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {wallet.low_balance.length > 0 && (
              <p className="mt-3 text-sm text-amber-400">
                Баланс на исходе: {wallet.low_balance.map((s) => s.name).join(', ')}
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
