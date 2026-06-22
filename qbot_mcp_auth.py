"""qbot_mcp_auth.py — realny OAuth2.1 dla publicznych konektorow MCP.

Scope-aware: 'qbot' (dane, /mcp) i 'dev' (control plane, /dev-mcp) maja
osobne passcode i osobny namespace tokenow. Token jednego scope nie dziala
na endpointcie drugiego. Kody + tokeny trwale w SQLite.
"""
from __future__ import annotations
import os, time, hmac, hashlib, base64, sqlite3, secrets, html

DB_PATH = os.getenv(
    "QBOT_MCP_AUTH_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "qbot_mcp_auth.db"),
)
TOKEN_TTL = int(os.getenv("QBOT_MCP_TOKEN_TTL", "86400"))
CODE_TTL = 600

_PASSCODE_ENV = {"qbot": "QBOT_MCP_PASSCODE_HASH", "dev": "QBOT_DEV_PASSCODE_HASH"}


def _now() -> float:
    return time.time()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS oauth_codes("
        "code TEXT PRIMARY KEY, client_id TEXT, redirect_uri TEXT, "
        "code_challenge TEXT, method TEXT, scope TEXT DEFAULT 'qbot', expires REAL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS oauth_tokens("
        "token TEXT PRIMARY KEY, issued REAL, expires REAL, scope TEXT DEFAULT 'qbot')"
    )
    # migracja istniejacej bazy (kolumny dodane pozniej)
    for tbl in ("oauth_codes", "oauth_tokens"):
        try:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN scope TEXT DEFAULT 'qbot'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn


# ---- passcode -------------------------------------------------------------
def verify_passcode(passcode: str, realm: str = "qbot") -> bool:
    env_name = _PASSCODE_ENV.get(realm)
    if not env_name:
        return False
    stored = os.getenv(env_name, "")
    if not stored or not passcode:
        return False
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", passcode.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def make_passcode_hash(passcode: str, iters: int = 200000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${dk.hex()}"


# ---- PKCE -----------------------------------------------------------------
def verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if not code_challenge or not code_verifier:
        return False
    if (method or "S256").upper() == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        calc = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return hmac.compare_digest(calc, code_challenge)
    return hmac.compare_digest(code_verifier, code_challenge)


# ---- codes ----------------------------------------------------------------
def save_code(code, client_id, redirect_uri, code_challenge, method, scope="qbot") -> None:
    conn = _db()
    with conn:
        conn.execute("DELETE FROM oauth_codes WHERE expires < ?", (_now(),))
        conn.execute(
            "INSERT OR REPLACE INTO oauth_codes"
            "(code, client_id, redirect_uri, code_challenge, method, scope, expires) "
            "VALUES(?,?,?,?,?,?,?)",
            (code, client_id, redirect_uri, code_challenge, method, scope, _now() + CODE_TTL),
        )
    conn.close()


def consume_code(code):
    conn = _db()
    cur = conn.execute(
        "SELECT code, client_id, redirect_uri, code_challenge, method, scope, expires "
        "FROM oauth_codes WHERE code=?",
        (code,),
    )
    row = cur.fetchone()
    if row:
        with conn:
            conn.execute("DELETE FROM oauth_codes WHERE code=?", (code,))
    conn.close()
    if not row:
        return None
    keys = ["code", "client_id", "redirect_uri", "code_challenge", "method", "scope", "expires"]
    d = dict(zip(keys, row))
    if d["expires"] < _now():
        return None
    return d


# ---- tokens ---------------------------------------------------------------
def issue_token(scope="qbot", ttl: int | None = None):
    ttl = TOKEN_TTL if ttl is None else ttl
    token = secrets.token_urlsafe(48)
    conn = _db()
    with conn:
        conn.execute("DELETE FROM oauth_tokens WHERE expires < ?", (_now(),))
        conn.execute(
            "INSERT INTO oauth_tokens(token, issued, expires, scope) VALUES(?,?,?,?)",
            (token, _now(), _now() + ttl, scope),
        )
    conn.close()
    return token, ttl


def validate_bearer(authorization: str, required_scope: str | None = None) -> bool:
    if not authorization:
        return False
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    token = parts[1].strip()
    if not token:
        return False
    conn = _db()
    cur = conn.execute("SELECT expires, scope FROM oauth_tokens WHERE token=?", (token,))
    row = cur.fetchone()
    conn.close()
    if not row or row[0] < _now():
        return False
    if required_scope is not None and (row[1] or "qbot") != required_scope:
        return False
    return True


# ---- login form -----------------------------------------------------------
def login_form_html(params: dict, error: str = "", realm: str = "qbot") -> str:
    title = "QBot DEV (control plane)" if realm == "dev" else "QBot MCP"
    hidden = "".join(
        '<input type="hidden" name="{}" value="{}">'.format(
            html.escape(str(k)), html.escape(str(v))
        )
        for k, v in params.items()
        if k != "passcode"
    )
    err = '<p style="color:#c0392b;margin:.5rem 0">{}</p>'.format(html.escape(error)) if error else ""
    return (
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>" + title + "</title></head>"
        '<body style="font-family:system-ui,-apple-system,sans-serif;max-width:360px;'
        'margin:12vh auto;padding:0 1rem;color:#222">'
        '<h2 style="margin-bottom:.2rem">' + title + "</h2>"
        '<p style="color:#555;margin-top:.2rem">Podaj passcode, aby polaczyc konektor.</p>'
        + err +
        '<form method="post" action="/oauth/authorize" autocomplete="on">'
        + hidden +
        '<input type="text" name="username" value="' + ("qbot-dev" if realm == "dev" else "qbot") + '" '
        'autocomplete="username" readonly style="position:absolute;left:-9999px" tabindex="-1" aria-hidden="true">'
        '<label for="passcode" style="font-size:.9rem;color:#555">Passcode</label>'
        '<input id="passcode" name="passcode" type="password" autocomplete="current-password" '
        'style="display:block;width:100%;box-sizing:border-box;padding:.65rem;margin:.35rem 0 1rem;'
        'font-size:1rem;border:1px solid #ccc;border-radius:8px" autofocus>'
        '<button type="submit" style="width:100%;padding:.7rem;font-size:1rem;border:0;'
        'border-radius:8px;background:#111;color:#fff;cursor:pointer">Polacz</button>'
        "</form></body></html>"
    )
