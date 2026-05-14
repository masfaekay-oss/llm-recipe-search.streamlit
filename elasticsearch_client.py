from __future__ import annotations

from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import os
import time
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
load_dotenv()


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lstrip("\ufeff")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        v = v[1:-1]
    elif len(v) >= 2 and v[0] == v[-1] == "'":
        v = v[1:-1]
    return v.strip() or None


def _es_hosts():
    return _clean_env_value(os.getenv("ES_URL")) or _clean_env_value(os.getenv("ES_CLUSTER_URL"))


def _es_basic_auth():
    user = _clean_env_value(os.getenv("ES_USERNAME")) or _clean_env_value(os.getenv("ES_USER"))
    password = _clean_env_value(os.getenv("ES_PASSWORD"))
    if user is None and password is None:
        return None
    return (user or "", password or "")


class ElasticsearchClient:
    def __init__(self):
        hosts = _es_hosts()
        if not hosts:
            es_keys = sorted(k for k in os.environ if k.startswith("ES_"))
            hint = (
                " No ES_* variables in the environment."
                if not es_keys
                else f" Found: {', '.join(es_keys)} (check values are non-empty)."
            )
            raise ValueError(
                "Elasticsearch hosts missing. Set ES_URL or ES_CLUSTER_URL in `.env` or the environment."
                + hint
            )

        basic_auth = _es_basic_auth()
        kwargs = {}
        if basic_auth is not None:
            kwargs["basic_auth"] = basic_auth

        self.client = Elasticsearch(hosts, **kwargs)
        self.index = _clean_env_value(os.getenv("ES_INDEX")) or "myrecipes"
        # Filter field paths — override if your mapping uses different names
        self.field_cuisine = _clean_env_value(os.getenv("ES_FIELD_CUISINE")) or "cuisine.keyword"
        self.field_course = _clean_env_value(os.getenv("ES_FIELD_COURSE")) or "course.keyword"
        self.field_cook_time = _clean_env_value(os.getenv("ES_FIELD_COOK_TIME")) or "totalTimeMinutes"

    def get_document(self, doc_id: str):
        query = {
            "query": {
                "match": {
                    "_id": doc_id
                }
            }
        }
        response = self.client.search(index=self.index, body=query)
        # print(response)
        document = response['hits']['hits'][0]['_source']

        doc = {
            "bookmarkCount" : document['bookmarkCount'],
            "averageRating" : document['averageRating'],
        }

        return doc

    def keyword_search_query(self, search_term, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^10.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "AND",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 2
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^5.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "OR",
                                        "minimum_should_match": "1<75% 3<58%",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 5
                                    }
                                }
                            ],
                            "filter": [
                                {"term": {"templateType": "RECIPESC"}},
                                {
                                    "terms": {
                                        "brand": [
                                            "EATINGWELL",
                                            "REALSIMPLE",
                                            "FOODANDWINE",
                                            "BHG",
                                            "SOUTHERNLIVING",
                                            "ALLRECIPES",
                                            "FOOD",
                                            "SIMPLYRECIPES",
                                            "SERIOUSEATS",
                                        ]
                                    }
                                },
                            ],
                            "must_not": [{"term": {"hidden": True}}],
                            "minimum_should_match": "1<70%"
                        }
                    },
                    "boost_mode": "multiply",
                    "functions": [
                        {
                            "field_value_factor": {
                                "field": "averageRating.average",
                                "factor": 2,
                                "modifier": "sqrt",
                            }
                        },
                        {
                            "field_value_factor": {
                                "field": "averageRating.count",
                                "factor": 2,
                                "modifier": "ln1p",
                            }
                        },
                    ],
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
        }
    
    def keyword_search_query_no_boost(self, search_term, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^10.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "AND",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 2
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^5.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "OR",
                                        "minimum_should_match": "1<75% 3<58%",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 5
                                    }
                                }
                            ],
                            "filter": [
                                {"term": {"templateType": "RECIPESC"}},
                                {
                                    "terms": {
                                        "brand": [
                                            "EATINGWELL",
                                            "REALSIMPLE",
                                            "FOODANDWINE",
                                            "BHG",
                                            "SOUTHERNLIVING",
                                            "ALLRECIPES",
                                            "FOOD",
                                            "SIMPLYRECIPES",
                                            "SERIOUSEATS",
                                        ]
                                    }
                                },
                            ],
                            "must_not": [{"term": {"hidden": True}}],
                            "minimum_should_match": "1<70%"
                        }
                    },
            "sort": [{"_score": {"order": "desc"}}]
        }

    def _allowed_brands(self):
        return [
            "EATINGWELL",
            "REALSIMPLE",
            "FOODANDWINE",
            "BHG",
            "SOUTHERNLIVING",
            "ALLRECIPES",
            "FOOD",
            "SIMPLYRECIPES",
            "SERIOUSEATS",
        ]

    def _recipe_base_filter_clauses(self):
        """Same filter slice as keyword_search_query_no_boost (templateType + brands)."""
        return [
            {"term": {"templateType": "RECIPESC"}},
            {"terms": {"brand": self._allowed_brands()}},
        ]

    def _recipe_must_not_hidden(self):
        return [{"term": {"hidden": True}}]

    def _browse_query(self, size, extra_filter_clauses):
        """match_all + base recipe filters + optional facet filters (same _source/sort shape as keyword no-boost)."""
        filters = self._recipe_base_filter_clauses() + list(extra_filter_clauses)
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description",
            ],
            "from": 0,
            "size": size,
            "query": {
                "bool": {
                    "must": [{"match_all": {}}],
                    "filter": filters,
                    "must_not": self._recipe_must_not_hidden(),
                }
            },
            "sort": [{"_score": {"order": "desc"}}],
        }

    def filtered_search_query(self, cuisine, cook_time, course, size):
        """
        Manual filters only. Reuses templateType, brand allowlist, and hidden guard
        from keyword search. Adds term/range only for non-empty arguments.
        """
        extra = []
        if cuisine:
            extra.append({"term": {self.field_cuisine: cuisine}})
        if cook_time is not None:
            extra.append({"range": {self.field_cook_time: {"lte": int(cook_time)}}})
        if course:
            extra.append({"term": {self.field_course: course}})
        return self._browse_query(size, extra)

    def intent_to_es_query(self, intent, size):
        """
        intent: validated dict with keys cuisine, cook_time, course (any may be None).
        Reuses base filters; falls back to match_all-only must when no facet filters.
        """
        extra = []
        c = intent.get("cuisine") if intent else None
        t = intent.get("cook_time") if intent else None
        r = intent.get("course") if intent else None
        if c:
            extra.append({"term": {self.field_cuisine: c}})
        if t is not None:
            extra.append({"range": {self.field_cook_time: {"lte": int(t)}}})
        if r:
            extra.append({"term": {self.field_course: r}})
        return self._browse_query(size, extra)

    def semantic_search_query(self, embedding, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "knn": {
                    "field": "embedding",        
                    "query_vector": embedding,  
                    "k": size,                     
                    "num_candidates": 100
            }
        }
    }

    def hybrid_search_query(self, search_term, embedding, size, keyword_weight=1, semantic_weight=700):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^10.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "AND",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 2
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^5.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "OR",
                                        "minimum_should_match": "1<75% 3<58%",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 5
                                    }
                                }
                            ],
                            "filter": [
                                {"term": {"templateType": "RECIPESC"}},
                                {
                                    "terms": {
                                        "brand": [
                                            "EATINGWELL",
                                            "REALSIMPLE",
                                            "FOODANDWINE",
                                            "BHG",
                                            "SOUTHERNLIVING",
                                            "ALLRECIPES",
                                            "FOOD",
                                            "SIMPLYRECIPES",
                                            "SERIOUSEATS",
                                        ]
                                    }
                                },
                            ],
                            "must_not": [{"term": {"hidden": True}}],
                            "minimum_should_match": "1<70%"
                        }
                    },
                    "boost_mode": "multiply",
                    "functions": [
                        {
                            "field_value_factor": {
                                "field": "averageRating.average",
                                "factor": 2,
                                "modifier": "sqrt",
                            }
                        },
                        {
                            "field_value_factor": {
                                "field": "averageRating.count",
                                "factor": 2,
                                "modifier": "ln1p",
                            }
                        },
                    ],
                "boost": keyword_weight 
                }
            },
            "knn": {
                "field": "embedding",        
                "query_vector": embedding,  
                "k": 10,                     
                "num_candidates": 100,
                "boost": semantic_weight
            }
        }
    
    def hybrid_search_no_boost_query(self, search_term, embedding, size, keyword_weight=1, semantic_weight=700):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^10.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "AND",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 2
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": search_term,
                                        "fields": ["title^5.0", "description^1.0"],
                                        "type": "best_fields",
                                        "operator": "OR",
                                        "minimum_should_match": "1<75% 3<58%",
                                        "fuzziness": "AUTO",
                                        "prefix_length": 2,
                                        "max_expansions": 5
                                    }
                                }
                            ],
                            "filter": [
                                {"term": {"templateType": "RECIPESC"}},
                                {
                                    "terms": {
                                        "brand": [
                                            "EATINGWELL",
                                            "REALSIMPLE",
                                            "FOODANDWINE",
                                            "BHG",
                                            "SOUTHERNLIVING",
                                            "ALLRECIPES",
                                            "FOOD",
                                            "SIMPLYRECIPES",
                                            "SERIOUSEATS",
                                        ]
                                    }
                                },
                            ],
                            "must_not": [{"term": {"hidden": True}}],
                            "minimum_should_match": "1<70%"
                        }
                    },
                    "boost_mode": "multiply",
                    "functions": [
                    ],
                "boost": keyword_weight
                }
            },
            "knn": {
                "field": "embedding",        
                "query_vector": embedding,  
                "k": 10,                     
                "num_candidates": 100,
                "boost": semantic_weight
            }
        }

    def RRF_search_query(self):
        return 'Fuses results of Keyword and Semantic queries using Reciprocal Rank Fusion, scores are not considered, only rankings.'
    
    def semantic_search_query_with_rating_counts(self, embedding, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "knn": {
                            "field": "embedding",        
                            "query_vector": embedding,  
                            "k": size,                     
                            "num_candidates": 100
                        },
                    },
                    "boost_mode": "multiply",
                    "functions": [
                        {
                            "field_value_factor": {
                                "field": "averageRating.average",
                                "factor": 2,
                                "modifier": "sqrt",
                            }
                        },
                        {
                            "field_value_factor": {
                                "field": "averageRating.count",
                                "factor": 2,
                                "modifier": "ln1p",
                            }
                        },
                    ],
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
        }

    def semantic_search_query_with_bookmarks(self, embedding, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "knn": {
                            "field": "embedding",        
                            "query_vector": embedding,  
                            "k": size,                     
                            "num_candidates": 100
                        },
                    },
                    "boost_mode": "multiply",
                    "functions": [
                        {
                            "field_value_factor": {
                                "field": "bookmarkCount",
                                "factor": 5,
                                "modifier": "ln1p"
                            }
                        }
                    ]
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
        }

    def semantic_query_with_new_rating_count_boost(self, embedding, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "function_score": {
                    "query": {
                        "knn": {
                            "field": "embedding",        
                            "query_vector": embedding,  
                            "k": size,                     
                            "num_candidates": 100,
                            "boost": 1000
                        },
                    },
                    "functions": [
                        {
                            "filter": {
                                "range": {
                                    "averageRating.average": {
                                        "gt": 0
                                    }
                                }
                            },
                            "gauss": {
                                "averageRating.average": {
                                    "origin": 5,      
                                    "scale": 1.0,       
                                    "decay": 0.7
                                }
                            },
                            "weight": 2
                        },
                        {
                            "filter": {
                                "range": {
                                    "averageRating.count": {
                                        "gt": 0
                                    }
                                }
                            },
                            "gauss": {
                                "averageRating.count": {
                                    "origin": 20000,    
                                    "scale": 10000,
                                    "decay": 0.5
                                }
                            },
                            "weight": 25
                        }
                    ],
                    "score_mode": "sum",
                    "boost_mode": "sum",
                    "max_boost": 25
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
            
        }

    def semantic_query_with_dtax_and_synonyms(self, search_term, embedding, size):
        return {
            "_source": [
                "_id",
                "brand",
                "heading",
                "title",
                "description"
            ],
            "from": 0,
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {"match": {"synonyms": search_term}},
                        {"term": { "descriptiveTaxonomy": search_term }}, 
                        ],
                        "filter": [
                                {"term": {"templateType": "RECIPESC"}},
                                {
                                "terms": {
                                    "brand": [
                                        "EATINGWELL",
                                        "REALSIMPLE",
                                        "FOODANDWINE",
                                        "BHG",
                                        "SOUTHERNLIVING",
                                        "ALLRECIPES",
                                        "FOOD",
                                        "SIMPLYRECIPES",
                                        "SERIOUSEATS",
                                    ]
                                }
                                },
                            ],
                        "must_not": [{"term": {"hidden": True}}],
                        "minimum_should_match": "1<70%"
                        }
                    },
            "knn": {
                "field": "embedding",        
                "query_vector": embedding,
                "k": size,                     
                "num_candidates": 100
            }
        }

    def search(self, query, search_type="general"):
        time.sleep(0.3)
        self.client.indices.clear_cache(index=self.index)

        start_time = time.time()
        response = self.client.search(index=self.index, **query)
        end_time = time.time()
        
        search_latency = (end_time - start_time) * 1000  # Convert to milliseconds
        return response, search_latency

    def fetch_hits_by_doc_ids(self, doc_ids: list[str]) -> list[dict]:
        """
        Hydrate ``_source`` from this client's index for doc IDs returned by Site Search GET /search.
        Each item matches the shape of ``search()['hits']['hits']`` entries for ``decorate_and_display``.
        """
        ids = [str(x).strip() for x in doc_ids if str(x).strip()]
        if not ids:
            return []
        resp = self.client.mget(index=self.index, ids=ids)
        hits: list[dict] = []
        for doc in resp.get("docs", []):
            if not doc.get("found"):
                continue
            hits.append(
                {
                    "_index": doc.get("_index", self.index),
                    "_id": doc["_id"],
                    "_score": 1.0,
                    "_source": doc.get("_source") or {},
                }
            )
        return hits