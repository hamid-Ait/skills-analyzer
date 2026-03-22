import hashlib
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()

# In-memory cache for proxied images (simple, sufficient for this use case)
_cache: dict[str, tuple[bytes, str]] = {}
MAX_CACHE = 2000


@router.get("/image-proxy")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")):
    """Proxy external images (e.g. LinkedIn CDN) to avoid CORS/referrer issues."""
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Only HTTPS URLs are supported")

    cache_key = hashlib.md5(url.encode()).hexdigest()
    if cache_key in _cache:
        data, content_type = _cache[cache_key]
        return Response(content=data, media_type=content_type,
                        headers={"Cache-Control": "public, max-age=86400"})

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Referer": ""})
            resp.raise_for_status()
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch image")

    content_type = resp.headers.get("content-type", "image/jpeg")
    data = resp.content

    # Cache if within limit
    if len(_cache) < MAX_CACHE:
        _cache[cache_key] = (data, content_type)

    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"})