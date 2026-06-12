import os
from os import getenv
# ---------------R---------------------------------
API_ID = int(os.environ.get("API_ID", "38498066"))
# ------------------------------------------------
API_HASH = os.environ.get("API_HASH", "c9696114751feacdeb1b4487f5839a1a")
# ----------------D--------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# -----------------A-------------------------------
BOT_USERNAME = os.environ.get("Cinderella_ExtractorBot")
# ------------------X------------------------------
OWNER_ID = int(os.environ.get("OWNER_ID", "8909902924"))
# ------------------X------------------------------
CREATOR_ID = int(os.environ.get("CREATOR_ID", "8909902924"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-1003597599758"))


SUDO_USERS = list(map(int, getenv("SUDO_USERS", "").split()))
# ------------------------------------------------
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004439789026"))
# ------------------------------------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://developerbro723_db_user:9axC7c7iQm0G3ESO@cluster0.dr8m75m.mongodb.net/?appName=Cluster0")
# -----------------------------------------------
PREMIUM_LOGS = int(os.environ.get("PREMIUM_LOGS", "-1004291233454"))
