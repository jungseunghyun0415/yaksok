"""화면의 '설정'에서 입력한 키·주소를 이 컴퓨터에만 저장한다 (GitHub에는 올라가지 않는다).

저장 위치: 내 사용자 폴더의 .yaksok/settings.json  (레포 밖이라 실수로 커밋될 일이 없다)
저장한 값은 환경변수로 옮겨 쓴다. main.py와 schedule_store.py가 환경변수를 읽기 때문이다.
"""
import json
import os
from pathlib import Path

KEYS = ("GEMINI_API_KEY", "DISCORD_WEBHOOK_URL", "EMAIL_USER", "EMAIL_PASSWORD", "EMAIL_TO", "GITHUB_REPO", "GITHUB_TOKEN")


def settings_file() -> Path:
    return Path.home() / ".yaksok" / "settings.json"


def load() -> dict:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(data[k]) for k in KEYS if data.get(k)}


def save(values: dict) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: values[k].strip() for k in KEYS if values.get(k, "").strip()}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)  # 다른 사용자가 읽지 못하게 (윈도우에서는 무시될 수 있다)
    except OSError:
        pass


def apply(values: dict, previous: dict | None = None) -> None:
    """값을 환경변수에 반영한다. 이번에 비운 항목은 환경변수에서도 지운다."""
    for k in KEYS:
        if values.get(k):
            os.environ[k] = values[k].strip()
        elif previous and previous.get(k):
            os.environ.pop(k, None)
