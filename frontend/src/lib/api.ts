import axios from 'axios';
import type { ApiGraphNode, GraphStats } from '../types';

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

// --- Граф ---
export const getGraphNodes = (limit = 200) =>
  data<ApiGraphNode[]>(api.get('/graph/nodes', { params: { limit } }));
export const getGraphStats = () => data<GraphStats>(api.get('/graph/stats'));

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
