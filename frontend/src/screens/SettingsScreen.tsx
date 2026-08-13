import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { getSystemStatus } from '../lib/api';
import { money } from '../lib/format';
import type { SystemStatusResponse } from '../types';
import { useLang } from '../lib/i18n';

// Экран показывал три строки, вписанные в код руками: адрес, папку и версию.
// При смене порта или папки он врал бы и не заметил этого. Теперь всё
// приходит с бэкенда — что там на самом деле, то здесь и написано.

const CARD = 'rounded-lg border border-gray-800 bg-dark p-5';

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-gray-800/70 py-2 last:border-0">
      <span className="text-sm text-gray-400">{label}</span>
      <span className="font-mono text-sm tabular-nums text-gray-100">{value}</span>
      {hint && <span className="w-full text-xs text-gray-500">{hint}</span>}
    </div>
  );
}

export default function SettingsScreen() {
  const { t } = useLang();
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemStatus()
      .then(setStatus)
      .catch(() => setError(t('Бэкенд недоступен. Запущен ли он на :8420?')));
  }, []);

  if (error) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="mb-4 text-2xl font-bold text-gray-100">{t('Настройки')}</h1>
        <div className="flex items-center gap-3 rounded-lg border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-100">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-400" aria-hidden />
          {error}
        </div>
      </div>
    );
  }

  if (!status) {
    return <div className={`m-8 ${CARD} h-40 animate-pulse motion-reduce:animate-none`} />;
  }

  const { runtime, autopilot, dream } = status;

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">{t('Настройки')}</h1>
        <p className="mt-1 text-sm text-gray-400">
          {t('Что система читает при запуске. Меняется в файле .env — отсюда не редактируется намеренно: ключи не должны проходить через браузер.')}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className={CARD}>
          <h2 className="mb-3 text-lg font-bold text-gray-100">{t('Где что лежит')}</h2>
          <Row label={t('Версия')} value={runtime.version} />
          <Row label={t('Адрес API')} value={runtime.api_url} />
          <Row label={t('Папка данных')} value={runtime.data_dir} />
          <Row label={t('Папка артефактов')} value={runtime.artifacts_dir} />
          <Row
            label={t('Файл токена')}
            value={runtime.auth_file}
            hint="Тот же токен лежит во frontend/.env.local как VITE_API_TOKEN"
          />
          <p className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/90">
            Папка данных до сих пор называется <code>.nexsys</code> — по старому имени проекта.
            Переименование делается отдельно и с копией: там лежит вся память, граф и настройки
            персон, и терять это на ровном месте нельзя.
          </p>
        </section>

        <section className={CARD}>
          <h2 className="mb-3 text-lg font-bold text-gray-100">{t('Пределы и расписание')}</h2>
          <Row label={t('Дневной бюджет на модели')} value={money(runtime.daily_budget_usd)} />
          <Row label={t('Потолок ответа')} value={`${runtime.max_reply_tokens} ${t('токенов')}`} />
          <Row label="Ночной прогон" value={dream.cron} hint="Формат cron, читается из NIGHT_ANALYSIS_CRON" />
          <Row
            label={t('Расписание ведёт процесс')}
            value={runtime.scheduler_pid ? String(runtime.scheduler_pid) : t('никто')}
            hint="Ровно один процесс на всю систему — иначе напоминания приходят по разу на каждый запущенный бэкенд"
          />
          <Row
            label={t('Автопилот Jarvis')}
            value={autopilot.enabled ? t('включён') : t('выключен')}
            hint={
              autopilot.enabled
                ? `каждые ${autopilot.interval_min} мин, до ${autopilot.max_runs_per_day} раз в сутки, тихие часы ${autopilot.quiet_hours[0]}:00–${autopilot.quiet_hours[1]}:00`
                : 'работает только по твоей команде'
            }
          />
        </section>

        <section className={`${CARD} lg:col-span-2`}>
          <h2 className="mb-3 text-lg font-bold text-gray-100">{t('Что подключено')}</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {status.integrations.map((item) => (
              <div key={item.key} className="flex items-start gap-3 rounded-md bg-darker p-3">
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    item.connected ? 'bg-primary' : 'bg-gray-600'
                  }`}
                />
                <div className="min-w-0">
                  <div className="text-sm text-gray-100">
                    {item.label}{' '}
                    <span className={item.connected ? 'text-primary' : 'text-gray-400'}>
                      — {item.connected ? t('подключено') : t('нет')}
                    </span>
                  </div>
                  <div className="break-words text-xs text-gray-400">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
