import { useEffect, useState } from 'react'
import { getGraphNodes, getGraphStats, searchGraph } from '../lib/api'
import OrbitalGraph from '../components/OrbitalGraph'

export default function GraphScreen() {
  const [nodes, setNodes] = useState<any[]>([])
  const [stats, setStats] = useState<any>({})
  const [query, setQuery] = useState('')

  useEffect(() => {
    getGraphNodes().then(setNodes)
    getGraphStats().then(setStats)
  }, [])

  const handleSearch = async () => {
    if (!query.trim()) {
      getGraphNodes().then(setNodes)
      return
    }
    const results = await searchGraph(query)
    setNodes(results)
  }

  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#22d3ee', marginBottom: 16 }}>Knowledge Graph</h2>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Search nodes..."
          style={{
            flex: 1, padding: '10px 14px', background: '#0f1520', border: '1px solid #1e2a3a',
            borderRadius: 8, color: '#e8eef6', fontSize: 14, outline: 'none',
          }}
        />
        <button onClick={handleSearch} style={{
          padding: '10px 20px', background: '#22d3ee', color: '#04121a', border: 'none',
          borderRadius: 8, fontWeight: 700, cursor: 'pointer',
        }}>Search</button>
      </div>

      <OrbitalGraph />

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, color: '#6d7f97', marginBottom: 8 }}>
          {nodes.length} nodes · {stats.edges || 0} edges
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
          {nodes.map((n: any) => (
            <div key={n.id} style={{
              background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 8, padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, color: '#6d7f97', textTransform: 'uppercase' }}>{n.node_type}</div>
              <div style={{ fontSize: 14, color: '#fff', fontWeight: 600 }}>{n.label}</div>
              <div style={{ fontSize: 11, color: '#6d7f97' }}>{n.id}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
