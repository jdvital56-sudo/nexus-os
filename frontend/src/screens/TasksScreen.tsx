import { useEffect, useState } from 'react'
import { getTasks, createTask } from '../lib/api'

const STATUS_COLORS: Record<string, string> = {
  todo: '#6d7f97',
  in_progress: '#22d3ee',
  done: '#2dd4bf',
  blocked: '#ef4444',
}

const PRIORITY_COLORS: Record<string, string> = {
  low: '#6d7f97',
  medium: '#f5b642',
  high: '#f97316',
  critical: '#ef4444',
}

export default function TasksScreen() {
  const [tasks, setTasks] = useState<any[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium' })

  useEffect(() => { getTasks().then(setTasks) }, [])

  const handleCreate = async () => {
    if (!form.title) return
    const task = await createTask(form)
    setTasks([...tasks, task])
    setForm({ title: '', description: '', priority: 'medium' })
    setShowCreate(false)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: '#2dd4bf' }}>Tasks</h2>
        <button onClick={() => setShowCreate(!showCreate)} style={{
          padding: '8px 16px', background: '#2dd4bf', color: '#04121a', border: 'none',
          borderRadius: 8, fontWeight: 700, cursor: 'pointer',
        }}>+ New</button>
      </div>

      {showCreate && (
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <input value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="Task title"
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14 }} />
          <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Description..." rows={3}
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14, resize: 'vertical' }} />
          <select value={form.priority} onChange={e => setForm({...form, priority: e.target.value})}
            style={{ padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14 }}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <br />
          <button onClick={handleCreate} style={{
            padding: '8px 16px', background: '#2dd4bf', color: '#04121a', border: 'none',
            borderRadius: 8, fontWeight: 700, cursor: 'pointer',
          }}>Create</button>
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        {tasks.map(t => (
          <div key={t.id} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderLeft: `3px solid ${STATUS_COLORS[t.status]}`, borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, color: '#fff' }}>{t.title}</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <span style={{ fontSize: 11, color: STATUS_COLORS[t.status], textTransform: 'uppercase' }}>{t.status}</span>
                <span style={{ fontSize: 11, color: PRIORITY_COLORS[t.priority], textTransform: 'uppercase' }}>{t.priority}</span>
              </div>
            </div>
            {t.description && <div style={{ fontSize: 13, color: '#95a6bd', marginTop: 4 }}>{t.description}</div>}
            {t.assigned_agent && <div style={{ fontSize: 11, color: '#a78bfa', marginTop: 4 }}>→ {t.assigned_agent}</div>}
          </div>
        ))}
        {tasks.length === 0 && <div style={{ color: '#6d7f97', textAlign: 'center', padding: 40 }}>No tasks yet</div>}
      </div>
    </div>
  )
}
