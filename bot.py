import os
import asyncio
import threading
from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pymongo import MongoClient
from flask import Flask, request, render_template_string, redirect
from dotenv import load_dotenv

# ------------------ Load Config -------------------
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
INDEX_CHANNEL = int(os.getenv("INDEX_CHANNEL"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DELETE_AFTER = int(os.getenv("DELETE_AFTER", 1800))
BASE_URL = os.getenv("BASE_URL", "https://yourdomain.com")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")

PAGE_SIZE = 6

# ------------------ Pyrogram Bot -------------------
client = Client("autofilter-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo["autofilter"]
files_collection = db["files"]

@client.on_message(filters.private & filters.command("start"))
async def start(c, m: Message):
    args = m.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("file_"):
        try:
            msg_id = int(args[1].split("_")[1])
            sent = await c.copy_message(chat_id=m.chat.id, from_chat_id=INDEX_CHANNEL, message_id=msg_id)
            
            warning_text = (
                "<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
                "ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
                "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>"
            ).format(DELETE_AFTER // 60)
            
            warning = await m.reply(warning_text, parse_mode=enums.ParseMode.HTML, quote=True)

            await asyncio.sleep(DELETE_AFTER)

            # Delete sent file and warning
            await sent.delete()
            await warning.delete()

            # Send deleted confirmation + button
            await m.reply_text(
                "<b>ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ.</b>\n"
                "<b>ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ</b>",
               reply_markup=InlineKeyboardMarkup([
    [InlineKeyboardButton("📥 Get Message Again", url=f"{BASE_URL}/redirect?id={msg_id}")]
])
            )

        except Exception as e:
            await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)
        return

    await m.reply_text("👋 Welcome! Send a keyword to search.\nI work in private chat and specific group only.")

@client.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def index(c, m: Message):
    file = m.document or m.video or m.audio
    if not file:
        return
    data = {
        "file_id": str(file.file_id),
        "file_name": file.file_name,
        "file_size": file.file_size,
        "message_id": m.id
    }
    files_collection.update_one({"message_id": m.id}, {"$set": data}, upsert=True)
    print(f"Indexed: {file.file_name}")

def get_file_buttons(files, query, page):
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_files = files[start:end]

    buttons = [
        [InlineKeyboardButton(
            text=f["file_name"],
            url=f"{BASE_URL}/redirect?id={f['message_id']}"
        )]
        for f in current_files
    ]

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{query}_{page - 1}"))
    if end < len(files):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{query}_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)

@client.on_message((filters.private | filters.group) & filters.text)
async def search(c: Client, m: Message):
    if m.chat.type == "group" and m.chat.id != GROUP_ID:
        return
    query = m.text.strip()
    results = list(files_collection.find({"file_name": {"$regex": query, "$options": "i"}}))
    if not results:
        await m.reply("❌ No matching files found.")
        return
    markup = get_file_buttons(results, query, 0)
    await m.reply("🔍 Found the following files:", reply_markup=markup)

@client.on_callback_query(filters.regex(r"^get_(\d+)$"))
async def resend_file(c: Client, cb: CallbackQuery):
    msg_id = int(cb.matches[0].group(1))
    try:
        sent = await c.copy_message(chat_id=cb.message.chat.id, from_chat_id=INDEX_CHANNEL, message_id=msg_id)
        await cb.answer("📥 File sent again.")
        
        warning_text = (
            "<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
            "ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
            "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>"
        ).format(DELETE_AFTER // 60)

        warning = await cb.message.reply(warning_text, parse_mode=enums.ParseMode.HTML)

        await asyncio.sleep(DELETE_AFTER)
        await sent.delete()
        await warning.delete()
    except Exception as e:
        await cb.answer("❌ Failed to resend.", show_alert=True)



# ------------------ Flask App -------------------
flask_app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Redirecting...</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      text-align: center;
      padding: 50px;
      background: #fafafa;
    }
    #countdownMessage {
      font-size: 30px;
    }
    #scrollMessage {
      display: none;
      margin-top: 20px;
      font-weight: bold;
    }
    #linkSection {
      display: none;
      margin-top: 40px;
    }
    #getLinkButton {
      padding: 10px 20px;
      font-size: 16px;
      background-color: #007bff;
      color: white;
      border: none;
      border-radius: 5px;
      cursor: pointer;
    }
    .ad-section {
      margin: 20px auto;
      padding: 10px;
      border: 1px solid #ccc;
      background: #f9f9f9;
      max-width: 100%;
      overflow: hidden;
      box-sizing: border-box;
    }
    .scroll {
      font-size: 38px;
    }

    @media (max-width: 600px) {
      #getLinkButton {
        width: 100%;
        font-size: 18px;
      }
      body {
        padding: 20px;
      }
      #countdownMessage {
        font-size: 38px;
        color: red;
        font-family:'Gill Sans', 'Gill Sans MT', Calibri, 'Trebuchet MS', sans-serif;
      }
      .scroll {
        font-size: 18px;
      }
    }
  </style>
