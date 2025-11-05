from django.core.mail import EmailMessage

def send_with_attachment(to_email: str, subject: str, body: str, attachments: list[str]):
    msg = EmailMessage(subject=subject, body=body, to=[to_email])
    for path in attachments:
        msg.attach_file(path)
    msg.send()
