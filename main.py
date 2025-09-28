# main.py — FastAPI → Databricks (robust reply + logs + mock mode)
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv(), override=True)

import os, re, json, requests, logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ───────────────────────── Logging ─────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("hokiefessor")

# ───────────────────────── Config (env) ────────────────────
WS_URL   = os.getenv("DATABRICKS_WORKSPACE_URL", "").rstrip("/")
TOKEN    = os.getenv("DATABRICKS_TOKEN", "")
ENDPOINT = os.getenv("DB_ENDPOINT_NAME", "")
MOCK     = os.getenv("MOCK", "0") in ("1","true","True","yes","YES")

DEFAULT_SYSTEM = os.getenv(
    "DEFAULT_SYSTEM",
    "You are a Virginia Tech course advisor. Be concise and factual."
)
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", "800"))
TIMEOUT_SECS = int(os.getenv("TIMEOUT_SECS", "35"))

INVOC = f"{WS_URL}/serving-endpoints/{ENDPOINT}/invocations" if WS_URL and ENDPOINT else ""
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"} if TOKEN else {}

# Log config on boot
log.info(f"WS_URL set: {bool(WS_URL)}  ENDPOINT set: {bool(ENDPOINT)}  TOKEN set: {bool(TOKEN)}")
log.info(f"Invocations URL: {INVOC or '(not configured)'}  MOCK={MOCK}")

# ───────────────────── Inline / file context ───────────────
from pathlib import Path

def _resolve_doc_path():
    p = (os.getenv("DOC_PATH") or "").strip().strip("'\"")
    if not p:
        return ""
    pth = Path(p)
    if not pth.is_absolute():
        pth = Path(__file__).parent.joinpath(pth).resolve()
    return str(pth)

DOC_PATH = _resolve_doc_path()
log.info(f"DOC_PATH='{DOC_PATH}' exists={os.path.exists(DOC_PATH)}")

DOC = ""
if DOC_PATH and os.path.exists(DOC_PATH):
    size = os.path.getsize(DOC_PATH)
    log.info(f"Loading dataset… size={size} bytes")
    with open(DOC_PATH, "r", encoding="utf-8", errors="ignore") as f:
        DOC = f.read()
else:
    log.warning("Dataset file not found. Set DOC_PATH correctly.")


DOC_LINES: List[str] = [ln for ln in DOC.splitlines() if ln.strip()]

# Detect where the reviews CSV starts (header begins with teacher_legacy_id,...)
REVIEWS_START = next(
    (i for i, ln in enumerate(DOC_LINES)
     if ln.lower().startswith("teacher_legacy_id,teacher_id")),
    None
)
COURSE_LINES = DOC_LINES if REVIEWS_START is None else DOC_LINES[:REVIEWS_START]
REVIEW_LINES = [] if REVIEWS_START is None else DOC_LINES[REVIEWS_START:]

log.info(f"doc_lines={len(DOC_LINES)} reviews_start_line={(REVIEWS_START + 1) if REVIEWS_START is not None else 'N/A'}")

def _search(lines: List[str], tokens: List[str], max_chars: int, must_contains: str | None = None) -> List[str]:
    picked, seen = [], set()
    for ln in lines:
        lo = ln.lower()
        if must_contains and must_contains not in lo:
            continue
        if any(tok in lo for tok in tokens):
            if ln in seen:
                continue
            seen.add(ln)
            picked.append(ln)
            if sum(len(x) + 1 for x in picked) >= max_chars:
                break
    return picked

def retrieve_context(user_prompt: str, max_chars: int = 8000) -> str:
    if not DOC_LINES:
        return ""
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9+\-_/]+", user_prompt)]
    if not tokens:
        # default: give a little of each section
        head = COURSE_LINES[:120] + REVIEW_LINES[:120]
        return "\n".join(head)[:max_chars]

    txt = " ".join(tokens)
    wants_reviews = any(k in tokens for k in ("review", "reviews", "rating", "ratings", "quality", "difficulty", "would", "again", "comment"))
    # if a proper name Give me 3 representative student reviews for Professor Margaret Ellis (CS 2114)appears (like 'ellis'), prefer matching that in reviews first
    prof_hint = None
    for t in tokens:
        if t in ("ellis","lewis","sole","rowson","ransbottom","clark","nazhandali","mcpherson","barnette","haqq","esakia"):
            prof_hint = t
            break

    # Pass 1: if asking about reviews OR professor name present → search REVIEW_LINES first
    picked = []
    if wants_reviews or prof_hint:
        header = REVIEW_LINES[:1] if REVIEW_LINES else []
        picked = header + _search(REVIEW_LINES, tokens, max_chars, must_contains=prof_hint if prof_hint else None)

    # Pass 2: if still empty or room left, add relevant course-grade lines
    if len("\n".join(picked)) < max_chars:
        picked += _search(COURSE_LINES, tokens, max_chars - len("\n".join(picked)))

    # Fallbacks
    if not picked:
        picked = (COURSE_LINES[:120] + REVIEW_LINES[:120])

    return "\n".join(picked)[:max_chars]


