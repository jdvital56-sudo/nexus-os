import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import HomeScreen from './screens/HomeScreen';
import GraphScreen from './screens/GraphScreen';

// Placeholder screens (can be expanded later)
const MemoryScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Memory Screen</h1></div>;
const SkillsScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Skills Screen</h1></div>;
const AgentsScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Agents Screen</h1></div>;
const DreamReviewScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Dream Review Screen</h1></div>;
const ActivityScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Activity Screen</h1></div>;
const SettingsScreen = () => <div className="p-8"><h1 className="text-3xl font-bold">Settings Screen</h1></div>;

export default function App() {
  return (
    <Router>
      <div className="flex min-h-screen bg-darker">
        <Sidebar />
        <main className="ml-64 flex-1">
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/memory" element={<MemoryScreen />} />
            <Route path="/skills" element={<SkillsScreen />} />
            <Route path="/agents" element={<AgentsScreen />} />
            <Route path="/dream-review" element={<DreamReviewScreen />} />
            <Route path="/graph" element={<GraphScreen />} />
            <Route path="/activity" element={<ActivityScreen />} />
            <Route path="/settings" element={<SettingsScreen />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
