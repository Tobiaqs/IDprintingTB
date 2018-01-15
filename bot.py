#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging
import sqlite3
import re
import requests
from os import environ

if 'IDPRINTING_ENDPOINT' not in environ or 'IDPRINTING_SHARED_SECRET' not in environ:
    print('Gosh darn it. IDPRINTING_ENDPOINT and/or IDPRINTING_SHARED_SECRET are not in the environment variables.')
    exit(1)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

pairing_code_regex = re.compile('^[0-9]{8}$')

db = sqlite3.connect('bot.db', check_same_thread=False)
dbc = db.cursor()
dbc.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, pairing_code INTEGER)')
db.commit()

def start(bot, update):
    update.message.reply_text('Hi! Please send us your pairing code.')

def is_registered_user(user_id):
    dbc.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    return dbc.fetchone() is not None

def add_registered_user(user_id, pairing_code):
    dbc.execute('INSERT INTO users VALUES (?, ?)', (user_id, pairing_code))
    db.commit()

def del_registered_user(user_id):
    dbc.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    db.commit()

def msg_received(bot, update):
    user = update.message.from_user
    if is_registered_user(user.id):
        update.message.reply_text('You are subscribed to the notifications of an ID printing account. To unsubscribe, send /unsub.')
    elif pairing_code_regex.fullmatch(update.message.text.strip()):
        pairing_code_raw = update.message.text.strip()
        update.message.reply_text('Verifying...')
        r = requests.post(environ['IDPRINTING_ENDPOINT'] + '/api/pair', data = {
            'secret': environ['IDPRINTING_SHARED_SECRET'],
            'telegram_id': user.id,
            'pairing_code': pairing_code_raw
        })

        print(r.json())
    else:
        update.message.reply_text('That doesn\'t look like a pairing code.\n\nPlease send us your pairing code.')

def unsub(bot, update):
    user = update.message.from_user
    if is_registered_user(user.id):
        del_registered_user(user.id)
        update.message.reply_text('You have been unsubscribed from all notifications.')
    else:
        update.message.reply_text('Sorry, our records show you are not subscribed to any ID printing account\'s notifications.')

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"', update, error)

def main():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    if not 'TELEGRAM_TOKEN' in environ:
        print('TELEGRAM_TOKEN not in environment variables.')
        exit(1)
        return

    updater = Updater(environ['TELEGRAM_TOKEN'])

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("unsub", unsub))

    # on noncommand i.e message - echo the message on Telegram
    dp.add_handler(MessageHandler(Filters.text, msg_received))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()
