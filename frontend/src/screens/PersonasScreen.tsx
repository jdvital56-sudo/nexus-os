import { useEffect, useState } from 'react';
import { Check, Save, Sparkles } from 'lucide-react';
import {
  getCharacter,
  getHermesPrompt,
  getPersonas,
  getSystemStatus,
  setCharacter,
  setHermesPrompt,
  updatePersona,
} from '../lib/api';
import type { Character, Persona, SystemStatusResponse } from '../types';
import { titleOf } from '../lib/pantheon';
import '../styles/pantheon.css';

// Пантеон: кто отвечает и каким тоном. Визуал — из одобренного макета
// (artifact 0de5f180, «Пантеон (финал)», см. nexus-os-canonical-design),
// перенесён построчно 14.08.2026, не сочинён заново. Бейджи и статистика —
// настоящие данные с /api/system/status, а не то, что было в самом
// макете (там они выдуманы для показа макета фаундеру).
//
// Ползунки не хранятся числами «для красоты»: бэкенд разворачивает их в
// понятные модели фразы, и эту фразу видно тут же, под ползунками.

const DIALS: Array<{ key: keyof Character; label: string; left: string; right: string }> = [
  { key: 'humor', label: 'Юмор', left: 'сухо', right: 'с шутками' },
  { key: 'warmth', label: 'Тон', left: 'по-деловому', right: 'по-дружески' },
  { key: 'verbosity', label: 'Подробность', left: 'односложно', right: 'разворачивает' },
  { key: 'pace', label: 'Темп речи', left: 'медленнее', right: 'живее' },
];

const ADDRESS: Array<Character['address']> = ['ты', 'вы', 'сэр'];
const LANGUAGE: Array<{ value: Character['language']; label: string }> = [
  { value: 'auto', label: 'как спросили' },
  { value: 'ru', label: 'русский' },
  { value: 'en', label: 'английский' },
];

const PALETTES: Array<{ value: string; label: string }> = [
  { value: 'gold', label: 'Золото' },
  { value: 'calm', label: 'Спокойная' },
  { value: 'lapis', label: 'Лазурит' },
  { value: 'light', label: 'Светлая' },
  { value: 'turquoise', label: 'Бирюза' },
  { value: 'carnelian', label: 'Сердолик' },
  { value: 'ivory', label: 'Слоновая кость' },
];

// Технические имена → файл портрета в /public/pantheon. Персоны, заведённые
// вручную через API и не входящие в исходную семёрку, портрета не имеют —
// вместо картинки покажем инициал.
const PORTRAITS: Record<string, string> = {
  orpheus: '/pantheon/orpheus.jpg',
  architect: '/pantheon/architect.jpg',
  mercury: '/pantheon/mercury.jpg',
  philosopher: '/pantheon/philosopher.jpg',
  labyrinth: '/pantheon/labyrinth.jpg',
  sekhmet: '/pantheon/sekhmet.jpg',
  bastet: '/pantheon/bastet.jpg',
};

