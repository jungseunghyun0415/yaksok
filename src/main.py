"""약속: 복용 시간이 된 약을 찾아 AI 안내문을 만들고 알림(디스코드/이메일)으로 보낸다.

- GitHub Actions가 30분마다 실행한다:  python src/main.py
- 화면(gui/yaksok_gui.py)도 이 파일의 process()를 그대로 불러 쓴다.
- 로컬 테스트:  TEST_MODE=1 DRY_RUN=1 python src/main.py

알림 채널은 환경변수(= GitHub Secrets / 화면의 설정)가 있는 쪽으로 자동 선택된다. 둘 다 있으면 둘 다 보낸다.
    디스코드: DISCORD_WEBHOOK_URL
    이메일  : EMAIL_USER, EMAIL_PASSWORD (+ 선택: EMAIL_TO, SMTP_HOST, SMTP_PORT)
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 레포 맨 위의 notification 폴더를 찾기 위해

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "yaksok" / "src"))  # 박채민의 durprompt.py 위치

try:  # 박채민 durprompt(DUR 연동 프롬프트)를 우선 쓰고, 불러올 수 없으면 김준우 ai_analyzer로 대신한다
    import durprompt  # noqa: E402
    from durprompt import generate_medicine_guide  # noqa: E402
except Exception as _e:  # noqa: BLE001  (python-dotenv 미설치 등)
    print(f"durprompt를 불러오지 못해 ai_analyzer를 사용합니다: {type(_e).__name__}: {_e}")
    durprompt = None
    from ai_analyzer import generate_medicine_guide  # noqa: E402
from drug_db import lookup_info  # noqa: E402  약 데이터(CSV)에서 제품명·제조사·주성분 찾기
from notification.discord_notify import send_reminder  # noqa: E402  로즈 모듈
from notification.email_notify import send_email  # noqa: E402
from schedule_store import in_period, load_schedule  # noqa: E402  복용 일정 읽기, 복용 기간 확인

KST = ZoneInfo("Asia/Seoul")

# cron 간격과 같게 유지한다. 실행이 조금 늦어져도 같은 알림이 두 번 가지 않게 하기 위함이다.
WINDOW_MIN = 30
NO_DUR = "(조회된 병용 주의 데이터가 없습니다)"
DISCLAIMER = "※ 본 안내는 의학적 조언이 아니며, 정확한 상담은 약사·의사와 진행하세요."


def due_time(med: dict, now: datetime) -> str | None:
    """지금 알려야 하면 해당 복용 시각("09:00")을, 아니면 None을 돌려준다.

    복용 시각 이후 WINDOW_MIN분 안이고, 그 날짜가 복용 기간(시작일~종료일) 안이어야 한다.
    자정 직후 실행도 어제 밤 시각까지 확인한다.
    """
    for t in med.get("times", []):
        hh, mm = map(int, t.split(":"))
        for day_offset in (0, -1):
            scheduled = (now + timedelta(days=day_offset)).replace(
                hour=hh, minute=mm, second=0, microsecond=0
            )
            if timedelta(0) <= now - scheduled < timedelta(minutes=WINDOW_MIN) and in_period(
                med, scheduled.date()
            ):
                return t
    return None


def is_due(med: dict, now: datetime) -> bool:
    return due_time(med, now) is not None


def get_dur_warning(med: dict) -> str:
    """병용 주의 데이터를 돌려준다.

    일정에 적어 둔 dur_warning이 있으면 그것을 쓰고, 없으면 공공데이터 DUR API(durprompt)로 조회한다.
    DATA_GO_KR_KEY가 없거나 조회에 실패하면 "조회된 데이터 없음" 문구를 돌려준다.
    TODO(박채민): data/dur_combination_clean.csv로 등록된 약들끼리의 병용금기 조합 확인.
    """
    if med.get("dur_warning"):
        return med["dur_warning"]
    if durprompt and os.environ.get("DATA_GO_KR_KEY"):
        try:
            return f"[DUR 병용금기]\n{durprompt.get_usjnt_taboo_text(med['name'])}"
        except Exception as e:  # noqa: BLE001
            print(f"DUR 조회 실패 ({med.get('name')}): {type(e).__name__}")
    return NO_DUR


# ---------------------------------------------------------------- 알림 채널
def channels() -> list[str]:
    found = []
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        found.append("디스코드")
    if os.environ.get("EMAIL_USER") and os.environ.get("EMAIL_PASSWORD"):
        found.append("이메일")
    return found


def notify(name: str, time_label: str, user: str, guide: str) -> list[str]:
    """설정된 모든 채널로 보낸다. 일부만 실패한 채널 이름을 돌려주고, 전부 실패하면 오류를 낸다."""
    greeting = f"{user}님, " if user else ""
    if os.environ.get("DRY_RUN"):
        print(f"----- (DRY_RUN) 보낼 내용: {name} / {time_label} -----")
        print(f"💊 {greeting}{name} 복용 시간이에요!\n\n{guide}")
        return []
    active = channels()
    if not active:
        raise ValueError("알림 채널이 없습니다. DISCORD_WEBHOOK_URL 또는 EMAIL_USER/EMAIL_PASSWORD를 설정하세요.")
    failed = []
    for ch in active:
        try:
            if ch == "디스코드":
                send_reminder(medicine_name=name, scheduled_time=time_label, guide=guide, user_name=user or None)
            else:
                send_email(f"[약속] {name} 복용 시간이에요", f"💊 {greeting}{name} 복용 시간이에요! ({time_label})\n\n{guide}")
        except Exception as e:  # noqa: BLE001
            print(f"{ch} 전송 실패: {type(e).__name__}: {e}")
            failed.append(f"{ch}: {type(e).__name__}: {e}")
    if len(failed) == len(active):
        raise RuntimeError("모든 알림 채널로 보내지 못했습니다. " + " / ".join(failed))
    return failed


# ---------------------------------------------------------------- 실행
def process(data: dict, now: datetime, test_mode: bool = False) -> dict:
    """일정(data)에서 알릴 약을 골라 안내문을 만들고 보낸다.

    돌려주는 값: {"sent": 보낸 수, "failed": 실패 수, "errors": [...], "warnings": [...], "channels": [...]}
    """
    user = data.get("user_name", "").strip()
    result = {"sent": 0, "failed": 0, "errors": [], "warnings": [], "channels": channels()}
    for med in data["medicines"]:
        matched = due_time(med, now)
        if not (test_mode or matched):
            continue
        name = med["name"]
        time_label = matched or f"{now:%H:%M} (테스트)"
        info = med.get("info") or lookup_info(name)  # 일정에 정보가 없으면 약 데이터(CSV)에서 찾는다
        try:
            guide = generate_medicine_guide(name, info, get_dur_warning(med))
        except Exception as e:  # noqa: BLE001  AI가 실패해도 알림 자체는 보낸다
            print(f"AI 안내문 생성 실패 ({name}): {type(e).__name__}: {e}")
            result["warnings"].append(f"AI 안내문을 만들지 못해 기본 문구로 보냈어요: {e}")
            guide = f"AI 안내문을 만들지 못했어요. 약 설명서를 확인해 주세요.\n{DISCLAIMER}"
        try:
            result["warnings"] += notify(name, time_label, user, guide)
            result["sent"] += 1
        except Exception as e:  # noqa: BLE001
            print(f"알림 발송 실패 ({name}): {e}")
            result["failed"] += 1
            result["errors"].append(f"{name}: {e}")
    return result


def main() -> int:
    now = datetime.now(KST)
    test_mode = os.environ.get("TEST_MODE", "").lower() in ("1", "true")
    print(f"[{now:%Y-%m-%d %H:%M} KST] 실행 (test_mode={test_mode}, 알림 채널={channels() or '없음'})")
    data = load_schedule()
    print(f"등록된 약 {len(data['medicines'])}개")
    r = process(data, now, test_mode)
    print(f"완료: 발송 {r['sent']}건, 실패 {r['failed']}건")
    return 1 if r["failed"] else 0  # 실패가 있으면 Actions 실행이 빨간색으로 표시된다


def run_gui() -> int:
    """창(GUI)을 띄운다. gui/ 폴더가 없거나 패키지가 없으면 안내만 하고 끝낸다."""
    gui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui")
    if gui_dir not in sys.path:
        sys.path.insert(0, gui_dir)
    try:
        import yaksok_gui
    except ImportError as e:
        print(f"GUI를 열 수 없습니다: {e}\n -> pip install -r gui/requirements.txt 를 먼저 실행하세요.")
        return 1
    yaksok_gui.main()
    return 0


def headless() -> bool:
    """GitHub Actions나 테스트 환경이면 창 없이 알림만 처리한다."""
    env = os.environ
    return bool(env.get("GITHUB_ACTIONS") or env.get("TEST_MODE") or env.get("DRY_RUN")) or "--notify" in sys.argv


if __name__ == "__main__":
    # 내 컴퓨터에서 python src/main.py -> 창이 열린다.
    # GitHub Actions(또는 --notify, TEST_MODE, DRY_RUN) -> 창 없이 알림 처리.
    sys.exit(main() if headless() else run_gui())