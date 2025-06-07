import os
import sys
import asyncio
import socket
import string
import re
import threading
from pyrogram import Client, filters, enums
from pyrogram.types import ChatMemberUpdated, ChatPrivileges
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
ADMIN_ID = int(os.getenv("ADMIN_ID"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))
UPDATES_CHANNEL = os.getenv("UPDATES_CHANNEL")
MOVIES_GROUP = os.getenv("MOVIES_GROUP")
AUTH_CHANNEL = int(os.getenv("AUTH_CHANNEL"))
DELETE_DELAY = int(os.getenv("DELETE_DELAY", 3600)) 

# Setup
client = Client("autofilter-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo["autofilter"]
files_collection = db["files"]
users_collection = db["users"]
pending_requests = db["pending_requests"] 
PAGE_SIZE = 6


def extract_episode_info(name: str) -> str:
    """
    Extract episode info like S01E01, S01 E01, Ep01, E01 etc. from file name.
    """
    patterns = [
        r"S\d{1,2}E\d{1,2}",       # S01E01
        r"S\d{1,2}\s*E\d{1,2}",    # S01 E01 or S01     E01
        r"S\d{1,2}\s*EP\d{1,2}",   # S01EP01 or S01 EP01
        r"EP?\d{1,2}",             # Ep01 or E01
    ]
    combined = "|".join(patterns)
    match = re.search(combined, name, re.IGNORECASE)
    return match.group(0).replace(" ", "") if match else ""



def extract_season_episode(filename):
    # Look for season (S or s followed by 1-2 digits)
    season_match = re.search(r'(S)(\d{1,2})', filename, re.IGNORECASE)
    # Look for episode (E or EP followed by 1-3 digits)
    episode_match = re.search(r'(EP?)(\d{1,3})', filename, re.IGNORECASE)
    
    if season_match and episode_match:
        season_num = season_match.group(2).zfill(2)  # pad to 2 digits
        episode_num = episode_match.group(2).zfill(2)
        return f'S{season_num}EP{episode_num}'
    elif episode_match:
        episode_num = episode_match.group(2).zfill(2)
        return f'EP{episode_num}'
    else:
        return None


def run_flask_app():
    # Create a socket to find a free port
    sock = socket.socket()
    sock.bind(('', 0))  # Bind to a free port assigned by the OS
    port = sock.getsockname()[1]
    sock.close()

    print(f"Starting Flask on port {port}")
    flask_app.run(host='0.0.0.0', port=port)


async def delete_after_delay(msg: Message, delay: int):
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception as e:
        print(f"Failed to delete message: {e}")


def build_index_page(files, page):
    PAGE_SIZE = 10
    total_pages = (len(files) + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current = files[start:end]

    lines = ["📄 <b>Stored Files:</b>\n"]
    for i, f in enumerate(current, start=start + 1):
        size_mb = round(f.get("file_size", 0) / (1024 * 1024), 2)
        clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', f['file_name']).strip()
        link = f"{BASE_URL}/redirect?id={f['message_id']}"
        lines.append(f"{i}. <a href='{link}'>{clean_name}</a> ({size_mb} MB)")

    text = "\n".join(lines)

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️ First", callback_data="indexpage_0"))
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"indexpage_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"indexpage_{page + 1}"))
        nav_buttons.append(InlineKeyboardButton("⏭️ Last", callback_data=f"indexpage_{total_pages - 1}"))

    # Close button
    close_button = [InlineKeyboardButton("❌ Close", callback_data="close_index")]

    # Final keyboard layout
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(close_button)

    markup = InlineKeyboardMarkup(keyboard)
    return text, markup


async def save_user(user_id):
    if not users_collection.find_one({"user_id": user_id}):
        user = await client.get_users(user_id)
        users_collection.insert_one({"user_id": user_id})
        name = user.first_name or "Unknown"
        msg = f"#New_Bot_User\n\n» ɴᴀᴍᴇ - {name}\n» ɪᴅ - <code>{user_id}</code>"
        try:
            await client.send_message(LOG_CHANNEL, msg, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print(f"Failed to log new user: {e}")

async def is_subscribed(user_id):
    try:
        member = await client.get_chat_member(AUTH_CHANNEL, user_id)
        return member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    except:
        return False

async def check_sub_and_send_file(c: Client, m: Message, msg_id: int):
    if not await is_subscribed(m.from_user.id):
        try:
            invite_link = await c.export_chat_invite_link(AUTH_CHANNEL)
        except Exception:
            invite_link = "https://t.me/+CyoimDCsFuIzNDQ1"

        return await m.reply_text(
            "<b>🚫 You must join our Updates Channel to access this file.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Join Channel", url=invite_link)],
                [InlineKeyboardButton("✅ I Joined", callback_data=f"retry_{msg_id}")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    try:
        sent = await c.copy_message(chat_id=m.chat.id, from_chat_id=INDEX_CHANNEL, message_id=msg_id)

        warning = await m.reply(
             "<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
                "ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
                "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>".format(DELETE_AFTER // 60),
            parse_mode=enums.ParseMode.HTML
        )

        await asyncio.sleep(DELETE_AFTER)
        await sent.delete()

        await warning.edit_text(
            "<b>ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ.</b>\n"
                "<b>ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Get Message Again", url=f"{BASE_URL}/redirect?id={msg_id}")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    except Exception as e:
        await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)

ITEMS_PER_PAGE = 6


async def send_paginated_files(c, user_id, files, page, filename_query, query: CallbackQuery = None):
    # Fetch user info for mention
    user = await c.get_users(user_id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    total_pages = (len(files) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_files = files[start:end]

    mention = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
    text = f"<b>👋 Hey {mention}, Your Requested Files Have Been Added By Admin</b> (Page {page + 1}/{total_pages}):\n\n"

    for i, file_doc in enumerate(current_files, start=1):
        file_name = file_doc["file_name"]
        file_size = round(file_doc.get("file_size", 0) / (1024 * 1024), 2)
        msg_id = file_doc["message_id"]
        text += f"➤ <b>{file_name}</b> — {file_size} MB\n"
        text += f"    <a href='{BASE_URL}/redirect?id={msg_id}'>📥 Download</a>\n\n"

    buttons = []
    nav_buttons = []

    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:{user_id}|{filename_query}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("➡️ Next", callback_data=f"nav:{user_id}|{filename_query}:{page + 1}")
        )

    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Send or edit message, get the message object for deletion later
    if query:
        await query.edit_message_text(
            text, reply_markup=markup, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True
        )
        msg = query.message
    else:
        msg = await c.send_message(
            GROUP_ID, text, reply_markup=markup, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True
        )

    # Notify user privately
    pm_text = (
    "✅ Your requested files have been sent to the group.\n\n"
    "<a href='https://t.me/+Dzcz5yk-ayFjODZl'>Click Here</a>"
)

    try:
        await c.send_message(user_id, pm_text)
    except Exception:
        # User might have blocked bot or privacy settings prevent PM
        pass

    # Async task to delete message after delay
    async def delete_message_after_delay(msg, delay=DELETE_DELAY):
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except Exception:
            pass

    asyncio.create_task(delete_message_after_delay(msg))



# ------------------ Handlers -------------------
@client.on_callback_query(filters.regex("close_index"))
async def close_index_handler(_, cb: CallbackQuery):
    try:
        await cb.message.delete()  # Delete the index message
        await cb.answer()  # Acknowledge silently (no popup)
    except Exception:
        await cb.answer("❌ Couldn't close.", show_alert=True)


@client.on_callback_query(filters.regex(r"^nav:(\d+)\|(.+):(\d+)$"))
async def handle_pagination_nav(c: Client, query: CallbackQuery):
    try:
        match = re.match(r"^nav:(\d+)\|(.+):(\d+)$", query.data)
        if not match:
            return await query.answer("Invalid navigation.")

        user_id = int(match.group(1))
        filename_query = match.group(2)
        page = int(match.group(3))

        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        await send_paginated_files(c, user_id, matching_files, page, filename_query, query)

    except Exception as e:
        await query.answer(f"❌ Error: {e}", show_alert=True)




@client.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_file_paginated(c: Client, m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 3:
            return await m.reply(
                "❗ Usage: `/send <user_id> <filename>`",
                parse_mode=enums.ParseMode.MARKDOWN
            )

        user_id = int(parts[1])
        filename_query = parts[2].strip()

        # Optional: Get user info for confirmation message
        try:
            user = await c.get_users(user_id)
        except Exception:
            user = None

        # Build regex pattern from keywords (fuzzy matching)
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)

        # Query MongoDB (ensure files_collection is defined elsewhere)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not matching_files:
            return await m.reply("❌ No files found matching your query.")

        # Send paginated files
        await send_paginated_files(c, user_id, matching_files, 0, filename_query)

        # Confirmation message
        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            await m.reply(
                f"✅ Sent to <a href='tg://user?id={user_id}'>{name}</a>",
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await m.reply(f"✅ Files sent to user ID: <code>{user_id}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await m.reply(
            f"❌ Error:\n<code>{e}</code>",
            parse_mode=enums.ParseMode.HTML
        )



@client.on_message(filters.group & filters.command("start"))
async def start_group(_, m: Message):
    # Send reply message
    msg = await m.reply_text("👋 Hey, I'm alive and working in this group!")

    # Wait 60 seconds
    await asyncio.sleep(5)

    # Delete the bot's reply message
    await msg.delete()


    
@client.on_message(filters.command("files"))
async def index_list(c: Client, m: Message):
    # Extract search query after the command (if any)
    command_parts = m.text.split(maxsplit=1)
    query = command_parts[1].strip() if len(command_parts) > 1 else ""

    if query:
        # Case-insensitive search using regex
        keywords = re.split(r"\s+", query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)

        files = list(files_collection.find({"file_name": {"$regex": regex}}).sort("file_name", 1))
    else:
        # No query, return all files
        files = list(files_collection.find().sort("file_name", 1))

    if not files:
        return await m.reply("📂 No matching files found.")

    page = 0
    text, buttons = build_index_page(files, page)
    await m.reply(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons, disable_web_page_preview=True)


@client.on_callback_query(filters.regex(r"^indexpage_(\d+)$"))
async def paginate_index(c: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    files = list(files_collection.find().sort("file_name", 1))

    if not files:
        return await cb.answer("❌ No indexed files.", show_alert=True)

    # Clean file names before passing to build_index_page
    for f in files:
        f['clean_name'] = re.sub(r'^@[^_\s-]+[_\s-]*', '', f['file_name']).strip()

    text, buttons = build_index_page(files, page)

    try:
        await cb.message.edit_text(
            text,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons,
            disable_web_page_preview=True
        )
        await cb.answer()
    except Exception as e:
        await cb.answer("⚠️ Couldn't update.", show_alert=True)


@client.on_chat_member_updated()
async def welcome_and_goodbye(client: Client, event: ChatMemberUpdated):
    # Ignore if the chat is a channel
    if event.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return

    chat_title = event.chat.title or "this group"

    # Welcome new users
    if event.new_chat_member and event.new_chat_member.status == enums.ChatMemberStatus.MEMBER:
        user = event.new_chat_member.user
        msg = await client.send_message(
            event.chat.id,
            f"<b>👋 Hᴇʏ <a href='tg://user?id={user.id}'>{user.first_name}</a>, Wᴇʟᴄᴏᴍᴇ ᴛᴏ {chat_title} 🎉.</b>\n\n"
            "<b>Jᴜsᴛ Sᴇɴᴅ ᴀ Mᴏᴠɪᴇ ᴏʀ Sᴇʀɪᴇs Nᴀᴍᴇ ᴡɪᴛʜ Cᴏʀʀᴇᴄᴛ Sᴘᴇʟʟɪɴɢ, I Wɪʟʟ Gɪᴠᴇ Yᴏᴜ ᴀ Fɪʟᴇs Lɪɴᴋ Sᴛᴏʀᴇᴅ ɪɴ Mʏ Dᴀᴛᴀʙᴀsᴇ.</b>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📢 Updates Channel", url=UPDATES_CHANNEL)]]
            ),
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(60)
        await msg.delete()

    # Goodbye message
    elif event.old_chat_member and event.old_chat_member.status in [
        enums.ChatMemberStatus.MEMBER,
        enums.ChatMemberStatus.RESTRICTED
    ] and event.new_chat_member and event.new_chat_member.status in [
        enums.ChatMemberStatus.LEFT,
        enums.ChatMemberStatus.KICKED
    ]:
        user = event.old_chat_member.user
        msg = await client.send_message(
            event.chat.id,
            f"<i>👋 <a href='tg://user?id={user.id}'>{user.first_name}</a> has left the group. Goodbye! 👋</i>",
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(60)
        await msg.delete()



@client.on_message(filters.private & filters.command("start"))
async def start(c, m: Message):
    await save_user(m.from_user.id)

    args = m.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("file_"):
        try:
            msg_id = int(args[1].split("_")[1])
            await check_sub_and_send_file(c, m, msg_id)
        except Exception as e:
            await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)
        return

    name = m.from_user.first_name or "User"
    await m.reply_text(
        f"😎 ʜᴇʏ {name},\n\n"
        "ɪ ᴀᴍ ᴀ ғɪʟᴛᴇʀ ʙᴏᴛ ᴀɴᴅ ᴜsᴇʀs ᴄᴀɴ ᴀᴄᴄᴇss sᴛᴏʀᴇᴅ ᴍᴇssᴀɢᴇs ʙʏ sᴇᴀʀᴄʜ ᴏʀ ᴜsɪɴɢ ᴀ sʜᴀʀᴇᴀʙʟᴇ ʟɪɴᴋ ɢɪᴠᴇɴ ʙʏ ᴍᴇ\n\n"
        "ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz\n\n"
        "ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Me To Group", 
             url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
            [InlineKeyboardButton("📢 Updates Channel", url=UPDATES_CHANNEL),
             InlineKeyboardButton("Help❓", callback_data="help_info")],
            [InlineKeyboardButton("🎬 Movie Group", url=MOVIES_GROUP)]
        ]),
        parse_mode=enums.ParseMode.HTML
    )

@client.on_callback_query(filters.regex("retry_"))
async def retry_after_join(c: Client, cb: CallbackQuery):
    msg_id = int(cb.data.split("_")[1])
    if await is_subscribed(cb.from_user.id):
        await cb.message.delete()
        await check_sub_and_send_file(c, cb.message, msg_id)
    else:
        await cb.answer("❌ You're still not subscribed!", show_alert=True)

@client.on_callback_query(filters.regex("help_info"))
async def help_callback(_, cb: CallbackQuery):
    await cb.message.edit_text(
        "<b>How to use me?</b>\n\n"
        "🔹 Just type any movie or file name.\n"
        "🔹 I’ll show you the available links.\n"
        "🔹 Click the one you want, and I’ll send it to you!\n\n"
        "🎥 For latest movies, join @Batmanlinkz",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="start_back")]
        ]),
        parse_mode=enums.ParseMode.HTML
    )

