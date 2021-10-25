import time

import requests

from webapp import app

bot_token = app.config["TELEGRAM_BOT_TOKEN"]
bot_chatID = app.config["TELEGRAM_BOT_CHAT_ID"]
hostname = app.config["HOSTNAME"]


def tsend(bot_message):
    if bot_token and bot_chatID:
        bot_message = hostname + ": " + bot_message
        send_text = (
            "https://api.telegram.org/bot"
            + bot_token
            + "/sendMessage?chat_id="
            + bot_chatID
            + "&parse_mode=Markdown&text="
            + bot_message
        )
        response = requests.get(send_text)
        return response.json()
    return False
