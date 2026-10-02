"""The index definition of ADR-0012 and the analysis chain of ADR-0011.
Changing anything here means bumping `MAPPING_VERSION`, which names a new
index and needs a reindex."""

import re

INDEX_ALIAS = "kith-chunks"
MAPPING_VERSION = 1
VECTOR_DIMENSION = 1024

_TEXT_ANALYZER = "kith_text"
_QUOTES_AND_DASHES_FILTER = "kith_quotes_and_dashes"
_ASCII_FOLDING_FILTER = "kith_ascii_folding"


def versioned_index_name(embedding_model_id: str) -> str:
    model_slug = re.sub(r"[^a-z0-9]+", "-", embedding_model_id.lower()).strip("-")
    return f"{INDEX_ALIAS}-{model_slug}-v{MAPPING_VERSION}"


def index_body() -> dict:
    return {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "analysis": {
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
                "filter": {
                    _ASCII_FOLDING_FILTER: {
                        "type": "asciifolding",
                        "preserve_original": True,
                    }
                },
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
            "dynamic": "strict",
            "_meta": {"mapping_version": MAPPING_VERSION},
            "properties": {
                "text": {"type": "text", "analyzer": _TEXT_ANALYZER},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIMENSION,
                    "space_type": "cosinesimil",
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 100, "m": 16},
                    },
                },
                "tenant_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "page_number": {"type": "integer"},
            },
        },
        "aliases": {INDEX_ALIAS: {}},
    }
