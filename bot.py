#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات چت ناشناس تلگرام (نسخه‌ی بازنویسی‌شده)

نیازمندی‌ها:  python-telegram-bot >= 20.0
متغیرهای محیطی:
    BOT_TOKEN  : 8626538162:AAFAjeF8Q1GDUkAFsQeRJ3vOeZXPLccvzXI
    ADMIN_ID   : 7332980185
    DATA_FILE  : (اختیاری) مسیر فایل ذخیره‌سازی، پیش‌فرض bot_data.json
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    Update,
    User,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================== تنظیمات ==============================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
DATA_FILE = os.environ.get("DATA_FILE", "bot_data.json")

if not BOT_TOKEN or ADMIN_ID == 0:
    raise RuntimeError("BOT_TOKEN و ADMIN_ID باید تنظیم شوند")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("anon-bot")

# ============================== متن دکمه‌ها ==============================
BTN_RANDOM = "به یک ناشناس وصلم کن"
BTN_SPECIFIC = "به مخاطب خاص وصلم کن"
BTN_MYLINK = "لینک ناشناس من"
BTN_HELP = "راهنما"
BTN_GIRL = "دختر 👩"
BTN_BOY = "پسر 👨"
BTN_BACK = "بازگشت به منو"
BTN_STOP = "قطع ارتباط ❌"
BTN_CANCEL_SEARCH = "لغو جستجو ❌"
BTN_CANCEL_ANON = "انصراف ❌"

GENDER_FA = {"girl": "دختر", "boy": "پسر"}
CAPTION_TYPES = ("photo", "video", "document", "audio", "voice", "animation")


# ============================== ذخیره‌سازی ==============================
class Store:
    """ذخیره‌ی پایدار کاربران، بلاک‌شده‌ها و جنسیت‌ها در یک فایل JSON."""

    def __init__(self, path: str):
        self.path = path
        self.users: dict[int, dict] = {}
        self.blocked: set[int] = set()
        self.genders: dict[int, str] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.users = {int(k): v for k, v in data.get("users", {}).items()}
            self.blocked = {int(x) for x in data.get("blocked", [])}
            self.genders = {int(k): v for k, v in data.get("genders", {}).items()}
        except Exception as e:  # noqa: BLE001
            logger.error("خطا در خواندن فایل داده: %s", e)

    def save(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "users": self.users,
                        "blocked": sorted(self.blocked),
                        "genders": self.genders,
                    },
                    f,
                    ensure_ascii=False,
                )
            os.replace(tmp, self.path)
        except Exception as e:  # noqa: BLE001
            logger.error("خطا در ذخیره‌ی فایل داده: %s", e)


store = Store(DATA_FILE)

# وضعیت‌های لحظه‌ای (در حافظه)
waiting: list[dict] = []          # [{"id", "gender", "wants"}]
partners: dict[int, int] = {}     # {user_id: partner_id}
admin_reply_target: dict[int, int] = {}  # {admin_id: target_user_id}


# ============================== ابزارهای کمکی ==============================
esc = html.escape


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def user_tag(uid: int) -> str:
    """نمایش HTML کاربر: نام (لینک) + آیدی + یوزرنیم + جنسیت."""
    info = store.users.get(uid, {})
    name = info.get("name") or str(uid)
    s = f'<a href="tg://user?id={uid}">{esc(name)}</a> (<code>{uid}</code>)'
    if info.get("username"):
        s += f" @{esc(info['username'])}"
    g = store.genders.get(uid)
    if g:
        s += f" [{GENDER_FA[g]}]"
    return s


def media_name(m: Message) -> str:
    for attr, title in (
        ("photo", "عکس"), ("video", "ویدیو"), ("voice", "ویس"), ("audio", "موزیک"),
        ("document", "فایل"), ("animation", "گیف"), ("sticker", "استیکر"),
        ("video_note", "ویدیو مسیج"), ("location", "لوکیشن"), ("contact", "مخاطب"),
        ("poll", "نظرسنجی"),
    ):
        if getattr(m, attr, None):
            return title
    return "رسانه"


def is_blocked(uid: int) -> bool:
    return uid != ADMIN_ID and uid in store.blocked


def in_queue(uid: int) -> bool:
    return any(e["id"] == uid for e in waiting)


def remove_from_queue(uid: int) -> None:
    waiting[:] = [e for e in waiting if e["id"] != uid]


