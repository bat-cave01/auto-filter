import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from config import client, files_collection, GROUP_ID, BASE_URL, BOT_USERNAME, UPDATES_CHANNEL, MOVIES_GROUP,ADMIN_ID, LOG_CHANNEL,DELETE_DELAY,DELETE_AFTER
from utils.helpers import save_user, delete_after_delay,users_collection,files_collection, check_sub_and_send_file,build_index_page,get_file_buttons,send_paginated_files

PAGE_SIZE = 6  # Default delay for messages in seconds

# ------------------ Group /start ------------------ #
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

    for user in users_collection.find():
        try:
            await client.get_users(user["user_id"])
        except Exception as e:
            if "deleted account" in str(e).lower():
                deleted += 1
            elif "USER_IS_BLOCKED" in str(e):
                blocked += 1
        await asyncio.sleep(0.05)

    active = total - deleted - blocked

    await msg.edit_text(
        f"📊 <b>Bot Status:</b>\n\n"
        f"👥 Total Users: <code>{total}</code>\n"
        f"✅ Active Users: <code>{active}</code>\n"
        f"🚫 Blocked Users: <code>{blocked}</code>\n"
        f"🗑 Deleted Accounts: <code>{deleted}</code>",
        parse_mode=enums.ParseMode.HTML
    )

