import os
import requests
import asyncio
import cloudscraper
import re
from pyrogram import filters
from Extractor import app
from config import CHANNEL_ID
import logging
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from datetime import datetime
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

log_channel = CHANNEL_ID

requests = cloudscraper.create_scraper()

ACCOUNT_ID = "6206459123001"
BCOV_POLICY = "BCpkADawqM1474MvKwYlMRZNBPoqkJY-UWm7zE1U769d5r5kqTjG0v8L-THXuVZtdIQJpfMPB37L_VJQxTKeNeLO2Eac_yMywEgyV9GjFDQ2LTiT4FEiHhKAUvdbx9ku6f815uIDd"
bc_url = f"https://edge.api.brightcove.com/playback/v1/accounts/{ACCOUNT_ID}/videos/"

# Define headers for all API requests
headers = {
    "Accept-Encoding": "gzip",
    "apptype": "android",
    "appver": "107",
    "Connection": "Keep-Alive",
    "Content-Type": "application/json; charset=UTF-8",
    "cwkey": "rUu1RIbI4vojHwIeU0EbMAAtpnTFnCgd43XjhxS7AJY=",
    "Host": "elearn.crwilladmin.com",
    "User-Agent": "okhttp/5.0.0-alpha.2",
    "userType": "",
}

# Encryption Config
KEY = b'm88=p?h,u4*I>A.|*()&7~.?\\:2{Yr+~'
IV = b'*}~;&;$;*:-![@;>'

# Encryption Functions
def enc_url(url):
    try:
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        ciphertext = cipher.encrypt(pad(url.encode(), AES.block_size))
        encrypted_url = "enc://:" + b64encode(ciphertext).decode('utf-8')
        logger.info(f"Encrypted URL: {url} -> {encrypted_url}")
        return encrypted_url
    except Exception as e:
        logger.error(f"Encryption failed for URL {url}: {e}")
        return url

def split_name_url(line):
    if ': ' in line:
        parts = line.rsplit(': ', 1)
        name = parts[0].strip()
        url = parts[1].strip()
        if re.match(r"https?://", url):
            logger.info(f"Valid URL found: {url}")
            return name, url
        else:
            logger.warning(f"Invalid URL format in line: {line}")
    else:
        logger.warning(f"No ': ' separator in line: {line}")
    return line.strip(), None

def encrypt_file(input_file):
    output_file = "encrypted_" + input_file
    encrypted_count = 0
    try:
        with open(input_file, "r", encoding="utf-8") as f, open(output_file, "w", encoding="utf-8") as out:
            for line in f:
                name, url = split_name_url(line)
                if url:
                    enc = enc_url(url)
                    out.write(f"{name}: {enc}\n")
                    encrypted_count += 1
                else:
                    out.write(line.strip() + "\n")
        logger.info(f"Encrypted {encrypted_count} URLs in {output_file}")
        return output_file
    except Exception as e:
        logger.error(f"Failed to encrypt file {input_file}: {e}")
        return None

async def sanitize_filename(name, max_length=50):
    name = re.sub(r'[\\/:*?"<>|\t\n\r]+', '', name).strip()
    if len(name) > max_length:
        name = name[:max_length]
    return name