def parse_gender(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    if "دختر" in text:
        return "girl"
    if "پسر" in text:
        return "boy"
    return None


# ============================== کیبوردها ==============================
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_RANDOM)],
            [KeyboardButton(BTN_SPECIFIC)],
            [KeyboardButton(BTN_MYLINK), KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def gender_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_GIRL), KeyboardButton(BTN_BOY)], [KeyboardButton(BTN_BACK)]],
        resize_keyboard=True,
    )


def chat_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_STOP)]], resize_keyboard=True)


def search_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_CANCEL_SEARCH)]], resize_keyboard=True)


def anon_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_CANCEL_ANON)]], resize_keyboard=True)


def admin_markup(*user_ids: int) -> InlineKeyboardMarkup:
    rows = []
    for uid in dict.fromkeys(user_ids):  # حذف تکراری با حفظ ترتیب
        if uid == ADMIN_ID:
            continue
        blocked = uid in store.blocked
        rows.append([
            InlineKeyboardButton(f"💬 پاسخ به {uid}", callback_data=f"reply_{uid}"),
            InlineKeyboardButton(
                f"✅ آنبلاک {uid}" if blocked else f"🚫 بلاک {uid}",
                callback_data=f"{'unblock' if blocked else 'block'}_{uid}",
            ),
        ])
    return InlineKeyboardMarkup(rows)


# ============================== ارتباط با ادمین ==============================
async def notify_admin(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> Optional[Message]:
    kb = markup if markup and markup.inline_keyboard else None
    try:
        return await context.bot.send_message(
            ADMIN_ID, text[:4000], parse_mode=ParseMode.HTML, reply_markup=kb
        )
    except Exception as e:  # noqa: BLE001
        logger.error("خطا در ارسال HTML به ادمین: %s", e)
        try:  # تلاش دوباره بدون فرمت تا پیام هرگز گم نشود
            plain = html.unescape(re.sub(r"<[^>]+>", "", text))
            return await context.bot.send_message(ADMIN_ID, plain[:4000], reply_markup=kb)
        except Exception as e2:  # noqa: BLE001
            logger.error("خطا در ارسال به ادمین: %s", e2)
            return None


_report_lock: Optional[asyncio.Lock] = None


async def report_message(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    sender: int,
    receiver: int,
    title: str,
    delivered: bool = True,
) -> None:
    """
    گزارش پیام برای ادمین در دو پیام پشت‌سرهم:
      ۱) پیام اطلاعات (بدون دکمه) شامل فرستنده/گیرنده/زمان
      ۲) خودِ پیام اصلی (متن یا رسانه) همراه با دکمه‌های پاسخ و بلاک
    """
    global _report_lock
    if sender == ADMIN_ID:
        return
    if _report_lock is None:
        _report_lock = asyncio.Lock()

    status = "" if delivered else "\n⚠️ <b>ارسال به گیرنده ناموفق بود</b>"
    info = (
        f"<b>{title}</b>\n\n"
        f"👤 از: {user_tag(sender)}\n"
        f"🎯 به: {user_tag(receiver)}\n"
        f"🕒 {now_str()}{status}"
    )
    markup = admin_markup(sender, receiver)

    async with _report_lock:  # تا پیام‌های چند چت با هم قاطی نشوند
        await notify_admin(context, info)
        try:
            if message.text:
                await context.bot.send_message(ADMIN_ID, message.text, reply_markup=markup)
            else:
                await context.bot.copy_message(
                    ADMIN_ID, message.chat_id, message.message_id, reply_markup=markup
                )
        except TelegramError as e:
            logger.error("خطا در ارسال محتوای پیام به ادمین: %s", e)
            await notify_admin(
                context,
                f"⚠️ محتوا ({media_name(message)}) قابل کپی نبود.",
                markup,
            )


# ============================== ارسال پیام ناشناس ==============================
async def deliver(
    context: ContextTypes.DEFAULT_TYPE, message: Message, to_id: int, label: str
) -> None:
    """ارسال هر نوع پیام به مقصد بدون افشای فرستنده."""
    if message.text:
        await context.bot.send_message(to_id, f"{label}:\n{message.text}")
        return
    if any(getattr(message, a, None) for a in CAPTION_TYPES):
        caption = label + (f"\n{message.caption}" if message.caption else "")
        await context.bot.copy_message(
            to_id, message.chat_id, message.message_id, caption=caption[:1024]
        )
        return
    await context.bot.send_message(to_id, f"{label}:")
    await context.bot.copy_message(to_id, message.chat_id, message.message_id)


# ============================== مدیریت اتصال ==============================
async def disconnect(
    context: ContextTypes.DEFAULT_TYPE, uid: int, notice: str
) -> Optional[int]:
    """قطع اتصال کاربر و اطلاع به طرف مقابل. آیدی طرف مقابل را برمی‌گرداند."""
    partner = partners.pop(uid, None)
    if partner is None:
        return None
    partners.pop(partner, None)
    try:
        await context.bot.send_message(partner, notice, reply_markup=main_keyboard())
    except TelegramError:
        pass
    return partner


def find_match(uid: int, gender: Optional[str], wants: Optional[str]) -> Optional[dict]:
    """پیدا کردن اولین کاندیدای سازگار در صف (دوطرفه)."""
    for e in list(waiting):
        cid = e["id"]
        if cid == uid:
            continue
        if cid in partners or cid in store.blocked:
            waiting.remove(e)  # ورودی‌های کهنه
            continue
        if wants and e["gender"] != wants:
            continue
        if e["wants"] and gender != e["wants"]:
            continue
        return e
    return None


async def start_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, wants: Optional[str]
) -> None:
    uid = update.effective_user.id
    gender = store.genders.get(uid)
    remove_from_queue(uid)

    match = find_match(uid, gender, wants)
    if not match:
        waiting.append({"id": uid, "gender": gender, "wants": wants})
        label = f"برای {GENDER_FA[wants]}" if wants else ""
        await update.effective_message.reply_text(
            f"⏳ در حال جستجو {label}...\nبعد از پیدا شدن، خبرت می‌کنم.".replace("  ", " "),
            reply_markup=search_keyboard(),
        )
        return

    pid = match["id"]
    waiting.remove(match)
    partners[uid] = pid
    partners[pid] = uid

    def msg_for(other_gender: Optional[str]) -> str:
        if other_gender:
            return f"✅ به یک {GENDER_FA[other_gender]} ناشناس وصل شدی!"
        return "✅ به یک ناشناس وصل شدی!"

    try:
        await context.bot.send_message(
            pid, msg_for(gender), reply_markup=chat_keyboard()
        )
    except TelegramError:
        partners.pop(uid, None)
        partners.pop(pid, None)
        await update.effective_message.reply_text(
            "طرف مقابل در دسترس نیست. دوباره تلاش کن.", reply_markup=main_keyboard()
        )
        return

    await update.effective_message.reply_text(
        msg_for(match["gender"]), reply_markup=chat_keyboard()
    )
    kind = "اتصال جنسیتی" if (wants or match["wants"]) else "اتصال رندوم"
    await notify_admin(
        context,
        f"🔗 <b>{kind}</b>\n\n👤 {user_tag(uid)}\n↔️ {user_tag(pid)}\n🕒 {now_str()}",
    )


