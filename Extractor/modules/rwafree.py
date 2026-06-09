import asyncio
import aiohttp
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
import base64
import time
from pyrogram import filters
from pyrogram.errors import PeerIdInvalid
from Extractor import app
import os

log_channel = -1002546086874 # Get CHANNEL_ID from environment variable

def decrypt(enc):
    enc = b64decode(enc.split(':')[0])
    key = '638udh3829162018'.encode('utf-8')
    iv = 'fedcba9876543210'.encode('utf-8')
    if len(enc) == 0:
        return ""
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = unpad(cipher.decrypt(enc), AES.block_size)
    return plaintext.decode('utf-8')

def decode_base64(encoded_str):
    try:
        decoded_bytes = base64.b64decode(encoded_str)
        decoded_str = decoded_bytes.decode('utf-8')
        return decoded_str
    except Exception as e:
        return f"Error decoding string: {e}"

async def fetch_item_details(session, api_base, course_id, item, headers):
    fi = item.get("id")
    vt = item.get("Title", "")
    outputs = []

    try:
        async with session.get(f"{api_base}/get/fetchVideoDetailsById?course_id={course_id}&folder_wise_course=1&ytflag=0&video_id={fi}", headers=headers) as response:
            if response.headers.get('Content-Type', '').startswith('application/json'):
                r4 = await response.json()
                data = r4.get("data")
                if not data:
                    return []

                vt = data.get("Title", "")
                vl = data.get("download_link", "")

                if vl:
                    dvl = decrypt(vl)
                    outputs.append(f"{vt}:{dvl}")
                else:
                    encrypted_links = data.get("encrypted_links", [])
                    for link in encrypted_links:
                        a = link.get("path")
                        k = link.get("key")

                        if a and k:
                            k1 = decrypt(k)
                            k2 = decode_base64(k1)
                            da = decrypt(a)
                            outputs.append(f"{vt}:{da}*{k2}")
                            break
                        elif a:
                            da = decrypt(a)
                            outputs.append(f"{vt}:{da}")
                            break

                if "material_type" in data:
                    mt = data["material_type"]
                    if mt == "VIDEO":
                        p1 = data.get("pdf_link", "")
                        pk1 = data.get("pdf_encryption_key", "")
                        p2 = data.get("pdf_link2", "")
                        pk2 = data.get("pdf2_encryption_key", "")
                        if p1:
                            dp1 = decrypt(p1)
                            depk1 = decrypt(pk1)
                            outputs.append(f"{vt}:{dp1}*{depk1}")
                        if p2:
                            dp2 = decrypt(p2)
                            depk2 = decrypt(pk2)
                            outputs.append(f"{vt}:{dp2}*{depk2}")
            else:
                error_page = await response.text()
                print(f"Error: Unexpected response for video ID {fi}:\n{error_page}")
                return []
    except Exception as e:
        print(f"An error occurred while fetching details for video ID {fi}: {str(e)}")
        return []

    return outputs

async def fetch_folder_contents(session, api_base, course_id, folder_id, headers):
    outputs = []

    try:
        async with session.get(f"{api_base}/get/folder_contentsv2?course_id={course_id}&parent_id={folder_id}", headers=headers) as response:
            j = await response.json()
            tasks = []
            if "data" in j:
                for item in j["data"]:
                    mt = item.get("material_type")
                    tasks.append(fetch_item_details(session, api_base, course_id, item, headers))
                    if mt == "FOLDER":
                        tasks.append(fetch_folder_contents(session, api_base, course_id, item["id"], headers))

            if tasks:
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res:
                        outputs.extend(res)
    except Exception as e:
        print(f"Error fetching folder contents for folder {folder_id}: {str(e)}")
        outputs.append(f"Error fetching folder contents for folder {folder_id}. Error: {e}")

    return outputs

async def resolve_log_channel(client, channel_id):
    try:
        await client.resolve_peer(channel_id)
        return True
    except PeerIdInvalid:
        print(f"Error: Bot cannot access the log channel {channel_id}. Ensure the bot is added to the channel.")
        return False

