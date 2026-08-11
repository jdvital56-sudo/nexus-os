export default function SkillsScreen() {
  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: '#a78bfa', marginBottom: 16 }}>Skills</h2>
      <div style={{
        background: '#0f1520', border: '1px solid #1e2a3a', borderRadius: 12,
        padding: 40, textAlign: 'center', color: '#6d7f97',
      }}>
        <div style={{ fontSize: 15, color: '#95a6bd', marginBottom: 8 }}>Экран в разработке</div>
        <div style={{ fontSize: 13 }}>
          Бэкенд скиллов уже работает: <code>/api/skills</code>. Интерфейс подключается в PR-21.
        </div>
      </div>
    </div>
  )
}