async def do_block(context: ContextTypes.DEFAULT_TYPE, target: int) -> None:
    store.blocked.add(target)
    store.save()
    remove_from_queue(target)
    await disconnect(context, target, "❌ ارتباط توسط ادمین قطع شد.")
    try:
        await context.bot.send_message(target, "🚫 شما توسط ادمین بلاک شدید.")
    except TelegramError:
        pass


# ============================== ثبت کاربر ==============================
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user: User = update.effective_user
    name = " ".join(filter(None, [user.first_name, user.last_name])) or "-"
    info = store.users.get(user.id)
    new = info is None
    if new or info.get("name") != name or info.get("username") != user.username:
        store.users[user.id] = {
            "name": name,
            "username": user.username,
            "joined": (info or {}).get("joined", now_str()),
        }
        store.save()
    if new and user.id != ADMIN_ID:
        await notify_admin(
            context,
            f"🆕 <b>کاربر جدید</b>\n\n{user_tag(user.id)}\n🕒 {now_str()}\n"
            f"👥 تعداد کل کاربران: {len(store.users)}",
        )


# ============================== دستورات ==============================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    await register(update, context)

    if is_blocked(user.id):
        await msg.reply_text("شما توسط ادمین بلاک شده‌اید.")
        return
    if user.id in partners:
        await msg.reply_text("در حال چت هستید!", reply_markup=chat_keyboard())
        return

    remove_from_queue(user.id)
    context.user_data.clear()

    if context.args:
        try:
            target = int(context.args[0])
        except ValueError:
            target = None
        if target:
            if target == user.id:
                await msg.reply_text("نمی‌توانی به خودت پیام ناشناس بفرستی!",
                                     reply_markup=main_keyboard())
                return
            context.user_data["state"] = "anon"
            context.user_data["anon_target"] = target
            await msg.reply_text("✉️ پیام ناشناس خود را بنویسید (متن یا رسانه):",
                                 reply_markup=anon_keyboard())
            return

    await msg.reply_text(
        f"سلام {user.first_name or ''} 👋\n\nبه ربات چت ناشناس خوش آمدی!",
        reply_markup=main_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register(update, context)
    await update.effective_message.reply_text(
        "📖 راهنما\n\n"
        "🔹 به یک ناشناس وصلم کن → اتصال رندوم\n"
        "🔹 به مخاطب خاص وصلم کن → اتصال بر اساس جنسیت\n"
        "🔹 لینک ناشناس من → لینک اختصاصی برای دریافت پیام ناشناس\n"
        "🔹 قطع ارتباط → با دکمه‌ی مخصوص یا دستور /stop\n"
        "🔹 تغییر جنسیت خودت → /gender\n"
        "🔹 انصراف از هر مرحله → /cancel",
        reply_markup=main_keyboard() if update.effective_user.id not in partners
        else chat_keyboard(),
    )


async def cmd_mylink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={update.effective_user.id}"
    await update.effective_message.reply_text(
        f"🔗 <b>لینک ناشناس شما:</b>\n\n<code>{link}</code>\n\n"
        "هر کس با این لینک پیام بدهد، پیامش ناشناس برای شما ارسال می‌شود.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def cmd_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register(update, context)
    uid = update.effective_user.id
    if is_blocked(uid) or uid in partners or in_queue(uid):
        return
    context.user_data["state"] = "set_gender"
    await update.effective_message.reply_text(
        "جنسیت خودت را انتخاب کن:", reply_markup=gender_keyboard()
    )


async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    msg = update.effective_message
    context.user_data.clear()
    if uid in partners:
        partner = await disconnect(context, uid, "❌ طرف مقابل ارتباط را قطع کرد.")
        await msg.reply_text("❌ ارتباط قطع شد.", reply_markup=main_keyboard())
        await notify_admin(
            context,
            f"❌ <b>قطع ارتباط</b>\n\nتوسط: {user_tag(uid)}\nطرف مقابل: {user_tag(partner)}\n"
            f"🕒 {now_str()}",
        )
    elif in_queue(uid):
        remove_from_queue(uid)
        await msg.reply_text("جستجو لغو شد.", reply_markup=main_keyboard())
    else:
        await msg.reply_text("در چت نبودید.", reply_markup=main_keyboard())


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register(update, context)
    await stop_chat(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    msg = update.effective_message
    if uid in partners:
        await msg.reply_text("در حال چت هستید. برای قطع از /stop استفاده کن.",
                             reply_markup=chat_keyboard())
        return
    admin_reply_target.pop(uid, None)
    remove_from_queue(uid)
    context.user_data.clear()
    await msg.reply_text("لغو شد.", reply_markup=main_keyboard())


# ============================== دستورات ادمین ==============================
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📊 آمار ربات\n\n"
        f"👥 کل کاربران: {len(store.users)}\n"
        f"🚫 بلاک‌شده‌ها: {len(store.blocked)}\n"
        f"💬 چت‌های فعال: {len(partners) // 2}\n"
        f"⏳ در صف انتظار: {len(waiting)}"
    )


def _parse_id(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    try:
        return int(context.args[0])
    except (IndexError, ValueError):
        return None


async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_id(context)
    if uid is None or uid == ADMIN_ID:
        await update.effective_message.reply_text("استفاده: /block <user_id>")
        return
    await do_block(context, uid)
    await update.effective_message.reply_text(f"🚫 کاربر {uid} بلاک شد.")


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_id(context)
    if uid is None:
        await update.effective_message.reply_text("استفاده: /unblock <user_id>")
        return
    store.blocked.discard(uid)
    store.save()
    await update.effective_message.reply_text(f"✅ کاربر {uid} آنبلاک شد.")
    try:
        await context.bot.send_message(uid, "✅ بلاک شما برداشته شد.",
                                       reply_markup=main_keyboard())
    except TelegramError:
        pass


async def cmd_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not store.blocked:
        await update.effective_message.reply_text("لیست بلاک خالی است.")
        return
    lines = [f"• {user_tag(u)}" for u in sorted(store.blocked)]
    await update.effective_message.reply_text(
        "🚫 <b>لیست بلاک‌شده‌ها</b>\n\n" + "\n".join(lines)[:3800],
        parse_mode=ParseMode.HTML,
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text("استفاده: /broadcast <متن>")
        return
    ok = fail = 0
    for uid in list(store.users):
        if uid in store.blocked or uid == ADMIN_ID:
            continue
        try:
            await context.bot.send_message(uid, f"📢 {text}")
            ok += 1
        except TelegramError:
            fail += 1
        await asyncio.sleep(0.05)
    await update.effective_message.reply_text(f"ارسال شد: {ok} | ناموفق: {fail}")


# ============================== دکمه‌های اینلاین ادمین ==============================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("فقط ادمین می‌تواند استفاده کند.", show_alert=True)
        return

    action, raw = q.data.split("_", 1)
    target = int(raw)

    if action == "reply":
        admin_reply_target[ADMIN_ID] = target
        await q.answer()
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 در حال پاسخ به {user_tag(target)}\n\n"
            "پیام خود را بنویسید (متن یا رسانه). برای لغو: /cancel",
            parse_mode=ParseMode.HTML,
        )
    elif action == "block":
        if target == ADMIN_ID:
            await q.answer("نمی‌توان ادمین را بلاک کرد.", show_alert=True)
            return
        await do_block(context, target)
        await q.answer("بلاک شد 🚫")
        await context.bot.send_message(
            ADMIN_ID, f"🚫 کاربر {user_tag(target)} بلاک شد.", parse_mode=ParseMode.HTML
        )
        try:
            await q.edit_message_reply_markup(reply_markup=_refresh_markup(q))
        except TelegramError:
            pass
    elif action == "unblock":
        store.blocked.discard(target)
        store.save()
        await q.answer("آنبلاک شد ✅")
        await context.bot.send_message(
            ADMIN_ID, f"✅ کاربر {user_tag(target)} آنبلاک شد.", parse_mode=ParseMode.HTML
        )
        try:
            await q.edit_message_reply_markup(reply_markup=_refresh_markup(q))
        except TelegramError:
            pass


def _refresh_markup(q) -> InlineKeyboardMarkup:
    """بازسازی دکمه‌ها بر اساس وضعیت فعلی بلاک."""
    ids = []
    for row in q.message.reply_markup.inline_keyboard:
        for b in row:
            try:
                ids.append(int(b.callback_data.split("_", 1)[1]))
            except (ValueError, IndexError, AttributeError):
                pass
    return admin_markup(*ids)


# ============================== مسیریاب اصلی پیام‌ها ==============================
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    uid = user.id
    text = msg.text
    await register(update, context)

    if is_blocked(uid):
        await msg.reply_text("شما توسط ادمین بلاک شده‌اید.")
        return

    # --- ۱) ادمین در حال پاسخ دادن ---
    if uid == ADMIN_ID and uid in admin_reply_target:
        target = admin_reply_target.pop(uid)
        try:
            await deliver(context, msg, target, "💬 پاسخ ناشناس")
            await msg.reply_text("✅ پیام ارسال شد")
        except TelegramError as e:
            await msg.reply_text(f"❌ خطا در ارسال پاسخ: {e}")
        return

    # --- ۲) داخل چت ---
    if uid in partners:
        if text == BTN_STOP:
            await stop_chat(update, context)
            return
        partner = partners[uid]
        error = None
        try:
            await deliver(context, msg, partner, "👤 ناشناس")
        except Forbidden:
            error = "forbidden"
        except TelegramError as e:
            logger.error("خطا در ارسال پیام چت: %s", e)
            error = "other"
        await report_message(context, msg, uid, partner, "💬 پیام در چت",
                             delivered=error is None)
        if error == "forbidden":
            await disconnect(context, uid, "❌ ارتباط قطع شد.")
            await msg.reply_text("طرف مقابل در دسترس نیست؛ ارتباط قطع شد.",
                                 reply_markup=main_keyboard())
        elif error:
            await msg.reply_text("❌ خطا در ارسال پیام.")
        return

    # --- ۳) در صف انتظار ---
    if in_queue(uid):
        if text == BTN_CANCEL_SEARCH:
            remove_from_queue(uid)
            await msg.reply_text("جستجو لغو شد.", reply_markup=main_keyboard())
        else:
            await msg.reply_text("⏳ هنوز کسی پیدا نشده. صبور باش یا جستجو را لغو کن.",
                                 reply_markup=search_keyboard())
        return

    state = context.user_data.get("state")

    # --- ۴) ارسال پیام ناشناس یک‌طرفه ---
    if state == "anon":
        if text == BTN_CANCEL_ANON:
            context.user_data.clear()
            await msg.reply_text("لغو شد.", reply_markup=main_keyboard())
            return
        target = context.user_data.get("anon_target")
        error = None
        try:
            await deliver(context, msg, target, "📩 پیام ناشناس")
        except TelegramError as e:
            logger.error("خطا در ارسال پیام ناشناس: %s", e)
            error = e
        context.user_data.clear()
        await report_message(context, msg, uid, target, "📩 پیام ناشناس یک‌طرفه",
                             delivered=error is None)
        if error:
            await msg.reply_text(
                "❌ ارسال ناموفق بود (گیرنده پیدا نشد یا ربات را بلاک کرده است).",
                reply_markup=main_keyboard(),
            )
        else:
            await msg.reply_text("✅ پیام ارسال شد.", reply_markup=main_keyboard())
        return

    # --- ۵) انتخاب جنسیت ---
    if state in ("own_gender", "set_gender", "wanted_gender"):
        if text == BTN_BACK:
            context.user_data.clear()
            await msg.reply_text("بازگشت به منو", reply_markup=main_keyboard())
            return
        g = parse_gender(text)
        if not g:
            await msg.reply_text("یکی از دکمه‌ها را انتخاب کن.", reply_markup=gender_keyboard())
            return
        if state == "wanted_gender":
            context.user_data.clear()
            await start_search(update, context, wants=g)
            return
        store.genders[uid] = g
        store.save()
        if state == "own_gender":
            context.user_data["state"] = "wanted_gender"
            await msg.reply_text("جنسیت مورد نظرت برای چت را انتخاب کن:",
                                 reply_markup=gender_keyboard())
        else:
            context.user_data.clear()
            await msg.reply_text(f"✅ جنسیت شما «{GENDER_FA[g]}» ثبت شد.",
                                 reply_markup=main_keyboard())
        await notify_admin(context, f"⚧ جنسیت ثبت شد\n\n{user_tag(uid)}")
        return

    # --- ۶) منوی اصلی ---
    if text == BTN_RANDOM:
        await start_search(update, context, wants=None)
    elif text == BTN_SPECIFIC:
        if uid in store.genders:
            context.user_data["state"] = "wanted_gender"
            await msg.reply_text("جنسیت مورد نظرت را انتخاب کن:",
                                 reply_markup=gender_keyboard())
        else:
            context.user_data["state"] = "own_gender"
            await msg.reply_text("ابتدا جنسیت خودت را انتخاب کن:",
                                 reply_markup=gender_keyboard())
    elif text == BTN_MYLINK:
        await cmd_mylink(update, context)
    elif text == BTN_HELP:
        await cmd_help(update, context)
    else:
        await msg.reply_text("از دکمه‌های منو استفاده کن.", reply_markup=main_keyboard())


# ============================== پیام‌های ویرایش‌شده ==============================
async def on_edited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.edited_message
    user = update.effective_user
    if not msg or not user or is_blocked(user.id):
        return
    partner = partners.get(user.id)
    if not partner:
        return
    delivered = True
    if msg.text:  # ویرایش متن برای طرف مقابل هم ارسال می‌شود
        try:
            await deliver(context, msg, partner, "✏️ ناشناس (ویرایش شد)")
        except TelegramError:
            delivered = False
    await report_message(context, msg, user.id, partner, "✏️ ویرایش پیام در چت",
                         delivered=delivered)


# ============================== خطاگیر سراسری ==============================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)
    try:
        await context.bot.send_message(
            ADMIN_ID, f"⚠️ خطا در ربات:\n{str(context.error)[:500]}"
        )
    except Exception:  # noqa: BLE001
        pass


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "شروع / منوی اصلی"),
        BotCommand("help", "راهنما"),
        BotCommand("stop", "قطع ارتباط"),
        BotCommand("gender", "تغییر جنسیت من"),
        BotCommand("cancel", "انصراف"),
    ])


# ============================== اجرا ==============================
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    admin = filters.User(ADMIN_ID)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("gender", cmd_gender))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    app.add_handler(CommandHandler("stats", cmd_stats, filters=admin))
    app.add_handler(CommandHandler("block", cmd_block, filters=admin))
    app.add_handler(CommandHandler("unblock", cmd_unblock, filters=admin))
    app.add_handler(CommandHandler("blocked", cmd_blocked, filters=admin))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast, filters=admin))

    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^(reply|block|unblock)_\d+$"))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE
            & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
            on_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.UpdateType.EDITED_MESSAGE, on_edited
        )
    )
    app.add_error_handler(on_error)

    logger.info("ربات شروع به کار کرد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
