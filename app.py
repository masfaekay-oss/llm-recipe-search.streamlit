"""
Natural Language search — **light POC** (demo only).

Three lanes: **Current** (no intent), **Filtered** (manual brands · cuisine · course / cook time),
**LLM intent** (``useIntent=true`` on site-search-service). Optional **intent panel** calls
**GET /intent/preview** on the same site-search host (off by default until that route exists; search lanes do not need it).
Lane failures are isolated.

Hydrates recipe titles from Elasticsearch when ``ES_URL`` is configured; otherwise shows doc ids.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
load_dotenv()

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.is_file() and _env_path.stat().st_size == 0:
    raise RuntimeError(
        f"`{_env_path}` is empty on disk. Save it, then restart Streamlit so env vars load."
    )

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _strip_surrounding_quotes(raw: str) -> str:
    """Docker ``--env-file`` and some editors keep literal ``\"`` around values; strip them."""
    s = raw.strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def _config_str(key: str, default: str = "") -> str:
    """``os.environ`` first, then Streamlit **Secrets** (Community Cloud / ``secrets.toml``), same key names."""
    raw = os.getenv(key)
    if raw is not None and str(raw).strip():
        return _strip_surrounding_quotes(str(raw)).strip()
    try:
        if key in st.secrets:
            val = st.secrets[key]
            if val is not None and str(val).strip():
                return _strip_surrounding_quotes(str(val)).strip()
    except Exception:
        pass
    return default


def _site_search_base_url() -> str:
    return _config_str("SITE_SEARCH_API_BASE_URL", "").rstrip("/")


def _search_path() -> str:
    p = _config_str("SITE_SEARCH_API_PATH", "/search")
    return p if p.startswith("/") else "/" + p


def _intent_preview_path() -> str:
    p = _config_str("SITE_SEARCH_INTENT_PREVIEW_PATH", "/intent/preview")
    return p if p.startswith("/") else "/" + p


def _normalize_algo_type(algo_type: str | None) -> str:
    """Strip Docker env-file quotes so we send ``MYRECIPES``, not ``\"MYRECIPES\"`` (``%22`` in query)."""
    raw = _strip_surrounding_quotes((algo_type or "MYRECIPES").strip())
    return raw if raw else "MYRECIPES"


# Two pick-lists for **Filtered** lane; merged into one ``brands:`` token (unique keys only).
BRAND_OPTIONS_PRIMARY: tuple[str, ...] = (
    "FOODANDWINE",
    "SERIOUSEATS",
    "MYRECIPES",
    "SIMPLYRECIPES",
    "EATINGWELL",
    "ALLRECIPES",
    "BHG",
)
BRAND_OPTIONS_EXTRA: tuple[str, ...] = (
    "REALSIMPLE",
    "SOUTHERNLIVING",
    "FOOD",
    "LIQUOR",
    "COOKINGLIGHT",
    "WOODENBOAT",
)


def build_manual_filters(
    cuisine: str,
    course: str,
    cook_time: str,
    brands_primary: list[str],
    brands_extra: list[str],
) -> list[str]:
    """Structured filters for **Filtered** lane. One ``brands:`` / ``cuisines:`` / … each."""
    parts: list[str] = []
    brand_tokens = sorted(
        {str(b).strip().upper() for b in (brands_primary or []) + (brands_extra or []) if str(b).strip()}
    )
    if brand_tokens:
        parts.append("brands:" + ",".join(brand_tokens))
    if cuisine and str(cuisine).strip():
        parts.append(f"cuisines:{str(cuisine).strip().upper()}")
    if course and str(course).strip():
        parts.append(f"courses:{str(course).strip().upper()}")
    if cook_time and str(cook_time).strip():
        parts.append(f"totaltime:{str(cook_time).strip().upper()}")
    return sorted(parts)


def _merge_unique_additional_filter_keys(parts: list[str]) -> list[str]:
    buckets: dict[str, set[str]] = {}
    key_display: dict[str, str] = {}
    for raw in parts:
        s = str(raw).strip()
        if ":" not in s:
            continue
        key, val = s.split(":", 1)
        nk = key.strip().casefold()
        if nk not in key_display:
            key_display[nk] = key.strip()
        for token in val.split(","):
            t = token.strip()
            if t:
                buckets.setdefault(nk, set()).add(t)
    return [f"{key_display[nk]}:{','.join(sorted(buckets[nk]))}" for nk in sorted(buckets.keys())]


