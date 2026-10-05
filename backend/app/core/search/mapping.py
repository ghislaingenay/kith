"""The index definition of ADR-0012 and the analysis chain of ADR-0011.
Changing anything here means bumping `MAPPING_VERSION`, which names a new
index and needs a reindex."""

import re

from core.embedding.provider import VECTOR_DIMENSION

INDEX_ALIAS = "kith-chunks"
MAPPING_VERSION = 2

_TEXT_ANALYZER = "kith_text"
_QUOTES_AND_DASHES_FILTER = "kith_quotes_and_dashes"
_ASCII_FOLDING_FILTER = "kith_ascii_folding"


def versioned_index_name(embedding_model_id: str) -> str:
    # Index names must be lowercase, so anything else becomes a hyphen.
    model_slug = re.sub(r"[^a-z0-9]+", "-", embedding_model_id.lower()).strip("-")
    return f"{INDEX_ALIAS}-{model_slug}-v{MAPPING_VERSION}"


def index_body() -> dict:
    """The body of the create-index request, in the order OpenSearch reads it:
    settings (how the index behaves), mappings (what a Chunk document looks
    like), aliases (the name the application uses)."""
    return {
        "settings": {
            "index": {
                # Turns on the k-nearest-neighbour search the `embedding`
                # field needs.
                "knn": True,
                # One shard holds a few thousand Chunks easily. Replicas need
                # a second node, so none in development (a deploy-time setting).
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            # How text becomes searchable tokens (ADR-0011). One chain, no
            # per-language fields and no stemmers. Applied in this order:
            # character filter, tokenizer, token filters.
            "analysis": {
                # Runs on the raw text first: curly quotes and en/em dashes
                # become their straight versions, so "client’s" and "client's"
                # produce the same token.
                "char_filter": {
                    _QUOTES_AND_DASHES_FILTER: {
                        "type": "mapping",
                        "mappings": [
                            "‘=>'",
                            "’=>'",
                            '“=>"',
                            '”=>"',
                            "–=>-",
                            "—=>-",
                        ],
                    }
                },
                # Runs on each token last: "résumé" also yields "resume".
                # `preserve_original` keeps "résumé" too, so a search with the
                # accents still matches exactly.
                "filter": {
                    _ASCII_FOLDING_FILTER: {
                        "type": "asciifolding",
                        "preserve_original": True,
                    }
                },
                # The chain itself: filter characters, split into words with
                # the standard tokenizer, lowercase, then fold accents. The
                # order matters: folding after lowercasing.
                "analyzer": {
                    _TEXT_ANALYZER: {
                        "type": "custom",
                        "char_filter": [_QUOTES_AND_DASHES_FILTER],
                        "tokenizer": "standard",
                        "filter": ["lowercase", _ASCII_FOLDING_FILTER],
                    }
                },
            },
        },
        "mappings": {
            # An unknown field is rejected instead of being added silently, so
            # a typo in a field name fails loudly. Adding a field means a new
            # mapping version.
            "dynamic": "strict",
            # Lets tooling see which mapping version an index was built with.
            "_meta": {"mapping_version": MAPPING_VERSION},
            "properties": {
                # The Chunk text, searched by keyword (BM25). It uses the
                # analyzer above both when indexed and when searched.
                "text": {"type": "text", "analyzer": _TEXT_ANALYZER},
                # The Chunk's vector, empty until the embedding phase. A
                # Chunk with no vector is still stored and keyword-searchable.
                "embedding": {
                    "type": "knn_vector",
                    # Voyage voyage-4-large's output size (ADR-0004).
                    "dimension": VECTOR_DIMENSION,
                    # Similarity is the angle between vectors; Voyage vectors
                    # are unit length, so this ranks the same as dot product
                    # and gives a score between 0 and 1.
                    "space_type": "cosinesimil",
                    # HNSW is the graph structure that finds near neighbours
                    # quickly; Faiss is the engine that runs it.
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        # `m`: links per node (more is more accurate and more
                        # memory). `ef_construction`: how many candidates are
                        # checked while building the graph. Both are the
                        # defaults, far more than a few thousand Chunks need.
                        "parameters": {"ef_construction": 100, "m": 16},
                    },
                },
                # Keyword fields are matched exactly and never analyzed:
                # filters, grouping and deleting by value.
                "tenant_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                # A number, so a Citation can be sorted and filtered by page.
                "page_number": {"type": "integer"},
                # The Chunk's position in its Document, to order hits.
                "ordinal": {"type": "integer"},
            },
        },
        # The index is created already behind the alias, so the application
        # never uses the versioned name.
        "aliases": {INDEX_ALIAS: {}},
    }
