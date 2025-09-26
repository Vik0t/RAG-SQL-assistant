from typing import List, Tuple
import re

from .schema_cache import schema_cache


BUSINESS_RULES = [
    "active statuses: new, in_progress",
    "completed status: done, closed",
    "employees see own tasks; managers see subordinates",
]


def tokenize(text: str) -> List[str]:
    return re.findall(r"[\w\-]+", text.lower())


def score(query_tokens: List[str], text: str) -> int:
    tokens = tokenize(text)
    token_set = set(tokens)
    return sum(1 for t in query_tokens if t in token_set)


def retrieve_snippets(user_question: str, k: int = 12) -> List[str]:
    if not schema_cache.tables:
        schema_cache.load()
    query_tokens = tokenize(user_question)
    corpus: List[Tuple[int, str]] = []
    for snippet in schema_cache.to_text_snippets():
        corpus.append((score(query_tokens, snippet), snippet))
    for rule in BUSINESS_RULES:
        corpus.append((score(query_tokens, rule), rule))
    corpus.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in corpus[:k]]