def call_site_search(
    base_url: str,
    query: str,
    filters: list[str],
    use_intent: bool,
    use_semantic: bool,
    limit: int,
    offset: int,
    algo_type: str,
    allow_fuzzy: bool = False,
) -> dict[str, Any]:
    filters = _merge_unique_additional_filter_keys(list(filters))
    algo = _normalize_algo_type(algo_type)
    timeout = float(_config_str("SITE_SEARCH_API_TIMEOUT", "120") or "120")
    headers: dict[str, str] = {}
    auth = _strip_surrounding_quotes(_config_str("SITE_SEARCH_API_AUTH_HEADER", "")).strip()
    if auth:
        headers["Authorization"] = auth
    params_list: list[tuple[str, str]] = [
        ("term", query),
        ("limit", str(limit)),
        ("offset", str(offset)),
        ("algoType", algo),
        ("allowFuzzy", "false" if not allow_fuzzy else "true"),
        ("useIntent", str(use_intent).lower()),
        ("useSemantic", str(use_semantic).lower()),
    ]
    for f in filters:
        t = str(f).strip()
        if t:
            params_list.append(("additionalFilterQuery", t))
    url = f"{base_url.rstrip('/')}{_search_path()}"
    response = requests.get(url, params=params_list, headers=headers or None, timeout=timeout)
    response.raise_for_status()
    elapsed_ms = response.elapsed.total_seconds() * 1000.0
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Search API returned non-object JSON")
    return {
        "json": body,
        "latency_ms": elapsed_ms,
        "request_url": getattr(response, "url", None) or url,
    }


def call_intent_preview(
    base_url: str,
    query: str,
    algo_type: str,
    use_semantic: bool,
) -> dict[str, Any]:
    """
    **GET /intent/preview** — same MyRecipes intent orchestrator as search (service-side LLM + cache).
    """
    algo = _normalize_algo_type(algo_type)
    timeout = float(_config_str("SITE_SEARCH_API_TIMEOUT", "120") or "120")
    headers: dict[str, str] = {}
    auth = _strip_surrounding_quotes(_config_str("SITE_SEARCH_API_AUTH_HEADER", "")).strip()
    if auth:
        headers["Authorization"] = auth
    path = _intent_preview_path()
    url = f"{base_url.rstrip('/')}{path}"
    params = {
        "term": query,
        "algoType": algo,
        "useSemantic": str(use_semantic).lower(),
    }
    response = requests.get(url, params=params, headers=headers or None, timeout=timeout)
    response.raise_for_status()
    elapsed_ms = response.elapsed.total_seconds() * 1000.0
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Intent preview API returned non-object JSON")
    return {
        **body,
        "_latency_ms": elapsed_ms,
        "_request_url": getattr(response, "url", None) or url,
        "_source": "site_search_GET_intent_preview",
    }


def _doc_ids_from_search_json(payload: dict) -> list[str]:
    rows = payload.get("results") or []
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict) and row.get("doc_id"):
            out.append(str(row["doc_id"]))
    return out


def _intent_panel_from_site_search(
    base_url: str,
    query: str,
    algo_type: str,
    use_semantic: bool,
) -> dict[str, Any]:
    """**Intent panel only** — same host as ``GET /search``; search lanes do not depend on this."""
    try:
        return call_intent_preview(base_url, query, algo_type, use_semantic)
    except requests.HTTPError as e:
        detail = ""
        if e.response is not None:
            try:
                detail = e.response.text[:500]
            except Exception:
                detail = str(e.response.status_code)
        status = getattr(e.response, "status_code", None)
        if status == 404:
            logger.info("Intent preview not available (404); search lanes unaffected: %s", e)
        else:
            logger.warning("Intent preview HTTP error (%s): %s", status, e)
        return {
            "_error": str(e),
            "_http_status": status,
            "_body_preview": detail,
            "_note": "Intent panel only. Search uses GET /search and does not require /intent/preview.",
        }
    except Exception as e:
        logger.warning("Intent preview failed (search lanes unaffected): %s", e)
        return {
            "_error": str(e),
            "_note": "Intent panel only; search lanes are unchanged.",
        }


def _get_es_client():
    if "_es_ok" in st.session_state and st.session_state["_es_ok"] is False:
        return None
    if "_es_client" in st.session_state and st.session_state["_es_client"] is not None:
        return st.session_state["_es_client"]
    try:
        from elasticsearch_client import ElasticsearchClient

        c = ElasticsearchClient()
        st.session_state["_es_client"] = c
        st.session_state["_es_ok"] = True
        return c
    except Exception as e:
        logger.warning("Elasticsearch not available for hydrate: %s", e)
        st.session_state["_es_client"] = None
        st.session_state["_es_ok"] = False
        return None


