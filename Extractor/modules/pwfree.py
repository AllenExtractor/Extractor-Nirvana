import os
import json
import asyncio
import aiohttp
import logging
import zipfile
import time
import requests
from pyrogram import filters
from Extractor import app
from config import CHANNEL_ID
import re
import aiofiles

txt_dump = CHANNEL_ID
appname = "Physics Wallah"

async def sanitize_bname(bname, max_length=50):
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', bname).strip()
    if len(bname) > max_length:
        bname = bname[:max_length]
    return bname

async def fetch_pwwp_data(session: aiohttp.ClientSession, url: str, headers: dict = None, params: dict = None, data: dict = None, method: str = 'GET') -> any:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.request(method, url, headers=headers, params=params, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Attempt {attempt + 1} failed: aiohttp error fetching {url}: {e}")
        except Exception as e:
            logging.exception(f"Attempt {attempt + 1} failed: Unexpected error fetching {url}: {e}")
        if attempt < max_retries - 1:
            await asyncio.sleep(90 ** attempt)
        else:
            logging.error(f"Failed to fetch {url} after {max_retries} attempts.")
            return None

async def process_pwwp_chapter_content(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, schedule_id, content_type, headers: dict):
    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_pwwp_data(session, url, headers=headers)
    content = []
    if data and data.get("success") and data.get("data"):
        data_item = data["data"]
        if content_type in ("videos", "DppVideos"):
            video_details = data_item.get('videoDetails', {})
            if video_details:
                name = data_item.get('topic', '')
                videoUrl = video_details.get('videoUrl') or video_details.get('embedCode') or ""
                if videoUrl:
                    line = f"{name}:{videoUrl}"
                    content.append(line)
        elif content_type in ("notes", "DppNotes"):
            homework_ids = data_item.get('homeworkIds', [])
            for homework in homework_ids:
                attachment_ids = homework.get('attachmentIds', [])
                name = homework.get('topic', '')
                for attachment in attachment_ids:
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url:
                        line = f"{name}:{url}"
                        content.append(line)
        return {content_type: content} if content else {}
    else:
        logging.warning(f"No Data Found For  Id - {schedule_id}")
        return {}

async def fetch_pwwp_all_schedule(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, content_type, headers: dict) -> list[dict]:
    all_schedule = []
    page = 1
    while True:
        params = {
            'tag': chapter_id,
            'contentType': content_type,
            'page': page
        }
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/contents"
        data = await fetch_pwwp_data(session, url, headers=headers, params=params)
        if data and data.get("success") and data.get("data"):
            for item in data["data"]:
                item['content_type'] = content_type
                all_schedule.append(item)
            page += 1
        else:
            break
    return all_schedule

async def process_pwwp_chapters(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, headers: dict):
    content_types = ['videos', 'notes', 'DppNotes', 'DppVideos']
    all_schedule_tasks = [fetch_pwwp_all_schedule(session, chapter_id, selected_batch_id, subject_id, content_type, headers) for content_type in content_types]
    all_schedules = await asyncio.gather(*all_schedule_tasks)
    all_schedule = []
    for schedule in all_schedules:
        all_schedule.extend(schedule)
    content_tasks = [
        process_pwwp_chapter_content(session, chapter_id, selected_batch_id, subject_id, item["_id"], item['content_type'], headers)
        for item in all_schedule
    ]
    content_results = await asyncio.gather(*content_tasks)
    combined_content = {}
    for result in content_results:
        if result:
            for content_type, content_list in result.items():
                if content_type not in combined_content:
                    combined_content[content_type] = []
                combined_content[content_type].extend(content_list)
    return combined_content

async def get_pwwp_all_chapters(session: aiohttp.ClientSession, selected_batch_id, subject_id, headers: dict):
    all_chapters = []
    page = 1
    while True:
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/topics?page={page}"
        data = await fetch_pwwp_data(session, url, headers=headers)
        if data and data.get("data"):
            chapters = data["data"]
            all_chapters.extend(chapters)
            page += 1
        else:
            break
    return all_chapters

async def process_pwwp_subject(session: aiohttp.ClientSession, subject: dict, selected_batch_id: str, selected_batch_name: str, zipf: zipfile.ZipFile, json_data: dict, all_subject_urls: dict[str, list[str]], headers: dict):
    subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
    subject_id = subject.get("_id")
    json_data[selected_batch_name][subject_name] = {}
    zipf.writestr(f"{subject_name}/", "")
    chapters = await get_pwwp_all_chapters(session, selected_batch_id, subject_id, headers)
    chapter_tasks = []
    for chapter in chapters:
        chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")
        zipf.writestr(f"{subject_name}/{chapter_name}/", "")
        json_data[selected_batch_name][subject_name][chapter_name] = {}
        chapter_tasks.append(process_pwwp_chapters(session, chapter["_id"], selected_batch_id, subject_id, headers))
    chapter_results = await asyncio.gather(*chapter_tasks)
    all_urls = []
    for chapter, chapter_content in zip(chapters, chapter_results):
        chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")
        for content_type in ['videos', 'notes', 'DppNotes', 'DppVideos']:
            if chapter_content.get(content_type):
                content = chapter_content[content_type]
                content.reverse()
                content_string = "\n".join(content)
                zipf.writestr(f"{subject_name}/{chapter_name}/{content_type}.txt", content_string.encode('utf-8'))
                json_data[selected_batch_name][subject_name][chapter_name][content_type] = content
                all_urls.extend(content)
    all_subject_urls[subject_name] = all_urls

def find_pw_old_batch(batch_search):
    try:
        response = requests.get("https://abhiguru143.github.io/AS-MULTIVERSE-PW/batch/batch.json")
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")
        return []
    matching_batches = []
    for batch in data:
        if batch_search.lower() in batch['batch_name'].lower():
            matching_batches.append(batch)
    return matching_batches

async def login(app, user_id, m, all_urls, start_time, bname, batch_id, app_name, price=None, start_date=None, imageUrl=None):
    bname = await sanitize_bname(bname)
    file_path_base = f"{user_id}_{bname}"
    end_time = time.time()
    response_time = end_time - start_time
    minutes = int(response_time // 60)
    seconds = int(response_time % 60)
    user = await app.get_users(user_id)
    contact_link = f"[{user.first_name}](tg://openmessage?user_id={user_id})"
    all_text = "\n".join(all_urls)
    video_count = len(re.findall(r'\.(m3u8|mpd|mp4)', all_text))
    pdf_count = len(re.findall(r'\.pdf', all_text))
    credit = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n"
    drm_video_count = len(re.findall(r'\.(videoid|mpd|testbook)', all_text))
    enc_pdf_count = len(re.findall(r'\.pdf\*', all_text))
    if minutes == 0:
        if seconds < 1:
            formatted_time = f"{response_time:.2f} seconds"
        else:
            formatted_time = f"{seconds} seconds"
    else:
        formatted_time = f"{minutes} minutes {seconds} seconds"
    caption = (
        f"**APP NAME :** {app_name} \n\n"
        f"**Batch Name :** {batch_id} - {bname} \n\n"
        f"TOTAL LINK - {len(all_urls)} \n"
        f"Video Links - {video_count - drm_video_count} \n"
        f"Expiry Date:-**{c_expire_at}\n **Extracted BY:{credit} \n"
        f"Total Pdf - {pdf_count} \n\n"
        f"**╾───• Txt Extractor •───╼** \n"
        f" UPLOADER IN CHEAP PRICE - @king_rajasthan_23_bot \n"
        f"Time Taken: {formatted_time}"
    )
    files = [f"{file_path_base}.{ext}" for ext in ["txt", "zip", "json"]]
    for file in files:
        file_ext = os.path.splitext(file)[1][1:]
        try:
            async with aiofiles.open(file, 'rb') as f:
                copiable = await m.reply_document(document=file, caption=caption, file_name=f"{bname}.{file_ext}")
                await app.send_document(txt_dump, file, caption=caption, file_name=f"{bname}.{file_ext}")
        except FileNotFoundError:
            logging.error(f"File not found: {file}")
        except Exception as e:
            logging.exception(f"Error sending document {file}: {e}")
        finally:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except OSError as e:
                logging.error(f"Error deleting {file}: {e}")

@app.on_message(filters.command("pwfreex"))
async def pwfreex_command(app, m):
    user_id = m.chat.id
    await process_pwwp(app, m, user_id, "https://t.me/username")

async def process_pwwp(app, m, user_id, bot_link):
    editable = await m.reply_text("**Enter Working Access Token\n\nOR\n\nEnter Phone Number**")
    try:
        input1 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
        raw_text1 = input1.text
        await input1.delete(True)
    except:
        await editable.edit("**Timeout! You took too long to respond**")
        return
    headers = {
        'Host': 'api.penpencil.co',
        'client-id': '5eb393ee95fab7468a79d189',
        'client-version': '1910',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; M2101K6P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
        'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
        'client-type': 'WEB',
        'content-type': 'application/json; charset=utf-8',
    }
    loop = asyncio.get_event_loop()
    CONNECTOR = aiohttp.TCPConnector(limit=1000, loop=loop)
    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            if raw_text1.isdigit() and len(raw_text1) == 10:
                phone = raw_text1
                data = {
                    "username": phone,
                    "countryCode": "+91",
                    "organizationId": "5eb393ee95fab7468a79d189"
                }
                try:
                    async with session.post("https://api.penpencil.co/v1/users/get-otp?smsType=0", json=data, headers=headers) as response:
                        await response.read()
                except Exception as e:
                    await editable.edit(f"**Error : {e}**")
                    return
                editable = await editable.edit("**ENTER OTP YOU RECEIVED**")
                try:
                    input2 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    otp = input2.text
                    await input2.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                payload = {
                    "username": phone,
                    "otp": otp,
                    "client_id": "system-admin",
                    "client_secret": "KjPXuAVfC5xbmgreETNMaL7z",
                    "grant_type": "password",
                    "organizationId": "5eb393ee95fab7468a79d189",
                    "latitude": 0,
                    "longitude": 0
                }
                try:
                    async with session.post("https://api.penpencil.co/v3/oauth/token", json=payload, headers=headers) as response:
                        access_token = (await response.json())["data"]["access_token"]
                        await editable.edit(f"<b>Physics Wallah Login Successful ✅</b>\n\n<pre language='Save this Login Token for future usage'>{access_token}</pre>\n\n")
                        editable = await m.reply_text("**Getting Batches In Your I'd**")
                except Exception as e:
                    await editable.edit(f"**Error : {e}**")
                    return
            else:
                access_token = raw_text1
            headers['authorization'] = f"Bearer {access_token}"
            params = {
                'mode': '1',
                'page': '1',
            }
            try:
                async with session.get("https://api.penpencil.co/v3/batches/all-purchased-batches", headers=headers, params=params) as response:
                    response.raise_for_status()
                    batches = (await response.json()).get("data", [])
            except Exception as e:
                await editable.edit("**```\nLogin Failed❗TOKEN IS EXPIRED```\nPlease Enter Working Token\n                       OR\nLogin With Phone Number**")
                return
            await editable.edit("**Enter Your Batch Name**")
            try:
                input3 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                batch_search = input3.text
                await input3.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            url = f"https://api.penpencil.co/v3/batches/search?name={batch_search}"
            courses = await fetch_pwwp_data(session, url, headers)
            courses = courses.get("data", {}) if courses else {}
            if courses:
                text = ''
                for cnt, course in enumerate(courses):
                    name = course['name']
                    text += f"{cnt + 1}. ```\n{name}```\n"
                await editable.edit(f"**Send index number of the course to download.\n\n{text}\n\nIf Your Batch Not Listed Above Enter - No**")
                try:
                    input4 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    raw_text4 = input4.text
                    await input4.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                if input4.text.isdigit() and 1 <= int(input4.text) <= len(courses):
                    selected_course_index = int(input4.text.strip())
                    course = courses[selected_course_index - 1]
                    selected_batch_id = course['_id']
                    selected_batch_name = course['name']
                    clean_batch_name = await sanitize_bname(selected_batch_name)
                    file_path_base = f"{user_id}_{clean_batch_name}"
                elif "No" in input4.text:
                    courses = find_pw_old_batch(batch_search)
                    if courses:
                        text = ''
                        for cnt, course in enumerate(courses):
                            name = course['batch_name']
                            text += f"{cnt + 1}. ```\n{name}```\n"
                        await editable.edit(f"**Send index number of the course to download.\n\n{text}**")
                        try:
                            input5 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                            raw_text5 = input5.text
                            await input5.delete(True)
                        except:
                            await editable.edit("**Timeout! You took too long to respond**")
                            return
                        if input5.text.isdigit() and 1 <= int(input5.text) <= len(courses):
                            selected_course_index = int(input5.text.strip())
                            course = courses[selected_course_index - 1]
                            selected_batch_id = course['batch_id']
                            selected_batch_name = course['batch_name']
                            clean_batch_name = await sanitize_bname(selected_batch_name)
                            file_path_base = f"{user_id}_{clean_batch_name}"
                        else:
                            raise Exception("Invalid batch index.")
                else:
                    raise Exception("Invalid batch index.")
                await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
                start_time = time.time()
                url = f"https://api.penpencil.co/v3/batches/{selected_batch_id}/details"
                batch_details = await fetch_pwwp_data(session, url, headers=headers)
                if batch_details and batch_details.get("success"):
                    subjects = batch_details.get("data", {}).get("subjects", [])
                    json_data = {selected_batch_name: {}}
                    all_subject_urls = {}
                    with zipfile.ZipFile(f"{file_path_base}.zip", 'w') as zipf:
                        zipf.writestr("Telegram Bot/Extractor Bot.txt", f"Extractor Bot:{bot_link}")
                        subject_tasks = [process_pwwp_subject(session, subject, selected_batch_id, selected_batch_name, zipf, json_data, all_subject_urls, headers) for subject in subjects]
                        await asyncio.gather(*subject_tasks)
                    json_data[selected_batch_name]["Telegram Bot"] = {"Extractor Bot": bot_link}
                    with open(f"{file_path_base}.json", 'w') as f:
                        json.dump(json_data, f, indent=4)
                    with open(f"{file_path_base}.txt", 'w', encoding='utf-8') as f:
                        f.write(f"Extractor Bot:{bot_link}\n")
                        for subject in subjects:
                            subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
                            if subject_name in all_subject_urls:
                                f.write('\n'.join(all_subject_urls[subject_name]) + '\n')
                    all_urls = []
                    for subject_name in all_subject_urls:
                        all_urls.extend(all_subject_urls[subject_name])
                    await login(app, user_id, m, all_urls, start_time, clean_batch_name, selected_batch_id, app_name="Physics Wallah")
                    await editable.delete()
                else:
                    raise Exception(f"Error fetching batch details: {batch_details.get('message')}")
            else:
                raise Exception("No batches found for the given search name.")
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            try:
                await editable.edit(f"**Error : {e}**")
            except Exception as ee:
                logging.error(f"Failed to send error message to user: {ee}")
        finally:
            if session:
                await session.close()
            await CONNECTOR.close()