# ───────────────────── Databricks call helper ──────────────
def call_databricks(system: str, prompt: str, temperature: float = 0.5) -> str:
    if MOCK:
        ctx = retrieve_context(prompt)
        return f"[MOCK REPLY]\nQ: {prompt}\n\nTop context lines:\n{ctx[:1000]}"

    if not (INVOC and TOKEN and WS_URL and ENDPOINT):
        raise HTTPException(
            status_code=500,
            detail="Databricks is not configured. Set DATABRICKS_WORKSPACE_URL, DATABRICKS_TOKEN, DB_ENDPOINT_NAME."
        )

    ctx = retrieve_context(prompt)

    messages = [
        {"role": "system", "content": system or DEFAULT_SYSTEM},
        {
            "role": "user",
            "content": (
                "Answer using the CONTEXT when relevant. If info isn't in context, say so briefly.\n\n"
                f"QUESTION:\n{prompt}\n\n"
                f"CONTEXT (CSV rows & reviews):\n{ctx}"
            ),
        },
    ]

    # IMPORTANT: OpenAI-compatible body (Databricks likes model+messages)
    payload = {
        "model": ENDPOINT,
        "messages": messages,
        "temperature": float(temperature or 0.2),
        "max_tokens": MAX_TOKENS,
    }

    log.info(f"POST {INVOC}")
    try:
        resp = requests.post(INVOC, headers=HEADERS, json=payload, timeout=TIMEOUT_SECS)
    except requests.exceptions.Timeout:
        log.error("Databricks timeout")
        raise HTTPException(status_code=504, detail="Databricks timeout")
    except requests.exceptions.RequestException as e:
        log.error(f"Databricks request error: {e}")
        raise HTTPException(status_code=502, detail=f"Request failed: {e}")

    log.info(f"Databricks status={resp.status_code}")
    if not resp.ok:
        try:
            info = resp.json()
        except Exception:
            info = resp.text
        log.error(f"Databricks error body: {info}")
        raise HTTPException(status_code=502, detail=f"API {resp.status_code}: {info}")

    try:
        data = resp.json()
        # Typical OpenAI-compatible schema
        content = data["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        log.error(f"Unexpected response schema: {e}; body={resp.text[:1200]}")
        raise HTTPException(status_code=502, detail=f"Unexpected response: {resp.text[:1200]}")

# ─────────────────────────── FastAPI app ───────────────────
app = FastAPI(title="Hokiefessor", version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

class AskBody(BaseModel):
    prompt: Optional[str] = None
    question: Optional[str] = None
    q: Optional[str] = None
    system: Optional[str] = DEFAULT_SYSTEM
    temperature: Optional[float] = 0.2

def _coalesce_prompt(body: AskBody) -> str:
    return (body.prompt or body.question or body.q or "").strip()

@app.get("/")
def root():
    return {"ok": True, "service": "Hokiefessor", "endpoints": ["/ask", "/api/chat", "/health", "/context"]}

@app.get("/health")
def health():
    return {
        "ok": True,
        "mock": MOCK,
        "workspace_url_set": bool(WS_URL),
        "endpoint_set": bool(ENDPOINT),
        "token_set": bool(TOKEN),
        "invocations_url": INVOC or None,
        "doc_lines": len(DOC_LINES),
    }

@app.get("/context")
def context(q: str = Query(..., description="Preview retrieved context for a query")):
    return {"query": q, "context": retrieve_context(q)}

@app.post("/ask")
def ask(body: AskBody = Body(...)):
    user_prompt = _coalesce_prompt(body)
    if not user_prompt:
        raise HTTPException(status_code=422, detail="Provide 'prompt' (or 'question'/'q') in JSON.")
    reply = call_databricks(body.system or DEFAULT_SYSTEM, user_prompt, body.temperature or 0.2)
    return {"reply": reply, "endpoint": ENDPOINT, "mock": MOCK}

# Alias for your frontend
@app.post("/api/chat")
def api_chat(body: AskBody = Body(...)):
    return ask(body)
