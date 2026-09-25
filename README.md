# مشاوره تخصصی نیما افشارنادری — بات تلگرام

بات: [t.me/NimaAfsharnaderiBot](https://t.me/NimaAfsharnaderiBot)
لینک مخصوص بایو و استوری اینستاگرام: `https://t.me/NimaAfsharnaderiBot?start=insta`

## چه کار می‌کند؟

- **پیش‌شرط:** عضویت در کانال‌های @nimasdiner و @nimaafsharnaderi و ثبت شماره تماس با دکمه‌ی «ارسال شماره».
  (بات باید در هر دو کانال **ادمین** باشد تا بتواند عضویت را چک کند.)
- کاربر «شروع مشاوره» را می‌زند، در صورت تمایل موضوع را انتخاب می‌کند و بعد هرچه لازم است می‌فرستد:
  متن، ویس، عکس، ویدیو یا فایل. آخر کار «ارسال برای مشاور» را می‌زند.
- همه‌ی پیام‌ها همراه با **نام، یوزرنیم و شماره تماس** کاربر به گروه ادمین می‌آیند.
- برای جواب، روی پیام **Reply** بزن (متن، ویس، عکس، فایل). گفتگو رفت‌وبرگشتی ادامه پیدا می‌کند.
- **مشاوره‌ی اولیه رایگان است.** هر وقت لازم دانستی، روی یکی از پیام‌های کاربر Reply بزن و بنویس
  `/pay ۵۰۰ هزار تومان` تا مبلغ و شماره کارت برای کاربر برود. کاربر رسید را می‌فرستد و تو تأیید یا رد می‌کنی.

### دستورهای ادمین (داخل گروه ادمین)

| دستور | کار |
|---|---|
| Reply روی پیام کاربر | ارسال جواب به کاربر |
| Reply + `/pay مبلغ` | درخواست پرداخت از کاربر |
| `/list` | درخواست‌های باز |
| `/show 12` | نمایش دوباره‌ی درخواست ۱۲ |
| `/stats` | آمار کاربران، پرداخت‌ها و منبع ورود (مثلاً insta) |
| `/broadcast` | روی یک پیام Reply بزن و این را بنویس تا برای همه‌ی کاربران ارسال شود |
| `/id` | نمایش آیدی گروه |

## راه‌اندازی قدم‌به‌قدم

### ۱. تنظیم بات در BotFather
در تلگرام به `@BotFather` برو:
- `/setname` ← نام: `مشاوره تخصصی نیما افشارنادری`
- `/setdescription` و `/setabouttext` ← یک توضیح کوتاه
- `/setuserpic` ← عکس پروفایل
- `/setcommands` ← این متن را بفرست:
  ```
  start - شروع
  new - درخواست مشاوره جدید
  help - راهنما
  cancel - لغو فرم
  ```
- `/token` ← توکن را بگیر و **به هیچ‌کس نده**.

### ۲. ساخت گروه ادمین
1. یک گروه خصوصی بساز (مثلاً «ادمین مشاوره») و بات را عضوش کن.
2. بات را **ادمین** گروه کن (تا همه‌ی پیام‌ها را ببیند).
3. بعد از اجرای بات (قدم ۳)، داخل گروه بنویس `/id` و عددی را که برمی‌گرداند در `ADMIN_GROUP_ID` بگذار و بات را ری‌استارت کن.

### ۳ (رایگان). نصب روی PythonAnywhere

در حساب رایگان PythonAnywhere بات با «وبهوک» اجرا می‌شود (`flask_app.py`) و وضعیت فرم‌ها در دیتابیس می‌ماند.

1. **Consoles → Bash** را باز کن و بزن:
   ```bash
   git clone https://github.com/nimania/nima-consult-bot.git
   cd nima-consult-bot
   pip3.10 install --user -r requirements.txt
   cp .env.example .env
   ```
2. **Files** → `nima-consult-bot/.env` را باز کن و پر کن:
   `BOT_TOKEN`، `CARD_NUMBER`، `CARD_HOLDER`،
   `PROXY=http://proxy.server:3128` (برای حساب رایگان لازم است)،
   و `WEBHOOK_SECRET` = یک رمز تصادفی بلند از حروف و عدد انگلیسی.
3. **Web → Add a new web app** → Manual configuration → Python 3.10.
   در فایل WSGI (لینکش در همان صفحه است) همه‌چیز را پاک کن و این را بگذار (به‌جای USERNAME نام کاربری خودت):
   ```python
   import sys
   path = "/home/USERNAME/nima-consult-bot"
   if path not in sys.path:
       sys.path.insert(0, path)
   from flask_app import app as application
   ```
   بعد دکمه‌ی سبز **Reload** را بزن.
4. در مرورگر باز کن: `https://USERNAME.pythonanywhere.com/setup/WEBHOOK_SECRET`
   اگر «✅ وبهوک تنظیم شد» دیدی، بات روشن است.
5. در گروه ادمین `/id` بزن، عدد را در `ADMIN_GROUP_ID` فایل `.env` بگذار و دوباره **Reload** کن.

> حساب رایگان ماهی یک بار در صفحه‌ی Web دکمه‌ی «Run until 1 month from today» می‌خواهد.

به‌روزرسانی: در Bash بزن `cd nima-consult-bot && git pull` و بعد در صفحه‌ی Web دکمه‌ی Reload.

### ۳ (VPS). نصب روی سرور لینوکس

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
sudo git clone https://github.com/nimania/nima-consult-bot.git /opt/nima-consult-bot
cd /opt/nima-consult-bot
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
sudo cp .env.example .env
sudo nano .env        # توکن، آیدی گروه، شماره کارت و قیمت را پر کن
```

تست دستی:
```bash
sudo venv/bin/python bot.py
```
اگر در لاگ `Bot @NimaAfsharnaderiBot started` دیدی، با `Ctrl+C` ببند و سرویس دائمی را فعال کن:

```bash
sudo cp consult-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now consult-bot
sudo systemctl status consult-bot      # وضعیت
sudo journalctl -u consult-bot -f      # لاگ زنده
```

### به‌روزرسانی
```bash
cd /opt/nima-consult-bot && sudo git pull && sudo systemctl restart consult-bot
```

## نکته‌ها
- سرور باید مستقیم به تلگرام دسترسی داشته باشد. اگر سرور داخل ایران است، در `.env` مقدار `PROXY` را بگذار.
- فایل `.env` (توکن و شماره کارت) و دیتابیس `consult.db` با `.gitignore` وارد گیت‌هاب نمی‌شوند.
- اگر وسط پر کردن فرم بات ری‌استارت شود، فرم نیمه‌کاره پاک می‌شود. درخواست‌های ثبت‌شده در دیتابیس می‌مانند.
- از `consult.db` گاهی نسخه‌ی پشتیبان بگیر.
- موضوع‌های مشاوره در بالای `bot.py` (بخش `TOPICS`) قابل تغییر است.
