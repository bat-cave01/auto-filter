import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import client, files_collection, GROUP_ID, BASE_URL, BOT_USERNAME, UPDATES_CHANNEL, MOVIES_GROUP, LOG_CHANNEL,DELETE_DELAY,DELETE_AFTER
from utils.helpers import save_user, delete_after_delay, check_sub_and_send_file,build_index_page,get_file_buttons

PAGE_SIZE = 65  # Default delay for messages in seconds

# ------------------ Group /start ------------------ #


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