@client.on_callback_query(filters.regex("start_back"))
async def back_to_start(_, cb: CallbackQuery):
    await start(_, cb.message)
    await cb.answer()



@client.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("❗ Reply to a message to broadcast.")
    
    sent, failed = 0, 0
    users = users_collection.find()
    for user in users:
        try:
            await m.reply_to_message.copy(user["user_id"])
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)
    await m.reply(f"✅ Broadcast done.\n✔️ Sent: {sent}\n❌ Failed: {failed}")


@client.on_message(filters.private & filters.command("help"))
async def help_cmd(c, m: Message):
    await m.reply_text(
         "<b>How to use me?</b>\n\n"
        "🔹 Just type any movie or file name.\n"
        "🔹 I’ll show you the available links.\n"
        "🔹 Click the one you want, and I’ll send it to you!\n\n"
        "🎥 For latest movies, join @Batmanlinkz",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Here", url="https://t.me/batmanlinkz")]
        ])
    )
@client.on_message(filters.command("status") & filters.user(ADMIN_ID))
async def status(_, m: Message):
    total = users_collection.count_documents({})
    deleted = 0
    blocked = 0

    msg = await m.reply("⏳ Checking user status...")

    users = users_collection.find()
    for user in users:
        try:
            await client.get_users(user["user_id"])
        except Exception as e:
            if "deleted account" in str(e).lower():
                deleted += 1
            elif "USER_IS_BLOCKED" in str(e):
                blocked += 1
            else:
                continue
        await asyncio.sleep(0.05)  # avoid floodwait

    active = total - deleted - blocked

    await msg.edit_text(
        f"📊 <b>Bot Status:</b>\n\n"
        f"👥 Total Users: <code>{total}</code>\n"
        f"✅ Active Users: <code>{active}</code>\n"
        f"🚫 Blocked Users: <code>{blocked}</code>\n"
        f"🗑 Deleted Accounts: <code>{deleted}</code>",
        parse_mode=enums.ParseMode.HTML
    )



