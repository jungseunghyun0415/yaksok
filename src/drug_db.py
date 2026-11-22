"""약 데이터(data/drug_info_clean.csv) 검색 도구. 알림(main.py)과 화면(app)이 함께 쓴다."""
import csv
import difflib
import re
from functools import lru_cache
from pathlib import Path

DRUG_CSV = Path(__file__).resolve().parent.parent / "data" / "drug_info_clean.csv"


def normalize(text: str) -> str:
    """공백·줄바꿈을 지우고 소문자로 바꿔 비교하기 쉽게 만든다."""
    return re.sub(r"\s+", "", text or "").lower()


def clean_name(text: str) -> str:
    """줄바꿈이 섞인 이름을 한 줄로 정리한다."""
    return re.sub(r"\s+", " ", text or "").strip()


@lru_cache(maxsize=1)
def load_drugs() -> list[dict]:
    with open(DRUG_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_norm"] = normalize(r.get("제품명", ""))
        r["_ing"] = normalize(r.get("주성분", ""))
    return rows


def search(query: str, limit: int = 5) -> list[dict]:
    """제품명에 query가 들어간 약을 먼저 찾고, 없으면 비슷한 이름을 찾는다."""
    q = normalize(query)
    if len(q) < 2:
        return []
    rows = load_drugs()
    hits = sorted((r for r in rows if q in r["_norm"]), key=lambda r: len(r["_norm"]))
    if hits:
        return hits[:limit]
    scored = []
    for r in rows:
        m = difflib.SequenceMatcher(None, q, r["_norm"][: len(q)])
        if m.real_quick_ratio() >= 0.6 and m.quick_ratio() >= 0.6:
            ratio = m.ratio()
            if ratio >= 0.6:
                scored.append((ratio, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def search_any(query: str, limit: int = 10) -> list[dict]:
    """제품명 또는 주성분에 query가 들어간 약을 찾는다 (제품명 일치가 먼저). 없으면 비슷한 이름을 찾는다."""
    q = normalize(query)
    if len(q) < 2:
        return []
    rows = load_drugs()
    by_name = sorted((r for r in rows if q in r["_norm"]), key=lambda r: len(r["_norm"]))
    seen = {id(r) for r in by_name}
    by_ing = sorted((r for r in rows if q in r["_ing"] and id(r) not in seen), key=lambda r: len(r["_norm"]))
    found = (by_name + by_ing)[:limit]
    return found or search(query, limit)


def info_text(row: dict) -> str:
    """AI 프롬프트의 [복용 약 정보]에 넣을 글. CSV에 있는 사실만 담는다."""
    return (
        f"- 제품명: {clean_name(row.get('제품명'))}\n"
        f"- 제조사: {clean_name(row.get('업체명'))}\n"
        f"- 주성분: {clean_name(row.get('주성분'))}"
    )


def lookup_info(name: str) -> str:
    """이름으로 약을 찾아 정보 글을 돌려준다. 못 찾으면 이름만 알려준다."""
    try:
        found = search(name, 1)
    except FileNotFoundError:
        found = []
    if found:
        return info_text(found[0])
    return f"- 제품명: {name}\n(이 약의 상세 정보는 약 데이터에 없습니다)"
