import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { addMemoryFact, getMemoryFacts, getMemoryStats } from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, NUM, PageHeader, Skeleton, when } from '../components/ui';
import { plural } from '../lib/format';

// Память из четырёх слоёв: сырое, рабочее, канон и то, чему система верит
// в первую очередь. Слой виден полосой слева и подписан словом — по цвету
// одному его не угадать.

const LAYERS: Record<string, { label: string; hint: string; border: string; text: string }> = {
  inbox: {
    label: 'Входящее',
    hint: 'сырое: реплики, расшифровки, всё непросмотренное',
    border: 'border-l-gray-600',
    text: 'text-gray-300',
  },
  operational: {
    label: 'Рабочее',
    hint: 'то, на что система ссылается в делах',
    border: 'border-l-blue-400',
    text: 'text-blue-300',
  },
  canonical: {
    label: 'Канон',
    hint: 'методики, цены, шаблоны — редко меняется',
    border: 'border-l-secondary',
    text: 'text-secondary',
  },
  memory: {
    label: 'Память',
    hint: 'чему система доверяет в первую очередь',
    border: 'border-l-primary',
    text: 'text-primary',
  },
};

export default function MemoryScreen() {
  const [facts, setFacts] = useState<any[] | null>(null);
  const [stats, setStats] = useState<any>({});
  const [layer, setLayer] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ content: '', layer: 'memory', source: 'вручную', confidence: 0.8 });

  const load = () => {
    const params: Record<string, string> = {};
    if (layer) params.layer = layer;
    getMemoryFacts(params)
      .then((f) => {
        setFacts(f);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
    getMemoryStats().then(setStats).catch(() => {});
  };

  useEffect(load, [layer]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = facts ?? [];
    return q ? list.filter((f) => (f.content ?? '').toLowerCase().includes(q)) : list;
  }, [facts, query]);

  const add = async () => {
    if (!form.content.trim()) return;
    try {
      await addMemoryFact(form);
      setForm({ ...form, content: '' });
      setShowAdd(false);
      load();
    } catch {
      setError('Факт не записался.');
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Память"
        subtitle={
          stats.active != null
            ? `${plural(stats.active, 'факт', 'факта', 'фактов')} · средняя достоверность ${stats.avg_confidence ?? 0}`
            : 'Чему система верит и откуда это узнала.'
        }
        action={
          <button onClick={() => setShowAdd(!showAdd)} className={BTN}>
            <Plus className="h-4 w-4" aria-hidden />
            Записать факт
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
          <textarea
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            placeholder="Что система должна знать"
            rows={3}
            className={INPUT}
            autoFocus
          />
          <div className="flex flex-wrap items-center gap-2">
            {Object.entries(LAYERS).map(([key, l]) => (
              <button
                key={key}
                onClick={() => setForm({ ...form, layer: key })}
                className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                  form.layer === key
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
                }`}
                title={l.hint}
              >
                {l.label}
              </button>
            ))}
            <button onClick={add} className={`${BTN} ml-auto`} disabled={!form.content.trim()}>
              Записать
            </button>
            <button onClick={() => setShowAdd(false)} className={BTN_GHOST}>
              Отмена
            </button>
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setLayer('')}
          className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
            layer === ''
              ? 'border-primary/40 bg-primary/10 text-primary'
              : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
          }`}
        >
          Все слои
        </button>
        {Object.entries(LAYERS).map(([key, l]) => (
          <button
            key={key}
            onClick={() => setLayer(key)}
            title={l.hint}
            className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
              layer === key
                ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
            }`}
          >
            {l.label}
            {stats.by_layer?.[key] != null && (
              <span className={`ml-2 text-xs text-gray-500 ${NUM}`}>{stats.by_layer[key]}</span>
            )}
          </button>
        ))}
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по тексту"
          className={`${INPUT} ml-auto max-w-xs`}
        />
      </div>

      {facts === null && !error && <Skeleton />}

      {facts?.length === 0 && (
        <Empty
          title="Фактов пока нет."
          hint="Память наполняется сама из разговоров с ботом — или запиши первый факт вручную."
        />
      )}

      {facts && facts.length > 0 && shown.length === 0 && (
        <Empty title={`По запросу «${query}» ничего не нашлось.`} />
      )}

      <div className="space-y-2">
        {shown.map((f) => {
          const l = LAYERS[f.layer] ?? LAYERS.inbox;
          return (
            <article key={f.id} className={`${CARD} border-l-4 ${l.border}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-[11px] uppercase tracking-wider ${l.text}`}>{l.label}</span>
                <span className={`ml-auto text-[11px] text-gray-500 ${NUM}`}>
                  достоверность {f.confidence}
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm text-gray-100">{f.content}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1">
                {f.tags?.slice(0, 6).map((t: string) => (
                  <span key={t} className="rounded-full bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
                    {t}
                  </span>
                ))}
                <span className="ml-auto text-[11px] text-gray-500">
                  {f.source} · {when(f.created_at)}
                </span>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
