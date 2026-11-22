"""디스코드 알림 전송 (로즈 작성 코드를 확장).

send_reminder(medicine_name, dosage, scheduled_time)는 예전 그대로 쓸 수 있고,
guide(AI 안내문)와 user_name을 주면 안내문까지 함께 보낸다.
"""
import os

import requests

EMBED_COLOR = 0x028090  # 약속 대표색(청록)


def send_reminder(medicine_name, dosage="", scheduled_time="", guide=None, user_name=None):
    # 웹훅 주소는 코드에 쓰지 않고 환경변수(GitHub Secrets)에서만 읽는다
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("Discord webhook URL is missing.")

    greeting = f"{user_name}님, 복용 시간이에요!" if user_name else "복용 시간이에요!"
    description = greeting if not guide else f"{greeting}\n\n{guide}"

    fields = [{"name": "약", "value": medicine_name, "inline": True}]
    if scheduled_time:
        fields.append({"name": "복용 시간", "value": scheduled_time, "inline": True})
    if dosage and dosage != "Not specified":
        fields.append({"name": "용량", "value": dosage, "inline": True})

    message = {
        "embeds": [
            {
                "title": "💊 약속 복약 알림",
                "description": description[:4000],  # 디스코드 embed 설명은 4096자까지
                "color": EMBED_COLOR,
                "fields": fields,
                "footer": {"text": "본 안내는 의학적 조언이 아닙니다. 처방과 약사·의사의 지도에 따라 복용하세요."},
            }
        ]
    }

    response = requests.post(webhook_url, json=message, timeout=15)
    response.raise_for_status()  # 전송 실패 시 오류를 내서 Actions가 빨간색으로 표시되게 한다
    print("Medication reminder sent successfully!")
