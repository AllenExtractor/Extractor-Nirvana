import aiohttp
import asyncio
import datetime
import re
import aiofiles
import os
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from base64 import b64decode
from pyrogram import filters
from pyrogram.errors import FloodWait, RPCError, ChatAdminRequired
from config import CHANNEL_ID
import logging
from time import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    logging.warning("psutil module not found. Memory monitoring disabled.")
    PSUTIL_AVAILABLE = False

try:
    from Extractor import app
except ImportError as e:
    logging.error(f"Failed to import Extractor: {e}. Ensure Extractor.py exists and defines 'app'.")
    raise ImportError("Cannot start bot: Extractor module not found. Check Extractor.py and its dependencies.")
except AttributeError as e:
    logging.error(f"Extractor module does not define 'app': {e}")
    raise AttributeError("Extractor module must define 'app' as a Pyrogram Client instance.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

appname = "Utkarsh"
txt_dump = CHANNEL_ID
message_lock = asyncio.Lock()
url_lock = asyncio.Lock()

class RateLimiter:
    def __init__(self, max_requests, period):
        self.max_requests = max_requests
        self.period = period
        self.requests = []
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        async with self.lock:
            while len(self.requests) >= self.max_requests:
                if self.requests and time() - self.requests[0] > self.period:
                    self.requests.pop(0)
                else:
                    await asyncio.sleep(0.1)
            self.requests.append(time())
    
    async def cleanup(self):
        async with self.lock:
            current = time()
            self.requests = [t for t in self.requests if current - t < self.period]

def decrypt(enc):
    try:
        enc = b64decode(enc)
        key = '%!$!%_$&!%F)&^!^'.encode('utf-8')
        iv = '#*y*#2yJ*#$wJv*v'.encode('utf-8')
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(enc), AES.block_size)
        return plaintext.decode('utf-8')
    except Exception:
        return None

async def safe_send_message(chat_id, text, client):
    async with message_lock:
        for attempt in range(3):
            try:
                return await client.send_message(chat_id, text)
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)
            except ChatAdminRequired as e:
                logger.error(f"ChatAdminRequired: {e}")
                return None
            except RPCError as e:
                logger.error(f"RPCError: {e}")
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        logger.error(f"Failed to send message to {chat_id} after retries")
        return None

async def safe_edit_message(message, text, client):
    async with message_lock:
        for attempt in range(3):
            try:
                return await message.edit(text)
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)
            except ChatAdminRequired as e:
                logger.error(f"ChatAdminRequired: {e}")
                return None
            except RPCError as e:
                logger.error(f"RPCError: {e}")
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        logger.error("Failed to edit message after retries")
        return None

