import { useEffect, useState } from 'react';
import { Plus, ExternalLink } from 'lucide-react';
import {
  cancelService,
  createService,
  getServices,
  getWalletSummary,
  updateService,
} from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import { days, money } from '../lib/format';
import type { WalletSummary } from '../types';
import '../styles/pantheon.css';

// Реестр платных сервисов. Бэкенд считает деньги и напоминает о списаниях
// в 9:00 с PR-26.
//
// Переписано 23.08.2026 на карточки (стиль Пантеона, см. .n-card в
// styles/pantheon.css) по двум жалобам фаундера сразу: «это не все
// подписки» и «не видно, сколько денег у меня на счету».
//
// Про деньги: автоматически баланс отдаёт только DeepSeek. У Anthropic,
// fal.ai и Hetzner открытого API остатка нет, а лезть в его личные
// кабинеты нельзя — поэтому баланс можно вписать руками прямо в карточке,
// и рядом видно, когда цифра последний раз обновлялась. Неизвестные
// балансы показываются явно, а не прячутся: «$1.98 на счетах» без
// оговорки читалось бы как полная картина, хотя это остаток одного
// сервиса из трёх.

const PERIODS: Record<string, string> = {
  monthly: 'в месяц',
  yearly: 'в год',
  prepaid: 'предоплата',
  free: 'бесплатно',
};

