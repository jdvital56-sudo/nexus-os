import { useEffect, useState } from 'react';
import { Plus, ExternalLink, XCircle } from 'lucide-react';
import {
  cancelService,
  createService,
  getServices,
  getWalletSummary,
} from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, NUM, PageHeader, Pill, Skeleton } from '../components/ui';
import { days, money } from '../lib/format';
import type { WalletSummary } from '../types';

// Реестр платных сервисов. Бэкенд считает деньги и напоминает о списаниях
// в 9:00 с PR-26, но увидеть весь список можно было только через API.
//
// Здесь важна не красота, а два вопроса: сколько уходит в месяц и что
// спишется в ближайшие дни. Поэтому они стоят первыми.

const PERIODS: Record<string, string> = {
  monthly: 'в месяц',
  yearly: 'в год',
  prepaid: 'предоплата',
  free: 'бесплатно',
};

const EMPTY_FORM = {
  name: '',
  cost: '',
  period: 'monthly',
  next_charge: '',
  cancel_url: '',
  notes: '',
};

function whenCharged(daysLeft: number | null | undefined): string {
  if (daysLeft == null) return 'дата неизвестна';
  if (daysLeft === 0) return 'сегодня';
  if (daysLeft > 0) return `через ${days(daysLeft)}`;
  return `просрочено на ${days(-daysLeft)}`;
}

export default function WalletScreen() {
  const [services, setServices] = useState<any[] | null>(null);
  const [summary, setSummary] = useState<WalletSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const load = () => {
    Promise.all([getServices('active'), getWalletSummary()])
      .then(([s, sum]) => {
        setServices(s);
        setSummary(sum);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const add = async () => {
    if (!form.name.trim()) return;
    try {
      await createService({
        name: form.name.trim(),
        cost: Number(form.cost) || 0,
        period: form.period,
        next_charge: form.next_charge || null,
        cancel_url: form.cancel_url,
        notes: form.notes,
      });
      setForm({ ...EMPTY_FORM });
      setShowAdd(false);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.error ?? 'Сервис не добавился.');
    }
  };

  // Отмена не удаляет запись: важно помнить, что подписка была и когда её
  // закрыли — иначе через месяц не вспомнить, за что списали
  const cancel = async (id: string, name: string) => {
    if (!window.confirm(`Пометить «${name}» как отменённый? Запись останется в истории.`)) return;
    try {
      await cancelService(id);
      load();
    } catch {
      setError('Не удалось отметить отмену.');
    }
  };

  const dueSoon = summary?.due_soon ?? [];
  const lowBalance = summary?.low_balance ?? [];

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Подписки"
        subtitle="За что система платит и когда спишут в следующий раз. Напоминание приходит в Телеграм в 9:00."
        action={
          <button onClick={() => setShowAdd(!showAdd)} className={BTN}>
            <Plus className="h-4 w-4" aria-hidden />
            Добавить сервис
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      {showAdd && (
        <div className={`${CARD} mb-6 space-y-3`}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-gray-400">
              Название
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className={`${INPUT} mt-1`}
                placeholder="ChatGPT Plus"
                autoFocus
              />
            </label>
            <label className="text-xs text-gray-400">
              Сколько стоит, $
              <input
                value={form.cost}
                onChange={(e) => setForm({ ...form, cost: e.target.value })}
                className={`${INPUT} mt-1`}
                placeholder="20"
                inputMode="decimal"
              />
            </label>
            <label className="text-xs text-gray-400">
              Дата следующего списания
              <input
                type="date"
                value={form.next_charge}
                onChange={(e) => setForm({ ...form, next_charge: e.target.value })}
                className={`${INPUT} mt-1`}
              />
            </label>
            <label className="text-xs text-gray-400">
              Ссылка на отмену
              <input
                value={form.cancel_url}
                onChange={(e) => setForm({ ...form, cancel_url: e.target.value })}
                className={`${INPUT} mt-1`}
                placeholder="https://…"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {Object.entries(PERIODS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setForm({ ...form, period: key })}
                className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                  form.period === key
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-gray-100'
                }`}
              >
                {label}
              </button>
            ))}
            <button onClick={add} className={`${BTN} ml-auto`} disabled={!form.name.trim()}>
              Добавить
            </button>
            <button onClick={() => setShowAdd(false)} className={BTN_GHOST}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {summary && (
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <div className={CARD}>
            <h3 className="text-sm text-gray-400">Уходит в месяц</h3>
            <p className={`mt-2 text-2xl font-bold text-gray-100 ${NUM}`}>
              {money(summary.monthly_total_usd)}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              активных сервисов: {summary.active_count}
            </p>
          </div>
          <div className={CARD}>
            <h3 className="text-sm text-gray-400">Скоро спишут</h3>
            <p className={`mt-2 text-2xl font-bold ${dueSoon.length ? 'text-amber-300' : 'text-gray-100'} ${NUM}`}>
              {dueSoon.length}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {dueSoon.length ? dueSoon.map((s) => s.name).join(', ') : 'в ближайшие дни ничего'}
            </p>
          </div>
          <div className={CARD}>
            <h3 className="text-sm text-gray-400">Баланс на исходе</h3>
            <p className={`mt-2 text-2xl font-bold ${lowBalance.length ? 'text-red-300' : 'text-gray-100'} ${NUM}`}>
              {lowBalance.length}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {lowBalance.length ? lowBalance.map((s) => s.name).join(', ') : 'везде хватает'}
            </p>
          </div>
        </div>
      )}

      {services === null && !error && <Skeleton rows={2} />}

      {services?.length === 0 && (
        <Empty
          title="Реестр пуст."
          hint="Добавь сюда всё, за что платишь — система будет напоминать о списаниях и следить за остатками там, где это возможно."
        />
      )}

      <div className="space-y-2">
        {services?.map((s) => {
          const due = dueSoon.find((d) => d.id === s.id);
          const low = lowBalance.some((l) => l.id === s.id);
          return (
            <article key={s.id} className={CARD}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-semibold text-gray-100">{s.name}</h3>
                  <p className="mt-0.5 text-sm text-gray-400">
                    {s.cost ? `${money(s.cost)} ${PERIODS[s.period] ?? s.period}` : PERIODS[s.period] ?? s.period}
                    {s.balance != null && (
                      <>
                        {' · '}
                        <span className={low ? 'text-red-300' : 'text-gray-300'}>
                          остаток {money(s.balance)}
                        </span>
                      </>
                    )}
                  </p>
                  {s.notes && <p className="mt-1 text-xs text-gray-500">{s.notes}</p>}
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {due && (
                    <Pill
                      text={whenCharged(due.days_left)}
                      tone={due.days_left < 0 ? 'red' : 'amber'}
                    />
                  )}
                  {!due && s.next_charge && (
                    <span className={`text-xs text-gray-500 ${NUM}`}>списание {s.next_charge}</span>
                  )}
                  {s.cancel_url && (
                    <a
                      href={s.cancel_url}
                      target="_blank"
                      rel="noreferrer"
                      className={BTN_GHOST}
                      title="Открыть страницу отмены"
                    >
                      <ExternalLink className="h-4 w-4" aria-hidden />
                      отменить
                    </a>
                  )}
                  <button onClick={() => cancel(s.id, s.name)} className={BTN_GHOST}>
                    <XCircle className="h-4 w-4" aria-hidden />
                    не плачу больше
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