export default function PersonasScreen() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [character, setChar] = useState<Character | null>(null);
  const [prompt, setPrompt] = useState('');
  const [promptSaved, setPromptSaved] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<Persona>>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [palette, setPalette] = useState<string>(() => localStorage.getItem('pantheon-palette') || 'gold');

  useEffect(() => {
    Promise.all([getPersonas(), getCharacter(), getHermesPrompt()])
      .then(([p, c, s]) => {
        setPersonas(p);
        setChar(c);
        setPrompt(s.system_prompt);
        setSelected((prev) => prev ?? p[0]?.name ?? null);
      })
      .catch(() => setError('Бэкенд недоступен. Запущен ли он на :8420?'));
    getSystemStatus().then(setStatus).catch(() => {});
  }, []);

  const choosePalette = (value: string) => {
    setPalette(value);
    localStorage.setItem('pantheon-palette', value);
  };

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
        <h1 className="mb-4 text-2xl font-bold text-gray-100">Пантеон</h1>
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-100">{error}</div>
      </div>
    );
  }

  if (!character) {
    return <div className="m-8 h-48 animate-pulse rounded-lg border border-gray-800 bg-dark motion-reduce:animate-none" />;
  }

  const activePersona = personas.find((p) => p.name === selected) ?? null;
  const draft = selected ? drafts[selected] ?? {} : {};
  const changed = Object.keys(draft).length > 0;
  const telegramOn = status?.integrations.find((i) => i.key === 'telegram')?.connected ?? false;
  const defaultModel = status?.integrations.find((i) => i.key === 'llm')?.detail ?? '—';
  const spentToday = status?.spend ? `$${status.spend.spent_usd}` : '—';

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 lg:text-3xl">Пантеон</h1>
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

      <div className="pantheon-theme" data-palette={palette === 'gold' ? undefined : palette}>
        <div className="p-palette-toggle">
          {PALETTES.map((p) => (
            <button
              key={p.value}
              className={palette === p.value ? 'active' : ''}
              onClick={() => choosePalette(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="p-banner">
          <img src="/pantheon/jarvis-banner.jpg" alt="" />
          <div className="p-fade" />
          <div className={`p-live ${telegramOn ? 'on' : 'off'}`}>
            <span className="p-dot" />
            {telegramOn ? 'На связи' : 'Бот не отвечает'}
          </div>
          <div className="p-word">ДЖАРВИС</div>
        </div>

        <div className="p-badges">
          {(status?.integrations ?? []).map((i) => (
            <span key={i.key} className={`p-badge ${i.connected ? 'on' : 'off'}`} title={i.detail}>
              <span className="p-ic" />
              {i.label}
            </span>
          ))}
        </div>

        <div className="p-stats">
          <div className="p-stat"><div className="p-k">Персон</div><div className="p-v">{personas.length}</div></div>
          <div className="p-stat"><div className="p-k">Модель по умолчанию</div><div className="p-v">{defaultModel}</div></div>
          <div className="p-stat"><div className="p-k">Потрачено сегодня</div><div className="p-v">{spentToday}</div></div>
        </div>

        <div className="p-panel">
          <h2><Sparkles className="h-4 w-4" aria-hidden />Характер</h2>
          <p className="p-sub">Общий поверх любой персоны. Сохраняется сразу, кнопка не нужна.</p>

          <div className="p-dials">
            {DIALS.map((dial) => (
              <div key={dial.key} className="p-dial">
                <label>
                  {dial.label}
                  <span className="p-num">{character[dial.key] as number}</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={10}
                  value={character[dial.key] as number}
                  onChange={(e) => changeDial({ [dial.key]: Number(e.target.value) } as Partial<Character>)}
                />
                <div className="p-ends">
                  <span>{dial.left}</span>
                  <span>{dial.right}</span>
                </div>
                {dial.key === 'pace' && <span className="p-hint">Только озвучка — на текст ответа не влияет</span>}
              </div>
            ))}
          </div>

          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <div>
              <span className="mb-2 block text-sm" style={{ color: 'var(--ink)' }}>Обращение</span>
              <div className="p-choice-row">
                {ADDRESS.map((value) => (
                  <button
                    key={value}
                    className={`p-choice ${character.address === value ? 'active' : ''}`}
                    onClick={() => changeDial({ address: value })}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className="mb-2 block text-sm" style={{ color: 'var(--ink)' }}>Язык ответа</span>
              <div className="p-choice-row">
                {LANGUAGE.map((item) => (
                  <button
                    key={item.value}
                    className={`p-choice ${character.language === item.value ? 'active' : ''}`}
                    onClick={() => changeDial({ language: item.value })}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {character.prompt && <p className="p-note"><b style={{ color: 'var(--ink)' }}>Что уйдёт в модель:</b> {character.prompt}</p>}
        </div>

        <div className="p-panel">
          <h2>Общие правила</h2>
          <p className="p-sub">
            Идут перед характером и перед персоной. Здесь живут запреты — например, не выдумывать
            факты и не делать необратимое без спроса.
          </p>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5}
            style={{ width: '100%', background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 6, color: 'var(--ink)', padding: '10px 12px', fontSize: '0.86rem', lineHeight: 1.6 }} />
          <button className="p-promptbox p-save" style={{ marginTop: 10 }} onClick={savePrompt}>
            {promptSaved ? <Check className="h-4 w-4" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
            {promptSaved ? 'Сохранено' : 'Сохранить'}
          </button>
        </div>

        <div className="p-head">
          <h2>Пантеон</h2>
          <span>{personas.length} персон · нажми карточку — снизу откроется её промпт</span>
        </div>

        <div className="p-gallery">
          {personas.map((persona) => {
            const key = persona.name.toLowerCase();
            const portrait = PORTRAITS[key];
            return (
              <button
                key={persona.name}
                className={`p-card ${selected === persona.name ? 'selected' : ''}`}
                onClick={() => setSelected(persona.name)}
              >
                <div className="p-art">
                  <span className="p-chip">{persona.provider}</span>
                  {portrait ? (
                    <img src={portrait} alt={titleOf(persona.name)} />
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontFamily: 'var(--display)', fontSize: '2rem', color: 'var(--ink-dimmer)' }}>
                      {titleOf(persona.name)[0]}
                    </div>
                  )}
                </div>
                <div className="p-meta">
                  <h3>{titleOf(persona.name)}</h3>
                  <div className="p-tech">{persona.name}</div>
                  <p>{persona.description}</p>
                </div>
              </button>
            );
          })}
        </div>

        {activePersona && (
          <div className="p-promptbox">
            <div className="p-phead">
              <b>{titleOf(activePersona.name)}</b>
              <span>что реально уйдёт модели</span>
            </div>
            <div className="p-body">
              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--ink-dimmer)', marginBottom: 4 }}>
                Модель
                <input
                  value={draft.model ?? activePersona.model}
                  onChange={(e) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [activePersona.name]: { ...prev[activePersona.name], model: e.target.value },
                    }))
                  }
                  style={{ marginTop: 4, marginBottom: 10 }}
                />
              </label>
              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--ink-dimmer)' }}>
                Промпт персоны
                <textarea
                  value={draft.system_prompt ?? activePersona.system_prompt}
                  onChange={(e) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [activePersona.name]: { ...prev[activePersona.name], system_prompt: e.target.value },
                    }))
                  }
                  rows={5}
                  style={{ marginTop: 4 }}
                />
              </label>
              <button className="p-save" disabled={!changed} onClick={() => savePersona(activePersona)}>
                {saved === activePersona.name ? <Check className="h-4 w-4" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
                {saved === activePersona.name ? 'Сохранено' : 'Сохранить'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
