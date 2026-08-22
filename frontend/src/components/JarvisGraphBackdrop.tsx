import { useEffect, useRef } from 'react';
import { colorOfType } from '../lib/graphColors';
import type { ApiGraphEdge, ApiGraphNode } from '../types';

// Фон экрана «Джарвис»: тот же второй мозг, что на /graph, но здесь он не
// главный экспонат, а атмосфера позади разговора — поэтому без перетаскивания
// и колеса (это уже есть на /graph, дублировать под чужим текстовым полем
// означало бы, что клик по узлу конкурирует с кликом по чату). Механика
// орбит вокруг нескольких хабов и мерцание при сближении — из одобренного
// макета (artifact 07699535, «Джарвис — граф + кольцо»), перенесено
// построчно. Сами узлы, их подписи, типы и связи — настоящие данные с
// бэкенда, не выдуманный NOTE_LABELS макета.

interface Props {
  nodes: ApiGraphNode[];
  edges: ApiGraphEdge[];
}

interface OrbitNode {
  id: string;
  label: string;
  color: string;
  hubX: number;
  hubY: number;
  angle: number;
  radius: number;
  speed: number;
  x: number;
  y: number;
  r: number;
  glow: number;
}

export default function JarvisGraphBackdrop({ nodes, edges }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let W = 0;
    let H = 0;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      W = canvas.width = canvas.offsetWidth * dpr;
      H = canvas.height = canvas.offsetHeight * dpr;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    // Пять хабов со случайным положением — не данные, а раскладка: реальные
    // узлы просто распределяются по ближайшему хабу и вращаются вокруг него,
    // как в макете. 90 секунд на полный оборот у ближних узлов (канон
    // скорости — см. nexus-os-canonical-design), у дальних чуть быстрее.
    const hubCount = 5;
    const hubs = Array.from({ length: hubCount }, () => ({
      x: (0.15 + 0.7 * Math.random()) * W,
      y: (0.15 + 0.7 * Math.random()) * H,
    }));

    const byId = new Map<string, OrbitNode>();
    const placed: OrbitNode[] = nodes.map((n) => {
      const hub = hubs[Math.floor(Math.random() * hubs.length)];
      const o: OrbitNode = {
        id: n.id,
        label: n.label,
        color: colorOfType(n.node_type),
        hubX: hub.x,
        hubY: hub.y,
        angle: Math.random() * Math.PI * 2,
        radius: 30 + Math.random() * 220,
        speed: ((Math.PI * 2) / (65 + Math.random() * 65)) / 60 * (Math.random() < 0.5 ? 1 : -1),
        x: 0,
        y: 0,
        r: 1.6 + Math.random() * 2.4,
        glow: 0,
      };
      byId.set(n.id, o);
      return o;
    });

    const links = edges
      .map((e) => ({ a: byId.get(e.source), b: byId.get(e.target), t: Math.random() }))
      .filter((l): l is { a: OrbitNode; b: OrbitNode; t: number } => !!l.a && !!l.b);

    const GLOW_RADIUS = 46 * dpr;
    let frame = 0;

    const step = () => {
      frame = requestAnimationFrame(step);
      ctx.clearRect(0, 0, W, H);

      // орбиты
      for (const p of placed) {
        if (!reduceMotion) p.angle += p.speed;
        p.x = p.hubX + Math.cos(p.angle) * p.radius * dpr;
        p.y = p.hubY + Math.sin(p.angle) * p.radius * dpr * 0.62;
      }

      // связи
      ctx.lineWidth = 1;
      for (const l of links) {
        ctx.strokeStyle = 'rgba(34,211,238,0.12)';
        ctx.beginPath();
        ctx.moveTo(l.a.x, l.a.y);
        ctx.lineTo(l.b.x, l.b.y);
        ctx.stroke();

        if (!reduceMotion) {
          l.t += 0.0012;
          if (l.t > 1) l.t = 0;
          const px = l.a.x + (l.b.x - l.a.x) * l.t;
          const py = l.a.y + (l.b.y - l.a.y) * l.t;
          ctx.fillStyle = 'rgba(245,182,66,0.6)';
          ctx.beginPath();
          ctx.arc(px, py, 1.4 * dpr, 0, 7);
          ctx.fill();
        }
      }

      // мерцание при сближении
      for (const p of placed) p.glow *= 0.9;
      for (let i = 0; i < placed.length; i++) {
        for (let j = i + 1; j < placed.length; j++) {
          const a = placed[i];
          const b = placed[j];
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < GLOW_RADIUS) {
            const boost = 1 - dist / GLOW_RADIUS;
            a.glow = Math.max(a.glow, boost);
            b.glow = Math.max(b.glow, boost);
          }
        }
      }

      // узлы
      for (const p of placed) {
        if (p.glow > 0.05) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r * dpr * (2.4 + p.glow * 2), 0, 7);
          ctx.fillStyle = p.color;
          ctx.globalAlpha = p.glow * 0.2;
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * dpr * (1 + p.glow * 0.6), 0, 7);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = 0.55 + p.glow * 0.4;
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    };

    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [nodes, edges]);

  return <canvas ref={canvasRef} className="j-canvas" aria-hidden />;
}
