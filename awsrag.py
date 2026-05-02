from flask import Flask, request, jsonify, render_template
import boto3
import json
import chromadb
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF for PDF reading
import os
import uuid

app = Flask(__name__)

# Setup
chroma_client = chromadb.Client()
collection = chroma_client.create_collection(name="my_docs")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

doc_counter = 0
uploaded_files = []

print("Upload a PDF to get started.")


def chunk_text(text, chunk_size=500, overlap=50):
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    global doc_counter, uploaded_files

    if "file" not in request.files:
        return jsonify({"success": False, "error": "no file provided"})

    file = request.files["file"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"success": False, "error": "only pdf files are supported"})

    os.makedirs("/tmp/rag_uploads", exist_ok=True)
    tmp_path = f"/tmp/rag_uploads/{uuid.uuid4().hex}.pdf"
    file.save(tmp_path)

    try:
        text = extract_text_from_pdf(tmp_path)
        if not text.strip():
            return jsonify({"success": False, "error": "could not extract text from pdf"})

        chunks = chunk_text(text)
        if not chunks:
            return jsonify({"success": False, "error": "pdf had no usable text"})

        chunk_embeddings = embedder.encode(chunks).tolist()
        chunk_ids = [f"doc_{doc_counter + i}" for i in range(len(chunks))]
        collection.add(
            documents=chunks,
            embeddings=chunk_embeddings,
            ids=chunk_ids,
        )
        doc_counter += len(chunks)

        if file.filename not in uploaded_files:
            uploaded_files.append(file.filename)

        return jsonify({
            "success": True,
            "chunks": len(chunks),
            "total_docs": doc_counter,
            "filename": file.filename,
            "files": uploaded_files,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        os.remove(tmp_path)


@app.route("/clear", methods=["POST"])
def clear():
    global doc_counter, uploaded_files, collection
    chroma_client.delete_collection(name="my_docs")
    collection = chroma_client.create_collection(name="my_docs")
    doc_counter = 0
    uploaded_files = []
    return jsonify({"success": True})


def strip_reasoning(text):
    """Remove <reasoning>...</reasoning> tags from model output."""
    import re
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)
    return cleaned.strip()


@app.route("/ask", methods=["POST"])
def ask_endpoint():
    question = request.json.get("question", "")

    query_embedding = embedder.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=3)
    context_docs = results["documents"][0]

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    context = "\n".join(f"- {doc}" for doc in context_docs)

    body = json.dumps({
        "messages": [
            {
                "role": "system",
                "content": """You are a document Q&A assistant. Follow these rules strictly:

                1. Answer ONLY based on the provided context. Never use outside knowledge.
                2. If the context does not contain enough information to answer, say: "I don't have enough information in the uploaded documents to answer this."
                3. If the question is vague (e.g. "summarize this", "what is this about"), provide a structured summary of the key topics found in the context.
                4. Be concise and direct. Use bullet points for complex answers.
                5. Do NOT include any reasoning, thinking, or internal monologue in your response. Only provide the final answer.
                6. Always cite which parts of the context support your answer."""
            },
            {
                "role": "user",
                "content": f"Context from uploaded documents:\n{context}\n\nQuestion: {question}"
            }
        ],
        "max_tokens": 800,
        "temperature": 0.3,
    })

    try:
        response = bedrock.invoke_model(
            modelId="openai.gpt-oss-20b-1:0",
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        answer = result["choices"][0]["message"]["content"]
        answer = strip_reasoning(answer)
    except Exception as e:
        answer = f"Error: {e}"

    return jsonify({"answer": answer, "sources": context_docs})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
