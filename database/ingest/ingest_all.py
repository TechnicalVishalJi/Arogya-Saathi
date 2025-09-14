# ingest/ingest_all.py
import os, json, time
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from pathlib import Path
from tqdm import tqdm
import pandas as pd  # NEW

from utils import clean_text, chunk_text

# CONFIG
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "health_kb"
EMB_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # multilingual small model
BATCH_SIZE = 256

# connect qdrant
client = QdrantClient(url=QDRANT_URL)

# init embedder
embedder = SentenceTransformer(EMB_MODEL_NAME)

def ensure_collection(dim):
    if COLLECTION_NAME not in [c.name for c in client.get_collections().collections]:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

def ingest_docs_from_folder(folder_path, source_name="local_docs"):
    """
    Process .docx, .pdf, .txt, and .csv files in a folder and upsert into Qdrant
    """
    points_buffer = []
    for p in Path(folder_path).rglob("*"):
        if p.suffix.lower() in [".docx", ".pdf", ".txt", ".csv"]:
            text = extract_text_from_file(p)
            text = clean_text(text)
            chunks = chunk_text(text, chunk_size=400, overlap=50)
            for c_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": source_name,
                    "path": str(p),
                    "doc_id": str(p.name),
                    "chunk_id": c_idx,
                }
                vect = embedder.encode(chunk).tolist()
                points_buffer.append(
                    PointStruct(
                        id=f"{p.name}__{c_idx}",
                        vector=vect,
                        payload={"text": chunk, **metadata}
                    )
                )
                if len(points_buffer) >= BATCH_SIZE:
                    client.upsert(collection_name=COLLECTION_NAME, points=points_buffer)
                    points_buffer = []
    if points_buffer:
        client.upsert(collection_name=COLLECTION_NAME, points=points_buffer)
    print("Ingested docs from folder:", folder_path)

def extract_text_from_file(path: Path):
    if path.suffix.lower() == ".docx":
        return extract_text_docx(path)
    elif path.suffix.lower() == ".pdf":
        return extract_text_pdf(path)
    elif path.suffix.lower() == ".txt":
        return path.read_text(encoding='utf-8')
    elif path.suffix.lower() == ".csv":
        return extract_text_csv(path)
    else:
        return ""

def extract_text_docx(path: Path):
    from docx import Document
    doc = Document(str(path))
    return "\n".join([para.text for para in doc.paragraphs])

def extract_text_pdf(path: Path):
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    return "\n".join([page.get_text("text") for page in doc])

def extract_text_csv(path: Path):
    """
    Reads CSV into DataFrame and returns rows as text.
    You can customize to select only certain columns if needed.
    """
    try:
        df = pd.read_csv(path)
        texts = []
        for i, row in df.iterrows():
            row_text = ", ".join([f"{col}: {val}" for col, val in row.items()])
            texts.append(row_text)
        return "\n".join(texts)
    except Exception as e:
        print(f"CSV extraction failed for {path}: {e}")
        return ""

def ingest_api_json_items(items, source_name="api_source", id_prefix="api"):
    points = []
    for i, item in enumerate(items):
        text = item.get("text") or json.dumps(item)
        text = clean_text(text)
        chunks = chunk_text(text, chunk_size=400, overlap=50)
        for ci, chunk in enumerate(chunks):
            payload = {"source": source_name, "doc_id": f"{source_name}_{i}", "chunk_id": ci, **item.get("meta", {})}
            vect = embedder.encode(chunk).tolist()
            points.append(
                PointStruct(
                    id=f"{source_name}_{i}__{ci}",
                    vector=vect,
                    payload={"text": chunk, **payload}
                )
            )
            if len(points) >= BATCH_SIZE:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                points = []
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

import requests
def fetch_cowin_district_sessions(district_id, date):
    url = f"https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict?district_id={district_id}&date={date}"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    items = []
    for center in data.get("centers", []):
        text = f"Center: {center.get('name')}, address: {center.get('address')}. Sessions:"
        for s in center.get("sessions", []):
            text += f" Date {s.get('date')}, vaccine {s.get('vaccine')}, min_age {s.get('min_age_limit')}, available {s.get('available_capacity')}. "
        items.append({"text": text, "meta": {"center_id": center.get("center_id"), "district_id": district_id}})
    return items

if __name__ == "__main__":
    # 0) ensure Qdrant collection set up with correct dim
    sample = embedder.encode("sample text")
    dim = len(sample)
    ensure_collection(dim)

    # 1) ingest local docs folder
    docs_folder = "../data/docs"   # put your .pdf/.docx/.txt/.csv files here
    ingest_docs_from_folder(docs_folder, source_name="local_docs")

    # 2) ingest CoWIN example
    try:
        cowin_items = fetch_cowin_district_sessions(district_id=395, date="10-09-2025")
        ingest_api_json_items(cowin_items, source_name="cowin")
    except Exception as e:
        print("CoWIN fetch failed:", e)

    print("Ingestion complete")
