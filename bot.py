"""
بات تلگرام «مشاوره تخصصی نیما افشارنادری»
t.me/NimaAfsharnaderiBot

- کاربر موضوع و نوع مشاوره را انتخاب می‌کند و فرم کوتاهی پر می‌کند.
- اولین درخواست هر کاربر رایگان است؛ از دومی به بعد کارت‌به‌کارت با تأیید دستی.
- همه‌ی درخواست‌ها به گروه خصوصی ادمین می‌آید؛ با Reply روی پیام، جواب به کاربر می‌رسد.
"""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime
from html import escape

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------------------------------------------------------------- تنظیمات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0") or 0)
BOT_TITLE = os.getenv("BOT_TITLE", "مشاوره تخصصی نیما افشارنادری")
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
PRICE_TEXT = os.getenv("PRICE_TEXT", "")
PROXY = os.getenv("PROXY", "").strip()
DB_PATH = os.getenv("DB_PATH", "consult.db")
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(BASE_DIR, DB_PATH)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
MAX_PHOTOS = 5

TOPICS = {
    "menu": "منو و مهندسی منو",
    "recipe": "دستور پخت و فرمولاسیون",
    "launch": "راه‌اندازی رستوران / فست‌فود",
    "cost": "بهای تمام‌شده و قیمت‌گذاری",
    "kitchen": "آشپزخانه، تولید و پرسنل",
    "other": "سایر موارد",
}
CTYPES = {
    "text": "متنی / ویس",
    "call": "تماس تلفنی",
}
STATUS_FA = {
    "awaiting_payment": "در انتظار پرداخت",
    "receipt_sent": "رسید ارسال شده",
    "open": "باز",
    "answered": "پاسخ داده شده",
    "closed": "بسته",
    "rejected": "رد شده",
}

BTN_NEW = "📝 درخواست مشاوره جدید"
BTN_MINE = "📋 درخواست‌های من"
BTN_HELP = "ℹ️ راهنما"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consult-bot")


# ---------------------------------------------------------------- دیتابیس
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                source TEXT,
                free_used INTEGER DEFAULT 0,
                blocked INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                topic TEXT,
                ctype TEXT,
                business TEXT,
                city TEXT,
                description TEXT,
                photos TEXT,
                call_time TEXT,
                is_free INTEGER,
                status TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS msgmap (
                admin_msg_id INTEGER PRIMARY KEY,
                request_id INTEGER,
                user_id INTEGER
            );
            """
        )


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def upsert_user(m: Message, source: str | None = None) -> None:
    u = m.from_user
    with db() as c:
        row = c.execute("SELECT user_id FROM users WHERE user_id=?", (u.id,)).fetchone()
        if row:
            c.execute(
                "UPDATE users SET username=?, full_name=?, blocked=0 WHERE user_id=?",
                (u.username, u.full_name, u.id),
            )
        else:
            c.execute(
                "INSERT INTO users (user_id, username, full_name, source, created_at) VALUES (?,?,?,?,?)",
                (u.id, u.username, u.full_name, source or "direct", now()),
            )


def free_available(user_id: int) -> bool:
    with db() as c:
        row = c.execute("SELECT free_used FROM users WHERE user_id=?", (user_id,)).fetchone()
    return not row or not row["free_used"]


def set_free_used(user_id: int, used: bool) -> None:
    with db() as c:
        c.execute("UPDATE users SET free_used=? WHERE user_id=?", (1 if used else 0, user_id))


def create_request(user_id: int, data: dict, is_free: bool, status: str) -> int:
    with db() as c:
        cur = c.execute(
            """INSERT INTO requests (user_id, topic, ctype, business, city, description,
               photos, call_time, is_free, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                data.get("topic"),
                data.get("ctype"),
                data.get("business"),
                data.get("city"),
                data.get("description"),
                json.dumps(data.get("photos", [])),
                data.get("call_time"),
                1 if is_free else 0,
                status,
                now(),
            ),
        )
        return cur.lastrowid


def get_request(rid: int):
    with db() as c:
        return c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()