async def fetch_api(session, url, headers, data=None, method='POST', retries=3, rate_limiter=None):
    for attempt in range(retries):
        if rate_limiter:
            await rate_limiter.acquire()
        try:
            async with asyncio.timeout(30):
                if method == 'POST':
                    async with session.post(url, headers=headers, data=data) as response:
                        response.raise_for_status()
                        text = await response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            logger.error(f"Non-JSON response from {url}: Response (first 500 chars): {text[:500]}")
                            return None
                else:
                    async with session.get(url, headers=headers) as response:
                        response.raise_for_status()
                        text = await response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            logger.error(f"Non-JSON response from {url}: Response (first 500 chars): {text[:500]}")
                            return None
        except asyncio.TimeoutError:
            logger.error(f"API request timed out (attempt {attempt + 1}/{retries}): {url}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
        except aiohttp.ClientError as e:
            logger.error(f"API request failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
        finally:
            if rate_limiter:
                await rate_limiter.cleanup()
    return None

async def log_memory():
    if not PSUTIL_AVAILABLE:
        logger.debug("Memory logging skipped: psutil not available")
        return
    try:
        process = psutil.Process()
        mem = process.memory_info().rss / 1024 / 1024
        logger.info(f"Memory usage: {mem:.2f} MB")
    except Exception as e:
        logger.error(f"Failed to log memory: {e}")

async def fetch_subjects(session, batch_id, token, headers, rate_limiter):
    data4 = {
        'tile_input': f'{{"course_id": {batch_id},"revert_api":"1#0#0#1","parent_id":0,"tile_id":"0","layer":1,"type":"course_combo"}}',
        'csrf_name': token
    }
    key = '%!$!%_$&!%F)&^!^'.encode('utf-8')
    iv = '#*y*#2yJ*#$wJv*v'.encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data4['tile_input'].encode(), AES.block_size)
    encoded_data = base64.b64encode(cipher.encrypt(padded_data)).decode()
    data4['tile_input'] = encoded_data
    res4 = await fetch_api(session, "https://online.utkarsh.com/web/Course/tiles_data", headers, data4, method='POST', rate_limiter=rate_limiter)
    if not res4:
        return []
    res4_data = res4.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
    res4_dec = decrypt(res4_data)
    if not res4_dec:
        return []
    try:
        res4_json = json.loads(res4_dec)
        return res4_json.get("data", [])
    except Exception as e:
        logger.error(f"Failed to parse subjects: {e}")
        return []

async def fetch_topics(session, batch_id, subject_id, topic_name, token, headers, rate_limiter):
    data5 = {
        'tile_input': f'{{"course_id":{subject_id},"layer":1,"page":1,"parent_id":{batch_id},"revert_api":"1#0#0#1","tile_id":"0","type":"content"}}',
        'csrf_name': token
    }
    key = '%!$!%_$&!%F)&^!^'.encode('utf-8')
    iv = '#*y*#2yJ*#$wJv*v'.encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data5['tile_input'].encode(), AES.block_size)
    encoded_data = base64.b64encode(cipher.encrypt(padded_data)).decode()
    data5['tile_input'] = encoded_data
    res5 = await fetch_api(session, "https://online.utkarsh.com/web/Course/tiles_data", headers, data5, method='POST', rate_limiter=rate_limiter)
    if not res5:
        return []
    res5_data = res5.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
    decres5 = decrypt(res5_data)
    if not decres5:
        return []
    try:
        res5l = json.loads(decres5)
        return res5l.get("data", {}).get("list", [])
    except Exception as e:
        logger.error(f"Failed to parse topics: {e}")
        return []

async def fetch_subtopics(session, batch_id, subject_id, topic_id, topic_title, token, headers, rate_limiter):
    data5 = {
        'tile_input': f'{{"course_id":{subject_id},"parent_id":{batch_id},"layer":2,"page":1,"revert_api":"1#0#0#1","subject_id": {topic_id},"tile_id":0,"topic_id": {topic_id},"type":"content"}}',
        'csrf_name': token
    }
    key = '%!$!%_$&!%F)&^!^'.encode('utf-8')
    iv = '#*y*#2yJ*#$wJv*v'.encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data5['tile_input'].encode(), AES.block_size)
    encoded_data = base64.b64encode(cipher.encrypt(padded_data)).decode()
    data5['tile_input'] = encoded_data
    res6 = await fetch_api(session, "https://online.utkarsh.com/web/Course/tiles_data", headers, data5, method='POST', rate_limiter=rate_limiter)
    if not res6:
        return []
    res6_data = res6.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
    decres6 = decrypt(res6_data)
    if not decres6:
        return []
    try:
        res6l = json.loads(decres6)
        return res6l.get("data", {}).get("list", [])
    except Exception as e:
        logger.error(f"Failed to parse subtopics: {e}")
        return []

