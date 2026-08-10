import { useEffect, useState } from 'react'
import { getDocuments, createDocument } from '../lib/api'

export default function DocumentsScreen() {
  const [docs, setDocs] = useState<any[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', content: '', doc_type: 'markdown' })

  useEffect(() => { getDocuments().then(setDocs) }, [])

  const handleCreate = async () => {
    if (!form.title || !form.content) return
    const doc = await createDocument(form)
    setDocs([...docs, doc])
    setForm({ title: '', content: '', doc_type: 'markdown' })
    setShowCreate(false)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: '#22d3ee' }}>Documents</h2>
        <button onClick={() => setShowCreate(!showCreate)} style={{
          padding: '8px 16px', background: '#22d3ee', color: '#04121a', border: 'none',
          borderRadius: 8, fontWeight: 700, cursor: 'pointer',
        }}>+ New</button>
      </div>

      {showCreate && (
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <input value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="Title"
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14 }} />
          <textarea value={form.content} onChange={e => setForm({...form, content: e.target.value})} placeholder="Content..." rows={6}
            style={{ width: '100%', padding: '8px 12px', background: '#0a0e14', border: '1px solid #1e2a3a', borderRadius: 6, color: '#e8eef6', marginBottom: 8, fontSize: 14, resize: 'vertical' }} />
          <button onClick={handleCreate} style={{
            padding: '8px 16px', background: '#2dd4bf', color: '#04121a', border: 'none',
            borderRadius: 8, fontWeight: 700, cursor: 'pointer',
          }}>Create</button>
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        {docs.map(d => (
          <div key={d.id} style={{
            background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 700, color: '#fff' }}>{d.title}</span>
              <span style={{ fontSize: 11, color: '#6d7f97' }}>{d.doc_type}</span>
            </div>
            <div style={{ fontSize: 13, color: '#95a6bd', marginTop: 4 }}>{d.content.slice(0, 120)}...</div>
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              {d.tags?.map((t: string) => (
                <span key={t} style={{ fontSize: 11, color: '#f5b642', background: 'rgba(245,182,66,.1)', padding: '2px 8px', borderRadius: 999 }}>{t}</span>
              ))}
            </div>
          </div>
        ))}
        {docs.length === 0 && <div style={{ color: '#6d7f97', textAlign: 'center', padding: 40 }}>No documents yet</div>}
      </div>
    </div>
  )
}