def set_status(rid: int, status: str) -> None:
    with db() as c:
        c.execute("UPDATE requests SET status=? WHERE id=?", (status, rid))


def map_msg(admin_msg_id: int, rid: int, user_id: int) -> None:
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO msgmap (admin_msg_id, request_id, user_id) VALUES (?,?,?)",
            (admin_msg_id, rid, user_id),
        )


def lookup_msg(admin_msg_id: int):
    with db() as c:
        return c.execute("SELECT * FROM msgmap WHERE admin_msg_id=?", (admin_msg_id,)).fetchone()


def latest_active_request(user_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM requests WHERE user_id=? AND status IN ('open','answered') ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()


# ---------------------------------------------------------------- قالب پیام‌ها
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_NEW)], [KeyboardButton(text=BTN_MINE), KeyboardButton(text=BTN_HELP)]],
        resize_keyboard=True,
    )


def welcome_text() -> str:
    return (
        f"سلام! به <b>{escape(BOT_TITLE)}</b> خوش آمدید 🌿\n\n"
        "اینجا می‌توانید درباره‌ی رستوران، فست‌فود، منو، دستور پخت و تولید مشاوره بگیرید.\n\n"
        "🎁 <b>اولین مشاوره‌ی شما رایگان است.</b>\n\n"
        f"برای شروع روی «{BTN_NEW}» بزنید."
    )


def help_text() -> str:
    lines = [
        f"<b>راهنمای {escape(BOT_TITLE)}</b>\n",
        "۱. روی «درخواست مشاوره جدید» بزنید.",
        "۲. موضوع و نوع مشاوره (متنی/ویس یا تماس) را انتخاب کنید.",
        "۳. به چند سؤال کوتاه جواب بدهید و در صورت نیاز عکس بفرستید.",
        "۴. درخواست را تأیید کنید؛ پاسخ همین‌جا برایتان می‌آید.\n",
        "🎁 اولین درخواست رایگان است.",
    ]
    if PRICE_TEXT:
        lines.append(f"💳 هزینه‌ی درخواست‌های بعدی: {escape(PRICE_TEXT)}")
    lines.append("\nبعد از ثبت درخواست، هر پیامی بفرستید به همان درخواست اضافه می‌شود.")
    lines.append("برای لغو فرم در هر مرحله: /cancel")
    return "\n".join(lines)


def request_summary(data: dict, rid: int | None = None, user=None, is_free: bool | None = None) -> str:
    head = f"📨 <b>درخواست #{rid}</b>\n" if rid else "🧾 <b>پیش‌نمایش درخواست</b>\n"
    parts = [head]
    if user is not None:
        uname = f"@{user['username']}" if user["username"] else "—"
        parts.append(f"👤 {escape(user['full_name'] or '')} | {escape(uname)} | <code>{user['user_id']}</code>")
        parts.append(f"🔗 منبع: {escape(user['source'] or 'direct')}")
    if is_free is not None:
        parts.append("🎁 رایگان" if is_free else "💳 پولی (پرداخت تأیید شده)")
    parts.append(f"📌 موضوع: {escape(TOPICS.get(data.get('topic'), '—'))}")
    parts.append(f"💬 نوع مشاوره: {escape(CTYPES.get(data.get('ctype'), '—'))}")
    parts.append(f"🏪 کسب‌وکار: {escape(data.get('business') or '—')}")
    parts.append(f"📍 شهر: {escape(data.get('city') or '—')}")
    if data.get("ctype") == "call":
        parts.append(f"⏰ زمان مناسب تماس: {escape(data.get('call_time') or '—')}")
    photos = data.get("photos") or []
    parts.append(f"🖼 عکس‌ها: {len(photos)}")
    parts.append(f"\n📝 شرح:\n{escape(data.get('description') or '—')}")
    return "\n".join(parts)


def row_to_data(r) -> dict:
    return {
        "topic": r["topic"],
        "ctype": r["ctype"],
        "business": r["business"],
        "city": r["city"],
        "description": r["description"],
        "photos": json.loads(r["photos"] or "[]"),
        "call_time": r["call_time"],
    }


