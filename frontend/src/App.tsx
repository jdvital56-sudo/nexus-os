import { useState } from 'react'
import type { Screen } from './types'
import Sidebar from './components/Sidebar'
import HomeScreen from './screens/HomeScreen'
import GraphScreen from './screens/GraphScreen'
import DocumentsScreen from './screens/DocumentsScreen'
import TasksScreen from './screens/TasksScreen'
import AgentsScreen from './screens/AgentsScreen'
import MemoryScreen from './screens/MemoryScreen'
import ActivityScreen from './screens/ActivityScreen'
import SettingsScreen from './screens/SettingsScreen'
import PipelineScreen from './screens/PipelineScreen'

const screens: Record<Screen, () => JSX.Element> = {
  home: HomeScreen,
  graph: GraphScreen,
  documents: DocumentsScreen,
  tasks: TasksScreen,
  agents: AgentsScreen,
  memory: MemoryScreen,
  activity: ActivityScreen,
  settings: SettingsScreen,
  pipeline: PipelineScreen,
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('home')
  const ScreenComponent = screens[screen]

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <Sidebar current={screen} onNavigate={setScreen} />
      <main style={{ flex: 1, overflow: 'auto', padding: '24px' }}>
        <ScreenComponent />
      </main>
    </div>
  )
}
