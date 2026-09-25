# مشاوره تخصصی نیما افشارنادری — بات تلگرام

بات: [t.me/NimaAfsharnaderiBot](https://t.me/NimaAfsharnaderiBot)
لینک مخصوص بایو و استوری اینستاگرام: `https://t.me/NimaAfsharnaderiBot?start=insta`

## چه کار می‌کند؟

- کاربر موضوع و نوع مشاوره (متنی/ویس یا تماس) را انتخاب می‌کند. بعد کسب‌وکار، شهر و شرح مشکل را می‌نویسد و اگر خواست عکس هم می‌فرستد. پیش از ثبت، پیش‌نمایش درخواست را می‌بیند.
- **اولین درخواست هر کاربر رایگان است.** از درخواست دوم به بعد، بات شماره کارت را نشان می‌دهد و کاربر عکس رسید را می‌فرستد. رسید با دکمه‌های تأیید و رد به گروه ادمین می‌رود.
- همه‌ی درخواست‌ها به **گروه خصوصی ادمین** می‌آیند. برای جواب دادن کافی است روی پیام درخواست **Reply** بزنی. متن، ویس، عکس و فایل همه به کاربر می‌رسد.
- پیام‌هایی که کاربر بعد از ثبت درخواست می‌فرستد، خودکار به همان درخواست در گروه اضافه می‌شوند.
- اگر درخواست رایگانی را رد کنی، سهمیه‌ی رایگان به کاربر برمی‌گردد.

### دستورهای ادمین (داخل گروه ادمین)

| دستور | کار |
|---|---|
| `/list` | درخواست‌های باز |
| `/show 12` | نمایش دوباره‌ی درخواست ۱۲ |
| `/stats` | آمار کاربران، درخواست‌ها و منبع ورود (مثلاً insta) |
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

### ۳. نصب روی سرور (VPS لینوکس، ترجیحاً خارج از ایران)

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