def get_user(user_id: int):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def is_admin_chat(m: Message) -> bool:
    return ADMIN_GROUP_ID != 0 and m.chat.id == ADMIN_GROUP_ID


# ---------------------------------------------------------------- وضعیت‌های فرم
class Form(StatesGroup):
    topic = State()
    ctype = State()
    business = State()
    city = State()
    description = State()
    photos = State()
    call_time = State()
    confirm = State()
    receipt = State()


router = Router()
admin = Router()
admin.message.filter(lambda m: is_admin_chat(m))


# ---------------------------------------------------------------- ارسال درخواست به ادمین
async def send_request_to_admins(bot: Bot, rid: int) -> None:
    r = get_request(rid)
    data = row_to_data(r)
    user = get_user(r["user_id"])
    kb = InlineKeyboardBuilder()
    if r["is_free"]:
        kb.button(text="❌ رد درخواست", callback_data=f"rej:{rid}")
    kb.button(text="✅ بستن درخواست", callback_data=f"close:{rid}")
    text = request_summary(data, rid=rid, user=user, is_free=bool(r["is_free"]))
    text += "\n\n↩️ برای پاسخ، روی همین پیام Reply بزنید."
    sent = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=kb.as_markup())
    map_msg(sent.message_id, rid, r["user_id"])
    photos = data["photos"]
    if photos:
        media = [InputMediaPhoto(media=p) for p in photos[:10]]
        msgs = await bot.send_media_group(ADMIN_GROUP_ID, media, reply_to_message_id=sent.message_id)
        for mm in msgs:
            map_msg(mm.message_id, rid, r["user_id"])


# ---------------------------------------------------------------- دستورهای عمومی
@router.message(Command("id"))
async def cmd_id(m: Message):
    await m.reply(f"Chat ID: <code>{m.chat.id}</code>")


@admin.message(Command("list"))
async def cmd_list(m: Message):
    with db() as c:
        rows = c.execute(
            "SELECT r.*, u.full_name FROM requests r LEFT JOIN users u ON u.user_id=r.user_id "
            "WHERE r.status NOT IN ('closed','rejected') ORDER BY r.id DESC LIMIT 30"
        ).fetchall()
    if not rows:
        await m.reply("درخواست بازی وجود ندارد ✅")
        return
    lines = ["<b>درخواست‌های باز:</b>\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} | {escape(r['full_name'] or '')} | {escape(TOPICS.get(r['topic'], ''))} | "
            f"{STATUS_FA.get(r['status'], r['status'])} | {'رایگان' if r['is_free'] else 'پولی'}"
        )
    lines.append("\nبرای دیدن دوباره‌ی یک درخواست: /show شماره")
    await m.reply("\n".join(lines))


@admin.message(Command("show"))
async def cmd_show(m: Message, command: CommandObject, bot: Bot):
    if not command.args or not command.args.strip().lstrip("#").isdigit():
        await m.reply("مثال: /show 12")
        return
    rid = int(command.args.strip().lstrip("#"))
    if not get_request(rid):
        await m.reply("این درخواست پیدا نشد.")
        return
    await send_request_to_admins(bot, rid)


@admin.message(Command("stats"))
async def cmd_stats(m: Message):
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        by_status = c.execute("SELECT status, COUNT(*) n FROM requests GROUP BY status").fetchall()
        free = c.execute("SELECT COUNT(*) FROM requests WHERE is_free=1 AND status!='rejected'").fetchone()[0]
        paid = c.execute(
            "SELECT COUNT(*) FROM requests WHERE is_free=0 AND status IN ('open','answered','closed')"
        ).fetchone()[0]
        sources = c.execute(
            "SELECT source, COUNT(*) n FROM users GROUP BY source ORDER BY n DESC LIMIT 10"
        ).fetchall()
    lines = [f"<b>آمار {escape(BOT_TITLE)}</b>\n", f"👥 کاربران: {users}", f"🎁 درخواست رایگان: {free}", f"💳 درخواست پولی تأییدشده: {paid}\n"]
    lines.append("<b>وضعیت درخواست‌ها:</b>")
    for r in by_status:
        lines.append(f"• {STATUS_FA.get(r['status'], r['status'])}: {r['n']}")
    lines.append("\n<b>منبع ورود کاربران:</b>")
    for r in sources:
        lines.append(f"• {escape(r['source'] or 'direct')}: {r['n']}")
    await m.reply("\n".join(lines))


