import { useEffect, useState } from 'react'
import { getHealth, getGraphStats, getDocuments, getTasks, getAgents, getMemoryStats } from '../lib/api'
import OrbitalGraph from '../components/OrbitalGraph'

export default function HomeScreen() {
  const [health, setHealth] = useState<string>('checking...')
  const [stats, setStats] = useState<any>({})
  const [counts, setCounts] = useState({ docs: 0, tasks: 0, agents: 0, memories: 0 })

  useEffect(() => {
    getHealth().then(r => setHealth(r.status)).catch(() => setHealth('error'))
    getGraphStats().then(setStats).catch(() => {})
    Promise.all([getDocuments(), getTasks(), getAgents(), getMemoryStats()]).then(([d, t, a, m]) => {
      setCounts({ docs: d.length, tasks: t.length, agents: a.length, memories: m.active || 0 })
    }).catch(() => {})
  }, [])

  const cards = [
    { label: 'Memories', value: counts.memories, color: '#f5b642' },
    { label: 'Graph Nodes', value: stats.nodes || 0, color: '#22d3ee' },
    { label: 'Documents', value: counts.docs, color: '#a78bfa' },
    { label: 'Tasks', value: counts.tasks, color: '#2dd4bf' },
    { label: 'Agents', value: counts.agents, color: '#f472b6' },
    { label: 'Edges', value: stats.edges || 0, color: '#38bdf8' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: '#fff' }}>NEXSYS</h1>
          <p style={{ color: '#6d7f97', fontSize: 13 }}>Operator · Local · {health}</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
        {cards.map(c => (
          <div key={c.label} style={{
            background: '#0f1520',
            border: '1px solid #1e2a3a',
            borderRadius: 12,
            padding: '16px 20px',
          }}>
            <div style={{ fontSize: 12, color: '#6d7f97', textTransform: 'uppercase', letterSpacing: 1 }}>{c.label}</div>
            <div style={{ fontSize: 32, fontWeight: 800, color: c.color, marginTop: 4 }}>{c.value}</div>
          </div>
        ))}
      </div>

      <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, color: '#6d7f97', marginBottom: 8 }}>Knowledge Graph</div>
        <OrbitalGraph />
      </div>
    </div>
  )
}
