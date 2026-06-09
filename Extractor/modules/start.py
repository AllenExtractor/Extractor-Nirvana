import re
import random
from pyrogram import filters
from Extractor import app
from config import OWNER_ID, SUDO_USERS, CHANNEL_ID
from Extractor.core import script
from Extractor.core.func import subscribe, chk_user
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from Extractor.modules.classplus import classplus_txt
from Extractor.modules.exampur import exampur_txt
from Extractor.modules.appex_v3 import appex_v3_txt
from Extractor.modules.kdlive import kdlive
from Extractor.modules.pw import pw_login
from Extractor.modules.careerwill import career_will
from Extractor.modules.getappxotp import send_otp
from Extractor.modules.findapi import findapis_extract
from Extractor.modules.utk import handle_utk_logic
from Extractor.modules.iq import handle_iq_logic
from Extractor.modules.adda import adda_command_handler

log_channel = CHANNEL_ID


# Define the caption message
captionn = """<b>🔓 Don't pay for this bot — it's 100% FREE!</b><br>
Welcome to the <b>Free Txt Extractor Bot</b> 📂
<hr>

<b>📌 Join our official channel:</b><br>
👉 <a href="https://t.me/+5T4l-2VPfDo3Mjhl">Join Now</a>
<hr>

<b>🛠 Available Bot Commands:</b><br>
<blockquote>
/appx       - Master Appx Extraction
/appxlist   - Get Appx List
/appxotp    - Appx OTP Login
/adda       - Adda 247
/cp         - Classplus
/getapi     - Find Appx API
/iq         - Study IQ
/kd         - KD Campus
/khan       - Khan GS App
/pw         - Physics Wallah
/utkarsh    - Utkarsh
/ak         - Apni Kaksha
html        - for site (utkarsh only )
</blockquote>

<b>⚡owner/paid Tools (Without ID/Pass):</b><br>
<blockquote>
/cpfree     - CLASSPLUS FREE [9 txt per user/day]
/studyfull  - STUDY IQ Free (all user)
/cdsfreex   - cds without id pass (all user)
/cwc          - carrierwill without id pass (free with uploader)
/pen        - pinnacle without id pass
</blockquote>
"""

# Define the buttons for /start
start_buttons = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Join Now", url="https://t.me/+CLOrDhSK-ig1ODg1"),
            InlineKeyboardButton("Supports", url="https://t.me/king_rajasthan_23_bot")
        ]
    ]
)

@app.on_message(filters.command("start"))
async def start(_, message):
    join = await subscribe(_, message)
    if join == 1:
        return
    await message.reply_text(captionn, reply_markup=start_buttons)

@app.on_message(filters.command("apps"))
async def apps(_, message):
    await message.reply_photo(
        photo=random.choice(script.IMG),
        caption=captionn,
        reply_markup=start_buttons
    )

# Define ownerid at the module level  # Replace with your actual Telegram chat ID (integer)


@app.on_message(filters.command("appxotp"))
async def appxotp(app, message):
    api = await app.ask(message.chat.id, text="**SEND APPX API\n\n✅ Example:\ntcsexamzoneapi.classx.co.in**")
    api_txt = api.text
    name = api_txt.split('.')[0].replace("api", "") if api else api_txt.split('.')[0]
    if "api" in api_txt:
        await send_otp(app, message, api_txt)
    else:
        await app.send_message(message.chat.id, "INVALID INPUT IF YOU DONT KNOW API GO TO FIND API OPTION")
      

@app.on_callback_query()
async def handle_callback(_, query):
    if query.data == "home_":
        await query.message.delete(True)

    elif query.data == "maintainer_":
        await query.answer("sᴏᴏɴ.... \n ʙᴏᴛ ᴜɴᴅᴇʀ ɪɴ ᴍᴀɪɴᴛᴀɪɴᴀɴᴄᴇ ", show_alert=True)

    elif query.data == "my_":
        await my_pathshala_login(app, query.message)

    elif query.data == "findapi_":
        await findapis_extract(app, query.message)

    elif query.data == "kdlive_":
        await kdlive(app, query.message)

    elif query.data == "careerwill_":
        await career_will(app, query.message)

  

    elif query.data == "pw_":
        await pw_login(app, query.message)

    elif query.data == "classplus_":
        await classplus_txt(app, query.message)

    elif query.data == "close_data":
        await query.message.delete()
        await query.message.reply_to_message.delete()
