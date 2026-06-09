import os
import requests
import asyncio
import cloudscraper
from pyrogram import filters
from Extractor import app
from config import CHANNEL_ID
from Crypto.Cipher import AES
from pymongo import MongoClient
import base64

OWNER_ID = 7438818824  # <-- Replace with your Telegram user ID

log_channel = CHANNEL_ID
# MongoDB setup
mongo = MongoClient("")
db = mongo["yourbotdb"]
auth_collection = db["auth_users"]

# 🔐 AUTH CHECK FUNCTION (ADD THIS HERE)
def is_authorized(user_id):
    return auth_collection.find_one({"user_id": user_id}) is not None

# ✅ /authshiv Command
@app.on_message(filters.command("authcw"))
async def authorize_user(app, m):
    if m.from_user.id != OWNER_ID:
        await m.reply_text("🚫 Only the bot owner can authorize users.")
        return

    # Get user ID from command argument
    try:
        user_id = int(m.command[1])
    except (IndexError, ValueError):
        await m.reply_text("⚠️ Usage: `/authshiv <user_id>`", quote=True)
        return

    if auth_collection.find_one({"user_id": user_id}):
        await m.reply_text("✅ User already authorized.")
    else:
        auth_collection.insert_one({"user_id": user_id})
        await m.reply_text(f"✅ Authorized user: `{user_id}`")


@app.on_message(filters.command("unauthcw"))
async def unauthorize_user(app, m):
    if m.from_user.id != OWNER_ID:
        await m.reply_text("🚫 Only the bot owner can unauthorize.")
        return

    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
    else:
        await m.reply_text("⚠️ Reply to a user's message to unauthorize.")
        return

    result = auth_collection.delete_one({"user_id": user_id})
    if result.deleted_count:
        await m.reply_text(f"❌ User `{user_id}` unauthorized.")
    else:
        await m.reply_text("⚠️ User was not authorized.")

        

requests = cloudscraper.create_scraper()

ACCOUNT_ID = "6206459123001"
BCOV_POLICY = "BCpkADawqM1474MvKwYlMRZNBPoqkJY-UWm7zE1U769d5r5kqTjG0v8L-THXuVZtdIQJpfMPB37L_VJQxTKeNeLO2Eac_yMywEgyV9GjFDQ2LTiT4FEiHhKAUvdbx9ku6fGnQKSMB8J5uIDd"
bc_url = f"https://edge.api.brightcove.com/playback/v1/accounts/{ACCOUNT_ID}/videos/"
bc_hdr = {"BCOV-POLICY": BCOV_POLICY}

CAREERWILL_CW_KEY = "PBccoITYzIdkpz2D2F5/lj/oLvkJiwcE9yv2yx3cAuqqYGtrnb4Yu1TnUiDG+gHK"

# AES Encryption Key and IV
KEY = b'm98=p?h,u6*I>A.|*()&7-.?\:2{Yr+-'
IV = b'*}~;&;$;*:-![@;>'

# Define headers for all API requests
headers = {
    "Accept-Encoding": "gzip",
    "apptype": "android",
    "appver": "107",
    "Connection": "Keep-Alive",
    "Content-Type": "application/json; charset=UTF-8",
    "cwkey": CAREERWILL_CW_KEY,
    "Host": "elearn.crwilladmin.com",
    "User-Agent": "okhttp/5.0.0-alpha.2",
    "userType": "",
}

def aes_encrypt(text):
    """Encrypt text using AES-256-CBC with provided KEY and IV."""
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    # Pad text to multiple of 16 bytes
    pad_length = 16 - (len(text) % 16)
    padded_text = text + (chr(pad_length) * pad_length).encode()
    encrypted = cipher.encrypt(padded_text)
    # Encode to base64 for text-safe representation
    return base64.b64encode(encrypted).decode()