def _render_recipe_lane(title: str, lane_result: dict[str, Any] | None, err: str | None) -> None:
    st.markdown(f"### {title}")
    if err:
        st.error(err)
        return
    if lane_result is None:
        st.warning("No result for this lane.")
        return
    j = lane_result["json"]
    st.caption(
        f"``total_results``={j.get('total_results')} · ``latency_ms``={lane_result['latency_ms']:.0f}"
    )
    ids = _doc_ids_from_search_json(j)
    if not ids:
        st.caption("(no doc ids in this page)")
        return
    es = _get_es_client()
    if es is None:
        st.caption("Set **ES_URL** / **ES_INDEX** to hydrate titles; showing doc ids.")
        for did in ids[:30]:
            st.code(did, language=None)
        return
    try:
        hits = es.fetch_hits_by_doc_ids(ids)
        for h in hits:
            src = h.get("_source") or {}
            label = src.get("heading") or src.get("title") or src.get("shortHeading") or h.get("_id")
            url = src.get("url") or "#"
            st.markdown(f"- [{label}]({url})")
    except Exception as e:
        st.warning(f"ES hydrate failed: {e}")
        for did in ids[:30]:
            st.code(did, language=None)


def _run_lane_safe(name: str, fn: Callable[[], dict[str, Any]]) -> tuple[str, dict[str, Any] | None, str | None]:
    try:
        return name, fn(), None
    except Exception as e:
        logger.exception("%s lane failed", name)
        return name, None, str(e)


