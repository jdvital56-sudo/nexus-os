import { Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Brain, 
  Sparkles, 
  Bot, 
  FileText, 
  Settings,
  Activity,
  Network,
  Calendar,
  CheckSquare,
  Workflow
} from 'lucide-react';

const menuItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/memory', label: 'Memory Graph', icon: Brain },
  { path: '/skills', label: 'Skills', icon: Sparkles },
  { path: '/agents', label: 'Agents', icon: Bot },
  { path: '/dream-review', label: 'Dream Review', icon: Calendar },
  { path: '/graph', label: 'Knowledge Graph', icon: Network },
  { path: '/documents', label: 'Documents', icon: FileText },
  { path: '/tasks', label: 'Tasks', icon: CheckSquare },
  { path: '/pipeline', label: 'Pipeline', icon: Workflow },
  { path: '/activity', label: 'Activity', icon: Activity },
  { path: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside className="w-64 bg-darker border-r border-gray-800 h-screen fixed left-0 top-0 overflow-y-auto">
      <div className="p-6">
        <h1 className="text-2xl font-bold text-primary">NEXUS OS</h1>
        <p className="text-xs text-gray-500 mt-1">Claude Code Operating System</p>
      </div>
      
      <nav className="mt-6">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center px-6 py-3 text-sm transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary border-r-2 border-primary'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              <Icon className="w-5 h-5 mr-3" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      
      <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-gray-800">
        <div className="flex items-center space-x-3">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-xs text-gray-400">System Online</span>
        </div>
      </div>
    </aside>
  );
}
