import io
import aiofiles
import os
import time
import sys
import motor
from Extractor import app
from pyrogram import filters
from Extractor.core.mongo.usersdb import get_users, add_user, get_user
from Extractor.core.mongo.plans_db import premium_users

# Define ownerid at the module level
ownerid = 7438818824  # Replace with your actual Telegram chat ID (integer)

# MongoDB database instance (same as implied in stats module)
from motor.motor_asyncio import AsyncIOMotorClient
MONGO_URI = ""  # Replace with your MongoDB URI
client = AsyncIOMotorClient(MONGO_URI)
db = client['king']  # Replace with your database name

start_time = time.time()

@app.on_message(group=10)
async def chat_watcher_func(app, message):
    try:
        if message.from_user:
            us_in_db = await get_user(message.from_user.id)
            if not us_in_db:
                await add_user(message.from_user.id)
    except:
        pass

def time_formatter():
    minutes, seconds = divmod(int(time.time() - start_time), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)
    tmp = (
        ((str(weeks) + "w:") if weeks else "")
        + ((str(days) + "d:") if days else "")
        + ((str(hours) + "h:") if hours else "")
        + ((str(minutes) + "m:") if minutes else "")
        + ((str(seconds) + "s") if seconds else "")
    )
    if tmp != "":
        if tmp.endswith(":"):
            return tmp[:-1]
        else:
            return tmp
    else:
        return "0 s"

@app.on_message(filters.command("stats") & filters.user(ownerid))
async def stats(app, message):
    start = time.time()
    users = len(await get_users())
    premium = await premium_users()
    ping = round((time.time() - start) * 1000)
    await message.reply_text(f"""
**Stats of** {(await app.get_me()).mention} :

🏓 **Ping Pong**: {ping}ms

📊 **Total Users** : `{users}`
📈 **Premium Users** : `{len(premium)}`
⚙️ **Bot Uptime** : `{time_formatter()}`
    
🎨 **Python Version**: `{sys.version.split()[0]}`
📑 **Mongo Version**: `{motor.version}`
""")

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast(app, message):
    if message.chat.id != ownerid:
        return await app.send_message(message.chat.id, "You are not authorized to use this command.")
    
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        return await app.send_message(message.chat.id, "Usage: /broadcast <message> or /broadcast -v for video/photo broadcast")
    
    if parts[1] == "-v":
        await app.send_message(message.chat.id, "Please send the video or photo with a caption to broadcast.")
        media_message = await app.ask(message.chat.id)
        media_file_id = None
        caption = media_message.caption or ""
        
        if media_message.video:
            media_file_id = media_message.video.file_id
            media_type = "video"
        elif media_message.photo:
            media_file_id = media_message.photo[-1].file_id  # Highest quality photo
            media_type = "photo"
        
        if not media_file_id:
            return await app.send_message(message.chat.id, "No video or photo found. Please try again.")
        
        users = await get_users()  # Fetch users from MongoDB
        async for user_id in users:
            try:
                if media_type == "video":
                    await app.send_video(user_id, media_file_id, caption=caption)
                elif media_type == "photo":
                    await app.send_photo(user_id, media_file_id, caption=caption)
            except Exception as e:
                print(f"Failed to send {media_type} to user {user_id}: {e}")
        return await app.send_message(message.chat.id, f"{media_type.capitalize()} broadcast completed.")
    
    message_text = parts[1]
    users = await get_users()  # Fetch users from MongoDB
    async for user_id in users:
        try:
            await app.send_message(user_id, message_text)
        except Exception as e:
            print(f"Failed to send message to user {user_id}: {e}")
    
    await app.send_message(message.chat.id, "Broadcast completed.")

@app.on_message(filters.command("allbackupfiles") & filters.private)
async def allbackupfiles(app, message):
    if message.chat.id != ownerid:
        return await app.send_message(message.chat.id, "You are not authorized to use this command.")
    
    all_files = await db.backup_files.find().to_list(None)  # Fetch all backup files from MongoDB
    if not all_files:
        return await app.send_message(message.chat.id, "No backup files found.")
    
    for file in all_files:
        file_data = io.BytesIO(file['file_data'])
        file_name = file['file_name']
        async with aiofiles.open(file_name, 'wb') as f:
            await f.write(file_data.read())
        try:
            await app.send_document(message.chat.id, document=file_name, caption=file['caption'])
        except Exception as e:
            print(f"Failed to send document {file_name} to user {message.chat.id}: {e}")
        finally:
            os.remove(file_name)

