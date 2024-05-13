#!/usr/bin/env python3
import requests
from rethinkdb import r

chat_id = None
bot_token = None

dbconn = r.connect("isard-db", 28015, "isard").repl()


def telegram_send(chat_id, bot_token, message):
    """
    Sends Telegram message
    """
    if not chat_id or not bot_token:
        print(message)
        return None
    message = f"<b>QUERY MSG</b>: \n{message}"
    query = None
    try:
        query = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={
                "chat_id": [chat_id],
                "text": message,
                "parse_mode": "html",
            },
            timeout=10,
        )
    except Exception as e:
        print("Telegram notification error: %s", e)
    return query


telegram_send(chat_id, bot_token, "Starting query duration monitoring")
for c in r.db("rethinkdb").table("jobs").changes().run(dbconn):
    if c.get("new_val") is None:
        continue
    try:
        if "changes" in c["new_val"]["info"]["query"]:
            # Skip changes
            continue
        if c["new_val"]["duration_sec"] > 15 and c["new_val"]["duration_sec"] <= 16:
            telegram_send(
                chat_id,
                bot_token,
                f'INFO: Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
        if c["new_val"]["duration_sec"] > 30 and c["new_val"]["duration_sec"] <= 31:
            telegram_send(
                chat_id,
                bot_token,
                f'WARNING!!! Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
        if c["new_val"]["duration_sec"] > 60 and c["new_val"]["duration_sec"] <= 61:
            telegram_send(
                chat_id,
                bot_token,
                f'WARNING!!! Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
        if c["new_val"]["duration_sec"] > 90 and c["new_val"]["duration_sec"] <= 91:
            telegram_send(
                chat_id,
                bot_token,
                f'WARNING!!! Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
        if c["new_val"]["duration_sec"] > 120 and c["new_val"]["duration_sec"] <= 121:
            telegram_send(
                chat_id,
                bot_token,
                f'WARNING!!! Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
        if c["new_val"]["duration_sec"] > 150:
            telegram_send(
                chat_id,
                bot_token,
                f'WARNING!!! Id: {c["new_val"]["id"][1]} \nDuration: {c["new_val"]["duration_sec"]}  \nQuery: {c["new_val"]["info"]["query"]}',
            )
    except:
        pass
