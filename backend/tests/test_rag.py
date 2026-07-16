import pytest
import uuid
import json
from unittest.mock import MagicMock
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService

def test_rrf_merging_math():
    # Mock Reciprocal Rank Fusion calculation
    # Formula: score = sum( 1 / (60 + rank) )
    vector_results = [{"chunk_id": "chunk_A"}, {"chunk_id": "chunk_B"}]
    bm25_results = [{"chunk_id": "chunk_B"}, {"chunk_id": "chunk_C"}]
    
    # Let's perform a mini RRF merge manually as in RetrievalService
    scores = {}
    
    # rank 1 for A, rank 2 for B in vector
    for rank, res in enumerate(vector_results, 1):
        cid = res["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (60.0 + rank)
        
    # rank 1 for B, rank 2 for C in bm25
    for rank, res in enumerate(bm25_results, 1):
        cid = res["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (60.0 + rank)
        
    # Chunk B matches in both, so it should rank first due to higher cumulative score
    # Score calculations:
    # A: 1 / 61 = 0.01639
    # B: (1 / 62) + (1 / 61) = 0.016129 + 0.01639 = 0.0325
    # C: 1 / 62 = 0.016129
    
    assert scores["chunk_B"] > scores["chunk_A"]
    assert scores["chunk_A"] > scores["chunk_C"]

def test_citation_extraction():
    citation_service = CitationService()
    
    # Setup mock chunks
    chunk_a = MagicMock()
    chunk_a.id = uuid.uuid4()
    chunk_a.page_number = 4
    chunk_a.section_title = "Introduction"
    
    chunk_b = MagicMock()
    chunk_b.id = uuid.uuid4()
    chunk_b.page_number = 12
    chunk_b.section_title = "Data Analysis"
    
    retrieved_results = [
        {"chunk": chunk_a, "rerank_score": 0.88},
        {"chunk": chunk_b, "rerank_score": 0.45},
    ]
    
    # LLM reply citing both sources
    response_text = "According to [Source 1], climate change is rising, while [Source 2] details local temperatures."
    
    citations = citation_service.extract_citations(
        response_text=response_text,
        retrieved_results=retrieved_results,
    )
    
    assert len(citations) == 2
    assert citations[0]["chunk_id"] == chunk_a.id
    assert citations[0]["page_number"] == 4
    assert citations[0]["section_title"] == "Introduction"
    assert citations[0]["confidence_score"] == 0.88
    
    assert citations[1]["chunk_id"] == chunk_b.id
    assert citations[1]["page_number"] == 12
    assert citations[1]["section_title"] == "Data Analysis"
    assert citations[1]["confidence_score"] == 0.45

def test_cache_payload_serialization():
    # Check that cache json serializes citation floats and UUIDs correctly
    chunk_uuid = uuid.uuid4()
    citations_data = [
        {
            "chunk_id": chunk_uuid,
            "page_number": 5,
            "section_title": "Summary",
            "confidence_score": 0.92,
        }
    ]
    
    # Prepare serializable dict
    serializable = []
    for c in citations_data:
        serializable.append({
            "chunk_id": str(c["chunk_id"]),
            "page_number": c["page_number"],
            "section_title": c["section_title"],
            "confidence_score": c["confidence_score"],
        })
        
    payload = {
        "reply": "Cached text",
        "citations": serializable,
    }
    
    json_str = json.dumps(payload)
    parsed = json.loads(json_str)
    
    assert parsed["reply"] == "Cached text"
    assert parsed["citations"][0]["chunk_id"] == str(chunk_uuid)
    assert parsed["citations"][0]["confidence_score"] == 0.92
