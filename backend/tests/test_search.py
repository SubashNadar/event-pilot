"""Retrieval: BM25, the semantic path (with a fake embedder) and reciprocal rank fusion."""

import pytest

from app.search import benchmarks, semantic, venues
from app.search.bm25 import BM25
from app.search.hybrid import rrf


def names(result):
    return [r["name"] for r in result["recommendations"]]


def test_bm25_prefers_rare_exact_terms():
    index = BM25(["banquet hall with parking", "rooftop with sea view", "banquet hall in Koramangala"])
    assert index.rank("Koramangala banquet") == [2, 0]
    assert index.rank("unrelated words") == []


def test_rrf_rewards_items_ranked_well_in_several_lists():
    fused = [item for item, _ in rrf([[1, 2, 3], [3, 1], [1]])]
    assert fused[0] == 1 and set(fused) == {1, 2, 3}


def test_city_aliases_and_area_matching():
    assert benchmarks.resolve_city("Bombay") == "Mumbai" and benchmarks.resolve_city("Gurgaon") == "Delhi NCR"
    assert names(venues.search("Navi Mumbai", 200, 1000000))[0] == "Vashi Grand Ballroom"
    assert names(venues.search("Koramangala, Bengaluru", 80, 500000))[0] == "Koramangala Workshop Studio"


def test_keyword_preferences_rank_matching_venues_first():
    assert names(venues.search("Bombay", 100, 600000, preferences="sea view sunset"))[0] == "Bandra Sea Breeze Terrace"
    assert names(venues.search("Goa", 150, 1200000, venue_type="beach resort"))[0] == "Candolim Beach Resort"


def test_near_misses_explain_empty_results():
    assert venues.search("Mumbai", 200, 300000)["near_misses"]["venue_share_needed_pct"] == 70
    assert venues.search("Mumbai", 2000, 5000000)["near_misses"]["reason"] == "too_small"
    assert venues.search("Coimbatore", 100, 500000)["near_misses"]["reason"] == "city_not_in_catalog"


CONCEPTS = [("sea", "beach", "coast", "seaside", "ocean", "shore"), ("garden", "lawn", "green", "outdoor"), ("palace", "heritage", "royal", "fort"), ("projector", "training", "workshop")]


def fake_embed(texts):
    """Tiny 'meaning' model: counts words per concept, so 'coast' ≈ 'beach'."""
    return [[sum(word.strip(".,") in group for word in text.lower().split()) + 0.01 for group in CONCEPTS] for text in texts]


@pytest.fixture()
def fake_embeddings(monkeypatch):
    semantic.reset_cache()
    monkeypatch.setattr(semantic, "EMBED_FACTORY", fake_embed)
    yield
    semantic.reset_cache()


def test_semantic_search_finds_meaning_that_keywords_miss(fake_embeddings):
    keyword_only = venues._index().rank("somewhere on the coast", [i for i, v in enumerate(venues.catalog()) if v["city"] == "Goa"])
    assert keyword_only == []  # no Goa description contains "somewhere" or "coast"
    result = venues.search("Goa", 120, 1200000, preferences="somewhere on the coast")
    assert result["search"]["mode"] == "hybrid"
    assert names(result)[0] in {"Candolim Beach Resort", "Calangute Shack Deck"}
    assert "close to what you described" in result["recommendations"][0]["match_reasons"]


def test_event_type_matching_and_budget_guidance():
    assert benchmarks.match_event_type("sangeet night")["label"] == "Wedding"
    assert benchmarks.match_event_type("hackathon for 100 devs")["label"] == "Workshop"
    assert benchmarks.match_event_type("xyz") is None
    wedding = benchmarks.type_by_label("Wedding")
    assert [o["label"] for o in benchmarks.budget_options(wedding, "Mumbai", 200)] == ["₹5L", "₹8L", "₹16L"]
    warning = benchmarks.budget_check(wedding, "Mumbai", 350, 250000)
    assert warning["id"] == "budget_low" and "₹714 a head" in warning["message"]
    assert benchmarks.budget_check(wedding, "Mumbai", 200, 800000) is None
