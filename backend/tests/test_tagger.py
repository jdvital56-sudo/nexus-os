"""Auto-tagger tests."""
from backend.services.tagger import extract_keywords, generate_tags, create_document_graph_nodes


def test_extract_keywords():
    text = "Machine learning is a subset of artificial intelligence that enables systems to learn"
    kw = extract_keywords(text, max_keywords=5)
    assert len(kw) <= 5
    assert all(isinstance(k, str) for k in kw)
    assert "machine" in kw or "learning" in kw


def test_extract_keywords_russian():
    text = "Граф знаний это структура данных которая хранит связи между сущностями"
    kw = extract_keywords(text, max_keywords=5)
    assert len(kw) > 0
    assert "граф" in kw or "знаний" in kw


def test_generate_tags():
    content = "Обсудили коммерческое предложение для клиента. Бюджет 300-500к. Звонок был в понедельник."
    tags = generate_tags(content, title="КП для клиента X")
    assert len(tags) > 0
    assert len(tags) <= 15
    # Should detect "proposal" pattern
    assert any("предлож" in t or "коммерч" in t or "клиент" in t for t in tags)


def test_generate_tags_with_existing():
    tags = generate_tags("test content", title="Test", existing_tags=["custom-tag"])
    assert "custom-tag" in tags


def test_create_document_graph_nodes():
    node, edges = create_document_graph_nodes("doc1", "Test Doc", ["ai", "graph", "memory"])
    assert node.id == "doc:doc1"
    assert node.label == "Test Doc"
    assert node.node_type.value == "document"
    assert len(edges) == 3
    assert all(e.source == "doc:doc1" for e in edges)
    assert any(e.target == "concept:ai" for e in edges)


def test_create_document_graph_nodes_empty_tags():
    node, edges = create_document_graph_nodes("doc2", "No Tags", [])
    assert node.id == "doc:doc2"
    assert len(edges) == 0
