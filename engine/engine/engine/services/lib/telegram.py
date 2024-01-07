import os
import threading

from engine.services.log import logs
from requests import post

chat_id = os.environ.get("TELEGRAM_ENGINE_CHAT_ID")
bot_token = os.environ.get("TELEGRAM_ENGINE_TOKEN")


def telegram_send(status, message):
    """
    Sends Telegram message
    """
    if not chat_id or not bot_token:
        return None
    message = f'<b>{status}</b>: <b><a href="https://{os.environ.get("DOMAIN")}">{os.environ.get("DOMAIN")}</a></b>\n{message}'
    query = None
    try:
        query = post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={
                "chat_id": [chat_id],
                "text": message,
                "parse_mode": "html",
            },
        )
    except Exception as e:
        logs.main.error("Telegram notification error: %s", e)
    return query


def telegram_send_thread(status, message):
    """
    Sends Telegram message with function telegram_send in thread
    """
    t = threading.Thread(target=telegram_send, args=(status, message))
    t.start()
    return t
