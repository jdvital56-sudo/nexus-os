import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { getGraphMap } from '../lib/api';
import { links as linksWord, nodes as nodesWord } from '../lib/format';
import type { ApiGraphNode, GraphMap } from '../types';

// Карта второго мозга на настоящих данных (PR-20). До этого экран показывал
// восемь выдуманных узлов вроде «Project Alpha» — красиво и ни о чём.
//
// Движение здесь не украшение: симуляция никогда не останавливается, поэтому
// граф медленно дышит, как облако в невесомости. По связям бегут светлые
// точки — так видно, что это живые связи, а не картинка. Наведение
// подсвечивает соседей: у узла с сорока связями иначе не понять, куда он ведёт.

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

const DIM = 'rgba(148, 163, 184, 0.12)';

type SimNode = ApiGraphNode & { degree: number; x?: number; y?: number };
type SimLink = { source: any; target: any; weight: number; edge_type: string };

function colorOf(type: string): string {
  return TYPE_COLORS[type] ?? '#6B7280';
}

export default function GraphScreen() {
  const [map, setMap] = useState<GraphMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<SimNode | null>(null);
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const holder = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 800, height: 600 });

  useEffect(() => {
    getGraphMap(500)
      .then(setMap)
      .catch(() => setError('Не удалось загрузить граф. Бэкенд запущен?'));
  }, []);

  // Холст должен занимать всё окно и переживать его изменение
  useEffect(() => {
    if (!holder.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setBox({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(holder.current);
    return () => observer.disconnect();
  }, [map]);

  const data = useMemo(() => {
    if (!map) return { nodes: [] as SimNode[], links: [] as SimLink[] };

    const degree = new Map<string, number>();
    for (const e of map.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }

    const visible = map.nodes.filter((n) => !hiddenTypes.has(n.node_type));
    const ids = new Set(visible.map((n) => n.id));

    return {
      nodes: visible.map((n) => ({ ...n, degree: degree.get(n.id) ?? 0 })),
      links: map.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => ({ source: e.source, target: e.target, weight: e.weight, edge_type: e.edge_type })),
    };
  }, [map, hiddenTypes]);

  // Соседи подсвеченного узла — считаем один раз на наведение, а не на кадр
  const lit = useMemo(() => {
    const node = hovered ?? selected;
    if (!node) return { nodes: new Set<string>(), links: new Set<string>() };
    const nodes = new Set<string>([node.id]);
    const links = new Set<string>();
    for (const l of data.links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      if (s === node.id || t === node.id) {
        links.add(`${s}->${t}`);
        nodes.add(s);
        nodes.add(t);
      }
    }
    return { nodes, links };
  }, [hovered, selected, data.links]);

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, scale: number) => {
      // Первый кадр рисуется раньше, чем симуляция расставит координаты.
      // Без этой проверки createRadialGradient получал NaN и роняло весь
      // экран в белое — React выносил всё дерево вместе с приложением.
      if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;

      const focus = hovered ?? selected;
      const isLit = !focus || lit.nodes.has(node.id);
      const base = 2.2 + Math.min(node.degree, 24) * 0.32;
      const color = colorOf(node.node_type);

      // Свечение: чем больше связей, тем ярче ореол
      const halo = base * (isLit ? 3.4 : 2.2);
      const glow = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, halo);
      glow.addColorStop(0, color);
      glow.addColorStop(0.35, `${color}55`);
      glow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.globalAlpha = isLit ? 0.85 : 0.25;
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(node.x, node.y, halo, 0, 2 * Math.PI);
      ctx.fill();

      ctx.globalAlpha = isLit ? 1 : 0.35;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, base, 0, 2 * Math.PI);
      ctx.fill();

      // Подписи мелким шрифтом читать невозможно — показываем только
      // крупные узлы, а на отдалении не показываем вовсе
      const showLabel = scale > 1.1 && (node.degree > 2 || isLit);
      if (showLabel) {
        ctx.globalAlpha = isLit ? 0.95 : 0.4;
        ctx.font = `${Math.max(10 / scale, 2.6)}px ui-monospace, Consolas, monospace`;
        ctx.fillStyle = '#E2E8F0';
        ctx.textAlign = 'center';
        ctx.fillText(node.label.slice(0, 28), node.x, node.y + base + 5 / scale);
      }
      ctx.globalAlpha = 1;
    },
    [hovered, selected, lit],
  );

  const linkColor = useCallback(
    (link: any) => {
      const focus = hovered ?? selected;
      if (!focus) return DIM;
      const s = typeof link.source === 'object' ? link.source.id : link.source;
      const t = typeof link.target === 'object' ? link.target.id : link.target;
      return lit.links.has(`${s}->${t}`) ? 'rgba(226, 232, 240, 0.75)' : 'rgba(148, 163, 184, 0.05)';
    },
    [hovered, selected, lit],
  );

  const toggleType = (type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-6 text-red-100">{error}</div>
    );
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
      <div ref={holder} className="absolute inset-0">
        <ForceGraph2D
          graphData={data as any}
          width={box.width}
          height={box.height}
          backgroundColor="#020617"
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
            if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={linkColor}
          linkWidth={(l: any) => 0.3 + Math.min(l.weight, 4) * 0.25}
          // Те самые светлые точки, бегущие по нитям
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={(l: any) => {
            const focus = hovered ?? selected;
            const s = typeof l.source === 'object' ? l.source.id : l.source;
            const t = typeof l.target === 'object' ? l.target.id : l.target;
            return !focus || lit.links.has(`${s}->${t}`) ? 1.8 : 0.6;
          }}
          linkDirectionalParticleSpeed={(l: any) => 0.0015 + Math.min(l.weight, 5) * 0.0006}
          linkDirectionalParticleColor={() => 'rgba(255,255,255,0.9)'}
          onNodeHover={(node: any) => setHovered(node ?? null)}
          onNodeClick={(node: any) => setSelected(node ?? null)}
          onBackgroundClick={() => setSelected(null)}
          // Симуляция не остывает: облако всё время медленно движется
          d3AlphaDecay={0}
          d3VelocityDecay={0.94}
          cooldownTime={Infinity}
          warmupTicks={60}
          enableNodeDrag
        />
      </div>

      {/* Легенда — она же фильтр по типам */}
      <div className="pointer-events-auto absolute left-6 top-6 w-56 rounded-lg border border-gray-800 bg-dark/85 p-4 backdrop-blur">
        <h2 className="mb-1 text-sm font-bold tracking-wide text-white">Второй мозг</h2>
        <p className="mb-3 text-xs text-gray-400">
          {nodesWord(map.stats.nodes)} · {linksWord(map.stats.edges)}
        </p>
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
          Наведи — подсветятся связи. Нажми — подробности. Тип можно скрыть.
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
              onClick={() => setSelected(null)}
              className="cursor-pointer rounded px-2 text-gray-400 transition-colors duration-200 hover:text-white focus:outline-none focus:ring-1 focus:ring-primary"
              aria-label="Закрыть"
            >
              ✕
            </button>
          </div>

          <dl className="space-y-1 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-gray-400">Связей</dt>
              <dd className="font-mono tabular-nums text-gray-100">{selected.degree}</dd>
            </div>
            {selected.created_at && (
              <div className="flex justify-between gap-3">
                <dt className="text-gray-400">Создан</dt>
                <dd className="font-mono text-xs text-gray-100">{selected.created_at.slice(0, 16).replace('T', ' ')}</dd>
              </div>
            )}
          </dl>

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
