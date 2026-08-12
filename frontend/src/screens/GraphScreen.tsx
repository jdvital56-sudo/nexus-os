import { useEffect, useMemo, useState } from 'react';
import MemoryGalaxy, { type GalaxyLink, type GalaxyNode } from '../components/MemoryGalaxy';
import { getGraphMap, getNote } from '../lib/api';
import { links as linksWord, nodes as nodesWord } from '../lib/format';
import type { ApiGraphNode, GraphMap } from '../types';

// Карта второго мозга на настоящих данных (PR-20). До этого экран показывал
// восемь выдуманных узлов вроде «Project Alpha» — красиво и ни о чём.
// Отрисовка живёт в MemoryGalaxy, здесь — данные, легенда и карточка узла.

const TYPE_COLORS: Record<string, string> = {
  memory: '#00DC82',
  concept: '#F5B642',
  document: '#3B82F6',
  file: '#38BDF8',
  task: '#A78BFA',
  agent: '#EC4899',
  decision: '#FB923C',
  session: '#94A3B8',
};

const TYPE_LABELS: Record<string, string> = {
  memory: 'Память',
  concept: 'Понятия',
  document: 'Документы',
  file: 'Файлы',
  task: 'Задачи',
  agent: 'Агенты',
  decision: 'Решения',
  session: 'Сессии',
};

function colorOf(type: string): string {
  return TYPE_COLORS[type] ?? '#6B7280';
}

// Порог по числу связей. Единица по умолчанию: узел с одной связью почти
// всегда шум — слово из одной заметки, которое больше нигде не встретилось.
const DEFAULT_MIN_LINKS = 2;

