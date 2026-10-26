import pytest
from app.rag.retriever import retrieve, load_chunks
from app.rag.relevance import calculate_word_coverage, passes_relevance_gate


def test_chunk_model_metadata():
    chunks = load_chunks(force_reload=True)
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk["model"] == "CX-02"
        assert chunk["source_url"].startswith("https://")
        assert len(chunk["text"]) > 20


def test_retrieval_specs_accuracy():
    # Test print speed query
    res_speed = retrieve("How fast does the Citizen CX-02 print a 4x6 photo?", top_k=2)
    assert len(res_speed) > 0
    top_chunk = res_speed[0]
    assert "8.4" in top_chunk["text"] or "Speed" in top_chunk["section"]

    # Test weight / dimensions query
    res_dim = retrieve("What are the dimensions and weight of CX-02 in mm and kg?", top_k=2)
    assert len(res_dim) > 0
    top_chunk_dim = res_dim[0]
    assert "12.0 kg" in top_chunk_dim["text"] or "275 mm" in top_chunk_dim["text"]

    # Test ribbon rewind feature
    res_rewind = retrieve("Does it have ribbon rewind to prevent wasted ribbon?", top_k=2)
    assert len(res_rewind) > 0
    assert "rewind" in res_rewind[0]["text"].lower()


def test_relevance_gate_rejects_off_topic():
    # Query completely outside CX-02 specs
    res_alien = retrieve("What is the battery life of an iPhone 15 Pro Max?", top_k=2)
    assert len(res_alien) == 0

    res_weather = retrieve("What is the temperature in Dubai today?", top_k=2)
    assert len(res_weather) == 0


def test_word_coverage_calculation():
    query = "print speed for 4x6 photo in seconds"
    text_match = "## Print Speeds\n- 4 x 6 inch: 8.4 seconds in High Speed mode"
    coverage = calculate_word_coverage(query, text_match)
    assert coverage >= 0.50

    text_unrelated = "## Protective Carry Bag\nPadded nylon carrying bag with shoulder strap."
    cov_unrelated = calculate_word_coverage(query, text_unrelated)
    assert cov_unrelated < 0.35
