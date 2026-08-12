import { useEffect, useState } from 'react';
import { Check, Save, Sparkles } from 'lucide-react';
import {
  getCharacter,
  getHermesPrompt,
  getPersonas,
  setCharacter,
  setHermesPrompt,
  updatePersona,
} from '../lib/api';
import type { Character, Persona } from '../types';

// Пантеон: кто отвечает и каким тоном. Бэкенд для этого готов с PR-8 —
// правка влияет уже на следующее сообщение в любом канале, — но экрана не
// было, и настроить характер можно было только через API.
//
// Ползунки не хранятся числами «для красоты»: бэкенд разворачивает их в
// понятные модели фразы, и эту фразу видно тут же, под ползунками. Иначе
// непонятно, что вообще меняет «юмор 7».

const CARD = 'rounded-lg border border-gray-800 bg-dark p-5';

const DIALS: Array<{ key: keyof Character; label: string; left: string; right: string }> = [
  { key: 'humor', label: 'Юмор', left: 'сухо', right: 'с шутками' },
  { key: 'warmth', label: 'Тон', left: 'по-деловому', right: 'по-дружески' },
  { key: 'verbosity', label: 'Подробность', left: 'односложно', right: 'разворачивает' },
];

const ADDRESS: Array<Character['address']> = ['ты', 'вы', 'сэр'];
const LANGUAGE: Array<{ value: Character['language']; label: string }> = [
  { value: 'auto', label: 'как спросили' },
  { value: 'ru', label: 'русский' },
  { value: 'en', label: 'английский' },
];

