import os
import json
import asyncio
import aiohttp
import logging
import zipfile
import time
import calendar
import requests
from datetime import datetime, timedelta
from pyrogram import filters
from Extractor import app
from config import CHANNEL_ID
import re
import aiofiles

txt_dump = CHANNEL_ID
appname = "Physics Wallah"

# Semaphore: max 3 concurrent schedule-detail requests to avoid 429
_schedule_detail_semaphore = asyncio.Semaphore(3)

async def sanitize_bname(bname, max_length=50):
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', bname).strip()
    if len(bname) > max_length:
        bname = bname[:max_length]
    return bname

async def fetch_pwwp_data(session: aiohttp.ClientSession, url: str, headers: dict = None, params: dict = None, data: dict = None, method: str = 'GET') -> any:
    max_retries = 5
    for attempt in range(max_retries):
        try:
            async with session.request(method, url, headers=headers, params=params, json=data) as response:
                # 404 — endpoint doesn't exist, no point retrying
                if response.status == 404:
                    logging.warning(f"404 Not Found: {url} — skipping")
                    return None
                # 429 — rate limited, respect Retry-After header
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    retry_after = min(retry_after, 30)  # cap at 30s
                    logging.warning(f"429 Rate Limited: {url} — waiting {retry_after}s (attempt {attempt+1})")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                logging.warning(f"404 Not Found: {url} — skipping")
                return None
            if e.status == 429:
                wait = min(5 * (attempt + 1), 30)
                logging.warning(f"429 Rate Limited: {url} — waiting {wait}s (attempt {attempt+1})")
                await asyncio.sleep(wait)
                continue
            logging.error(f"Attempt {attempt + 1} failed: aiohttp error fetching {url}: {e}")
        except aiohttp.ClientError as e:
            logging.error(f"Attempt {attempt + 1} failed: aiohttp error fetching {url}: {e}")
        except Exception as e:
            logging.exception(f"Attempt {attempt + 1} failed: Unexpected error fetching {url}: {e}")
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
        else:
            logging.error(f"Failed to fetch {url} after {max_retries} attempts.")
            return None

async def process_pwwp_chapter_content(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, schedule_id, content_type, headers: dict):
    url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
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

async def fetch_today_schedule(session: aiohttp.ClientSession, batch_id: str, target_date: str, headers: dict):
    """Fetch schedule for a specific date from PW API using correct endpoints"""
    all_schedules = []

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        epoch_ms = int(calendar.timegm(dt.timetuple())) * 1000
        next_dt = dt + timedelta(days=1)
        epoch_ms_end = int(calendar.timegm(next_dt.timetuple())) * 1000
    except ValueError:
        logging.error(f"Invalid date format: {target_date}")
        return []

    # PW real working endpoints tried in order
    endpoint_variants = [
        (f"https://api.penpencil.co/v2/batches/{batch_id}/batch-contents",
            [{"page": 1, "startDate": epoch_ms, "endDate": epoch_ms_end},
             {"page": 1, "startDate": target_date, "endDate": target_date}]),
        (f"https://api.penpencil.co/v3/batches/{batch_id}/batch-contents",
            [{"page": 1, "startDate": epoch_ms, "endDate": epoch_ms_end},
             {"page": 1, "startDate": target_date, "endDate": target_date}]),
        (f"https://api.penpencil.co/v4/batches/{batch_id}/contents",
            [{"page": 1, "startDate": epoch_ms, "endDate": epoch_ms_end},
             {"page": 1, "date": target_date}]),
        (f"https://api.penpencil.co/v1/batches/{batch_id}/contents",
            [{"page": 1, "startDate": epoch_ms, "endDate": epoch_ms_end},
             {"page": 1, "startDate": target_date, "endDate": target_date}]),
    ]

    for url, params_list in endpoint_variants:
        for base_params in params_list:
            page = 1
            trial = []
            got_success = False
            while True:
                params = dict(base_params)
                params["page"] = page
                data = await fetch_pwwp_data(session, url, headers=headers, params=params)
                if data is None:
                    break  # 404 or hard error — skip this endpoint entirely
                if data.get("success") and data.get("data"):
                    items = data["data"]
                    if not items:
                        break
                    for item in items:
                        item["_page"] = page
                        trial.append(item)
                    got_success = True
                    page += 1
                else:
                    break
            if trial:
                # Filter to only items matching target_date if date field present
                filtered = [
                    item for item in trial
                    if target_date in str(
                        item.get("date") or item.get("startTime") or
                        item.get("scheduleDate") or item.get("createdAt") or ""
                    ) or not (
                        item.get("date") or item.get("startTime") or
                        item.get("scheduleDate") or item.get("createdAt")
                    )
                ]
                all_schedules = filtered if filtered else trial
                logging.info(f"fetch_today_schedule: {len(all_schedules)} items via {url}")
                return all_schedules
            elif got_success:
                logging.info(f"fetch_today_schedule: {url} worked but empty for {target_date}")
                return []

    # Last resort: fetch per-subject contents and filter client-side
    logging.warning("fetch_today_schedule: all endpoints failed, trying subject-content fallback")
    try:
        bd = await fetch_pwwp_data(
            session, f"https://api.penpencil.co/v2/batches/{batch_id}/details", headers=headers
        )
        if bd and bd.get("success"):
            for subj in bd.get("data", {}).get("subjects", []):
                subj_id = subj.get("_id")
                for ct in ["videos", "notes", "DppVideos", "DppNotes"]:
                    page = 1
                    while True:
                        params = {"contentType": ct, "page": page,
                                  "startDate": epoch_ms, "endDate": epoch_ms_end}
                        url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subj_id}/contents"
                        data = await fetch_pwwp_data(session, url, headers=headers, params=params)
                        if data and data.get("success") and data.get("data"):
                            items = data["data"]
                            if not items:
                                break
                            for item in items:
                                item["_subject_id"] = subj_id
                                item["_content_type"] = ct
                                all_schedules.append(item)
                            page += 1
                        else:
                            break
    except Exception as e:
        logging.error(f"fetch_today_schedule fallback error: {e}")

    logging.info(f"fetch_today_schedule fallback: {len(all_schedules)} items")
    return all_schedules

