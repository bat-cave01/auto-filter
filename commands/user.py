from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import client

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



