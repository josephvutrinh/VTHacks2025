#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
rmp.py — Collect Virginia Tech professors (engineering-focused by default) from
RateMyProfessors via their public GraphQL endpoint, then fetch all ratings for
each professor and save to CSV.

Tested Feb 2025.

If you want ALL departments, set ONLY_ENGINEERING_DEPTS = False below.
"""

import csv
import time
import json
import string
from typing import Dict, List, Any, Iterable
import requests

# -------------------------
# Config
# -------------------------

SCHOOL_ID = "U2Nob29sLTEzNDk="  # Virginia Tech (base64 RMP node id)
ENDPOINT = "https://www.ratemyprofessors.com/graphql"

# This header set mirrors what the site uses in production; the 'authorization'
# is required now (Basic dGVzdDp0ZXN0 == "test:test").
HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.ratemyprofessors.com",
    "referer": "https://www.ratemyprofessors.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "authorization": "Basic dGVzdDp0ZXN0",  # 'test:test'
}

OUT_PROFESSORS = "vt_engineering_professors.csv"
OUT_REVIEWS = "vt_professor_reviews.csv"

# Collect only engineering-ish depts (client-side filter)
ONLY_ENGINEERING_DEPTS = True
ENGINEERING_KEYWORDS = {
    "engineering",
    "computer science",
    "electrical",
    "mechanical",
    "civil",
    "aerospace",
    "materials",
    "industrial",
    "systems",
    "biomedical",
    "mining",
    "nuclear",
    "construction",
    "robotics",
    "mechatronics",
    "data",
    "software",
}

# Rate limits / retries
PAGE_SIZE = 100
RATINGS_PAGE_SIZE = 100
RETRY = 3
SLEEP_BETWEEN_CALLS = 0.25  # seconds

# -------------------------
# GraphQL
# -------------------------

Q_SEARCH = """
query NewSearchTeachers($text: String, $schoolID: ID!, $first: Int, $after: String) {
  newSearch {
    teachers(
      query: {text: $text, schoolID: $schoolID, fallback: true}
      first: $first
      after: $after
    ) {
      pageInfo { hasNextPage endCursor }
      resultCount
      edges {
        node {
          __typename
          id
          legacyId
          firstName
          lastName
          department
          school { id name city state legacyId }
          avgRating
          avgDifficulty
          numRatings
          wouldTakeAgainPercent
        }
      }
    }
  }
}
"""

# NOTE: renamed fields on Rating:
# quality -> qualityRating
# difficulty -> difficultyRating
# attendance -> attendanceMandatory
Q_RATINGS = """
query TeacherRatings($id: ID!, $first: Int, $after: String) {
  node(id: $id) {
    ... on Teacher {
      id
      legacyId
      firstName
      lastName
      department
      ratings(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            legacyId
            date
            class
            comment
            qualityRating
            difficultyRating
            attendanceMandatory
            wouldTakeAgain
            grade
            isForOnlineClass
            textbookUse
            thumbsUpTotal
            thumbsDownTotal
          }
        }
      }
    }
  }
}
"""

# -------------------------
# Helpers
# -------------------------

def _post(session: requests.Session, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"query": query, "variables": variables}
    for attempt in range(1, RETRY + 1):
        resp = session.post(ENDPOINT, headers=HEADERS, data=json.dumps(payload))
        # Simple handling for 429 or random 5xx/403 throttling
        if resp.status_code == 429:
            time.sleep(1.5 * attempt)
            continue
        if resp.status_code >= 400:
            # Bubble up GraphQL 'errors' if present
            try:
                data = resp.json()
                if "errors" in data:
                    raise RuntimeError(f"HTTP {resp.status_code}: {data['errors']}")
            except Exception:
                pass
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if "errors" in data:
            # If schema error etc., don't retry endlessly—raise now.
            raise RuntimeError(str(data["errors"]))
        return data
    raise RuntimeError("Too many retry attempts")

def dept_looks_engineering(dept: str) -> bool:
    if not dept:
        return False
    d = dept.strip().lower()
    return any(k in d for k in ENGINEERING_KEYWORDS)

def paginate_teachers(session: requests.Session, text: str) -> Iterable[Dict[str, Any]]:
    """
    Yield teacher nodes for a given search text (may be empty string).
    """
    after = None
    while True:
        vars_ = {
            "text": (None if text == "" else text),
            "schoolID": SCHOOL_ID,
            "first": PAGE_SIZE,
            "after": after,
        }
        data = _post(session, Q_SEARCH, vars_)
        conn = data["data"]["newSearch"]["teachers"]
        edges = conn.get("edges") or []
        for e in edges:
            node = e.get("node") or {}
            yield node
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        time.sleep(SLEEP_BETWEEN_CALLS)

def fetch_all_teachers(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Search with '' (empty), then 'a'..'z' to maximize recall and de-duplicate by legacyId.
    """
    terms = [""] + list(string.ascii_lowercase)
    seen: Dict[int, Dict[str, Any]] = {}
    total_reported = 0

    print("[INFO] Collecting Virginia Tech professors (engineering only) ...")
    for t in terms:
        try:
            # For logs: show nice symbol for empty search
            log_t = "∅" if t == "" else t
            count = 0
            for node in paginate_teachers(session, t):
                legacy = node.get("legacyId")
                if legacy is None:
                    continue
                if ONLY_ENGINEERING_DEPTS and not dept_looks_engineering(node.get("department") or ""):
                    continue
                if legacy not in seen:
                    seen[legacy] = node
                    count += 1
            print(f"[INFO] term '{log_t}' -> {count if t != '' else len(seen)} teachers")
            total_reported += count
        except Exception as e:
            print(f"[WARN] term '{t or '∅'}' failed: {e}")
    print(f"[INFO] Unique engineering professors found: {len(seen)}")
    return list(seen.values())

