import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import HomeScreen from './screens/HomeScreen';
import GraphScreen from './screens/GraphScreen';
import MemoryScreen from './screens/MemoryScreen';
import SkillsScreen from './screens/SkillsScreen';
import AgentsScreen from './screens/AgentsScreen';
import DreamReviewScreen from './screens/DreamReviewScreen';
import ActivityScreen from './screens/ActivityScreen';
import SettingsScreen from './screens/SettingsScreen';
import DocumentsScreen from './screens/DocumentsScreen';
import TasksScreen from './screens/TasksScreen';
import PipelineScreen from './screens/PipelineScreen';

export default function App() {
  return (
    <Router>
      <div className="flex min-h-screen bg-darker">
        <Sidebar />
        <main className="ml-64 flex-1 p-8">
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/memory" element={<MemoryScreen />} />
            <Route path="/skills" element={<SkillsScreen />} />
            <Route path="/agents" element={<AgentsScreen />} />
            <Route path="/dream-review" element={<DreamReviewScreen />} />
            <Route path="/graph" element={<GraphScreen />} />
            <Route path="/documents" element={<DocumentsScreen />} />
            <Route path="/tasks" element={<TasksScreen />} />
            <Route path="/pipeline" element={<PipelineScreen />} />
            <Route path="/activity" element={<ActivityScreen />} />
            <Route path="/settings" element={<SettingsScreen />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
