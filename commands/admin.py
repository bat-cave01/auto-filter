import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from config import client, ADMIN_ID, users_collection, files_collection, INDEX_CHANNEL, BASE_URL
from utils.helpers import save_user,get_file_buttons,build_index_page,send_paginated_files

# ------------------ /status ------------------ #
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


# ------------------ /send ------------------ #
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

        # Optional: Get user info for confirmation
        try:
            user = await c.get_users(user_id)
        except Exception:
            user = None

        # Regex search for matching files
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not matching_files:
            return await m.reply("❌ No files found matching your query.")

        # Send paginated files
        await send_paginated_files(c, user_id, matching_files, 0, filename_query)

        # Confirmation
        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            await m.reply(f"✅ Sent to <a href='tg://user?id={user_id}'>{name}</a>", parse_mode=enums.ParseMode.HTML)
        else:
            await m.reply(f"✅ Files sent to user ID: <code>{user_id}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)


# ------------------ /broadcast ------------------ #
@client.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("❗ Reply to a message to broadcast.")

    sent, failed = 0, 0
    users = users_collection.find()

    for user in users:
        try:
            sent_msg = await m.reply_to_message.copy(user["user_id"])
            sent += 1
            asyncio.create_task(auto_delete(sent_msg, delay=172800))
        except:
            failed += 1
        await asyncio.sleep(0.1)

    await m.reply(f"✅ Broadcast done.\n✔️ Sent: {sent}\n❌ Failed: {failed}")


# ------------------ Auto Delete ------------------ #
async def auto_delete(message: Message, delay: int = 10):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# ------------------ /link ------------------ #
@client.on_message(filters.command("link") & filters.user(ADMIN_ID))
async def link_handler(c: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to any message (text/media) with `/link`.", quote=True)

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
