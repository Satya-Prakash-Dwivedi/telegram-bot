import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
from datetime import datetime, timedelta, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
UPI_ID = os.getenv("UPI_ID")
AMOUNT = os.getenv("AMOUNT", "499")
CHANNEL_ID = os.getenv("CHANNEL_ID")           
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")  
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) if os.getenv("ADMIN_USER_ID") else None

# simple in-memory map: channel_message_id -> payer_user_id
# (persists only while bot runs; add DB for persistence)
proof_map = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Type /pay to get UPI payment details.")


async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        f"💰 *Payment Details:*\n\n"
        f"UPI ID: `{UPI_ID}`\n"
        f"Amount: ₹{AMOUNT}\n\n"
        f"Pay on the above UPI id and share a full screenshot of the transaction."
    )
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive screenshot from payer, post to channel with Accept/Decline buttons."""
    user = update.effective_user
    if not update.message or not update.message.photo:
        await update.message.reply_text("Please send a photo (screenshot) of your payment.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    caption = (
        f"🧾 *Payment proof received*\n\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n"
    )

    # Inline buttons include encoded action + payer id so handlers can act
    accept_cb = f"action:accept|payer:{user.id}"
    decline_cb = f"action:decline|payer:{user.id}"
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Accept", callback_data=accept_cb),
            InlineKeyboardButton("❌ Decline", callback_data=decline_cb),
        ]]
    )

    # send photo to the moderator channel and capture resulting message id
    sent = await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    # map the channel message to payer id for later reference
    proof_map[sent.message_id] = int(user.id)

    await update.message.reply_text("✅ Payment proof received. Awaiting manual verification.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Accept/Decline presses by admin."""
    query = update.callback_query
    await query.answer()  # acknowledge callback to Telegram

    user_who_pressed = query.from_user
    if ADMIN_USER_ID and user_who_pressed.id != ADMIN_USER_ID:
        await query.reply_text("You are not authorized to approve payments.")
        return

    data = query.data  # format: action:accept|payer:12345
    # parse
    parts = dict(part.split(":", 1) for part in data.split("|"))
    action = parts.get("action")
    payer_id = int(parts.get("payer"))
    channel_msg_id = query.message.message_id

    if action == "accept":
        # create single-use invite link to TARGET_CHANNEL_ID
        try:
            # expire in 1 hour (optional)
            expire_ts = int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())
            link = await context.bot.create_chat_invite_link(
                chat_id=TARGET_CHANNEL_ID,
                member_limit=1,
                expire_date=expire_ts
            )
            invite_url = link.invite_link
        except Exception as e:
            logger.exception("Failed to create invite link")
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n⚠️ Approval failed: could not create invite link.",
                parse_mode="Markdown"
            )
            await query.reply_text("Failed to create invite link. Check bot permissions.")
            return

        # notify the payer privately with the one-time link
        try:
            await context.bot.send_message(
                chat_id=payer_id,
                text=(
                    "✅ Your payment has been *approved*.\n\n"
                    f"Join the approved channel using this one-time link:\n{invite_url}\n\n"
                    "Note: This link is single-use and will expire once used."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.exception("Failed to send invite to payer")
            # still proceed to update channel message
            await query.reply_text("Approval done but failed to message the payer. They may not have started the bot.")

        # edit the channel post to mark approved
        approved_by = user_who_pressed.full_name
        new_caption = query.message.caption + f"\n\n✅ *Approved by:* {approved_by}"
        await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")

    elif action == "decline":
        declined_by = user_who_pressed.full_name
        new_caption = query.message.caption + f"\n\n❌ *Declined by:* {declined_by}"
        await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")

        # notify payer privately
        try:
            await context.bot.send_message(
                chat_id=payer_id,
                text="❌ Your payment proof was *declined*. Please contact support or re-upload a valid proof.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    # Optionally remove mapping
    proof_map.pop(channel_msg_id, None)


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing in .env")
        return
    if not CHANNEL_ID or not TARGET_CHANNEL_ID:
        logger.error("CHANNEL_ID or TARGET_CHANNEL_ID missing in .env")
        return
    if not ADMIN_USER_ID:
        logger.warning("ADMIN_USER_ID missing. Any user can press approve buttons.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pay", pay))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
