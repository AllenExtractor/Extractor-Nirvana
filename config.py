import os
from os import getenv
# ---------------R---------------------------------
API_ID = int(os.environ.get("API_ID", "20369373"))
# ------------------------------------------------
API_HASH = os.environ.get("API_HASH", "0d53cc7f978163fed3263be5cbb20ab0")
# ----------------D--------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# -----------------A-------------------------------
BOT_USERNAME = os.environ.get("Masterextratorraonebot")
# ------------------X------------------------------
OWNER_ID = int(os.environ.get("OWNER_ID", "5680454765"))
# ------------------X------------------------------
CREATOR_ID = int(os.environ.get("CREATOR_ID", "5680454765"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-1002585176866"))


SUDO_USERS = list(map(int, getenv("SUDO_USERS", "5680454765").split()))
# ------------------------------------------------
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002585176866"))
# ------------------------------------------------
MONGO_URL = os.environ.get("MONGO_URL", "")
# -----------------------------------------------
PREMIUM_LOGS = int(os.environ.get("PREMIUM_LOGS", "-1002585176866"))
