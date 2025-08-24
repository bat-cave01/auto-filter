from pyrogram import Client, enums
from pyrogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from config import client, UPDATES_CHANNEL
import asyncio

@client.on_chat_member_updated()
async def welcome_and_goodbye(client: Client, event: ChatMemberUpdated):
    if event.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return

    if event.new_chat_member and event.new_chat_member.status == enums.ChatMemberStatus.MEMBER:
        user = event.new_chat_member.user
        msg = await client.send_message(
            event.chat.id,
            f"<b>👋 Hᴇʏ <a href='tg://user?id={user.id}'>{user.first_name}</a>, Wᴇʟᴄᴏᴍᴇ ᴛᴏ {chat_title} 🎉.</b>\n\n"
            "<b>Jᴜsᴛ Sᴇɴᴅ ᴀ Mᴏᴠɪᴇ ᴏʀ Sᴇʀɪᴇs Nᴀᴍᴇ ᴡɪᴛʜ Cᴏʀʀᴇᴄᴛ Sᴘᴇʟʟɪɴɢ, I Wɪʟʟ Gɪᴠᴇ Yᴏᴜ ᴀ Fɪʟᴇs Lɪɴᴋ Sᴛᴏʀᴇᴅ ɪɴ Mʏ Dᴀᴛᴀʙᴀsᴇ.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Updates Channel", url=UPDATES_CHANNEL)]])
        )
        await asyncio.sleep(60)
        await msg.delete()

    elif event.old_chat_member and event.old_chat_member.status in [
        enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.RESTRICTED
    ] and event.new_chat_member and event.new_chat_member.status in [
        enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.KICKED
    ]:
        user = event.old_chat_member.user
        msg = await client.send_message(
            event.chat.id,
            f"<i>👋 <a href='tg://user?id={user.id}'>{user.first_name}</a> has left the group. Goodbye!</i>",
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(60)
        await msg.delete()
