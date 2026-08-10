import { useRef, useEffect, useState, useCallback } from 'react'
import { getGraphNodes, getGraphStats } from '../lib/api'
import type { GraphNode, GraphStats } from '../types'

interface NodePosition extends GraphNode {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  color: string
}

const COLORS: Record<string, string> = {
  memory: '#f5b642',
  document: '#22d3ee',
  task: '#2dd4bf',
  concept: '#a78bfa',
  agent: '#f472b6',
  decision: '#38bdf8',
  session: '#6ee7b7',
  file: '#94a3b8',
}

export default function OrbitalGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const nodesRef = useRef<NodePosition[]>([])
  const animRef = useRef<number>(0)
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getGraphNodes(), getGraphStats()]).then(([nodes, s]) => {
      setStats(s)
      const w = canvasRef.current?.width || 800
      const h = canvasRef.current?.height || 600
      const cx = w / 2
      const cy = h / 2
      nodesRef.current = nodes.map((n: GraphNode, i: number) => {
        const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2
        const dist = 120 + Math.random() * 100
        return {
          ...n,
          x: cx + Math.cos(angle) * dist,
          y: cy + Math.sin(angle) * dist,
          vx: 0,
          vy: 0,
          radius: 8 + Math.min(n.metadata?.importance || 1, 5) * 3,
          color: COLORS[n.node_type] || '#6d7f97',
        }
      })
    })
  }, [])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const w = canvas.width
    const h = canvas.height

    ctx.fillStyle = '#0a0e14'
    ctx.fillRect(0, 0, w, h)

    const nodes = nodesRef.current

    // Simple force simulation
    const cx = w / 2, cy = h / 2
    for (const node of nodes) {
      // Gravity toward center
      node.vx += (cx - node.x) * 0.0003
      node.vy += (cy - node.y) * 0.0003
      // Repulsion between nodes
      for (const other of nodes) {
        if (other === node) continue
        const dx = node.x - other.x
        const dy = node.y - other.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        if (dist < 100) {
          node.vx += dx / dist * 0.5
          node.vy += dy / dist * 0.5
        }
      }
      node.vx *= 0.95
      node.vy *= 0.95
      node.x += node.vx
      node.y += node.vy
      // Bounds
      node.x = Math.max(20, Math.min(w - 20, node.x))
      node.y = Math.max(20, Math.min(h - 20, node.y))
    }

    // Draw edges
    ctx.strokeStyle = '#1e2a3a'
    ctx.lineWidth = 1
    for (const node of nodes) {
      // Connect to nearest 2
      const sorted = [...nodes].filter(n => n !== node).sort((a, b) => {
        const da = Math.hypot(node.x - a.x, node.y - a.y)
        const db = Math.hypot(node.x - b.x, node.y - b.y)
        return da - db
      })
      for (const target of sorted.slice(0, 2)) {
        ctx.beginPath()
        ctx.moveTo(node.x, node.y)
        ctx.lineTo(target.x, target.y)
        ctx.stroke()
      }
    }

    // Draw nodes
    for (const node of nodes) {
      const isHovered = hovered === node.id
      // Glow
      if (isHovered) {
        ctx.shadowColor = node.color
        ctx.shadowBlur = 20
      }
      ctx.beginPath()
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
      ctx.fillStyle = node.color
      ctx.fill()
      ctx.shadowBlur = 0

      // Label
      ctx.fillStyle = isHovered ? '#fff' : '#95a6bd'
      ctx.font = isHovered ? 'bold 12px sans-serif' : '11px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.label, node.x, node.y + node.radius + 14)
    }

    animRef.current = requestAnimationFrame(draw)
  }, [hovered])

  useEffect(() => {
    animRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(animRef.current)
  }, [draw])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    let found: string | null = null
    for (const node of nodesRef.current) {
      if (Math.hypot(mx - node.x, my - node.y) < node.radius + 4) {
        found = node.id
        break
      }
    }
    if (found !== hovered) setHovered(found)
  }, [hovered])

  return (
    <div>
      {stats && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 13, color: '#6d7f97' }}>
          <span>{stats.nodes} nodes</span>
          <span>{stats.edges} edges</span>
          <span>{stats.connected_components} components</span>
        </div>
      )}
      <canvas
        ref={canvasRef}
        width={800}
        height={500}
        style={{ background: '#0a0e14', borderRadius: 12, border: '1px solid #1e2a3a', width: '100%' }}
        onMouseMove={handleMouseMove}
      />
    </div>
  )
}