async def fetch_schedule_details(session: aiohttp.ClientSession, batch_id: str, subject_id: str, schedule_id: str, headers: dict):
    """Fetch detailed content for a schedule item — rate-limited via semaphore"""
    async with _schedule_detail_semaphore:
        url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
        result = await fetch_pwwp_data(session, url, headers=headers)
        # Small delay after each request to avoid burst 429
        await asyncio.sleep(0.4)
        return result

async def process_today_class(session: aiohttp.ClientSession, selected_batch_id: str, selected_batch_name: str, target_date: str, headers: dict, bot_link: str):
    """Process Today's Class extraction - fetch only scheduled content for target date"""
    logging.info(f"Fetching schedule for date: {target_date}")

    # Get batch details to find subjects
    url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/details"
    batch_details = await fetch_pwwp_data(session, url, headers=headers)

    if not batch_details or not batch_details.get("success"):
        return None, None, None, "Failed to fetch batch details"

    subjects = batch_details.get("data", {}).get("subjects", [])
    if not subjects:
        return None, None, None, "No subjects found in batch"

    # Fetch schedule for target date
    schedules = await fetch_today_schedule(session, selected_batch_id, target_date, headers)

    if not schedules:
        return None, None, None, f"No classes scheduled for {target_date}"

    logging.info(f"Found {len(schedules)} schedule items for {target_date}")

    # Build subject lookup
    subject_map = {}
    for subj in subjects:
        sid = subj.get("_id")
        sname = subj.get("subject", "Unknown").replace("/", "-")
        subject_map[sid] = {"name": sname, "info": subj}

    # Process each scheduled item
    json_data = {selected_batch_name: {}}
    all_urls = []
    structured_data = {}

    clean_batch_name = await sanitize_bname(selected_batch_name)
    file_path_base = f"today_{target_date}_{clean_batch_name}"

    for schedule_item in schedules:
        # Robust subject_id extraction — handles list, dict, or string
        raw_subject = schedule_item.get("subject", "")
        if isinstance(raw_subject, list):
            first = raw_subject[0] if raw_subject else ""
            subject_id = first.get("_id", "") if isinstance(first, dict) else str(first)
        elif isinstance(raw_subject, dict):
            subject_id = raw_subject.get("_id", "")
        else:
            subject_id = str(raw_subject) if raw_subject else ""
        if not subject_id:
            subject_id = schedule_item.get("_subject_id", "")

        schedule_id = schedule_item.get("_id", "")
        topic = schedule_item.get("topic", schedule_item.get("name", "Unknown Topic")).replace("/", "-").replace(":", "-")
        start_time = schedule_item.get("startTime", schedule_item.get("startDate", ""))
        end_time = schedule_item.get("endTime", schedule_item.get("endDate", ""))
        content_type_tag = schedule_item.get("contentType", schedule_item.get("_content_type", schedule_item.get("type", "unknown")))

        subject_name = subject_map.get(subject_id, {}).get("name", "")
        if not subject_name:
            raw_sub = schedule_item.get("subject", {})
            if isinstance(raw_sub, dict):
                subject_name = raw_sub.get("subject", raw_sub.get("name", ""))
            if not subject_name:
                subject_name = schedule_item.get("subjectName", "Unknown Subject")
            subject_name = (subject_name or "Unknown Subject").replace("/", "-")

        if subject_name not in structured_data:
            structured_data[subject_name] = []
        if subject_name not in json_data[selected_batch_name]:
            json_data[selected_batch_name][subject_name] = {}

        # Fetch detailed content
        details = await fetch_schedule_details(session, selected_batch_id, subject_id, schedule_id, headers)

        item_data = {
            "topic": topic,
            "start_time": start_time,
            "end_time": end_time,
            "content_type": content_type_tag,
            "videos": [],
            "notes": [],
            "DppVideos": [],
            "DppNotes": []
        }

        if details and details.get("success") and details.get("data"):
            data_item = details["data"]

            # Extract videos
            video_details = data_item.get('videoDetails', {})
            if video_details:
                video_url = video_details.get('videoUrl') or video_details.get('embedCode') or ""
                if video_url:
                    line = f"{topic}:{video_url}"
                    if content_type_tag in ("DppVideo", "DppVideos"):
                        item_data["DppVideos"].append(line)
                    else:
                        item_data["videos"].append(line)
                    all_urls.append(line)

            # Extract notes/attachments
            homework_ids = data_item.get('homeworkIds', [])
            for homework in homework_ids:
                attachment_ids = homework.get('attachmentIds', [])
                hw_topic = homework.get('topic', topic)
                for attachment in attachment_ids:
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url:
                        line = f"{hw_topic}:{url}"
                        if content_type_tag in ("DppNotes", "DppNote"):
                            item_data["DppNotes"].append(line)
                        else:
                            item_data["notes"].append(line)
                        all_urls.append(line)

        structured_data[subject_name].append(item_data)

        # Build json data for this topic
        topic_key = f"{topic} ({start_time})"
        json_data[selected_batch_name][subject_name][topic_key] = {}
        for ct in ['videos', 'notes', 'DppVideos', 'DppNotes']:
            if item_data[ct]:
                json_data[selected_batch_name][subject_name][topic_key][ct] = item_data[ct]

    # Create ZIP file
    zip_path = f"{file_path_base}.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        zipf.writestr("Telegram Bot/Extractor Bot.txt", f"Extractor Bot:{bot_link}")

        for subject_name, items in structured_data.items():
            zipf.writestr(f"{subject_name}/", "")

            for item in items:
                topic = item["topic"]
                time_slot = item["start_time"]
                folder_name = f"{subject_name}/{topic}_{time_slot}"

                for ct in ['videos', 'notes', 'DppVideos', 'DppNotes']:
                    if item[ct]:
                        content_text = "\n".join(item[ct])
                        zipf.writestr(f"{folder_name}/{ct}.txt", content_text.encode('utf-8'))

    # Create JSON file
    json_path = f"{file_path_base}.json"
    json_data[selected_batch_name]["Telegram Bot"] = {"Extractor Bot": bot_link}
    json_data[selected_batch_name]["date"] = target_date
    json_data[selected_batch_name]["total_schedules"] = len(schedules)
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=4)

    # Create TXT file
    txt_path = f"{file_path_base}.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Extractor Bot:{bot_link}\n")
        f.write(f"=== {selected_batch_name} - Classes for {target_date} ===\n\n")
        for subject_name, items in structured_data.items():
            f.write(f"\n--- {subject_name} ---\n")
            for item in items:
                f.write(f"\n📚 {item['topic']}\n")
                f.write(f"⏰ {item['start_time']} - {item['end_time']}\n")
                for ct in ['videos', 'notes', 'DppVideos', 'DppNotes']:
                    if item[ct]:
                        f.write(f"\n[{ct}]\n")
                        f.write("\n".join(item[ct]) + "\n")

    # Create HTML file
    html_path = f"{file_path_base}.html"
    html_content = generate_html_output(selected_batch_name, target_date, structured_data, schedules, bot_link, len(all_urls))
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return all_urls, file_path_base, len(schedules), None

