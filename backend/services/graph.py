"""Knowledge graph service — NetworkX-backed."""
import json
import uuid
import networkx as nx
from ..core.config import GRAPH_FILE, ensure_data_dir
from ..core.errors import NotFoundError
from ..models.schemas import GraphNode, GraphEdge, GraphStats, NodeType, EdgeType
from ..core.jsonio import read_json, write_json


def _load_graph() -> nx.DiGraph:
    ensure_data_dir()
    G = nx.DiGraph()
    if GRAPH_FILE.exists():
        data = read_json(GRAPH_FILE, {"nodes": [], "edges": []})
        for n in data.get("nodes", []):
            G.add_node(n["id"], **n)
        for e in data.get("edges", []):
            G.add_edge(e["source"], e["target"], **e)
    return G


def _save_graph(G: nx.DiGraph):
    ensure_data_dir()
    data = {
        "nodes": [dict(G.nodes[n]) for n in G.nodes],
        "edges": [dict(G.edges[e]) for e in G.edges],
    }
    write_json(GRAPH_FILE, data)


def get_stats() -> GraphStats:
    G = _load_graph()
    node_types: dict[str, int] = {}
    for n in G.nodes:
        nt = G.nodes[n].get("node_type", "unknown")
        node_types[nt] = node_types.get(nt, 0) + 1
    comps = nx.number_weakly_connected_components(G) if G.is_directed() else nx.number_connected_components(G)
    return GraphStats(nodes=G.number_of_nodes(), edges=G.number_of_edges(), node_types=node_types, connected_components=comps)


def list_nodes(node_type: str | None = None, label_contains: str | None = None, limit: int = 50) -> list[GraphNode]:
    G = _load_graph()
    nodes = []
    for n in G.nodes:
        data = G.nodes[n]
        if node_type and data.get("node_type") != node_type:
            continue
        if label_contains and label_contains.lower() not in data.get("label", "").lower():
            continue
        nodes.append(GraphNode(
            id=data.get("id", n),
            label=data.get("label", n),
            node_type=data.get("node_type", "concept"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
        ))
        if len(nodes) >= limit:
            break
    return nodes


def get_node(node_id: str) -> GraphNode:
    G = _load_graph()
    if node_id not in G:
        raise NotFoundError("Node", node_id)
    data = G.nodes[node_id]
    return GraphNode(
        id=data.get("id", node_id),
        label=data.get("label", node_id),
        node_type=data.get("node_type", "concept"),
        metadata=data.get("metadata", {}),
        created_at=data.get("created_at", ""),
    )


def add_node(node: GraphNode) -> GraphNode:
    G = _load_graph()
    if not node.id:
        node.id = str(uuid.uuid4())[:8]
    G.add_node(node.id, **node.model_dump())
    _save_graph(G)
    return node


def remove_node(node_id: str) -> bool:
    G = _load_graph()
    if node_id not in G:
        raise NotFoundError("Node", node_id)
    G.remove_node(node_id)
    _save_graph(G)
    return True


def add_edge(edge: GraphEdge) -> GraphEdge:
    G = _load_graph()
    if edge.source not in G:
        raise NotFoundError("Node (source)", edge.source)
    if edge.target not in G:
        raise NotFoundError("Node (target)", edge.target)
    G.add_edge(edge.source, edge.target, **edge.model_dump())
    _save_graph(G)
    return edge


def remove_edge(source: str, target: str) -> bool:
    G = _load_graph()
    if not G.has_edge(source, target):
        raise NotFoundError("Edge", f"{source} -> {target}")
    G.remove_edge(source, target)
    _save_graph(G)
    return True


def get_neighbors(node_id: str, depth: int = 1) -> dict:
    G = _load_graph()
    if node_id not in G:
        raise NotFoundError("Node", node_id)
    visited = set()
    frontier = {node_id}
    all_discovered = set()
    result_nodes = []
    result_edges = []
    for _ in range(depth):
        next_frontier = set()
        for n in frontier:
            if n in visited:
                continue
            visited.add(n)
            all_discovered.add(n)
            data = G.nodes[n]
            result_nodes.append({"id": n, "label": data.get("label", n), "node_type": data.get("node_type", "unknown")})
            for neighbor in set(G.successors(n)) | set(G.predecessors(n)):
                next_frontier.add(neighbor)
                all_discovered.add(neighbor)
                edge_data = G.edges[n, neighbor] if G.has_edge(n, neighbor) else G.edges[neighbor, n]
                result_edges.append({"source": n, "target": neighbor, "edge_type": edge_data.get("edge_type", "related")})
        frontier = next_frontier - visited
    # Add neighbor nodes that were discovered but not yet in result_nodes
    for n in all_discovered:
        if n not in visited:
            data = G.nodes[n]
            result_nodes.append({"id": n, "label": data.get("label", n), "node_type": data.get("node_type", "unknown")})
    return {"nodes": result_nodes, "edges": result_edges}


def search(query: str, limit: int = 20) -> list[GraphNode]:
    """Simple text search across node labels and metadata."""
    G = _load_graph()
    q = query.lower()
    results = []
    for n in G.nodes:
        data = G.nodes[n]
        label = data.get("label", "").lower()
        meta_str = json.dumps(data.get("metadata", {})).lower()
        if q in label or q in meta_str:
            results.append(GraphNode(
                id=data.get("id", n),
                label=data.get("label", n),
                node_type=data.get("node_type", "concept"),
                metadata=data.get("metadata", {}),
                created_at=data.get("created_at", ""),
            ))
            if len(results) >= limit:
                break
    return results
