import { useEffect, useState } from 'react'
import { getPipelineStatus, createContent, advanceContent } from '../lib/api'

const STAGE_COLORS: Record<string, string> = {
  idea: '#6d7f97',
  draft: '#22d3ee',
  review: '#f5b642',
  approve: '#a78bfa',
  schedule: '#38bdf8',
  publish: '#2dd4bf',
  metrics: '#f472b6',
}

export default function PipelineScreen() {
  const [status, setStatus] = useState<any>({})
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', platform: 'general', description: '' })

  const load = () => { getPipelineStatus().then(setStatus).catch(() => {}) }
  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!form.title) return
    await createContent(form)
    setForm({ title: '', platform: 'general', description: '' })
    setShowCreate(false)
    load()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: '#2dd4bf' }}>Content Pipeline</h2>
          <p style={{ color: '#6d7f97', fontSize: 13 }}>{status.total_items || 0} items in pipeline</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} style={{
          padding: '8px 16px', background: '#2dd4bf', color: '#04121a', border: 'none',
          borderRadius: 8, fontWeight: 700, cursor: 'pointer',
        }}>+ New Content</button>
      </div>

      {showCreate && (
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <input value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="Content title"
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14 }} />
          <div style={{ display: 'flex', gap: 8 }}>
            <select value={form.platform} onChange={e => setForm({...form, platform: e.target.value})}
              style={{ padding: '8px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6' }}>
              <option value="general">General</option>
              <option value="instagram">Instagram</option>
              <option value="twitter">Twitter</option>
              <option value="blog">Blog</option>
              <option value="linkedin">LinkedIn</option>
            </select>
            <input value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Description"
              style={{ flex: 1, padding: '8px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', fontSize: 14 }} />
            <button onClick={handleCreate} style={{
              padding: '8px 16px', background: '#2dd4bf', color: '#04121a', border: 'none',
              borderRadius: 8, fontWeight: 700, cursor: 'pointer',
            }}>Create</button>
          </div>
        </div>
      )}

      {/* Pipeline stages */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8, marginBottom: 24 }}>
        {(status.stages || []).map((stage: string) => (
          <div key={stage} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 10, padding: '12px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 11, color: STAGE_COLORS[stage] || '#6d7f97', textTransform: 'uppercase', letterSpacing: 1 }}>{stage}</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: '#fff', marginTop: 4 }}>
              {status.by_stage?.[stage] || 0}
            </div>
          </div>
        ))}
      </div>

      {/* Funnel visualization */}
      <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16 }}>
        <h3 style={{ fontSize: 14, color: '#6d7f97', marginBottom: 12 }}>Pipeline Funnel</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {(status.stages || []).map((stage: string, i: number) => {
            const count = status.by_stage?.[stage] || 0
            const maxCount = Math.max(...Object.values(status.by_stage || {}).map(Number), 1)
            const width = Math.max((count / maxCount) * 100, 5)
            return (
              <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 70, fontSize: 12, color: '#6d7f97', textAlign: 'right' }}>{stage}</span>
                <div style={{
                  height: 20, width: `${width}%`, background: STAGE_COLORS[stage] || '#6d7f97',
                  borderRadius: 4, opacity: 0.8, transition: 'width 0.3s',
                }} />
                <span style={{ fontSize: 12, color: '#fff' }}>{count}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
