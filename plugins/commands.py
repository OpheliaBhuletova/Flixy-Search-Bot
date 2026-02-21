import os
import re
import json
import base64
import time
import random
import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.utils.messages import Texts
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_size, is_subscribed
from bot.utils.helpers import get_settings, save_group_settings

from database.ia_filterdb import Media, get_file_details, unpack_new_file_id
from database.users_chats_db import db
from database.connections_mdb import active_connection

logger = logging.getLogger(__name__)

BATCH_FILES: dict = {}


# ─── START / GENID ────────────────────────────────────────────────────

@Client.on_message(filters.command("genid") & filters.private)
async def gen_file_id(client: Client, message: Message):
    msg = await message.reply_photo("images/start_1.png")
    await message.reply_text(
        f"FILE_ID:\n<code>{msg.photo.file_id}</code>",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command("start") & filters.incoming)
async def start_handler(client: Client, message: Message):
    # ── GROUP START ──
    if message.chat.type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}:
        buttons = [
            [InlineKeyboardButton("🤖 Updates", url="https://t.me/+lRax6d2QVoJlNmMx")],
            [InlineKeyboardButton("ℹ️ Help", url=f"https://t.me/{RuntimeCache.bot_username}?start=help")]
        ]
        await message.reply(
            Texts.START_TXT.format(
                message.from_user.mention if message.from_user else message.chat.title,
                RuntimeCache.bot_username,
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN,
        )

        await asyncio.sleep(2)

        if not await db.get_chat(message.chat.id):
            members = await client.get_chat_members_count(message.chat.id)
            if settings.LOG_CHANNEL:
                try:
                    await client.send_message(
                        settings.LOG_CHANNEL,
                        Texts.LOG_TEXT_G.format(
                            message.chat.title,
                            message.chat.id,
                            members,
                            "Unknown",
                        ),
                    )
                except (PeerIdInvalid, ValueError) as e:
                    logger.warning("Failed to send log message to LOG_CHANNEL %s: %s", settings.LOG_CHANNEL, e)
                except Exception:
                    logger.exception("Unexpected error sending log message to LOG_CHANNEL")
            await db.add_chat(message.chat.id, message.chat.title)
        return

    # ── PRIVATE START ──
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        if settings.LOG_CHANNEL:
            try:
                await client.send_message(
                    settings.LOG_CHANNEL,
                    Texts.LOG_TEXT_P.format(message.from_user.id, message.from_user.mention),
                )
            except (PeerIdInvalid, ValueError) as e:
                logger.warning("Failed to send log message to LOG_CHANNEL %s: %s", settings.LOG_CHANNEL, e)
            except Exception:
                logger.exception("Unexpected error sending log message to LOG_CHANNEL")

    if len(message.command) != 2:
        buttons = [
            [
                InlineKeyboardButton("🔍 Search", switch_inline_query_current_chat=""),
                InlineKeyboardButton("🤖 Updates", url="https://t.me/+VbQUA9MDA7A2ODRl")
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                InlineKeyboardButton("😊 About", callback_data="about")
            ]
        ]
        await message.reply_photo(
            random.choice(settings.PICS),
            caption=Texts.START_TXT.format(
                message.from_user.mention,
                RuntimeCache.bot_username,
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    # ── FORCE SUB ──
    if settings.AUTH_CHANNEL and not await is_subscribed(client, message):
        try:
            invite = await client.create_chat_invite_link(settings.AUTH_CHANNEL)
        except ChatAdminRequired:
            logger.error("Bot must be admin in AUTH_CHANNEL")
            return

        buttons = [[InlineKeyboardButton("🤖 Join Updates Channel", url=invite.invite_link)]]
        await client.send_message(
            message.from_user.id,
            "**Please join the updates channel to use this bot!**",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return