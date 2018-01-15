#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.error import Unauthorized
import logging
import sqlite3
import re
import requests
from os import environ
import falcon

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
dbc.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY)')
db.commit()

def start(bot, update):
    update.message.reply_text('Hi! Please send us your pairing code.')

def is_registered_chat(chat_id):
    dbc.execute('SELECT chat_id FROM chats WHERE chat_id = ?', (chat_id,))
    return dbc.fetchone() is not None

def add_registered_chat(chat_id):
    dbc.execute('INSERT INTO chats VALUES (?)', (chat_id,))
    db.commit()

def del_registered_chat(chat_id):
    dbc.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
    db.commit()

def msg_received(bot, update):
    chat_id = update.message.chat.id
    pairing_code_raw = update.message.text.replace(' ', '').strip()
    if is_registered_chat(chat_id):
        update.message.reply_text('You are subscribed to the notifications of an ID printing account. To unsubscribe, send /unsub.')
    elif pairing_code_regex.fullmatch(pairing_code_raw):
        update.message.reply_text('Verifying...')
        r = requests.post(environ['IDPRINTING_ENDPOINT'] + '/api/pair', data = {
            'secret': environ['IDPRINTING_SHARED_SECRET'],
            'chat_id': chat_id,
            'pairing_code': pairing_code_raw
        })

        try:
            result = r.json()
        except ValueError:
            update.message.reply_text('An internal error occurred. Sorry 🙁')
            return
        
        if 'success' in result:
            add_registered_chat(chat_id)
            update.message.reply_text('Linking successful! 👍\nYou will now receive notifications about your orders.')
        else:
            update.message.reply_text('An error occurred. Sorry 🙁\n\n' + result['error'])
        
    else:
        update.message.reply_text('That doesn\'t look like a pairing code.\n\nPlease send us your pairing code.')

def unsub(bot, update):
    chat_id = update.message.chat.id
    if is_registered_chat(chat_id):
        del_registered_chat(chat_id)
        update.message.reply_text('You have been unsubscribed from all notifications.')
    else:
        update.message.reply_text('Sorry, our records show you are not subscribed to any ID printing account\'s notifications.')

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"', update, error)

"""Start the bot."""
# Create the EventHandler and pass it your bot's token.
if 'TELEGRAM_TOKEN' not in environ:
    print('TELEGRAM_TOKEN not in environment variables.')
    exit(1)

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
# updater.start_polling()

class NotifyResource:
    def on_post(self, req, resp):
        if environ['IDPRINTING_SHARED_SECRET'] != req.media.get('secret'):
            resp.media = { 'error': 'Secret not correct.', 'errorCode': 1 }
            return
        
        if 'chat_id' not in req.media or 'notification' not in req.media:
            resp.media = { 'error': 'chat_id or notification not specified', 'errorCode': 2 }
            return

        chat_id = int(req.media.get('chat_id'))
        notification = str(req.media.get('notification'))
        notification_len = len(notification)

        if is_registered_chat(chat_id):
            if notification_len > 0 and notification_len <= 4096:
                try:
                    updater.bot.send_message(chat_id=chat_id, text=notification)
                    resp.media = { 'success': True }
                except Unauthorized:
                    resp.media = { 'error': 'Chat ID not registered.', 'errorCode': 4 }
                    del_registered_chat(chat_id)
            else:
                resp.media = { 'error': 'Message too long.', 'errorCode': 3 }
        else:
            resp.media = { 'error': 'Chat ID not registered.', 'errorCode': 4 }

class IsRegisteredResource:
    def on_post(self, req, resp):
        if environ['IDPRINTING_SHARED_SECRET'] != req.media.get('secret'):
            resp.media = { 'error': 'Secret not correct.', 'errorCode': 1 }
            return
        
        if 'chat_id' not in req.media:
            resp.media = { 'error': 'chat_id not specified', 'errorCode': 2 }
            return

        chat_id = int(req.media.get('chat_id'))

        resp.media = { 'result': is_registered_chat(chat_id) }

class UnpairResource:
    def on_post(self, req, resp):
        if environ['IDPRINTING_SHARED_SECRET'] != req.media.get('secret'):
            resp.media = { 'error': 'Secret not correct.', 'errorCode': 1 }
            return
        
        if 'chat_id' not in req.media:
            resp.media = { 'error': 'chat_id not specified', 'errorCode': 2 }
            return

        chat_id = int(req.media.get('chat_id'))

        resp.media = { 'success': True }

        if is_registered_chat(chat_id):
            del_registered_chat(chat_id)
            try:
                updater.bot.send_message(chat_id=chat_id, text='You have been unsubscribed from all notifications.')
            except Unauthorized:
                pass

class WakeMyDynoResource:
    def on_get(self, req, resp):
        resp.content_type = falcon.MEDIA_TEXT
        resp.body = 'hello'

api = falcon.API()
api.add_route('/notify', NotifyResource())
api.add_route('/is_registered', IsRegisteredResource())
api.add_route('/unpair', UnpairResource())
api.add_route('/wakemydyno.txt', WakeMyDynoResource())
