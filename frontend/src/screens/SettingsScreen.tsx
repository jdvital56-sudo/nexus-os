export default function SettingsScreen() {
  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#6d7f97', marginBottom: 16 }}>Settings</h2>
      <div style={{ display: 'grid', gap: 12, maxWidth: 500 }}>
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 10, padding: '14px 18px' }}>
          <div style={{ fontWeight: 700, color: '#fff', marginBottom: 4 }}>API Endpoint</div>
          <div style={{ fontSize: 13, color: '#95a6bd' }}>http://127.0.0.1:8420</div>
        </div>
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 10, padding: '14px 18px' }}>
          <div style={{ fontWeight: 700, color: '#fff', marginBottom: 4 }}>Data Directory</div>
          <div style={{ fontSize: 13, color: '#95a6bd' }}>~/.nexsys/</div>
        </div>
        <div style={{ background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 10, padding: '14px 18px' }}>
          <div style={{ fontWeight: 700, color: '#fff', marginBottom: 4 }}>Version</div>
          <div style={{ fontSize: 13, color: '#95a6bd' }}>0.1.0</div>
        </div>
      </div>
    </div>
  )
}
