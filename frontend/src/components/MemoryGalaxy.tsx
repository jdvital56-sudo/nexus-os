import { useEffect, useMemo, useRef, useState } from 'react';

// Карта второго мозга в объёме.
//
// Плоский граф (react-force-graph) выглядел схемой: все узлы в одной
// плоскости, светились либо все, либо ничего. Здесь у каждого узла есть
// глубина, облако медленно поворачивается вокруг вертикальной оси, и
// ближние к зрителю узлы разгораются сами — по мере вращения очередь
// доходит до каждого. Наведение подсвечивает узел и его связи поверх этого.
//
// Своя отрисовка, без библиотек: раскладка считается один раз при загрузке,
// дальше каждый кадр — только поворот и проекция. Поэтому пятьсот узлов
// крутятся, не грея процессор.

export interface GalaxyNode {
  id: string;
  label: string;
  type: string;
  color: string;
  degree: number;
}

export interface GalaxyLink {
  source: string;
  target: string;
  weight: number;
}

interface Props {
  nodes: GalaxyNode[];
  links: GalaxyLink[];
  onSelect?: (id: string | null) => void;
  selectedId?: string | null;
}

interface Placed extends GalaxyNode {
  x: number;
  y: number;
  z: number;
  // Экранные координаты последнего кадра — по ним ищем узел под курсором
  sx: number;
  sy: number;
  sr: number;
  depth: number;
}

// Полный оборот. Медленнее — засыпает, быстрее — начинает раздражать.
const TURN_SECONDS = 75;

// Фокусное расстояние: чем меньше, тем сильнее перспектива
const FOCAL = 900;

// Радиус подсветки от курсора в экранных пикселях
const POINTER_RADIUS = 150;

// Пределы приближения: дальше нечего разглядывать, ближе — теряешь карту
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 6;

// Солнечный свет подсветки — тёплый, в отличие от холодной паутины
const SOLAR = '255, 196, 92';

/** Раскладка силами в трёх измерениях. Считается один раз, не каждый кадр. */
function layout(nodes: GalaxyNode[], links: GalaxyLink[]): Placed[] {
  const index = new Map(nodes.map((n, i) => [n.id, i]));
  // Стартуем с равномерной сферы: случайный старт даёт комки и долгую усадку
  const placed: Placed[] = nodes.map((n, i) => {
    const golden = Math.PI * (3 - Math.sqrt(5));
    const y = 1 - (i / Math.max(nodes.length - 1, 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    const scale = 200 + (i % 7) * 18;
    return {
      ...n,
      x: Math.cos(theta) * radius * scale,
      y: y * scale * 0.75,
      z: Math.sin(theta) * radius * scale,
      sx: 0,
      sy: 0,
      sr: 0,
      depth: 0,
    };
  });

  const edges = links
    .map((l) => ({ a: index.get(l.source), b: index.get(l.target), w: l.weight }))
    .filter((e): e is { a: number; b: number; w: number } => e.a !== undefined && e.b !== undefined);

  const vx = new Float64Array(placed.length);
  const vy = new Float64Array(placed.length);
  const vz = new Float64Array(placed.length);

  const ticks = placed.length > 200 ? 60 : 140;
  for (let step = 0; step < ticks; step++) {
    // Отталкивание. Пар много, поэтому на больших графах считаем реже
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        const dx = placed[j].x - placed[i].x;
        const dy = placed[j].y - placed[i].y;
        const dz = placed[j].z - placed[i].z;
        const d2 = dx * dx + dy * dy + dz * dz || 1;
        if (d2 > 160000) continue;
        const f = 26000 / d2;
        const d = Math.sqrt(d2);
        vx[i] -= (dx / d) * f;
        vy[i] -= (dy / d) * f;
        vz[i] -= (dz / d) * f;
        vx[j] += (dx / d) * f;
        vy[j] += (dy / d) * f;
        vz[j] += (dz / d) * f;
      }
    }
    // Связи стягивают
    for (const e of edges) {
      const a = placed[e.a];
      const b = placed[e.b];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = b.z - a.z;
      const d = Math.hypot(dx, dy, dz) || 1;
      const f = (d - 150) * 0.008 * Math.min(e.w, 3);
      vx[e.a] += (dx / d) * f;
      vy[e.a] += (dy / d) * f;
      vz[e.a] += (dz / d) * f;
      vx[e.b] -= (dx / d) * f;
      vy[e.b] -= (dy / d) * f;
      vz[e.b] -= (dz / d) * f;
    }
    for (let i = 0; i < placed.length; i++) {
      // Слабое притяжение к центру, чтобы облако не расползалось
      vx[i] -= placed[i].x * 0.004;
      vy[i] -= placed[i].y * 0.006;
      vz[i] -= placed[i].z * 0.004;
      vx[i] *= 0.82;
      vy[i] *= 0.82;
      vz[i] *= 0.82;
      placed[i].x += vx[i];
      placed[i].y += vy[i];
      placed[i].z += vz[i];
    }
  }
  return placed;
}