def save_professors_csv(rows: List[Dict[str, Any]], path: str) -> None:
    fieldnames = [
        "legacyId",
        "id",
        "firstName",
        "lastName",
        "department",
        "school_legacyId",
        "school_name",
        "school_city",
        "school_state",
        "avgRating",
        "avgDifficulty",
        "numRatings",
        "wouldTakeAgainPercent",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in rows:
            sch = p.get("school") or {}
            w.writerow({
                "legacyId": p.get("legacyId"),
                "id": p.get("id"),
                "firstName": p.get("firstName"),
                "lastName": p.get("lastName"),
                "department": p.get("department"),
                "school_legacyId": sch.get("legacyId"),
                "school_name": sch.get("name"),
                "school_city": sch.get("city"),
                "school_state": sch.get("state"),
                "avgRating": p.get("avgRating"),
                "avgDifficulty": p.get("avgDifficulty"),
                "numRatings": p.get("numRatings"),
                "wouldTakeAgainPercent": p.get("wouldTakeAgainPercent"),
            })

def fetch_reviews_for_teacher(session: requests.Session, teacher_id: str) -> List[Dict[str, Any]]:
    """
    teacher_id is the base64 node id (not legacy); returns list of rating dicts (node objects).
    """
    after = None
    out: List[Dict[str, Any]] = []
    while True:
        vars_ = {"id": teacher_id, "first": RATINGS_PAGE_SIZE, "after": after}
        data = _post(session, Q_RATINGS, vars_)
        node = (data.get("data") or {}).get("node") or {}
        ratings = (node.get("ratings") or {})
        edges = ratings.get("edges") or []
        for e in edges:
            r = e.get("node") or {}
            out.append(r)
        page = ratings.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out

def save_reviews_csv(session: requests.Session, profs: List[Dict[str, Any]], path: str) -> None:
    fieldnames = [
        "teacher_legacy_id",
        "teacher_id",
        "teacher_name",
        "teacher_department",
        "rating_legacy_id",
        "date",
        "class",
        "comment",
        "quality",                 # mapped from qualityRating
        "difficulty",              # mapped from difficultyRating
        "attendance_mandatory",    # mapped from attendanceMandatory
        "would_take_again",
        "grade",
        "is_online",
        "textbook_use",
        "thumbs_up",
        "thumbs_down",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        # (Optional) skip professors with 0 ratings to reduce calls
        work = [p for p in profs if (p.get("numRatings") or 0) > 0]

        print("[INFO] Fetching all reviews for each professor (this can take a while) ...")
        for idx, p in enumerate(work, start=1):
            name = f"{p.get('firstName','').strip()} {p.get('lastName','').strip()}".strip()
            try:
                ratings = fetch_reviews_for_teacher(session, p.get("id"))
                for r in ratings:
                    w.writerow({
                        "teacher_legacy_id": p.get("legacyId"),
                        "teacher_id": p.get("id"),
                        "teacher_name": name,
                        "teacher_department": p.get("department"),
                        "rating_legacy_id": r.get("legacyId"),
                        "date": r.get("date"),
                        "class": r.get("class"),
                        "comment": (r.get("comment") or "").replace("\r", " ").replace("\n", " ").strip(),
                        "quality": r.get("qualityRating"),
                        "difficulty": r.get("difficultyRating"),
                        "attendance_mandatory": r.get("attendanceMandatory"),
                        "would_take_again": r.get("wouldTakeAgain"),
                        "grade": r.get("grade"),
                        "is_online": r.get("isForOnlineClass"),
                        "textbook_use": r.get("textbookUse"),
                        "thumbs_up": r.get("thumbsUpTotal"),
                        "thumbs_down": r.get("thumbsDownTotal"),
                    })
                # Light heartbeat so you know it's alive
                if idx % 25 == 0:
                    print(f"[INFO]  processed {idx}/{len(work)} professors ...")
            except Exception as e:
                print(f"[WARN] reviews for {name} failed: {e}")

# -------------------------
# Main
# -------------------------

def main():
    with requests.Session() as s:
        # 1) Collect professors
        profs = fetch_all_teachers(s)
        save_professors_csv(profs, OUT_PROFESSORS)
        print(f"[INFO] Saved professors -> {OUT_PROFESSORS} ({len(profs)} rows)")

        # 2) Collect all reviews
        save_reviews_csv(s, profs, OUT_REVIEWS)
        print(f"[INFO] Saved reviews -> {OUT_REVIEWS}")

if __name__ == "__main__":
    main()
