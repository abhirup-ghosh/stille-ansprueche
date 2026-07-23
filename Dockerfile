FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the sentence-transformers models so the container starts offline-fast.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('intfloat/multilingual-e5-small'); CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')"

COPY src/ src/
COPY app/ app/

ENV APP_PORT=8501
EXPOSE 8501

CMD ["sh", "-c", "streamlit run app/app.py --server.port ${APP_PORT} --server.address 0.0.0.0"]
