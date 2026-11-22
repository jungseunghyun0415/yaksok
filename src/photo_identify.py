"""약 사진에서 제품명만 읽어 낸다. 복용법 등 정보는 여기서 만들지 않는다."""
import json
import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPT = """사진 속 의약품 포장이나 알약에 적힌 '제품명'을 읽어 주세요.
- 사진에 실제로 보이는 글자만 근거로 하세요. 읽을 수 없으면 추측하지 말고 name을 null로 하세요.
- 약의 효능, 복용법 같은 설명은 하지 마세요.
- 아래 JSON 형식으로만 답하세요.
{"name": "제품명 또는 null", "reason": "읽은 근거를 한 줄로"}"""


def identify_drug_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
    )
    try:
        data = json.loads(response.text or "")
        name = data.get("name")
        if isinstance(name, str) and name.strip().lower() not in ("", "null", "none"):
            return {"name": name.strip(), "reason": str(data.get("reason", ""))}
        return {"name": None, "reason": str(data.get("reason", ""))}
    except (ValueError, AttributeError):
        return {"name": None, "reason": "AI 응답을 해석하지 못했어요"}