async def fetch_content(session, batch_id, subject_id, topic_id, subtopic_id, topic_name, topic_title, token, headers, rate_limiter):
    data6 = {
        'layer_two_input_data': f'{{"course_id":{subject_id},"parent_id":{batch_id},"layer":3,"page":1,"revert_api":"1#0#0#1","subject_id": {topic_id},"tile_id":0,"topic_id": {subtopic_id},"type":"content"}}',
        'content': 'content',
        'csrf_name': token
    }
    encoded_data = base64.b64encode(data6['layer_two_input_data'].encode()).decode()
    data6['layer_two_input_data'] = encoded_data
    res6 = await fetch_api(session, "https://online.utkarsh.com/web/Course/get_layer_two_data", headers, data6, method='POST', rate_limiter=rate_limiter)
    if not res6:
        return []
    res6_data = res6.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
    decres6 = decrypt(res6_data)
    if not decres6:
        return []
    try:
        res6_json = json.loads(decres6)
        res6data = res6_json.get('data', {})
        res6_list = res6data.get('list', [])
        urls = []
        for item in res6_list:
            title = item.get("title", "").replace("||", "-").replace(":", "-")
            bitrate_urls = item.get("bitrate_urls", [])
            url = None
            for url_data in bitrate_urls:
                if url_data.get("title") == "720p":
                    url = url_data.get("url")
                    break
                elif url_data.get("name") == "720x1280.mp4":
                    url = url_data.get("link") + ".mp4"
                    url = url.replace("/enc/", "/plain/")
            if url is None:
                url = item.get("file_url")
            if url and not url.endswith('.ws'):
                if url.endswith(("_0_0", "_0")):
                    url = f"https://apps-s3-jw-prod.utkarshapp.com/admin_v1/file_library/videos/enc_plain_mp4/{url.split('_')[0]}/plain/720x1280.mp4"
                elif not url.startswith(("https://", "http://")):
                    url = f"https://youtu.be/{url}"
                prefix = f"({topic_title})" if topic_title else ""
                urls.append(f"{prefix}{title}: {url}")
        return urls
    except Exception as e:
        logger.error(f"Failed to parse content: {e}")
        return []

async def process_batch(session, batch_id, bname, token, headers, all_urls, rate_limiter):
    subjects = await fetch_subjects(session, batch_id, token, headers, rate_limiter)
    subject_ids = [(s["id"], s["title"]) for s in subjects]

    tasks = []
    for subject_id, topic_name in subject_ids:
        topics = await fetch_topics(session, batch_id, subject_id, topic_name, token, headers, rate_limiter)
        topic_ids = [(t["id"], t["title"]) for t in topics]
        for topic_id, topic_title in topic_ids:
            subtopics = await fetch_subtopics(session, batch_id, subject_id, topic_id, topic_title, token, headers, rate_limiter)
            subtopic_ids = [st["id"] for st in subtopics]
            for subtopic_id in subtopic_ids:
                tasks.append(fetch_content(session, batch_id, subject_id, topic_id, subtopic_id, topic_name, topic_title, token, headers, rate_limiter))

    # Process content fetching concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    async with url_lock:
        for result in results:
            if isinstance(result, list):
                all_urls.extend(result)

@app.on_message(filters.command(["utkarsh"]))
async def handle_utk_logic(client, m):
    user_id = m.from_user.id
    rate_limiter = RateLimiter(max_requests=3, period=1)  # Reduced to 3 req/s
    async with aiohttp.ClientSession() as session:
        task = asyncio.create_task(process_user_request(client, m, user_id, rate_limiter, session))
        setattr(m, f'utk_task_{user_id}', task)
        await task