async def careerdl(app, message, headers, raw_text2, token, raw_text3, prog, name):
    num_id = raw_text3.split('&')
    encrypted_content = ""  # For user (AES-encrypted links)
    decrypted_content = ""  # For log channel (decrypted links)

    headers_with_token = headers.copy()
    headers_with_token["token"] = token

    for x in range(len(num_id)):
        id_text = num_id[x]

        try:
            # Video Details
            details_url = f"https://elearn.crwilladmin.com/api/v9/batch-detail/{raw_text2}?topicId={id_text}"
            response = requests.get(details_url, headers=headers_with_token)
            if response.status_code != 200:
                print(f"Failed to fetch details for topic ID {id_text}: {response.status_code} {response.text}")
                continue

            try:
                data = response.json()
                if not isinstance(data, dict) or "data" not in data:
                    print(f"Invalid details response for topic ID {id_text}: {data}")
                    continue
            except ValueError:
                print(f"Invalid JSON response for topic ID {id_text}: {response.text}")
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
                        print(f"Failed to fetch class detail for video ID {vid_id}: {lesson_url_response.status_code}")
                        continue

                    try:
                        lesson_data = lesson_url_response.json()
                        lesson_url = lesson_data['data']['class_detail']['lessonUrl']
                    except (ValueError, KeyError) as e:
                        print(f"Error parsing class detail for video ID {vid_id}: {e}")
                        continue

                    video_link = f"{bc_url}{lesson_url}/master.m3u8?bcov_auth={token}"
                    encrypted_link = f"enc://:{aes_encrypt(video_link.encode())}"
                    encrypted_content += f"{lesson_name}: {encrypted_link}\n"
                    decrypted_content += f"{lesson_name}: {video_link}\n"
                
                elif lesson_ext == 'youtube':
                    lesson_url_response = requests.get(
                        f"https://elearn.crwilladmin.com/api/v9/class-detail/{vid_id}",
                        headers=headers_with_token
                    )
                    if lesson_url_response.status_code != 200:
                        print(f"Failed to fetch class detail for video ID {vid_id}: {lesson_url_response.status_code}")
                        continue

                    try:
                        lesson_data = lesson_url_response.json()
                        lesson_url = lesson_data['data']['class_detail']['lessonUrl']
                    except (ValueError, KeyError) as e:
                        print(f"Error parsing class detail for video ID {vid_id}: {e}")
                        continue

                    video_link = f"https://www.youtube.com/embed/{lesson_url}"
                    encrypted_link = f"enc://:{aes_encrypt(video_link.encode())}"
                    encrypted_content += f"{lesson_name}: {encrypted_link}\n"
                    decrypted_content += f"{lesson_name}: {video_link}\n"

            # Notes Details
            notes_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{raw_text2}?type=notes"
            notes_resp = requests.get(notes_url, headers=headers_with_token)
            if notes_resp.status_code != 200:
                print(f"Failed to fetch notes for batch {raw_text2}: {notes_resp.status_code}")
                continue

            try:
                notes_data = notes_resp.json()
                if 'data' not in notes_data or 'batch_topic' not in notes_data['data']:
                    print(f"Invalid notes response for batch {raw_text2}: {notes_data}")
                    continue
            except ValueError:
                print(f"Invalid JSON notes response for batch {raw_text2}: {notes_resp.text}")
                continue

            notes_topics = notes_data['data']['batch_topic']
            for topic in notes_topics:
                topic_id = topic['id']
                notes_topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-notes/{raw_text2}?topicId={topic_id}"
                notes_topic_resp = requests.get(notes_topic_url, headers=headers_with_token)
                if notes_topic_resp.status_code != 200:
                    print(f"Failed to fetch notes details for topic ID {topic_id}: {notes_topic_resp.status_code}")
                    continue

                try:
                    notes_topic_data = notes_topic_resp.json()
                    if 'data' not in notes_topic_data or 'notesDetails' not in notes_topic_data['data']:
                        print(f"Invalid notes details response for topic ID {topic_id}: {notes_topic_data}")
                        continue
                except ValueError:
                    print(f"Invalid JSON notes details response for topic ID {topic_id}: {notes_topic_resp.text}")
                    continue

                notes_details = notes_topic_data['data']['notesDetails']
                for note_detail in reversed(notes_details):
                    doc_title = note_detail.get('docTitle', '')
                    doc_url = note_detail.get('docUrl', '').replace(' ', '%20')
                    
                    if f"{doc_title}: {doc_url}\n" not in encrypted_content:
                        encrypted_content += f"{doc_title}: {doc_url}\n"
                        decrypted_content += f"{doc_title}: {doc_url}\n"

        except Exception as e:
            print(f"Error processing topic ID {id_text}: {e}")
            continue
    
    if '/' in name:
        name = name.replace("/", "_")
    
    encrypted_file = f"encrypted_{name}.txt"
    decrypted_file = f"{name}_decrypted.txt"
    
    with open(encrypted_file, 'w') as f:
        f.write(encrypted_content)
    with open(decrypted_file, 'w') as f:
        f.write(decrypted_content)

    credit = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n"
    caption = (
        f"**APP NAME :** cw [pro] \n\n"
        f"**Extracted BY: {credit}** \n\n"
        f"**[Ksi ko usa ka account chiye tho msg kr lo stock h new Msg here @Hidfgh] \n\n**"
        f"**╾───• Txtx Extractor •───╼** uploader in cheap price @king_rajasthan_23_bot"
    )
    
    try:
        await app.send_document(
            chat_id=message.chat.id,
            document=encrypted_file,
            caption=caption
        )
        await app.send_document(
            log_channel,
            document=decrypted_file,
            caption=caption
        )
    except Exception as e:
        print(f"Error sending document: {e}")
    finally:
        await prog.delete()
        if os.path.exists(encrypted_file):
            os.remove(encrypted_file)
        if os.path.exists(decrypted_file):
            os.remove(decrypted_file)

