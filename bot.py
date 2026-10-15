import logging
import os
import random
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

if not BOT_TOKEN or ADMIN_ID == 0:
    raise RuntimeError("BOT_TOKEN و ADMIN_ID باید تنظیم شوند")

# ================== وضعیت‌ها ==================
(
    MAIN_MENU,
    WAITING_GENDER,
    IN_CHAT,
) = range(3)

# صف‌ها و وضعیت کاربران
random_queue = []          # صف رندوم
girl_queue = []            # صف دختر
boy_queue = []             # صف پسر
partners = {}              # {user_id: partner_id}
user_gender = {}           # {user_id: "girl" یا "boy"}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== کیبوردها ==================
def main_keyboard():
    keyboard = [
        [KeyboardButton("به یک ناشناس وصلم کن")],
        [KeyboardButton("به مخاطب خاص وصلم کن")],
        [KeyboardButton("لینک ناشناس من"), KeyboardButton("راهنما")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def gender_keyboard():
    keyboard = [
        [KeyboardButton("دختر 👩"), KeyboardButton("پسر 👨")],
        [KeyboardButton("بازگشت به منو")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def chat_keyboard():
    keyboard = [
        [KeyboardButton("قطع ارتباط ❌")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== توابع کمکی ==================
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطا در ارسال به ادمین: {e}")

def remove_from_queues(user_id):
    if user_id in random_queue:
        random_queue.remove(user_id)
    if user_id in girl_queue:
        girl_queue.remove(user_id)
    if user_id in boy_queue:
        boy_queue.remove(user_id)

# ================== دستورات ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # اگر از لینک ناشناس آمده
    if args:
        try:
            target_id = int(args[0])
            if target_id == user.id:
                await update.message.reply_text("نمی‌توانی به خودت پیام ناشناس بفرستی!")
                return MAIN_MENU

            context.user_data["anonymous_target"] = target_id
            await update.message.reply_text(
                "✉️ پیام ناشناس خود را بنویسید:\n\n"
                "پیام شما به صورت ناشناس ارسال می‌شود.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        except:
            pass

    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        "به ربات چت ناشناس خوش آمدی!\n"
        "از دکمه‌های زیر استفاده کن:",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **راهنمای ربات**\n\n"
        "🔹 **به یک ناشناس وصلم کن**\n"
        "رندوم به یک نفر وصل می‌شوی و می‌توانی چت کنی.\n\n"
        "🔹 **به مخاطب خاص وصلم کن**\n"
        "جنسیت مورد نظرت را انتخاب کن تا فقط با همان جنسیت وصل شوی.\n\n"
        "🔹 **لینک ناشناس من**\n"
        "لینک اختصاصی خودت را بگیر و برای دیگران بفرست تا بتوانند ناشناس به تو پیام دهند.\n\n"
        "🔹 برای قطع چت از دکمه «قطع ارتباط ❌» یا دستور /stop استفاده کن."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    return MAIN_MENU

async def my_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user.id}"

    await update.message.reply_text(
        f"🔗 **لینک ناشناس شما:**\n\n"
        f"`{link}`\n\n"
        "این لینک را برای دوستانت بفرست تا بتوانند به صورت ناشناس به تو پیام دهند.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

# ================== اتصال رندوم ==================
async def connect_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in partners:
        await update.message.reply_text("شما در حال حاضر در چت هستید! اول قطع ارتباط کنید.")
        return IN_CHAT

    remove_from_queues(user_id)

    # اگر کسی در صف باشد
    if random_queue:
        partner_id = random_queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id

        await context.bot.send_message(
            partner_id,
            "✅ به یک ناشناس وصل شدی!\nحالا می‌تونی پیام بفرستی.\n\nبرای قطع ارتباط از دکمه زیر استفاده کن.",
            reply_markup=chat_keyboard()
        )
        await update.message.reply_text(
            "✅ به یک ناشناس وصل شدی!\nحالا می‌تونی پیام بفرستی.\n\nبرای قطع ارتباط از دکمه زیر استفاده کن.",
            reply_markup=chat_keyboard()
        )

        await notify_admin(
            context,
            f"🔗 **اتصال رندوم جدید**\n"
            f"کاربر ۱: `{user_id}`\n"
            f"کاربر ۲: `{partner_id}`"
        )
        return IN_CHAT
    else:
        random_queue.append(user_id)
        await update.message.reply_text(
            "⏳ در حال جستجو برای یک ناشناس...\nلطفاً صبر کن.",
            reply_markup=ReplyKeyboardRemove()
        )
        return MAIN_MENU

# ================== اتصال بر اساس جنسیت ==================
async def connect_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in partners:
        await update.message.reply_text("شما در حال حاضر در چت هستید! اول قطع ارتباط کنید.")
        return IN_CHAT

    await update.message.reply_text(
        "می‌خوای با چه جنسیتی صحبت کنی؟",
        reply_markup=gender_keyboard()
    )
    return WAITING_GENDER

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "بازگشت به منو":
        await update.message.reply_text("به منوی اصلی برگشتی.", reply_markup=main_keyboard())
        return MAIN_MENU

    if "دختر" in text:
        preferred = "girl"
        queue = girl_queue
    elif "پسر" in text:
        preferred = "boy"
        queue = boy_queue
    else:
        await update.message.reply_text("لطفاً یکی از دکمه‌ها را انتخاب کن.", reply_markup=gender_keyboard())
        return WAITING_GENDER

    remove_from_queues(user_id)

    if queue:
        partner_id = queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id

        await context.bot.send_message(
            partner_id,
            f"✅ به یک {'دختر' if preferred == 'girl' else 'پسر'} ناشناس وصل شدی!",
            reply_markup=chat_keyboard()
        )
        await update.message.reply_text(
            f"✅ به یک {'دختر' if preferred == 'girl' else 'پسر'} ناشناس وصل شدی!",
            reply_markup=chat_keyboard()
        )

        await notify_admin(
            context,
            f"🔗 **اتصال جنسیتی جدید**\n"
            f"کاربر: `{user_id}` → {'دختر' if preferred == 'girl' else 'پسر'}\n"
            f"شریک: `{partner_id}`"
        )
        return IN_CHAT
    else:
        queue.append(user_id)
        await update.message.reply_text(
            f"⏳ در حال جستجو برای یک {'دختر' if preferred == 'girl' else 'پسر'}...\nلطفاً صبر کن.",
            reply_markup=ReplyKeyboardRemove()
        )
        return MAIN_MENU

# ================== مدیریت چت ==================
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message

    # اگر کاربر در صف است و پیام داد
    if user_id in random_queue or user_id in girl_queue or user_id in boy_queue:
        await update.message.reply_text("هنوز کسی پیدا نشده. لطفاً صبر کن یا /start را بزن.")
        return MAIN_MENU

    # اگر در چت است
    if user_id in partners:
        partner_id = partners[user_id]

        if message.text == "قطع ارتباط ❌":
            return await stop_chat(update, context)

        # ارسال پیام به طرف مقابل
        try:
            if message.text:
                await context.bot.send_message(partner_id, f"👤 ناشناس:\n{message.text}")
            elif message.photo:
                await context.bot.send_photo(partner_id, message.photo[-1].file_id, caption="👤 ناشناس (عکس)")
            elif message.voice:
                await context.bot.send_voice(partner_id, message.voice.file_id)
            elif message.video:
                await context.bot.send_video(partner_id, message.video.file_id, caption="👤 ناشناس (ویدیو)")
            elif message.document:
                await context.bot.send_document(partner_id, message.document.file_id, caption="👤 ناشناس (فایل)")
            else:
                await context.bot.send_message(partner_id, "👤 ناشناس یک پیام رسانه‌ای فرستاد.")

            # اطلاع به ادمین
            admin_text = (
                f"💬 **پیام در چت ناشناس**\n\n"
                f"از: `{user_id}`\n"
                f"به: `{partner_id}`\n\n"
                f"متن: {message.text or '(رسانه)'}"
            )
            await notify_admin(context, admin_text)

        except Exception as e:
            await update.message.reply_text("خطا در ارسال پیام. ممکن است طرف مقابل ربات را بلاک کرده باشد.")
            logger.error(e)

        return IN_CHAT

    # پیام عادی
    await update.message.reply_text("از دکمه‌های منو استفاده کن.", reply_markup=main_keyboard())
    return MAIN_MENU

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in partners:
        partner_id = partners[user_id]
        del partners[user_id]
        if partner_id in partners:
            del partners[partner_id]

        await context.bot.send_message(
            partner_id,
            "❌ طرف مقابل ارتباط را قطع کرد.",
            reply_markup=main_keyboard()
        )
        await update.message.reply_text(
            "❌ ارتباط قطع شد.",
            reply_markup=main_keyboard()
        )

        await notify_admin(context, f"❌ قطع ارتباط\nکاربر: `{user_id}` و `{partner_id}`")
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
        await context.bot.send_message(
            target_id,
            f"📩 **پیام ناشناس جدید:**\n\n{update.message.text or '(رسانه)'}",
            parse_mode="Markdown"
        )

        await update.message.reply_text("✅ پیام شما ارسال شد.", reply_markup=main_keyboard())

        # اطلاع به ادمین
        admin_text = (
            f"📩 **پیام ناشناس یک‌طرفه**\n\n"
            f"فرستنده: `{user.id}`\n"
            f"نام: {user.first_name}\n"
            f"یوزرنیم: @{user.username or 'ندارد'}\n"
            f"گیرنده: `{target_id}`\n\n"
            f"متن: {update.message.text or '(رسانه)'}"
        )
        await notify_admin(context, admin_text)

    except Exception:
        await update.message.reply_text("❌ خطا در ارسال. ممکن است گیرنده ربات را بلاک کرده باشد.")

    context.user_data.pop("anonymous_target", None)
    return MAIN_MENU

# ================== اصلی ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^به یک ناشناس وصلم کن$"), connect_random),
                MessageHandler(filters.Regex("^به مخاطب خاص وصلم کن$"), connect_specific),
                MessageHandler(filters.Regex("^لینک ناشناس من$"), my_link),
                MessageHandler(filters.Regex("^راهنما$"), help_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat),
            ],
            WAITING_GENDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gender_selected),
            ],
            IN_CHAT: [
                MessageHandler(filters.Regex("^قطع ارتباط ❌$"), stop_chat),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_chat),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("stop", stop_chat),
            MessageHandler(filters.Regex("^قطع ارتباط ❌$"), stop_chat),
        ],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anonymous_message))

    print("ربات پیشرفته شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()
