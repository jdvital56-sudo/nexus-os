// Сводка для дашборда — то, что бэкенд знает на самом деле (GET /api/system/status).
// Прежние AnalyticsData/ApiUsage описывали придуманные числа («сэкономлено $8940»)
// и удалены вместе с ними.
export interface SpendDay {
  date: string;
  spent_usd: number;
}

export interface SystemSpend {
  spent_usd: number;
  budget_usd: number;
  throttled: boolean;
  history: SpendDay[];
}

export interface Integration {
  key: string;
  label: string;
  connected: boolean;
  detail: string;
}

export interface DreamState {
  cron: string;
  last_run_at: string | null;
  last_run_id: string | null;
  last_cost_usd: number | null;
  has_brief: boolean;
  new_findings: number;
}

export interface AutopilotState {
  enabled: boolean;
  interval_min: number;
  max_runs_per_day: number;
  quiet_hours: [number, number];
  /** Откуда взято текущее состояние: нажатие кнопки или настройка .env */
  source?: 'кнопка' | '.env';
  /** Что мешает прогону прямо сейчас. null — ничего не мешает */
  blocked_by?: string | null;
}

// Пантеон: персона — это модель плюс характер, заданный промптом
export interface Persona {
  name: string;
  description: string;
  model: string;
  provider: string;
  system_prompt: string;
}

// Характер Hermes поверх любой персоны. Ползунки 0..10 превращаются в
// указания модели — их видно в поле prompt.
export interface Character {
  humor: number;
  warmth: number;
  verbosity: number;
  pace: number;
  address: 'ты' | 'вы' | 'сэр';
  language: 'auto' | 'ru' | 'en';
  prompt?: string;
}

export interface RuntimeInfo {
  version: string;
  api_url: string;
  data_dir: string;
  artifacts_dir: string;
  auth_file: string;
  scheduler_pid: number | null;
  daily_budget_usd: number;
  max_reply_tokens: number;
}

export interface SystemStatusResponse {
  spend: SystemSpend;
  integrations: Integration[];
  dream: DreamState;
  autopilot: AutopilotState;
  runtime: RuntimeInfo;
}

export interface WalletSummary {
  active_count: number;
  monthly_total_usd: number;
  // Деньги на предоплаченных счетах. unknown важен не меньше total: без него
  // «на счетах $1.98» читалось бы как полная картина, хотя это баланс одного
  // сервиса, а про остальные просто ничего не известно (23.08.2026).
  prepaid: { total: number; known: string[]; unknown: string[] };
  due_soon: Array<{ id: string; name: string; days_left: number; cost: number; cancel_url?: string }>;
  low_balance: Array<{ id: string; name: string; balance: number }>;
  unknown_charge_date?: string[];
}

// Ночной прогон Dream Cadence: находки и утренний бриф
export interface DreamFinding {
  finding_id: string;
  run_id: string;
  dimension: string;
  severity: 'low' | 'medium' | 'high';
  title: string;
  detail: string;
  action: Record<string, any> | null;
  status: 'new' | 'applied' | 'skipped';
  created_at: string;
  resolved_at: string | null;
}

export interface DreamBrief {
  run_id: string;
  brief: string;
  cost_usd: number;
  findings_count: number;
  created_at: string;
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

// Форма ответа бэкенда (backend/models/schemas.py), в отличие от GraphNode выше,
// который описывает демо-данные экрана Graph
export interface ApiGraphNode {
  id: string;
  label: string;
  node_type: string;
  metadata: Record<string, any>;
  created_at: string;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  node_types: Record<string, number>;
  connected_components: number;
}

export interface ApiGraphEdge {
  source: string;
  target: string;
  edge_type: string;
  weight: number;
  metadata: Record<string, any>;
}

// GET /api/graph/map — карта второго мозга целиком
export interface GraphMap {
  nodes: ApiGraphNode[];
  edges: ApiGraphEdge[];
  stats: GraphStats;
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

