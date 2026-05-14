FROM public.ecr.aws/docker/library/python:3.8-slim

WORKDIR /semantic_search_streamlit

COPY requirements.txt /semantic_search_streamlit/requirements.txt

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir -r requirements.txt

COPY . /semantic_search_streamlit

RUN python -c "import streamlit, elasticsearch, openai, requests, dotenv"
