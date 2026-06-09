import os
from flask import Flask
from threading import Thread
from pyrogram import Client
import asyncio
from cleanup import start_cleanup_scheduler

# Start the cleanup scheduler
scheduler = start_cleanup_scheduler()

# Your existing app code continues here...

# Flask app to keep Heroku dyno alive
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello from Tech VJ'

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Start Flask in a separate thread
Thread(target=run_flask).start()

# Fetch credentials from environment variables
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

# Pyrogram bot setup with reconnection logic
bot = Client(
    "my_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    sleep_threshold=60,  # Wait 60 seconds before reconnecting
    max_retries=5  # Retry 5 times before giving up
)

@bot.on_message()
async def my_handler(client, message):
    await message.reply("Hello from Tech VJ Bot!")

async def main():
    try:
        await bot.start()
        print("Bot is running...")
        await bot.idle()  # Keep the bot running
    except Exception as e:
        print(f"Error: {e}")
        await bot.stop()
        await asyncio.sleep(5)  # Wait 5 seconds before restarting
        await bot.start()

if __name__ == "__main__":
    bot.run(main())
