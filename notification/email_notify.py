"""이메일 알림 전송. Gmail은 평소 비밀번호가 아니라 '앱 비밀번호'를 써야 한다."""
import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, text: str) -> None:
    user = os.environ["EMAIL_USER"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = os.environ.get("EMAIL_TO") or user  # 받는 사람을 안 정하면 나에게 보낸다
    msg.set_content(text.replace("**", ""))  # 메일에는 굵게 표시 기호가 필요 없다
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(user, os.environ["EMAIL_PASSWORD"])
        smtp.send_message(msg)