async def careerdl(app, message, headers, raw_text2, token, raw_text3, prog, name):
    num_id = raw_text3.split('&')
    fuck = ""

    # Update headers with token for authenticated requests
    headers_with_token = headers.copy()
    headers_with_token["token"] = token

    for x in range(len(num_id)):
        id_text = num_id[x].strip()
        if not id_text:
            continue

        try:
            # Video Details
            details_url = f"https://elearn.crwilladmin.com/api/v9/batch-detail/{raw_text2}?topicId={id_text}"
            response = requests.get(details_url, headers=headers_with_token)
            if response.status_code != 200:
                logger.error(f"Failed to fetch details for topic ID {id_text}: {response.status_code} {response.text}")
                continue

            try:
                data = response.json()
                if not isinstance(data, dict) or "data" not in data:
                    logger.error(f"Invalid details response for topic ID {id_text}: {data}")
                    continue
            except ValueError:
                logger.error(f"Invalid JSON response for topic ID {id_text}: {response.text}")
                continue

            details_list = data["data"]["class_list"]
            batch_class = details_list["classes"]
            batch_class.reverse()

            for video_data in batch_class:
                vid_id = video_data['id']
                lesson_name = video_data['lessonName']
                lesson_ext = video_data['lessonExt']

                if lesson_ext == 'brightcove':
                    lesson_url_response = requests.get(
                        f"https://elearn.crwilladmin.com/api/v9/class-detail/{vid_id}",
                        headers=headers_with_token
                    )
                    if lesson_url_response.status_code != 200:
                        logger.error(f"Failed to fetch class detail for video ID {vid_id}: {lesson_url_response.status_code}")
                        continue

                    try:
                        lesson_data = lesson_url_response.json()
                        lesson_url = lesson_data['data']['class_detail']['lessonUrl']
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing class detail for video ID {vid_id}: {e}")
                        continue

                    video_link = f"{bc_url}{lesson_url}/master.m3u8?bcov_auth={token}"
                    fuck += f"{lesson_name}: {video_link}\n"
                
                elif lesson_ext == 'youtube':
                    lesson_url_response = requests.get(
                        f"https://elearn.crwilladmin.com/api/v9/class-detail/{vid_id}",
                        headers=headers_with_token
                    )
                    if lesson_url_response.status_code != 200:
                        logger.error(f"Failed to fetch class detail for video ID {vid_id}: {lesson_url_response.status_code}")
                        continue

                    try:
                        lesson_data = lesson_url_response.json()
                        lesson_url = lesson_data['data']['class_detail']['lessonUrl']
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing class detail for video ID {vid_id}: {e}")
                        continue

                    video_link = f"https://www.youtube.com/embed/{lesson_url}"
                    fuck += f"{lesson_name}: {video_link}\n"

            # Notes Details
            notes_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{raw_text2}?type=notes"
            notes_resp = requests.get(notes_url, headers=headers_with_token)
            if notes_resp.status_code != 200:
                logger.error(f"Failed to fetch notes for batch {raw_text2}: {notes_resp.status_code}")
                continue

            try:
                notes_data = notes_resp.json()
                if 'data' not in notes_data or 'batch_topic' not in notes_data['data']:
                    logger.error(f"Invalid notes response for batch {raw_text2}: {notes_data}")
                    continue
            except ValueError:
                logger.error(f"Invalid JSON notes response for batch {raw_text2}: {notes_resp.text}")
                continue

            notes_topics = notes_data['data']['batch_topic']
            for topic in notes_topics:
                topic_id = topic['id']
                notes_topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-notes/{raw_text2}?topicId={topic_id}"
                notes_topic_resp = requests.get(notes_topic_url, headers=headers_with_token)
                if notes_topic_resp.status_code != 200:
                    logger.error(f"Failed to fetch notes details for topic ID {topic_id}: {notes_topic_resp.status_code}")
                    continue

                try:
                    notes_topic_data = notes_topic_resp.json()
                    if 'data' not in notes_topic_data or 'notesDetails' not in notes_topic_data['data']:
                        logger.error(f"Invalid notes details response for topic ID {topic_id}: {notes_topic_data}")
                        continue
                except ValueError:
                    logger.error(f"Invalid JSON notes details response for topic ID {topic_id}: {notes_topic_resp.text}")
                    continue

                notes_details = notes_topic_data['data']['notesDetails']
                for note_detail in reversed(notes_details):
                    doc_title = note_detail.get('docTitle', '')
                    doc_url = note_detail.get('docUrl', '').replace(' ', '%20')
                    
                    if f"{doc_title}: {doc_url}\n" not in fuck:
                        fuck += f"{doc_title}: {doc_url}\n"

        except Exception as e:
            logger.error(f"Error processing topic ID {id_text}: {e}")
            continue

    if not fuck:
        logger.error("No content collected for batch")
        await prog.delete()
        await message.reply_text("❌ No content found for the selected batch.")
        return

    logger.info(f"Collected content sample: {fuck[:200]}")  # Log sample content

    # Sanitize and create file name
    name = await sanitize_filename(name)
    file_name = f"{name}.txt"
    enc_file_name = f"encrypted_{name}.txt"

    # Write decrypted file
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(fuck)
        logger.info(f"Decrypted file written: {file_name}")
    except Exception as e:
        logger.error(f"Failed to write decrypted file {file_name}: {e}")
        await prog.delete()
        await message.reply_text("❌ Error creating file.")
        return

    # Generate encrypted file
    enc_file_path = encrypt_file(file_name)
    if not enc_file_path or not os.path.exists(enc_file_path):
        logger.error(f"Encrypted file not created: {enc_file_path}")
        await prog.delete()
        await message.reply_text("❌ Error encrypting file.")
        if os.path.exists(file_name):
            os.remove(file_name)
            logger.info(f"Cleaned up file: {file_name}")
        return

    c_txt = f"**App Name: CareerWill \n Batch Name: `{name}`**"
    try:
        # Send encrypted file to user
        await app.send_document(
            chat_id=message.chat.id,
            document=enc_file_path,
            caption=c_txt,
            file_name=f"encrypted_{name}.txt"
        )
        logger.info(f"Sent encrypted file {enc_file_path} to user {message.chat.id}")

        # Send decrypted file to log channel
        await app.send_document(
            chat_id=log_channel,
            document=file_name,
            caption=c_txt,
            file_name=f"{name}.txt"
        )
        logger.info(f"Sent decrypted file {file_name} to log channel {log_channel}")
    except Exception as e:
        logger.error(f"Error sending documents: {e}")
        await message.reply_text(f"❌ Error sending files: {str(e)}")
    finally:
        await prog.delete()
        for f in [file_name, enc_file_path]:
            if f and os.path.exists(f):
                os.remove(f)
                logger.info(f"Cleaned up file: {f}")

