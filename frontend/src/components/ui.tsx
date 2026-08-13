import type { ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { useLang } from '../lib/i18n';

// Общие блоки экранов. Раньше каждый экран нёс свои инлайн-стили, из-за
// чего одна и та же карточка выглядела в трёх местах по-разному, а любая
// правка оформления требовала обойти одиннадцать файлов.

export const CARD = 'rounded-lg border border-gray-800 bg-dark p-5';
export const NUM = 'font-mono tabular-nums';
export const INPUT =
  'w-full rounded-md border border-gray-800 bg-darker px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary';
export const BTN =
  'flex cursor-pointer items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-darker transition-colors duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-40';
export const BTN_GHOST =
  'flex cursor-pointer items-center gap-2 rounded-md border border-gray-800 px-3 py-2 text-sm text-gray-300 transition-colors duration-200 hover:border-gray-700 hover:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary';

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-gray-400">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/** Пусто — это состояние, а не ошибка: объясняем, откуда тут что берётся. */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className={`${CARD} text-center`}>
      <p className="text-gray-300">{title}</p>
      {hint && <p className="mx-auto mt-2 max-w-xl text-sm text-gray-400">{hint}</p>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useLang();
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-red-500/40 bg-red-500/10 p-4">
      <AlertCircle className="h-5 w-5 shrink-0 text-red-400" aria-hidden />
      <span className="text-sm text-red-100">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="ml-auto cursor-pointer text-sm text-red-100 underline focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          {t('Повторить')}
        </button>
      )}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={`${CARD} h-20 animate-pulse motion-reduce:animate-none`} />
      ))}
    </div>
  );
}

/** Метка состояния. Цвет дублируется словом — дальтоник видит то же самое. */
export function Pill({ text, tone = 'gray' }: { text: string; tone?: string }) {
  const tones: Record<string, string> = {
    gray: 'bg-gray-800 text-gray-300',
    green: 'bg-primary/10 text-primary',
    blue: 'bg-blue-500/10 text-blue-300',
    amber: 'bg-amber-500/10 text-amber-300',
    red: 'bg-red-500/10 text-red-300',
    violet: 'bg-secondary/10 text-secondary',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] ${tones[tone] ?? tones.gray}`}>{text}</span>
  );
}

/** Дата в человеческом виде. Часть сервисов пишет время без зоны. */
export function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
