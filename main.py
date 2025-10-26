import os
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
UPI_ID = os.getenv("UPI_ID")
AMOUNT = os.getenv("AMOUNT", "499")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) if os.getenv("ADMIN_USER_ID") else None
APP_URL = os.getenv("APP_URL")

# Simple in-memory map
proof_map = {}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Type /pay to get UPI payment details.")


async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"💰 *Payment Details:*\n\n"
        f"UPI ID: `{UPI_ID}`\n"
        f"Amount: ₹{AMOUNT}\n\n"
        "Pay on the above UPI ID and share a full screenshot of the transaction."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message or not update.message.photo:
        await update.message.reply_text("Please send a photo of your payment.")
        return

    photo = update.message.photo[-1]
    caption = (
        f"🧾 *Payment proof received*\n\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n"
    )

    accept_cb = f"action:accept|payer:{user.id}"
    decline_cb = f"action:decline|payer:{user.id}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=accept_cb),
            InlineKeyboardButton("❌ Decline", callback_data=decline_cb),
        ]
    ])

    sent = await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=photo.file_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    proof_map[sent.message_id] = user.id
    await update.message.reply_text("✅ Payment proof received. Awaiting admin verification.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if ADMIN_USER_ID and query.from_user.id != ADMIN_USER_ID:
        await query.reply_text("You are not authorized to approve payments.")
        return

    data = dict(part.split(":", 1) for part in query.data.split("|"))
    action, payer_id = data["action"], int(data["payer"])
    channel_msg_id = query.message.message_id

    if action == "accept":
        try:
            expire_ts = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
            link = await context.bot.create_chat_invite_link(
                chat_id=TARGET_CHANNEL_ID,
                member_limit=1,
                expire_date=expire_ts,
            )
            invite_url = link.invite_link
        except Exception as e:
            logger.exception("Invite link creation failed")
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n⚠️ Failed to create invite link.",
                parse_mode="Markdown",
            )
            return

        try:
            await context.bot.send_message(
                chat_id=payer_id,
                text=(
                    "✅ Payment approved!\n\n"
                    f"Join the private channel using this one-time link:\n{invite_url}\n\n"
                    "_Expires in 1 hour or after one use._"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Could not message payer directly: %s", e)

        approved_by = query.from_user.full_name
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ *Approved by:* {approved_by}",
            parse_mode="Markdown",
        )

    elif action == "decline":
        declined_by = query.from_user.full_name
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n❌ *Declined by:* {declined_by}",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=payer_id,
                text="❌ Payment proof declined. Please contact support.",
            )
        except Exception:
            pass

    proof_map.pop(channel_msg_id, None)


# --- Webhook Server ---
async def webhook_handler(request):
    data = await request.json()
    await request.app["bot_app"].update_queue.put(data)
    return web.Response(status=200)


async def set_webhook(app):
    webhook_url = f"{APP_URL}/webhook/{BOT_TOKEN}"
    await app["bot_app"].bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")


def main():
    if not BOT_TOKEN or not APP_URL:
        raise ValueError("Missing BOT_TOKEN or APP_URL in environment")

    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("pay", pay))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))

    web_app = web.Application()
    web_app["bot_app"] = bot_app
    web_app.router.add_post(f"/webhook/{BOT_TOKEN}", webhook_handler)

    async def on_startup(app):
        await bot_app.initialize()
        await bot_app.start()
        await set_webhook(app)

    async def on_shutdown(app):
        await bot_app.stop()
        await bot_app.shutdown()

    web_app.on_startup.append(on_startup)
    web_app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 8000))
    web.run_app(web_app, port=port)


if __name__ == "__main__":
    main()
