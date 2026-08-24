import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import WidgetScreen from './screens/WidgetScreen';
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
import IdeasScreen from './screens/IdeasScreen';
import GuardScreen from './screens/GuardScreen';
import ContentScreen from './screens/ContentScreen';
import PipelineScreen from './screens/PipelineScreen';
import PersonasScreen from './screens/PersonasScreen';
import WalletScreen from './screens/WalletScreen';
import ArtifactsScreen from './screens/ArtifactsScreen';
import ChatScreen from './screens/ChatScreen';
import MailScreen from './screens/MailScreen';
import CalendarScreen from './screens/CalendarScreen';

export default function App() {
  return (
    <Router>
      <Routes>
        {/* Виджет — своя ветка без сайдбара: это либо крошечное окно
            Electron поверх рабочего стола, либо маленькая страница сама
            по себе, сайдбар шириной 256px там просто не поместится. */}
        <Route path="/widget" element={<WidgetScreen />} />
        <Route
          path="*"
          element={
            <div className="flex min-h-screen bg-darker">
              <Sidebar />
              <main className="ml-64 flex-1 p-8">
                <Routes>
                  <Route path="/" element={<HomeScreen />} />
                  <Route path="/chat" element={<ChatScreen />} />
                  <Route path="/memory" element={<MemoryScreen />} />
                  <Route path="/skills" element={<SkillsScreen />} />
                  <Route path="/agents" element={<AgentsScreen />} />
                  <Route path="/personas" element={<PersonasScreen />} />
                  <Route path="/wallet" element={<WalletScreen />} />
                  <Route path="/artifacts" element={<ArtifactsScreen />} />
                  <Route path="/mail" element={<MailScreen />} />
                  <Route path="/calendar" element={<CalendarScreen />} />
                  <Route path="/dream-review" element={<DreamReviewScreen />} />
                  <Route path="/graph" element={<GraphScreen />} />
                  <Route path="/documents" element={<DocumentsScreen />} />
                  <Route path="/tasks" element={<TasksScreen />} />
                  <Route path="/ideas" element={<IdeasScreen />} />
                  <Route path="/guard" element={<GuardScreen />} />
                  <Route path="/content" element={<ContentScreen />} />
                  {/* Старый Pipeline остаётся доступен по прямой ссылке, но из
                      меню на него больше не ведёт: «Контент» в сайдбаре — это
                      контент-завод (services/content_factory.py), а Pipeline —
                      другая, более ранняя система со своим хранилищем. */}
                  <Route path="/pipeline" element={<PipelineScreen />} />
                  <Route path="/activity" element={<ActivityScreen />} />
                  <Route path="/settings" element={<SettingsScreen />} />
                </Routes>
              </main>
            </div>
          }
        />
      </Routes>
    </Router>
  );
}