@client.on_message(filters.command("link") & filters.user(ADMIN_ID))
async def link_handler(c: Client, m: Message):
    if not m.reply_to_message:
        await m.reply("❌ Please reply to any message (text/media) with `/link`.", quote=True)
        return

    reply = m.reply_to_message

    # Copy the message instead of forwarding (removes "forwarded from" tag)
    try:
        fwd_msg = await reply.copy(chat_id=INDEX_CHANNEL)
    except Exception as e:
        await m.reply(f"❌ Failed to copy message: {e}")
        return

    # Basic fallback for file name
    file_name = reply.text or getattr(reply, 'caption', None) or "Unnamed"

    # Save to DB
    files_collection.insert_one({
        "file_name": file_name,
        "message_id": fwd_msg.id,
        "type": "generic"
    })

    redirect_link = f"{BASE_URL}/redirect?id={fwd_msg.id}"

    await m.reply(
        f"✅ File indexed!\n\n<code>{redirect_link}</code>",
        parse_mode=enums.ParseMode.HTML
    )




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

    buttons = []
    for f in current_files:
        size_mb = round(f.get("file_size", 0) / (1024 * 1024), 2)
        clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', f['file_name']).strip()
                # Try to extract episode or season info
        match = re.search(r'(S?\d{1,2})[\s._-]*[Vv]?[Oo]?[Ll]?[\s._-]*(E[Pp]?\d{1,3})', clean_name, re.IGNORECASE)
        if match:
            season = match.group(1).zfill(3 if 'E' not in match.group(1).upper() else 2).upper().replace("S", "")
            episode = re.sub(r"[^\d]", "", match.group(2)).zfill(2)
            episode_info = f"S{season}EP{episode}"
            label = f"🎞 {size_mb}MB | {episode_info} | {clean_name}"
        else:
            label = f"🎞 {size_mb}MB | {clean_name}"

        buttons.append([InlineKeyboardButton(label, url=f"{BASE_URL}/redirect?id={f['message_id']}")])

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{query}_{page - 1}"))
    if end < len(files):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{query}_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)