# ------------------ /send ------------------ #
@client.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_file_paginated_handler(c: Client, m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 3:
            return await m.reply(
                "❗ Usage: `/send <user_id> <filename>`",
                parse_mode=enums.ParseMode.MARKDOWN
            )

        user_id = int(parts[1])
        filename_query = parts[2].strip()

        try:
            user = await c.get_users(user_id)
        except Exception:
            user = None

        # Fuzzy search using regex
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not matching_files:
            return await m.reply("❌ No files found matching your query.")

        # Send paginated files (first page)
        await send_paginated_files(c, user_id, matching_files, 0, filename_query)

        # Confirmation
        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            await m.reply(f"✅ Sent to <a href='tg://user?id={user_id}'>{name}</a>", parse_mode=enums.ParseMode.HTML)
        else:
            await m.reply(f"✅ Files sent to user ID: <code>{user_id}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)

# ------------------ /link ------------------ #
@client.on_message(filters.command("link") & filters.user(ADMIN_ID))
async def link_handler(c: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to a message with `/link`.", quote=True)

    reply = m.reply_to_message
    try:
        fwd_msg = await reply.copy(chat_id=INDEX_CHANNEL)
    except Exception as e:
        return await m.reply(f"❌ Failed to copy message: {e}")

    file_name = reply.text or getattr(reply, "caption", None) or "Unnamed"
    files_collection.insert_one({
        "file_name": file_name,
        "message_id": fwd_msg.id,
        "type": "generic"
    })

    redirect_link = f"{BASE_URL}/redirect?id={fwd_msg.id}"
    await m.reply(f"✅ File indexed!\n\n<code>{redirect_link}</code>", parse_mode=enums.ParseMode.HTML)

# ------------------ Broadcast ------------------ #
@client.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("❗ Reply to a message to broadcast.")

    sent, failed = 0, 0
    for user in users_collection.find():
        try:
            await m.reply_to_message.copy(user["user_id"])
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)

    await m.reply(f"✅ Broadcast done.\n✔️ Sent: {sent}\n❌ Failed: {failed}")

# ------------------ Pagination Callback ------------------ #
@client.on_callback_query(filters.regex(r"^nav:(\d+)\|(.+):(\d+)$"))
async def handle_pagination_nav(c: Client, query: CallbackQuery):
    try:
        match = re.match(r"^nav:(\d+)\|(.+):(\d+)$", query.data)
        if not match:
            return await query.answer("Invalid navigation.")

        user_id = int(match.group(1))
        filename_query = match.group(2)
        page = int(match.group(3))

        # Fuzzy search again
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        await send_paginated_files(c, user_id, matching_files, page, filename_query, query)

    except Exception as e:
        await query.answer(f"❌ Error: {e}", show_alert=True)


# ------------------ /files command ------------------ #
@client.on_message(filters.command("files"))
async def index_list(c: Client, m: Message):
    command_parts = m.text.split(maxsplit=1)
    query = command_parts[1].strip() if len(command_parts) > 1 else ""

    if query:
        keywords = re.split(r"\s+", query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        files = list(files_collection.find({"file_name": {"$regex": regex}}).sort("file_name", 1))
    else:
        files = list(files_collection.find().sort("file_name", 1))

    if not files:
        return await m.reply("📂 No matching files found.")

    text, buttons = build_index_page(files, 0)
    await m.reply(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons, disable_web_page_preview=True)



# ------------------ Private /start ------------------ #
@client.on_message(filters.command("start") & (filters.private | filters.group))
async def start(c: Client, m: Message):
    if m.chat.type == enums.ChatType.PRIVATE:
        await save_user(m.from_user.id)

    args = m.text.split(maxsplit=1)

    # Deep link with file
    if len(args) > 1 and args[1].startswith("file_") and m.chat.type == enums.ChatType.PRIVATE:
        try:
            msg_id = int(args[1].split("_")[1])
            await check_sub_and_send_file(c, m, msg_id)
        except Exception as e:
            msg = await m.reply(
                f"❌ Error:\n<code>{e}</code>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # Deep link with search
    if len(args) > 1 and args[1].startswith("search_") and m.chat.type == enums.ChatType.PRIVATE:
        query = args[1].replace("search_", "").replace("_", " ").strip()

        keywords = re.split(r"\s+", query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)

        results = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not results:
            msg = await m.reply(
                f"❗️No results found for <b>{query}</b>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
            return

        markup = get_file_buttons(results, query, 0)
        msg = await m.reply(
            f"🔍 Search results for <b>{query}</b>:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # Default welcome (same for private & group)
    name = m.from_user.first_name if m.from_user else "User"
    msg = await m.reply_text(
        f"😎 ʜᴇʏ {name},\n\n"
        "ɪ ᴀᴍ ᴀ ғɪʟᴛᴇʀ ʙᴏᴛ...\n\n"
        "ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz\n\n"
        "ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Me To Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
            [InlineKeyboardButton("📢 Updates Channel", url=UPDATES_CHANNEL),
             InlineKeyboardButton("Help❓", callback_data="help_info")],
            [InlineKeyboardButton("🎬 Movie Group", url=MOVIES_GROUP)]
        ]),
        parse_mode=enums.ParseMode.HTML
    )

    # Auto-delete welcome in groups only
    if m.chat.type != enums.ChatType.PRIVATE:
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))




# ------------------ Group Text Search ------------------ #
@client.on_message((filters.group | filters.private) & filters.text)
async def search(c: Client, m: Message):
    if m.text.startswith("/"):
        return  # Ignore commands

    query = m.text.strip()
    keywords = re.split(r"\s+", query)
    regex_pattern = ".*".join(map(re.escape, keywords))
    regex = re.compile(regex_pattern, re.IGNORECASE)
    results = list(files_collection.find({"file_name": {"$regex": regex}}))

    try:
        await m.delete()
    except Exception:
        pass

    if not results:
        if m.chat.type == enums.ChatType.PRIVATE:
            msg = await m.reply("❗️No Results found.", parse_mode=enums.ParseMode.HTML)
        else:
            chat_info = f"🗣 Group: <code>{m.chat.title}</code> ({m.chat.id})"
            log_text = (
                f"🔍 <b>Missing File Request</b>\n\n"
                f"👤 User: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
                f"🆔 User ID: <code>{m.from_user.id}</code>\n"
                f"{chat_info}\n"
                f"💬 Chat ID: <code>{m.chat.id}</code>\n"
                f"🔎 Query: <code>{query}</code>"
            )
            await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)

            msg = await m.reply(
                "<b>Nᴏ Sᴇᴀʀᴄʜ Rᴇsᴜʟᴛ Fᴏᴜɴᴅ. Pᴏssɪʙʟᴇ Sᴘᴇʟʟɪɴɢ Mɪsᴛᴀᴋᴇ ᴏʀ Uɴʀᴇʟᴇᴀsᴇᴅ/Uɴᴀᴠᴀɪʟᴀʙʟᴇ Mᴏᴠɪᴇ ᴏɴ OTT Pʟᴀᴛғᴏʀᴍ (Theater Prints are not Available).</b>\n\n"
                "<b>Note:</b>\n"
                "<b>Dᴏɴ'ᴛ Mᴇɴᴛɪᴏɴ \"ᴛᴀᴍɪʟ ᴅᴜʙʙᴇᴅ\" ᴏʀ \"ᴛᴀᴍɪʟ ᴍᴏᴠɪᴇs\"</b>\n"
                "<b>Jᴜsᴛ Sᴇɴᴅ Mᴏᴠɪᴇ Nᴀᴍᴇ ᴡɪᴛʜ Yᴇᴀʀ</b>",
                parse_mode=enums.ParseMode.HTML
            )

        asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))
        return

    # ✅ Results found (also auto delete)
    markup = get_file_buttons(results, query, 0)
    user = m.from_user
    mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    msg = await m.reply(
        f"🔍 Found the following files for {mention}:",
        reply_markup=markup,
        parse_mode=enums.ParseMode.HTML
    )
    asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))




# ------------------ Channel File Indexing ------------------ #
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


