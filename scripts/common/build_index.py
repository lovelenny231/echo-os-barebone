"""
ECHO OS Barebone: Index Building Utilities

Tools for building FAISS and Azure AI Search indexes.
"""

import os
import json
import pickle
from typing import List, Dict, Any, Optional
from pathlib import Path

import numpy as np

from .chunker import Chunk, chunk_text
from .embedder import embed_texts


def build_faiss_index(
    chunks: List[Chunk],
    output_dir: str,
    index_name: str = "index"
) -> Dict[str, Any]:
    """Build a FAISS index from chunks.

    Args:
        chunks: List of Chunk objects
        output_dir: Output directory
        index_name: Name for the index files

    Returns:
        Index metadata
    """
    try:
        import faiss
    except ImportError:
        raise ImportError("faiss-cpu package required. Install with: pip install faiss-cpu")

    if not chunks:
        raise ValueError("No chunks provided")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Building FAISS index with {len(chunks)} chunks...")

    # Extract texts and generate embeddings
    texts = [chunk.content for chunk in chunks]
    print(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = embed_texts(texts)

    # Convert to numpy array
    embeddings_array = np.array(embeddings, dtype=np.float32)
    dimension = embeddings_array.shape[1]

    print(f"Embedding dimension: {dimension}")

    # Build FAISS index
    index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity with normalized vectors)

    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings_array)

    # Add vectors to index
    index.add(embeddings_array)

    print(f"Index built with {index.ntotal} vectors")

    # Prepare metadata
    metadata = []
    for i, chunk in enumerate(chunks):
        metadata.append({
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "content": chunk.content,
            **chunk.metadata
        })

    # Save index
    index_path = output_path / f"{index_name}.faiss"
    faiss.write_index(index, str(index_path))
    print(f"Index saved to: {index_path}")

    # Save metadata
    metadata_path = output_path / f"{index_name}_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"Metadata saved to: {metadata_path}")

    # Save embeddings (for potential reuse)
    embeddings_path = output_path / f"{index_name}_embeddings.npy"
    np.save(embeddings_path, embeddings_array)
    print(f"Embeddings saved to: {embeddings_path}")

    return {
        "index_path": str(index_path),
        "metadata_path": str(metadata_path),
        "embeddings_path": str(embeddings_path),
        "vector_count": index.ntotal,
        "dimension": dimension,
        "chunk_count": len(chunks),
    }


def build_azure_index(
    chunks: List[Chunk],
    index_name: str,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    recreate: bool = False
) -> Dict[str, Any]:
    """Upload chunks to Azure AI Search.

    Args:
        chunks: List of Chunk objects
        index_name: Azure AI Search index name
        endpoint: Azure Search endpoint (defaults to AZURE_SEARCH_ENDPOINT)
        api_key: Azure Search API key (defaults to AZURE_SEARCH_API_KEY)
        recreate: Whether to recreate the index if it exists

    Returns:
        Upload results
    """
    try:
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.indexes.models import (
            SearchIndex,
            SearchField,
            SearchFieldDataType,
            VectorSearch,
            HnswAlgorithmConfiguration,
            VectorSearchProfile,
        )
        from azure.core.credentials import AzureKeyCredential
    except ImportError:
        raise ImportError("azure-search-documents package required")

    endpoint = endpoint or os.getenv("AZURE_SEARCH_ENDPOINT")
    api_key = api_key or os.getenv("AZURE_SEARCH_API_KEY")

    if not endpoint or not api_key:
        raise ValueError("Azure Search endpoint and API key required")

    credential = AzureKeyCredential(api_key)

    # Create or update index
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)

    if recreate:
        try:
            index_client.delete_index(index_name)
            print(f"Deleted existing index: {index_name}")
        except Exception:
            pass

    # Define index schema
    fields = [
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="source", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="chunk_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,
            vector_search_profile_name="default-profile"
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="default-algorithm"),
        ],
        profiles=[
            VectorSearchProfile(
                name="default-profile",
                algorithm_configuration_name="default-algorithm",
            ),
        ],
    )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
    )

    index_client.create_or_update_index(index)
    print(f"Index created/updated: {index_name}")

    # Generate embeddings
    print(f"Generating embeddings for {len(chunks)} chunks...")
    texts = [chunk.content for chunk in chunks]
    embeddings = embed_texts(texts)

    # Upload documents
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    documents = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        doc = {
            "id": chunk.chunk_id,
            "content": chunk.content,
            "source": chunk.source,
            "chunk_id": chunk.chunk_id,
            "embedding": embedding.tolist(),
        }
        documents.append(doc)

    # Upload in batches
    batch_size = 100
    uploaded = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        result = search_client.upload_documents(documents=batch)
        uploaded += len([r for r in result if r.succeeded])
        print(f"Uploaded {uploaded}/{len(documents)} documents")

    return {
        "index_name": index_name,
        "documents_uploaded": uploaded,
        "total_chunks": len(chunks),
    }


def load_faiss_index(index_path: str, metadata_path: str) -> tuple:
    """Load a FAISS index and metadata.

    Args:
        index_path: Path to .faiss file
        metadata_path: Path to metadata JSON file

    Returns:
        Tuple of (faiss_index, metadata_list)
    """
    try:
        import faiss
    except ImportError:
        raise ImportError("faiss-cpu package required")

    index = faiss.read_index(index_path)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


def search_faiss_index(
    index,
    metadata: List[Dict],
    query_embedding: np.ndarray,
    k: int = 5
) -> List[Dict[str, Any]]:
    """Search FAISS index.

    Args:
        index: FAISS index
        metadata: Metadata list
        query_embedding: Query embedding
        k: Number of results

    Returns:
        List of search results with scores
    """
    try:
        import faiss
    except ImportError:
        raise ImportError("faiss-cpu package required")

    # Normalize query for cosine similarity
    query_embedding = query_embedding.reshape(1, -1).astype(np.float32)
    faiss.normalize_L2(query_embedding)

    # Search
    scores, indices = index.search(query_embedding, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        result = {
            "score": float(score),
            **metadata[idx]
        }
        results.append(result)

    return results
