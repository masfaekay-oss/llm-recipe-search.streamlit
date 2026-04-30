# Recipe Search App

Simple streamlit app to compare different retrieval methods.



### Step 1: Clone the repository
```bash
cd LLM-Intent-search-streamlit
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

SITE_SEARCH_API_BASE_URL="http://localhost:8000"
SITE_SEARCH_API_PATH="/search"
SITE_SEARCH_ALGO_TYPE="MYRECIPES"
```

### Start the app
```bash
streamlit run app.py
```

The app will open in your web browser at `http://localhost:8501`