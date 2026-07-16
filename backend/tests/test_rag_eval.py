import re

# LLM-as-judge prompts for RAG quality evaluation

CONTEXT_PRECISION_PROMPT = """
You are an expert judge evaluating RAG retrieval quality.
Given the QUESTION and the retrieved CONTEXT, output a score between 0.0 and 1.0 representing the precision of retrieval.
A score of 1.0 means ALL facts needed to answer the question are present in the context.
A score of 0.0 means NONE of the facts needed are present.

QUESTION: {question}
CONTEXT: {context}

Return your score in the exact format: SCORE: <value> (e.g. SCORE: 0.95).
Provide a one-sentence explanation.
"""

GROUNDEDNESS_PROMPT = """
You are an expert judge evaluating RAG response quality.
Analyze the provided CONTEXT and the generated ANSWER.
Determine if the ANSWER is fully grounded in (supported by) the CONTEXT without introducing any outside facts or hallucinations.
A score of 1.0 means the answer is 100% grounded in the context.
A score of 0.0 means the answer contains hallucinated or unsupported claims.

CONTEXT: {context}
ANSWER: {answer}

Return your score in the exact format: SCORE: <value> (e.g. SCORE: 1.0).
Provide a one-sentence explanation.
"""

def parse_judge_score(response_text: str) -> float:
    """Helper to parse SCORE: <val> from judge output."""
    match = re.search(r'SCORE:\s*([0-9\.]+)', response_text)
    if match:
        return float(match.group(1))
    return 0.0

def test_evaluation_prompt_generation():
    question = "What is the storage size limit for Free tier?"
    context = "Free tier profiles have a limit of 5 documents and 10MB of storage."
    answer = "The Free tier supports a maximum storage size of 10MB."

    # 1. Format Context Precision Prompt
    precision_prompt = CONTEXT_PRECISION_PROMPT.format(question=question, context=context)
    assert question in precision_prompt
    assert context in precision_prompt

    # 2. Format Groundedness Prompt
    groundedness_prompt = GROUNDEDNESS_PROMPT.format(context=context, answer=answer)
    assert context in groundedness_prompt
    assert answer in groundedness_prompt

def test_score_parser():
    # Test valid scores
    assert parse_judge_score("Explanation of RAG. SCORE: 0.95") == 0.95
    assert parse_judge_score("SCORE:1.0 is the grade.") == 1.0
    assert parse_judge_score("The score is SCORE: 0.40") == 0.4

    # Test fallback
    assert parse_judge_score("No score found here.") == 0.0

def test_mock_rag_quality_judge():
    # Simulated judge outputs
    mock_precision_reply = "The retrieved context contains all constraints. SCORE: 1.0"
    mock_groundedness_reply = "The answer directly matches the 10MB limit. SCORE: 1.0"

    precision_score = parse_judge_score(mock_precision_reply)
    groundedness_score = parse_judge_score(mock_groundedness_reply)

    assert precision_score == 1.0
    assert groundedness_score == 1.0

    # Check that average quality is excellent
    avg_quality = (precision_score + groundedness_score) / 2.0
    assert avg_quality >= 0.8
