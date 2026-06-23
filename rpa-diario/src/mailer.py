import os
import smtplib
import mimetypes
from email.message import EmailMessage


def _as_list(value):
    if not value:
        return []

    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value).split(",")

    return [str(x).strip() for x in items if str(x).strip()]


def send_smtp_mail(
    smtp_host,
    smtp_port,
    smtp_user,
    smtp_pass,
    mail_from,
    mail_to,
    subject,
    body_text,
    attachment_path=None,
    mail_cc=None,
):
    to_list = _as_list(mail_to)
    cc_list = _as_list(mail_cc)

    if not to_list and not cc_list:
        raise ValueError("No hay destinatarios configurados en mail_to/mail_cc")

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_list)

    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg["Subject"] = subject
    msg.set_content(body_text or "")

    if attachment_path and os.path.exists(attachment_path):
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"

        maintype, subtype = ctype.split("/", 1)

        with open(attachment_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(attachment_path),
            )

    recipients = to_list + cc_list
    smtp_port = int(smtp_port or 587)

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=60) as smtp:
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg, from_addr=mail_from, to_addrs=recipients)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg, from_addr=mail_from, to_addrs=recipients)
