# """
# LLM / site-search-service intent extraction for the NL search POC.

# Aligns with site-search-service ``llm_intent_parser`` / ``IntentService`` JSON shape:
# ``must_filters``, ``time_max_ms`` (milliseconds), ``classification``, etc.
# Maps that into the flat {cuisine, cook_time, minutes} shape used by ``intent_to_es_query``.
# """

# from __future__ import annotations

# import json
# import os
# import re
# from pathlib import Path
# from typing import Any

# import requests
# from dotenv import load_dotenv

# load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
# load_dotenv()

# # --- Free-text / LLM labels → ES token values (extend with your index) ---

# CUISINE_MAP: dict[str, str] = {
#     "italian": "ITALIAN",
#     "asian": "ASIAN",
#     "mexican": "MEXICAN",
#     "indian": "INDIAN",
#     "chinese": "CHINESE",
#     "thai": "THAI",
#     "japanese": "JAPANESE",
#     "french": "FRENCH",
#     "greek": "GREEK",
#     "british": "BRITISH",
#     "spanish": "SPANISH",
#     "german": "GERMAN",
#     "korean": "ASIAN",
#     "vietnamese": "ASIAN",
#     "mediterranean": "EUROPEAN",
# }

# COURSE_MAP: dict[str, str] = {
#     "dinner": "DINNER",
#     "breakfast": "BREAKFAST",
#     "lunch": "LUNCH",
#     "brunch": "BRUNCH",
#     "snack": "SNACK",
#     "dessert": "DESSERT",
#     "appetizer": "APPETIZER",
#     "supper": "DINNER",
# }

# # Substring → cuisine token (parity with site_search … llm_intent_parser fallbacks)
# _FALLBACK_CUISINE_SUBSTRINGS: tuple[tuple[str, str], ...] = (
#     ("asian", "ASIAN"),
#     ("italian", "ITALIAN"),
#     ("mexican", "MEXICAN"),
#     ("indian", "INDIAN"),
#     ("chinese", "CHINESE"),
#     ("thai", "THAI"),
#     ("japanese", "JAPANESE"),
#     ("french", "FRENCH"),
#     ("greek", "GREEK"),
#     ("british", "BRITISH"),
#     ("spanish", "SPANISH"),
#     ("german", "GERMAN"),
#     ("korean", "ASIAN"),
#     ("vietnamese", "ASIAN"),
#     ("mediterranean", "EUROPEAN"),
# )

# ALLOWED_CUISINE: set[str] = set(CUISINE_MAP.values())
# ALLOWED_COURSE: set[str] = set(COURSE_MAP.values())

# _TIME_CAP_UNDER_MINUTES_RE = re.compile(
#     r"(?:under|less\s+than|within|at\s+most|max\.?\s*)\s*(\d{1,4})\s*(?:min|minute|minutes)\b",
#     re.IGNORECASE,
# )
# _TIME_CAP_OR_LESS_RE = re.compile(
#     r"\b(\d{1,4})\s*(?:min|minute|minutes)\s+or\s+less\b",
#     re.IGNORECASE,
# )


# def _clean_str(v: Any) -> str | None:
#     if v is None:
#         return None
#     s = str(v).strip()
#     return s or None


# def _coerce_str_list(val: Any) -> list[str]:
#     if val is None:
#         return []
#     if isinstance(val, str):
#         s = val.strip()
#         return [s] if s else []
#     if isinstance(val, list):
#         return [str(x).strip() for x in val if str(x).strip()]
#     return []


# def _extract_time_cap_minutes_from_query(term: str) -> int | None:
#     """Same idea as site-search ``_extract_time_cap_ms_from_term`` but returns minutes."""
#     raw = (term or "").strip()
#     if not raw:
#         return None
#     caps: list[int] = []
#     for rx in (_TIME_CAP_UNDER_MINUTES_RE, _TIME_CAP_OR_LESS_RE):
#         for m in rx.finditer(raw):
#             try:
#                 mins = int(m.group(1))
#             except (TypeError, ValueError):
#                 continue
#             if 1 <= mins <= 24 * 60:
#                 caps.append(mins)
#     if not caps:
#         return None
#     return min(caps)


# def _unwrap_service_payload(data: dict[str, Any]) -> dict[str, Any]:
#     """HTTP APIs often wrap the intent object."""
#     for key in ("intent", "parsedIntent", "parsed_intent", "data", "body"):
#         v = data.get(key)
#         if isinstance(v, dict) and (
#             "must_filters" in v or "classification" in v or "time_max_ms" in v
#         ):
#             return v
#     return data


# def raw_intent_to_poc_filters(data: dict[str, Any], user_query: str) -> dict[str, Any]:
#     """
#     Map **site-search-style** LLM JSON (or service payload) into the flat dict
#     ``{ "cuisine", "cook_time", "course" }`` used by ``ElasticsearchClient.intent_to_es_query``.

