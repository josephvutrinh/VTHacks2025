#!/usr/bin/env python3
# VT Engineering Reddit Scraper — with certifi SSL patch
import asyncio, aiohttp, csv, json, os, re, sys, time, ssl, certifi
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from typing import Dict, List, Optional

BASE_URL = "https://www.reddit.com"
LISTING_PATH = "/r/{sub}/{sort}.json"
HEADERS = {
    "User-Agent": "VTHacks-EngScraper/3.1 (macOS; Python) by u/your_reddit_name contact: you@example.com"
}

DEFAULT_SUBS = ["VirginiaTech", "VirginiaTechStudents", "hokies"]
SORT = "new"
T = None
LIMIT = 600
OUT_PREFIX = "vt_eng_posts"

# ------------ FILTER -------------
ENG_KEYWORDS = [
    "engineering","engineer","capstone","lab","senior design","co-op",
    "internship","research","course override","resume","recruiter","career fair",
    "aoe","bme","cee","cem","cs","ece","enge","ene","esm","ise","me","mse","stat","bse"
]
COURSE_CODE_RE = r"\b(?:AOE|BME|CEE|CEM|CS|ECE|ENGE|ENE|ESM|ISE|ME|MSE|STAT|BSE)\s?[- ]?\d{3,4}\b"

ENG_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in ENG_KEYWORDS) + r"|" + COURSE_CODE_RE + r")",
    re.IGNORECASE
)

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
        "selftext": (d.get("selftext") or "")[:8000],
    }

def make_ssl_connector():
    ctx = ssl.create_default_context(cafile=certifi.where())
    return TCPConnector(ssl=ctx, limit=8, ttl_dns_cache=300)

async def fetch_json(session: ClientSession, url: str, params: Dict[str,str], retries: int = 5) -> Optional[Dict]:
    delay = 1.0
    for attempt in range(retries):
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
            sys.stderr.write(f"[warn] {type(e).__name__} {e}; retrying...\n")
            await asyncio.sleep(delay); delay *= 1.8
    sys.stderr.write(f"[error] failed after {retries} retries: {url}\n")
    return None

async def fetch_sub(session: ClientSession, sub: str, sort="new", t=None, limit=200) -> List[Dict]:
    out, after, fetched = [], None, 0
    while fetched < limit:
        count = min(100, limit - fetched)
        params = {"limit": str(count)}
        if sort == "top" and t: params["t"] = t
        if after: params["after"] = after
        url = BASE_URL + LISTING_PATH.format(sub=sub, sort=sort)
        data = await fetch_json(session, url, params)
        if not data: break
        children = data.get("data",{}).get("children",[])
        if not children: break
        for c in children:
            out.append(to_row(c,sub))
        fetched += len(children)
        after = data.get("data",{}).get("after")
        if not after: break
        await asyncio.sleep(0.7)
    return out

async def scrape(subs: List[str], sort="new", t=None, limit=200) -> List[Dict]:
    timeout = ClientTimeout(total=None, connect=20, sock_read=40)
    connector = make_ssl_connector()
    async with ClientSession(timeout=timeout, connector=connector) as s:
        tasks = [fetch_sub(s, sub, sort, t, limit) for sub in subs]
        results = await asyncio.gather(*tasks)
    return [row for chunk in results for row in chunk]

def save(rows: List[Dict], prefix: str, rejected_sample: List[str]):
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    if rows:
        with open(prefix + ".csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)
    if rejected_sample:
        with open(prefix + "_rejected_titles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(rejected_sample[:50]))

def main():
    subs = DEFAULT_SUBS
    sort, t, limit, out = SORT, T, LIMIT, OUT_PREFIX

    start = time.time()
    all_rows = asyncio.run(scrape(subs, sort, t, limit))

    fetched_count = len(all_rows)
    kept, rejected_titles = [], []
    for r in all_rows:
        blob = (r.get("title") or "") + "\n" + (r.get("selftext") or "")
        if ENG_PATTERN.search(blob):
            kept.append(r)
        else:
            rejected_titles.append(r.get("title") or "")

    save(kept, out, rejected_titles)

    dur = time.time() - start
    print(f"Fetched: {fetched_count}  |  Kept (engineering): {len(kept)}  |  Rejected: {fetched_count - len(kept)}")
    print(f"Subs: {', '.join(subs)}  |  Sort: {sort}  |  Limit per sub: {limit}")
    print(f"Wrote {out}.json and {out}.csv  (debug: {out}_rejected_titles.txt)")
    print(f"Done in {dur:.1f}s")

if __name__ == "__main__":
    main()