@admin.message(Command("broadcast"))
async def cmd_broadcast(m: Message, bot: Bot):
    if not m.reply_to_message:
        await m.reply("روی پیامی که می‌خواهید برای همه ارسال شود Reply بزنید و بنویسید /broadcast")
        return
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT user_id FROM users WHERE blocked=0").fetchall()]
    note = await m.reply(f"در حال ارسال برای {len(ids)} نفر…")
    ok = fail = 0
    for uid in ids:
        try:
            await bot.copy_message(uid, m.chat.id, m.reply_to_message.message_id)
            ok += 1
        except Exception:
            fail += 1
            with db() as c:
                c.execute("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
        await asyncio.sleep(0.05)
    await note.edit_text(f"ارسال همگانی تمام شد ✅\nموفق: {ok} | ناموفق: {fail}")


@admin.message(F.reply_to_message)
async def admin_reply(m: Message, bot: Bot):
    if m.text and m.text.startswith("/"):
        return
    link = lookup_msg(m.reply_to_message.message_id)
    if not link:
        return
    try:
        await bot.copy_message(link["user_id"], m.chat.id, m.message_id)
    except Exception as e:
        await m.reply(f"⚠️ ارسال نشد: {escape(str(e))}")
        return
    map_msg(m.message_id, link["request_id"], link["user_id"])
    r = get_request(link["request_id"])
    if r and r["status"] == "open":
        set_status(r["id"], "answered")
    await m.reply(f"✅ برای کاربر درخواست #{link['request_id']} ارسال شد.")


# ---------------------------------------------------------------- دکمه‌های ادمین
@router.callback_query(F.data.startswith(("rej:", "close:", "pay_ok:", "pay_no:")))
async def admin_buttons(cq: CallbackQuery, bot: Bot):
    if cq.message.chat.id != ADMIN_GROUP_ID:
        await cq.answer("دسترسی ندارید.", show_alert=True)
        return
    action, rid = cq.data.split(":")
    rid = int(rid)
    r = get_request(rid)
    if not r:
        await cq.answer("درخواست پیدا نشد.", show_alert=True)
        return
    by = cq.from_user.full_name

    if action == "rej":
        if r["status"] in ("closed", "rejected"):
            await cq.answer("این درخواست قبلاً بسته شده.")
            return
        set_status(rid, "rejected")
        if r["is_free"]:
            set_free_used(r["user_id"], False)
        await safe_send(bot, r["user_id"],
                        f"درخواست #{rid} شما پذیرفته نشد. 🙏\n"
                        + ("سهمیه‌ی مشاوره‌ی رایگان شما برگشت و می‌توانید درخواست تازه‌ای ثبت کنید." if r["is_free"] else ""))
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"❌ درخواست #{rid} توسط {escape(by)} رد شد.")

    elif action == "close":
        set_status(rid, "closed")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"✅ درخواست #{rid} توسط {escape(by)} بسته شد.")

    elif action == "pay_ok":
        if r["status"] != "receipt_sent":
            await cq.answer("این رسید قبلاً بررسی شده.")
            return
        set_status(rid, "open")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"💳 پرداخت درخواست #{rid} توسط {escape(by)} تأیید شد.")
        await send_request_to_admins(bot, rid)
        await safe_send(bot, r["user_id"],
                        f"✅ پرداخت شما تأیید شد و درخواست #{rid} ثبت شد.\nپاسخ همین‌جا برایتان ارسال می‌شود.")

    elif action == "pay_no":
        if r["status"] != "receipt_sent":
            await cq.answer("این رسید قبلاً بررسی شده.")
            return
        set_status(rid, "awaiting_payment")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"⛔️ رسید درخواست #{rid} توسط {escape(by)} رد شد.")
        await safe_send(bot, r["user_id"],
                        f"رسید پرداخت درخواست #{rid} تأیید نشد. ⛔️\n"
                        "اگر فکر می‌کنید اشتباهی رخ داده، عکس رسید درست را همین‌جا بفرستید.")
        # اجازه‌ی ارسال دوباره‌ی رسید
        await set_user_state_receipt(bot, r["user_id"], rid)

    await cq.answer()


