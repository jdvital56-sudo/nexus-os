import { useEffect, useState } from 'react'
import { getAgents, runAgent } from '../lib/api'

const ROLE_COLORS: Record<string, string> = {
  builder: '#22d3ee',
  librarian: '#f5b642',
  reviewer: '#2dd4bf',
  researcher: '#a78bfa',
  monitor: '#f472b6',
  jarvis: '#38bdf8',
}

const STATUS_ICONS: Record<string, string> = {
  idle: '◉',
  running: '⟳',
  error: '✗',
  paused: '❚❚',
}

export default function AgentsScreen() {
  const [agents, setAgents] = useState<any[]>([])
  const [running, setRunning] = useState<string | null>(null)
  const [output, setOutput] = useState<string | null>(null)

  useEffect(() => { getAgents().then(setAgents) }, [])

  const handleRun = async (id: string) => {
    setRunning(id)
    setOutput(null)
    try {
      const result = await runAgent(id, 'test task')
      setOutput(result.output)
      setAgents(agents.map(a => a.id === id ? { ...a, status: 'idle', last_run: new Date().toISOString() } : a))
    } catch (e: any) {
      setOutput(`Error: ${e.message}`)
    }
    setRunning(null)
  }

  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#a78bfa', marginBottom: 16 }}>Agents</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {agents.map(a => (
          <div key={a.id} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: '16px 20px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: 20 }}>{STATUS_ICONS[a.status] || '◉'}</span>
                <span style={{ fontWeight: 700, color: '#fff', marginLeft: 8 }}>{a.name}</span>
              </div>
              <span style={{
                fontSize: 11, color: ROLE_COLORS[a.role] || '#6d7f97',
                background: `${ROLE_COLORS[a.role] || '#6d7f97'}15`, padding: '3px 10px', borderRadius: 999,
                textTransform: 'uppercase',
              }}>{a.role}</span>
            </div>
            <div style={{ fontSize: 13, color: '#95a6bd', marginTop: 6 }}>{a.description || 'No description'}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button
                onClick={() => handleRun(a.id)}
                disabled={running === a.id}
                style={{
                  padding: '6px 14px', background: running === a.id ? '#1e2a3a' : '#a78bfa', color: '#04121a',
                  border: 'none', borderRadius: 6, fontWeight: 700, cursor: running ? 'wait' : 'pointer', fontSize: 12,
                }}
              >
                {running === a.id ? 'Running...' : 'Run'}
              </button>
            </div>
          </div>
        ))}
        {agents.length === 0 && <div style={{ color: '#6d7f97', textAlign: 'center', padding: 40, gridColumn: '1 / -1' }}>No agents yet</div>}
      </div>

      {output && (
        <div style={{
          marginTop: 16, background: '#070b11', border: '1px solid #1e2a3a', borderRadius: 10,
          padding: 16, fontFamily: 'monospace', fontSize: 13, color: '#b7cde2', whiteSpace: 'pre-wrap',
        }}>
          {output}
        </div>
      )}
    </div>
  )
}