</head>
<body>
  <h1>{{ file_name }}</h1>
  <p id="countdownMessage">Please wait for <span id="countdown">5</span> seconds...</p>
  <div class="scroll" id="scrollMessage">⬇ Scroll down to continue ⬇</div>

  {% for i in range(10) %}
  <div class="ad-section">
    <script type="text/javascript">
      atOptions = {
        'key' : '{{ 'c2a1b45a25c2143f809c9a7008c7fd05' if i % 2 == 0 else 'ca149717d545722020724203492181fe' }}',
        'format' : 'iframe',
        'height' : {{ '50' if i % 2 == 0 else '250' }},
        'width' : {{ '320' if i % 2 == 0 else '300' }},
        'params' : {}
      };
    </script>
    <script type="text/javascript" src="//www.highperformanceformat.com/{{ 'c2a1b45a25c2143f809c9a7008c7fd05' if i % 2 == 0 else 'ca149717d545722020724203492181fe' }}/invoke.js"></script>
  </div>
  {% endfor %}

  <div id="linkSection">
    <a href="https://t.me/{{ bot_username }}?start=file_{{ msg_id }}">
      <button id="getLinkButton">📥 Get File</button>
    </a>
  </div>

  <script>
    let countdown = 5;
    const countdownEl = document.getElementById("countdown");
    const msgEl = document.getElementById("countdownMessage");
    const scrollMsg = document.getElementById("scrollMessage");
    const linkSection = document.getElementById("linkSection");

    const interval = setInterval(() => {
      countdown--;
      countdownEl.textContent = countdown;
      if (countdown <= 0) {
        clearInterval(interval);
        msgEl.style.display = "none";
        scrollMsg.style.display = "block";
        linkSection.style.display = "block";
      }
    }, 1000);

    // Protection
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', function(e) {
      if (e.key === 'F12' || (e.ctrlKey || e.metaKey) && (
        ['U','S','P'].includes(e.key.toUpperCase()) ||
        (e.shiftKey && ['I','J','C','K'].includes(e.key.toUpperCase()))
      )) e.preventDefault();
    });
  </script>
</body>
</html>
'''

@flask_app.route('/redirect')
def redirect_page():
    msg_id = request.args.get("id")
    if not msg_id:
        return redirect(f"https://t.me/{BOT_USERNAME}")
    
    file_entry = files_collection.find_one({"message_id": int(msg_id)})
    file_name = file_entry.get("file_name", "Requested File") if file_entry else "Requested File"

    return render_template_string(
        HTML_TEMPLATE,
        msg_id=msg_id,
        bot_username=BOT_USERNAME,
        file_name=file_name
    )


def run_flask():
    flask_app.run(host="0.0.0.0", port=5000)

# ------------------ Run Both -------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    client.run()
