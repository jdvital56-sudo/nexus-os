import { useEffect, useState } from 'react'
import { getAgents, getTasks } from '../lib/api'

export default function ActivityScreen() {
  const [agents, setAgents] = useState<any[]>([])
  const [recentTasks, setRecentTasks] = useState<any[]>([])

  useEffect(() => {
    getAgents().then(setAgents).catch(() => {})
    getTasks().then(tasks => {
      setRecentTasks(tasks.slice(-10).reverse())
    }).catch(() => {})
  }, [])

  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#22d3ee', marginBottom: 16 }}>Activity</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Agent Status */}
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontSize: 16, color: '#a78bfa', marginBottom: 12 }}>Agent Status</h3>
          {agents.length === 0 ? (
            <div style={{ color: '#6d7f97', textAlign: 'center', padding: 20 }}>No agents</div>
          ) : (
            <div style={{ display: 'grid', gap: 6 }}>
              {agents.map(a => (
                <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #1e2a3a' }}>
                  <span style={{ color: '#fff', fontSize: 13 }}>{a.name}</span>
                  <span style={{
                    fontSize: 11,
                    color: a.status === 'running' ? '#22d3ee' : a.status === 'error' ? '#ef4444' : '#6d7f97',
                    textTransform: 'uppercase',
                  }}>{a.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Tasks */}
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontSize: 16, color: '#2dd4bf', marginBottom: 12 }}>Recent Tasks</h3>
          {recentTasks.length === 0 ? (
            <div style={{ color: '#6d7f97', textAlign: 'center', padding: 20 }}>No tasks</div>
          ) : (
            <div style={{ display: 'grid', gap: 6 }}>
              {recentTasks.map(t => (
                <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #1e2a3a' }}>
                  <span style={{ color: '#fff', fontSize: 13 }}>{t.title}</span>
                  <span style={{
                    fontSize: 11,
                    color: t.status === 'done' ? '#2dd4bf' : t.status === 'blocked' ? '#ef4444' : '#6d7f97',
                    textTransform: 'uppercase',
                  }}>{t.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
