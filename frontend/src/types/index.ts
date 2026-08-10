export interface GraphNode {
  id: string
  label: string
  node_type: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface GraphEdge {
  source: string
  target: string
  edge_type: string
  weight: number
  metadata: Record<string, unknown>
}

export interface GraphStats {
  nodes: number
  edges: number
  node_types: Record<string, number>
  connected_components: number
}

export interface Document {
  id: string
  title: string
  content: string
  doc_type: string
  tags: string[]
  source: string | null
  graph_node_id: string | null
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  title: string
  description: string
  status: 'todo' | 'in_progress' | 'done' | 'blocked'
  priority: 'low' | 'medium' | 'high' | 'critical'
  assigned_agent: string | null
  tags: string[]
  created_at: string
  updated_at: string
}

export interface Agent {
  id: string
  name: string
  role: string
  description: string
  status: 'idle' | 'running' | 'error' | 'paused'
  model: string
  config: Record<string, unknown>
  last_run: string | null
  created_at: string
}

export type Screen = 'home' | 'graph' | 'documents' | 'tasks' | 'agents' | 'memory' | 'activity' | 'settings'