@app.on_message(filters.command("rwafree"))
async def rwafree_command(app, message):
    if not log_channel:
        await message.reply_text("Error: CHANNEL_ID is not configured. Please contact the administrator.")
        return

    log_channel_resolved = await resolve_log_channel(app, log_channel)
    if not log_channel_resolved:
        await message.reply_text("Error: Bot cannot access the log channel. Please ensure the bot is added to the channel and has permission to send messages.")
        return

    api_base = "https://rozgarapinew.teachx.in"
    app_name = "Rozgar API"
    userid = "517077"
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6IjUxNzA3NyIs “‘ImVtYWlsIjoidml2ZWtrYXNhbmE0QGdtYWlsLmNvbSIsInRpbWVzdGFtcCI6MTcyNjU2MTM2Nn0.XimZ3jxS_j-7B4BpTUR9ZeeaJ8at-ROfPYMdm0GCf6I"

    hdr1 = {
        "Client-Service": "Appx",
        "source": "website",
        "Auth-Key": "appxapi",
        "Authorization": token,
        "User-ID": userid
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{api_base}/get/get_all_purchases?userid={userid}&item_type=10", headers=hdr1) as res1:
                if res1.status != 200:
                    await message.reply_text(f"Failed to fetch batch details. HTTP Status: {res1.status}")
                    print(f"API request failed with status {res1.status}: {await res1.text()}")
                    return

                j1 = await res1.json()
                print(f"API Response: {j1}")  # Debug log to check the API response
        except Exception as e:
            await message.reply_text("Error fetching batch details. Please try again later.")
            print(f"Error fetching batch details: {str(e)}")
            return

        FFF = "**COURSE-ID  -  COURSE NAME**\n\n"
        valid_ids = []
        start = ""
        end = ""
        pricing = ""
        if "data" in j1 and j1["data"]:
            for item in j1["data"]:
                for ct in item["coursedt"]:
                    i = ct.get("id")
                    cn = ct.get("course_name")
                    start = ct.get("start_date")
                    end = ct.get("end_date")
                    pricing = ct.get("price")
                    FFF += f"**`{i}`   -   `{cn}`**\n\n"
                    valid_ids.append(i)
        else:
            await message.reply_text("No batches found for this account. The token may be invalid or expired.")
            print("No batches found in API response.")
            return

        if FFF.strip() == "**COURSE-ID  -  COURSE NAME**\n\n":
            await message.reply_text("No batches available to display.")
            return

        if len(FFF) <= 4096:
            editable1 = await message.reply_text(FFF)
        else:
            plain_FFF = FFF.replace("**", "").replace("`", "")
            file_path = f"{app_name}_batches.txt"
            with open(file_path, "w") as file:
                file.write(plain_FFF)
            await app.send_document(
                message.chat.id,
                document=file_path,
                caption="Too many batches, select batch ID from txt"
            )
            try:
                await app.send_document(log_channel, document=file_path, caption="Many Batches Found")
            except PeerIdInvalid:
                await message.reply_text("Error: Bot cannot send to the log channel. Please ensure the bot is added to the channel.")
                os.remove(file_path)
                return
            os.remove(file_path)
            editable1 = None

        input2 = await app.ask(message.chat.id, text="**Now send the Course ID to Download**")
        raw_text2 = input2.text
        if raw_text2 not in valid_ids:
            await message.reply_text("**Invalid Course ID. Please send a valid Course ID from the list.**")
            await input2.delete(True)
            if editable1:
                await editable1.delete(True)
            return

        await message.reply_text("Wait, extracting your batch")
        start_time = time.time()

        async with session.get(f"{api_base}/get/folder_contentsv2?course_id={raw_text2}&parent_id=-1", headers=hdr1) as res2:
            j2 = await res2.json()
        if not j2.get("data"):
            return await message.reply_text("No data found in the response. Try switching to v3 and retry.")

        course_name = next((ct.get("course_name") for item in j1["data"] for ct in item["coursedt"] if ct.get("id") == raw_text2), "Course")
        sanitized_course_name = "".join(c if c.isalnum() else "_" for c in course_name)
        filename = f"{sanitized_course_name}.txt"

        all_outputs = []
        tasks = []
        if "data" in j2:
            for item in j2["data"]:
                tasks.append(fetch_item_details(session, api_base, raw_text2, item, hdr1))
                if item["material_type"] == "FOLDER":
                    tasks.append(fetch_folder_contents(session, api_base, raw_text2, item["id"], hdr1))
        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                if res:
                    all_outputs.extend(res)

        with open(filename, 'w') as f:
            for output_line in all_outputs:
                f.write(output_line + '\n')

        end_time = time.time()
        elapsed_time = end_time - start_time
        c_text = (f"**AppName:** {app_name}\n"
                  f"**BatchName:** {sanitized_course_name}\n"
                  f"**Batch Start Date:** {start}\n"
                  f"**Validity Ends On:** {end}\n"
                  f"Elapsed time: {elapsed_time:.1f} seconds\n"
                  f"**Batch Purchase At:** {pricing}")
        await app.send_document(message.chat.id, filename, caption=c_text)
        try:
            await app.send_document(log_channel, filename, caption=c_text)
        except PeerIdInvalid:
            await message.reply_text("Error: Bot cannot send to the log channel. Please ensure the bot is added to the channel.")
            os.remove(filename)
            return
        os.remove(filename)
        await message.reply_text("Done✅")