@client.on_message(filters.group & filters.text)
async def search(c: Client, m: Message):
    query = m.text.strip()

    # Preprocess query
    keywords = re.split(r"\s+", query)
    regex_pattern = ".*".join(map(re.escape, keywords))
    regex = re.compile(regex_pattern, re.IGNORECASE)

    results = list(files_collection.find({"file_name": {"$regex": regex}}))

    try:
        await m.delete()
    except Exception as e:
        print(f"Failed to delete user message: {e}")

    if not results:
        # Log missing query
        log_text = (
            f"🔍 <b>Missing File Request</b>\n\n"
            f"👤 User: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
            f"🆔 User ID: <code>{m.from_user.id}</code>\n"
            f"🗣 Group: <code>{m.chat.title}</code> ({m.chat.id})\n"
            f"💬 Chat ID: <code>{m.chat.id}</code>\n"
            f"🔎 Query: <code>{query}</code>"
        )
        try:
            await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print(f"Failed to log missing file: {e}")

        # Save the query and user
        db["pending_requests"].insert_one({
            "query": query.lower(),
            "user_id": m.from_user.id,
            "chat_id": m.chat.id,
            "status": "pending"
        })

        msg = await m.reply(
            "❌ <b>No matching files found.</b>\n\n"
            "📥 <b>Your request has been stored.</b>\n\n"
            "🛎 <b>We will notify you if the file is added in the future.</b>",
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, 15))
        return

    markup = get_file_buttons(results, query, 0)
    msg = await m.reply("🔍 Found the following files:", reply_markup=markup)
    asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))



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
    except Exception:
        await cb.answer("❌ Failed to resend.", show_alert=True)

@client.on_callback_query(filters.regex(r"^page_(.+)_(\d+)$"))
async def paginate_files(c: Client, cb: CallbackQuery):
    raw_query, page = cb.matches[0].group(1), int(cb.matches[0].group(2))
    query = raw_query.replace("_", " ")  # Fix space formatting

    # Convert query back to proper regex
    keywords = re.split(r"\s+", query)
    regex_pattern = ".*".join(map(re.escape, keywords))
    regex = re.compile(regex_pattern, re.IGNORECASE)

    results = list(files_collection.find({"file_name": {"$regex": regex}}))
    if not results:
        return await cb.answer("❌ No results.", show_alert=True)

    markup = get_file_buttons(results, query, page)
    try:
        await cb.message.edit_reply_markup(markup)
        await cb.answer()
    except Exception as e:
        print(f"❌ Pagination error: {e}")
        await cb.answer("⚠️ Couldn't load page.", show_alert=True)

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
    h1 {
  text-align: center;
  margin-top: 30px;
  font-size: 28px;
  word-break: break-word;
  max-width: 90%;
  margin-left: auto;
  margin-right: auto;
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