#     Handles:
#     - Top-level ``time_max_ms`` (milliseconds) and ``time_max_minutes``
#     - ``must_filters.cuisines`` / ``must_filters.cuisine`` / legacy ``cuisine``
#     - ``must_filters.meal_type``, ``must_filters.courses``, ``descriptiveTaxonomy`` meal phrases
#     - Legacy POC shape: flat ``cuisine`` / ``cook_time`` / ``course`` keys
#     """
#     out: dict[str, Any] = {"cuisine": None, "cook_time": None, "course": None}
#     if not isinstance(data, dict):
#         return out

#     data = _unwrap_service_payload(data)
#     must = data.get("must_filters") if isinstance(data.get("must_filters"), dict) else {}

#     # --- cook_time (minutes) ---
#     ms = data.get("time_max_ms")
#     if ms is not None:
#         try:
#             m = int(ms) // 60_000
#             if 1 <= m <= 24 * 60:
#                 out["cook_time"] = m
#         except (TypeError, ValueError):
#             pass
#     tmm = data.get("time_max_minutes")
#     if tmm is None:
#         tmm = must.get("time_max_minutes")
#     if tmm is not None:
#         try:
#             n = int(tmm)
#             if 1 <= n <= 24 * 60:
#                 out["cook_time"] = n if out["cook_time"] is None else min(out["cook_time"], n)
#         except (TypeError, ValueError):
#             pass
#     if out["cook_time"] is None:
#         inferred = _extract_time_cap_minutes_from_query(user_query)
#         if inferred is not None:
#             out["cook_time"] = inferred

#     # --- cuisine ---
#     candidates: list[str] = []
#     candidates.extend(_coerce_str_list(must.get("cuisines")))
#     candidates.extend(_coerce_str_list(must.get("cuisine")))
#     candidates.extend(_coerce_str_list(data.get("cuisines")))
#     c0 = _clean_str(data.get("cuisine")) or _clean_str(must.get("cuisine"))
#     if c0:
#         candidates.append(c0)
#     for c in candidates:
#         u = str(c).strip().upper()
#         if u in ALLOWED_CUISINE:
#             out["cuisine"] = u
#             break
#         m = CUISINE_MAP.get(c.lower())
#         if m:
#             out["cuisine"] = m
#             break
#     if out["cuisine"] is None:
#         q = user_query.lower()
#         for needle, token in _FALLBACK_CUISINE_SUBSTRINGS:
#             if needle in q and token in ALLOWED_CUISINE:
#                 out["cuisine"] = token
#                 break

#     # --- course / meal ---
#     meal_sources: list[str] = []
#     meal_sources.extend(_coerce_str_list(must.get("courses")))
#     meal_sources.extend(_coerce_str_list(data.get("courses")))
#     for key in ("meal_type", "mealType"):
#         v = must.get(key) or data.get(key)
#         if isinstance(v, str) and v.strip():
#             meal_sources.append(v.strip())
#     dt = must.get("descriptiveTaxonomy")
#     if isinstance(dt, list):
#         meal_sources.extend(str(x) for x in dt)
#     elif isinstance(dt, str) and dt.strip():
#         meal_sources.append(dt)

#     for phrase in meal_sources:
#         pl = phrase.lower()
#         for word, token in COURSE_MAP.items():
#             if re.search(rf"\b{re.escape(word)}\b", pl):
#                 out["course"] = token
#                 break
#         if out["course"]:
#             break

#     if out["course"] and out["course"] not in ALLOWED_COURSE:
#         out["course"] = None

#     # --- legacy flat POC keys (override only if still empty) ---
#     if data.get("cook_time") is not None and out["cook_time"] is None:
#         try:
#             n = int(float(data["cook_time"]))
#             if 1 <= n <= 24 * 60:
#                 out["cook_time"] = n
#         except (TypeError, ValueError):
#             pass
#     if not out["cuisine"] and data.get("cuisine"):
#         tmp = validate_intent({"cuisine": data.get("cuisine"), "course": None, "cook_time": None})
#         out["cuisine"] = tmp.get("cuisine")
#     if not out["course"] and data.get("course"):
#         tmp = validate_intent({"cuisine": None, "course": data.get("course"), "cook_time": None})
#         out["course"] = tmp.get("course")

#     return out


# def validate_intent(raw: dict[str, Any] | None) -> dict[str, Any]:
#     """
#     Returns { "cuisine": str|None, "cook_time": int|None, "course": str|None }
#     with only index-safe values; invalid entries dropped.
#     """
#     out: dict[str, Any] = {"cuisine": None, "cook_time": None, "course": None}
#     if not raw or not isinstance(raw, dict):
#         return out

#     c = _clean_str(raw.get("cuisine"))
#     if c:
#         u = c.upper()
#         if u in ALLOWED_CUISINE:
#             out["cuisine"] = u
#         else:
#             m = CUISINE_MAP.get(c.lower())
#             if m:
#                 out["cuisine"] = m

#     r = _clean_str(raw.get("course"))
#     if r:
#         u = r.upper()
#         if u in ALLOWED_COURSE:
#             out["course"] = u
#         else:
#             m = COURSE_MAP.get(r.lower())
#             if m:
#                 out["course"] = m

