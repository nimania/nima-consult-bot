"""
نسخه‌ی وبهوک برای PythonAnywhere (حساب رایگان).
تلگرام هر پیام را به آدرس /webhook/<WEBHOOK_SECRET> می‌فرستد و این‌جا پردازش می‌شود.
"""
import asyncio
import hmac

from flask import Flask, abort, request
from aiogram.types import Update

import bot as B
from sqlite_storage import SQLiteStorage

B.init_db()
dp = B.make_dispatcher(SQLiteStorage(B.DB_PATH))
app = Flask(__name__)


def _check(secret: str) -> None:
    if not B.WEBHOOK_SECRET or not hmac.compare_digest(secret, B.WEBHOOK_SECRET):
        abort(404)


async def _process(payload: dict) -> None:
    bot = B.make_bot()
    try:
        update = Update.model_validate(payload, context={"bot": bot})
        await dp.feed_update(bot, update)
    finally:
        await bot.session.close()


@app.route("/")
def index():
    return "bot is running"


@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    _check(secret)
    try:
        asyncio.run(_process(request.get_json(force=True)))
    except Exception:
        B.log.exception("update failed")
    return "ok"


@app.route("/setup/<secret>")
def setup(secret):
    """یک بار این آدرس را در مرورگر باز کن تا وبهوک تنظیم شود."""
    _check(secret)
    url = f"https://{request.host}/webhook/{B.WEBHOOK_SECRET}"

    async def go():
        bot = B.make_bot()
        try:
            await bot.set_webhook(url, drop_pending_updates=True,
                                  allowed_updates=["message", "callback_query"])
            me = await bot.get_me()
            info = await bot.get_webhook_info()
            return me.username, info
        finally:
            await bot.session.close()

    try:
        username, info = asyncio.run(go())
    except Exception as e:
        return f"<h3 dir=rtl>خطا: {e}</h3>", 500
    return (f"<div dir=rtl style='font-family:sans-serif'><h2>✅ وبهوک تنظیم شد</h2>"
            f"<p>بات: @{username}</p><p>پیام‌های در صف: {info.pending_update_count}</p>"
            f"<p>حالا در تلگرام به بات /start بفرست.</p></div>")
