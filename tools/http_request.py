
# tools/http_request.py
# Purpose: Async HTTP client tool (GET, POST, OPTIONS, HEAD) for APIs, headers, or raw source.
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional, Literal, Union
from pydantic import BaseModel, AnyUrl, Field, validator
from tool_registry import tool
import aiohttp

DEFAULT_TIMEOUT = 30
UA = "v-axion-ai/1.0 (+https://vontainment.com)"

class HTTPInput(BaseModel):
    action: Literal["headers", "request", "source"] = Field(..., description="Which operation to perform")
    method: Literal["GET", "POST", "OPTIONS", "HEAD"] = Field("GET", description="HTTP method for 'request'")
    url: AnyUrl = Field(..., description="Target URL (http or https)")
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Union[str, int, float]]] = None
    json: Optional[Any] = None
    data: Optional[Union[str, bytes]] = None
    timeout: float = Field(DEFAULT_TIMEOUT, ge=1, le=120)
    allow_redirects: bool = True

    @validator("method")
    def _normalize_method(cls, v: str) -> str:
        return v.upper()

async def _to_text(resp: aiohttp.ClientResponse) -> str:
    try:
        return await resp.text()
    except UnicodeDecodeError:
        b = await resp.read()
        return b.decode("latin-1", errors="replace")

def _slim_headers(h) -> Dict[str, str]:
    return {k: v for k, v in h.items()}

async def _do_request(session: aiohttp.ClientSession, inp: HTTPInput) -> aiohttp.ClientResponse:
    kwargs: Dict[str, Any] = {
        "headers": inp.headers or {},
        "params": inp.params or {},
        "allow_redirects": inp.allow_redirects,
    }
    if inp.json is not None:
        kwargs["json"] = inp.json
    elif inp.data is not None:
        kwargs["data"] = inp.data
    return await session.request(inp.method, str(inp.url), **kwargs)

@tool(
    name="http_request",
    model=HTTPInput,
    description="HTTP client tool (GET, POST, OPTIONS, HEAD). Supports headers, API requests, or page source.",
    instructions=(
        "action='headers' -> returns response headers.\n"
        "action='request' -> API call with status, headers, and JSON/text.\n"
        "action='source'  -> GETs page and returns raw HTML/source."
    )
)
async def http_request(inp: HTTPInput) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=inp.timeout)
    base_headers = {"User-Agent": UA}
    if inp.headers:
        base_headers.update(inp.headers)

    async with aiohttp.ClientSession(timeout=timeout, headers=base_headers, trust_env=True) as session:
        if inp.action == "headers":
            try:
                resp = await session.request("HEAD", str(inp.url), allow_redirects=inp.allow_redirects)
                async with resp:
                    return {"action":"headers","status":resp.status,"url":str(resp.url),"headers":_slim_headers(resp.headers)}
            except aiohttp.ClientResponseError:
                pass
            resp = await session.request("GET", str(inp.url), allow_redirects=inp.allow_redirects)
            async with resp:
                return {"action":"headers","status":resp.status,"url":str(resp.url),"headers":_slim_headers(resp.headers)}

        if inp.action == "source":
            resp = await session.get(str(inp.url), allow_redirects=inp.allow_redirects)
            async with resp:
                text = await _to_text(resp)
                return {"action":"source","status":resp.status,"url":str(resp.url),
                        "content_type":resp.headers.get("content-type"),
                        "encoding":resp.charset,
                        "headers":_slim_headers(resp.headers),
                        "text":text}

        # action == "request"
        resp = await _do_request(session, inp)
        async with resp:
            result: Dict[str, Any] = {
                "action":"request",
                "status":resp.status,
                "url":str(resp.url),
                "method":inp.method,
                "headers":_slim_headers(resp.headers),
            }
            if inp.method in ("HEAD","OPTIONS"):
                return result
            try:
                result["json"] = await resp.json(content_type=None)
            except Exception:
                result["text"] = await _to_text(resp)
            return result
