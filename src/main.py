"""약속: 복용 시간이 된 약을 찾아 AI 안내문을 만들고 디스코드로 보낸다.

GitHub Actions가 30분마다 실행한다. 로컬 테스트:
    TEST_MODE=1 DRY_RUN=1 python src/main.py
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from ai_analyzer import generate_medicine_guide # 김준우 모듈 (파일 이름이 다르면 여기를 수정)

KST = ZoneInfo("Asia/Seoul")
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "medicines.json"

# cron 간격과 같게 유지한다. 실행이 조금 늦어져도 같은 알림이 두 번 가지 않게 하기 위함이다.
WINDOW_MIN = 30
NO_DUR = "(조회된 병용 주의 데이터가 없습니다)"
DISCLAIMER = "※ 본 안내는 의학적 조언이 아니며, 정확한 상담은 약사·의사와 진행하세요."


def load_medicines() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)["medicines"]


def is_due(times: list[str], now: datetime) -> bool:
    """now가 복용 시각 이후 WINDOW_MIN분 안이면 True. 자정 직후 실행도 어제 시각까지 확인한다."""
    for t in times:
        hh, mm = map(int, t.split(":"))
        for day_offset in (0, -1):
            scheduled = (now + timedelta(days=day_offset)).replace(
                hour=hh, minute=mm, second=0, microsecond=0
            )
            if timedelta(0) <= now - scheduled < timedelta(minutes=WINDOW_MIN):
                return True
    return False


def get_dur_warning(med: dict) -> str:
    """병용 주의 데이터를 돌려준다.

    TODO(박채민): 공공데이터 DUR API 조회로 교체. 지금은 medicines.json의 dur_warning을 쓴다.
    """
    return med.get("dur_warning") or NO_DUR


def send_discord(text: str) -> None:
    if os.environ.get("DRY_RUN"):
        print("----- (DRY_RUN) 디스코드로 보낼 내용 -----")
        print(text)
        return
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
    # 디스코드 메시지는 2000자까지만 가능하다.
    resp = requests.post(url, json={"content": text[:2000]}, timeout=10)
    resp.raise_for_status()


def main() -> int:
    now = datetime.now(KST)
    test_mode = os.environ.get("TEST_MODE", "").lower() in ("1", "true")
    print(f"[{now:%Y-%m-%d %H:%M} KST] 실행 (test_mode={test_mode})")

    sent = failed = 0
    for med in load_medicines():
        if not (test_mode or is_due(med["times"], now)):
            continue
        name = med["name"]
        try:
            guide = generate_medicine_guide(name, med.get("info", ""), get_dur_warning(med))
        except Exception as e:  # AI가 실패해도 알림 자체는 보낸다
            print(f"AI 안내문 생성 실패 ({name}): {e}")
            guide = f"AI 안내문을 만들지 못했어요. 약 설명서를 확인해 주세요.\n{DISCLAIMER}"
        try:
            send_discord(f"💊 **{name}** 복용 시간이에요!\n\n{guide}")
            sent += 1
        except Exception as e:
            print(f"알림 발송 실패 ({name}): {e}")
            failed += 1

    print(f"완료: 발송 {sent}건, 실패 {failed}건")
    return 1 if failed else 0  # 실패가 있으면 Actions 실행이 빨간색으로 표시된다


if __name__ == "__main__":
    sys.exit(main())