#     ct = raw.get("cook_time")
#     if ct is not None and ct != "":
#         try:
#             n = int(float(ct))
#             if 1 <= n <= 24 * 60:
#                 out["cook_time"] = n
#         except (TypeError, ValueError):
#             pass

#     return out


# def _load_site_search_system_prompt() -> str:
#     """Reuse production ``_SYSTEM_PROMPT`` from sibling repo when present."""
#     repo_root = Path(__file__).resolve().parent.parent
#     p = (
#         repo_root
#         / "site-search-service"
#         / "site_search"
#         / "programs"
#         / "myrecipes"
#         / "search"
#         / "llm_intent_parser.py"
#     )
#     if not p.is_file():
#         return _FALLBACK_SITE_SEARCH_PROMPT
#     text = p.read_text(encoding="utf-8")
#     m = re.search(r'_SYSTEM_PROMPT = """(.*?)"""', text, re.DOTALL)
#     if not m:
#         return _FALLBACK_SITE_SEARCH_PROMPT
#     return m.group(1).strip()


# _FALLBACK_SITE_SEARCH_PROMPT = """You extract recipe search intent as JSON only.

# Return:
# - classification: one of "simple", "complex", "ambiguous"
# - refined_query: optional cleaned search string
# - must_filters: object with optional keys: text, descriptiveTaxonomy (array of lowercase strings),
#   cuisines (array of uppercase tokens like ITALIAN), cuisine (string), meal_type, courses,
#   time_max_minutes (integer minutes)
# - should_filters: optional object
# - time_max_ms: optional integer — maximum total recipe time in **milliseconds** (minutes × 60 × 1000)

# Return only a JSON object, no markdown."""


# def _parse_intent_site_search_service(query: str, algo_type: str | None = None) -> dict[str, Any]:
#     url = (os.getenv("SITE_SEARCH_INTENT_URL") or "").strip()
#     if not url:
#         raise RuntimeError("SITE_SEARCH_INTENT_URL is not set")
#     timeout = float(os.getenv("SITE_SEARCH_INTENT_TIMEOUT", "30"))
#     use_term = (os.getenv("SITE_SEARCH_INTENT_USE_TERM") or "").strip().lower() in (
#         "1",
#         "true",
#         "yes",
#     )
#     algo = (algo_type or os.getenv("SITE_SEARCH_INTENT_ALGO") or "MYRECIPES").strip()
#     payload: dict[str, Any] = (
#         {"term": query, "algoType": algo}
#         if use_term
#         else {"query": query}
#     )
#     headers: dict[str, str] = {"Content-Type": "application/json"}
#     auth = (os.getenv("SITE_SEARCH_INTENT_AUTH_HEADER") or os.getenv("SITE_SEARCH_API_AUTH_HEADER") or "").strip()
#     if auth:
#         headers["Authorization"] = auth
#     resp = requests.post(
#         url,
#         json=payload,
#         timeout=timeout,
#         headers=headers,
#     )
#     resp.raise_for_status()
#     data = resp.json()
#     if not isinstance(data, dict):
#         raise ValueError("Intent service returned non-object JSON")
#     return _unwrap_service_payload(data)


# def _parse_intent_openai(query: str) -> dict[str, Any]:
#     from openai import OpenAI

#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise RuntimeError("OPENAI_API_KEY is not set")
#     model = os.getenv("OPENAI_INTENT_MODEL") or os.getenv(
#         "OPENAI_MODEL", "gpt-4o-mini"
#     )
#     client = OpenAI(api_key=api_key)
#     system = _load_site_search_system_prompt()
#     completion = client.chat.completions.create(
#         model=model,
#         response_format={"type": "json_object"},
#         messages=[
#             {"role": "system", "content": system},
#             {"role": "user", "content": f'Query: """{query}"""\nReturn JSON intent.'},
#         ],
#     )
#     content = completion.choices[0].message.content or "{}"
#     return json.loads(content)


# def parse_intent(query: str, algo_type: str | None = None) -> dict[str, Any]:
#     """
#     Raw intent JSON (site-search shape when aligned, or service payload).

#     ``algo_type`` is sent to ``SITE_SEARCH_INTENT_URL`` when that env is set and
#     ``SITE_SEARCH_INTENT_USE_TERM`` is true (same idea as ``GET /search`` ``algoType``).

#     For ES POC filters, run ``raw_intent_to_poc_filters(parse_intent(q), q)``
#     then ``validate_intent(...)``.
#     """
#     q = (query or "").strip()
#     if not q:
#         return {}

#     force_local = (os.getenv("FORCE_LOCAL_INTENT") or "").strip().lower() in (
#         "1",
#         "true",
#         "yes",
#     )
#     service_url = (os.getenv("SITE_SEARCH_INTENT_URL") or "").strip()
#     if service_url and not force_local:
#         return _parse_intent_site_search_service(q, algo_type=algo_type)
#     return _parse_intent_openai(q)
