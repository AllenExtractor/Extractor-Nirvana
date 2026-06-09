import os
import asyncio
from flask import Flask
from threading import Thread
from cleanup import start_cleanup_scheduler

# Start the cleanup scheduler
scheduler = start_cleanup_scheduler()

# Flask app to keep Render dyno alive
app_flask = Flask(__name__)

@app_flask.route('/')
def hello_world():
    return 'Hello from Tech VJ - Bot is Running!'

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app_flask.run(host='0.0.0.0', port=port)

# Start Flask in a separate thread
Thread(target=run_flask, daemon=True).start()

# Now import and run the actual Extractor bot
import importlib
from pyrogram import idle
from Extractor import app
from Extractor.modules import ALL_MODULES

async def main():
    for module in ALL_MODULES:
        importlib.import_module("Extractor.modules." + module)
    print("» ʙᴏᴛ ᴅᴇᴘʟᴏʏ sᴜᴄᴄᴇssғᴜʟʟʏ ✨ 🎉")
    await idle()

if __name__ == "__main__":
    app.run(main())
