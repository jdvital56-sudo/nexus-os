import type { Screen } from '../types'

const items: { screen: Screen; label: string; icon: string }[] = [
  { screen: 'home', label: 'Home', icon: '◉' },
  { screen: 'graph', label: 'Graph', icon: '◎' },
  { screen: 'documents', label: 'Documents', icon: '◫' },
  { screen: 'tasks', label: 'Tasks', icon: '☑' },
  { screen: 'agents', label: 'Agents', icon: '◈' },
  { screen: 'memory', label: 'Memory', icon: '◉' },
  { screen: 'activity', label: 'Activity', icon: '▦' },
  { screen: 'settings', label: 'Settings', icon: '⚙' },
]

interface Props {
  current: Screen
  onNavigate: (s: Screen) => void
}

export default function Sidebar({ current, onNavigate }: Props) {
  return (
    <nav style={{
      width: 200,
      background: '#0f1520',
      borderRight: '1px solid #1e2a3a',
      padding: '16px 0',
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
    }}>
      <div style={{ padding: '0 16px 16px', borderBottom: '1px solid #1e2a3a', marginBottom: 8 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: '#22d3ee' }}>NEXSYS</div>
        <div style={{ fontSize: 11, color: '#6d7f97' }}>v0.1.0 · Operator</div>
      </div>
      {items.map(item => (
        <button
          key={item.screen}
          onClick={() => onNavigate(item.screen)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 16px',
            border: 'none',
            background: current === item.screen ? '#1a2434' : 'transparent',
            color: current === item.screen ? '#22d3ee' : '#95a6bd',
            cursor: 'pointer',
            fontSize: 14,
            textAlign: 'left',
            width: '100%',
          }}
        >
          <span style={{ fontSize: 16 }}>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  )
}
