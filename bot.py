import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

if not BOT_TOKEN or ADMIN_ID == 0:
    raise RuntimeError("BOT_TOKEN و ADMIN_ID باید تنظیم شوند")

# ================== وضعیت‌ها ==================
MAIN_MENU, WAITING_GENDER, IN_CHAT, WAITING_ADMIN_REPLY = range(4)

# داده‌ها
random_queue = []
girl_queue = []
boy_queue = []
partners = {}
blocked_users = set()          # کاربران بلاک‌شده
admin_reply_target = {}        # {admin_id: target_user_id}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
    return ReplyKeyboardMarkup([[KeyboardButton("قطع ارتباط ❌")]], resize_keyboard=True)

def admin_buttons(user_id: int):
    """دکمه‌های شیشه‌ای برای ادمین"""
    keyboard = [
        [
            InlineKeyboardButton("💬 پاسخ دادن", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 بلاک کردن", callback_data=f"block_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ================== اطلاع به ادمین با دکمه ==================
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int = None):
    try:
        if user_id:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=admin_buttons(user_id)
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                parse_mode="Markdown"
            )
        logger.info("✅ پیام به ادمین ارسال شد")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به ادمین: {e}")

def remove_from_queues(user_id: int):
    for q in (random_queue, girl_queue, boy_queue):
        if user_id in q:
            q.remove(user_id)

# ================== دستورات ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if user.id in blocked_users:
        await update.message.reply_text("شما توسط ادمین بلاک شده‌اید.")
        return ConversationHandler.END

    if args:
        try:
            target_id = int(args[0])
            if target_id == user.id:
                await update.message.reply_text("نمی‌توانی به خودت پیام ناشناس بفرستی!")
                return MAIN_MENU
            context.user_data["anonymous_target"] = target_id
            await update.message.reply_text(
                "✉️ پیام ناشناس خود را بنویسید:",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        except:
            pass

    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\nبه ربات چت ناشناس خوش آمدی!",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **راهنما**\n\n"
        "🔹 به یک ناشناس وصلم کن → رندوم\n"
        "🔹 به مخاطب خاص وصلم کن → بر اساس جنسیت\n"
        "🔹 لینک ناشناس من → لینک اختصاصی\n"
        "🔹 قطع ارتباط با دکمه مخصوص"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    return MAIN_MENU

async def my_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={user.id}"
    await update.message.reply_text(
        f"🔗 **لینک ناشناس شما:**\n\n`{link}`",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

# ================== اتصال‌ها ==================
async def connect_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        await update.message.reply_text("شما بلاک شده‌اید.")
        return MAIN_MENU
    if user_id in partners:
        await update.message.reply_text("در حال چت هستید!", reply_markup=chat_keyboard())
        return IN_CHAT

    remove_from_queues(user_id)
    if random_queue:
        partner_id = random_queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id
        msg = "✅ به یک ناشناس وصل شدی!"
        await context.bot.send_message(partner_id, msg, reply_markup=chat_keyboard())
        await update.message.reply_text(msg, reply_markup=chat_keyboard())
        await notify_admin(context, f"🔗 اتصال رندوم\n`{user_id}` ↔ `{partner_id}`")
        return IN_CHAT
    else:
        random_queue.append(user_id)
        await update.message.reply_text("⏳ در حال جستجو...", reply_markup=ReplyKeyboardRemove())
        return MAIN_MENU

async def connect_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in blocked_users:
        await update.message.reply_text("شما بلاک شده‌اید.")
        return MAIN_MENU
    await update.message.reply_text("جنسیت مورد نظرت را انتخاب کن:", reply_markup=gender_keyboard())
    return WAITING_GENDER

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text == "بازگشت به منو":
        await update.message.reply_text("بازگشت به منو", reply_markup=main_keyboard())
        return MAIN_MENU

    if "دختر" in text:
        queue, gender_name = girl_queue, "دختر"
    elif "پسر" in text:
        queue, gender_name = boy_queue, "پسر"
    else:
        await update.message.reply_text("یکی از دکمه‌ها را انتخاب کن.", reply_markup=gender_keyboard())
        return WAITING_GENDER

    remove_from_queues(user_id)
    if queue:
        partner_id = queue.pop(0)
        partners[user_id] = partner_id
        partners[partner_id] = user_id
        msg = f"✅ به یک {gender_name} ناشناس وصل شدی!"
        await context.bot.send_message(partner_id, msg, reply_markup=chat_keyboard())
        await update.message.reply_text(msg, reply_markup=chat_keyboard())
        await notify_admin(context, f"🔗 اتصال جنسیتی\n`{user_id}` → {gender_name}\n`{partner_id}`")
        return IN_CHAT
    else:
        queue.append(user_id)
        await update.message.reply_text(f"⏳ در حال جستجو برای {gender_name}...", reply_markup=ReplyKeyboardRemove())
        return MAIN_MENU

# ================== مدیریت پیام در چت ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    message = update.message

    if user_id in blocked_users:
        await update.message.reply_text("شما توسط ادمین بلاک شده‌اید.")
        return MAIN_MENU

    if user_id in random_queue or user_id in girl_queue or user_id in boy_queue:
        await update.message.reply_text("هنوز کسی پیدا نشده.")
        return MAIN_MENU

    if user_id in partners:
        partner_id = partners[user_id]
        if message.text == "قطع ارتباط ❌":
            return await stop_chat(update, context)

        try:
            if message.text:
                await context.bot.send_message(partner_id, f"👤 ناشناس:\n{message.text}")
            elif message.photo:
                await context.bot.send_photo(partner_id, message.photo[-1].file_id, caption="👤 ناشناس")
            elif message.voice:
                await context.bot.send_voice(partner_id, message.voice.file_id)
            elif message.video:
                await context.bot.send_video(partner_id, message.video.file_id, caption="👤 ناشناس")
            elif message.document:
                await context.bot.send_document(partner_id, message.document.file_id, caption="👤 ناشناس")
            else:
                await context.bot.send_message(partner_id, "👤 ناشناس پیام رسانه‌ای فرستاد")

            # اطلاع به ادمین با دکمه
            admin_text = (
                f"💬 **پیام در چت**\n\n"
                f"از: `{user_id}`\n"
                f"نام: {user.first_name or '-'}\n"
                f"یوزرنیم: @{user.username or 'ندارد'}\n"
                f"به: `{partner_id}`\n\n"
                f"متن: {message.text or '(رسانه)'}"
            )
            await notify_admin(context, admin_text, user_id=user_id)

        except Exception as e:
            logger.error(e)
            await update.message.reply_text("خطا در ارسال پیام.")
        return IN_CHAT

    await update.message.reply_text("از دکمه‌های منو استفاده کن.", reply_markup=main_keyboard())
    return MAIN_MENU

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in partners:
        partner_id = partners.pop(user_id)
        if partner_id in partners:
            del partners[partner_id]
        try:
            await context.bot.send_message(partner_id, "❌ طرف مقابل قطع کرد.", reply_markup=main_keyboard())
        except:
            pass
        await update.message.reply_text("❌ ارتباط قطع شد.", reply_markup=main_keyboard())
        await notify_admin(context, f"❌ قطع ارتباط\n`{user_id}` و `{partner_id}`")
    else:
        remove_from_queues(user_id)
        await update.message.reply_text("در چت نبودید.", reply_markup=main_keyboard())
    return MAIN_MENU

# ================== پیام ناشناس یک‌طرفه ==================
async def anonymous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in blocked_users:
        await update.message.reply_text("شما بلاک شده‌اید.")
        return

    target_id = context.user_data.get("anonymous_target")
    if not target_id:
        return

    try:
        text = update.message.text or "(رسانه)"
        await context.bot.send_message(target_id, f"📩 **پیام ناشناس:**\n\n{text}", parse_mode="Markdown")
        await update.message.reply_text("✅ پیام ارسال شد.", reply_markup=main_keyboard())

        admin_text = (
            f"📩 **پیام ناشناس یک‌طرفه**\n\n"
            f"فرستنده: `{user.id}`\n"
            f"نام: {user.first_name or '-'}\n"
            f"یوزرنیم: @{user.username or 'ندارد'}\n"
            f"گیرنده: `{target_id}`\n\n"
            f"متن: {text}"
        )
        await notify_admin(context, admin_text, user_id=user.id)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ خطا در ارسال.")
    context.user_data.pop("anonymous_target", None)

# ================== دکمه‌های ادمین (پاسخ و بلاک) ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    admin_id = query.from_user.id

    if admin_id != ADMIN_ID:
        await query.edit_message_text("فقط ادمین می‌تواند از این دکمه‌ها استفاده کند.")
        return

    if data.startswith("reply_"):
        target_id = int(data.split("_")[1])
        admin_reply_target[admin_id] = target_id
        await query.edit_message_text(f"💬 در حال پاسخ به کاربر `{target_id}`\n\nمتن پاسخ خود را بنویسید:", parse_mode="Markdown")
        return WAITING_ADMIN_REPLY

    elif data.startswith("block_"):
        target_id = int(data.split("_")[1])
        blocked_users.add(target_id)
        # اگر در چت بود قطع کن
        if target_id in partners:
            partner = partners.pop(target_id)
            if partner in partners:
                del partners[partner]
            try:
                await context.bot.send_message(partner, "❌ طرف مقابل قطع شد.")
            except:
                pass
        remove_from_queues(target_id)
        await query.edit_message_text(f"🚫 کاربر `{target_id}` بلاک شد.", parse_mode="Markdown")
        await notify_admin(context, f"🚫 کاربر `{target_id}` توسط ادمین بلاک شد.")

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id != ADMIN_ID:
        return

    target_id = admin_reply_target.get(admin_id)
    if not target_id:
        await update.message.reply_text("هدفی برای پاسخ وجود ندارد.")
        return MAIN_MENU

    try:
        await context.bot.send_message(target_id, f"💬 **پاسخ ناشناس از طرف گیرنده:**\n\n{update.message.text}", parse_mode="Markdown")
        await update.message.reply_text("✅ پاسخ ارسال شد.")
        await notify_admin(context, f"✅ ادمین به کاربر `{target_id}` پاسخ داد:\n{update.message.text}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال پاسخ: {e}")

    admin_reply_target.pop(admin_id, None)
    return MAIN_MENU

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
            WAITING_ADMIN_REPLY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply),
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anonymous_message))

    logger.info("ربات با قابلیت پاسخ و بلاک شروع شد...")
    app.run_polling()

if __name__ == "__main__":
    main()
