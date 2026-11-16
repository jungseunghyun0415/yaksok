import os
from google import genai


def generate_medicine_guide(
    medicine_name: str, medicine_info: str, dur_warning: str
) -> str:
    """약 기본 정보와 DUR 병용금기 데이터를 받아 '약속' AI 도우미의 복약 안내문을 생성합니다."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)

    prompt = f"""당신은 복용 알림 및 병용 주의 안내 서비스인 '약속'의 친절한 AI 도우미입니다.
어려운 의약품 정보를 일반인이 이해하기 쉽게 설명해 주세요.
반드시 아래 제공된 [복용 약 정보]와 [병용 주의 데이터]에 있는 사실만 바탕으로 답변하고, 데이터에 없는 내용을 추측해서 지어내지 마세요.

[복용 약 이름]
{medicine_name}

[복용 약 정보]
{medicine_info}

[병용 주의 데이터 (DUR 및 사용상의 주의사항)]
{dur_warning}

[작성 규칙]
1. 첫인사는 "안녕하세요, 복용 알림 및 병용 주의 안내 서비스 '약속'의 AI 도우미입니다!"로 시작할 것.
2. 어려운 의학 용어는 일상적인 쉬운 단어로 풀어서 핵심 복용법만 요약할 것.
3. 숫자 범위를 표기할 때 취소선 오류가 나지 않도록 물결표(~) 대신 '1-2알' 또는 '1알에서 2알' 형태로 작성할 것.
4. 함께 먹으면 안 되는 약이나 주의해야 할 점(음주, 중복 복용 등)을 눈에 띄게 강조할 것.
5. 안내문 마지막 줄에는 반드시 "※ 본 안내는 의학적 조언이 아니며, 정확한 상담은 약사·의사와 진행하세요."라는 문구를 포함할 것.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text


if __name__ == "__main__":
    sample_name = "아세트아미노펜 500mg"
    sample_info = (
        "- 유효성분: 아세트아미노펜 500mg\n"
        "- 효능·효과: 감기로 인한 발열 및 통증, 두통, 신경통, 근육통, 월경통, 염좌통, 치통, 관절통\n"
        "- 용법·용량: 만 12세 이상 소아 및 성인 1회 1정에서 2정씩, 1일 3회에서 4회 (4시간에서 6시간마다) 필요시 복용. "
        "1일 최대 4그램(8정)을 초과하여 복용하지 말 것."
    )
    sample_dur = (
        "- 매일 세 잔 이상 정기적으로 술을 마시는 사람이 이 약이나 다른 해열진통제를 복용해야 할 경우 반드시 의사 또는 약사와 상의해야 함 (간손상 유발 가능).\n"
        "- 아세트아미노펜을 포함하는 다른 제품과 함께 복용하지 말 것 (일일 최대용량 4,000mg 초과 시 간손상 위험)."
    )

    print(generate_medicine_guide(sample_name, sample_info, sample_dur))
