import axios from 'axios';
import type {
  ApiGraphNode,
  DreamBrief,
  DreamFinding,
  GraphMap,
  GraphStats,
  AutopilotState,
  Character,
  Persona,
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

// --- Подписки ---
export const getServices = (status: string | null = 'active') =>
  data<any[]>(api.get('/wallet', { params: status ? { status } : { status: '' } }));
export const createService = (payload: Record<string, any>) =>
  data<any>(api.post('/wallet', payload));
export const updateService = (id: string, payload: Record<string, any>) =>
  data<any>(api.put(`/wallet/${id}`, payload));
export const cancelService = (id: string) => data<any>(api.post(`/wallet/${id}/cancelled`));
export const removeService = (id: string) => data<any>(api.delete(`/wallet/${id}`));

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

// --- Пантеон персон и характер ---
export const getPersonas = () => data<Persona[]>(api.get('/personas'));
export const updatePersona = (name: string, payload: Partial<Persona>) =>
  data<Persona>(api.put(`/personas/${encodeURIComponent(name)}`, payload));
export const getHermesPrompt = () =>
  data<{ system_prompt: string }>(api.get('/personas/system-prompt'));
export const setHermesPrompt = (system_prompt: string) =>
  data<{ system_prompt: string }>(api.put('/personas/system-prompt', { system_prompt }));
export const getCharacter = () => data<Character>(api.get('/personas/character'));
export const setCharacter = (payload: Partial<Character>) =>
  data<Character>(api.put('/personas/character', payload));

// --- Почта и календарь ---
// Отправки писем нет намеренно: система готовит черновик, отправляет человек
export const getGmailStatus = () =>
  data<{ configured: boolean; can_send: boolean; note: string }>(api.get('/gmail/status'));
export const getDrafts = (limit = 20) => data<any[]>(api.get('/gmail/drafts', { params: { limit } }));
export const createDraft = (payload: Record<string, any>) =>
  data<any>(api.post('/gmail/drafts', payload));
export const searchMail = (q: string) => data<any[]>(api.get('/gmail/search', { params: { q } }));

export const getCalendarStatus = () =>
  data<{ configured: boolean; instructions: string | null }>(api.get('/calendar/status'));
export const getCalendarEvents = (days = 7) =>
  data<{ count: number; events: any[] }>(api.get('/calendar/events', { params: { days } }));

// --- Голос ---
export const getVoiceStatus = () =>
  data<{ engine: string; enabled: boolean; ready: boolean; detail: string; voice: string; voices: Array<{ id: string; label: string; gender: string }> }>(
    api.get('/voice/status'),
  );
/** Озвучка приходит файлом — браузер играет его сам, без потоков. */
export const speak = (text: string, voice?: string) =>
  api.post('/voice/say', { text, voice }, { responseType: 'blob' }).then((r) => r.data as Blob);

// --- Веб-чат ---
// Тот же контур мышления, что у Телеграма, только другой канал
export const getChatHistory = () =>
  data<{ messages: Array<{ role: string; text: string; persona: string; at: string }> }>(
    api.get('/chat/history'),
  );
export const sendChatMessage = (text: string, persona?: string) =>
  data<{ reply: string; persona: string }>(api.post('/chat/message', { text, persona }));
export const resetChat = () => data<{ removed: number }>(api.post('/chat/reset'));

// --- Артефакты ---
// Система файлы не стирает: помечает и объясняет причину, стирает человек
export const getArtifacts = () => data<any[]>(api.get('/artifacts'));
export const getArtifact = (id: string) =>
  data<{ content: string }>(api.get(`/artifacts/${id}/content`));
export const requestArtifactDelete = (id: string, reason: string) =>
  data<any>(api.post(`/artifacts/${id}/request-delete`, { reason }));
export const cancelArtifactDelete = (id: string) =>
  data<any>(api.post(`/artifacts/${id}/cancel-delete`));
export const adoptArtifacts = () => data<{ adopted: any[] }>(api.post('/artifacts/adopt'));

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
