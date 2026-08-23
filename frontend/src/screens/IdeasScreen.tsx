import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { createIdea, deleteIdea, getIdeas, updateIdea } from '../lib/api';
import { ErrorBox, PageHeader } from '../components/ui';
import '../styles/pantheon.css';

// Идея — не задача. Задача делается сейчас, идея откладывается на будущую
// разработку: фаундер сказал «запиши это на будущее» (голосом/чатом, см.
// conversation.py._try_idea) — или система предложила сама (source: system).
//
// Карточки, а не список строк — прямая просьба фаундера 23.08.2026: список
// ему нечитаем, нужно «навёл — подсветилось, нажал — раскрылась суть».
// Стиль взят из уже одобренного им Пантеона (.pantheon-theme + .n-card в
// styles/pantheon.css), не выдуман заново — и палитру он там же выбирает.

const STATUS: Record<string, { label: string; tone: string }> = {
  new: { label: 'новая', tone: 'neutral' },
  considered: { label: 'рассмотрена', tone: 'progress' },
  planned: { label: 'в план', tone: 'good' },
  dismissed: { label: 'отклонена', tone: 'off' },
};

const SOURCE_LABEL: Record<string, string> = {
  founder: 'от вас',
  system: 'предложил Джарвис',
};

const FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'все' },
  { value: 'new', label: 'новые' },
  { value: 'considered', label: 'рассмотренные' },
  { value: 'planned', label: 'в плане' },
  { value: 'dismissed', label: 'отклонённые' },
];

function when(iso?: string | null): string {
  if (!iso) return '';
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function IdeasScreen() {
  const [ideas, setIdeas] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [content, setContent] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  // Палитра общая с Пантеоном: фаундер выбирает её там, здесь только читаем —
  // две независимые темы на соседних экранах выглядели бы поломкой.
  const palette = localStorage.getItem('pantheon-palette') || 'gold';

  const load = () => {
    getIdeas()
      .then((i) => {
        setIdeas(i);
        setError(null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  };

  useEffect(load, []);

  const create = async () => {
    if (!content.trim()) return;
    try {
      await createIdea({ content: content.trim() });
      setContent('');
      setShowCreate(false);
      load();
    } catch {
      setError('Идея не записалась.');
    }
  };

  const setStatus = async (id: string, status: string) => {
    try {
      await updateIdea(id, { status });
      load();
    } catch {
      setError('Не удалось обновить идею.');
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteIdea(id);
      if (openId === id) setOpenId(null);
      load();
    } catch {
      setError('Не удалось удалить идею.');
    }
  };

  const visible = (ideas ?? []).filter((i) => !filter || i.status === filter);
  const counts = FILTERS.map((f) => ({
    ...f,
    n: f.value ? (ideas ?? []).filter((i) => i.status === f.value).length : (ideas ?? []).length,
  }));

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Идеи"
        subtitle="То, что откладывается на будущую разработку — не делается прямо сейчас. Скажите «запиши идею X» или «запиши это на будущее»."
        action={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Новая идея
          </button>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {showCreate && (
          <div className="n-newbox">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="О чём идея"
              rows={3}
              autoFocus
            />
            <div className="n-actions">
              <button className="n-act n-spacer" onClick={create} disabled={!content.trim()}>
                Записать
              </button>
              <button className="n-act" onClick={() => setShowCreate(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

        {ideas !== null && ideas.length > 0 && (
          <div className="n-filters">
            {counts.map((f) => (
              <button
                key={f.value || 'all'}
                className={filter === f.value ? 'active' : ''}
                onClick={() => setFilter(f.value)}
              >
                {f.label} · {f.n}
              </button>
            ))}
          </div>
        )}

        {ideas === null && !error && (
          <div className="n-empty">
            <p>Загружаю…</p>
          </div>
        )}

        {ideas?.length === 0 && (
          <div className="n-empty">
            <p>Идей пока нет.</p>
            <p className="n-sub">
              Заведите первую кнопкой выше — или просто скажите Джарвису «запиши это на будущее».
            </p>
          </div>
        )}

        {visible.length === 0 && (ideas?.length ?? 0) > 0 && (
          <div className="n-empty">
            <p>В этой категории пусто.</p>
          </div>
        )}

        <div className="n-grid">
          {visible.map((i) => {
            const status = STATUS[i.status] ?? STATUS.new;
            const open = openId === i.id;
            return (
              <div
                key={i.id}
                className={`n-card ${open ? 'open' : ''}`}
                data-tone={status.tone}
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(open ? null : i.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOpenId(open ? null : i.id);
                  }
                }}
              >
                <div className="n-top">
                  <h3 className="n-title">{i.content}</h3>
                  <span className="n-badge" data-tone={status.tone}>
                    {status.label}
                  </span>
                </div>

                <div className="n-foot">
                  <span>{when(i.created_at)}</span>
                  <span>·</span>
                  <span>{SOURCE_LABEL[i.source] ?? i.source}</span>
                  <span className="n-hint">{open ? 'свернуть' : 'раскрыть'}</span>
                </div>

                {open && (
                  <div className="n-body" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <div className="n-label">Суть идеи</div>
                      <p className="n-full">{i.content}</p>
                    </div>
                    {i.context && (
                      <div>
                        <div className="n-label">Контекст</div>
                        <p className="n-full">{i.context}</p>
                      </div>
                    )}
                    <div>
                      <div className="n-label">Что с ней делать</div>
                      <div className="n-actions" style={{ marginTop: 6 }}>
                        {Object.keys(STATUS).map((s) => (
                          <button
                            key={s}
                            className={`n-act ${i.status === s ? 'active' : ''}`}
                            onClick={() => setStatus(i.id, s)}
                          >
                            {STATUS[s].label}
                          </button>
                        ))}
                        <button className="n-act danger n-spacer" onClick={() => remove(i.id)}>
                          удалить
                        </button>
                      </div>
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
