import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { createIdea, deleteIdea, getIdeas, updateIdea } from '../lib/api';
import { BTN, BTN_GHOST, CARD, Empty, ErrorBox, INPUT, PageHeader, Pill, Skeleton, when } from '../components/ui';

// Идея — не задача. Задача делается сейчас, идея откладывается на будущую
// разработку: фаундер сказал «запиши это на будущее» (голосом/чатом, см.
// conversation.py._try_idea) — или система предложила сама (source: system).

const STATUS: Record<string, { label: string; tone: string; border: string }> = {
  new: { label: 'новая', tone: 'gray', border: 'border-l-gray-600' },
  considered: { label: 'рассмотрена', tone: 'blue', border: 'border-l-blue-400' },
  planned: { label: 'в план', tone: 'green', border: 'border-l-primary' },
  dismissed: { label: 'отклонена', tone: 'red', border: 'border-l-red-500' },
};

const SOURCE_LABEL: Record<string, string> = {
  founder: 'от вас',
  system: 'предложено системой',
};

export default function IdeasScreen() {
  const [ideas, setIdeas] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [content, setContent] = useState('');

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
      load();
    } catch {
      setError('Не удалось удалить идею.');
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <PageHeader
        title="Идеи"
        subtitle="То, что откладывается на будущую разработку — не делается прямо сейчас. Скажите «запиши идею X» или «запиши это на будущее»."
        action={
          <button onClick={() => setShowCreate(!showCreate)} className={BTN}>
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

      {showCreate && (
        <div className={`${CARD} mb-6 space-y-3`}>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="О чём идея"
            rows={3}
            className={INPUT}
            autoFocus
          />
          <div className="flex items-center gap-2">
            <button onClick={create} className={`${BTN} ml-auto`} disabled={!content.trim()}>
              Записать
            </button>
            <button onClick={() => setShowCreate(false)} className={BTN_GHOST}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {ideas === null && !error && <Skeleton />}

      {ideas?.length === 0 && (
        <Empty
          title="Идей пока нет."
          hint="Заведите первую кнопкой выше — или скажите в разговоре «запиши это на будущее»."
        />
      )}

      <div className="space-y-2">
        {ideas?.map((i) => {
          const status = STATUS[i.status] ?? STATUS.new;
          return (
            <article key={i.id} className={`${CARD} border-l-4 ${status.border}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-gray-100">{i.content}</p>
                <Pill text={status.label} tone={status.tone} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <p className="text-[11px] text-gray-500">
                  {when(i.created_at)} · {SOURCE_LABEL[i.source] ?? i.source}
                </p>
                <div className="ml-auto flex items-center gap-2">
                  {Object.keys(STATUS)
                    .filter((s) => s !== i.status)
                    .map((s) => (
                      <button
                        key={s}
                        onClick={() => setStatus(i.id, s)}
                        className="cursor-pointer text-[11px] text-gray-400 underline decoration-dotted hover:text-gray-200"
                      >
                        {STATUS[s].label}
                      </button>
                    ))}
                  <button
                    onClick={() => remove(i.id)}
                    className="cursor-pointer text-[11px] text-gray-500 hover:text-red-400"
                  >
                    удалить
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