const CATEGORY_TONE: Record<string, string> = {
  hosting: 'progress',
  ai: 'good',
  tools: 'neutral',
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

function daysUntil(iso?: string | null): number | null {
  if (!iso) return null;
  const target = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

function checkedAgo(iso?: string | null): string {
  if (!iso) return 'не вводился';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return 'не вводился';
  const hours = Math.floor((Date.now() - d.getTime()) / 3600000);
  if (hours < 1) return 'только что';
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} дн назад`;
}

export default function WalletScreen() {
  const [services, setServices] = useState<any[] | null>(null);
  const [summary, setSummary] = useState<WalletSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [openId, setOpenId] = useState<string | null>(null);
  const [balanceDraft, setBalanceDraft] = useState<Record<string, string>>({});
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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
        next_charge: form.next_charge || undefined,
        cancel_url: form.cancel_url || undefined,
        notes: form.notes || undefined,
      });
      setForm({ ...EMPTY_FORM });
      setShowAdd(false);
      load();
    } catch {
      setError('Сервис не добавился.');
    }
  };

  const saveBalance = async (id: string) => {
    const raw = balanceDraft[id];
    if (raw === undefined || raw === '') return;
    const value = Number(raw.replace(',', '.'));
    if (Number.isNaN(value)) {
      setError('Баланс должен быть числом.');
      return;
    }
    try {
      await updateService(id, { balance: value });
      setBalanceDraft((d) => ({ ...d, [id]: '' }));
      load();
    } catch {
      setError('Не удалось сохранить баланс.');
    }
  };

  const cancel = async (id: string) => {
    try {
      await cancelService(id);
      load();
    } catch {
      setError('Не удалось отметить отмену.');
    }
  };

  const prepaid = summary?.prepaid;

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Подписки"
        subtitle="Что оплачено, когда спишется и сколько осталось на счетах."
        action={
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
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

      <div className="pantheon-theme" data-palette={palette}>
        {summary && (
          <div className="p-stats">
            <div className="p-stat">
              <div className="p-k">Уходит в месяц</div>
              <div className="p-v">{money(summary.monthly_total_usd)}</div>
            </div>
            <div className="p-stat">
              <div className="p-k">На предоплаченных счетах</div>
              <div className="p-v">{prepaid ? money(prepaid.total) : '—'}</div>
            </div>
            <div className="p-stat">
              <div className="p-k">Баланс неизвестен</div>
              <div className="p-v">{prepaid?.unknown.length ?? 0} серв.</div>
            </div>
            <div className="p-stat">
              <div className="p-k">Активных</div>
              <div className="p-v">{summary.active_count}</div>
            </div>
          </div>
        )}

        {prepaid && prepaid.unknown.length > 0 && (
          <p className="p-note" style={{ marginBottom: 14 }}>
            Баланс не вписан у: {prepaid.unknown.join(', ')}. Эти сервисы не отдают остаток по API —
            откройте карточку и впишите цифру руками, тогда она попадёт в сумму.
          </p>
        )}

        {showAdd && (
          <div className="n-newbox">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Название сервиса"
              autoFocus
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                value={form.cost}
                onChange={(e) => setForm({ ...form, cost: e.target.value })}
                placeholder="Сколько стоит"
                style={{ flex: '1 1 140px' }}
              />
              <input
                value={form.next_charge}
                onChange={(e) => setForm({ ...form, next_charge: e.target.value })}
                placeholder="Дата списания (2026-09-01)"
                style={{ flex: '1 1 200px' }}
              />
            </div>
            <div className="n-actions">
              {Object.entries(PERIODS).map(([key, label]) => (
                <button
                  key={key}
                  className={`n-act ${form.period === key ? 'active' : ''}`}
                  onClick={() => setForm({ ...form, period: key })}
                >
                  {label}
                </button>
              ))}
              <button className="n-act n-spacer" onClick={add} disabled={!form.name.trim()}>
                Добавить
              </button>
              <button className="n-act" onClick={() => setShowAdd(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        {services === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {services?.length === 0 && (
          <div className="n-empty">
            <p>Сервисов пока нет.</p>
            <p className="n-sub">Добавьте первый кнопкой выше.</p>
          </div>
        )}

        <div className="n-grid wide">
          {services?.map((s) => {
            const open = openId === s.id;
            const left = daysUntil(s.next_charge);
            const isPrepaid = s.period === 'prepaid';
            const noBalance = isPrepaid && s.balance == null;
            const tone = noBalance ? 'warn' : CATEGORY_TONE[s.category] ?? 'neutral';
            return (
              <div
                key={s.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : s.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{s.name}</h3>
                  <span className="n-badge" data-tone={tone}>
                    {money(s.cost)} {PERIODS[s.period] ?? s.period}
                  </span>
                </div>

                <div className="n-foot">
                  {isPrepaid ? (
                    <span>
                      на счету: {s.balance != null ? money(s.balance) : 'неизвестно'}
                    </span>
                  ) : (
                    <span>{whenCharged(left)}</span>
                  )}
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    {s.notes && (
                      <div>
                        <div className="n-label">Заметка</div>
                        <p className="n-full">{s.notes}</p>
                      </div>
                    )}

                    <div>
                      <div className="n-label">Деньги на счету</div>
                      <div className="n-foot" style={{ marginTop: 4 }}>
                        <span>
                          {s.balance != null ? money(s.balance) : 'не вписан'} · обновлён{' '}
                          {checkedAgo(s.balance_checked_at)}
                        </span>
                      </div>
                      <div className="n-actions" style={{ marginTop: 6 }}>
                        <input
                          value={balanceDraft[s.id] ?? ''}
                          onChange={(e) => setBalanceDraft((d) => ({ ...d, [s.id]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveBalance(s.id);
                          }}
                          placeholder="Сколько сейчас, напр. 12.50"
                          style={{
                            flex: '1 1 180px',
                            background: 'var(--panel-2)',
                            border: '1px solid var(--line)',
                            borderRadius: 6,
                            color: 'var(--ink)',
                            padding: '6px 10px',
                            fontFamily: 'var(--p-mono)',
                            fontSize: '0.82rem',
                          }}
                        />
                        <button
                          className="n-act"
                          onClick={() => saveBalance(s.id)}
                          disabled={!balanceDraft[s.id]}
                        >
                          Сохранить
                        </button>
                      </div>
                      {s.balance_provider && (
                        <p className="p-note" style={{ marginTop: 4, fontSize: '0.74rem' }}>
                          Этот сервис отдаёт баланс по API — обновляется сам.
                        </p>
                      )}
                    </div>

                    <div>
                      <div className="n-label">Списание</div>
                      <div className="n-foot" style={{ marginTop: 4 }}>
                        <span>{s.next_charge ? `${s.next_charge} · ${whenCharged(left)}` : 'дата неизвестна'}</span>
                      </div>
                    </div>

                    <div className="n-actions">
                      {s.url && (
                        <a
                          className="n-act"
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, textDecoration: 'none' }}
                        >
                          <ExternalLink className="h-3 w-3" aria-hidden />
                          сайт
                        </a>
                      )}
                      {s.cancel_url && (
                        <a
                          className="n-act"
                          href={s.cancel_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ textDecoration: 'none' }}
                        >
                          где отменить
                        </a>
                      )}
                      <button className="n-act danger n-spacer" onClick={() => cancel(s.id)}>
                        отметить отменённой
                      </button>
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
