#!/usr/bin/env python3
# VT Engineering Reddit Scraper — search-only + strict filter + certifi SSL
import asyncio, aiohttp, csv, json, os, re, sys, time, ssl, certifi
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from typing import Dict, List, Optional, Tuple

BASE_URL = "https://www.reddit.com"
LISTING_PATH = "/r/{sub}/{sort}.json"
SEARCH_PATH  = "/r/{sub}/search.json"

HEADERS = {
    "User-Agent": "VTHacks-EngScraper/4.0 (macOS; Python) by u/your_reddit_name contact: you@example.com"
}

# ──────────────────────────────────────────────────────────────────────────────
# Subreddits: VT-centric only (you can add pure engineering subs if you want)
DEFAULT_SUBS = ["VirginiaTech", "VirginiaTechStudents"]

# We will use SEARCH ONLY (not listings) so we don't bring in non-engineering posts.
SORT = "new"          # used for search sorting
LIMIT_PER_TERM = 100  # Reddit search max per request is ~100; we'll iterate terms
TERMS_PER_SUB = 10    # safety cap across terms per subreddit
OUT_PREFIX = "vt_eng_posts"

# ──────────────────────────────────────────────────────────────────────────────
# Engineering terms to SEARCH for within VT subs (kept short for precision)
ENG_SEARCH_TERMS = [
    # general
    "engineering", "engineer", "capstone", "senior design", "lab",
    "co-op", "internship", "research", "course override", "career fair",
    # dept names / acronyms
    "AOE", "Aerospace", "BME", "Biomedical",
    "CEE", "Civil", "CEM", "Construction Engineering",
    "CS", "Computer Science",
    "ECE", "Electrical", "Computer Engineering",
    "ENGE", "General Engineering", "ENE",
    "ESM", "Engineering Science and Mechanics",
    "ISE", "Industrial and Systems",
    "ME", "Mechanical",
    "MSE", "Materials Science",
    "STAT", "Statistics",
    "BSE", "Biological Systems",
]

# Strict keep-filter: department acronyms + course codes like "CS 2114", "ECE-3105"
ENG_KEYWORDS = [
    "engineering","engineer","capstone","lab","senior design","co-op",
    "internship","research","course override","resume","recruiter","career fair",
    "aoe","bme","cee","cem","cs","ece","enge","ene","esm","ise","me","mse","stat","bse",
    # common VT phrases people use
    "college of engineering", "ceed", "ware lab", "frith lab"
]
COURSE_CODE_RE = r"\b(?:AOE|BME|CEE|CEM|CS|ECE|ENGE|ENE|ESM|ISE|ME|MSE|STAT|BSE)\s?[- ]?\d{3,4}\b"
FLAIR_RE = r"\b(academics|class|course|engineering|major|advising|internship|research)\b"

ENG_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in ENG_KEYWORDS) + r"|" + COURSE_CODE_RE + r")",
    re.IGNORECASE
)
FLAIR_PATTERN = re.compile(FLAIR_RE, re.IGNORECASE)

# ──────────────────────────────────────────────────────────────────────────────
def make_ssl_connector():
    ctx = ssl.create_default_context(cafile=certifi.where())
    return TCPConnector(ssl=ctx, limit=10, ttl_dns_cache=300)

def to_row(post: Dict, sub: str) -> Dict:
    d = post.get("data", {})
    return {
        "subreddit": sub,
        "id": d.get("id"),
        "title": d.get("title"),
        "author": d.get("author"),
        "score": d.get("score"),
        "num_comments": d.get("num_comments"),
        "created_utc": d.get("created_utc"),
        "permalink": f"{BASE_URL}{d.get('permalink','')}",
        "url": d.get("url"),
        "link_flair_text": d.get("link_flair_text"),
        "selftext": (d.get("selftext") or "")[:8000],
    }

