"""Recuperación léxica BM25 sobre los fragmentos de un documento.

Se implementa sin dependencias externas: normaliza acentos, descarta palabras
vacías del español y aplica una normalización ligera de plurales.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .models import DocumentChunk

BM25_K1 = 1.5
BM25_B = 0.75

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun
    bajo bien cada como con contra cual cuales cuando cuanto de del desde
    donde dos el ella ellas ello ellos en entre era eran es esa esas ese eso
    esos esta estan estas este esto estos fue fueron ha hay hace la las le
    les lo los mas me mi mis mucho muy nada ni no nos o otra otras otro otros
    para pero poco por porque que quien quienes se sea segun ser si sin sobre
    solo son su sus tambien tan te tiene tienen todo todos tu tus un una unas
    uno unos y ya yo dice explica documento texto tengo
    """.split()
)

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class ScoredChunk:
    chunk: DocumentChunk
    score: float
    matched_terms: tuple[str, ...]


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in _WORD.findall(normalize(text)):
        if len(word) > 4 and word.endswith("s"):
            word = word[:-1]
        if len(word) < 3 or word in STOPWORDS:
            continue
        tokens.append(word)
    return tokens


def bm25_rank(chunks: list[DocumentChunk], question: str) -> list[ScoredChunk]:
    """Ordena los fragmentos por relevancia BM25; solo devuelve los que coinciden."""
    query_terms = list(dict.fromkeys(tokenize(question)))
    if not chunks or not query_terms:
        return []
    documents = [Counter(tokenize(chunk.content)) for chunk in chunks]
    lengths = [sum(counts.values()) for counts in documents]
    average_length = (sum(lengths) / len(lengths)) or 1
    total = len(chunks)
    idf = {}
    for term in query_terms:
        frequency = sum(1 for counts in documents if term in counts)
        idf[term] = math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    scored: list[ScoredChunk] = []
    for chunk, counts, length in zip(chunks, documents, lengths):
        score = 0.0
        matched = []
        for term in query_terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            matched.append(term)
            score += idf[term] * tf * (BM25_K1 + 1) / (
                tf + BM25_K1 * (1 - BM25_B + BM25_B * length / average_length)
            )
        if score > 0:
            scored.append(ScoredChunk(chunk, round(score, 3), tuple(matched)))
    return sorted(scored, key=lambda item: (-item.score, item.chunk.chunk_index))
