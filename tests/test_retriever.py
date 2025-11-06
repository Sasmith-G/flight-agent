import pytest

from disruption_agent.rag import PolicyRetriever


def test_retrieves_eu261_for_delay_compensation(fare_rules_dir):
    retriever = PolicyRetriever(fare_rules_dir)
    passages = retriever.retrieve("delay 3 hours compensation", top_k=3)
    assert passages
    assert any("eu261" in p.source for p in passages)


def test_retrieves_rebooking_policy_for_cancellation(fare_rules_dir):
    retriever = PolicyRetriever(fare_rules_dir)
    passages = retriever.retrieve("cancellation re-routing refund", top_k=3)
    assert any("af_rebooking_policy" in p.source or "eu261" in p.source for p in passages)


def test_scores_are_ordered(fare_rules_dir):
    retriever = PolicyRetriever(fare_rules_dir)
    passages = retriever.retrieve("baggage checked allowance", top_k=3)
    scores = [p.score for p in passages]
    assert scores == sorted(scores, reverse=True)
    assert "baggage" in passages[0].source


def test_missing_directory_raises():
    with pytest.raises(FileNotFoundError):
        PolicyRetriever("does/not/exist")
