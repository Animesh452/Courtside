"""
rag.py — On-demand RAG (Retrieval-Augmented Generation) pipeline.

When the user asks a deep question that the LLM can't answer from its training data
alone (e.g. "tell me about Ilia Topuria's fighting style"), this module:

1. Fetches relevant content from Wikipedia
2. Chunks the text into smaller pieces
3. Embeds the chunks using ChromaDB's built-in embeddings (runs locally)
4. Retrieves the most relevant chunks for the user's query
5. Returns them as context for the LLM to use in its answer
6. Discards everything — no persistent vector DB to maintain

This is the "on-demand" RAG pattern from the project reference doc:
"No static vector DB. Data is fetched at query time, used, and discarded."
"""

import requests
from bs4 import BeautifulSoup
import chromadb
import uuid


def fetch_wikipedia(query: str) -> str:
    """
    Search Wikipedia and fetch the content of the top result.
    Returns the article text, or an empty string if nothing found.
    """
    # Wikipedia requires a User-Agent header
    headers = {
        "User-Agent": "Courtside/1.0 (Sports Assistant; educational project)"
    }

    # Step 1: Search Wikipedia for the query
    search_url = "https://en.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "format": "json",
    }

    try:
        search_resp = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        search_resp.raise_for_status()
        search_data = search_resp.json()
        results = search_data.get("query", {}).get("search", [])

        if not results:
            return ""

        # Step 2: Get the full text of the top result
        title = results[0]["title"]
        content_params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": True,
            "format": "json",
        }

        content_resp = requests.get(search_url, params=content_params, headers=headers, timeout=10)
        content_resp.raise_for_status()
        content_data = content_resp.json()
        pages = content_data.get("query", {}).get("pages", {})

        for page in pages.values():
            text = page.get("extract", "")
            if text:
                return f"Source: Wikipedia — {title}\n\n{text}"

        return ""

    except Exception as e:
        print(f"[RAG] Wikipedia fetch failed: {type(e).__name__}: {e}")
        return ""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: The full text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: How many characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a sentence boundary
        if end < len(text):
            last_period = chunk.rfind(". ")
            if last_period > chunk_size * 0.5:
                end = start + last_period + 2
                chunk = text[start:end]

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if len(c) > 50]  # filter tiny fragments


def retrieve_relevant_chunks(query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    """
    Embed chunks and retrieve the most relevant ones for the query.
    
    Uses ChromaDB's in-memory client with built-in embeddings (all-MiniLM-L6-v2).
    Everything is created, queried, and discarded — no persistent storage.
    """
    if not chunks:
        return []

    # Create an ephemeral (in-memory) ChromaDB client — dies when function ends
    client = chromadb.EphemeralClient()

    # Create a collection with a unique name (so parallel calls don't collide)
    collection_name = f"rag_{uuid.uuid4().hex[:8]}"
    collection = client.create_collection(name=collection_name)

    # Add all chunks to the collection — ChromaDB handles embedding automatically
    collection.add(
        documents=chunks,
        ids=[f"chunk_{i}" for i in range(len(chunks))],
    )

    # Query for the most relevant chunks
    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, len(chunks)),
    )

    # Extract the matched documents
    relevant = results.get("documents", [[]])[0]

    return relevant


def on_demand_rag(query: str) -> str:
    """
    Full on-demand RAG pipeline:
    1. Fetch from Wikipedia
    2. Chunk the content
    3. Retrieve the most relevant chunks
    4. Return formatted context for the LLM
    
    Returns:
        A formatted text block with relevant context, or an error message.
    """
    # Step 1: Fetch
    raw_text = fetch_wikipedia(query)

    if not raw_text:
        return f"No relevant information found for '{query}'. I'll answer from my general knowledge."

    # Step 2: Chunk
    chunks = chunk_text(raw_text)

    if not chunks:
        return f"Found content but couldn't process it for '{query}'."

    # Step 3: Retrieve
    relevant_chunks = retrieve_relevant_chunks(query, chunks, top_k=5)

    if not relevant_chunks:
        return f"Found content but couldn't find relevant sections for '{query}'."

    # Step 4: Format for the LLM
    context = "\n\n---\n\n".join(relevant_chunks)

    return (
        f"=== Retrieved Context for: {query} ===\n"
        f"(Source: Wikipedia — retrieved and processed on-demand)\n\n"
        f"{context}\n\n"
        f"=== End of Retrieved Context ===\n"
        f"Use the above context to answer the user's question. "
        f"Cite the source as Wikipedia when relevant. "
        f"If the context doesn't fully answer the question, supplement with your general knowledge "
        f"but clearly note what comes from the retrieved data vs your own knowledge."
    )