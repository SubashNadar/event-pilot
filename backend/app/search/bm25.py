"""A small Okapi BM25 index.

BM25 scores a document by how many query words it contains, giving more weight
to rare words and less to very long documents. It is exact about words, which is
what venue names, area names and acronyms (RSVP, GST, AV) need, and it costs
nothing to run. The corpora here are small (tens of rows), so an in-memory index
is enough; for large corpora use a search engine or a Postgres BM25 extension.
"""

import math
import re
from collections import Counter

_STOP = {"a", "an", "and", "the", "of", "for", "in", "on", "at", "to", "with", "or", "is", "are", "by", "from", "near", "our", "we", "i", "my", "it", "this", "that", "be", "as", "into"}


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if raw in _STOP:
            continue
        # light stemming so "venues"/"venue" and "weddings"/"wedding" match
        if len(raw) > 4 and raw.endswith("ies"):
            raw = raw[:-3] + "y"
        elif len(raw) > 3 and raw.endswith("s") and not raw.endswith("ss"):
            raw = raw[:-1]
        tokens.append(raw)
    return tokens


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokenize(doc) for doc in documents]
        self.doc_freqs = [Counter(doc) for doc in self.docs]
        self.avg_len = (sum(len(doc) for doc in self.docs) / len(self.docs)) if self.docs else 0.0
        df: Counter = Counter()
        for doc in self.docs:
            df.update(set(doc))
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        results = []
        for freqs, doc in zip(self.doc_freqs, self.docs):
            score = 0.0
            length_norm = 1 - self.b + self.b * (len(doc) / self.avg_len if self.avg_len else 1)
            for term in terms:
                tf = freqs.get(term, 0)
                if tf:
                    score += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + self.k1 * length_norm)
            results.append(score)
        return results

    def rank(self, query: str, candidates: list[int] | None = None) -> list[int]:
        """Indices of documents with a positive score, best first."""
        scores = self.scores(query)
        pool = candidates if candidates is not None else list(range(len(scores)))
        return sorted((i for i in pool if scores[i] > 0), key=lambda i: -scores[i])
