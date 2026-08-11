export default function DreamReviewScreen() {
  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#38bdf8', marginBottom: 16 }}>Dream Review</h2>
      <div style={{
        background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12,
        padding: 40, textAlign: 'center', color: '#6d7f97',
      }}>
        <div style={{ fontSize: 15, color: '#95a6bd', marginBottom: 8 }}>Экран в разработке</div>
        <div style={{ fontSize: 13 }}>
          Dream Cadence написан, но пока не запускается. Ночные находки и кнопки Apply/Skip
          появятся после PR-11 (бэкенд) и PR-21 (интерфейс).
        </div>
      </div>
    </div>
  )
}