export default function MemoryGalaxy({ nodes, links, onSelect, selectedId }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const hoverId = useRef<string | null>(null);
  // Камера: приближение и сдвиг. В ref — их меняет колесо и перетаскивание
  // много раз в секунду, состояние React тут только мешало бы
  const camera = useRef({ zoom: 1, panX: 0, panY: 0 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number; moved: number } | null>(null);
  const [hoverLabel, setHoverLabel] = useState<{ node: GalaxyNode; x: number; y: number } | null>(null);

  const placed = useMemo(() => layout(nodes, links), [nodes, links]);

  const neighbours = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const l of links) {
      if (!map.has(l.source)) map.set(l.source, new Set());
      if (!map.has(l.target)) map.set(l.target, new Set());
      map.get(l.source)!.add(l.target);
      map.get(l.target)!.add(l.source);
    }
    return map;
  }, [links]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const byId = new Map(placed.map((p) => [p.id, p]));
    const slow = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    let width = 0;
    let height = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    // Колесо приближает к точке под курсором, а не к центру экрана —
    // иначе то, что разглядываешь, уезжает из виду
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const cam = camera.current;
      const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, cam.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const ratio = next / cam.zoom;
      cam.panX = mx - centerX - (mx - centerX - cam.panX) * ratio;
      cam.panY = my - centerY - (my - centerY - cam.panY) * ratio;
      cam.zoom = next;
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });

    const started = performance.now();

    const render = (now: number) => {
      frame = requestAnimationFrame(render);
      const t = (now - started) / 1000;
      const angle = slow ? 0 : (t / TURN_SECONDS) * Math.PI * 2;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const cx = width / 2;
      const cy = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Поворот вокруг вертикальной оси, перспектива и камера
      const { zoom, panX, panY } = camera.current;
      for (const p of placed) {
        const rx = p.x * cos - p.z * sin;
        const rz = p.x * sin + p.z * cos;
        const k = FOCAL / (FOCAL + rz);
        p.sx = cx + rx * k * zoom + panX;
        p.sy = cy + p.y * k * zoom + panY;
        p.sr = (1.6 + Math.min(p.degree, 20) * 0.34) * k * zoom;
        // 1 — у самого зрителя, 0 — на дальнем краю
        p.depth = Math.max(0, Math.min(1, (FOCAL * 0.5 - rz) / (FOCAL * 0.9)));
      }

      // Дальние первыми: ближние должны лечь поверх
      const order = [...placed].sort((a, b) => a.depth - b.depth);
      const ptr = pointer.current;
      const focus = hoverId.current ?? selectedId ?? null;
      const focusSet = focus ? new Set([focus, ...(neighbours.get(focus) ?? [])]) : null;

      const heatOf = (p: Placed): number => {
        if (focusSet) return focusSet.has(p.id) ? 1 : 0.05;
        // Само собой разгорается то, что ближе всего к зрителю. Пока
        // облако поворачивается, очередь доходит до каждого узла.
        let heat = Math.pow(p.depth, 6);
        if (ptr) {
          const near = Math.max(0, 1 - Math.hypot(p.sx - ptr.x, p.sy - ptr.y) / POINTER_RADIUS);
          heat = Math.max(heat, near * near);
        }
        return heat;
      };

      // Нити
      ctx.lineCap = 'round';
      links.forEach((l, li) => {
        const a = byId.get(l.source);
        const b = byId.get(l.target);
        if (!a || !b) return;
        const lit = focusSet ? focusSet.has(a.id) && focusSet.has(b.id) : false;
        const heat = focusSet ? (lit ? 0.85 : 0.03) : 0.06 + 0.45 * Math.pow((a.depth + b.depth) / 2, 5);

        // Подсвеченная нить горит тёплым солнечным светом, спокойная —
        // холодная паутина. Так видно, что именно ты сейчас трогаешь
        ctx.strokeStyle = lit
          ? `rgba(${SOLAR}, ${heat.toFixed(3)})`
          : `rgba(190, 228, 224, ${heat.toFixed(3)})`;
        ctx.lineWidth = Math.max(0.4, ((a.depth + b.depth) / 2) * 1.1 * Math.min(zoom, 2));
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();

        // Точки идут по нити всегда — они и показывают, что связь живая.
        // Раньше их гасил порог, и на спокойной карте не двигалось ничего.
        const speed = 0.03 + Math.min(l.weight, 4) * 0.012;
        const bright = focusSet ? (lit ? 1 : 0.06) : 0.3 + 0.7 * Math.pow((a.depth + b.depth) / 2, 3);
        for (let i = 0; i < 2; i++) {
          const prog = (t * speed + i * 0.5 + (li % 7) / 7) % 1;
          ctx.globalAlpha = Math.min(0.95, 0.2 + bright * 0.75);
          ctx.fillStyle = lit ? `rgb(${SOLAR})` : '#ffffff';
          ctx.beginPath();
          ctx.arc(
            a.sx + (b.sx - a.sx) * prog,
            a.sy + (b.sy - a.sy) * prog,
            (bright > 0.5 ? 1.5 : 0.9) * Math.min(zoom, 2),
            0,
            7,
          );
          ctx.fill();
          ctx.globalAlpha = 1;
        }
      });

      // Узлы: дальние рисуются раньше, ближние ложатся поверх
      for (const p of order) {
        const heat = heatOf(p);

        if (heat > 0.03) {
          ctx.globalCompositeOperation = 'lighter';
          const halo = p.sr * (1.6 + 6 * heat);
          const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, halo);
          g.addColorStop(0, p.color);
          g.addColorStop(0.16, `${p.color}bb`);
          g.addColorStop(0.42, `${p.color}33`);
          g.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.globalAlpha = 0.12 + 0.85 * heat;
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, halo, 0, 7);
          ctx.fill();
          ctx.globalCompositeOperation = 'source-over';
        }

        // Дальние узлы бледнее — так читается глубина
        ctx.globalAlpha = 0.2 + 0.5 * p.depth + 0.3 * heat;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.sr, 0, 7);
        ctx.fill();

        if (heat > 0.45) {
          ctx.globalAlpha = 0.9 * heat;
          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, p.sr * 0.4, 0, 7);
          ctx.fill();
        }

        if (heat > 0.6) {
          ctx.globalAlpha = Math.min(1, heat);
          ctx.font = '11px ui-monospace, Consolas, monospace';
          ctx.fillStyle = '#E2E8F0';
          ctx.textAlign = 'center';
          ctx.fillText(p.label.slice(0, 30), p.sx, p.sy + p.sr + 13);
        }
        ctx.globalAlpha = 1;
      }
    };

    frame = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener('wheel', onWheel);
    };
  }, [placed, links, neighbours, selectedId]);

  const pick = (x: number, y: number): Placed | null => {
    let best: Placed | null = null;
    let bestD = 26;
    for (const p of placed) {
      const d = Math.hypot(p.sx - x, p.sy - y);
      // Ближний к зрителю выигрывает при равном промахе
      if (d < bestD + p.sr) {
        bestD = d;
        best = p;
      }
    }
    return best;
  };

  return (
    <canvas
      ref={canvasRef}
      className={`h-full w-full ${drag.current ? 'cursor-grabbing' : 'cursor-crosshair'}`}
      onMouseDown={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        drag.current = {
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          panX: camera.current.panX,
          panY: camera.current.panY,
          moved: 0,
        };
      }}
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        if (drag.current) {
          const dx = x - drag.current.x;
          const dy = y - drag.current.y;
          drag.current.moved = Math.max(drag.current.moved, Math.hypot(dx, dy));
          camera.current.panX = drag.current.panX + dx;
          camera.current.panY = drag.current.panY + dy;
          return;
        }

        pointer.current = { x, y };
        const hit = pick(x, y);
        hoverId.current = hit?.id ?? null;
        setHoverLabel(hit ? { node: hit, x, y } : null);
      }}
      onMouseUp={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const wasDrag = (drag.current?.moved ?? 0) > 4;
        drag.current = null;
        // Тащили карту — это не выбор узла
        if (wasDrag) return;
        const hit = pick(e.clientX - rect.left, e.clientY - rect.top);
        onSelect?.(hit?.id ?? null);
      }}
      onDoubleClick={() => {
        camera.current = { zoom: 1, panX: 0, panY: 0 };
      }}
      onMouseLeave={() => {
        pointer.current = null;
        hoverId.current = null;
        drag.current = null;
        setHoverLabel(null);
      }}
      title={hoverLabel?.node.label}
    />
  );
}
