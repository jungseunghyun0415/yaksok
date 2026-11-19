import os
import time
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()  # .env의 키를 환경변수로 등록

BASE_URL = "https://apis.data.go.kr/1471000/DURPrdlstInfoService03"
EASY_DRUG_URL = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService"


# ───────────── DUR API (병용금기) ─────────────
def _call(operation: str, **params) -> list[dict]:
    """DUR API를 호출해 item 리스트를 반환합니다. (키가 에러 메시지에 노출되지 않게 처리)"""
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        raise ValueError("DATA_GO_KR_KEY 환경변수가 설정되지 않았습니다.")

    query = {"serviceKey": key, "type": "json", "pageNo": 1, "numOfRows": 50, **params}

    last_err = None
    for attempt in range(3):  # 최대 3번 시도
        try:
            res = requests.get(f"{BASE_URL}/{operation}", params=query, timeout=30)
            res.raise_for_status()
            break
        except requests.RequestException as e:
            last_err = type(e).__name__
            if attempt < 2:
                print(f"DUR API 응답 지연({last_err}), 재시도합니다... ({attempt + 1}/2)")
                time.sleep(3)
    else:
        raise RuntimeError(f"DUR API 호출 실패: {last_err}") from None

    try:
        data = res.json()
    except ValueError:
        raise RuntimeError(
            "DUR API 응답이 JSON이 아닙니다. 인증키(Decoding)와 활용신청 승인 상태를 확인하세요."
        ) from None

    header = data.get("header") or {}
    code = header.get("resultCode")
    if code and code not in ("00", "03"):  # 00 정상, 03 데이터 없음
        raise RuntimeError(f"DUR API 오류 코드 {code}: {header.get('resultMsg')}")

    items = (data.get("body") or {}).get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items


def get_usjnt_taboo_text(item_name: str, max_items: int = 10) -> str:
    """품목명으로 병용금기 정보를 조회해 프롬프트에 넣을 텍스트로 변환합니다."""
    items = _call("getUsjntTabooInfoList03", itemName=item_name)

    if not items:
        return (
            "DUR 병용금기 데이터가 조회되지 않았음 "
            "(등록된 정보가 없다는 뜻일 뿐, 안전하다는 의미가 아님)."
        )

    lines, seen = [], set()
    for it in items:
        mixture = it.get("MIXTURE_INGR_KOR_NAME")
        reason = it.get("PROHBT_CONTENT")
        if (mixture, reason) in seen:
            continue
        seen.add((mixture, reason))
        lines.append(
            f"- {it.get('INGR_KOR_NAME')}과(와) {mixture}은(는) 함께 복용 금지: {reason}"
        )
        if len(lines) >= max_items:
            break
    return "\n".join(lines)


# ───────────── e약은요 API (효능·용법) ─────────────
def get_drug_info_text(item_name: str) -> str | None:
    """e약은요 API에서 약의 효능·용법·주의사항을 조회해 텍스트로 만듭니다. 없으면 None."""
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        raise ValueError("DATA_GO_KR_KEY 환경변수가 설정되지 않았습니다.")

    query = {
        "serviceKey": key, "type": "json",
        "pageNo": 1, "numOfRows": 3, "itemName": item_name,
    }

    last_err = None
    for attempt in range(3):
        try:
            res = requests.get(
                f"{EASY_DRUG_URL}/getDrbEasyDrugList", params=query, timeout=30
            )
            res.raise_for_status()
            break
        except requests.RequestException as e:
            last_err = type(e).__name__
            if attempt < 2:
                print(f"약 정보 API 응답 지연({last_err}), 재시도합니다... ({attempt + 1}/2)")
                time.sleep(3)
    else:
        raise RuntimeError(f"약 정보 API 호출 실패: {last_err}") from None

    try:
        data = res.json()
    except ValueError:
        raise RuntimeError("약 정보 API 응답이 JSON이 아닙니다. 인증키를 확인하세요.") from None

    items = (data.get("body") or {}).get("items") or []
    if not items:
        return None  # 조회 결과 없음

    it = items[0]  # 첫 번째 결과 사용
    parts = []
    if it.get("efcyQesitm"):        # 효능
        parts.append(f"- 효능·효과: {it['efcyQesitm']}")
    if it.get("useMethodQesitm"):   # 사용법
        parts.append(f"- 사용법: {it['useMethodQesitm']}")
    if it.get("atpnQesitm"):        # 주의사항
        parts.append(f"- 주의사항: {it['atpnQesitm']}")
    if it.get("intrcQesitm"):       # 상호작용
        parts.append(f"- 상호작용: {it['intrcQesitm']}")
    if it.get("seQesitm"):          # 부작용
        parts.append(f"- 부작용: {it['seQesitm']}")
    return "\n".join(parts) if parts else None


# ───────────── Gemini ─────────────
def generate_medicine_guide(
    medicine_name: str, medicine_info: str, dur_warning: str
) -> str:
    """약 기본 정보와 DUR 데이터를 받아 '약속' AI 도우미의 복약 안내문을 생성합니다."""
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
6. 병용 주의 데이터가 없거나 조회되지 않았더라도 "안전하다"고 단정하지 말고, 약사나 의사에게 확인하도록 안내할 것.
"""

    model = "gemini-3.5-flash-lite"

    for attempt in range(4):  # 서버 혼잡 시 최대 4번 시도
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text
        except errors.ServerError:  # 5xx 일시 오류만 재시도
            if attempt == 3:
                raise
            wait = 2 ** attempt * 3  # 3, 6, 12초 대기
            print(f"Gemini 서버가 혼잡합니다. {wait}초 후 재시도합니다... ({attempt + 1}/3)")
            time.sleep(wait)


# ───────────── 실행 ─────────────
if __name__ == "__main__":
    product_name = input("약 이름(제품명)을 입력하세요: ").strip()

    if not product_name:
        print("약 이름을 입력하지 않았습니다. 프로그램을 종료합니다.")
        raise SystemExit

    print(f"\n'{product_name}' 정보를 조회 중입니다...\n")

    # 효능·용법을 e약은요 API에서 조회
    drug_info = get_drug_info_text(product_name)
    if not drug_info:
        drug_info = (
            "해당 약의 기본 정보가 조회되지 않았습니다. "
            "약 이름(제품명)을 정확히 입력했는지 확인하세요."
        )

    # DUR 병용금기 조회
    dur_text = get_usjnt_taboo_text(product_name)
    dur_warning = f"[DUR 병용금기]\n{dur_text}"

    print(generate_medicine_guide(product_name, drug_info, dur_warning))