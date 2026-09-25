"""
بات تلگرام «مشاوره تخصصی نیما افشارنادری»
t.me/NimaAfsharnaderiBot

- پیش‌شرط: عضویت در کانال‌های مشخص‌شده + ثبت شماره تماس.
- کاربر (اختیاری) موضوع را انتخاب می‌کند و بعد هرچه لازم است می‌فرستد: متن، ویس، عکس، ویدیو، فایل.
- مشاوره‌ی اولیه رایگان است؛ هر جا مشاور لازم بداند با دستور /pay مبلغ را اعلام می‌کند
  و کاربر کارت‌به‌کارت می‌کند و رسید می‌فرستد (تأیید دستی).
- همه‌چیز به گروه خصوصی ادمین می‌آید (همراه با شماره تماس)؛ با Reply روی پیام، جواب به کاربر می‌رسد.
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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
# کانال‌هایی که عضویت در آن‌ها لازم است (بات باید در هر کدام ادمین باشد)
REQUIRED_CHANNELS = [
    c.strip() for c in os.getenv("REQUIRED_CHANNELS", "@nimasdiner,@nimaafsharnaderi").split(",") if c.strip()
]
MAX_MSGS = 30

TOPICS = {
    "menu": "منو و مهندسی منو",
    "recipe": "دستور پخت و فرمولاسیون",
    "launch": "راه‌اندازی رستوران / فست‌فود",
    "cost": "بهای تمام‌شده و قیمت‌گذاری",
    "kitchen": "آشپزخانه، تولید و پرسنل",
    "other": "سایر موارد",
}
STATUS_FA = {
    "awaiting_payment": "در انتظار پرداخت",
    "receipt_sent": "رسید ارسال شده",
    "open": "باز",
    "answered": "پاسخ داده شده",
    "closed": "بسته",
    "rejected": "رد شده",
}

BTN_NEW = "🎙 شروع مشاوره"
BTN_MINE = "📋 درخواست‌های من"
BTN_HELP = "ℹ️ راهنما"
BTN_SEND = "✅ ارسال برای مشاور"
BTN_CANCEL = "✖️ لغو"
BTN_PHONE = "📱 ارسال شماره تماس"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consult-bot")


# ---------------------------------------------------------------- دیتابیس
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column(c, table: str, col: str, decl: str) -> None:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


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
                is_free INTEGER,
                status TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                user_id INTEGER,
                amount TEXT,
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
        _add_column(c, "users", "phone", "TEXT")
        _add_column(c, "requests", "msgs", "TEXT")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def upsert_user(u, source: str | None = None) -> None:
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


def get_user(user_id: int):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def set_phone(user_id: int, phone: str) -> None:
    with db() as c:
        c.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))


def free_available(user_id: int) -> bool:
    u = get_user(user_id)
    return not u or not u["free_used"]


def set_free_used(user_id: int, used: bool) -> None:
    with db() as c:
        c.execute("UPDATE users SET free_used=? WHERE user_id=?", (1 if used else 0, user_id))


def create_request(user_id: int, topic: str | None, msgs: list, is_free: bool, status: str) -> int:
    with db() as c:
        cur = c.execute(
            "INSERT INTO requests (user_id, topic, msgs, is_free, status, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, topic, json.dumps(msgs), 1 if is_free else 0, status, now()),
        )
        return cur.lastrowid


def create_payment(rid: int, user_id: int, amount: str) -> int:
    with db() as c:
        cur = c.execute(
            "INSERT INTO payments (request_id, user_id, amount, status, created_at) VALUES (?,?,?,?,?)",
            (rid, user_id, amount, "pending", now()),
        )
        return cur.lastrowid


def get_payment(pid: int):
    with db() as c:
        return c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()


def set_payment_status(pid: int, status: str) -> None:
    with db() as c:
        c.execute("UPDATE payments SET status=? WHERE id=?", (status, pid))


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


# ---------------------------------------------------------------- کیبوردها و متن‌ها
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_NEW)], [KeyboardButton(text=BTN_MINE), KeyboardButton(text=BTN_HELP)]],
        resize_keyboard=True,
    )


def collect_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SEND)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def channel_link(ch: str) -> str:
    return f"https://t.me/{ch.lstrip('@')}" if ch.startswith("@") else ch


def join_kb():
    kb = InlineKeyboardBuilder()
    for ch in REQUIRED_CHANNELS:
        kb.button(text=f"📢 عضویت در {ch}", url=channel_link(ch))
    kb.button(text="✅ عضو شدم", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()


def welcome_text() -> str:
    return (
        f"سلام! به <b>{escape(BOT_TITLE)}</b> خوش آمدید 🌿\n\n"
        "اینجا می‌توانید درباره‌ی رستوران، فست‌فود، منو، دستور پخت و تولید مشاوره بگیرید؛ "
        "با متن، ویس، عکس یا ویدیو.\n\n"
        "🎁 <b>مشاوره‌ی اولیه رایگان است.</b> اگر موضوع شما به بررسی تخصصی‌تر نیاز داشته باشد، "
        "قبل از ادامه هزینه‌اش را اعلام می‌کنم و فقط با موافقت شما ادامه می‌دهیم.\n\n"
        f"برای شروع روی «{BTN_NEW}» بزنید."
    )


def help_text() -> str:
    lines = [
        f"<b>راهنمای {escape(BOT_TITLE)}</b>\n",
        f"۱. روی «{BTN_NEW}» بزنید و موضوع را انتخاب کنید.",
        "۲. سؤال یا مشکلتان را هر طور راحتید بفرستید: متن، ویس، عکس، ویدیو یا فایل.",
        f"۳. آخر کار «{BTN_SEND}» را بزنید.",
        "۴. جواب همین‌جا می‌آید و می‌توانید گفتگو را ادامه دهید.\n",
        "🎁 مشاوره‌ی اولیه رایگان است.",
        "💳 اگر موضوع به بررسی تخصصی‌تر نیاز داشته باشد، مبلغ پیش از ادامه اعلام می‌شود؛ "
        "با واریز کارت‌به‌کارت و ارسال رسید، مشاوره ادامه پیدا می‌کند.",
    ]
    lines.append("\nبرای لغو در هر مرحله: /cancel")
    return "\n".join(lines)


def user_line(user) -> str:
    uname = f"@{user['username']}" if user["username"] else "—"
    phone = user["phone"] or "—"
    return (
        f"👤 {escape(user['full_name'] or '')} | {escape(uname)} | <code>{user['user_id']}</code>\n"
        f"📞 <code>{escape(phone)}</code>\n"
        f"🔗 منبع: {escape(user['source'] or 'direct')}"
    )


def is_admin_chat(m: Message) -> bool:
    return ADMIN_GROUP_ID != 0 and m.chat.id == ADMIN_GROUP_ID


# ---------------------------------------------------------------- پیش‌شرط‌ها
async def is_member(bot: Bot, user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
        except Exception as e:  # بات در کانال ادمین نیست یا کانال پیدا نشد
            log.warning("membership check failed for %s: %s", ch, e)
            continue
        status = getattr(m, "status", "")
        if status in ("left", "kicked"):
            return False
        if status == "restricted" and not getattr(m, "is_member", True):
            return False
    return True


async def ensure_ready(m: Message, bot: Bot, state: FSMContext) -> bool:
    """عضویت و شماره تماس را چک می‌کند. اگر آماده نبود پیام مناسب می‌فرستد."""
    uid = m.chat.id
    if not await is_member(bot, uid):
        await m.answer(
            "برای استفاده از مشاوره، اول عضو این کانال‌ها شوید و بعد «✅ عضو شدم» را بزنید:",
            reply_markup=join_kb(),
        )
        return False
    u = get_user(uid)
    if not u or not u["phone"]:
        await state.set_state(Form.phone)
        await m.answer(
            "لطفاً با دکمه‌ی زیر شماره تماستان را ثبت کنید تا در صورت نیاز با شما تماس بگیریم.",
            reply_markup=phone_kb(),
        )
        return False
    return True


# ---------------------------------------------------------------- وضعیت‌ها
class Form(StatesGroup):
    phone = State()
    topic = State()
    collect = State()
    receipt = State()


router = Router()
admin = Router()
admin.message.filter(lambda m: is_admin_chat(m))
private = F.chat.type == ChatType.PRIVATE


# ---------------------------------------------------------------- ارسال به گروه ادمین
async def send_request_to_admins(bot: Bot, rid: int) -> None:
    r = get_request(rid)
    user = get_user(r["user_id"])
    msgs = json.loads(r["msgs"] or "[]")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ بستن درخواست", callback_data=f"close:{rid}")
    text = (
        f"📨 <b>درخواست #{rid}</b>\n"
        f"{user_line(user)}\n"
        f"📌 موضوع: {escape(TOPICS.get(r['topic'] or '', 'انتخاب نشده'))}\n"
        f"✉️ تعداد پیام: {len(msgs)}\n\n"
        "↩️ برای پاسخ، روی همین پیام یا پیام‌های زیر Reply بزنید.\n"
        "💳 برای درخواست هزینه: Reply بزنید و بنویسید <code>/pay مبلغ</code>"
    )
    head = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=kb.as_markup())
    map_msg(head.message_id, rid, r["user_id"])
    for mid in msgs:
        try:
            cp = await bot.copy_message(ADMIN_GROUP_ID, r["user_id"], mid, reply_to_message_id=head.message_id)
            map_msg(cp.message_id, rid, r["user_id"])
        except Exception as e:
            log.warning("copy %s failed: %s", mid, e)


# ---------------------------------------------------------------- دستورهای ادمین
@router.message(Command("id"))
async def cmd_id(m: Message):
    await m.reply(f"Chat ID: <code>{m.chat.id}</code>")


@admin.message(Command("list"))
async def cmd_list(m: Message):
    with db() as c:
        rows = c.execute(
            "SELECT r.*, u.full_name, u.phone FROM requests r LEFT JOIN users u ON u.user_id=r.user_id "
            "WHERE r.status NOT IN ('closed','rejected') ORDER BY r.id DESC LIMIT 30"
        ).fetchall()
    if not rows:
        await m.reply("درخواست بازی وجود ندارد ✅")
        return
    lines = ["<b>درخواست‌های باز:</b>\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} | {escape(r['full_name'] or '')} | {escape(r['phone'] or '')} | "
            f"{STATUS_FA.get(r['status'], r['status'])}"
        )
    lines.append("\nبرای دیدن دوباره‌ی یک درخواست: /show شماره")
    await m.reply("\n".join(lines))


@admin.message(Command("show"))
async def cmd_show(m: Message, command: CommandObject, bot: Bot):
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdigit() or not get_request(int(arg)):
        await m.reply("مثال: /show 12")
        return
    await send_request_to_admins(bot, int(arg))


@admin.message(Command("stats"))
async def cmd_stats(m: Message):
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        phones = c.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL").fetchone()[0]
        by_status = c.execute("SELECT status, COUNT(*) n FROM requests GROUP BY status").fetchall()
        total = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        paid = c.execute("SELECT COUNT(*) FROM payments WHERE status='approved'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM payments WHERE status IN ('pending','receipt_sent')").fetchone()[0]
        sources = c.execute(
            "SELECT source, COUNT(*) n FROM users GROUP BY source ORDER BY n DESC LIMIT 10"
        ).fetchall()
    lines = [
        f"<b>آمار {escape(BOT_TITLE)}</b>\n",
        f"👥 کاربران: {users} (با شماره: {phones})",
        f"📨 کل درخواست‌ها: {total}",
        f"💳 پرداخت‌های تأییدشده: {paid} | در انتظار: {pending}\n",
        "<b>وضعیت درخواست‌ها:</b>",
    ]
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


@admin.message(Command("pay"))
async def cmd_pay(m: Message, command: CommandObject, bot: Bot):
    amount = (command.args or "").strip()
    link = lookup_msg(m.reply_to_message.message_id) if m.reply_to_message else None
    if not link or not amount:
        await m.reply("روی یکی از پیام‌های کاربر Reply بزنید و بنویسید:\n<code>/pay ۵۰۰ هزار تومان</code>")
        return
    pid = create_payment(link["request_id"], link["user_id"], amount)
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 ارسال رسید پرداخت", callback_data=f"receipt:{pid}")
    lines = [
        "💳 <b>ادامه‌ی مشاوره‌ی تخصصی</b>\n",
        "برای بررسی دقیق‌تر موضوع شما، مشاوره‌ی تخصصی لازم است.",
        f"مبلغ: <b>{escape(amount)}</b>\n",
        f"شماره کارت:\n<code>{escape(CARD_NUMBER)}</code>",
    ]
    if CARD_HOLDER:
        lines.append(f"به نام: {escape(CARD_HOLDER)}")
    lines.append("\nبعد از واریز، دکمه‌ی زیر را بزنید و عکس رسید را بفرستید.")
    try:
        sent = await bot.send_message(link["user_id"], "\n".join(lines), reply_markup=kb.as_markup())
    except Exception as e:
        await m.reply(f"⚠️ ارسال نشد: {escape(str(e))}")
        return
    await m.reply(f"💳 درخواست پرداخت <b>{escape(amount)}</b> برای کاربر درخواست #{link['request_id']} ارسال شد.")


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


@router.callback_query(F.data.startswith(("close:", "pay_ok:", "pay_no:")))
async def admin_buttons(cq: CallbackQuery, bot: Bot):
    if cq.message.chat.id != ADMIN_GROUP_ID:
        await cq.answer("دسترسی ندارید.", show_alert=True)
        return
    action, oid = cq.data.split(":")
    oid = int(oid)
    by = escape(cq.from_user.full_name)

    if action == "close":
        if not get_request(oid):
            await cq.answer("درخواست پیدا نشد.", show_alert=True)
            return
        set_status(oid, "closed")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"✅ درخواست #{oid} توسط {by} بسته شد.")
        await cq.answer()
        return

    p = get_payment(oid)
    if not p or p["status"] != "receipt_sent":
        await cq.answer("این رسید قبلاً بررسی شده.")
        return
    if action == "pay_ok":
        set_payment_status(oid, "approved")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"💳 پرداخت {escape(p['amount'])} (درخواست #{p['request_id']}) توسط {by} تأیید شد.")
        await safe_send(bot, p["user_id"], "✅ پرداخت شما تأیید شد. ممنونم! مشاوره‌ی تخصصی را ادامه می‌دهیم.")
    else:
        set_payment_status(oid, "pending")
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.message.reply(f"⛔️ رسید درخواست #{p['request_id']} توسط {by} رد شد.")
        kb = InlineKeyboardBuilder()
        kb.button(text="📤 ارسال دوباره‌ی رسید", callback_data=f"receipt:{oid}")
        try:
            await bot.send_message(p["user_id"], "رسید پرداخت تأیید نشد. ⛔️\n"
                                   "اگر فکر می‌کنید اشتباهی رخ داده، دکمه‌ی زیر را بزنید و رسید درست را بفرستید.",
                                   reply_markup=kb.as_markup())
        except Exception as e:
            log.warning("notify failed: %s", e)
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
@router.message(CommandStart(), private)
async def cmd_start(m: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    upsert_user(m.from_user, source=(command.args or None))
    await m.answer(welcome_text(), reply_markup=main_kb())
    await ensure_ready(m, bot, state)


@router.callback_query(F.data == "check_sub")
async def check_sub(cq: CallbackQuery, state: FSMContext, bot: Bot):
    if not await is_member(bot, cq.from_user.id):
        await cq.answer("هنوز عضو همه‌ی کانال‌ها نشده‌اید.", show_alert=True)
        return
    await cq.answer("عضویت تأیید شد ✅")
    await cq.message.edit_reply_markup(reply_markup=None)
    if await ensure_ready(cq.message, bot, state):
        await cq.message.answer(f"عالی! حالا روی «{BTN_NEW}» بزنید.", reply_markup=main_kb())


@router.message(Form.phone, F.contact)
async def got_phone(m: Message, state: FSMContext):
    if m.contact.user_id and m.contact.user_id != m.from_user.id:
        await m.answer("لطفاً شماره‌ی خودتان را با همان دکمه بفرستید.", reply_markup=phone_kb())
        return
    upsert_user(m.from_user)
    phone = m.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    set_phone(m.from_user.id, phone)
    await state.clear()
    await m.answer(f"شماره‌ی شما ثبت شد ✅\nحالا روی «{BTN_NEW}» بزنید.", reply_markup=main_kb())


@router.message(Form.phone)
async def need_phone(m: Message):
    await m.answer(f"لطفاً فقط با دکمه‌ی «{BTN_PHONE}» شماره را بفرستید.", reply_markup=phone_kb())


@router.message(Command("help"), private)
@router.message(F.text == BTN_HELP, private)
async def cmd_help(m: Message):
    await m.answer(help_text(), reply_markup=main_kb())


@router.message(Command("cancel"), private)
@router.message(F.text == BTN_CANCEL, private)
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("لغو شد.", reply_markup=main_kb())


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
        lines.append(
            f"#{r['id']} | {escape(TOPICS.get(r['topic'] or '', '—'))} | "
            f"{STATUS_FA.get(r['status'], r['status'])} | {r['created_at']}"
        )
    await m.answer("\n".join(lines))


@router.message(Command("new"), private)
@router.message(F.text == BTN_NEW, private)
async def new_request(m: Message, state: FSMContext, bot: Bot):
    upsert_user(m.from_user)
    await state.clear()
    if not await ensure_ready(m, bot, state):
        return
    kb = InlineKeyboardBuilder()
    for k, v in TOPICS.items():
        kb.button(text=v, callback_data=f"topic:{k}")
    kb.button(text="⏭ بدون انتخاب موضوع", callback_data="topic:none")
    kb.adjust(1)
    await state.set_state(Form.topic)
    await m.answer("موضوع مشاوره چیست؟", reply_markup=kb.as_markup())


@router.callback_query(Form.topic, F.data.startswith("topic:"))
async def pick_topic(cq: CallbackQuery, state: FSMContext):
    key = cq.data.split(":", 1)[1]
    topic = key if key in TOPICS else None
    await state.update_data(topic=topic, msgs=[])
    await state.set_state(Form.collect)
    label = TOPICS.get(topic, "بدون موضوع") if topic else "بدون موضوع"
    await cq.message.edit_text(f"موضوع: <b>{escape(label)}</b>")
    await cq.message.answer(
        "حالا سؤال یا مشکلتان را هر طور راحتید بفرستید:\n"
        "✍️ متن  🎙 ویس  🖼 عکس  🎬 ویدیو  📎 فایل\n\n"
        "هر چند پیام که لازم است بفرستید (مثلاً درباره‌ی کسب‌وکار، شهر و مشکل‌تان).\n"
        f"آخر کار دکمه‌ی «{BTN_SEND}» را بزنید.",
        reply_markup=collect_kb(),
    )
    await cq.answer()


@router.message(Form.collect, F.text == BTN_SEND)
async def submit(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    msgs = data.get("msgs", [])
    if not msgs:
        await m.answer("هنوز چیزی نفرستاده‌اید. اول سؤالتان را بفرستید (متن، ویس یا عکس).")
        return
    uid = m.from_user.id
    rid = create_request(uid, data.get("topic"), msgs, is_free=True, status="open")
    await state.clear()
    await send_request_to_admins(bot, rid)
    await m.answer(
        f"✅ درخواست #{rid} برای مشاور ارسال شد.\n"
        "پاسخ همین‌جا می‌آید. اگر چیزی یادتان رفت، همین‌جا بفرستید.",
        reply_markup=main_kb(),
    )


@router.message(Form.collect)
async def collect(m: Message, state: FSMContext):
    if m.text and m.text.startswith("/"):
        await m.answer(f"پیامتان را بفرستید یا «{BTN_SEND}» را بزنید. (برای لغو: /cancel)")
        return
    if m.contact or m.location or m.poll:
        await m.answer("این نوع پیام پشتیبانی نمی‌شود؛ متن، ویس، عکس، ویدیو یا فایل بفرستید.")
        return
    data = await state.get_data()
    msgs = data.get("msgs", [])
    if len(msgs) >= MAX_MSGS:
        await m.answer(f"حداکثر {MAX_MSGS} پیام. لطفاً «{BTN_SEND}» را بزنید.")
        return
    msgs.append(m.message_id)
    first = len(msgs) == 1
    await state.update_data(msgs=msgs)
    if first:
        await m.answer(
            f"دریافت شد ✅ اگر چیز دیگری هم هست بفرستید؛ آخر کار «{BTN_SEND}» را بزنید.",
            reply_markup=collect_kb(),
        )


@router.callback_query(F.data.startswith("receipt:"))
async def ask_receipt(cq: CallbackQuery, state: FSMContext):
    pid = int(cq.data.split(":")[1])
    p = get_payment(pid)
    if not p or p["user_id"] != cq.from_user.id or p["status"] == "approved":
        await cq.answer("این پرداخت قبلاً تأیید شده یا معتبر نیست.", show_alert=True)
        return
    await state.set_state(Form.receipt)
    await state.update_data(receipt_pid=pid)
    await cq.message.answer("عکس رسید پرداخت را همین‌جا بفرستید. (برای لغو: /cancel)")
    await cq.answer()


@router.message(Form.receipt, F.photo | F.document)
async def got_receipt(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    p = get_payment(data.get("receipt_pid") or 0)
    await state.clear()
    if not p:
        await m.answer("پرداختی پیدا نشد.", reply_markup=main_kb())
        return
    set_payment_status(p["id"], "receipt_sent")
    user = get_user(p["user_id"])
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تأیید پرداخت", callback_data=f"pay_ok:{p['id']}")
    kb.button(text="⛔️ رد رسید", callback_data=f"pay_no:{p['id']}")
    caption = (f"💳 <b>رسید پرداخت — درخواست #{p['request_id']}</b>\n"
               f"مبلغ اعلام‌شده: {escape(p['amount'])}\n{user_line(user)}")
    sent = await bot.copy_message(ADMIN_GROUP_ID, m.chat.id, m.message_id, caption=caption,
                                  parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
    map_msg(sent.message_id, p["request_id"], p["user_id"])
    await m.answer("رسید دریافت شد 🙏 بعد از بررسی خبر می‌دهیم.", reply_markup=main_kb())


@router.message(Form.receipt)
async def receipt_other(m: Message):
    await m.answer("لطفاً عکس رسید پرداخت را بفرستید. (برای لغو: /cancel)")


# پیام‌های بعدی کاربر در ادامه‌ی گفتگو → به گروه ادمین
@router.message(private, StateFilter(None))
async def followup(m: Message, bot: Bot, state: FSMContext):
    if m.text and m.text.startswith("/"):
        await m.answer("دستور ناشناخته. از منوی پایین استفاده کنید.", reply_markup=main_kb())
        return
    upsert_user(m.from_user)
    r = latest_active_request(m.from_user.id)
    if not r:
        await m.answer(f"برای گرفتن مشاوره روی «{BTN_NEW}» بزنید.", reply_markup=main_kb())
        return
    user = get_user(m.from_user.id)
    head = await bot.send_message(
        ADMIN_GROUP_ID,
        f"💬 <b>ادامه‌ی گفتگو — درخواست #{r['id']}</b>\n{user_line(user)}\n↩️ برای پاسخ روی پیام زیر Reply بزنید.",
    )
    map_msg(head.message_id, r["id"], r["user_id"])
    cp = await bot.copy_message(ADMIN_GROUP_ID, m.chat.id, m.message_id, reply_to_message_id=head.message_id)
    map_msg(cp.message_id, r["id"], r["user_id"])
    await m.answer("پیام شما به مشاور رسید ✅")


# ---------------------------------------------------------------- اجرا
class RetrySession(AiohttpSession):
    """اتصال PythonAnywhere به تلگرام گاهی چند ثانیه قطع می‌شود؛ درخواست را چند بار تکرار می‌کنیم."""

    async def make_request(self, bot, method, timeout=None):
        from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
        delay = 1.0
        for attempt in range(4):
            try:
                return await super().make_request(bot, method, timeout)
            except TelegramAPIError as e:
                if not isinstance(e, TelegramNetworkError):
                    raise
                err = e
            except Exception as e:  # خطای پروکسی/شبکه
                err = e
            log.warning("network error (try %s): %s", attempt + 1, err)
            await asyncio.sleep(delay)
            delay *= 2
        raise err


def is_network_error(e: BaseException) -> bool:
    from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
    if isinstance(e, TelegramNetworkError):
        return True
    return not isinstance(e, TelegramAPIError) and isinstance(e, (OSError, asyncio.TimeoutError)) or \
        type(e).__module__.startswith(("aiohttp", "aiohttp_socks", "python_socks"))


def make_bot() -> Bot:
    session = RetrySession(proxy=PROXY) if PROXY else None
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
