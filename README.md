# Recipe Search App

Streamlit app to compare retrieval lanes (current / filtered / LLM-intent) against site-search **GET /search**, with an optional **GET /intent/preview** panel.

## Local setup

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd llm-intent-search-streamlit
```

### 2. Virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

Create a `.env` file in the repo root (gitignored). Example keys:

```
THUMBOR_KEY=""
ES_URL=""
ES_USERNAME=""
ES_PASSWORD=""
OPENAI_API_KEY=""

SITE_SEARCH_API_BASE_URL="http://localhost:8000"
SITE_SEARCH_API_PATH="/search"
SITE_SEARCH_ALGO_TYPE="MYRECIPES"
```

Optional: `SITE_SEARCH_INTENT_PREVIEW_PATH`, `SITE_SEARCH_API_TIMEOUT`, `SITE_SEARCH_API_AUTH_HEADER`, `SITE_SEARCH_STREAMLIT_USE_SEMANTIC`, `ES_INDEX`, etc. See [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) for a fuller list.

### 5. Run Streamlit

From the repo root (so [`.streamlit/config.toml`](.streamlit/config.toml) and `.env` load):

```bash
streamlit run app.py
```

Default in this repo is **port 8502** — open **http://localhost:8502**. To use **8501** instead: `streamlit run app.py --server.port=8501` or move/rename `.streamlit/config.toml`.

## CI / Docker (internal deploy)

- [`ci/manifest.json`](ci/manifest.json) — `packageRepository: "s3"` → multistage; **8502**, health **`/_stcore/health`**.
- [`ci/Dockerfile.multistage`](ci/Dockerfile.multistage) — `{{BASE_REGISTRY_URL}}/common/python:3.12.4`, stages `base` / `build` / `run` / `export`.
- Other: [`ci/Dockerfile.build`](ci/Dockerfile.build), [`ci/Dockerfile.run`](ci/Dockerfile.run), [`ci/Dockerfile.branch`](ci/Dockerfile.branch).

Local Docker builds need substituted `{{BASE_REGISTRY_URL}}` / `{{VERSION}}` (see internal docs); smoke builds often use `python:3.12.4-slim` as a stand-in base.

## Streamlit Community Cloud (optional)

Community Cloud deploys from **GitHub** only ([deploy docs](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)). This repo lives on **Bitbucket**, so pick one:

1. **Mirror** — create a GitHub repo (public or private), push or sync the same code, deploy that repo on Cloud.  
2. **One-off** — export/copy the project to GitHub when you need a Cloud demo.

### Secrets on Cloud

Cloud stores secrets in the UI ([secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)). Use **root-level** TOML keys so they appear as **environment variables** (this app uses `python-dotenv` + `os.getenv`).

Copy from [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example), replace placeholders, paste into **App settings → Secrets**. Never commit real secrets.

### Networking (critical)

Cloud runs on **Streamlit’s public hosts**. Your **site-search** and **Elasticsearch** URLs must be reachable from the **public internet** (or a host Cloud can reach). Typical internal-only `*.dotdash.com` / VPC endpoints **will not work** from Community Cloud unless you expose a **public** gateway or tunnel your org approves.

### Cloud app settings

- **Main file:** `app.py`  
- **Python version:** align with **3.12** if possible (matches internal `common/python:3.12.4` image).  
- **Branch:** your mirrored default branch.

## Deploy/runtime (ECS)

Provide the same variables as `.env` via the task definition or secrets manager. If users open the app via a real service URL, set **`STREAMLIT_BROWSER_SERVER_ADDRESS`** (see comments in [`.streamlit/config.toml`](.streamlit/config.toml)).