async def safe_send(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        log.warning("send to %s failed: %s", user_id, e)


_dp_ref: dict = {}


async def set_user_state_receipt(bot: Bot, user_id: int, rid: int) -> None:
    dp: Dispatcher = _dp_ref["dp"]
    ctx = dp.fsm.get_context(bot=bot, chat_id=user_id, user_id=user_id)
    await ctx.set_state(Form.receipt)
    await ctx.update_data(receipt_rid=rid)


# ---------------------------------------------------------------- گفتگو با کاربر
private = F.chat.type == ChatType.PRIVATE


@router.message(CommandStart(), private)
async def cmd_start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    upsert_user(m, source=(command.args or None))
    await m.answer(welcome_text(), reply_markup=main_kb())


@router.message(Command("help"), private)
@router.message(F.text == BTN_HELP, private)
async def cmd_help(m: Message):
    await m.answer(help_text(), reply_markup=main_kb())


@router.message(Command("cancel"), private)
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("فرم لغو شد.", reply_markup=main_kb())


@router.message(F.text == BTN_MINE, private)
async def my_requests(m: Message):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM requests WHERE user_id=? ORDER BY id DESC LIMIT 10", (m.from_user.id,)
        ).fetchall()
    if not rows:
        await m.answer("هنوز درخواستی ثبت نکرده‌اید.")
        return
    lines = ["<b>درخواست‌های شما:</b>\n"]
    for r in rows:
        lines.append(f"#{r['id']} | {escape(TOPICS.get(r['topic'], ''))} | {STATUS_FA.get(r['status'], r['status'])} | {r['created_at']}")
    await m.answer("\n".join(lines))


@router.message(Command("new"), private)
@router.message(F.text == BTN_NEW, private)
async def new_request(m: Message, state: FSMContext):
    upsert_user(m)
    await start_form(m, state)


