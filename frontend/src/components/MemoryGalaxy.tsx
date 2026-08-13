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
  /** Двойной щелчок — провалиться внутрь узла (например, открыть заметку). */
  onOpen?: (id: string) => void;
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

// Полный оборот. На большой карте быстрое вращение мешает читать подписи —
// глаз не успевает поймать узел, как тот уже уехал.
const TURN_SECONDS = 160;

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
  // Облако растёт вместе с числом узлов. При фиксированном радиусе полтысячи
  // штук слипались в белое пятно: ореолы наезжали друг на друга, подписи
  // ложились стопкой, разобрать было нечего.
  const spread = 170 + 24 * Math.sqrt(nodes.length);

  // Стартуем с равномерной сферы: случайный старт даёт комки и долгую усадку
  const placed: Placed[] = nodes.map((n, i) => {
    const golden = Math.PI * (3 - Math.sqrt(5));
    const y = 1 - (i / Math.max(nodes.length - 1, 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    const scale = spread * (0.75 + (i % 7) * 0.05);
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
        if (d2 > spread * spread) continue;
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

export default function MemoryGalaxy({ nodes, links, onSelect, onOpen, selectedId }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const hoverId = useRef<string | null>(null);
  // Камера: приближение и сдвиг. В ref — их меняет колесо и перетаскивание
  // много раз в секунду, состояние React тут только мешало бы
  const camera = useRef({ zoom: 1, panX: 0, panY: 0 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number; moved: number } | null>(null);
  // Узел, который тянут мышью. Пока он схвачен, связанные с ним подтягиваются
  const dragged = useRef<Placed | null>(null);
  // Угол поворота последнего кадра — нужен, чтобы перевести курсор в мир
  const angleRef = useRef(0);
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
      angleRef.current = angle;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);

      // Пока узел держат, соседи подтягиваются за ним — карта ведёт себя
      // как связанная сеть, а не как картинка, по которой возят точку
      if (dragged.current) {
        for (let it = 0; it < 3; it++) {
          for (const l of links) {
            const a = byId.get(l.source);
            const b = byId.get(l.target);
            if (!a || !b) continue;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dz = b.z - a.z;
            const d = Math.hypot(dx, dy, dz) || 1;
            const shift = ((d - 150) / d) * 0.09;
            if (a !== dragged.current) {
              a.x += dx * shift;
              a.y += dy * shift;
              a.z += dz * shift;
            }
            if (b !== dragged.current) {
              b.x -= dx * shift;
              b.y -= dy * shift;
              b.z -= dz * shift;
            }
          }
        }
      }
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
        // Шарики заметно крупнее: мелкие точки выглядели пылью, а узел —
        // это вещь, о которой система что-то знает
        p.sr = (4.5 + Math.min(p.degree, 20) * 0.75) * k * zoom;
        // 1 — у самого зрителя, 0 — на дальнем краю
        p.depth = Math.max(0, Math.min(1, (FOCAL * 0.5 - rz) / (FOCAL * 0.9)));
      }

      // Дальние первыми: ближние должны лечь поверх
      // Выбранный узел плавно подтягивается в центр — иначе после поиска
      // приходится искать его глазами по всей карте
      if (selectedId && !drag.current) {
        const target = byId.get(selectedId);
        if (target) {
          camera.current.panX += (cx - target.sx) * 0.05;
          camera.current.panY += (cy - target.sy) * 0.05;
        }
      }

      const order = [...placed].sort((a, b) => a.depth - b.depth);
      const ptr = pointer.current;
      const focus = hoverId.current ?? selectedId ?? null;
      const focusSet = focus ? new Set([focus, ...(neighbours.get(focus) ?? [])]) : null;

      // Кто сейчас ближе всех к зрителю. Эти двое горят всегда, даже когда
      // мышь никто не трогает: облако поворачивается — и очередь переходит
      // к следующему узлу. Считать «примерно по глубине» оказалось мало,
      // ясная звезда должна быть всегда.
      let first: Placed | null = null;
      let second: Placed | null = null;
      for (const p of placed) {
        if (!first || p.depth > first.depth) {
          second = first;
          first = p;
        } else if (!second || p.depth > second.depth) {
          second = p;
        }
      }
      // Медленное дыхание ведущей звезды — чтобы взгляд её находил
      const pulse = 0.9 + 0.1 * Math.sin(t * 1.6);

      const heatOf = (p: Placed): number => {
        if (focusSet) return focusSet.has(p.id) ? 1 : 0.05;
        let heat = 0.35 * Math.pow(p.depth, 8);
        if (p === first) heat = pulse;
        else if (p === second) heat = Math.max(heat, 0.7 * pulse);
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

        // Одна точка на нить: две читались как поток данных, а тут
        // спокойный обмен. Идёт всегда — она и показывает, что связь живая
        // Вдвое медленнее прежнего: фаундер сказал, что точки бегали
        // «чересчур» быстро. Нить проходится примерно за минуту — связь
        // видно как живую, но глаз за ней не гоняется.
        const speed = 0.015 + Math.min(l.weight, 4) * 0.006;
        const bright = focusSet ? (lit ? 1 : 0.06) : 0.3 + 0.7 * Math.pow((a.depth + b.depth) / 2, 3);
        const prog = (t * speed + (li % 11) / 11) % 1;
        ctx.globalAlpha = Math.min(0.95, 0.2 + bright * 0.75);
        // Тёплый песок вместо чистого белого — белый выбивался из палитры
        ctx.fillStyle = lit ? `rgb(${SOLAR})` : '#cbbfa0';
        ctx.beginPath();
        ctx.arc(
          a.sx + (b.sx - a.sx) * prog,
          a.sy + (b.sy - a.sy) * prog,
          (bright > 0.5 ? 1.8 : 1.1) * Math.min(zoom, 2),
          0,
          7,
        );
        ctx.fill();
        ctx.globalAlpha = 1;
      });

      // Узлы: дальние рисуются раньше, ближние ложатся поверх
      for (const p of order) {
        const heat = heatOf(p);

        // Ореол — только у по-настоящему разгоревшихся. Раньше слабое
        // свечение было у половины карты, и все ореолы складывались в
        // сплошное белое зарево
        if (heat > 0.25) {
          ctx.globalCompositeOperation = 'lighter';
          const halo = p.sr * (1.2 + 3.4 * heat);
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
          ctx.fillStyle = '#e0d6bb';
          ctx.beginPath();
          ctx.arc(p.sx, p.sy, p.sr * 0.4, 0, 7);
          ctx.fill();
        }

        // Подпись — только у ведущей звезды и у того, что под курсором.
        // Десяток подписей одновременно ложился стопкой и читать было
        // нечего; имя нужно ровно там, куда смотришь
        const named = p === first || p.id === hoverId.current || p.id === selectedId;
        if (named) {
          ctx.globalAlpha = 0.95;
          ctx.font = '12px ui-monospace, Consolas, monospace';
          ctx.textAlign = 'center';
          const text = p.label.slice(0, 34);
          // Тёмная подложка: поверх светящегося облака белый текст пропадал
          const w = ctx.measureText(text).width;
          ctx.fillStyle = 'rgba(27, 25, 21, 0.78)';
          ctx.fillRect(p.sx - w / 2 - 5, p.sy + p.sr + 4, w + 10, 16);
          ctx.fillStyle = '#cbbfa0';
          ctx.fillText(text, p.sx, p.sy + p.sr + 16);
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
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const hit = pick(x, y);
        // Схватил узел — тянем его; схватил пустоту — двигаем всю карту
        dragged.current = hit ?? null;
        drag.current = {
          x,
          y,
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

          const node = dragged.current;
          if (node) {
            // Экран → мир: глубину узла оставляем прежней, меняем только
            // то, что видно на плоскости экрана, и раскручиваем поворот назад
            const { zoom, panX, panY } = camera.current;
            const rzOld = node.x * Math.sin(angleRef.current) + node.z * Math.cos(angleRef.current);
            const k = FOCAL / (FOCAL + rzOld);
            const rx = (x - rect.width / 2 - panX) / (k * zoom);
            const cos = Math.cos(angleRef.current);
            const sin = Math.sin(angleRef.current);
            node.x = rx * cos + rzOld * sin;
            node.z = -rx * sin + rzOld * cos;
            node.y = (y - rect.height / 2 - panY) / (k * zoom);
            return;
          }

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
        dragged.current = null;
        // Тащили карту — это не выбор узла
        if (wasDrag) return;
        const hit = pick(e.clientX - rect.left, e.clientY - rect.top);
        onSelect?.(hit?.id ?? null);
      }}
      onDoubleClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const hit = pick(e.clientX - rect.left, e.clientY - rect.top);
        // По узлу — провалиться внутрь, по пустоте — вернуть вид
        if (hit && onOpen) {
          onOpen(hit.id);
          return;
        }
        camera.current = { zoom: 1, panX: 0, panY: 0 };
      }}
      onMouseLeave={() => {
        pointer.current = null;
        hoverId.current = null;
        drag.current = null;
        dragged.current = null;
        setHoverLabel(null);
      }}
      title={hoverLabel?.node.label}
    />
  );
}
