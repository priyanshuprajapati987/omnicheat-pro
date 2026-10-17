"""Conversation Memory with Qdrant Vector DB (with in-memory fallback)"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue


@dataclass
class MemoryEntry:
    id: str
    session_id: str
    role: str
    content: str
    embedding: List[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ConversationMemory:
    """Vector-based conversation memory using Qdrant (with in-memory fallback)"""
    
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.collection_name = "conversations"
        self.client: Optional[QdrantClient] = None
        self._connected = False
        
        # In-memory fallback storage
        self._memory_store: Dict[str, List[MemoryEntry]] = {}
        self._max_entries_per_session = 100
        
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        try:
            self.client = QdrantClient(url=self.url, timeout=2)
            
            # Test connection
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=384,
                        distance=Distance.COSINE,
                    ),
                )
                print(f"[OK] Created Qdrant collection: {self.collection_name}")
            
            self._connected = True
            print(f"[OK] Qdrant connected: {self.url}")
        except Exception as e:
            print(f"[WARN] Qdrant not available: {type(e).__name__}")
            print("   Using in-memory fallback for conversation history")
            self.client = None
            self._connected = False
    
    async def add(
        self,
        session_id: str,
        role: str,
        content: str,
        embedding: List[float],
        metadata: dict = None,
    ) -> MemoryEntry:
        """Add a message to memory"""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
        )
        
        # Always store in in-memory fallback
        if session_id not in self._memory_store:
            self._memory_store[session_id] = []
        self._memory_store[session_id].append(entry)
        
        # Trim if too many entries
        if len(self._memory_store[session_id]) > self._max_entries_per_session:
            self._memory_store[session_id] = self._memory_store[session_id][-self._max_entries_per_session:]
        
        # Also try Qdrant if connected
        if self._connected and self.client:
            try:
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.collection_name,
                    points=[
                        PointStruct(
                            id=entry.id,
                            vector=entry.embedding,
                            payload={
                                "session_id": entry.session_id,
                                "role": entry.role,
                                "content": entry.content,
                                "metadata": entry.metadata,
                                "created_at": entry.created_at,
                            },
                        )
                    ],
                )
            except Exception as e:
                print(f"[WARN] Failed to save to Qdrant: {e}")
        
        return entry
    
    async def recall(
        self,
        session_id: str,
        query_embedding: List[float],
        limit: int = 5,
    ) -> List[MemoryEntry]:
        """Recall relevant messages from memory"""
        # Use in-memory fallback if Qdrant not connected
        if not self._connected or not self.client:
            entries = self._memory_store.get(session_id, [])
            return entries[-limit:] if entries else []
        
        try:
            results = await asyncio.to_thread(
                self.client.search,
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id",
                            match=MatchValue(value=session_id),
                        )
                    ]
                ),
                limit=limit,
            )

            if not results:
                entries = self._memory_store.get(session_id, [])
                return entries[-limit:] if entries else []

            return [
                MemoryEntry(
                    id=str(point.id),
                    session_id=point.payload.get("session_id", ""),
                    role=point.payload.get("role", ""),
                    content=point.payload.get("content", ""),
                    embedding=point.vector,
                    metadata=point.payload.get("metadata", {}),
                    created_at=point.payload.get("created_at", ""),
                )
                for point in results
            ]
        except Exception as e:
            print(f"[WARN] Failed to search Qdrant: {e}")
            # Fallback to in-memory
            entries = self._memory_store.get(session_id, [])
            return entries[-limit:] if entries else []
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """Get recent history for a session (always chronological, oldest -> newest)"""
        # Use in-memory fallback if Qdrant not connected
        if not self._connected or not self.client:
            entries = self._memory_store.get(session_id, [])
            return entries[-limit:] if entries else []
        
        try:
            results = await asyncio.to_thread(
                self.client.scroll,
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id",
                            match=MatchValue(value=session_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            
            points = results[0]
            entries = [
                MemoryEntry(
                    id=str(point.id),
                    session_id=point.payload.get("session_id", ""),
                    role=point.payload.get("role", ""),
                    content=point.payload.get("content", ""),
                    metadata=point.payload.get("metadata", {}),
                    created_at=point.payload.get("created_at", ""),
                )
                for point in points
            ]
            
            if not entries:
                mem_entries = self._memory_store.get(session_id, [])
                return mem_entries[-limit:] if mem_entries else []
            
            entries.sort(key=lambda x: x.created_at)
            return entries[-limit:]
        except Exception as e:
            print(f"[WARN] Failed to get history: {e}")
            entries = self._memory_store.get(session_id, [])
            return entries[-limit:] if entries else []
    
    async def clear_session(self, session_id: str):
        """Clear all memory for a session"""
        # Clear in-memory
        if session_id in self._memory_store:
            del self._memory_store[session_id]
        
        # Clear Qdrant if connected
        if self._connected and self.client:
            try:
                await asyncio.to_thread(
                    self.client.delete,
                    collection_name=self.collection_name,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchValue(value=session_id),
                            )
                        ]
                    ),
                )
            except Exception as e:
                print(f"[WARN] Failed to clear session: {e}")


# Simple embedding function (using a lightweight approach)
class SimpleEmbedder:
    """Simple embedding for demo - in production use sentence-transformers"""
    
    def __init__(self):
        self.dimension = 384
    
    async def embed(self, text: str) -> List[float]:
        """Generate a simple hash-based embedding"""
        import hashlib
        
        # Create deterministic embedding from text
        hash_bytes = hashlib.sha256(text.encode()).digest()
        
        # Expand to exactly 384 dimensions
        embedding = []
        for i in range(self.dimension):
            byte_val = hash_bytes[i % len(hash_bytes)]
            embedding.append((byte_val / 255.0) - 0.5)
        
        # Normalize
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        
        return embedding


# Singleton instances
_memory: Optional[ConversationMemory] = None
_embedder: Optional[SimpleEmbedder] = None


def get_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory


def get_embedder() -> SimpleEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = SimpleEmbedder()
    return _embedder
