# ingest/query_demo.py
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "health_kb"
client = QdrantClient(url=QDRANT_URL)
embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def answer_query_gemini_ready(question, top_k=4):
    q_vec = embedder.encode(question).tolist()
    hits = client.search(collection_name=COLLECTION_NAME, query_vector=q_vec, limit=top_k)
    contexts = []
    for h in hits:
        txt = h.payload.get("text")
        src = h.payload.get("source")
        score = h.score
        contexts.append({"text": txt, "source": src, "score": score})
    # Build prompt for Gemini
    prompt = "You are a health assistant. Use only the following documents to answer the user's question. If the answer is not in the documents, say you don't know.\n\n"
    for i, c in enumerate(contexts):
        prompt += f"Document {i+1} (source={c['source']}, score={c['score']}):\n{c['text']}\n\n"
    prompt += f"Question: {question}\nAnswer concisely and clearly."
    return prompt, contexts

if __name__ == "__main__":
    q = "What are common dengue symptoms?"
    prompt, contexts = answer_query_gemini_ready(q)
    print("PROMPT -> send this to Gemini:\n")
    print(prompt[:4000])  # print first N chars
    # call Gemini generation API with prompt, then respond to user
