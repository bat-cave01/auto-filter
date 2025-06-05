import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
INDEX_CHANNEL = int(os.getenv("INDEX_CHANNEL"))  # Must be negative ID

client = Client("AutoFilterBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo["autofilter"]
files_collection = db["files"]

# ------------- INDEXER ------------------
@client.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def index_files(c: Client, m: Message):
    file = m.document or m.video or m.audio
    if not file:
        return

    data = {
        "file_id": str(file.file_id),
        "file_name": file.file_name,
        "file_size": file.file_size,
        "message_id": m.id
    }

    files_collection.update_one(
        {"message_id": m.id},
        {"$set": data},
        upsert=True
    )


# --------- SEARCH HANDLER (GROUPS) ----------
@client.on_message(filters.group & filters.text & ~filters.edited)
async def filter_files(c: Client, m: Message):
    query = m.text.strip()
    results = list(files_collection.find({"file_name": {"$regex": query, "$options": "i"}}).limit(10))

    if not results:
        return

    buttons = [
        [InlineKeyboardButton(text=f"{r['file_name']}", callback_data=f"get_{r['message_id']}")]
        for r in results
    ]

    await m.reply("🔍 Found these files:", reply_markup=InlineKeyboardMarkup(buttons))


# --------- CALLBACK: SEND FILE ------------
@client.on_callback_query(filters.regex(r"get_(\d+)"))
async def send_file(c: Client, cb: CallbackQuery):
    msg_id = int(cb.data.split("_")[1])

    try:
        await cb.answer("📤 Sending file...")
        sent_msg = await cb.message.reply_copy(
            chat_id=cb.message.chat.id,
            from_chat_id=INDEX_CHANNEL,
            message_id=msg_id,
            caption="📁 Here is your file. Auto-deletes in 30 minutes."
        )

        await asyncio.sleep(1800)  # 30 minutes
        await sent_msg.delete()
    except Exception as e:
        await cb.message.reply(f"❌ Failed to send file:\n`{e}`")


client.run()
