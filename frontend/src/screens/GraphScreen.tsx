import { useState, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useApi } from '../hooks/useApi';
import { memoryApi } from '../lib/api';
import type { GraphData, GraphNode } from '../types';

// Mock data for demo
const mockGraphData: GraphData = {
  nodes: [
    { id: '1', label: 'Memory Core', type: 'memory', size: 20, color: '#00DC82' },
    { id: '2', label: 'Workspaces', type: 'workspace', size: 15, color: '#7C3AED' },
    { id: '3', label: 'Project Alpha', type: 'file', size: 10, color: '#3B82F6' },
    { id: '4', label: 'Decision: Tech Stack', type: 'decision', size: 12, color: '#F59E0B' },
    { id: '5', label: 'Session #42', type: 'session', size: 8, color: '#EC4899' },
    { id: '6', label: 'Skill: Code Review', type: 'skill', size: 14, color: '#10B981' },
    { id: '7', label: 'Obsidian Vault', type: 'memory', size: 18, color: '#00DC82' },
    { id: '8', label: 'API Integration', type: 'file', size: 10, color: '#3B82F6' },
  ],
  links: [
    { source: '1', target: '2', weight: 3 },
    { source: '2', target: '3', weight: 2 },
    { source: '1', target: '4', weight: 2 },
    { source: '4', target: '5', weight: 1 },
    { source: '1', target: '6', weight: 3 },
    { source: '1', target: '7', weight: 2 },
    { source: '7', target: '8', weight: 1 },
    { source: '6', target: '3', weight: 2 },
  ],
};

export default function GraphScreen() {
  const [graphData, setGraphData] = useState<GraphData>(mockGraphData);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // In production, uncomment:
  // const { data, loading, error } = useApi<GraphData>(() => memoryApi.getGraph(), []);
  // if (data) setGraphData(data);

  const getNodeColor = (type: string) => {
    const colors: Record<string, string> = {
      memory: '#00DC82',
      workspace: '#7C3AED',
      file: '#3B82F6',
      decision: '#F59E0B',
      session: '#EC4899',
      skill: '#10B981',
    };
    return colors[type] || '#6B7280';
  };

  return (
    <div className="h-screen flex">
      {/* Graph Container */}
      <div className="flex-1 bg-dark">
        <ForceGraph2D
          graphData={graphData}
          nodeLabel="label"
          nodeColor={(node: any) => getNodeColor(node.type)}
          nodeAutoColorBy="type"
          linkColor={() => '#4B5563'}
          linkWidth={(link: any) => Math.sqrt(link.weight)}
          nodeVal={(node: any) => node.size * 2}
          backgroundColor="#0F172A"
          onNodeClick={(node: any) => setSelectedNode(node)}
          cooldownTicks={100}
        />
      </div>

      {/* Node Details Panel */}
      {selectedNode && (
        <div className="w-80 bg-darker border-l border-gray-800 p-6 overflow-y-auto">
          <button
            onClick={() => setSelectedNode(null)}
            className="text-gray-400 hover:text-white mb-4"
          >
            ← Back to Graph
          </button>
          
          <div className="mb-6">
            <div 
              className="w-4 h-4 rounded-full mb-2"
              style={{ backgroundColor: getNodeColor(selectedNode.type) }}
            />
            <h2 className="text-xl font-bold text-white">{selectedNode.label}</h2>
            <p className="text-sm text-gray-400 capitalize">{selectedNode.type}</p>
          </div>

          <div className="space-y-4">
            <div className="bg-dark p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Connections</h3>
              <p className="text-white">
                {graphData.links.filter(
                  (l) => l.source === selectedNode.id || l.target === selectedNode.id
                ).length} linked nodes
              </p>
            </div>

            <div className="bg-dark p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Metadata</h3>
              <div className="text-sm text-gray-300 space-y-2">
                <p>ID: {selectedNode.id}</p>
                <p>Size: {selectedNode.size}</p>
                <p>Type: {selectedNode.type}</p>
              </div>
            </div>

            <button className="w-full bg-primary text-darker font-medium py-2 px-4 rounded-lg hover:bg-primary/90 transition-colors">
              View Details
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
