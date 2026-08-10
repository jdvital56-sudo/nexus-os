import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const analyticsApi = {
  getOverview: () => api.get('/analytics/overview'),
  getApiUsage: () => api.get('/analytics/api-usage'),
  getRoi: (period: string) => api.get(`/analytics/roi?period=${period}`),
};

export const dreamReviewApi = {
  getLatest: () => api.get('/dream-review/latest'),
  getHistory: () => api.get('/dream-review/history'),
  triggerReview: () => api.post('/dream-review/trigger'),
};

export const skillsApi = {
  getAll: () => api.get('/skills'),
  getById: (id: string) => api.get(`/skills/${id}`),
  create: (data: any) => api.post('/skills', data),
  update: (id: string, data: any) => api.put(`/skills/${id}`, data),
  delete: (id: string) => api.delete(`/skills/${id}`),
  autoGenerate: () => api.post('/skills/auto-generate'),
};

export const memoryApi = {
  getGraph: () => api.get('/memory/graph'),
  search: (query: string) => api.get(`/memory/search?q=${query}`),
  getNode: (id: string) => api.get(`/memory/nodes/${id}`),
};

export const agentsApi = {
  getAll: () => api.get('/agents'),
  getStatus: (id: string) => api.get(`/agents/${id}/status`),
  activate: (id: string) => api.post(`/agents/${id}/activate`),
  deactivate: (id: string) => api.post(`/agents/${id}/deactivate`),
};

export const systemApi = {
  getStatus: () => api.get('/system/status'),
  runSetupWizard: () => api.post('/system/setup-wizard'),
  checkConnections: () => api.get('/system/connections'),
};

export default api;
