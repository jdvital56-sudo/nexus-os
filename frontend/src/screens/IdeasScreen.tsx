import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search } from 'lucide-react';
import {
  createContentPlan,
  createIdea,
  deleteIdea,
  getDirections,
  getIdeas,
  runResearch,
  setDirections,
  updateIdea,
} from '../lib/api';
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
  const [directions, setDirs] = useState<string[]>([]);
  const [showDirs, setShowDirs] = useState(false);
  const [dirsDraft, setDirsDraft] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const navigate = useNavigate();
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

  useEffect(() => {
    getDirections()
      .then((d) => {
        setDirs(d);
        setDirsDraft(d.join('\n'));
      })
      .catch(() => {
        /* направления — не главное на экране, молча без них */
      });
  }, []);

  /** Разведка трендов сейчас: Исследователь кладёт находки сюда же. */
  const research = async () => {
    if (directions.length === 0) {
      setShowDirs(true);
      setError('Сначала задайте направления — по чему искать.');
      return;
    }
    setBusy('research');
    try {
      const found = await runResearch();
      setError(found.length === 0 ? 'Новых тем не нашлось — всё уже в списке.' : null);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось поискать тренды.');
    } finally {
      setBusy(null);
    }
  };

  const saveDirections = async () => {
    const list = dirsDraft
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy('dirs');
    try {
      const saved = await setDirections(list);
      setDirs(saved);
      setDirsDraft(saved.join('\n'));
      setShowDirs(false);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить направления.');
    } finally {
      setBusy(null);
    }
  };

  /** Идея -> контент: тема уезжает в контент-завод, идея уходит «в план». */
  const toContent = async (idea: any) => {
    setBusy(`content:${idea.id}`);
    try {
      await createContentPlan({ topic: idea.content, count: 3 });
      await updateIdea(idea.id, { status: 'planned' });
      setError(null);
      navigate('/content');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сделать контент по идее.');
      setBusy(null);
    }
  };

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
          <div className="flex gap-2">
            <button
              onClick={research}
              disabled={busy === 'research'}
              title="Посмотреть, что сейчас обсуждают по вашим направлениям"
              className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600 disabled:opacity-60"
            >
              <Search className="h-4 w-4" aria-hidden />
              {busy === 'research' ? 'ищу…' : 'Найти тренды'}
            </button>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 hover:border-gray-600"
            >
              <Plus className="h-4 w-4" aria-hidden />
              Новая идея
            </button>
          </div>
        }
      />

      {error && (
        <div className="mb-6">
          <ErrorBox message={error} onRetry={load} />
        </div>
      )}

      <div className="pantheon-theme" data-palette={palette}>
        {/* Направления Исследователя: задаются один раз, дальше он ходит по
            ним сам — и по кнопке, и утром в 9:30, ничего не спрашивая. */}
        <div className="n-when" style={{ marginBottom: 12 }}>
          <span className="n-sub">
            {directions.length > 0
              ? `Исследователь смотрит: ${directions.join(', ')}`
              : 'Исследователь пока не знает, где искать'}
          </span>
          <button className="n-act" onClick={() => setShowDirs(!showDirs)}>
            {showDirs ? 'свернуть' : 'настроить направления'}
          </button>
        </div>

        {showDirs && (
          <div className="n-newbox">
            <div className="n-label">По каким направлениям искать — по одному в строке</div>
            <textarea
              value={dirsDraft}
              onChange={(e) => setDirsDraft(e.target.value)}
              placeholder={'спа и велнес\nаренда жилья в Дубае\nоливковое масло'}
              rows={4}
            />
            <div className="n-actions">
              <button className="n-act n-spacer" onClick={saveDirections} disabled={busy === 'dirs'}>
                {busy === 'dirs' ? 'сохраняю…' : 'Сохранить'}
              </button>
              <button className="n-act" onClick={() => setShowDirs(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}

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
                      <div className="n-label">Воплотить</div>
                      <div className="n-actions" style={{ marginTop: 6 }}>
                        <button
                          className="n-act"
                          disabled={busy === `content:${i.id}`}
                          onClick={() => toContent(i)}
                          title="Придумать по этой идее сценарии в разделе «Контент»"
                        >
                          {busy === `content:${i.id}` ? 'придумываю…' : 'сделать контент по идее'}
                        </button>
                      </div>
                    </div>

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
