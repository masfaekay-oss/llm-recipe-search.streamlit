# Recipe Search App

Simple streamlit app to compare different retrieval methods.

### What it does

- **4 different retrieval methods**:
  - **Keyword**: Finds recipes with your exact words
  - **Semantic**: Finds recipes based on semantic meaning
  - **Hybrid**: Mixes both keyword and semantic search (based on scores)
  - **RRF**: Combines results from keyword and semantic results (based on rankings)

### Step 1: Clone the repository
```bash
cd semantic_search_streamlit
```

### Step 2: Virtual Environment
```bash
python -m venv venv
source venv/bin/activate
```

### Step 3: Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Set up your settings
Create `.env` file and add details

```
THUMBOR_KEY=""
ES_URL=""
ES_USERNAME=""
ES_PASSWORD=""
OPENAI_API_KEY=""
# Intent lane: in-app OpenAI only (bypass site-search HTTP API) — leave unset or force:
# SITE_SEARCH_INTENT_URL=""
# FORCE_LOCAL_INTENT=1
# Optional: intent HTTP uses {"term","algoType"} like internal APIs — set SITE_SEARCH_INTENT_USE_TERM=1
#
# Lane 3 — call Site Search GET /search (service runs LLM + ES; Streamlit hydrates cards from ES):
# SITE_SEARCH_API_BASE_URL="https://your-site-search-host"
# SITE_SEARCH_API_PATH="/search"
# SITE_SEARCH_ALGO_TYPE="MYRECIPES"
# SITE_SEARCH_API_AUTH_HEADER="Bearer ..."   # if required
# SITE_SEARCH_API_EXTRA_FILTERS=""         # optional: "cuisines:ITALIAN|totaltime:30MINUTESORLESS" (| = extra params)
# SITE_SEARCH_STREAMLIT_MATCH_SWAGGER_DEFAULTS=1   # Current/Filtered omit useIntent/useSemantic (API defaults true). Set 0 for legacy useIntent=false on those lanes.
```

### Start the app
```bash
streamlit run app.py
```

The app will open in your web browser at `http://localhost:8501`