@app.on_message(filters.command("cwc"))
async def handle_utk_logic(app, m):
    if not is_authorized(m.from_user.id):
        await m.reply_text("🚫 Access Denied.\nUse /authshiv to get access.")
        return
    await career_will(app, m)       
async def career_will(app, message):
    # Step 1: Send batchid.txt as a document
    batchid_file = "Txt/batchid.txt"
    try:
        if not os.path.exists(batchid_file):
            await message.reply_text("Error: `batchid.txt` file not found.")
            return

        editable = await message.reply_text("⏳ Sending batch list...")
        await message.reply_document(
            document=batchid_file,
            caption=(
                "**📚 CareerWill Batch List **\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "**👤 Created By:** [YourName](https://t.me/YourHandle)"
            )
        )
        await editable.delete()
    except Exception as e:
        await message.reply_text(f"Error sending batchid.txt: {str(e)}")
        return

    # Step 2: Ask for batch ID
    input2 = await app.ask(message.chat.id, text="<blockquote>**Now send the Batch ID to Download**</blockquote>")
    raw_text2 = input2.text.strip()

    # Step 3: Read idpass.txt to find the corresponding phone_number*password
    idpass_file = "Txt/idpass.txt"
    login_credentials = None
    try:
        if not os.path.exists(idpass_file):
            await message.reply_text("Error: `idpass.txt` file not found.")
            return

        with open(idpass_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.endswith(f":{raw_text2}"):
                    login_credentials = line.split(":")[0]
                    break

        if not login_credentials:
            await message.reply_text(f"Error: No credentials found for Batch ID `{raw_text2}`.")
            return
    except Exception as e:
        await message.reply_text(f"Error reading idpass.txt: {str(e)}")
        return

    # Step 4: Perform login using the found credentials
    login_url = "https://elearn.crwilladmin.com/api/v9/login-other"
    try:
        if "*" not in login_credentials:
            await message.reply_text(f"Error: Invalid credential format for Batch ID `{raw_text2}`. Expected `phone_number*password`.")
            return

        phone_number, password = login_credentials.split("*")
        login_headers = headers.copy()
        data = {
            "deviceType": "android",
            "password": password,
            "deviceModel": "Xiaomi M2007J20CI",
            "deviceVersion": "Q(Android 10.0)",
            "email": phone_number,
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
        await message.reply_text(f"<blockquote>**Login Successful**\n\n`le le `</blockquote>")
    except Exception as e:
        await message.reply_text(f"An error occurred during login: {e}")
        return

    # Step 5: Fetch batch topics
    headers_with_token = headers.copy()
    headers_with_token["token"] = token
    topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{raw_text2}?type=class"
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
    input3 = await app.ask(message.chat.id, f"<blockquote>Now send the **Topic IDs** to Download\n\nSend like this **1&2&3&4** so on\nor copy paste or edit **below ids** according to you :\n\n**Enter this to download full batch :-**\n`{id_num}`</blockquote>")
    raw_text3 = input3.text

    prog = await message.reply_text("<blockquote>**Extracting Videos Links Please Wait  📥 **</blockquote>")

    try:
        await careerdl(app, message, headers, raw_text2, token, raw_text3, prog, name)
    except Exception as e:
        await message.reply_text(f"Error during download: {str(e)}")
