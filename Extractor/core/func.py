
from config import CHANNEL_ID, SUDO_USERS
from Extractor.core import script
from pyrogram.types import *
from Extractor.core.mongo.plans_db import premium_users


async def chk_user(query, user_id):
    # Removed premium user check; allow all users
    await query.answer("Access granted!")
    return 0


async def gen_link(app, chat_id):
    link = await app.export_chat_invite_link(chat_id)
    return link


async def subscribe(app, message):
    # Removed channel join check; allow all users
    return 0


async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""

        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1

        unit = ts[index:].lstrip()

        if value:
            value = int(value)

        return value, unit

    value, unit = extract_value_and_unit(time_string)

    if unit == 's':
        return value
    elif unit == 'min':
        return value * 60
    elif unit == 'hour':
        return value * 3600
    elif unit == 'day':
        return value * 86400
    elif unit == 'month':
        return value * 86400 * 30
    elif unit == 'year':
        return value * 86400 * 365
    else:
        return 0