export default function GraphScreen() {
  const [map, setMap] = useState<GraphMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [minLinks, setMinLinks] = useState(DEFAULT_MIN_LINKS);
  const [query, setQuery] = useState('');
  const [note, setNote] = useState<{ title: string; path: string; content: string } | null>(null);
  const [noteError, setNoteError] = useState<string | null>(null);

  useEffect(() => {
    getGraphMap(500)
      .then(setMap)
      .catch(() => setError('Не удалось загрузить граф. Бэкенд запущен?'));
  }, []);

  const { galaxyNodes, galaxyLinks, byId } = useMemo(() => {
    if (!map) return { galaxyNodes: [] as GalaxyNode[], galaxyLinks: [] as GalaxyLink[], byId: new Map<string, ApiGraphNode>() };

    const degree = new Map<string, number>();
    for (const e of map.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }

    const visible = map.nodes.filter(
      (n) => !hiddenTypes.has(n.node_type) && (degree.get(n.id) ?? 0) >= minLinks,
    );
    const ids = new Set(visible.map((n) => n.id));

    return {
      galaxyNodes: visible.map((n) => ({
        id: n.id,
        label: n.label,
        type: n.node_type,
        color: colorOf(n.node_type),
        degree: degree.get(n.id) ?? 0,
      })),
      galaxyLinks: map.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => ({ source: e.source, target: e.target, weight: e.weight })),
      byId: new Map(map.nodes.map((n) => [n.id, n])),
    };
  }, [map, hiddenTypes, minLinks]);

  // Поиск по названию: выбранный узел карта сама подтянет в центр
  const found = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    return galaxyNodes
      .filter((n) => n.label.toLowerCase().includes(q))
      .sort((a, b) => b.degree - a.degree)
      .slice(0, 8);
  }, [query, galaxyNodes]);

  const selected = selectedId ? byId.get(selectedId) : null;
  const selectedDegree = galaxyNodes.find((n) => n.id === selectedId)?.degree ?? 0;

  // Двойной щелчок по узлу-заметке открывает саму заметку: без этого карта
  // остаётся картинкой, из которой нельзя провалиться в содержимое
  const openNote = async (id: string) => {
    setSelectedId(id);
    setNote(null);
    setNoteError(null);
    if (!id.startsWith('note:')) {
      setNoteError('Это не заметка — у понятий нет своего файла.');
      return;
    }
    try {
      setNote(await getNote(id.slice('note:'.length)));
    } catch (e: any) {
      setNoteError(e?.response?.data?.detail ?? 'Заметку открыть не удалось.');
    }
  };

  const toggleType = (type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (error) {
    return <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-6 text-red-100">{error}</div>;
  }

  if (!map) {
    return <div className="h-96 animate-pulse rounded-lg bg-dark motion-reduce:animate-none" />;
  }

  if (map.nodes.length === 0) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-white">Второй мозг</h1>
        <div className="mt-6 rounded-lg border border-gray-800 bg-dark p-10 text-center">
          <p className="text-gray-300">Граф пока пуст.</p>
          <p className="mt-2 text-sm text-gray-400">
            Узлы появляются сами: из диалога с Hermes, из заметок Obsidian и из ночных
            прогонов. Напиши боту пару сообщений — и карта начнёт расти.
          </p>
        </div>
      </div>
    );
  }

  const types = Object.entries(map.stats.node_types).sort((a, b) => b[1] - a[1]);

  return (
    <div className="relative -m-8 h-screen overflow-hidden bg-darker">
      <MemoryGalaxy
        nodes={galaxyNodes}
        links={galaxyLinks}
        selectedId={selectedId}
        onSelect={(id) => {
          setSelectedId(id);
          setNote(null);
          setNoteError(null);
        }}
        onOpen={openNote}
      />

      {/* Легенда — она же фильтр по типам */}
      <div className="pointer-events-auto absolute left-6 top-6 w-64 rounded-lg border border-gray-800 bg-dark/85 p-4 backdrop-blur">
        <h2 className="mb-1 text-sm font-bold tracking-wide text-white">Второй мозг</h2>
        <p className="mb-3 text-xs text-gray-400">
          показано {galaxyNodes.length} из {map.stats.nodes} · {linksWord(map.stats.edges)}
        </p>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Найти узел…"
          className="mb-2 w-full rounded-md border border-gray-800 bg-darker px-3 py-1.5 text-xs text-gray-100 placeholder-gray-500 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {found.length > 0 && (
          <ul className="mb-3 max-h-40 space-y-0.5 overflow-y-auto">
            {found.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => {
                    setSelectedId(n.id);
                    setQuery('');
                  }}
                  className="flex w-full cursor-pointer items-center gap-2 rounded px-2 py-1 text-left text-xs text-gray-200 transition-colors duration-200 hover:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: n.color }} />
                  <span className="truncate">{n.label}</span>
                  <span className="ml-auto font-mono text-gray-500">{n.degree}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <label className="mb-3 block text-xs text-gray-300">
          <span className="mb-1 flex items-center justify-between">
            Минимум связей
            <span className="font-mono tabular-nums text-gray-400">{minLinks}</span>
          </span>
          <input
            type="range"
            min={0}
            max={6}
            value={minLinks}
            onChange={(e) => setMinLinks(Number(e.target.value))}
            className="w-full cursor-pointer accent-primary"
          />
          <span className="text-[11px] text-gray-500">
            {minLinks === 0 ? 'видно всё, включая одиночек' : 'редкие узлы скрыты'}
          </span>
        </label>
        <ul className="space-y-1">
          {types.map(([type, count]) => {
            const off = hiddenTypes.has(type);
            return (
              <li key={type}>
                <button
                  onClick={() => toggleType(type)}
                  className={`flex w-full cursor-pointer items-center justify-between rounded px-2 py-1 text-xs transition-colors duration-200 hover:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-primary ${
                    off ? 'opacity-40' : ''
                  }`}
                  title={off ? 'Показать' : 'Скрыть'}
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: colorOf(type), boxShadow: `0 0 6px ${colorOf(type)}` }}
                    />
                    <span className="text-gray-200">{TYPE_LABELS[type] ?? type}</span>
                  </span>
                  <span className="font-mono tabular-nums text-gray-400">{count}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-[11px] leading-snug text-gray-500">
          Карта поворачивается сама, ближний узел разгорается. Наведи — зажжётся другой,
          нажми — останутся только он и соседи, двойной щелчок откроет саму заметку.
          Колесо приближает, узел можно тянуть, двойной щелчок по пустоте вернёт вид.
        </p>
      </div>

      {/* Карточка выбранного узла */}
      {selected && (
        <div className="absolute right-6 top-6 w-80 rounded-lg border border-gray-800 bg-dark/90 p-5 backdrop-blur">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <span
                className="mb-2 inline-block rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider"
                style={{ backgroundColor: `${colorOf(selected.node_type)}22`, color: colorOf(selected.node_type) }}
              >
                {TYPE_LABELS[selected.node_type] ?? selected.node_type}
              </span>
              <h3 className="break-words text-lg font-bold text-white">{selected.label}</h3>
            </div>
            <button
              onClick={() => setSelectedId(null)}
              className="cursor-pointer rounded px-2 text-gray-400 transition-colors duration-200 hover:text-white focus:outline-none focus:ring-1 focus:ring-primary"
              aria-label="Закрыть"
            >
              ✕
            </button>
          </div>

          <dl className="space-y-1 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-gray-400">Связей</dt>
              <dd className="font-mono tabular-nums text-gray-100">{selectedDegree}</dd>
            </div>
            {selected.created_at && (
              <div className="flex justify-between gap-3">
                <dt className="text-gray-400">Создан</dt>
                <dd className="font-mono text-xs text-gray-100">
                  {selected.created_at.slice(0, 16).replace('T', ' ')}
                </dd>
              </div>
            )}
          </dl>

          {/* Сама заметка: двойной щелчок по узлу — и текст здесь */}
          {note && (
            <div className="mt-3 border-t border-gray-800 pt-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <h4 className="text-xs text-gray-400">{note.path}</h4>
                <a
                  href={`obsidian://open?path=${encodeURIComponent(note.path)}`}
                  className="shrink-0 text-[11px] text-primary underline"
                >
                  открыть в Obsidian
                </a>
              </div>
              <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-darker p-3 text-xs leading-relaxed text-gray-200">
                {note.content.slice(0, 4000)}
              </pre>
            </div>
          )}

          {noteError && !note && (
            <p className="mt-3 border-t border-gray-800 pt-3 text-xs text-gray-400">{noteError}</p>
          )}

          {!note && !noteError && selected.id.startsWith('note:') && (
            <p className="mt-3 text-[11px] text-gray-500">
              Двойной щелчок по узлу — покажу текст заметки.
            </p>
          )}

          {Object.keys(selected.metadata ?? {}).length > 0 && (
            <div className="mt-3 border-t border-gray-800 pt-3">
              <h4 className="mb-1 text-xs text-gray-400">Что о нём известно</h4>
              <ul className="space-y-1 text-xs text-gray-300">
                {Object.entries(selected.metadata).slice(0, 6).map(([k, v]) => (
                  <li key={k} className="break-words">
                    <span className="text-gray-500">{k}: </span>
                    {String(v).slice(0, 160)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
