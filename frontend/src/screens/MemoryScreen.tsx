import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { addMemoryFact, getMemoryFacts, getMemoryStats } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Память из четырёх слоёв: сырое, рабочее, канон и то, чему система верит
// в первую очередь.
//
// Переписано 23.08.2026 на карточки (стиль Пантеона). По дороге вскрылось
// то, что важнее вёрстки: вся память фаундера лежала одним слоем INBOX —
// то есть это куски диалогов, а не проверенные факты о его делах. Отсюда
// и жалоба «Джарвис не помнит»: система честно подмешивает в ответ то,
// что у неё есть, а есть у неё только сырьё. Поэтому слои теперь не
// просто фильтр, а видимая шкала: сколько сырья и сколько разобранного.

const LAYERS: Record<string, { label: string; hint: string; tone: string }> = {
  inbox: {
    label: 'Входящее',
    hint: 'сырое: реплики, расшифровки, всё непросмотренное',
    tone: 'neutral',
  },
  operational: {
    label: 'Рабочее',
    hint: 'то, на что система ссылается в делах',
    tone: 'progress',
  },
  canonical: {
    label: 'Канон',
    hint: 'методики, цены, шаблоны — редко меняется',
    tone: 'warn',
  },
  memory: {
    label: 'Память',
    hint: 'чему система доверяет в первую очередь',
    tone: 'good',
  },
};

function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function sourceLabel(source?: string | null): string {
  if (!source) return 'без источника';
  if (source.startsWith('agent:')) return 'прогон агента';
  if (source.startsWith('agent-sweep:')) return `обход: ${source.split(':')[1]}`;
  if (source.startsWith('web:')) return 'веб-чат';
  if (source.startsWith('telegram:')) return 'Telegram';
  if (source === 'researcher') return 'находка Исследователя';
  if (source === 'reviewer') return 'вердикт Рецензента';
  if (source === 'builder') return 'план Строителя';
  return source.slice(0, 30);
}

/** Диалоговые факты сохраняются как «Пользователь: … \n Персона: …» —
 *  в карточке показываем только суть, без служебной шапки. */
function shorten(content: string): string {
  const withoutSpeaker = content.replace(/^Пользователь:\s*/i, '');
  return withoutSpeaker.trim();
}

export default function MemoryScreen() {
  const [facts, setFacts] = useState<any[] | null>(null);
  const [stats, setStats] = useState<any>({});
  const [layer, setLayer] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form, setForm] = useState({ content: '', layer: 'memory', source: 'вручную', confidence: 0.8 });
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

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

  const add = async () => {
    if (!form.content.trim()) return;
    try {
      await addMemoryFact({ ...form, content: form.content.trim() });
      setForm({ content: '', layer: 'memory', source: 'вручную', confidence: 0.8 });
      setShowAdd(false);
      load();
    } catch {
      setError('Факт не добавился.');
    }
  };

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = facts ?? [];
    if (!q) return list;
    return list.filter((f) => f.content?.toLowerCase().includes(q));
  }, [facts, query]);

  const byLayer = stats.by_layer ?? {};
  const rawOnly = (byLayer.inbox ?? 0) > 0 && Object.keys(byLayer).length === 1;

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Память"
        subtitle="Чему система доверяет, когда отвечает. Разложена по слоям: от сырых реплик до проверенного канона."
        action={
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Добавить факт
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        <div className="p-stats">
          <div className="p-stat">
            <div className="p-k">Всего фактов</div>
            <div className="p-v">{stats.total ?? '—'}</div>
          </div>
          {Object.entries(LAYERS).map(([key, l]) => (
            <div className="p-stat" key={key}>
              <div className="p-k">{l.label}</div>
              <div className="p-v">{byLayer[key] ?? 0}</div>
            </div>
          ))}
        </div>

        {rawOnly && (
          <p className="p-note" style={{ marginBottom: 14 }}>
            Вся память сейчас — сырое «входящее»: куски разговоров, ничего разобранного. Именно поэтому
            система отвечает общими словами, когда спрашиваешь о твоих делах: проверенных фактов у неё
            просто нет. Разобрать может Куратор на экране «Агенты», либо впишите ключевые факты руками
            кнопкой выше — они лягут в слой «Память», которому система доверяет в первую очередь.
          </p>
        )}

        {showAdd && (
          <div className="n-newbox">
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              placeholder="Факт: коротко и по делу. Например: «Спа-оффер стоит $1200, скидок не даём»"
              rows={3}
              autoFocus
            />
            <div className="n-actions">
              {Object.entries(LAYERS).map(([key, l]) => (
                <button
                  key={key}
                  className={`n-act ${form.layer === key ? 'active' : ''}`}
                  onClick={() => setForm({ ...form, layer: key })}
                  title={l.hint}
                >
                  {l.label}
                </button>
              ))}
              <button className="n-act n-spacer" onClick={add} disabled={!form.content.trim()}>
                Запомнить
              </button>
              <button className="n-act" onClick={() => setShowAdd(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        <div className="n-filters">
          <button className={layer === '' ? 'active' : ''} onClick={() => setLayer('')}>
            все слои · {stats.total ?? 0}
          </button>
          {Object.entries(LAYERS).map(([key, l]) => (
            <button key={key} className={layer === key ? 'active' : ''} onClick={() => setLayer(key)}>
              {l.label} · {byLayer[key] ?? 0}
            </button>
          ))}
        </div>

        {(facts?.length ?? 0) > 0 && (
          <div className="n-newbox" style={{ padding: 10 }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск по фактам"
            />
          </div>
        )}

        {facts === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {facts?.length === 0 && (
          <div className="n-empty">
            <p>В этом слое пусто.</p>
            <p className="n-sub">Память наполняется сама из разговоров — или впишите факт кнопкой выше.</p>
          </div>
        )}

        {shown.length === 0 && (facts?.length ?? 0) > 0 && (
          <div className="n-empty">
            <p>Ничего не нашлось.</p>
          </div>
        )}

        <div className="n-grid wide">
          {shown.map((f) => {
            const l = LAYERS[f.layer] ?? LAYERS.inbox;
            const open = openId === f.id;
            const confidence = Math.round((f.confidence ?? 0) * 100);
            return (
              <div
                key={f.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={l.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : f.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : f.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{shorten(f.content)}</h3>
                  <span className="n-badge" data-tone={l.tone}>
                    {l.label}
                  </span>
                </div>

                <div className="n-foot">
                  <span>{sourceLabel(f.source)}</span>
                  <span>·</span>
                  <span>уверенность {confidence}%</span>
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Полностью</div>
                      <p
                        className="n-full"
                        style={{ maxHeight: 380, overflow: 'auto', fontSize: '0.84rem' }}
                      >
                        {f.content}
                      </p>
                    </div>
                    <div className="n-foot">
                      <span>{l.hint}</span>
                    </div>
                    <div className="n-foot">
                      <span>записано: {when(f.created_at)}</span>
                      {f.updated_at !== f.created_at && <span>· правлено: {when(f.updated_at)}</span>}
                      {f.ttl_hours && <span>· живёт {f.ttl_hours} ч</span>}
                    </div>
                    {(f.tags ?? []).length > 0 && (
                      <div className="n-foot">
                        {f.tags.map((t: string) => (
                          <span key={t} className="n-badge">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
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
