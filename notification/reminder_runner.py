"""(호환용) 예전 실행 파일.

알림 시각 판단·AI 안내문·전송 로직은 src/main.py 하나로 합쳤다.
이 파일을 실행해도 같은 일이 일어난다:  python notification/reminder_runner.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
