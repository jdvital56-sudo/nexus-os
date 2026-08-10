import { useEffect, useState } from 'react'
import { getGraphNodes } from '../lib/api'

export default function MemoryScreen() {
  const [memories, setMemories] = useState<any[]>([])

  useEffect(() => {
    getGraphNodes({ node_type: 'memory' }).then(setMemories).catch(() => {})
  }, [])

  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#f5b642', marginBottom: 16 }}>Memory</h2>
      <p style={{ color: '#6d7f97', marginBottom: 16 }}>Persistent facts and context the system remembers between sessions.</p>

      <div style={{ display: 'grid', gap: 8 }}>
        {memories.map(m => (
          <div key={m.id} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderLeft: '3px solid #f5b642',
            borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ fontWeight: 700, color: '#fff' }}>{m.label}</div>
            {m.metadata?.source && <div style={{ fontSize: 11, color: '#6d7f97', marginTop: 4 }}>Source: {m.metadata.source}</div>}
            {m.metadata?.content && <div style={{ fontSize: 13, color: '#95a6bd', marginTop: 4 }}>{m.metadata.content}</div>}
          </div>
        ))}
        {memories.length === 0 && (
          <div style={{ color: '#6d7f97', textAlign: 'center', padding: 40 }}>
            No memories yet. Import documents to start building the knowledge graph.
          </div>
        )}
      </div>
    </div>
  )
}