export default function PersonasScreen() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [character, setChar] = useState<Character | null>(null);
  const [prompt, setPrompt] = useState('');
  const [promptSaved, setPromptSaved] = useState(false);
  const [openName, setOpenName] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<Persona>>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getPersonas(), getCharacter(), getHermesPrompt()])
      .then(([p, c, s]) => {
        setPersonas(p);
        setChar(c);
        setPrompt(s.system_prompt);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
  }, []);

  // Правка уходит на бэкенд сразу: ползунок без кнопки «сохранить»
  // честнее — то, что видишь, и есть то, что уйдёт в модель
  const changeDial = async (patch: Partial<Character>) => {
    if (!character) return;
    setChar({ ...character, ...patch });
    try {
      setChar(await setCharacter(patch));
    } catch {
      setError('Характер не сохранился.');
    }
  };

  const savePersona = async (persona: Persona) => {
    const draft = drafts[persona.name];
    if (!draft) return;
    try {
      const updated = await updatePersona(persona.name, draft);
      setPersonas((prev) => prev.map((p) => (p.name === persona.name ? updated : p)));
      setDrafts((prev) => ({ ...prev, [persona.name]: {} }));
      setSaved(persona.name);
      setTimeout(() => setSaved(null), 2000);
    } catch {
      setError(`Персона ${persona.name} не сохранилась.`);
    }
  };

  const savePrompt = async () => {
    try {
      const res = await setHermesPrompt(prompt);
      setPrompt(res.system_prompt);
      setPromptSaved(true);
      setTimeout(() => setPromptSaved(false), 2000);
    } catch {
      setError('Общие правила не сохранились.');
    }
  };

  if (error && !character) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="mb-4 text-2xl font-bold text-white">Пантеон</h1>
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-100">{error}</div>
      </div>
    );
  }

  if (!character) {
    return <div className={`m-8 ${CARD} h-48 animate-pulse motion-reduce:animate-none`} />;
  }

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white lg:text-3xl">Пантеон</h1>
        <p className="mt-1 text-sm text-gray-400">
          Кто отвечает и каким тоном. Любая правка здесь влияет уже на следующее сообщение —
          и в Телеграме, и везде, где система заговорит.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
          {error}
        </div>
      )}

      <section className={`${CARD} mb-6`}>
        <h2 className="mb-1 flex items-center gap-2 text-lg font-bold text-white">
          <Sparkles className="h-5 w-5 text-primary" aria-hidden />
          Характер
        </h2>
        <p className="mb-5 text-sm text-gray-400">
          Общий поверх любой персоны. Сохраняется сразу, кнопка не нужна.
        </p>

        <div className="grid gap-5 lg:grid-cols-3">
          {DIALS.map((dial) => (
            <label key={dial.key} className="block">
              <span className="mb-1 flex items-center justify-between text-sm text-gray-200">
                {dial.label}
                <span className="font-mono tabular-nums text-gray-400">
                  {character[dial.key] as number}
                </span>
              </span>
              <input
                type="range"
                min={0}
                max={10}
                value={character[dial.key] as number}
                onChange={(e) => changeDial({ [dial.key]: Number(e.target.value) } as Partial<Character>)}
                className="w-full cursor-pointer accent-primary"
              />
              <span className="flex justify-between text-[11px] text-gray-500">
                <span>{dial.left}</span>
                <span>{dial.right}</span>
              </span>
            </label>
          ))}
        </div>

        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <div>
            <span className="mb-2 block text-sm text-gray-200">Обращение</span>
            <div className="flex gap-2">
              {ADDRESS.map((value) => (
                <button
                  key={value}
                  onClick={() => changeDial({ address: value })}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                    character.address === value
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="mb-2 block text-sm text-gray-200">Язык ответа</span>
            <div className="flex flex-wrap gap-2">
              {LANGUAGE.map((item) => (
                <button
                  key={item.value}
                  onClick={() => changeDial({ language: item.value })}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary ${
                    character.language === item.value
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* То, что реально уйдёт в модель — без этого ползунки гадание */}
        {character.prompt && (
          <div className="mt-5 rounded-md bg-darker p-3">
            <h3 className="mb-1 text-xs uppercase tracking-wider text-gray-500">
              Что уйдёт в модель
            </h3>
            <p className="text-xs leading-relaxed text-gray-300">{character.prompt}</p>
          </div>
        )}
      </section>

      <section className={`${CARD} mb-6`}>
        <h2 className="mb-1 text-lg font-bold text-white">Общие правила</h2>
        <p className="mb-3 text-sm text-gray-400">
          Идут перед характером и перед персоной. Здесь живут запреты — например, не выдумывать
          факты и не делать необратимое без спроса.
        </p>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          className="w-full rounded-md border border-gray-800 bg-darker p-3 text-sm leading-relaxed text-gray-100 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          onClick={savePrompt}
          className="mt-3 flex cursor-pointer items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-darker transition-colors duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {promptSaved ? <Check className="h-4 w-4" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
          {promptSaved ? 'Сохранено' : 'Сохранить'}
        </button>
      </section>

      <h2 className="mb-3 text-lg font-bold text-white">Персоны</h2>
      <div className="space-y-3">
        {personas.map((persona) => {
          const open = openName === persona.name;
          const draft = drafts[persona.name] ?? {};
          const changed = Object.keys(draft).length > 0;
          return (
            <article key={persona.name} className={CARD}>
              <button
                onClick={() => setOpenName(open ? null : persona.name)}
                className="flex w-full cursor-pointer items-start justify-between gap-3 text-left focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <span className="min-w-0">
                  <span className="font-semibold text-white">{persona.name}</span>
                  <span className="mt-0.5 block text-sm text-gray-400">{persona.description}</span>
                </span>
                <span className="shrink-0 font-mono text-xs text-gray-500">
                  {persona.provider}/{persona.model}
                </span>
              </button>

              {open && (
                <div className="mt-4 space-y-3 border-t border-gray-800 pt-4">
                  <label className="block text-xs text-gray-400">
                    Модель
                    <input
                      value={draft.model ?? persona.model}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [persona.name]: { ...prev[persona.name], model: e.target.value },
                        }))
                      }
                      className="mt-1 w-full rounded-md border border-gray-800 bg-darker px-3 py-1.5 font-mono text-sm text-gray-100 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>

                  <label className="block text-xs text-gray-400">
                    Характер персоны (промпт)
                    <textarea
                      value={draft.system_prompt ?? persona.system_prompt}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [persona.name]: { ...prev[persona.name], system_prompt: e.target.value },
                        }))
                      }
                      rows={4}
                      className="mt-1 w-full rounded-md border border-gray-800 bg-darker p-3 text-sm leading-relaxed text-gray-100 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>

                  <button
                    onClick={() => savePersona(persona)}
                    disabled={!changed}
                    className="flex cursor-pointer items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-darker transition-colors duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-40"
                  >
                    {saved === persona.name ? (
                      <Check className="h-4 w-4" aria-hidden />
                    ) : (
                      <Save className="h-4 w-4" aria-hidden />
                    )}
                    {saved === persona.name ? 'Сохранено' : 'Сохранить'}
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
