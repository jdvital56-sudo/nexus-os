import axios from 'axios';
import type {
  ApiGraphNode,
  DreamBrief,
  DreamFinding,
  GraphMap,
  GraphStats,
  AutopilotState,
  SystemStatusResponse,
  WalletSummary,
} from '../types';

// Бэкенд монтирует роутеры с префиксом /api и слушает 8420 (см. Makefile)
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8420/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Локальный bearer-токен из data/auth.json; без него бэкенд отвечает 401
const authToken = import.meta.env.VITE_API_TOKEN;
if (authToken) {
  api.defaults.headers.common.Authorization = `Bearer ${authToken}`;
}

const data = <T>(p: Promise<{ data: T }>): Promise<T> => p.then(r => r.data);

// --- Сводка системы (дашборд) ---
export const getSystemStatus = () =>
  data<SystemStatusResponse>(api.get('/system/status'));
export const getWalletSummary = () => data<WalletSummary>(api.get('/wallet/summary'));

// --- Скиллы ---
// Список отдаёт только число шагов, сами шаги — отдельным запросом
export const getSkills = () => data<any[]>(api.get('/skills'));
export const getSkill = (id: string) => data<any>(api.get(`/skills/${id}`));
export const runSkill = (id: string, params: Record<string, any> = {}) =>
  data<any>(api.post(`/skills/${id}/run`, { params }));
// Выключение — не удаление: контракт остаётся на диске, скилл просто
// перестаёт запускаться, пока его не вернут
export const setSkillEnabled = (id: string, enabled: boolean) =>
  data<{ id: string; enabled: boolean }>(api.post(`/skills/${id}/enabled`, { enabled }));

// --- Автопилот ---
// Нажатие сильнее .env: переменная — позиция по умолчанию при старте,
// кнопка — сегодняшнее решение
export const getAutopilot = () => data<AutopilotState>(api.get('/system/autopilot'));
export const setAutopilot = (enabled: boolean) =>
  data<AutopilotState>(api.post('/system/autopilot', { enabled }));

// --- База знаний ---
export const getNote = (name: string) =>
  data<{ title: string; path: string; content: string }>(
    api.get('/obsidian/note', { params: { name } }),
  );

// --- Ночной прогон ---
export const getDreamFindings = (status?: string) =>
  data<DreamFinding[]>(api.get('/dream/findings', { params: status ? { status } : {} }));
export const getDreamBrief = () => data<DreamBrief | null>(api.get('/dream/brief'));
export const applyFinding = (id: string) => data<DreamFinding>(api.post(`/dream/findings/${id}/apply`));
export const skipFinding = (id: string) => data<DreamFinding>(api.post(`/dream/findings/${id}/skip`));

// --- Граф ---
export const getGraphNodes = (limit = 200) =>
  data<ApiGraphNode[]>(api.get('/graph/nodes', { params: { limit } }));
export const getGraphStats = () => data<GraphStats>(api.get('/graph/stats'));
export const getGraphMap = (limit = 500) =>
  data<GraphMap>(api.get('/graph/map', { params: { limit } }));

// --- Агенты ---
export const getAgents = () => data<any[]>(api.get('/agents'));
export const runAgent = (id: string, task: string, context: Record<string, any> = {}) =>
  data<any>(api.post(`/agents/${id}/run`, { task, context }));

// --- Задачи ---
export const getTasks = () => data<any[]>(api.get('/tasks'));
export const createTask = (payload: Record<string, any>) =>
  data<any>(api.post('/tasks', payload));

// --- Документы ---
export const getDocuments = () => data<any[]>(api.get('/documents'));
export const createDocument = (payload: Record<string, any>) =>
  data<any>(api.post('/documents', payload));

// --- Память ---
export const getMemoryFacts = (params: Record<string, string> = {}) =>
  data<any[]>(api.get('/memory/facts', { params }));
export const getMemoryStats = () => data<any>(api.get('/memory/stats'));
export const addMemoryFact = (payload: Record<string, any>) =>
  data<any>(api.post('/memory/facts', payload));

// --- Контент-пайплайн ---
export const getPipelineStatus = () => data<any>(api.get('/pipeline/status'));
export const createContent = (payload: Record<string, any>) =>
  data<any>(api.post('/pipeline/content', payload));
export const advanceContent = (contentId: string, contentText = '') =>
  data<any>(api.post(`/pipeline/content/${contentId}/advance`, { content_text: contentText }));

// --- Скиллы ---
export const skillsApi = {
  getAll: () => api.get('/skills'),
  getById: (id: string) => api.get(`/skills/${id}`),
  run: (id: string, payload: Record<string, any> = {}) => api.post(`/skills/${id}/run`, payload),
};

export const memoryApi = {
  getFacts: (params: Record<string, string> = {}) => api.get('/memory/facts', { params }),
  getStats: () => api.get('/memory/stats'),
  recall: (query: string) => api.get('/memory/recall', { params: { q: query } }),
};

export const agentsApi = {
  getAll: () => api.get('/agents'),
  getById: (id: string) => api.get(`/agents/${id}`),
  run: (id: string, task: string) => api.post(`/agents/${id}/run`, { task, context: {} }),
};

export default api;
