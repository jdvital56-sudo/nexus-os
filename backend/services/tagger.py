"""Auto-tagging service — extracts keywords and links documents to the knowledge graph."""
import re
import json
from collections import Counter
from ..models.schemas import GraphNode, GraphEdge, NodeType, EdgeType


# Common stop words to filter out
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "it", "as", "was", "are", "be", "has", "had", "have", "this",
    "that", "these", "those", "not", "no", "can", "will", "if", "so", "do", "does",
    "did", "than", "then", "just", "about", "also", "how", "what", "when", "where",
    "which", "who", "whom", "why", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "too", "very",
    # Russian stop words
    "и", "в", "на", "с", "к", "по", "для", "от", "из", "о", "что", "как", "это",
    "не", "но", "да", "нет", "то", "ты", "он", "она", "мы", "вы", "они", "его",
    "её", "их", "мой", "твой", "наш", "ваш", "свой", "кто", "где", "когда",
    "почему", "все", "каждый", "любой", "другой", "такой", "этот", "тот",
    "был", "была", "было", "были", "быть", "есть", "будет",
}


def extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """Extract top keywords from text using frequency analysis."""
    # Normalize
    text = text.lower()
    # Split into words (Latin + Cyrillic)
    words = re.findall(r'[a-zа-яё]{3,}', text)
    # Filter stop words
    words = [w for w in words if w not in STOP_WORDS]
    # Count and return top N
    counter = Counter(words)
    return [word for word, _ in counter.most_common(max_keywords)]


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract structured entities from text."""
    entities: dict[str, list[str]] = {
        "emails": list(set(re.findall(r'[\w.-]+@[\w.-]+\.\w+', text))),
        "urls": list(set(re.findall(r'https?://\S+', text))),
        "hashtags": list(set(re.findall(r'#(\w+)', text))),
        "mentions": list(set(re.findall(r'@(\w+)', text))),
        "numbers": list(set(re.findall(r'\b\d+(?:\.\d+)?\b', text)))[:5],
    }
    return {k: v for k, v in entities.items() if v}


def generate_tags(content: str, title: str = "", existing_tags: list[str] | None = None) -> list[str]:
    """Generate tags for a document from its content and title."""
    tags = set(existing_tags or [])

    # Keywords from title (weighted higher — add twice)
    if title:
        title_kw = extract_keywords(title, max_keywords=5)
        tags.update(title_kw)
        tags.update(title_kw)  # double weight

    # Keywords from content
    content_kw = extract_keywords(content, max_keywords=8)
    tags.update(content_kw)

    # Hashtags from content
    hashtags = re.findall(r'#(\w+)', content)
    tags.update(hashtags)

    # Detect content type heuristics
    content_lower = content.lower()
    if any(w in content_lower for w in ["meeting", "встреча", "звонок", "call", "minutes"]):
        tags.add("meeting")
    if any(w in content_lower for w in ["proposal", "кп", "коммерческое", "offer", "quote"]):
        tags.add("proposal")
    if any(w in content_lower for w in ["договор", "contract", "agreement", "соглашение"]):
        tags.add("contract")
    if any(w in content_lower for w in ["тз", "spec", "specification", "требования", "requirements"]):
        tags.add("specification")
    if any(w in content_lower for w in ["bug", "ошибка", "error", "fix", "исправление"]):
        tags.add("bugfix")
    if any(w in content_lower for w in ["идея", "idea", "концепт", "concept", "гипотеза", "hypothesis"]):
        tags.add("idea")

    # Clean up — only keep reasonable tags
    tags = {t for t in tags if len(t) >= 2 and len(t) <= 30}
    return sorted(tags)[:15]


def create_document_graph_nodes(doc_id: str, title: str, tags: list[str]) -> tuple[GraphNode, list[GraphEdge]]:
    """Create a graph node for a document and edges to concept nodes for its tags."""
    doc_node = GraphNode(
        id=f"doc:{doc_id}",
        label=title,
        node_type=NodeType.DOCUMENT,
        metadata={"doc_id": doc_id, "tags": tags},
    )

    edges = []
    for tag in tags[:8]:  # max 8 concept links
        concept_id = f"concept:{tag}"
        edges.append(GraphEdge(
            source=f"doc:{doc_id}",
            target=concept_id,
            edge_type=EdgeType.MENTIONS,
        ))

    return doc_node, edges


def create_concept_node(tag: str) -> GraphNode:
    """Create or update a concept node for a tag."""
    return GraphNode(
        id=f"concept:{tag}",
        label=tag,
        node_type=NodeType.CONCEPT,
        metadata={"source": "auto-tagger"},
    )


def find_related_documents(doc_id: str, tags: list[str], all_docs: list[dict]) -> list[GraphEdge]:
    """Find documents with overlapping tags and create edges."""
    edges = []
    tag_set = set(tags)
    for doc in all_docs:
        if doc["id"] == doc_id:
            continue
        doc_tags = set(doc.get("tags", []))
        overlap = tag_set & doc_tags
        if len(overlap) >= 2:  # at least 2 shared tags
            edges.append(GraphEdge(
                source=f"doc:{doc_id}",
                target=f"doc:{doc['id']}",
                edge_type=EdgeType.RELATED,
                weight=len(overlap) / max(len(tag_set), 1),
                metadata={"shared_tags": list(overlap)},
            ))
    return edges[:10]  # max 10 related docs
