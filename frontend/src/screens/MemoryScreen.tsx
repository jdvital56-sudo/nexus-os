import { useEffect, useState } from 'react'
import { getMemoryFacts, getMemoryStats, addMemoryFact } from '../lib/api'

const LAYER_COLORS: Record<string, string> = {
  inbox: '#6d7f97',
  operational: '#22d3ee',
  canonical: '#a78bfa',
  memory: '#f5b642',
}

export default function MemoryScreen() {
  const [facts, setFacts] = useState<any[]>([])
  const [stats, setStats] = useState<any>({})
  const [layer, setLayer] = useState<string>('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ content: '', layer: 'inbox', source: '', confidence: 0.5 })

  const load = () => {
    const params: Record<string, string> = {}
    if (layer) params.layer = layer
    getMemoryFacts(params).then(setFacts).catch(() => {})
    getMemoryStats().then(setStats).catch(() => {})
  }

  useEffect(() => { load() }, [layer])

  const handleAdd = async () => {
    if (!form.content) return
    await addMemoryFact(form)
    setForm({ content: '', layer: 'inbox', source: '', confidence: 0.5 })
    setShowAdd(false)
    load()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: '#f5b642' }}>Memory</h2>
          <p style={{ color: '#6d7f97', fontSize: 13 }}>
            {stats.active || 0} active facts · avg confidence {stats.avg_confidence || 0}
          </p>
        </div>
        <button onClick={() => setShowAdd(!showAdd)} style={{
          padding: '8px 16px', background: '#f5b642', color: '#04121a', border: 'none',
          borderRadius: 8, fontWeight: 700, cursor: 'pointer',
        }}>+ Add Fact</button>
      </div>

      {/* Layer filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {[{ l: '', label: 'All' }, { l: 'inbox', label: 'Inbox' }, { l: 'operational', label: 'Operational' }, { l: 'canonical', label: 'Canon' }, { l: 'memory', label: 'Memory' }].map(({ l, label }) => (
          <button key={l} onClick={() => setLayer(l)} style={{
            padding: '6px 14px', background: layer === l ? '#1a2434' : 'transparent',
            border: `1px solid ${layer === l ? '#f5b642' : '#1e2a3a'}`,
            borderRadius: 8, color: layer === l ? '#f5b642' : '#6d7f97',
            cursor: 'pointer', fontSize: 13,
          }}>{label}</button>
        ))}
      </div>

      {showAdd && (
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <textarea value={form.content} onChange={e => setForm({...form, content: e.target.value})} placeholder="Fact content..." rows={3}
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14, resize: 'vertical' }} />
          <div style={{ display: 'flex', gap: 8 }}>
            <select value={form.layer} onChange={e => setForm({...form, layer: e.target.value})}
              style={{ padding: '8px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6' }}>
              <option value="inbox">Inbox</option>
              <option value="operational">Operational</option>
              <option value="canonical">Canonical</option>
              <option value="memory">Memory</option>
            </select>
            <input value={form.source} onChange={e => setForm({...form, source: e.target.value})} placeholder="Source"
              style={{ flex: 1, padding: '8px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', fontSize: 14 }} />
            <input type="number" value={form.confidence} onChange={e => setForm({...form, confidence: parseFloat(e.target.value)})} min={0} max={1} step={0.1}
              style={{ width: 80, padding: '8px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', fontSize: 14 }} />
            <button onClick={handleAdd} style={{
              padding: '8px 16px', background: '#f5b642', color: '#04121a', border: 'none',
              borderRadius: 8, fontWeight: 700, cursor: 'pointer',
            }}>Save</button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        {facts.map(f => (
          <div key={f.id} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderLeft: `3px solid ${LAYER_COLORS[f.layer] || '#6d7f97'}`,
            borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: LAYER_COLORS[f.layer], textTransform: 'uppercase', letterSpacing: 1 }}>{f.layer}</span>
              <div style={{ display: 'flex', gap: 8, fontSize: 11, color: '#6d7f97' }}>
                <span>conf: {f.confidence}</span>
                {f.source && <span>src: {f.source}</span>}
              </div>
            </div>
            <div style={{ color: '#fff', marginTop: 6, fontSize: 14 }}>{f.content}</div>
            {f.tags?.length > 0 && (
              <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
                {f.tags.map((t: string) => (
                  <span key={t} style={{ fontSize: 11, color: '#f5b642', background: 'rgba(245,182,66,.1)', padding: '2px 8px', borderRadius: 999 }}>{t}</span>
                ))}
              </div>
            )}
          </div>
        ))}
        {facts.length === 0 && <div style={{ color: '#6d7f97', textAlign: 'center', padding: 40 }}>No memory facts yet</div>}
      </div>
    </div>
  )
}
