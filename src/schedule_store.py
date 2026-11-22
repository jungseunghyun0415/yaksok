"""복용 일정(data/medicines.json) 읽기·쓰기.

- GITHUB_TOKEN, GITHUB_REPO(예: 계정/yaksok)가 있으면 GitHub 레포의 파일을 직접 수정한다.
  → GitHub Actions 알림이 바로 그 일정을 읽는다.
- 없으면 내 컴퓨터의 data/medicines.json을 수정한다.
"""
import base64
import json
import os
from datetime import date
from pathlib import Path

import requests

LOCAL_FILE = Path(__file__).resolve().parent.parent / "data" / "medicines.json"
REMOTE_PATH = "data/medicines.json"


def _remote():
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
    if token and repo:
        return {"token": token, "repo": repo, "branch": os.environ.get("GITHUB_BRANCH", "main")}
    return None


def storage_mode() -> str:
    return "GitHub 레포" if _remote() else "이 컴퓨터의 파일"


def _url_headers(cfg):
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{REMOTE_PATH}"
    headers = {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json"}
    return url, headers


def _remote_get(cfg):
    url, headers = _url_headers(cfg)
    r = requests.get(url, headers=headers, params={"ref": cfg["branch"]}, timeout=15)
    if r.status_code == 404:
        return {"medicines": []}, None
    r.raise_for_status()
    j = r.json()
    return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j["sha"]


def load_schedule() -> dict:
    cfg = _remote()
    if cfg:
        data = _remote_get(cfg)[0]
    elif LOCAL_FILE.exists():
        data = json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    else:
        data = {}
    data.setdefault("medicines", [])
    return data


def save_schedule(data: dict, message: str = "약속 화면: 복용 일정 수정") -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    cfg = _remote()
    if not cfg:
        LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_FILE.write_text(text, encoding="utf-8")
        return
    _, sha = _remote_get(cfg)
    url, headers = _url_headers(cfg)
    body = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        body["sha"] = sha
    requests.put(url, headers=headers, json=body, timeout=15).raise_for_status()


def in_period(med: dict, d: date) -> bool:
    """d가 이 약의 복용 기간(시작일~종료일) 안인지. 날짜가 없으면 항상 True."""
    start, end = med.get("start_date"), med.get("end_date")
    if start and d < date.fromisoformat(start):
        return False
    if end and d > date.fromisoformat(end):
        return False
    return True