def generate_html_output(batch_name, target_date, structured_data, raw_schedules, bot_link, total_links):
    """Generate beautiful HTML output for Today's Class"""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{batch_name} - {target_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: rgba(255,255,255,0.95); border-radius: 20px; padding: 30px; margin-bottom: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); text-align: center; }}
        .header h1 {{ color: #333; font-size: 2em; margin-bottom: 10px; }}
        .header .date {{ color: #667eea; font-size: 1.2em; font-weight: 600; }}
        .header .stats {{ display: flex; justify-content: center; gap: 30px; margin-top: 20px; flex-wrap: wrap; }}
        .stat-box {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 15px 25px; border-radius: 15px; text-align: center; }}
        .stat-box .number {{ font-size: 1.8em; font-weight: bold; }}
        .stat-box .label {{ font-size: 0.9em; opacity: 0.9; }}
        .subject-card {{ background: rgba(255,255,255,0.95); border-radius: 20px; padding: 25px; margin-bottom: 25px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }}
        .subject-title {{ color: #667eea; font-size: 1.5em; font-weight: 700; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 3px solid #667eea; }}
        .class-item {{ background: #f8f9ff; border-radius: 15px; padding: 20px; margin-bottom: 15px; border-left: 5px solid #667eea; }}
        .class-time {{ color: #764ba2; font-weight: 600; font-size: 0.95em; margin-bottom: 8px; }}
        .class-topic {{ color: #333; font-size: 1.1em; font-weight: 600; margin-bottom: 15px; }}
        .content-section {{ margin-top: 12px; }}
        .content-title {{ color: #555; font-weight: 600; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
        .link-list {{ list-style: none; }}
        .link-list li {{ background: white; padding: 10px 15px; margin-bottom: 8px; border-radius: 10px; font-size: 0.9em; word-break: break-all; border: 1px solid #e0e0e0; }}
        .link-list li a {{ color: #667eea; text-decoration: none; }}
        .link-list li a:hover {{ text-decoration: underline; }}
        .footer {{ text-align: center; color: rgba(255,255,255,0.8); margin-top: 30px; padding: 20px; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.75em; font-weight: 600; text-transform: uppercase; }}
        .badge-video {{ background: #e3f2fd; color: #1976d2; }}
        .badge-note {{ background: #f3e5f5; color: #7b1fa2; }}
        .badge-dpp {{ background: #e8f5e9; color: #388e3c; }}
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 1.5em; }}
            .stats {{ gap: 15px; }}
            .subject-card {{ padding: 18px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 {batch_name}</h1>
            <div class="date">📅 {target_date}</div>
            <div class="stats">
                <div class="stat-box">
                    <div class="number">{len(raw_schedules)}</div>
                    <div class="label">Classes</div>
                </div>
                <div class="stat-box">
                    <div class="number">{len(structured_data)}</div>
                    <div class="label">Subjects</div>
                </div>
                <div class="stat-box">
                    <div class="number">{total_links}</div>
                    <div class="label">Total Links</div>
                </div>
            </div>
        </div>
"""

    for subject_name, items in structured_data.items():
        html += f"""
        <div class="subject-card">
            <div class="subject-title">📖 {subject_name}</div>
"""
        for item in items:
            time_display = f"{item['start_time']} - {item['end_time']}" if item['end_time'] else item['start_time']
            html += f"""
            <div class="class-item">
                <div class="class-time">⏰ {time_display}</div>
                <div class="class-topic">{item['topic']}</div>
"""
            for ct, badge_class in [('videos', 'badge-video'), ('notes', 'badge-note'), ('DppVideos', 'badge-dpp'), ('DppNotes', 'badge-dpp')]:
                if item[ct]:
                    html += f"""
                <div class="content-section">
                    <div class="content-title"><span class="badge {badge_class}">{ct}</span></div>
                    <ul class="link-list">
"""
                    for link in item[ct]:
                        parts = link.split(":", 1)
                        if len(parts) == 2:
                            name, url = parts
                            html += f"                        <li><strong>{name}</strong><br><a href='{url}' target='_blank'>{url}</a></li>\n"
                        else:
                            html += f"                        <li>{link}</li>\n"
                    html += "                    </ul>\n                </div>\n"

            html += "            </div>\n"

        html += "        </div>\n"

    html += f"""
        <div class="footer">
            <p>Extracted by Extractor Bot | {bot_link}</p>
        </div>
    </div>
</body>
</html>"""
    return html

def generate_full_batch_html(batch_name, subjects_data, all_urls, bot_link, expiry_date):
    """Generate HTML output for Full Batch extraction"""
    video_count = len(re.findall(r'\.(m3u8|mpd|mp4)', "\n".join(all_urls)))
    pdf_count = len(re.findall(r'\.pdf', "\n".join(all_urls)))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{batch_name} - Full Batch Content</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); min-height: 100vh; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ background: rgba(255,255,255,0.95); border-radius: 20px; padding: 30px; margin-bottom: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); text-align: center; }}
        .header h1 {{ color: #333; font-size: 2em; margin-bottom: 10px; }}
        .header .subtitle {{ color: #11998e; font-size: 1.2em; font-weight: 600; }}
        .header .stats {{ display: flex; justify-content: center; gap: 30px; margin-top: 20px; flex-wrap: wrap; }}
        .stat-box {{ background: linear-gradient(135deg, #11998e, #38ef7d); color: white; padding: 15px 25px; border-radius: 15px; text-align: center; }}
        .stat-box .number {{ font-size: 1.8em; font-weight: bold; }}
        .stat-box .label {{ font-size: 0.9em; opacity: 0.9; }}
        .subject-card {{ background: rgba(255,255,255,0.95); border-radius: 20px; padding: 25px; margin-bottom: 25px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }}
        .subject-title {{ color: #11998e; font-size: 1.5em; font-weight: 700; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 3px solid #11998e; }}
        .chapter-item {{ background: #f0fff4; border-radius: 15px; padding: 18px; margin-bottom: 15px; border-left: 5px solid #11998e; }}
        .chapter-name {{ color: #333; font-size: 1.1em; font-weight: 600; margin-bottom: 12px; }}
        .content-section {{ margin-top: 10px; }}
        .content-title {{ color: #555; font-weight: 600; font-size: 0.85em; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
        .link-list {{ list-style: none; }}
        .link-list li {{ background: white; padding: 8px 12px; margin-bottom: 6px; border-radius: 8px; font-size: 0.85em; word-break: break-all; border: 1px solid #e0e0e0; }}
        .link-list li a {{ color: #11998e; text-decoration: none; }}
        .link-list li a:hover {{ text-decoration: underline; }}
        .footer {{ text-align: center; color: rgba(255,255,255,0.8); margin-top: 30px; padding: 20px; }}
        .badge {{ display: inline-block; padding: 3px 10px; border-radius: 15px; font-size: 0.7em; font-weight: 600; text-transform: uppercase; margin-right: 5px; }}
        .badge-video {{ background: #e3f2fd; color: #1976d2; }}
        .badge-note {{ background: #f3e5f5; color: #7b1fa2; }}
        .badge-dppv {{ background: #fff3e0; color: #e65100; }}
        .badge-dppn {{ background: #e8f5e9; color: #2e7d32; }}
        .expiry-info {{ color: #e74c3c; font-weight: 600; margin-top: 10px; }}
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 1.5em; }}
            .stats {{ gap: 15px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 {batch_name}</h1>
            <div class="subtitle">🗂️ Full Batch Content</div>
            <div class="stats">
                <div class="stat-box">
                    <div class="number">{len(all_urls)}</div>
                    <div class="label">Total Links</div>
                </div>
                <div class="stat-box">
                    <div class="number">{video_count}</div>
                    <div class="label">Videos</div>
                </div>
                <div class="stat-box">
                    <div class="number">{pdf_count}</div>
                    <div class="label">PDFs</div>
                </div>
            </div>
            {f'<div class="expiry-info">📅 Batch Expiry: {expiry_date}</div>' if expiry_date else ''}
        </div>
"""

    for subject_name, chapters in subjects_data.items():
        html += f"""
        <div class="subject-card">
            <div class="subject-title">📖 {subject_name}</div>
"""
        for chapter_name, content_types in chapters.items():
            html += f"""
            <div class="chapter-item">
                <div class="chapter-name">📂 {chapter_name}</div>
"""
            for ct, badge_class in [('videos', 'badge-video'), ('notes', 'badge-note'), ('DppVideos', 'badge-dppv'), ('DppNotes', 'badge-dppn')]:
                if ct in content_types and content_types[ct]:
                    html += f"""
                <div class="content-section">
                    <div class="content-title"><span class="badge {badge_class}">{ct}</span></div>
                    <ul class="link-list">
"""
                    for link in content_types[ct]:
                        parts = link.split(":", 1)
                        if len(parts) == 2:
                            name, url = parts
                            html += f"                        <li><strong>{name}</strong><br><a href='{url}' target='_blank'>{url}</a></li>\n"
                        else:
                            html += f"                        <li>{link}</li>\n"
                    html += "                    </ul>\n                </div>\n"

            html += "            </div>\n"

        html += "        </div>\n"

    html += f"""
        <div class="footer">
            <p>Extracted by Extractor Bot | {bot_link}</p>
        </div>
    </div>
</body>
</html>"""
    return html

async def login(app, user_id, m, all_urls, start_time, bname, batch_id, app_name, expiry_date=None, price=None, start_date=None, imageUrl=None, file_path_base=None, is_today_class=False, target_date=None, total_schedules=None):
    bname = await sanitize_bname(bname)
    if not file_path_base:
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
    credit = f"[{m.from_user.first_name}](tg://user?id={m.from_user.id})\n\n"
    drm_video_count = len(re.findall(r'\.(videoid|mpd|testbook)', all_text))
    enc_pdf_count = len(re.findall(r'\.pdf\*', all_text))
    if minutes == 0:
        if seconds < 1:
            formatted_time = f"{response_time:.2f} seconds"
        else:
            formatted_time = f"{seconds} seconds"
    else:
        formatted_time = f"{minutes} minutes {seconds} seconds"

    # Determine file extensions to send
    if is_today_class:
        extensions = ["txt", "zip", "json", "html"]
        class_info = f"\n📅 Date: {target_date}\n📊 Total Classes: {total_schedules}\n"
    else:
        extensions = ["txt", "zip", "json", "html"]
        class_info = "\n"

    expiry_display = expiry_date if expiry_date else "N/A"

    caption = (
        f"**APP NAME :** {app_name} \n\n"
        f"**Batch Name :** {batch_id} - {bname} \n\n"
        f"TOTAL LINK - {len(all_urls)} \n"
        f"Video Links - {video_count - drm_video_count} \n"
        f"Expiry Date:-**{expiry_display}\n **Extracted BY:{credit}"
        f"Total Pdf - {pdf_count} {class_info}\n\n"
        f"**╾───• Txt Extractor •───╼** \n"
        f" WAllah Wallah Habibi - @SmartBoy_ApnaMS \n"
        f"Time Taken: {formatted_time}"
    )

    files = [f"{file_path_base}.{ext}" for ext in extensions]
    for file in files:
        file_ext = os.path.splitext(file)[1][1:]
        try:
            if os.path.exists(file):
                copiable = await m.reply_document(document=file, caption=caption, file_name=f"{bname}.{file_ext}")
                await app.send_document(txt_dump, file, caption=caption, file_name=f"{bname}.{file_ext}")
            else:
                logging.warning(f"File not found: {file}")
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

    CONNECTOR = aiohttp.TCPConnector(limit=1000)
    async with aiohttp.ClientSession(connector=CONNECTOR) as session:
        try:
            if raw_text1.isdigit() and len(raw_text1) == 10:
                phone = raw_text1
                data = {
                    "username": phone,
                    "countryCode": "+91",
                    "organizationId": "5eb393ee95fab7468a79d189"
                }
                try:
                    async with session.post("https://api.penpencil.co/v2/users/get-otp?smsType=0", json=data, headers=headers) as response:
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
                    async with session.post("https://api.penpencil.co/v2/oauth/token", json=payload, headers=headers) as response:
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
                async with session.get("https://api.penpencil.co/v2/batches/all-purchased-batches", headers=headers, params=params) as response:
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
            url = f"https://api.penpencil.co/v2/batches/search?name={batch_search}"
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
                        raise Exception("No old batches found.")
                else:
                    raise Exception("Invalid batch index.")

                # === CALENDAR MENU: Full Batch vs Today's Class ===
                await editable.edit(
                    "**📅 Select Extraction Mode:**\n\n"
                    "1️⃣ **Full Batch** - Extract ALL content (videos, notes, DPPs)\n"
                    "2️⃣ **Today's Class** - Extract only scheduled classes for a specific date\n\n"
                    "**Send 1 or 2**"
                )
                try:
                    input_mode = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    mode_choice = input_mode.text.strip()
                    await input_mode.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return

                # Fetch batch details for expiry date
                url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/details"
                batch_details = await fetch_pwwp_data(session, url, headers=headers)

                expiry_date = None
                if batch_details and batch_details.get("success"):
                    expiry_date = batch_details.get("data", {}).get("expireAt") or batch_details.get("data", {}).get("batch", {}).get("expireAt")

                if mode_choice == "2":
                    # === TODAY'S CLASS MODE ===
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    await editable.edit(
                        f"**📅 Today's Class Mode**\n\n"
                        f"Today's date: `{today_str}`\n\n"
                        f"**Enter date in YYYY-MM-DD format**\n"
                        f"OR send 'today' for today's classes\n"
                        f"OR send 'tomorrow' for tomorrow's classes"
                    )
                    try:
                        input_date = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                        date_input = input_date.text.strip().lower()
                        await input_date.delete(True)
                    except:
                        await editable.edit("**Timeout! You took too long to respond**")
                        return

                    if date_input == "today":
                        target_date = datetime.now().strftime("%Y-%m-%d")
                    elif date_input == "tomorrow":
                        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    else:
                        # Validate date format
                        try:
                            datetime.strptime(date_input, "%Y-%m-%d")
                            target_date = date_input
                        except ValueError:
                            await editable.edit("**❌ Invalid date format! Use YYYY-MM-DD (e.g., 2024-01-15)**")
                            return

                    await editable.edit(f"**📅 Fetching scheduled classes for {target_date}...**")
                    start_time = time.time()

                    all_urls, file_path_base, total_schedules, error = await process_today_class(
                        session, selected_batch_id, selected_batch_name, 
                        target_date, headers, bot_link
                    )

                    if error:
                        await editable.edit(f"**❌ Error: {error}**")
                        return

                    if all_urls:
                        await login(
                            app, user_id, m, all_urls, start_time, 
                            clean_batch_name, selected_batch_id, 
                            app_name="Physics Wallah",
                            expiry_date=expiry_date,
                            file_path_base=file_path_base,
                            is_today_class=True,
                            target_date=target_date,
                            total_schedules=total_schedules
                        )
                        await editable.delete()
                    else:
                        await editable.edit(f"**⚠️ No content found for {target_date}**")

                elif mode_choice == "1":
                    # === FULL BATCH MODE ===
                    await editable.edit(f"**Extracting FULL BATCH course : {selected_batch_name} ...**")
                    start_time = time.time()

                    if batch_details and batch_details.get("success"):
                        subjects = batch_details.get("data", {}).get("subjects", [])
                        json_data = {selected_batch_name: {}}
                        all_subject_urls = {}

                        # Store subjects data for HTML
                        subjects_html_data = {}

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

                        # Build subjects_html_data
                        all_urls = []
                        for subject_name in all_subject_urls:
                            subjects_html_data[subject_name] = {}
                            all_urls.extend(all_subject_urls[subject_name])

                        # Get chapter-wise data for HTML
                        for subject in subjects:
                            subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
                            subject_id = subject.get("_id")
                            subjects_html_data[subject_name] = {}
                            chapters = await get_pwwp_all_chapters(session, selected_batch_id, subject_id, headers)
                            for chapter in chapters:
                                chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")
                                chapter_content = await process_pwwp_chapters(session, chapter["_id"], selected_batch_id, subject_id, headers)
                                subjects_html_data[subject_name][chapter_name] = {}
                                for ct in ['videos', 'notes', 'DppNotes', 'DppVideos']:
                                    if chapter_content.get(ct):
                                        subjects_html_data[subject_name][chapter_name][ct] = chapter_content[ct]

                        # Generate HTML
                        html_content = generate_full_batch_html(
                            selected_batch_name, subjects_html_data, 
                            all_urls, bot_link, expiry_date
                        )
                        with open(f"{file_path_base}.html", 'w', encoding='utf-8') as f:
                            f.write(html_content)

                        await login(
                            app, user_id, m, all_urls, start_time, 
                            clean_batch_name, selected_batch_id, 
                            app_name="Physics Wallah",
                            expiry_date=expiry_date,
                            file_path_base=file_path_base
                        )
                        await editable.delete()
                    else:
                        raise Exception(f"Error fetching batch details: {batch_details.get('message')}")
                else:
                    raise Exception("Invalid mode selection. Send 1 for Full Batch or 2 for Today's Class.")
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
