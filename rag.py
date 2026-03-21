"""
rag.py — On-demand RAG (Retrieval-Augmented Generation) pipeline.

When a deep question is asked, this module:
1. Fetches relevant content from Wikipedia
2. Chunks the text into smaller pieces
3. Scores chunks by keyword relevance (no embedding model needed)
4. Returns the most relevant chunks as context for the LLM

Uses simple keyword-based retrieval instead of vector embeddings.
This avoids the 80MB model download that was causing timeouts on Render.
The trade-off is slightly less semantic matching, but for Wikipedia article
chunks about a specific topic, keyword matching works well.
"""

import requests
import re
import uuid


def fetch_wikipedia(query: str) -> str:
    """
    Search Wikipedia and fetch the content of the top result.
    Returns the article text, or an empty string if nothing found.
    """
    headers = {
        "User-Agent": "Courtside/1.0 (Sports Assistant; educational project)"
    }

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
    """Split text into overlapping chunks."""
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

    return [c for c in chunks if len(c) > 50]


def _score_chunk(chunk: str, query: str) -> float:
    """
    Score a chunk's relevance to the query using keyword matching.
    Higher score = more relevant.
    """
    chunk_lower = chunk.lower()
    query_lower = query.lower()

    # Extract keywords from query (words with 3+ characters)
    keywords = [w for w in re.findall(r'\b\w+\b', query_lower) if len(w) >= 3]

    if not keywords:
        return 0.0

    score = 0.0
    for keyword in keywords:
        # Count occurrences of each keyword in the chunk
        count = chunk_lower.count(keyword)
        if count > 0:
            score += 1.0 + (count * 0.5)  # base score + bonus for frequency

    # Bonus: if the full query appears as a phrase
    if query_lower in chunk_lower:
        score += 3.0

    return score


def retrieve_relevant_chunks(query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    """
    Retrieve the most relevant chunks using keyword scoring.
    No embedding model needed — fast and lightweight.
    """
    if not chunks:
        return []

    # Score each chunk
    scored = [(chunk, _score_chunk(chunk, query)) for chunk in chunks]

    # Sort by score descending, filter out zero-score chunks
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Return top_k chunks
    return [c for c, s in scored[:top_k]]


def on_demand_rag(query: str) -> str:
    """
    Full on-demand RAG pipeline:
    1. Fetch from Wikipedia
    2. Chunk the content
    3. Retrieve the most relevant chunks
    4. Return formatted context for the LLM
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
        # Fall back to first few chunks if no keyword matches
        relevant_chunks = chunks[:5]

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