def main() -> None:
    st.set_page_config(page_title="NL search light POC", layout="wide")
    st.title("Natural Language search light POC")

    base_url = _site_search_base_url()
    if not base_url:
        st.error(
            "**SITE_SEARCH_API_BASE_URL** is not set. "
            "Local: use a `.env` file or export the variable. "
            "Streamlit Community Cloud: **App settings → Secrets** and add the same key (see `.streamlit/secrets.toml.example`)."
        )
        st.stop()

    with st.sidebar:
        st.text_input("Site Search base URL", value=base_url, disabled=True)
        show_debug = st.checkbox("Show raw /search JSON (debug)", value=False)
        run_intent_panel = st.checkbox(
            "Run intent panel (GET /intent/preview — optional; off until that route exists on your host)",
            value=False,
        )

    use_semantic = st.checkbox(
        "useSemantic (all /search calls)",
        value=(_config_str("SITE_SEARCH_STREAMLIT_USE_SEMANTIC", "true") or "true").strip().lower()
        in ("1", "true", "yes"),
    )

    query = st.text_input(
        "Natural language query",
        value="quick Italian dinner under 30 minutes",
        key="nl_query",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        limit = st.number_input("limit", 1, 100, 12)
    with c2:
        offset = st.number_input("offset", 0, 10_000, 0)
    with c3:
        algo = st.text_input(
            "algoType",
            value=_normalize_algo_type(_config_str("SITE_SEARCH_ALGO_TYPE", "")),
        )
        algo = _normalize_algo_type(algo)

    st.markdown("##### Filtered lane — manual facets (brands · cuisine · course · cook time)")
    b1, b2 = st.columns(2)
    with b1:
        sel_brands_primary = st.multiselect(
            "Brands (primary list)",
            list(BRAND_OPTIONS_PRIMARY),
            default=[],
            key="fil_brands_primary",
        )
    with b2:
        sel_brands_extra = st.multiselect(
            "Brands (extra list)",
            list(BRAND_OPTIONS_EXTRA),
            default=[],
            key="fil_brands_extra",
            help="Merged with the primary list into a single ``brands:`` filter for the Filtered lane.",
        )
    f1, f2, f3 = st.columns(3)
    with f1:
        sel_cuisine = st.selectbox("Cuisine", ["", "ITALIAN", "MEXICAN", "ASIAN"], key="fil_cuisine")
    with f2:
        sel_course = st.selectbox("Course", ["", "DINNER", "LUNCH", "BREAKFAST"], key="fil_course")
    with f3:
        sel_time = st.selectbox(
            "Cook time (total time bucket)",
            ["", "30MINUTESORLESS", "15MINUTESORLESS", "1TO3HOURS"],
            key="fil_time",
        )

    run = st.button("Run all lanes", type="primary")

    if "poc" not in st.session_state:
        st.session_state.poc = {}

    if not run and not st.session_state.poc.get("ran"):
        st.stop()

    if run and (query or "").strip():
        q = query.strip()
        manual = build_manual_filters(
            sel_cuisine,
            sel_course,
            sel_time,
            sel_brands_primary,
            sel_brands_extra,
        )

        def current_fn() -> dict[str, Any]:
            return call_site_search(
                base_url, q, [], False, use_semantic, int(limit), int(offset), algo
            )

        def filtered_fn() -> dict[str, Any]:
            return call_site_search(
                base_url, q, manual, False, use_semantic, int(limit), int(offset), algo
            )

        def llm_fn() -> dict[str, Any]:
            return call_site_search(
                base_url, q, [], True, use_semantic, int(limit), int(offset), algo
            )

        def intent_panel_fn() -> dict[str, Any]:
            if not run_intent_panel:
                return {"_skipped": True}
            return _intent_panel_from_site_search(base_url, q, algo, use_semantic)

        futures = []
        max_workers = 4 if run_intent_panel else 3
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures.append(ex.submit(_run_lane_safe, "current", current_fn))
            futures.append(ex.submit(_run_lane_safe, "filtered", filtered_fn))
            futures.append(ex.submit(_run_lane_safe, "llm", llm_fn))
            if run_intent_panel:
                futures.append(ex.submit(_run_lane_safe, "intent_panel", intent_panel_fn))
            else:
                st.session_state.poc["intent_panel"] = {"_skipped": True}

        lane_err: dict[str, str | None] = {}
        for fut in as_completed(futures):
            name, val, err = fut.result()
            if name == "intent_panel":
                st.session_state.poc["intent_panel"] = (
                    val if val is not None else {"_error": err or "intent_panel failed"}
                )
                continue
            st.session_state.poc[name] = val
            lane_err[name] = err

        st.session_state.poc["lane_errors"] = lane_err
        st.session_state.poc["ran"] = True
        st.session_state.poc["last_query"] = q
        st.session_state.poc["manual_filters"] = manual

    elif run:
        st.warning("Enter a non-empty query.")
        st.stop()

    poc = st.session_state.poc
    if not poc.get("ran"):
        st.stop()

    st.markdown("---")
    st.subheader("Intent panel (parsed constraints — demo only)")
    st.caption(
        "Served by **GET /intent/preview** on your site-search host (same MyRecipes orchestrator as "
        "**GET /search** — Redis cache + LLM there, not in Streamlit). Override path with "
        "**SITE_SEARCH_INTENT_PREVIEW_PATH** if needed. **algoType** must be **MYRECIPES** for preview."
    )
    ip = poc.get("intent_panel")
    if isinstance(ip, dict) and ip.get("_skipped"):
        st.info("Intent panel skipped (checkbox off). **Search lanes still ran.**")
    elif isinstance(ip, dict) and ip.get("_error"):
        status = ip.get("_http_status")
        if status == 404:
            st.info(
                "**Intent preview** returned 404 (route not on this site-search build yet). "
                "**Recipe lanes below still used GET /search** — no intent-parser deploy required for those."
            )
        else:
            st.warning(ip.get("_error"))
        if ip.get("_body_preview") and status != 404:
            st.caption(ip.get("_body_preview"))
    elif isinstance(ip, dict):
        st.success("Intent preview returned data (GET /intent/preview).")
        st.json(ip)
    else:
        st.caption("No intent data.")

    st.markdown("---")
    st.subheader("Recipe results (three lanes)")
    lane_errors = poc.get("lane_errors") or {}
    c1, c2, c3 = st.columns(3)
    with c1:
        _render_recipe_lane(
            "Current search (keyword, no intent)",
            poc.get("current"),
            lane_errors.get("current"),
        )
    with c2:
        _render_recipe_lane(
            "Filtered search (manual facets)",
            poc.get("filtered"),
            lane_errors.get("filtered"),
        )
    with c3:
        _render_recipe_lane(
            "LLM intent search (intent inside site-search)",
            poc.get("llm"),
            lane_errors.get("llm"),
        )

    if show_debug:
        st.markdown("---")
        st.subheader("Raw /search JSON")
        d1, d2, d3 = st.columns(3)
        with d1:
            st.json(poc.get("current") or {})
        with d2:
            st.json(poc.get("filtered") or {})
        with d3:
            st.json(poc.get("llm") or {})


if __name__ == "__main__":
    main()
