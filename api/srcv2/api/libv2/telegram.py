# ~ import schedule
import requests
import time

def tsend(bot_message):
    print(bot_message)    
    return True
    bot_token = '1116693240:AAFo_H5L0nSFruZVSMW4Zl5EmQXtDCyG2MU'
    bot_chatID = '451903641'
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message

    response = requests.get(send_text)

    return response.json()


# ~ def report():
    # ~ my_balance = 10   ## Replace this number with an API call to fetch your account balance
    # ~ my_message = "Current balance is: {}".format(my_balance)   ## Customize your message
    # ~ telegram_bot_sendtext(my_message)


    
# ~ schedule.every().day.at("12:00").do(report)

# ~ while True:
    # ~ schedule.run_pending()
    # ~ telegram_bot_sendtext('running')
    # ~ time.sleep(1)
    
