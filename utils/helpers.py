import asyncio
import re
import urllib.parse
import socket
from pyrogram import enums, Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from config import (
    client, files_collection, users_collection, LOG_CHANNEL, BASE_URL, 
    DELETE_AFTER_FILE, DELETE_AFTER, DELETE_DELAY_REQ, INDEX_CHANNEL, 
    AUTH_CHANNEL, GROUP_ID
)

# ------------------ User Utilities ------------------ #

async def save_user(user_id):
    if not users_collection.find_one({"user_id": user_id}):
        user = await client.get_users(user_id)
        users_collection.insert_one({"user_id": user_id})
        msg = (
            f"#New_Bot_User\n\n"
            f"» ɴᴀᴍᴇ - <a href='tg://user?id={user_id}'>{user.first_name}</a>\n"
            f"» ɪᴅ - <code>{user_id}</code>"
        )
        try:
            await client.send_message(LOG_CHANNEL, msg, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print(f"Failed to log new user: {e}")


async def delete_after_delay(msg: Message, delay: int):
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception as e:
        print(f"Failed to delete message: {e}")


# ------------------ File Parsing ------------------ #

def extract_episode_info(name: str) -> str:
    patterns = [
        r"S\d{1,2}E\d{1,2}",
        r"S\d{1,2}\s*E\d{1,2}",
        r"S\d{1,2}\s*EP\d{1,2}",
        r"EP?\d{1,2}",
    ]
    combined = "|".join(patterns)
    match = re.search(combined, name, re.IGNORECASE)
    return match.group(0).replace(" ", "") if match else ""


def extract_season_episode(filename):
    season_match = re.search(r'(S)(\d{1,2})', filename, re.IGNORECASE)
    episode_match = re.search(r'(EP?)(\d{1,3})', filename, re.IGNORECASE)
    if season_match and episode_match:
        season_num = season_match.group(2).zfill(2)
        episode_num = episode_match.group(2).zfill(2)
        return f'S{season_num}EP{episode_num}'
    elif episode_match:
        episode_num = episode_match.group(2).zfill(2)
        return f'EP{episode_num}'
    return None


def run_flask_app(flask_app):
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    print(f"Starting Flask on port {port}")
    flask_app.run(host='0.0.0.0', port=port)

PAGE_SIZE=6
# ------------------ Index Page ------------------ #


def build_custom_caption(file_name: str) -> str:
    # Clean file name and append your custom text
    clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', file_name).strip()
    return f"📄 {clean_name}\n\nBy @BatmanLinkz"



async def send_file_with_caption(c, chat_id, msg_id):
    original = await c.get_messages(chat_id=INDEX_CHANNEL, message_ids=msg_id)
    
    file_name = getattr(original.document, "file_name", None) or \
                getattr(original.video, "file_name", None) or \
                getattr(original.audio, "file_name", None) or \
                original.caption or "File"

    caption = build_custom_caption(file_name)

    if original.document:
        return await c.send_document(chat_id=chat_id, document=original.document.file_id, caption=caption, parse_mode=enums.ParseMode.HTML)
    elif original.video:
        return await c.send_video(chat_id=chat_id, video=original.video.file_id, caption=caption, parse_mode=enums.ParseMode.HTML)
    elif original.audio:
        return await c.send_audio(chat_id=chat_id, audio=original.audio.file_id, caption=caption, parse_mode=enums.ParseMode.HTML)
    else:
        return await c.copy_message(chat_id, INDEX_CHANNEL, msg_id)


# ------------------ File Buttons & Pagination ------------------ #


def build_index_page(files, page):
    PAGE_SIZE = 20
    total_pages = (len(files) + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current = files[start:end]

    lines = ["📄 <b>Stored Files:</b>\n"]
    for i, f in enumerate(current, start=start + 1):
        file_size = f.get("file_size") or 0
        size_mb = round(file_size / (1024 * 1024), 2)
        file_name = f.get('file_name') or ''
        clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', file_name).strip()
        link = f"{BASE_URL}/redirect?id={f['message_id']}"
        lines.append(f"{i}. <a href='{link}'>{clean_name}</a> ({size_mb} MB)")

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️ First", callback_data="indexpage_0"))
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"indexpage_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"indexpage_{page + 1}"))
        nav_buttons.append(InlineKeyboardButton("⏭️ Last", callback_data=f"indexpage_{total_pages - 1}"))

    close_button = [InlineKeyboardButton("❌ Close", callback_data="close_index")]

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(close_button)

    markup = InlineKeyboardMarkup(keyboard)
    return "\n".join(lines), markup


# ------------------ Subscription ------------------ #

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
            f"<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
            f"ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{DELETE_AFTER//60}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
            "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>",
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(DELETE_AFTER_FILE)
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


# ------------------ Pagination ------------------ #

ITEMS_PER_PAGE = 6

async def send_paginated_files(c: Client, user_id, files, page, filename_query, query: CallbackQuery = None):
    user = await c.get_users(user_id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    # Pagination calculation
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

    # Navigation buttons
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

    # Send or edit message
    if query:
        await query.edit_message_text(
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        msg = query.message
    else:
        msg = await c.send_message(
            GROUP_ID,
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

        # ✅ Send PM only on first send, not on pagination
        pm_text = (
            "✅ Your requested files have been sent to the group.\n\n"
            "<a href='https://t.me/+Dzcz5yk-ayFjODZl'>Click Here</a>"
        )
        try:
            await c.send_message(user_id, pm_text)
        except Exception:
            pass

    # Auto-delete after delay
    asyncio.create_task(delete_after_delay(msg, DELETE_DELAY_REQ))



import urllib.parse

def get_file_buttons(files, query, page):
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_files = files[start:end]
    buttons = []

    # Encode the query so spaces/specials don't break callback_data
    encoded_query = urllib.parse.quote(query)

    # 📤 Send All (this page)
    if current_files:
        buttons.append([
            InlineKeyboardButton("📤 Send All", callback_data=f"sendall_{encoded_query}_{page}")
        ])

    for f in current_files:
        size_mb = round(f.get("file_size", 0) / (1024 * 1024), 2)
        clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', f['file_name']).strip()
        match = re.search(r'(S?\d{1,2})[\s._-]*[Vv]?[Oo]?[Ll]?[\s._-]*(E[Pp]?\d{1,3})', clean_name, re.IGNORECASE)
        if match:
            season = match.group(1).upper().replace("S", "").zfill(2)
            episode = re.sub(r"[^\d]", "", match.group(2)).zfill(2)
            episode_info = f"S{season}EP{episode}"
            label = f"🎞 {size_mb}MB | {episode_info} | {clean_name}"
        else:
            label = f"🎞 {size_mb}MB | {clean_name}"
        buttons.append([InlineKeyboardButton(label, url=f"{BASE_URL}/redirect?id={f['message_id']}")])

    # Prev / Next (also encode!)
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{encoded_query}_{page - 1}"))
    if end < len(files):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{encoded_query}_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)