async def process_user_request(client, m, user_id, rate_limiter, session):
    await log_memory()
    unique_id = str(uuid.uuid4())
    file_path = None

    try:
        async with asyncio.timeout(600):
            # Initialize headers for this user
            session_id = str(uuid.uuid4()).replace('-', '')
            headers = {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                'referer': 'https://online.utkarsh.com/',
                'accept-encoding': 'gzip, deflate, br, zstd',
                'accept-language': 'en-US,en;q=0.9',
                'cookie': f'ci_session={session_id}'
            }
            token_response = await fetch_api(session, 'https://online.utkarsh.com/web/home/get_states', headers, method='GET', rate_limiter=rate_limiter)
            if not token_response:
                await safe_send_message(m.chat.id, "Error: Failed to get token from Utkarsh API. Try again later or contact support.", client)
                return
            token = token_response.get("token")
            if not token:
                await safe_send_message(m.chat.id, "Error: No token received from Utkarsh API", client)
                return

            headers.update({
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'x-requested-with': 'XMLHttpRequest',
                'origin': 'https://online.utkarsh.com',
                'cookie': f'csrf_name={token}; ci_session={session_id}'
            })

            editable = await safe_send_message(
                m.chat.id,
                "Send **ID & Password** in this manner otherwise app will not respond.\n\nSend like this:- **ID*Password**",
                client
            )
            if not editable:
                return
            input1 = await client.listen(chat_id=m.chat.id)
            raw_text = input1.text
            await input1.delete()

            if '*' in raw_text:
                ids, ps = raw_text.split("*")
                data = f"csrf_name={token}&mobile={ids}&url=0&password={ps}&submit=LogIn&device_token=null"
                log_response = await fetch_api(session, 'https://online.utkarsh.com/web/Auth/login', headers, data, rate_limiter=rate_limiter)
                if not log_response:
                    await safe_edit_message(editable, "Login error: Failed to connect to Utkarsh server. Please try again.", client)
                    return
                log_data = log_response.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
                dec_log = decrypt(log_data)
                if not dec_log:
                    await safe_edit_message(editable, "Failed to decrypt login response. Please try again.", client)
                    return
                try:
                    dec_logs = json.loads(dec_log)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in login response: {e}")
                    await safe_edit_message(editable, "Invalid login response format. Please try again.", client)
                    return
                error_message = dec_logs.get("message", "No message")
                status = dec_logs.get('status', False)
                if status:
                    await safe_edit_message(editable, "**User authentication successful.**", client)
                else:
                    await safe_edit_message(editable, f"Login Failed - {error_message}. Please try again.", client)
                    return
            else:
                await safe_edit_message(editable, "**Please Send id password in this manner** \n\n**Id*Password**", client)
                return

            data2 = f"type=Batch&csrf_name={token}&sort=0"
            res2 = await fetch_api(session, 'https://online.utkarsh.com/web/Profile/my_course', headers, data2, rate_limiter=rate_limiter)
            if not res2:
                await safe_edit_message(editable, "Error fetching courses: Failed to connect to Utkarsh server. Please try again.", client)
                return
            res2_data = res2.get("response", "").replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
            decrypted_res = decrypt(res2_data)
            if not decrypted_res:
                await safe_edit_message(editable, "Failed to decrypt course response. Please try again.", client)
                return
            try:
                dc = json.loads(decrypted_res)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in course response: {e}")
                await safe_edit_message(editable, "Invalid course response format. Please try again.", client)
                return
            bdetail = dc.get('data', {}).get("data", [])

            if not bdetail:
                await safe_edit_message(editable, "No batches found", client)
                return

            cool = ""
            FFF = "**BATCH-ID -      BATCH NAME **"
            Batch_ids = ''
            for item in bdetail:
                id = item.get("id")
                batch = item.get("title")
                price = item.get("mrp")
                aa = f" `{id}`      - **{batch} ✳️ {price}**\n\n"
                if len(f'{cool}{aa}') > 4096:
                    cool = ""
                cool += aa
                Batch_ids += str(id) + '&'
            Batch_ids = Batch_ids.rstrip('&')
            login_msg = f'<b>{appname} Login Successful ✅</b>\n'
            login_msg += f'\n<b>ID Password :- </b><code>{raw_text}</code>\n\n'
            login_msg += f'\n\n<b>BATCH ID ➤ BATCH NAME</b>\n\n{cool}'
            txt_dump_msg = await safe_send_message(txt_dump, login_msg, client)
            if not txt_dump_msg:
                await safe_send_message(m.chat.id, "Warning: Could not send login details to txt_dump channel. Ensure bot is admin.", client)
            await safe_edit_message(editable, f"**You have these batches :-**\n\n{FFF}\n\n{cool}", client)

            editable1 = await safe_send_message(
                m.chat.id,
                f"**Now send the Batch ID to Download**\n\n**For All batch -** `{Batch_ids}`",
                client
            )
            if not editable1:
                return
            input2 = await client.listen(chat_id=m.chat.id)
            await input2.delete()
            await safe_edit_message(editable, "Processing...", client)
            await editable1.delete()

            if "&" in input2.text:
                batch_ids = input2.text.split('&')
            else:
                batch_ids = [input2.text]

            for batch_id in batch_ids:
                await log_memory()
                start_time = datetime.datetime.now()
                bname = next((x['title'] for x in bdetail if str(x['id']) == batch_id), None)
                if not bname:
                    await safe_send_message(m.chat.id, f"Invalid Batch ID: {batch_id}", client)
                    continue

                xx = await safe_send_message(m.chat.id, f"<b>Processing batch: {bname}</b>", client)
                if not xx:
                    continue

                all_urls = []
                await process_batch(session, batch_id, bname, token, headers, all_urls, rate_limiter)
                
                file_path = f"{batch_id}_{await sanitize_bname(bname)}_{user_id}_{unique_id}.txt"
                if all_urls:
                    try:
                        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                            for url in all_urls:
                                await f.write(url + '\n')
                        await safe_edit_message(xx, f"<b>Scraping completed for {bname}!</b>", client)
                        await login(client, user_id, m, file_path, start_time, bname, batch_id, len(all_urls), app_name="Utkarsh")
                    except OSError as e:
                        logger.error(f"File I/O error: {e}")
                        await safe_send_message(m.chat.id, f"Failed to write to file: {e}. Please try again.", client)
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    await safe_send_message(m.chat.id, "No URLs found for the selected batch.", client)
                await xx.delete()

                await rate_limiter.acquire()
              

    except asyncio.TimeoutError:
        logger.error(f"Timeout: Course extraction for user {user_id} took longer than 10 minutes")
        await safe_send_message(m.chat.id, "Error: Course extraction took longer than 10 minutes. Please try again.", client)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Unexpected error for user {user_id}: {e}")
        await safe_send_message(m.chat.id, f"Unexpected error occurred: {e}. Please try again.", client)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    finally:
        await log_memory()

