const BASE = '/api'

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || res.statusText)
  }
  return res.json()
}

// Health
export const getHealth = () => fetchJSON<{ status: string }>('/health')

// Graph
export const getGraphStats = () => fetchJSON<any>('/graph/stats')
export const getGraphNodes = (params?: Record<string, string>) => {
  const q = params ? '?' + new URLSearchParams(params).toString() : ''
  return fetchJSON<any[]>(`/graph/nodes${q}`)
}
export const getGraphNeighbors = (id: string, depth = 1) =>
  fetchJSON<any>(`/graph/neighbors/${id}?depth=${depth}`)
export const searchGraph = (q: string) => fetchJSON<any[]>(`/graph/search?q=${encodeURIComponent(q)}`)

// Documents
export const getDocuments = (params?: Record<string, string>) => {
  const q = params ? '?' + new URLSearchParams(params).toString() : ''
  return fetchJSON<any[]>(`/documents${q}`)
}
export const getDocument = (id: string) => fetchJSON<any>(`/documents/${id}`)
export const createDocument = (data: any) => fetchJSON<any>('/documents', { method: 'POST', body: JSON.stringify(data) })

// Tasks
export const getTasks = (params?: Record<string, string>) => {
  const q = params ? '?' + new URLSearchParams(params).toString() : ''
  return fetchJSON<any[]>(`/tasks${q}`)
}
export const createTask = (data: any) => fetchJSON<any>('/tasks', { method: 'POST', body: JSON.stringify(data) })

// Agents
export const getAgents = (params?: Record<string, string>) => {
  const q = params ? '?' + new URLSearchParams(params).toString() : ''
  return fetchJSON<any[]>(`/agents${q}`)
}
export const runAgent = (id: string, task: string) =>
  fetchJSON<any>(`/agents/${id}/run`, { method: 'POST', body: JSON.stringify({ task, context: {} }) })
