import asyncio
from pyrogram import filters
from pyrogram.errors import FloodWait
from Extractor import app
from Extractor.core.mongo.usersdb import get_users
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB configuration
MONGO_URI = ""
client = AsyncIOMotorClient(MONGO_URI)
db = client['king']

# Owner ID
ownerid = 7438818824

# Helper function to check if a user is an admin
async def is_admin(user_id: int) -> bool:
    if user_id == ownerid:
        return True
    admin = await db.admins.find_one({"user_id": user_id})
    return bool(admin)

# Background task to update broadcast progress
async def update_progress(chat_id, message_id, sent_count, failed_count, total_users, stop_event):
    while not stop_event.is_set():
        try:
            await app.edit_message_text(
                chat_id,
                message_id,
                f"📢 Broadcasting in progress...\n"
                f"👥 Total Users: {total_users}\n"
                f"✅ Sent to: {sent_count} users\n"
                f"❌ Failed for: {failed_count} users"
            )
        except Exception as e:
            print(f"Failed to update progress message: {e}")
        await asyncio.sleep(50)  # Update every 50 seconds

@app.on_message(filters.command("bro") & filters.private)
async def broadcast_bro(app, message):
    # Check if the user is authorized (owner or admin)
    if not await is_admin(message.chat.id):
        return await app.send_message(message.chat.id, "🚫 You are not authorized to use this command.")

    # Parse the command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await app.send_message(message.chat.id, "❓ Usage: /bro <message>")

    message_text = parts[1]
    
    # Fetch all users from the database
    users = await get_users()
    if not users:
        return await app.send_message(message.chat.id, "⚠️ No users found in the database.")

    total_users = len(users)
    
    # Send initial progress message
    progress_message = await app.send_message(
        message.chat.id,
        f"📢 Broadcasting started...\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Sent to: 0 users\n"
        f"❌ Failed for: 0 users"
    )

    # Create an event to signal when broadcasting is complete
    stop_event = asyncio.Event()

    # Start the progress update task
    progress_task = asyncio.create_task(
        update_progress(message.chat.id, progress_message.id, 0, 0, total_users, stop_event)
    )

    # Broadcast the message to all users
    sent_count = 0
    failed_count = 0
    for user_id in users:  # Use regular for loop since users is a list
        try:
            await app.send_message(user_id, message_text)
            sent_count += 1
        except FloodWait as e:
            print(f"FloodWait for user {user_id}: waiting {e.value} seconds")
            await asyncio.sleep(e.value)
            try:
                await app.send_message(user_id, message_text)
                sent_count += 1
            except Exception as e:
                print(f"Failed to send message to user {user_id}: {e}")
                failed_count += 1
        except Exception as e:
            print(f"Failed to send message to user {user_id}: {e}")
            failed_count += 1
        await asyncio.sleep(0.1)  # Prevent flooding

    # Signal the progress update task to stop
    stop_event.set()

    # Wait for the progress task to complete
    await progress_task

    # Send final report
    await app.edit_message_text(
        message.chat.id,
        progress_message.id,
        f"📢 Broadcast completed.\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Sent to: {sent_count} users\n"
        f"❌ Failed for: {failed_count} users"
    )
