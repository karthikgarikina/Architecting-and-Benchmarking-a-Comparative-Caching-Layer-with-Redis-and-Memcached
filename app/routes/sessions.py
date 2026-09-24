from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Dict, Any, Optional
from app.models import SessionData, SessionUpdate
from app.cache import get_cache_backend, get_backend_name
from app.cache.base import BaseCacheBackend

router = APIRouter(prefix="/session", tags=["Session"])

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Get session by ID.
    Redis: Uses HGETALL.
    Memcached: Deserializes JSON string.
    """
    response.headers["X-Cache-Backend"] = backend_name
    data = await cache.get_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"backend": backend_name, "session": data}

@router.post("/{session_id}")
async def create_or_set_session(
    session_id: str,
    session: SessionData,
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Store or replace session.
    Redis: Stores via HSET.
    Memcached: Serializes JSON string.
    """
    response.headers["X-Cache-Backend"] = backend_name
    data = session.model_dump()
    data["session_id"] = session_id
    await cache.set_session(session_id, data)
    return {"backend": backend_name, "status": "stored", "session_id": session_id}

@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    updates: Dict[str, Any],
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Partially update session fields (e.g. last_login).
    Redis: Updates fields individually using HSET.
    Memcached: Retrieves, re-serializes entire object, and sets back.
    """
    response.headers["X-Cache-Backend"] = backend_name
    for field, value in updates.items():
        await cache.update_session_field(session_id, field, value)
    
    updated_session = await cache.get_session(session_id)
    return {
        "backend": backend_name,
        "status": "updated",
        "session_id": session_id,
        "session": updated_session
    }