async def login(client, user_id, m, file_path, start_time, bname, batch_id, url_count, app_name):
    await log_memory()
    bname = await sanitize_bname(bname)
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    minutes, seconds = divmod(duration.total_seconds(), 60)
    user = await client.get_users(user_id)
    contact_link = f"[{user.first_name}](tg://openmessage?user_id={user_id})"
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            all_text = await f.read()
    except OSError as e:
        logger.error(f"Failed to read file: {e}")
        await safe_send_message(m.chat.id, f"Error reading file: {e}. Please try again.", client)
        return
    video_count = len(re.findall(r'\.(m3u8|mpd|mp4)', all_text))
    pdf_count = len(re.findall(r'\.pdf', all_text))
    drm_video_count = len(re.findall(r'\.(videoid|mpd|testbook)', all_text))
    enc_pdf_count = len(re.findall(r'\.pdf\*', all_text))
    credit = f"[{m.from_user.first_name}](tg://user?id={m.from_user.id})\n\n"
    caption = (
        f"**APP NAME :** UTKARSH \n\n"
        f"**Batch Name :** {batch_id} - {bname} \n\n"
        f"TOTAL LINK - {url_count} \n"
        f"Video Links - {video_count - drm_video_count} \n"
        f"Total Pdf - {pdf_count} \n"
        f"**Extracted BY: {credit}** \n\n"
        f"**[Ksi ko usa ka account chiye tho msg kr lo stock h new Msg here @Hidfgh] \n\n**"
        f"**╾───• Txtx Extractor •───╼** uploader in cheap price @king_rajasthan_23_bot"
    )
    async with message_lock:
        try:
            await client.send_document(m.chat.id, file_path, caption=caption)
            txt_dump_doc = await client.send_document(txt_dump, file_path, caption=caption)
            if not txt_dump_doc:
                await safe_send_message(m.chat.id, "Warning: Could not send file to txt_dump channel. Ensure bot is admin.", client)
        except ChatAdminRequired as e:
            logger.error(f"ChatAdminRequired in txt_dump: {e}")
            await safe_send_message(m.chat.id, "Error: Bot lacks admin privileges in txt_dump channel. File sent only to you.", client)
        except Exception as e:
            logger.error(f"Failed to send document: {e}")
            await safe_send_message(m.chat.id, f"Error sending file: {e}. Please try again.", client)

async def sanitize_bname(bname, max_length=50):
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', bname).strip()
    if len(bname) > max_length:
        bname = bname[:max_length]
    return bname