async def fetch_json(session: ClientSession, url: str, params: Dict[str,str], retries: int = 5) -> Optional[Dict]:
    delay = 1.0
    for _ in range(retries):
        try:
            async with session.get(url, params=params, headers=HEADERS) as r:
                if r.status == 200:
                    return await r.json()
                if r.status in (429, 500, 502, 503, 504):
                    await asyncio.sleep(delay); delay *= 1.8
                else:
                    sys.stderr.write(f"[warn] {r.status} {url}\n")
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            sys.stderr.write(f"[warn] {type(e).__name__}: {e}; retrying...\n")
            await asyncio.sleep(delay); delay *= 1.8
    sys.stderr.write(f"[error] failed after retries: {url}\n")
    return None

async def search_sub_term(session: ClientSession, sub: str, term: str, sort: str, limit: int) -> List[Dict]:
    """
    Use subreddit search to fetch ONLY engineering-related hits for a given term.
    """
    params = {
        "q": term,
        "restrict_sr": "on",
        "sort": sort,      # "new", "relevance", "top", "comments"
        "limit": str(min(100, limit)),
        "include_over_18": "off",
        "t": "all",
    }
    url = BASE_URL + SEARCH_PATH.format(sub=sub)
    data = await fetch_json(session, url, params)
    rows: List[Dict] = []
    if not data: return rows
    children = data.get("data", {}).get("children", [])
    for c in children:
        rows.append(to_row(c, sub))
    return rows

async def search_subreddit(session: ClientSession, sub: str, terms: List[str], sort: str, limit_per_term: int, max_terms: int) -> List[Dict]:
    got: List[Dict] = []
    # cap terms per sub so we don't hammer the API
    for i, term in enumerate(terms[:max_terms]):
        chunk = await search_sub_term(session, sub, term, sort, limit_per_term)
        got.extend(chunk)
        await asyncio.sleep(0.6)
    return got

def strict_keep(row: Dict) -> bool:
    blob = f"{row.get('title','')}\n{row.get('selftext','')}"
    flair = row.get("link_flair_text") or ""
    # must match engineering pattern
    if not ENG_PATTERN.search(blob) and not ENG_PATTERN.search(flair):
        return False
    # if flair exists, prefer it to be academic/eng-ish (but don't require)
    if flair and not FLAIR_PATTERN.search(flair):
        # allow if the text is a clear match (course code etc.)
        return bool(ENG_PATTERN.search(blob))
    return True

def dedupe(rows: List[Dict]) -> List[Dict]:
    seen = set(); out = []
    for r in rows:
        k = (r.get("subreddit"), r.get("id"))
        if k not in seen:
            out.append(r); seen.add(k)
    return out

async def scrape(subs: List[str]) -> Tuple[List[Dict], Dict[str,int]]:
    timeout = ClientTimeout(total=None, connect=20, sock_read=40)
    connector = make_ssl_connector()
    stats = {"fetched":0, "kept":0, "rejected":0}
    async with ClientSession(timeout=timeout, connector=connector) as s:
        tasks = [search_subreddit(s, sub, ENG_SEARCH_TERMS, SORT, LIMIT_PER_TERM, TERMS_PER_SUB) for sub in subs]
        results = await asyncio.gather(*tasks)

    all_rows = [r for chunk in results for r in chunk]
    stats["fetched"] = len(all_rows)
    all_rows = dedupe(all_rows)

    kept, rejected = [], []
    for r in all_rows:
        if strict_keep(r):
            kept.append(r)
        else:
            rejected.append(r)

    stats["kept"] = len(kept)
    stats["rejected"] = len(rejected)
    return kept, stats

def save(rows: List[Dict], prefix: str):
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    if rows:
        with open(prefix + ".csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)

def main():
    subs = DEFAULT_SUBS
    start = time.time()
    rows, stats = asyncio.run(scrape(subs))
    save(rows, OUT_PREFIX)
    dur = time.time() - start
    print(f"Fetched via search: {stats['fetched']}  |  Kept (strict engineering): {stats['kept']}  |  Rejected: {stats['rejected']}")
    print(f"Subs: {', '.join(subs)}  |  Terms used: {min(len(ENG_SEARCH_TERMS), TERMS_PER_SUB)} per sub  |  Limit/term: {LIMIT_PER_TERM}")
    print(f"Wrote {OUT_PREFIX}.json and {OUT_PREFIX}.csv")
    print(f"Done in {dur:.1f}s")

if __name__ == "__main__":
    main()
