import { useState } from 'react';
import { DollarSign, Clock, TrendingUp, AlertCircle } from 'lucide-react';
import { analyticsApi, systemApi } from '../lib/api';
import { useApi } from '../hooks/useApi';
import type { AnalyticsData, SystemStatus } from '../types';
import { JarvisHudWidget } from '../components/JarvisHudWidget';

// Mock data for demo (will be replaced with real API calls)
const mockAnalytics: AnalyticsData = {
  totalSpent: 247.83,
  timeSaved: 127,
  moneySaved: 8940,
  netRoi: 3512,
  apiUsage: [
    { provider: 'Claude API', tokensUsed: '2.4M', cost: 124.50, limit: 500 },
    { provider: 'OpenAI API', tokensUsed: '1.8M', cost: 89.20, limit: 300 },
    { provider: 'Gemini API', tokensUsed: '3.1M', cost: 34.13, limit: 1000 },
  ],
};

const mockSystemStatus: SystemStatus = {
  dreamCadenceEnabled: true,
  nextDreamReview: 'Today at 3:00 AM',
  obsidianConnected: true,
  apolloConnected: true,
  googleCalendarConnected: false,
  telegramConnected: true,
};

export default function HomeScreen() {
  const [period, setPeriod] = useState('7d');
  const [jarvisState, setJarvisState] = useState<'ONLINE' | 'LISTENING' | 'SPEAKING' | 'PROCESSING'>('ONLINE');
  
  // In production, uncomment these:
  // const { data: analytics } = useApi<AnalyticsData>(() => analyticsApi.getOverview(), [period]);
  // const { data: systemStatus } = useApi<SystemStatus>(() => systemApi.getStatus(), []);
  
  const analytics = mockAnalytics;
  const systemStatus = mockSystemStatus;

  const statCards = [
    {
      title: 'Total Spent on AI',
      value: `$${analytics.totalSpent.toFixed(2)}`,
      icon: DollarSign,
      color: 'text-red-400',
      bgColor: 'bg-red-400/10',
    },
    {
      title: 'Time Saved',
      value: `${analytics.timeSaved}h`,
      icon: Clock,
      color: 'text-blue-400',
      bgColor: 'bg-blue-400/10',
    },
    {
      title: 'Money Saved',
      value: `$${analytics.moneySaved.toLocaleString()}`,
      icon: TrendingUp,
      color: 'text-green-400',
      bgColor: 'bg-green-400/10',
    },
    {
      title: 'Net ROI',
      value: `${((analytics.netRoi / analytics.totalSpent) * 100).toFixed(0)}%`,
      icon: TrendingUp,
      color: 'text-purple-400',
      bgColor: 'bg-purple-400/10',
    },
  ];

  return (
    <div className="p-8">
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-gray-400">Overview of your AI operations and ROI</p>
        </div>
        
        {/* J.A.R.V.I.S. HUD Widget */}
        <div className="relative">
          <JarvisHudWidget state={jarvisState} activeModel="GEMINI-2.0" />
          
          {/* Quick state controls for demo */}
          <div className="absolute -bottom-2 left-1/2 transform -translate-x-1/2 flex gap-1">
            <button
              onClick={() => setJarvisState('ONLINE')}
              className={`px-2 py-1 text-xs rounded ${jarvisState === 'ONLINE' ? 'bg-emerald-500 text-white' : 'bg-gray-700 text-gray-300'}`}
            >
              Online
            </button>
            <button
              onClick={() => setJarvisState('LISTENING')}
              className={`px-2 py-1 text-xs rounded ${jarvisState === 'LISTENING' ? 'bg-pink-500 text-white' : 'bg-gray-700 text-gray-300'}`}
            >
              Listen
            </button>
            <button
              onClick={() => setJarvisState('SPEAKING')}
              className={`px-2 py-1 text-xs rounded ${jarvisState === 'SPEAKING' ? 'bg-cyan-500 text-white' : 'bg-gray-700 text-gray-300'}`}
            >
              Speak
            </button>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {statCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.title} className="bg-dark rounded-xl p-6 border border-gray-800">
              <div className="flex items-center justify-between mb-4">
                <div className={`${stat.bgColor} p-3 rounded-lg`}>
                  <Icon className={`w-6 h-6 ${stat.color}`} />
                </div>
              </div>
              <h3 className="text-gray-400 text-sm mb-1">{stat.title}</h3>
              <p className="text-2xl font-bold text-white">{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* API Usage Table */}
      <div className="bg-dark rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">API Usage & Costs</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-gray-400 text-sm">
                <th className="pb-4 font-medium">Provider</th>
                <th className="pb-4 font-medium">Tokens Used</th>
                <th className="pb-4 font-medium">Cost</th>
                <th className="pb-4 font-medium">Limit</th>
                <th className="pb-4 font-medium">Usage</th>
              </tr>
            </thead>
            <tbody>
              {analytics.apiUsage.map((usage, index) => (
                <tr key={usage.provider} className="border-t border-gray-800">
                  <td className="py-4 text-white">{usage.provider}</td>
                  <td className="py-4 text-gray-400">{usage.tokensUsed}</td>
                  <td className="py-4 text-white">${usage.cost.toFixed(2)}</td>
                  <td className="py-4 text-gray-400">${usage.limit}</td>
                  <td className="py-4">
                    <div className="w-32 bg-gray-800 rounded-full h-2">
                      <div 
                        className="bg-primary h-2 rounded-full" 
                        style={{ width: `${Math.min((usage.cost / usage.limit) * 100, 100)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* System Status */}
      <div className="bg-dark rounded-xl p-6 border border-gray-800">
        <h2 className="text-xl font-bold text-white mb-4">System Status</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="flex items-center space-x-3 p-4 bg-darker rounded-lg">
            <div className={`w-3 h-3 rounded-full ${systemStatus.dreamCadenceEnabled ? 'bg-green-500' : 'bg-gray-500'}`} />
            <span className="text-gray-300">Dream Cadence</span>
          </div>
          <div className="flex items-center space-x-3 p-4 bg-darker rounded-lg">
            <div className={`w-3 h-3 rounded-full ${systemStatus.obsidianConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-300">Obsidian Vault</span>
          </div>
          <div className="flex items-center space-x-3 p-4 bg-darker rounded-lg">
            <div className={`w-3 h-3 rounded-full ${systemStatus.apolloConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-300">Apollo.io</span>
          </div>
          <div className="flex items-center space-x-3 p-4 bg-darker rounded-lg">
            <div className={`w-3 h-3 rounded-full ${systemStatus.googleCalendarConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-300">Google Calendar</span>
          </div>
          <div className="flex items-center space-x-3 p-4 bg-darker rounded-lg">
            <div className={`w-3 h-3 rounded-full ${systemStatus.telegramConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-300">Telegram Bot</span>
          </div>
        </div>
        
        {systemStatus.dreamCadenceEnabled && (
          <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary/20">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-5 h-5 text-primary" />
              <span className="text-primary text-sm">Next Dream Review: {systemStatus.nextDreamReview}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
