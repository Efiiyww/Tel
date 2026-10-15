import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# خواندن از محیط (Environment)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("BOT_TOKEN و ADMIN_ID باید تنظیم شوند")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

reply_map = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args:
        try:
            target_id = int(args[0])
            context.user_data["target_id"] = target_id
            await update.message.reply_text(
                "✉️ پیام ناشناس خود را بنویسید:\n\n"
                "پیام شما به صورت ناشناس ارسال می‌شود."
            )
        except ValueError:
            await update.message.reply_text("لینک نامعتبر است.")
    else:
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={user.id}"

        text = (
            f"سلام {user.first_name} 👋\n\n"
            "لینک اختصاصی پیام ناشناس شما:\n"
            f"`{link}`\n\n"
            "این لینک را برای دوستانت بفرست تا بتوانند به صورت ناشناس به تو پیام دهند.\n\n"
            "⚠️ توجه: آیدی فرستنده برای ادمین ربات قابل مشاهده است."
        )
        await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if "target_id" in context.user_data:
        target_id = context.user_data["target_id"]

        sender_info = (
            f"👤 فرستنده:\n"
            f"آیدی: `{user.id}`\n"
            f"نام: {user.first_name or ''}\n"
            f"یوزرنیم: @{user.username if user.username else 'ندارد'}"
        )

        try:
            sent = await context.bot.send_message(
                chat_id=target_id,
                text=f"📩 پیام ناشناس جدید:\n\n{message.text or '(پیام رسانه‌ای)'}"
            )

            if message.photo:
                await context.bot.send_photo(chat_id=target_id, photo=message.photo[-1].file_id, caption="📩 پیام ناشناس")
            elif message.video:
                await context.bot.send_video(chat_id=target_id, video=message.video.file_id, caption="📩 پیام ناشناس")
            elif message.voice:
                await context.bot.send_voice(chat_id=target_id, voice=message.voice.file_id)
            elif message.document:
                await context.bot.send_document(chat_id=target_id, document=message.document.file_id, caption="📩 پیام ناشناس")

            await message.reply_text("✅ پیام شما با موفقیت ارسال شد.")

            admin_text = (
                f"🔔 پیام ناشناس جدید دریافت شد\n\n"
                f"{sender_info}\n\n"
                f"📝 متن پیام:\n{message.text or '(رسانه)'}\n\n"
                f"گیرنده آیدی: `{target_id}`"
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="Markdown"
            )

            reply_map[sent.message_id] = user.id

        except Exception as e:
            await message.reply_text("❌ خطا در ارسال پیام. ممکن است گیرنده ربات را بلاک کرده باشد.")
            logger.error(e)

        del context.user_data["target_id"]
        return

    if message.reply_to_message and message.reply_to_message.message_id in reply_map:
        original_sender = reply_map[message.reply_to_message.message_id]
        try:
            await context.bot.send_message(
                chat_id=original_sender,
                text=f"💬 پاسخ ناشناس:\n\n{message.text}"
            )
            await message.reply_text("✅ پاسخ ارسال شد.")
        except Exception:
            await message.reply_text("❌ نتوانستم پاسخ را ارسال کنم.")
        return

    await message.reply_text(
        "برای دریافت پیام ناشناس، لینک اختصاصی خود را از دستور /start بگیرید."
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    print("ربات شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()
