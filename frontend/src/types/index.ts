export interface AnalyticsData {
  totalSpent: number;
  timeSaved: number; // hours
  moneySaved: number;
  netRoi: number;
  apiUsage: ApiUsage[];
}

export interface ApiUsage {
  provider: string;
  tokensUsed: number;
  cost: number;
  limit: number;
}

export interface DreamReview {
  date: string;
  summary: string;
  actions: ActionItem[];
  patterns: Pattern[];
  memoryIssues: MemoryIssue[];
}

export interface ActionItem {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  estimatedSavings: number;
}

export interface Pattern {
  action: string;
  count: number;
  suggestion: string;
  potentialSavings: number;
}

export interface MemoryIssue {
  source: string;
  issue: string;
  age: string;
  recommendation: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  executions: number;
  timeSaved: number;
  moneySaved: number;
  efficiency: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'memory' | 'workspace' | 'file' | 'decision' | 'session' | 'skill';
  size: number;
  color: string;
}

export interface GraphLink {
  source: string;
  target: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface Agent {
  id: string;
  name: string;
  persona: string;
  model: string;
  status: 'active' | 'idle' | 'busy';
  tasksCompleted: number;
  avgResponseTime: number;
}

export interface SystemStatus {
  dreamCadenceEnabled: boolean;
  nextDreamReview: string;
  obsidianConnected: boolean;
  apolloConnected: boolean;
  googleCalendarConnected: boolean;
  telegramConnected: boolean;
}