async def start_form(m: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for k, v in TOPICS.items():
        kb.button(text=v, callback_data=f"topic:{k}")
    kb.adjust(1)
    await state.set_state(Form.topic)
    await m.answer("موضوع مشاوره را انتخاب کنید:", reply_markup=kb.as_markup())


@router.callback_query(Form.topic, F.data.startswith("topic:"))
async def pick_topic(cq: CallbackQuery, state: FSMContext):
    key = cq.data.split(":", 1)[1]
    await state.update_data(topic=key, photos=[])
    kb = InlineKeyboardBuilder()
    for k, v in CTYPES.items():
        kb.button(text=v, callback_data=f"ctype:{k}")
    kb.adjust(2)
    await state.set_state(Form.ctype)
    await cq.message.edit_text(f"موضوع: <b>{escape(TOPICS[key])}</b>\n\nنوع مشاوره را انتخاب کنید:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(Form.ctype, F.data.startswith("ctype:"))
async def pick_ctype(cq: CallbackQuery, state: FSMContext):
    key = cq.data.split(":", 1)[1]
    await state.update_data(ctype=key)
    await state.set_state(Form.business)
    await cq.message.edit_text(f"نوع مشاوره: <b>{escape(CTYPES[key])}</b>")
    await cq.message.answer("کسب‌وکار شما چیست؟\n(مثلاً: فست‌فود ۴۰ متری، رستوران ایرانی، کترینگ، هنوز راه‌اندازی نشده…)")
    await cq.answer()


@router.message(Form.business, F.text)
async def got_business(m: Message, state: FSMContext):
    await state.update_data(business=m.text[:500])
    await state.set_state(Form.city)
    await m.answer("در کدام شهر هستید؟")


@router.message(Form.city, F.text)
async def got_city(m: Message, state: FSMContext):
    await state.update_data(city=m.text[:200])
    await state.set_state(Form.description)
    await m.answer("مشکل یا سؤالتان را کامل شرح دهید.\nهرچه دقیق‌تر بنویسید، جواب دقیق‌تری می‌گیرید.")


@router.message(Form.description, F.text)
async def got_description(m: Message, state: FSMContext):
    await state.update_data(description=m.text[:3500])
    await state.set_state(Form.photos)
    kb = InlineKeyboardBuilder()
    kb.button(text="بدون عکس، ادامه ➡️", callback_data="photos_done")
    await m.answer(
        f"اگر عکسی دارید (منو، غذا، آشپزخانه، فاکتور…) تا {MAX_PHOTOS} عکس بفرستید.\n"
        "بعد از ارسال عکس‌ها دکمه‌ی «ادامه» را بزنید.",
        reply_markup=kb.as_markup(),
    )


@router.message(Form.description)
@router.message(Form.business)
@router.message(Form.city)
async def need_text(m: Message):
    await m.answer("لطفاً جواب را به‌صورت متن بنویسید. (برای لغو: /cancel)")


@router.message(Form.photos, F.photo)
async def got_photo(m: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await m.answer(f"حداکثر {MAX_PHOTOS} عکس قابل ارسال است.")
        return
    photos.append(m.photo[-1].file_id)
    last_group = data.get("last_group")
    await state.update_data(photos=photos, last_group=m.media_group_id)
    if m.media_group_id and m.media_group_id == last_group:
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="ادامه ➡️", callback_data="photos_done")
    await m.answer("عکس دریافت شد ✅ اگر عکس دیگری ندارید «ادامه» را بزنید.", reply_markup=kb.as_markup())


@router.message(Form.photos)
async def photos_other(m: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="ادامه ➡️", callback_data="photos_done")
    await m.answer("در این مرحله فقط عکس بفرستید یا «ادامه» را بزنید.", reply_markup=kb.as_markup())


@router.callback_query(Form.photos, F.data == "photos_done")
async def photos_done(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cq.message.edit_reply_markup(reply_markup=None)
    if data.get("ctype") == "call":
        await state.set_state(Form.call_time)
        await cq.message.answer("چه روزها و ساعت‌هایی برای تماس مناسب است؟ شماره‌ی تماس را هم بنویسید.")
    else:
        await show_preview(cq.message, state)
    await cq.answer()


@router.message(Form.call_time, F.text)
async def got_call_time(m: Message, state: FSMContext):
    await state.update_data(call_time=m.text[:500])
    await show_preview(m, state)


@router.message(Form.call_time)
async def call_time_need_text(m: Message):
    await m.answer("لطفاً زمان تماس را به‌صورت متن بنویسید. (برای لغو: /cancel)")


async def show_preview(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.confirm)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ ثبت درخواست", callback_data="confirm")
    kb.button(text="🔄 از اول", callback_data="restart")
    kb.button(text="✖️ لغو", callback_data="cancel")
    kb.adjust(1, 2)
    await m.answer(request_summary(data), reply_markup=kb.as_markup())


@router.callback_query(Form.confirm, F.data == "restart")
async def restart(cq: CallbackQuery, state: FSMContext):
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.answer()
    await start_form(cq.message, state)


@router.callback_query(F.data == "cancel")
async def cancel_cb(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("لغو شد.", reply_markup=main_kb())
    await cq.answer()


@router.callback_query(Form.confirm, F.data == "confirm")
async def confirm(cq: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = cq.from_user.id
    await cq.message.edit_reply_markup(reply_markup=None)

    if free_available(uid):
        rid = create_request(uid, data, is_free=True, status="open")
        set_free_used(uid, True)
        await state.clear()
        await send_request_to_admins(bot, rid)
        await cq.message.answer(
            f"✅ درخواست #{rid} ثبت شد (مشاوره‌ی رایگان 🎁).\n"
            "پاسخ همین‌جا برایتان ارسال می‌شود. اگر توضیح بیشتری دارید، همین‌جا بفرستید.",
            reply_markup=main_kb(),
        )
    else:
        rid = create_request(uid, data, is_free=False, status="awaiting_payment")
        await state.clear()
        await state.set_state(Form.receipt)
        await state.update_data(receipt_rid=rid)
        pay = [f"🧾 درخواست #{rid} ساخته شد.\n", "مشاوره‌ی رایگان شما قبلاً استفاده شده است."]
        if PRICE_TEXT:
            pay.append(f"هزینه: <b>{escape(PRICE_TEXT)}</b>")
        pay.append(f"\nلطفاً مبلغ را به این کارت واریز کنید:\n<code>{escape(CARD_NUMBER)}</code>")
        if CARD_HOLDER:
            pay.append(f"به نام: {escape(CARD_HOLDER)}")
        pay.append("\nسپس <b>عکس رسید</b> را همین‌جا بفرستید. (برای لغو: /cancel)")
        await cq.message.answer("\n".join(pay))
    await cq.answer()


@router.message(Form.receipt, F.photo | F.document)
async def got_receipt(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    rid = data.get("receipt_rid")
    r = get_request(rid) if rid else None
    if not r:
        await state.clear()
        await m.answer("درخواستی برای پرداخت پیدا نشد. از منو دوباره شروع کنید.", reply_markup=main_kb())
        return
    set_status(rid, "receipt_sent")
    user = get_user(r["user_id"])
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تأیید پرداخت", callback_data=f"pay_ok:{rid}")
    kb.button(text="⛔️ رد رسید", callback_data=f"pay_no:{rid}")
    caption = "💳 <b>رسید پرداخت</b>\n\n" + request_summary(row_to_data(r), rid=rid, user=user)
    if len(caption) > 1000:
        caption = caption[:990] + "…"
    sent = await bot.copy_message(ADMIN_GROUP_ID, m.chat.id, m.message_id, caption=caption,
                                  parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
    map_msg(sent.message_id, rid, r["user_id"])
    await state.clear()
    await m.answer("رسید دریافت شد 🙏 بعد از بررسی، نتیجه را خبر می‌دهیم.", reply_markup=main_kb())


@router.message(Form.receipt)
async def receipt_other(m: Message):
    await m.answer("لطفاً عکس رسید پرداخت را بفرستید. (برای لغو: /cancel)")


# پیام‌های آزاد کاربر بعد از ثبت درخواست → به گروه ادمین
@router.message(private, StateFilter(None))
async def followup(m: Message, bot: Bot):
    if m.text and m.text.startswith("/"):
        await m.answer("دستور ناشناخته. از منوی پایین استفاده کنید.", reply_markup=main_kb())
        return
    upsert_user(m)
    r = latest_active_request(m.from_user.id)
    if not r:
        await m.answer(f"برای گرفتن مشاوره روی «{BTN_NEW}» بزنید.", reply_markup=main_kb())
        return
    head = await bot.send_message(
        ADMIN_GROUP_ID,
        f"💬 پیام تکمیلی از {escape(m.from_user.full_name)} برای درخواست #{r['id']}\n↩️ برای پاسخ روی پیام زیر Reply بزنید.",
    )
    map_msg(head.message_id, r["id"], r["user_id"])
    copied = await bot.copy_message(ADMIN_GROUP_ID, m.chat.id, m.message_id)
    map_msg(copied.message_id, r["id"], r["user_id"])
    await m.answer("پیام شما به مشاور رسید ✅")


# ---------------------------------------------------------------- اجرا
def make_bot() -> Bot:
    session = AiohttpSession(proxy=PROXY) if PROXY else None
    return Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def make_dispatcher(storage=None) -> Dispatcher:
    dp = Dispatcher(storage=storage or MemoryStorage())
    _dp_ref["dp"] = dp
    dp.include_router(admin)
    dp.include_router(router)
    return dp


async def main():
    """اجرا روی VPS با polling. (برای PythonAnywhere از flask_app.py استفاده می‌شود.)"""
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN در فایل .env تنظیم نشده است.")
    if not ADMIN_GROUP_ID:
        log.warning("ADMIN_GROUP_ID تنظیم نشده. بات را به گروه ادمین اضافه کنید و /id بزنید.")
    init_db()
    bot = make_bot()
    dp = make_dispatcher()
    await bot.delete_webhook(drop_pending_updates=False)
    me = await bot.get_me()
    log.info("Bot @%s started", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
