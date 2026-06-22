"""DEV MCP OAuth gate — logowanie identyczne jak glowny /mcp, scope 'dev'.

Publiczne /dev-mcp/* jest chronione OAuth (scope 'dev'); po poprawnym
logowaniu zapytanie jest przekazywane do DEV MCP (127.0.0.1:8012) z
doklejonym statycznym tokenem QBOT_DEV_MCP_TOKEN po stronie serwera
(uzytkownik go nie widzi). Endpointy .well-known zostaja publiczne, zeby
konektor mogl wykryc serwer autoryzacji.
"""
import os
import httpx
import qbot_mcp_auth as _auth
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

DEV_UPSTREAM = "http://127.0.0.1:8012"
BASE = "https://qbot.cytr.us"
DEV_RESOURCE = BASE + "/dev-mcp/mcp"
PR_META_URL = BASE + "/dev-mcp/.well-known/oauth-protected-resource"


def _protected_resource():
    return {
        "resource": DEV_RESOURCE,
        "authorization_servers": [BASE],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["dev"],
    }


def _auth_server():
    return {
        "issuer": BASE,
        "authorization_endpoint": BASE + "/oauth/authorize",
        "token_endpoint": BASE + "/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "registration_endpoint": BASE + "/oauth/register",
        "scopes_supported": ["dev"],
    }


def register_dev_mcp_routes(app):
    @app.api_route("/dev-mcp/{path:path}",
                   methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"])
    async def dev_mcp_gate(request: Request, path: str = ""):
        p = request.url.path
        # Publiczne wykrywanie OAuth — bez logowania
        if "/.well-known/oauth-protected-resource" in p:
            return JSONResponse(_protected_resource())
        if "/.well-known/oauth-authorization-server" in p:
            return JSONResponse(_auth_server())
        # Bramka OAuth — scope 'dev', tak samo jak glowny /mcp
        if not _auth.validate_bearer(request.headers.get("authorization", ""), "dev"):
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32001, "message": "unauthorized"}},
                status_code=401,
                headers={"WWW-Authenticate":
                         'Bearer resource_metadata="' + PR_META_URL + '"'},
            )
        # Po przejsciu — proxy do DEV MCP z doklejonym statycznym tokenem
        tok = os.environ.get("QBOT_DEV_MCP_TOKEN", "")
        target = DEV_UPSTREAM + "/" + path
        if request.url.query:
            target += "?" + request.url.query
        fwd = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length", "authorization")}
        fwd["authorization"] = "Bearer " + tok
        body = await request.body()
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))
        upstream = await client.send(
            client.build_request(request.method, target, headers=fwd, content=body),
            stream=True,
        )
        resp_headers = {k: v for k, v in upstream.headers.items()
                        if k.lower() not in ("content-length", "transfer-encoding", "connection")}

        async def _stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            _stream(),
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type=upstream.headers.get("content-type"),
        )