@app.on_message(filters.command(["cw"]))
async def career_will(app, message):
    try:
        input1 = await app.ask(message.chat.id, text="<blockquote>**Send ID & Password in this manner otherwise bot will not respond.\n\nSend like this:-  ID*Password\n\n OR Send Your Token**</blockquote>")
        login_url = "https://elearn.crwilladmin.com/api/v9/login-other"
        raw_text = input1.text
     
        if "*" in raw_text:
            # Use the defined headers for login
            login_headers = headers.copy()
            email, password = raw_text.split("*")
            data = {
                "deviceType": "android",
                "password": password,
                "deviceModel": "Xiaomi M2007J20CI",
                "deviceVersion": "Q(Android 10.0)",
                "email": email,
                "deviceIMEI": "d57adbd8a7b8u9i9",
                "deviceToken": "c8HzsrndRB6dMaOuKW2qMS:APA91bHu4YCP4rqhpN3ZnLjzL3LuLljxXua2P2aUXfIS4nLeT4LnfwWY6MiJJrG9XWdBUIfuA6GIXBPIRTGZsDyripIXoV1CyP3kT8GKuWHgGVn0DFRDEnXgAIAmaCE6acT3oussy2"
            }

            response = requests.post(login_url, headers=login_headers, json=data)
            if response.status_code != 200:
                await message.reply_text(f"Login failed with status {response.status_code}: {response.text}")
                return

            try:
                token = response.json()["data"]["token"]
            except (KeyError, ValueError) as e:
                await message.reply_text(f"Login response invalid: {response.text}")
                return

            await app.send_message(log_channel, response.text)
            await message.reply_text(f"<blockquote>**Login Successful**\n\n`{token}`</blockquote>")
        else:
            token = raw_text
    except Exception as e:
        await message.reply_text(f"An error occurred during login: {e}")
        return

    # Update headers with token for subsequent requests
    headers_with_token = headers.copy()
    headers_with_token["token"] = token

    await input1.delete(True)
    batch_url = "https://elearn.crwilladmin.com/api/v9/my-batch"
    response = requests.get(batch_url, headers=headers_with_token)
    
    if response.status_code != 200:
        await message.reply_text(f"Batch API request failed with status {response.status_code}: {response.text}")
        return

    try:
        data = response.json()
        if not isinstance(data, dict):
            await message.reply_text(f"Batch API response is not a dictionary: {data}")
            return
        if "data" not in data:
            await message.reply_text(f"'data' key missing in batch API response: {data}")
            return
        if "batchData" not in data["data"]:
            await message.reply_text(f"'batchData' key missing in batch API response: {data['data']}")
            return
        topicid = data["data"]["batchData"]
    except Exception as e:
        await message.reply_text(f"Error processing batch API response: {str(e)}")
        return

    FFF = "**BATCH-ID     -     BATCH NAME**\n\n"
    for item in topicid:
        FFF += f"`{item['id']}`     -    **{item['batchName']}**\n\n"
    dl = f"<blockquote>**CAREERWILL LOGIN SUCCESS**\n\n'{raw_text}'\n\n`{token}`\n{FFF}</blockquote>"

    await message.reply_text(f"<blockquote>**HERE IS YOUR BATCH**\n\n{FFF}</blockquote>")
    input2 = await app.ask(message.chat.id, text="<blockquote>**Now send the Batch ID to Download**</blockquote>")
    raw_text2 = input2.text
    await app.send_message(log_channel, dl)
    topic_url = "https://elearn.crwilladmin.com/api/v9/batch-topic/" + raw_text2 + "?type=class"
    response = requests.get(topic_url, headers=headers_with_token)

    if response.status_code != 200:
        await message.reply_text(f"Topic API request failed with status {response.status_code}: {response.text}")
        return

    try:
        topic_data = response.json()
        if "data" not in topic_data:
            await message.reply_text(f"'data' key missing in topic API response: {topic_data}")
            return
        batch_data = topic_data['data']['batch_topic']
        name = topic_data["data"]["batch_detail"]["name"]
    except Exception as e:
        await message.reply_text(f"Error processing topic API response: {str(e)}")
        return

    BBB = "**TOPIC-ID - TOPIC**\n\n"
    id_num = ""
    for data in batch_data:
        topic_id = data["id"]
        topic_name = data["topicName"]
        id_num += f"{topic_id}&"
        BBB += f"`{topic_id}` -  **{topic_name}** \n\n"

    await message.reply_text(f"<blockquote>**Batches details of {name}**\n\n{BBB}</blockquote>")
    input3 = await app.ask(message.chat.id, text=f"<blockquote>Now send the **Topic IDs** to Download\n\nSend like this **1&2&3&4** so on\nor copy paste or edit **below ids** according to you :\n\n**Enter this to download full batch :-**\n`{id_num}`</blockquote>")
    raw_text3 = input3.text

    prog = await message.reply_text("<blockquote>**Extracting Videos Links Please Wait  📥 **</blockquote>")

    try:
        await careerdl(app, message, headers, raw_text2, token, raw_text3, prog, name)
    except Exception as e:
        logger.error(f"Error in careerdl: {e}")
        await prog.delete()
        await message.reply_text(f"❌ Error extracting content: {str(e)}")
