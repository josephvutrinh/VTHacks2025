#!/usr/bin/env python3
"""
VT Engineering Reddit Scraper
- Scrapes VT subs: r/VirginiaTech, r/VirginiaTechStudents, r/hokies
- Filters automatically for engineering-related keywords (expanded list)
- Outputs one combined CSV and JSON
"""

import asyncio, aiohttp, csv, json, os, re, sys, time
from aiohttp import ClientSession, ClientTimeout
from typing import Dict, List, Optional

BASE_URL = "https://www.reddit.com"
LISTING_PATH = "/r/{sub}/{sort}.json"
HEADERS = {"User-Agent": "VT-Eng-Scraper/2.0 (by u/yourname)"}
DEFAULT_SUBS = ["VirginiaTech", "VirginiaTechStudents", "hokies"]
VALID_SORTS = {"hot","new","top","rising"}
VALID_T = {"hour","day","week","month","year","all"}

# 🔑 Expanded engineering keyword list
ENG_KEYWORDS = [
    # general
    "engineering","engineer","capstone","lab","senior design","co-op",
    "internship","research","course override",
    # departments/course prefixes
    "aoe","bme","cee","cem","cs","ece","enge","esm","ise","me","mse","stat","bse"
]
PATTERN = re.compile("|".join(re.escape(k) for k in ENG_KEYWORDS), re.IGNORECASE)

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
        "selftext": (d.get("selftext") or "")[:4000],
    }

async def fetch_json(session: ClientSession, url: str, params: Dict[str,str]) -> Optional[Dict]:
    try:
        async with session.get(url, params=params, headers=HEADERS) as r:
            if r.status == 200:
                return await r.json()
            sys.stderr.write(f"[warn] {r.status} {url}\n")
    except Exception as e:
        sys.stderr.write(f"[error] {e}\n")
    return None

async def fetch_sub(session: ClientSession, sub: str, sort="hot", t=None, limit=200) -> List[Dict]:
    out, after, fetched = [], None, 0
    while fetched < limit:
        count = min(100, limit-fetched)
        params = {"limit": str(count)}
        if sort=="top" and t: params["t"]=t
        if after: params["after"]=after
        url = BASE_URL + LISTING_PATH.format(sub=sub, sort=sort)
        data = await fetch_json(session,url,params)
        if not data: break
        children = data.get("data",{}).get("children",[])
        if not children: break
        for c in children:
            row = to_row(c,sub)
            blob = f"{row['title']}\n{row['selftext']}"
            if PATTERN.search(blob):   # ✅ auto-filter for engineering
                out.append(row)
        fetched += len(children)
        after = data.get("data",{}).get("after")
        if not after: break
        await asyncio.sleep(0.6)
    return out

async def scrape(subs: List[str], sort="hot", t=None, limit=200) -> List[Dict]:
    timeout = ClientTimeout(total=None, connect=20, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        tasks = [fetch_sub(s, sub, sort, t, limit) for sub in subs]
        results = await asyncio.gather(*tasks)
    return [row for chunk in results for row in chunk]

def save(rows: List[Dict], prefix="vt_eng"):
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    with open(prefix+".json","w",encoding="utf-8") as f: json.dump(rows,f,indent=2)
    if rows:
        with open(prefix+".csv","w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

def main():
    subs=DEFAULT_SUBS; sort="hot"; t=None; limit=300; out="vt_eng_posts"
    start=time.time()
    rows=asyncio.run(scrape(subs,sort,t,limit))
    save(rows,out)
    print(f"Saved {len(rows)} VT engineering posts → {out}.csv / {out}.json in {time.time()-start:.1f}s")

if __name__=="__main__":
    main()
