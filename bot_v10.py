# -*- coding: utf-8 -*-
"""
ربات بازی ماجراجویی تلگرام – نسخه‌ی یکپارچه (v10)

متغیرهای محیطی:
  BOT_TOKEN        توکن ربات (اجباری)
  ADMIN_IDS        آیدی عددی ادمین‌ها، با کاما جدا شده (اختیاری)
  PROXY_URL        مثلاً socks5://127.0.0.1:1080 (اختیاری)
  DB_PATH          مسیر دیتابیس (پیش‌فرض: game.db)
  STICKER_SETS     نام پک‌های استیکر (با کاما). پیش‌فرض خالی (استیکر تقریباً خاموش)
  STICKER_CHANCE   شانس استیکر (۰ تا ۱، پیش‌فرض 0.06 — خیلی کم)
  AUTO_PROFILE     اگه 0 باشه ربات توضیحات و منوی دستورها رو تنظیم نمی‌کنه
  BOT_CHANNEL      آیدی/یوزرنیم کانال (مثل @mychannel) — توی توضیحات ربات و اجبار عضویت
  REQUIRED_CHANNEL یوزرنیم کانال اجباری (مثل @mychannel) — بدون عضویت بازی نمی‌شه
  REQUIRED_GROUP   یوزرنیم یا لینک گروه اجباری (مثل @mygroup) — بدون عضویت بازی نمی‌شه

نکته‌ی مهم: برای اینکه ربات کلمه‌های فارسی بدون اسلش ("کار"، "پوینت"، ...) رو توی گروه ببینه،
توی BotFather بزن /setprivacy و Privacy Mode رو Disable کن (یا ربات رو ادمین گروه کن).
"""
import asyncio
import html
import logging
import math
import os
import random
import re
import sqlite3
import time
from contextlib import contextmanager

from telegram import InlineKeyboardButton as _InlineButton
from telegram import InlineKeyboardMarkup as Markup
from telegram import Update
from telegram.error import NetworkError
from telegram.ext import (Application, CallbackQueryHandler, ChatMemberHandler,
                          ContextTypes, MessageHandler, filters)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


def Btn(text, data=None, url=None):
    """در نسخه‌های جدید python-telegram-bot آرگومان دوم url است، نه callback_data؛ پس صریح می‌دهیم."""
    if url:
        return _InlineButton(text, url=url)
    return _InlineButton(text, callback_data=data)

TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
DB_PATH = os.getenv("DB_PATH", "game.db")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# ======================= تنظیمات بازی (همه قابل تغییر) =======================
WORK_COOLDOWN = 300
ADVENTURE_COOLDOWN = 900
DAILY_COOLDOWN = 20 * 3600
ROB_COOLDOWN = 1800
DUEL_COOLDOWN = 600
DUNGEON_COOLDOWN = 3600
BET_COOLDOWN = 60

CHAT_REWARD = 1
CHAT_COOLDOWN = 90
CHAT_DAILY_CAP = 30

POINT_BASE = 420
POINT_STEP = 30
POINT_MIN = 180
MAX_CITY = 12

BANK_RATE = 0.002
BANK_MAX_HOURS = 24
BANK_CAP_PER_LEVEL = 1000

LEVEL_CAP = 30
TRANSFER_FEE = 0.05
TRANSFER_DAILY_PER_LEVEL = 2000   # سقف انتقال روزانه = لول × این عدد
ROB_PROTECT = 1800                # بعد از دزدی، قربانی تا این مدت امنه
DUEL_TTL = 300
DUNGEON_TTL = 1800
SELL_RATIO = 0.5                  # فروش وسیله به چه نسبتی از قیمت خرید
GUILD_CREATE_COST = 500           # هزینه‌ی ساخت انجمن (۰ = رایگان)
GUILD_MAX_MEMBERS = 30
FLOOD_GAP = 0.7                   # حداقل فاصله‌ی بین دو دستور هر کاربر (ثانیه)

MARRY_LEVEL = 8                   # حداقل لول برای ازدواج (هر دو نفر)
MARRY_COST = 2000                 # هزینه‌ی حلقه و مراسم (از خواستگار)
MARRY_TTL = 6 * 3600              # مهلت جواب به خواستگاری
MARRY_BONUS = 5                   # درصد سکه‌ی بیشتر کار برای متاهل‌ها
DIVORCE_COST = 1000
LOVE_COOLDOWN = 12 * 3600         # فاصله‌ی دستور «عشق»

BOSS_HIT_COOLDOWN = 90            # فاصله‌ی دو حمله‌ی هر نفر به غول (ثانیه)
BOSS_TTL = 3 * 3600               # غول چند ساعت می‌مونه تا فرار کنه
BOSS_GAP = (4 * 3600, 8 * 3600)   # فاصله‌ی ظهور غول بعدی (حداقل، حداکثر)
BOSS_POOL_RATIO = 0.5             # مجموع جایزه‌ی سکه = این نسبت × جان غول
BOSS_MIN_PLAYERS = 2              # حداقل بازیکن فعال برای ظهور غول
INVITE_MIN_PLAYERS = 3            # گروه جدید باید حداقل این‌قدر بازیکن با شخصیت داشته باشه
INVITE_REWARD = 1500              # جایزه‌ی سکه‌ی دعوت موفق
INVITE_MAX = 10                   # سقف جایزه‌ی دعوت برای هر نفر

WHEEL_COOLDOWN = 20 * 3600        # فاصله‌ی چرخ شانس رایگان
WHEEL_PAID_BASE = 1000            # هزینه‌ی چرخش اضافه = این + (لول × ۱۰۰)
WHEEL_REVEAL_DELAY = 3.4          # صبر برای تموم شدن انیمیشن ماشین شانس (ثانیه)

try:
    SEASON_DAYS = max(1, int(os.getenv("SEASON_DAYS", "30")))   # طول هر فصل (روز)
except ValueError:
    SEASON_DAYS = 30
SEASON_MIN_PTS = 100              # حداقل امتیاز فصل برای جایزه‌ی مشارکت
MARKET_FEE = 0.05                 # کارمزد بازار (از مبلغ فروش کم می‌شه)
MARKET_MAX_LIST = 5               # حداکثر آگهی فعال هر نفر
MARKET_TTL = 48 * 3600            # مدت اعتبار آگهی
MARKET_PCTS = (80, 100, 125, 150)   # قیمت‌های پیشنهادی به درصدِ قیمت فروشگاه
MARKET_PAGE = 5                   # تعداد آگهی در هر صفحه
FORGE_MAX = 10                    # حداکثر تقویت
FORGE_CHANCE = [100, 95, 90, 80, 70, 60, 50, 40, 30, 20]   # شانس رفتن از +i به +(i+1) (٪)
GOLDEN_FRIDAY = 1.5               # ضریب XP و سکه‌ی کار در جمعه‌ی طلایی (جمعه به وقت ایران)

PET_MAX = 5                       # حداکثر همراه (به‌علاوه‌ی تخم‌های توی دستگاه)
PET_MAX_LEVEL = 30
INCUBATOR_SLOTS = 2               # تعداد تخمِ هم‌زمان توی دستگاه جوجه‌کشی
FEED_COOLDOWN = 4 * 3600          # فاصله‌ی غذا دادن به همراه
PLAY_COOLDOWN = 2 * 3600          # فاصله‌ی بازی با همراه
WORLD_TTL = 48 * 3600             # مدت هر غول جهانی
WORLD_GAP = (4 * 86400, 6 * 86400)   # فاصله تا غول جهانی بعدی (حداقل، حداکثر)
WORLD_HIT_COOLDOWN = 180          # فاصله‌ی دو ضربه‌ی هر نفر به غول جهانی (ثانیه)
WORLD_MIN_PLAYERS = 3             # حداقل بازیکن فعال برای ظهور خودکار غول جهانی

CHEST_TTL = 30 * 60               # مهلت باز کردن صندوق گنج
CHEST_DAILY_MAX = 5               # حداکثر صندوقی که هر نفر در روز می‌تونه باز کنه
CHEST_GAP = (3 * 3600, 6 * 3600)  # فاصله‌ی ظهور صندوق بعدی توی هر گروه
CHEST_MIN_PLAYERS = 2             # حداقل بازیکن فعال (۳ ساعت اخیر) برای ظهور صندوق
REF_WELCOME = 1000                # هدیه‌ی سکه‌ی کسی که با لینک دعوت میاد
REF_REWARD = 2500                 # جایزه‌ی دعوت‌کننده وقتی دوستش به لول ۵ برسه
REF_MAX = 30                      # سقف جایزه‌ی دعوت دوست برای هر نفر

STICKER_SETS = [x.strip() for x in os.getenv("STICKER_SETS", "").split(",") if x.strip()]
try:
    STICKER_CHANCE = float(os.getenv("STICKER_CHANCE", "0.06"))
except ValueError:
    STICKER_CHANCE = 0.06

# کانال و گروه اجباری
# کانال عمومی با یوزرنیم چک می‌شه؛ گروه خصوصی فقط لینک عضویت نشون داده می‌شه
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "Eldoria_Adventure").strip().lstrip("@")
REQUIRED_GROUP = os.getenv("REQUIRED_GROUP", "").strip().lstrip("@")  # یوزرنیم عمومی (اگر داشت)
REQUIRED_GROUP_INVITE = os.getenv("REQUIRED_GROUP_INVITE", "https://t.me/+Gxj_L7yfpwE5ZjEx").strip()

UNLOCK_TEXT = {
    2: "ماجراجویی و جایزه‌ی روزانه",
    3: "بانک (سود ساعتی)",
    4: "انتقال پول به دوستان",
    5: "شغل‌ها (کارگر، معدنچی و ...)",
    6: "ماموریت‌های روزانه",
    7: "ارتقای شهر گروه",
    8: "دزدی و ازدواج 💍",
    9: "سرداب (ماجراجویی مرحله‌ای)",
    10: "دوئل",
    12: "شرط‌بندی",
}

# متن تشویقی لول‌آپ (برای حس پیشرفت و جلوگیری از حوصله‌سررفتن)
LEVEL_UP_FLAVOR = {
    1: "اولین قدم‌هات رو توی این سرزمین برداشتی. قوی شو!",
    2: "دیگه تازه‌کار مطلق نیستی. وقت ماجراجوییه!",
    3: "پولتو توی بانک بذار تا سود بگیری. عاقلانه بازی کن.",
    4: "حالا می‌تونی به دوستات کمک کنی. سخاوتمند باش.",
    5: "شغل انتخاب کن و درآمدت رو چند برابر کن!",
    6: "ماموریت‌ها رو انجام بده، جایزه‌شون ارزشش رو داره.",
    7: "شهر گروهت رو ارتقا بده تا همه سود کنن.",
    8: "عشق و دزدی... زندگی واقعی شروع شد 😏",
    9: "سرداب منتظرته. معجون یادت نره!",
    10: "دوئل‌باز شدی. قدرتت رو نشون بده.",
    12: "شرط‌بندی باز شد. با احتیاط قمار کن!",
    15: "دیگه یه جنگجوی واقعی هستی. تجهیزات خفن بخر.",
    20: "اسطوره‌ها از اینجا شروع می‌شن. ادامه بده!",
    25: "پادشاهی نزدیکه. کسی جلودار تو نیست.",
    30: "امپراتور شدی. تمام سرزمین بهت احترام می‌ذاره 👑",
}
CITY_UPGRADE_LEVEL = 7
TITLES = [(1, "تازه‌وارد"), (3, "کارگر"), (5, "ماجراجو"), (8, "جنگجو"), (10, "شوالیه"),
          (13, "فرمانده"), (16, "قهرمان"), (20, "اسطوره"), (25, "پادشاه"), (30, "امپراتور")]

JOBS = {
    "کارگر": (5, "۴+ سکه در هر کار"),
    "معدنچی": (8, "۹+ سکه در هر کار"),
    "نگهبان": (8, "۱۰٪ دفاع بیشتر در برابر دزدی"),
    "تاجر": (10, "پوینت رایگان دو برابر"),
    "راهزن": (10, "۱۰٪ شانس بیشتر در دزدی"),
}
JOB_WORK = {"کارگر": 4, "معدنچی": 9}
JOB_CHANGE_COST = 300

MISSIONS = [  # (ستون، هدف، توضیح، سکه، XP)
    ("work", 6, "۶ بار کار کن", 60, 25),
    ("adv", 2, "۲ بار ماجراجویی کن", 80, 30),
    ("point", 4, "۴ بار پوینت بگیر", 40, 20),
]

# کلید -> (اسم، دسته، قیمت، حداقل لول، قدرت، توضیح)
# سلاح‌های پایه فقط برای جنگجو و نینجا مناسبن؛ جادوگر/شکارچی/کیمیاگر از تجهیزات کلاس خودشون استفاده می‌کنن
ITEMS = {
    "pick1": ("⛏ کلنگ چوبی", "tool", 300, 1, 2, "+۲ سکه در هر کار"),
    "pick2": ("⛏ کلنگ آهنی", "tool", 1500, 3, 5, "+۵ سکه در هر کار"),
    "pick3": ("⛏ کلنگ فولادی", "tool", 6000, 6, 10, "+۱۰ سکه در هر کار"),
    "pick4": ("⛏ کلنگ طلایی", "tool", 20000, 10, 18, "+۱۸ سکه در هر کار"),
    "pick5": ("💎 کلنگ الماسی", "tool", 60000, 15, 30, "+۳۰ سکه در هر کار"),
    # سلاح عمومی (بیشتر مناسب جنگجو/نینجا)
    "weap1": ("🪵 چوب‌دستی", "weapon", 400, 1, 2, "۲٪ شانس پیروزی بیشتر"),
    "weap2": ("🗡 خنجر", "weapon", 1800, 3, 4, "۴٪ شانس پیروزی بیشتر"),
    "weap3": ("⚔️ شمشیر آهنی", "weapon", 7000, 6, 7, "۷٪ شانس پیروزی بیشتر"),
    "weap4": ("🔱 شمشیر فولادی", "weapon", 22000, 10, 11, "۱۱٪ شانس پیروزی بیشتر"),
    "weap5": ("🪓 تبر جنگی", "weapon", 60000, 15, 15, "۱۵٪ شانس پیروزی بیشتر"),
    "weap6": ("🐉 شمشیر اژدها", "weapon", 150000, 20, 20, "۲۰٪ شانس پیروزی بیشتر"),
    # زره عمومی
    "arm1": ("🛡 سپر چوبی", "armor", 500, 1, 5, "۵٪ کاهش خسارت"),
    "arm2": ("🥋 زره چرمی", "armor", 2000, 3, 10, "۱۰٪ کاهش خسارت"),
    "arm3": ("⛓ زره آهنی", "armor", 8000, 6, 18, "۱۸٪ کاهش خسارت"),
    "arm4": ("🛡 زره فولادی", "armor", 25000, 10, 26, "۲۶٪ کاهش خسارت"),
    "arm5": ("🔰 زره میتریل", "armor", 70000, 15, 34, "۳۴٪ کاهش خسارت"),
    "arm6": ("🐲 زره اژدها", "armor", 170000, 20, 42, "۴۲٪ کاهش خسارت"),
    "chm1": ("🍀 طلسم شانس", "charm", 3000, 4, 10, "۱۰٪ جایزه بیشتر"),
    "chm2": ("🧿 طلسم طلایی", "charm", 20000, 10, 20, "۲۰٪ جایزه بیشتر"),
    "chm3": ("👑 تاج سلطنتی", "charm", 100000, 18, 35, "۳۵٪ جایزه بیشتر"),
    "lock": ("🔒 قفل", "misc", 800, 4, 0, "جلوی یک دزدی رو می‌گیره"),
    "potion": ("🧪 معجون", "misc", 1000, 9, 0, "تو سرداب جلوی مرگت رو می‌گیره"),
}
# ---------- تجهیزات ویژه‌ی کلاس و شغل ----------
ITEM_REQ = {}       # کلید -> ("cls", نام کلاس) یا ("job", نام شغل)
ITEM_RARITY = {}    # کلید -> 🟦 نادر / 🟪 حماسی / 🟧 افسانه‌ای


def _rarity(lvl):
    return "🟧" if lvl >= 22 else "🟪" if lvl >= 14 else "🟦" if lvl >= 7 else ""


def _gear(key, name, cat, price, lvl, power, req):
    desc = {"tool": f"+{power} سکه در هر کار", "weapon": f"{power}٪ شانس پیروزی بیشتر",
            "armor": f"{power}٪ کاهش خسارت", "charm": f"{power}٪ جایزه بیشتر"}[cat]
    ITEMS[key] = (name, cat, price, lvl, power, desc)
    ITEM_REQ[key] = req
    if _rarity(lvl):
        ITEM_RARITY[key] = _rarity(lvl)


_W = [(5, 6, 4500), (10, 13, 28000), (16, 21, 90000), (24, 30, 320000)]   # (لول، قدرت، قیمت)
_A = [(8, 20, 11000), (18, 44, 140000)]
_C = [(7, 15, 9000), (20, 42, 180000)]
CLASS_GEAR = {
    "warrior": {"weapon": ["⚔️ شمشیر نبرد", "🪓 تبر خون‌ریز", "🔱 نیزه‌ی تندر", "👑 اکسکالیبر"],
                "armor": ["🛡 سپر برجی", "🏰 زره تیتان"], "charm": ["🎖 نشان افتخار", "🦁 قلب شیر"]},
    "mage": {"weapon": ["🪄 عصای شاگرد", "🔮 عصای کریستالی", "⚡ عصای صاعقه", "🌌 عصای کهکشان"],
             "armor": ["🧙 ردای جادوگر", "🌠 ردای ستاره‌ای"], "charm": ["📿 تعویذ مرموز", "📖 کتاب ممنوعه"]},
    "hunter": {"weapon": ["🏹 کمان شکارچی", "🌲 کمان جنگل", "🔥 کمان آتشین", "🦅 کمان سایه‌ی عقاب"],
               "armor": ["🧥 جلیقه‌ی شکارچی", "🐺 پوست گرگ افسانه‌ای"], "charm": ["🪶 پر عقاب", "🐻 چنگال خرس غول‌پیکر"]},
    "ninja": {"weapon": ["🔪 کاتانای شب", "⭐ شوریکن فولادی", "🌑 تیغ سایه", "🩸 کاتانای شبح"],
              "armor": ["🥷 لباس مخفی", "🌫 شنل دود"], "charm": ["🌙 نگین ماه", "🎭 ماسک روح"]},
    "alchemist": {"weapon": ["🧪 قمقمه‌ی اسیدی", "💥 بمب دودزا", "☣️ بطری طاعون", "🌋 اکسیر آتشفشان"],
                  "armor": ["🥼 روپوش آزمایشگاه", "⚗️ زره‌ی شیشه‌ای کیمیا"], "charm": ["💎 سنگ جادو", "🧬 اکسیر جاودانگی"]},
}
for _cls, _parts in CLASS_GEAR.items():
    for _cat, _names in _parts.items():
        _spec = {"weapon": _W, "armor": _A, "charm": _C}[_cat]
        for _i, (_nm, (_lv, _pw, _pr)) in enumerate(zip(_names, _spec), 1):
            _gear(f"{_cls[:3]}_{_cat[0]}{_i}", _nm, _cat, _pr, _lv, _pw, ("cls", _cls))

JOB_GEAR = [  # (کلید، اسم، دسته، لول، قدرت، قیمت، شغل)
    ("kar_t1", "🔨 چکش کارگری", "tool", 6, 8, 5000, "کارگر"),
    ("kar_t2", "🪚 ارّه‌ی برقی", "tool", 12, 20, 35000, "کارگر"),
    ("min_t1", "⛏ کلنگ معدن‌کاو", "tool", 8, 14, 9000, "معدنچی"),
    ("min_t2", "💎 مته‌ی الماس", "tool", 14, 32, 75000, "معدنچی"),
    ("min_t3", "🌋 مته‌ی گدازه", "tool", 22, 55, 280000, "معدنچی"),
    ("neg_a1", "🛡 سپر نگهبان", "armor", 9, 24, 14000, "نگهبان"),
    ("neg_w1", "🔱 نیزه‌ی دروازه‌بان", "weapon", 12, 12, 25000, "نگهبان"),
    ("neg_a2", "🗼 زره‌ی قلعه", "armor", 16, 38, 90000, "نگهبان"),
    ("taj_c1", "💰 کیسه‌ی زر", "charm", 10, 25, 25000, "تاجر"),
    ("taj_c2", "🪙 سکه‌ی کمیاب", "charm", 18, 45, 130000, "تاجر"),
    ("taj_c3", "📜 قرارداد سلطنتی", "charm", 26, 50, 350000, "تاجر"),
    ("rah_w1", "🗡 خنجر راهزن", "weapon", 10, 12, 22000, "راهزن"),
    ("rah_a1", "🧥 شنل راهزن", "armor", 12, 25, 40000, "راهزن"),
    ("rah_w2", "🏴‍☠️ شمشیر دزد دریایی", "weapon", 17, 22, 95000, "راهزن"),
    ("rah_w3", "💀 تبر قرمز", "weapon", 25, 30, 300000, "راهزن"),
]
for _k, _n, _c, _lv, _pw, _pr, _job in JOB_GEAR:
    _gear(_k, _n, _c, _pr, _lv, _pw, ("job", _job))

ITEMS["potion2"] = ("🧪 معجون بزرگ", "misc", 3500, 12, 0,
                    "تو سرداب جلوی مرگت رو می‌گیره و ۶۰ جان برمی‌گردونه (یک‌بار مصرف)")
ITEMS["lock2"] = ("🔐 قفل آهنین", "misc", 2500, 10, 0,
                  "جلوی یک دزدی رو می‌گیره و دزد ۱۲۰ سکه جریمه می‌شه (یک‌بار مصرف)")

# آیتم‌های مخصوص سفیرها (فقط با دعوت به‌دست میان، توی فروشگاه نیستن)
ITEMS["amb1"] = ("📣 نشان سفیر", "charm", 30000, 1, 28, "۲۸٪ جایزه بیشتر — جایزه‌ی ۳ دعوت موفق")
ITEMS["amb2"] = ("👑 تاج سفیر", "charm", 150000, 1, 45, "۴۵٪ جایزه بیشتر — جایزه‌ی ۱۰ دعوت موفق")
ITEM_RARITY["amb1"], ITEM_RARITY["amb2"] = "🟪", "🟧"
ITEMS["champ1"] = ("👑 تاج قهرمان فصل", "charm", 250000, 1, 48, "۴۸٪ جایزه بیشتر — جایزه‌ی نفر اول فصل")
ITEMS["champ2"] = ("🥈 نشان برتر فصل", "charm", 90000, 1, 36, "۳۶٪ جایزه بیشتر — جایزه‌ی نفر دوم و سوم فصل")
ITEMS["road1"] = ("🌠 نشان جاده‌ی فصل", "charm", 60000, 1, 32, "۳۲٪ جایزه بیشتر — جایزه‌ی پله‌ی آخر جاده‌ی فصل")
ITEM_RARITY["champ1"], ITEM_RARITY["champ2"], ITEM_RARITY["road1"] = "🟧", "🟪", "🟪"
ITEMS["egg1"] = ("🥚 تخم معمولی", "misc", 6000, 3, 0,
                 "جوجه‌کشی کن تا یه همراه بده — ۲۰٪ شانس نادر، ۵٪ حماسی یا بهتر")
ITEMS["egg2"] = ("🪺 تخم نادر", "misc", 35000, 10, 0,
                 "همراهش حداقل نادره — ۳۰٪ حماسی، ۵٪ افسانه‌ای")
ITEMS["egg3"] = ("🐲 تخم افسانه‌ای", "misc", 250000, 1, 0,
                 "همراهش حماسی یا افسانه‌ایه (۴۰٪ افسانه‌ای) — فقط از رویدادها")
ITEMS["world1"] = ("🌍 نشان فاتح جهان", "charm", 200000, 1, 42, "۴۲٪ جایزه بیشتر — جایزه‌ی شکست غول جهانی")
ITEM_RARITY["world1"] = "🟧"
HIDDEN_ITEMS = {"amb1", "amb2", "champ1", "champ2", "road1", "egg3", "world1"}
INVITE_MILESTONES = {3: "amb1", 10: "amb2"}

# ---------- متن‌های رنگارنگ ----------
WORK_STORIES = {
    "": ["📦 توی بازار شهر بار حمل کردی و تاجرها کلی انعام دادن!",
         "🌾 مزرعه‌ی ارباب رو شخم زدی و عرق ریختی!",
         "🔥 تو کارگاه آهنگری چکش زدی و شمشیر ساختی!",
         "🏗 دیوار قلعه رو با بقیه تعمیر کردی!",
         "🐎 اسب‌های اصطبل سلطنتی رو شستی و براق کردی!"],
    "کارگر": ["🏗 ساعت‌ها آجر جابه‌جا کردی و برج تازه‌ای بالا رفت!", "🪵 چوب‌های جنگل رو بریدی و به کارگاه رسوندی!"],
    "معدنچی": ["⛏ تو عمق معدن یه رگه‌ی درخشان طلا پیدا کردی!", "💎 بین سنگ‌ها یه تیکه سنگ قیمتی کشف کردی!"],
    "نگهبان": ["🛡 تا صبح دروازه‌ی شهر رو نگهبانی دادی و هیچ دزدی رد نشد!", "🗼 از برج دیده‌بانی یه گروه مشکوک رو لو دادی!"],
    "تاجر": ["💰 یه معامله‌ی پرسود بستی و کیسه‌ت سنگین شد!", "🐪 کاروان ادویه رو سالم به مقصد رسوندی!"],
    "راهزن": ["🏴‍☠️ یه کاروان بی‌دفاع رو غافلگیر کردی!", "🌙 نصف شب از انبار یه تاجر ثروتمند رد شدی!"],
}
ADV_WIN = ["🐉 اژدهای آتشین رو شکست دادی و روی گنجش نشستی!",
           "💎 یه غار پر از جواهر پیدا کردی!",
           "🏴‍☠️ گنج دزدان دریایی رو کشف کردی!",
           "🗝 صندوق گمشده‌ی پادشاه قدیمی رو باز کردی!",
           "🧙 جادوگر پیر ازت راضی شد و پاداش داد!",
           "🏰 قلعه‌ی ارواح رو تسخیر کردی!"]
ADV_LOSE = ["☠️ تو جنگل تاریک گم شدی و دزدها گیرت انداختن!",
            "🐺 گرگ‌های وحشی بهت حمله کردن و فرار کردی!",
            "🌋 تو غار آتشفشانی غافلگیر شدی!",
            "🕸 عنکبوت‌های غول‌پیکر تو تار گیرت انداختن!",
            "👻 روح‌های سرگردان ازت باج گرفتن!"]
LOVE_LINES = ["💞 {a} برای {b} یه دسته گل رز چید 🌹 و {b} از خوشحالی پرواز کرد!",
              "🥰 {a} و {b} زیر نور ماه قدم زدن و دل‌هاشون رو بهم دادن 🌙",
              "💌 {a} یه نامه‌ی عاشقانه برای {b} نوشت و قلب {b} لرزید!",
              "🍷 {a} و {b} یه شام رمانتیک خوردن 🕯 و کلی خندیدن!",
              "💍 {a} دوباره به {b} گفت «دوستت دارم» و عشقشون قوی‌تر شد!"]

# رویداد -> ایموجی‌های مناسب برای انتخاب استیکر
EVENT_EMOJI = {
    "welcome": ["🎉", "⚔️", "🔥", "🤩"], "start": ["👋", "🤩", "😍"], "created": ["🎉", "🥳", "😎"],
    "levelup": ["🏆", "🎉", "🤩", "🥳"], "daily": ["🎁", "😍", "🤗"], "work": ["💪", "😎", "🔨"],
    "point": ["⭐", "🤩", "😊"], "win": ["😎", "🏆", "🔥", "🤑"], "lose": ["😭", "💔", "😢", "😱"],
    "duel": ["⚔️", "🔥", "😎"], "profile": ["😎", "👑", "🔥"], "love": ["😍", "❤️", "🥰", "💞"],
    "marry": ["💍", "😍", "🥰", "🎉"], "divorce": ["💔", "😭", "😢"],
    "achievement": ["🏆", "🎉", "🤩", "🥳"], "wheel": ["🎉", "🤑", "😍"],
    "chest": ["🤑", "🎉", "😍"], "tutorial": ["🎉", "🥳", "🤩"], "fal": ["🤩", "😍", "🥰"],
    "pet": ["😍", "🥰", "🤗"], "hatch": ["🥳", "🎉", "😍"], "world": ["😱", "🔥", "💪"],
    "worldwin": ["🏆", "🎉", "🥳", "😎"],
    "season": ["🏆", "🎉", "🥳", "🤩"], "forge": ["🔥", "😎", "💪"], "market": ["🤑", "😎", "🤝"],
    "boss": ["😱", "🔥", "😈"], "bosswin": ["🏆", "🎉", "🥳", "😎"], "bossfail": ["😭", "😢", "💔"],
}

CATEGORIES = {"tool": "⛏ ابزار کار", "weapon": "⚔️ سلاح", "armor": "🛡 زره و سپر",
              "charm": "🍀 طلسم", "misc": "🧰 متفرقه"}
SLOTS = ("tool", "weapon", "armor", "charm")
SLOT_LABELS = {"tool": "⛏ ابزار", "weapon": "⚔️ سلاح", "armor": "🛡 زره", "charm": "🍀 طلسم"}
CONSUMABLE_MAX = 10
ENEMIES = ["اسکلت", "عنکبوت غول‌پیکر", "گابلین", "خفاش‌های وحشی", "نگهبان سنگی", "روح سرگردان"]

# کلاس‌ها: (عنوان، توضیح)
CLASSES = {
    "warrior": ("⚔️ جنگجو", "+۵ قدرت در دوئل و ۵٪ کاهش خسارت (ماجراجویی/سرداب)"),
    "mage": ("🔮 جادوگر", "+۱ XP اضافه در هر فعالیت"),
    "hunter": ("🏹 شکارچی", "+۲ سکه اضافه در هر کار"),
    "ninja": ("🥷 نینجا", "+۵٪ شانس دزدی و ۲۵٪ شانس فرار از جریمه"),
    "alchemist": ("⚗️ کیمیاگر", "۲۰٪ تخفیف مصرفی‌ها و معجون قوی‌تر (جان ۴۰ به‌جای ۲۵)"),
}
GENDERS = {"m": "👨 مرد", "f": "👩 زن"}

# ارقام فارسی/عربی -> انگلیسی، و ي/ك عربی -> ی/ک فارسی
NORMALIZE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك",
                          "01234567890123456789یک")
NAME_RE = re.compile(r"[\w\u200c ]{2,16}")
GUILD_NAME_RE = re.compile(r"[\w\u200c ]{3,24}")

# ============================== دیتابیس ==============================
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)  # autocommit
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA busy_timeout=5000")
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', coins INTEGER NOT NULL DEFAULT 100);
CREATE TABLE IF NOT EXISTS items(
    user_id INTEGER, item TEXT, qty INTEGER DEFAULT 0, PRIMARY KEY(user_id, item));
CREATE TABLE IF NOT EXISTS cities(chat_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS last_point(
    user_id INTEGER, chat_id INTEGER, ts REAL, PRIMARY KEY(user_id, chat_id));
CREATE TABLE IF NOT EXISTS banned(user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS bank(
    user_id INTEGER PRIMARY KEY, amount INTEGER DEFAULT 0, ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS daily_stats(
    user_id INTEGER, day TEXT, work INTEGER DEFAULT 0, adv INTEGER DEFAULT 0,
    point INTEGER DEFAULT 0, claimed TEXT DEFAULT '', PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS equipped(
    user_id INTEGER NOT NULL, slot TEXT NOT NULL, item TEXT NOT NULL,
    PRIMARY KEY(user_id, slot));
CREATE TABLE IF NOT EXISTS friends(
    a INTEGER NOT NULL, b INTEGER NOT NULL, since REAL NOT NULL,
    PRIMARY KEY(a, b), CHECK(a < b));
CREATE TABLE IF NOT EXISTS friend_requests(
    from_id INTEGER NOT NULL, to_id INTEGER NOT NULL, chat_id INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL, PRIMARY KEY(from_id, to_id));
CREATE TABLE IF NOT EXISTS guilds(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    owner_id INTEGER NOT NULL, created REAL NOT NULL, description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS guild_members(
    user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member', joined REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_guild_members_guild ON guild_members(guild_id);
CREATE TABLE IF NOT EXISTS duel_requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, challenger INTEGER NOT NULL, target INTEGER NOT NULL,
    stake INTEGER NOT NULL, chat_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS dungeon_runs(
    user_id INTEGER PRIMARY KEY, stage INTEGER NOT NULL, hp INTEGER NOT NULL,
    loot INTEGER NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS marriages(
    a INTEGER NOT NULL, b INTEGER NOT NULL, since REAL NOT NULL,
    PRIMARY KEY(a, b), CHECK(a < b));
CREATE TABLE IF NOT EXISTS marriage_requests(
    from_id INTEGER NOT NULL, to_id INTEGER NOT NULL, chat_id INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL, PRIMARY KEY(from_id, to_id));
CREATE TABLE IF NOT EXISTS event_stickers(
    event TEXT NOT NULL, file_id TEXT NOT NULL, PRIMARY KEY(event, file_id));
CREATE TABLE IF NOT EXISTS chats(
    chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
    added REAL NOT NULL DEFAULT 0, last_active REAL NOT NULL DEFAULT 0, boss_next REAL NOT NULL DEFAULT 0,
    boss_kills INTEGER NOT NULL DEFAULT 0, score INTEGER NOT NULL DEFAULT 0,
    invited_by INTEGER NOT NULL DEFAULT 0, invite_paid INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chat_players(
    chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, ts REAL NOT NULL, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS bosses(
    chat_id INTEGER PRIMARY KEY, name TEXT NOT NULL, emoji TEXT NOT NULL, max_hp INTEGER NOT NULL,
    hp INTEGER NOT NULL, spawned REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS boss_damage(
    chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, dmg INTEGER NOT NULL DEFAULT 0,
    hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS achievements(
    user_id INTEGER NOT NULL, key TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY(user_id, key));
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notices(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_notices_user ON notices(user_id);
CREATE TABLE IF NOT EXISTS season_points(
    season INTEGER NOT NULL, user_id INTEGER NOT NULL, pts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(season, user_id));
CREATE INDEX IF NOT EXISTS idx_sp_rank ON season_points(season, pts DESC);
CREATE TABLE IF NOT EXISTS season_results(
    season INTEGER NOT NULL, place INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL,
    pts INTEGER NOT NULL, PRIMARY KEY(season, place));
CREATE TABLE IF NOT EXISTS season_titles(
    user_id INTEGER NOT NULL, season INTEGER NOT NULL, place INTEGER NOT NULL, title TEXT NOT NULL,
    PRIMARY KEY(user_id, season));
CREATE TABLE IF NOT EXISTS road_claims(
    season INTEGER NOT NULL, user_id INTEGER NOT NULL, tier INTEGER NOT NULL, PRIMARY KEY(season, user_id, tier));
CREATE TABLE IF NOT EXISTS item_plus(
    user_id INTEGER NOT NULL, item TEXT NOT NULL, plus INTEGER NOT NULL DEFAULT 0,
    fails INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, item));
CREATE TABLE IF NOT EXISTS market(
    id INTEGER PRIMARY KEY AUTOINCREMENT, seller INTEGER NOT NULL, item TEXT NOT NULL,
    price INTEGER NOT NULL, ts REAL NOT NULL, expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_market_seller ON market(seller);
CREATE TABLE IF NOT EXISTS pets(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, species TEXT NOT NULL, name TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0, fed_at REAL NOT NULL DEFAULT 0, played_at REAL NOT NULL DEFAULT 0,
    trip_kind INTEGER NOT NULL DEFAULT 0, trip_end REAL NOT NULL DEFAULT 0, born REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_pets_user ON pets(user_id);
CREATE TABLE IF NOT EXISTS incubator(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, tier INTEGER NOT NULL, ready REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_incubator_user ON incubator(user_id);
CREATE TABLE IF NOT EXISTS world_boss(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, emoji TEXT NOT NULL, max_hp INTEGER NOT NULL,
    hp INTEGER NOT NULL, t_start REAL NOT NULL, t_end REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS world_damage(
    boss_id INTEGER NOT NULL, user_id INTEGER NOT NULL, dmg INTEGER NOT NULL DEFAULT 0,
    hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(boss_id, user_id));
CREATE TABLE IF NOT EXISTS world_chat_damage(
    boss_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, dmg INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(boss_id, chat_id));
CREATE TABLE IF NOT EXISTS tutorial(
    user_id INTEGER NOT NULL, step TEXT NOT NULL, state INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, step));
CREATE TABLE IF NOT EXISTS chests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, ts REAL NOT NULL, tier INTEGER NOT NULL,
    claimed_by INTEGER NOT NULL DEFAULT 0, claimed_ts REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_chests_chat ON chests(chat_id);
""")


def ensure_columns(table, cols):
    """ستون‌های جدید رو به دیتابیس قدیمی اضافه می‌کنه (اطلاعات قبلی پاک نمی‌شه)."""
    have = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
    for name, decl in cols.items():
        if name not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


_INT0 = "INTEGER NOT NULL DEFAULT 0"
_REAL0 = "REAL NOT NULL DEFAULT 0"
_TXT0 = "TEXT NOT NULL DEFAULT ''"
ensure_columns("users", {
    "xp": _INT0, "work_count": _INT0, "adv_count": _INT0, "streak": _INT0, "job": _TXT0,
    "gender": _TXT0, "cls": _TXT0, "created": _REAL0,
    "last_work": _REAL0, "last_adv": _REAL0, "last_daily": _REAL0, "last_rob": _REAL0,
    "last_robbed": _REAL0, "last_duel": _REAL0, "last_dungeon": _REAL0, "last_bet": _REAL0,
    "chat_reward_day": _TXT0, "chat_reward_total": _INT0, "chat_reward_ts": _REAL0,
    "duel_wins": _INT0, "duel_losses": _INT0, "last_love": _REAL0,
    "last_hit": _REAL0, "invites": _INT0, "boss_kills": _INT0,
    "last_wheel": _REAL0, "wheel_spins": _INT0, "market_sales": _INT0,
    "active_pet": _INT0, "last_world": _REAL0, "world_wins": _INT0, "trips": _INT0, "hatched": _INT0,
    "pet_gift": _INT0, "referred_by": _INT0, "ref_paid": _INT0, "refs": _INT0,
    "fal_day": _INT0, "fal_kind": _TXT0, "fal_n": _INT0, "chest_day": _INT0, "chest_n": _INT0,
})
ensure_columns("chats", {"season_seen": _INT0, "world_spawn_seen": _INT0, "world_end_seen": _INT0,
                         "chest_next": _REAL0, "digest_day": _INT0, "digest_off": _INT0})
ensure_columns("daily_stats", {"sent": _INT0})
ensure_columns("friend_requests", {"chat_id": _INT0})

_TIME_COLS = {"last_work", "last_adv", "last_daily", "last_rob", "last_duel",
              "last_dungeon", "last_bet", "last_love", "last_hit", "last_wheel", "last_world"}
_STAT_COLS = {"work", "adv", "point"}
_tx_depth = 0


@contextmanager
def tx():
    """تراکنش امن (BEGIN IMMEDIATE). داخلش هیچ‌وقت await نکن. تو‌در‌تو هم مشکلی نداره."""
    global _tx_depth
    if _tx_depth:
        _tx_depth += 1
        try:
            yield
        finally:
            _tx_depth -= 1
        return
    db.execute("BEGIN IMMEDIATE")
    _tx_depth = 1
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")
    finally:
        _tx_depth = 0


def backup_db():
    try:
        dst = sqlite3.connect(DB_PATH + ".bak")
        db.backup(dst)
        dst.close()
    except Exception:
        logging.exception("backup failed")


def cleanup_old():
    t = time.time()
    db.execute("DELETE FROM duel_requests WHERE created<?", (t - 86400,))
    db.execute("DELETE FROM friend_requests WHERE ts<?", (t - 7 * 86400,))
    db.execute("DELETE FROM dungeon_runs WHERE ts<?", (t - 86400,))


# ============================== کمکی‌ها ==============================
def clean_name(s):
    return re.sub(r"\s+", " ", (s or "").strip())[:32] or "بازیکن"


def get_user(tg_user):
    name = clean_name(getattr(tg_user, "first_name", None))
    db.execute("INSERT INTO users(id, name) VALUES(?, ?) ON CONFLICT(id) DO NOTHING",
               (tg_user.id, name))
    # تا وقتی شخصیت نساخته، اسم از تلگرام همگام می‌شه؛ بعدش اسم شخصیت ثابته
    db.execute("UPDATE users SET name=? WHERE id=? AND cls='' AND name<>?",
               (name, tg_user.id, name))
    return user_by_id(tg_user.id)


def user_by_id(uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def has_char(u):
    return bool(u) and u["gender"] in GENDERS and u["cls"] in CLASSES


async def check_membership(ctx, uid):
    """عضویت کانال اجباری را چک می‌کند.
    گروه خصوصی فقط لینک دعوت نشان داده می‌شود (چک سخت برای invite link ممکن نیست).
    برمی‌گرداند: (ok: bool, (text, kb) یا None)"""
    missing_channel = False
    if REQUIRED_CHANNEL:
        try:
            m = await ctx.bot.get_chat_member(f"@{REQUIRED_CHANNEL}", uid)
            if m.status in ("left", "kicked"):
                missing_channel = True
        except Exception as e:
            # ربات باید ادمین کانال باشد؛ در غیر این صورت چک را رد می‌کنیم تا بازی قفل نشود
            logging.info("check_membership channel @%s: %s", REQUIRED_CHANNEL, e)

    # اگر کانال اوکی بود و گروه اجباری نداریم → اجازه بده
    if not missing_channel and not REQUIRED_GROUP:
        # حتی اگر کانال اوکی باشد، اگر لینک گروه داریم هنوز دکمه‌اش را نشان نده (فقط وقتی کم است)
        return True, None

    if not missing_channel and REQUIRED_GROUP:
        # گروه عمومی با یوزرنیم
        try:
            m = await ctx.bot.get_chat_member(f"@{REQUIRED_GROUP}", uid)
            if m.status not in ("left", "kicked"):
                return True, None
        except Exception as e:
            logging.info("check_membership group @%s: %s", REQUIRED_GROUP, e)
            return True, None  # در صورت خطا قفل نکن

    lines = ["🔒 برای ورود به سرزمین ماجراجویی باید عضو شی:\n"]
    buttons = []
    if missing_channel or REQUIRED_CHANNEL:
        lines.append(f"• کانال رسمی: @{REQUIRED_CHANNEL}")
        buttons.append([Btn("📢 عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL}")])
    if REQUIRED_GROUP:
        lines.append(f"• گروه بازی: @{REQUIRED_GROUP}")
        buttons.append([Btn("👥 ورود به گروه", url=f"https://t.me/{REQUIRED_GROUP}")])
    elif REQUIRED_GROUP_INVITE:
        lines.append("• گروه بازی (لینک دعوت)")
        buttons.append([Btn("👥 ورود به گروه", url=REQUIRED_GROUP_INVITE)])
    lines.append("\nبعد از عضویت دوباره دستور رو بزن ✅")
    # اگر فقط لینک گروه داریم و کانال اوکی است، اجبار سخت نکن (گروه خصوصی)
    if not missing_channel and not REQUIRED_GROUP:
        return True, None
    return False, ("\n".join(lines), Markup(buttons) if buttons else None)


def is_admin(uid):
    return uid in ADMIN_IDS


def is_banned(uid):
    return db.execute("SELECT 1 FROM banned WHERE user_id=?", (uid,)).fetchone() is not None


def class_key(uid):
    u = user_by_id(uid)
    return u["cls"] if u and u["cls"] in CLASSES else ""


def xp_for_level(n):
    return 60 * (n - 1) ** 2


def level_of(xp):
    lvl = 1
    while lvl < LEVEL_CAP and xp >= xp_for_level(lvl + 1):
        lvl += 1
    return lvl


def title_of(level):
    t = TITLES[0][1]
    for lv, name in TITLES:
        if level >= lv:
            t = name
    return t


def grant_xp(uid, amount):
    """XP می‌ده (جادوگر +۱). برمی‌گردونه: (مقدار واقعی، متن لول‌آپ یا '')."""
    if class_key(uid) == "mage":
        amount += 1
    amount = max(1, int(round(amount * xp_mult() * (1 + (pet_bonus(uid, "xp") + fal_bonus(uid, "xp")) / 100))))
    add_sp(uid, amount)
    pet_gain(uid, max(1, amount // 2))
    old = user_by_id(uid)["xp"]
    new = old + amount
    db.execute("UPDATE users SET xp=? WHERE id=?", (new, uid))
    lo, ln = level_of(old), level_of(new)
    if ln <= lo:
        return amount, ""
    unlocked = [UNLOCK_TEXT[lv] for lv in range(lo + 1, ln + 1) if lv in UNLOCK_TEXT]
    flavor = LEVEL_UP_FLAVOR.get(ln) or LEVEL_UP_FLAVOR.get(max(k for k in LEVEL_UP_FLAVOR if k <= ln), "قوی‌تر شدی! ادامه بده 🔥")
    text = f"\n\n🎊🎉 لول‌آپ! 🎉🎊\n⭐ حالا لول {ln} هستی — لقب: {title_of(ln)}\n💬 {flavor}"
    if unlocked:
        text += "\n🔓 باز شد:\n• " + "\n• ".join(unlocked)
    # دستورهای مهم این لول
    cmds = {
        2: "«ماجراجویی» • «جایزه»",
        3: "«بانک» • «واریز» • «برداشت»",
        4: "«انتقال» (با ریپلای)",
        5: "«شغل»",
        6: "«ماموریت»",
        7: "«شهر»",
        8: "«دزدی» • «ازدواج» (با ریپلای)",
        9: "«سرداب»",
        10: "«دوئل» (با ریپلای)",
        12: "«شرط»",
    }
    new_cmds = [cmds[lv] for lv in range(lo + 1, ln + 1) if lv in cmds]
    if new_cmds:
        text += "\n🎮 دستورهای جدید: " + " | ".join(new_cmds)
    return amount, text


def fmt_time(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def bar(cur, total, n=10):
    filled = n if total <= 0 else max(0, min(n, int(n * cur / total)))
    return "█" * filled + "░" * (n - filled)


def cd_left(u, col, seconds):
    return u[col] + seconds - time.time()


def set_time(uid, col):
    assert col in _TIME_COLS
    db.execute(f"UPDATE users SET {col}=? WHERE id=?", (time.time(), uid))


def today():
    return time.strftime("%Y-%m-%d")


def bump(uid, col):
    assert col in _STAT_COLS
    db.execute("INSERT OR IGNORE INTO daily_stats(user_id, day) VALUES(?, ?)", (uid, today()))
    db.execute(f"UPDATE daily_stats SET {col}={col}+1 WHERE user_id=? AND day=?", (uid, today()))


def parse_int(word):
    word = (word or "").translate(NORMALIZE)
    return int(word) if word.isascii() and word.isdigit() and len(word) <= 12 else None


def parse_amount(word, available):
    return available if word in ("همه", "all") else parse_int(word)


def add_coins(uid, delta):
    db.execute("UPDATE users SET coins=MAX(0, coins+?) WHERE id=?", (delta, uid))


def spend(uid, amount):
    cur = db.execute("UPDATE users SET coins=coins-? WHERE id=? AND coins>=?", (amount, uid, amount))
    return cur.rowcount == 1


def qty(uid, item):
    r = db.execute("SELECT qty FROM items WHERE user_id=? AND item=?", (uid, item)).fetchone()
    return r["qty"] if r else 0


def owned(uid):
    return {r["item"]: r["qty"] for r in
            db.execute("SELECT item, qty FROM items WHERE user_id=? AND qty>0", (uid,))}


def use_one(uid, item):
    db.execute("UPDATE items SET qty=qty-1 WHERE user_id=? AND item=? AND qty>0", (uid, item))


def req_text(key):
    req = ITEM_REQ.get(key)
    if not req:
        return ""
    kind, val = req
    return CLASSES[val][0] if kind == "cls" else f"شغل {val}"


def req_label(key):
    t = req_text(key)
    return f" [ویژه‌ی {t}]" if t else ""


# سلاح‌های شمشیری عمومی فقط برای جنگجو و نینجا (جادوگر عصا، شکارچی کمان، کیمیاگر قمقمه می‌خواد)
SWORD_KEYS = {"weap1", "weap2", "weap3", "weap4", "weap5", "weap6"}
SWORD_OK_CLASSES = {"warrior", "ninja"}


def item_usable(u, key):
    if not u:
        return True
    # محدودیت سلاح عمومی
    if key in SWORD_KEYS and u["cls"] not in SWORD_OK_CLASSES and u["cls"] in CLASSES:
        return False
    req = ITEM_REQ.get(key)
    if not req:
        return True
    kind, val = req
    return (u["cls"] if kind == "cls" else u["job"]) == val


def best_owned(uid, slot, have=None):
    have = owned(uid) if have is None else have
    u = user_by_id(uid)
    best = None
    for key in have:
        it = ITEMS.get(key)
        if it and it[1] == slot and item_usable(u, key) and (best is None or enhanced_power(uid, key) > enhanced_power(uid, best)):
            best = key
    return best


def equipped_items(uid):
    """تجهیزات فعال. اگه جایگاه خالی باشه و وسیله داشته باشه، بهترین رو خودکار فعال می‌کنه."""
    rows = {r["slot"]: r["item"] for r in
            db.execute("SELECT slot, item FROM equipped WHERE user_id=?", (uid,))}
    have = owned(uid)
    u_row = user_by_id(uid)
    for slot in SLOTS:
        key = rows.get(slot)
        if key and (key not in have or key not in ITEMS or ITEMS[key][1] != slot
                    or not item_usable(u_row, key)):
            db.execute("DELETE FROM equipped WHERE user_id=? AND slot=?", (uid, slot))
            rows.pop(slot, None)
            key = None
        if not key:
            cand = best_owned(uid, slot, have)
            if cand:
                db.execute("INSERT OR REPLACE INTO equipped(user_id, slot, item) VALUES(?,?,?)",
                           (uid, slot, cand))
                rows[slot] = cand
    return rows


def best_power(uid, slot):
    key = equipped_items(uid).get(slot)
    return enhanced_power(uid, key) if key in ITEMS else 0


def reward_mult(uid):
    return 1 + best_power(uid, "charm") / 100


def item_price(u, key):
    price = int(ITEMS[key][2] * season_perk("shop"))
    return int(price * 0.8) if u["cls"] == "alchemist" and ITEMS[key][1] == "misc" else price


def guild_of(uid):
    return db.execute("SELECT g.id, g.name, m.role FROM guild_members m "
                      "JOIN guilds g ON g.id=m.guild_id WHERE m.user_id=?", (uid,)).fetchone()


def guild_bonus(uid):
    """بونوس کار انجمن: هر ۳ عضو = ۱٪ (حداکثر ۱۰٪)."""
    n = db.execute("SELECT COUNT(*) FROM guild_members WHERE guild_id="
                   "(SELECT guild_id FROM guild_members WHERE user_id=?)", (uid,)).fetchone()[0]
    return min(10, n // 3)


async def safe_edit(q, text, kb=None):
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception as e:
        if "not modified" not in str(e):
            logging.warning("safe_edit failed: %s", e)


# ============================== استیکر ==============================
_sticker_cache = {}


async def _load_set(bot, name):
    if name in _sticker_cache:
        return _sticker_cache[name]
    try:
        st = await bot.get_sticker_set(name)
        _sticker_cache[name] = [(x.file_id, (x.emoji or "").replace("\ufe0f", "")) for x in st.stickers]
    except Exception as e:
        logging.info("پک استیکر %s در دسترس نیست: %s", name, e)
        _sticker_cache[name] = []
    return _sticker_cache[name]


async def pick_sticker(bot, event):
    rows = db.execute("SELECT file_id FROM event_stickers WHERE event=?", (event,)).fetchall()
    if rows:  # استیکرهایی که ادمین برای این رویداد ثبت کرده اولویت دارن
        return random.choice(rows)["file_id"]
    want = {e.replace("\ufe0f", "") for e in EVENT_EMOJI.get(event, ["🎉"])}
    pool = []
    for name in STICKER_SETS:
        pool += [fid for fid, em in await _load_set(bot, name) if em in want]
    return random.choice(pool) if pool else None


async def send_event_sticker(ctx, chat_id, event, chance=None):
    """استیکر مناسب رویداد رو می‌فرسته؛ هر خطایی بی‌صدا نادیده گرفته می‌شه."""
    chance = STICKER_CHANCE if chance is None else chance
    if chance < 1 and random.random() > chance:
        return
    try:
        fid = await pick_sticker(ctx.bot, event)
        if fid:
            await ctx.bot.send_sticker(chat_id, fid)
    except Exception as e:
        logging.info("ارسال استیکر ناموفق: %s", e)


async def reply_game(update, ctx, text, event=None, chance=None):
    """جواب بازی + استیکر خیلی کم (فقط رویدادهای مهم)."""
    await update.message.reply_text(text)
    # استیکر فقط برای لول‌آپ و چند رویداد خیلی خاص، با شانس پایین
    if "🎊🎉" in text:
        await send_event_sticker(ctx, update.effective_chat.id, "levelup", 0.35)
    elif event in ("marry", "bosswin", "worldwin", "created"):
        await send_event_sticker(ctx, update.effective_chat.id, event, chance if chance is not None else 0.25)


WELCOME_TEXT = (
    "⚔️ <b>سرزمین ماجراجویی فعال شد!</b>\n\n"
    "از همین لحظه این گروه یه دنیای زنده‌ست:\n"
    "⛏ کار کن • 🐉 غول بکش • 💍 ازدواج کن\n"
    "🐾 همراه بپرورون • 🌟 توی فصل‌ها رقابت کن\n\n"
    "🎯 <b>قدم اول:</b>\n"
    "دکمه پایین رو بزن → توی پیوی شخصیت بساز → برگرد اینجا و بنویس <b>آموزش</b>\n\n"
    "💡 ادمین‌ها: ربات رو ادمین کنید تا همه دستورهای فارسی رو ببینه.")


async def on_bot_added(update, ctx):
    """وقتی ربات به گروهی اضافه می‌شه، خوش‌آمدگویی می‌کنه."""
    m = update.my_chat_member
    if not m or m.chat.type not in ("group", "supergroup"):
        return
    was_in = m.old_chat_member.status in ("member", "administrator", "creator", "restricted")
    now_in = m.new_chat_member.status in ("member", "administrator")
    if was_in or not now_in:
        return
    adder = getattr(m, "from_user", None)
    register_chat(m.chat, adder.id if adder and not adder.is_bot else 0)
    await send_event_sticker(ctx, m.chat.id, "welcome", 1.0)
    url = f"https://t.me/{ctx.bot.username}?start=create"
    try:
        await ctx.bot.send_message(m.chat.id, WELCOME_TEXT, parse_mode="HTML",
                                   reply_markup=Markup([[Btn("🎭 ساخت شخصیت", url=url)]]))
    except Exception as e:
        logging.warning("پیام خوش‌آمدگویی ارسال نشد: %s", e)


# ============================== ثبت دستورها و مسیریاب ==============================
class Cmd:
    __slots__ = ("fn", "args", "admin", "level")

    def __init__(self, fn, args, admin, level):
        self.fn, self.args, self.admin, self.level = fn, args, admin, level


REGISTRY = {}


def _key(s):
    return s.translate(NORMALIZE).replace("\u200c", "").replace("_", " ").strip().lower()


def command(*names, args=False, admin=False, level=0):
    """نام‌های انگلیسی فقط با اسلش کار می‌کنن (/work)؛ نام‌های فارسی بدون اسلش."""
    def deco(fn):
        c = Cmd(fn, args, admin, level)
        for n in names:
            REGISTRY[_key(n)] = c
        return fn
    return deco


def parse_command(text, bot_username):
    parts = text.translate(NORMALIZE).split()
    if not parts:
        return None
    first = parts[0]
    slash = first.startswith("/")
    first = first.lstrip("/")
    if "@" in first:
        first, _, target = first.partition("@")
        if target.lower() != (bot_username or "").lower():
            return None
        slash = True
    rest = parts[1:]
    if len(rest) >= 2:   # دستورهای سه‌کلمه‌ای مثل «احضار غول جهانی»
        c = REGISTRY.get(_key(first + " " + rest[0] + " " + rest[1]))
        if c and (c.args or not rest[2:]):
            return c, rest[2:]
    if rest:
        c = REGISTRY.get(_key(first + " " + rest[0]))
        if c and (c.args or not rest[1:]):
            return c, rest[1:]
    c = REGISTRY.get(_key(first))
    if not c or (first.isascii() and not slash):
        return None
    if rest and not c.args:
        return None  # کلمه‌ی عادی توی جمله؛ دستور حساب نمی‌شه
    return c, rest


_last_cmd, _nag = {}, {}


def flooding(uid):
    t = time.monotonic()
    if len(_last_cmd) > 5000:
        _last_cmd.clear()
    if t - _last_cmd.get(uid, 0) < FLOOD_GAP:
        return True
    _last_cmd[uid] = t
    return False


async def nag_create(update, ctx, force=False):
    uid, t = update.effective_user.id, time.monotonic()
    if not force and t - _nag.get(uid, 0) < 60:
        return
    if len(_nag) > 5000:
        _nag.clear()
    _nag[uid] = t
    url = f"https://t.me/{ctx.bot.username}?start=create"
    await update.message.reply_text(
        "🔒 ای ماجراجو! قبل از ورود به سرزمین باید توی پیوی ربات شخصیتت رو بسازی 🎭",
        reply_markup=Markup([[Btn("🎭 ساخت شخصیت", url=url)]]))


async def router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.message, update.effective_user
    if not msg or not msg.text or not user or user.is_bot:
        return
    chat = update.effective_chat
    if chat.type == "private":
        return await private_router(update, ctx)
    if chat.type not in ("group", "supergroup"):
        return
    if is_banned(user.id) and not is_admin(user.id):
        return
    touch_chat(chat, user.id)
    await boss_tick(ctx, chat.id)
    await season_tick(ctx, chat.id)
    await world_tick(ctx, chat.id)
    await chest_tick(ctx, chat.id)
    await digest_tick(ctx, chat.id)
    parsed = parse_command(msg.text, ctx.bot.username)
    if not parsed:
        return chat_reward(user.id, msg.text)
    cmd, args = parsed
    if cmd.admin and not is_admin(user.id):
        return
    if flooding(user.id):
        return
    u = get_user(user)
    if cmd.fn is not cmd_start and not has_char(u) and not is_admin(user.id):
        return await nag_create(update, ctx)
    # اجبار عضویت در کانال/گروه (اگر تنظیم شده باشد)
    if not is_admin(user.id) and (REQUIRED_CHANNEL or REQUIRED_GROUP):
        ok, payload = await check_membership(ctx, user.id)
        if not ok:
            text, kb = payload
            return await msg.reply_text(text, reply_markup=kb)
    lvl = level_of(u["xp"])
    if cmd.level and lvl < cmd.level and not is_admin(user.id):
        return await msg.reply_text(
            f"🔒 این قابلیت از لول {cmd.level} باز می‌شه. لول تو: {lvl}\n"
            "با کار کردن، پوینت گرفتن و بازی XP جمع کن.")
    await cmd.fn(update, ctx, args)
    await ach_announce(ctx, chat.id, user.id)


async def private_router(update, ctx):
    msg, user = update.message, update.effective_user
    if is_banned(user.id) and not is_admin(user.id):
        return
    text = msg.text.translate(NORMALIZE).strip()
    parts = text.split()
    first = parts[0].lstrip("/").split("@")[0].lower() if parts else ""
    if text.startswith("/") and first in ("start", "شروع"):
        return await cmd_start(update, ctx, parts[1:])
    state = ctx.user_data.get("creating")
    if state and not text.startswith("/"):
        name = re.sub(r"\s+", " ", text)
        if not NAME_RE.fullmatch(name):
            return await msg.reply_text("اسم نامعتبره. ۲ تا ۱۶ حرف (فارسی/انگلیسی/عدد) بفرست.")
        ctx.user_data.pop("creating", None)
        u = get_user(user)
        if create_character(user.id, state["gender"], state["cls"], name):
            await msg.reply_text(created_text(user_by_id(user.id)))
            return await send_event_sticker(ctx, update.effective_chat.id, "created", 1.0)
        return await msg.reply_text("شخصیتت قبلاً ساخته شده.")
    u = get_user(user)
    if has_char(u):
        return await msg.reply_text("🎮 بازی فقط داخل گروه‌ها انجام می‌شه. برای دیدن دستورها توی گروه «راهنما» رو بزن.")
    await msg.reply_text("برای ساخت شخصیت /start رو بزن.")


async def callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    if not q.message:
        return await q.answer()
    if is_banned(q.from_user.id) and not is_admin(q.from_user.id):
        return await q.answer()
    data = q.data or ""
    chat = q.message.chat
    if chat.type == "private":
        if data.startswith("char_"):
            return await character_callbacks(update, ctx)
        return await q.answer("بازی فقط در گروه‌ها قابل اجراست.", show_alert=True)
    if chat.type not in ("group", "supergroup"):
        return await q.answer()
    u = get_user(q.from_user)
    if not has_char(u) and not is_admin(q.from_user.id):
        return await q.answer("اول توی پیوی ربات شخصیت بساز.", show_alert=True)
    handler = CALLBACKS.get(data.split(":", 1)[0])
    if handler:
        await handler(update, ctx)
        return await ach_announce(ctx, chat.id, q.from_user.id)
    await q.answer()


async def on_error(update, ctx):
    logging.error("Unhandled error", exc_info=ctx.error)
    if isinstance(ctx.error, NetworkError):
        return
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ یه خطای داخلی پیش اومد. دوباره تلاش کن.")
    except Exception:
        pass


# ============================== ساخت شخصیت (فقط در پیوی) ==============================
def gender_kb():
    return Markup([[Btn(GENDERS["m"], "char_gender:m"), Btn(GENDERS["f"], "char_gender:f")]])


def class_kb(gender):
    return Markup([[Btn(v[0], f"char_class:{gender}:{k}")] for k, v in CLASSES.items()])


def create_character(uid, gender, cls, name):
    if gender not in GENDERS or cls not in CLASSES:
        return False
    with tx():
        u = user_by_id(uid)
        if not u or has_char(u):
            return False
        db.execute("UPDATE users SET gender=?, cls=?, created=?, name=? WHERE id=?",
                   (gender, cls, time.time(), name, uid))
        if u["referred_by"]:   # با لینک دعوت یه دوست اومده: هدیه‌ی خوش‌آمد، و به دوستش خبر می‌دیم
            add_coins(uid, REF_WELCOME)
            give_item(uid, "egg1")
            notify(u["referred_by"], f"🤝 {name} با لینک دعوت تو شخصیت ساخت!\n"
                                     f"🏆 وقتی به لول ۵ برسه، جایزه‌ی دعوتت ({REF_REWARD:,} سکه + 🥚 تخم) می‌رسه.")
    return True


def created_text(u):
    return (f"🎉 شخصیتت ساخته شد!\n━━━━━━━━━━━━━━\n"
            f"👤 {u['name']}  {GENDERS[u['gender']]}\n"
            f"🎭 {CLASSES[u['cls']][0]}\n✨ {CLASSES[u['cls']][1]}\n"
            "━━━━━━━━━━━━━━\n"
            "⭐ لول ۱ شدی!\n\n"
            "🔥 چطور پول و XP دربیاری؟\n"
            "• «کار» → سکه + XP (هر ۵ دقیقه)\n"
            "• «پوینت» → سکه رایگان\n"
            "• از لول ۲: «ماجراجویی» و «جایزه» روزانه\n\n"
            "🚀 قدم بعدی:\n"
            "۱. برو توی گروه بازی\n"
            "۲. بنویس «آموزش» (جایزه‌های شروع)\n"
            "۳. «فروشگاه» رو ببین و تجهیزات کلاس خودت رو بخر\n\n"
            "💡 کلاس تو وسایل مخصوص خودش رو داره — جادوگر عصا می‌گیره، جنگجو شمشیر!\n"
            "🔒 بازی فقط داخل گروه فعال هست.")


@command("start", "شروع")
async def cmd_start(update, ctx, args):
    user, msg = update.effective_user, update.message
    if not user or user.is_bot or not msg:
        return
    u = get_user(user)
    if update.effective_chat.type != "private":
        if has_char(u):
            return await msg.reply_text("✅ شخصیتت آماده‌ست؛ بازی رو همین‌جا با دستورهای گروه انجام بده.\nبنویس «راهنما» یا «آموزش».")
        return await nag_create(update, ctx, force=True)
    ctx.user_data.pop("creating", None)
    # اجبار عضویت قبل از ساخت شخصیت
    if not is_admin(user.id) and (REQUIRED_CHANNEL or REQUIRED_GROUP):
        ok, payload = await check_membership(ctx, user.id)
        if not ok:
            text, kb = payload
            return await msg.reply_text(
                "👋 اول باید عضو شی تا بتونی بازی کنی:\n\n" + text,
                reply_markup=kb)
    ref_note = ""
    if args and args[0].startswith("ref_") and args[0][4:].isdigit() and register_ref(u, int(args[0][4:])):
        ref_note = ("🤝 یه دوستت دعوتت کرده! با ساخت شخصیت هدیه‌ی ویژه می‌گیری "
                    f"({REF_WELCOME:,} سکه + 🥚 تخم) 🎁\n\n")
    if has_char(u):
        return await msg.reply_text(
            f"🏰 خوش برگشتی {u['name']}!\n━━━━━━━━━━━━━━\n"
            f"{GENDERS[u['gender']]} | {CLASSES[u['cls']][0]} | لول {level_of(u['xp'])}\n\n"
            "🎮 برو توی گروه و بازی کن.\n"
            "برای شروع سریع بنویس «آموزش» یا «راهنما».")
    await msg.reply_text(
        ref_note +
        "⚔️ به سرزمین ماجراجویی خوش اومدی!\n━━━━━━━━━━━━━━\n"
        "اینجا کار می‌کنی، غول می‌کشی، همراه می‌پرورونی و با دوستات رقابت می‌کنی.\n\n"
        "🌟 اول شخصیتت رو بساز. جنسیت رو انتخاب کن:",
        reply_markup=gender_kb())


async def character_callbacks(update, ctx):
    q = update.callback_query
    u = get_user(q.from_user)
    if has_char(u):
        return await q.answer("شخصیتت قبلاً ساخته شده.", show_alert=True)
    parts = (q.data or "").split(":")
    action = parts[0]
    if action == "char_gender" and len(parts) == 2 and parts[1] in GENDERS:
        g = parts[1]
        await q.answer()
        return await safe_edit(
            q, f"{GENDERS[g]} انتخاب شد.\n\nحالا کلاس شخصیتت رو انتخاب کن:\n\n" +
            "\n".join(f"{v[0]} — {v[1]}" for v in CLASSES.values()), class_kb(g))
    if action in ("char_class", "char_ask", "char_done") and len(parts) == 3 \
            and parts[1] in GENDERS and parts[2] in CLASSES:
        g, c = parts[1], parts[2]
        tg_name = clean_name(q.from_user.first_name)
        if action == "char_class":
            await q.answer()
            kb = Markup([
                [Btn(f"✅ همین اسم: {tg_name[:20]}", f"char_done:{g}:{c}")],
                [Btn("✏️ اسم دلخواه", f"char_ask:{g}:{c}")],
                [Btn("↩️ برگشت", f"char_gender:{g}")]])
            return await safe_edit(
                q, f"{GENDERS[g]} | {CLASSES[c][0]}\n✨ {CLASSES[c][1]}\n\nاسم شخصیتت چی باشه؟", kb)
        if action == "char_ask":
            ctx.user_data["creating"] = {"gender": g, "cls": c}
            await q.answer()
            return await safe_edit(q, "✏️ اسم شخصیتت رو بفرست (۲ تا ۱۶ حرف، فارسی/انگلیسی/عدد).")
        ctx.user_data.pop("creating", None)
        if create_character(q.from_user.id, g, c, tg_name):
            await q.answer("شخصیت ساخته شد! 🎉")
            await safe_edit(q, created_text(user_by_id(q.from_user.id)))
            return await send_event_sticker(ctx, q.message.chat_id, "created", 1.0)
        return await q.answer("ساخت شخصیت انجام نشد.", show_alert=True)
    await q.answer()


# ============================== راهنما و پروفایل ==============================
@command("راهنما", "help")
async def cmd_help(update, ctx, args):
    await update.message.reply_text(
        "⚔️ <b>راهنمای سریع</b>\n"
        "━━━━━━━━━━━━━━\n"
        "🔥 <b>پول و XP دربیار</b>\n"
        "کار • پوینت • ماجراجویی • جایزه\n\n"
        "🛒 <b>رشد کن</b>\n"
        "فروشگاه • کوله • شغل • آهنگری • بانک\n\n"
        "⚔️ <b>بجنگ</b>\n"
        "غول • حمله • دوئل • سرداب • دزدی\n\n"
        "🐾 <b>همراه و شانس</b>\n"
        "همراه • تخم • چرخ • فال • صندوق گنج\n\n"
        "💍 <b>اجتماعی</b>\n"
        "ازدواج • انجمن • دوست • دعوت دوست\n\n"
        "🌟 <b>فصل و رقابت</b>\n"
        "فصل • جاده • برترین • غول جهانی • تالار افتخار\n\n"
        "📖 جزئیات بیشتر:\n"
        "«آموزش» — ماموریت‌های شروع با جایزه\n"
        "«پروفایل» — وضعیت کامل خودت\n\n"
        "🔓 قابلیت‌ها با لول باز می‌شن:\n" +
        "\n".join(f"• لول {lv}: {t}" for lv, t in sorted(UNLOCK_TEXT.items())) +
        "\n\n💡 بازی فقط داخل گروه فعال هست.", parse_mode="HTML")


LINE = "━━━━━━━━━━━━━━"


def profile_text(u):
    uid, lvl = u["id"], level_of(u["xp"])
    if lvl >= LEVEL_CAP:
        xp_line = f"✨ XP: {u['xp']:,} (حداکثر لول 👑)"
    else:
        base, nxt = xp_for_level(lvl), xp_for_level(lvl + 1)
        pct = int(100 * (u["xp"] - base) / max(1, nxt - base))
        xp_line = f"✨ XP: {u['xp']:,} / {nxt:,}\n[{bar(u['xp'] - base, nxt - base)}] {pct}٪"
    eq = equipped_items(uid)
    eq_lines = []
    for sl in SLOTS:
        if sl in eq:
            it = ITEMS[eq[sl]]
            eq_lines.append(f"{SLOT_LABELS[sl]}: {html.escape(gear_name(uid, eq[sl]))} <i>(+{enhanced_power(uid, eq[sl])})</i>")
        else:
            eq_lines.append(f"{SLOT_LABELS[sl]}: —")
    g = guild_of(uid)
    bal = db.execute("SELECT amount FROM bank WHERE user_id=?", (uid,)).fetchone()
    sp = spouse_of(uid)
    games = u["duel_wins"] + u["duel_losses"]
    rate = f" ({int(100 * u['duel_wins'] / games)}٪)" if games else ""
    return "\n".join([
        LINE,
        f"👑 <b>{html.escape(u['name'])}</b>  {GENDERS.get(u['gender'], '❔')}",
        f"{CLASSES[u['cls']][0]}  •  🏅 {html.escape(title_of(lvl))}",
        LINE,
        f"⭐ لول <b>{lvl}</b>",
        xp_line,
        LINE,
        f"💰 سکه: <b>{u['coins']:,}</b>   🏦 بانک: {(bal['amount'] if bal else 0):,}",
        f"💼 شغل: {html.escape(u['job'] or 'بیکار')}",
        f"🏰 انجمن: {html.escape(g['name']) if g else '—'}",
        f"💍 همسر: {html.escape(sp[0]['name']) if sp else '—'}",
        LINE,
        f"⚔️ دوئل: {u['duel_wins']} برد / {u['duel_losses']} باخت{rate}",
        f"🔨 کار: {u['work_count']}   🗺 ماجراجویی: {u['adv_count']}",
        f"🐉 غول‌کشی: {u['boss_kills']}   📣 دعوت: {u['invites']}",
        f"🏅 مدال‌ها: {ach_badges(uid)}",
        f"🌟 فصل {season_now()['no']}: {sp_of(uid):,} امتیاز (رتبه‌ی {sp_rank(uid)})",
        *([html.escape(season_title(uid))] if season_title(uid) else []),
        pet_profile_line(uid),
        f"⚡ قدرت رزمی: <b>{int(duel_power(u))}</b>",
        LINE,
        "🎒 <b>تجهیزات فعال</b>",
        *eq_lines,
        LINE,
    ])


@command("پروفایل", "profile")
async def cmd_profile(update, ctx, args):
    msg = update.message
    rt = msg.reply_to_message
    if rt and rt.from_user and not rt.from_user.is_bot and rt.from_user.id != update.effective_user.id:
        u = user_by_id(rt.from_user.id)
        if not has_char(u):
            return await msg.reply_text("این بازیکن هنوز شخصیت نساخته.")
    else:
        u = get_user(update.effective_user)
    await send_event_sticker(ctx, update.effective_chat.id, "profile", 0.6)
    kb = None
    if u["id"] == update.effective_user.id and ctx.bot.username:
        kb = Markup([[Btn("📤 اشتراک‌گذاری کارت قهرمان",
                          url=share_url(ref_link(ctx.bot.username, u["id"]), share_card_text(u)))]])
    await msg.reply_text(profile_text(u), parse_mode="HTML", reply_markup=kb)


# ============================== کار، پوینت، ماجراجویی، جایزه ==============================
@command("کار", "work")
async def cmd_work(update, ctx, args):
    u = get_user(update.effective_user)
    uid = u["id"]
    left = cd_left(u, "last_work", WORK_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی کار کنی.")
    gain = (random.randint(8, 14) + level_of(u["xp"]) + best_power(uid, "tool")
            + JOB_WORK.get(u["job"], 0) + (2 if u["cls"] == "hunter" else 0))
    bonus = guild_bonus(uid)
    gain = int(gain * (1 + bonus / 100))
    ev_mult, ev_label = event_mult()
    pet_c, fal_c = pet_bonus(uid, "coins"), fal_bonus(uid, "coins")
    gain = int(gain * ev_mult * season_perk("work_coins") * (1 + (pet_c + fal_c) / 100))
    married = spouse_of(uid) is not None
    if married:
        gain = int(gain * (1 + MARRY_BONUS / 100))
    with tx():
        db.execute("UPDATE users SET coins=coins+?, last_work=?, work_count=work_count+1 WHERE id=?",
                   (gain, time.time(), uid))
        bump(uid, "work")
        xp, note = grant_xp(uid, 6)
    perks = []
    if bonus:
        perks.append(f"🏰 انجمن +{bonus}٪")
    if married:
        perks.append(f"💍 همسر +{MARRY_BONUS}٪")
    if pet_c:
        perks.append(f"🐾 همراه +{pet_c:.0f}٪")
    if fal_c:
        perks.append(f"🔮 فال +{fal_c:.0f}٪")
    if ev_mult > 1:
        perks.append(f"{ev_label} ×{ev_mult:g}")
    if season_perk("work_coins") > 1:
        perks.append(f"{season_theme(season_now()['no'])[0]} مزیت فصل +{int(round((season_perk('work_coins') - 1) * 100))}٪")
    story = random.choice(WORK_STORIES.get(u["job"], WORK_STORIES[""]))
    text = f"{story}\n━━━━━━━━━━━━━━\n💰 +{gain:,} سکه\n✨ +{xp} XP"
    if perks:
        text += "\n" + "  ".join(perks)
    chat_score(update.effective_chat.id, 2)
    await reply_game(update, ctx, text + note, "work")


def city_level(chat_id):
    r = db.execute("SELECT level FROM cities WHERE chat_id=?", (chat_id,)).fetchone()
    return r["level"] if r else 0


def point_cooldown(level):
    return max(POINT_MIN, POINT_BASE - POINT_STEP * level)


def upgrade_cost(level):
    return 1500 * (level + 1)


@command("پوینت", "point")
async def cmd_point(update, ctx, args):
    chat_id = update.effective_chat.id
    u = get_user(update.effective_user)
    uid = u["id"]
    cd = point_cooldown(city_level(chat_id))
    r = db.execute("SELECT ts FROM last_point WHERE user_id=? AND chat_id=?", (uid, chat_id)).fetchone()
    left = (r["ts"] if r else 0) + cd - time.time()
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی پوینت بگیری.")
    gain = random.randint(3, 7) + level_of(u["xp"]) // 5
    if u["job"] == "تاجر":
        gain *= 2
    with tx():
        db.execute("UPDATE users SET coins=coins+? WHERE id=?", (gain, uid))
        db.execute("INSERT INTO last_point(user_id, chat_id, ts) VALUES(?,?,?) "
                   "ON CONFLICT(user_id, chat_id) DO UPDATE SET ts=excluded.ts",
                   (uid, chat_id, time.time()))
        bump(uid, "point")
        xp, note = grant_xp(uid, 4)
    await reply_game(update, ctx, f"⭐ پوینت گرفتی!\n━━━━━━━━━━━━━━\n💰 +{gain} سکه\n✨ +{xp} XP" + note, "point", STICKER_CHANCE * 0.6)
    chat_score(update.effective_chat.id, 1)


@command("ماجراجویی", "adventure", level=2)
async def cmd_adventure(update, ctx, args):
    u = get_user(update.effective_user)
    uid, lvl = u["id"], level_of(u["xp"])
    left = cd_left(u, "last_adv", ADVENTURE_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی بری ماجراجویی.")
    chance = min(0.50 + best_power(uid, "weapon") / 100 + lvl * 0.005 + (pet_bonus(uid, "luck") + fal_bonus(uid, "luck")) / 100, 0.90)
    if random.random() < chance:
        gain = int(random.randint(30, 80) * (1 + lvl * 0.04) * reward_mult(uid) * season_perk("adv_coins")
                   * (1 + (pet_bonus(uid, "loot") + fal_bonus(uid, "loot")) / 100))
        won, base_xp, delta = True, 15, gain
        result = f"{random.choice(ADV_WIN)}\n━━━━━━━━━━━━━━\n💰 +{gain:,} سکه"
    else:
        reduction = min(0.70, best_power(uid, "armor") / 100 + (0.05 if u["cls"] == "warrior" else 0)
                        + pet_bonus(uid, "defense") / 100)
        loss = int(u["coins"] * random.uniform(0.05, 0.12) * (1 - reduction))
        loss = min(max(10, loss), u["coins"])
        won, base_xp, delta = False, 5, -loss
        result = (f"{random.choice(ADV_LOSE)}\n━━━━━━━━━━━━━━\n💸 -{loss:,} سکه\n"
                  "💡 زره، خسارت رو کم می‌کنه و پول بانک امنه.")
    with tx():
        db.execute("UPDATE users SET coins=MAX(0, coins+?), last_adv=?, adv_count=adv_count+1 WHERE id=?",
                   (delta, time.time(), uid))
        bump(uid, "adv")
        xp, note = grant_xp(uid, base_xp)
    chat_score(update.effective_chat.id, 4 if won else 1)
    await reply_game(update, ctx, result + f"\n✨ +{xp} XP" + note, "win" if won else "lose")


@command("جایزه", "daily", level=2)
async def cmd_daily(update, ctx, args):
    u = get_user(update.effective_user)
    uid = u["id"]
    left = cd_left(u, "last_daily", DAILY_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی جایزه بگیری.")
    streak = u["streak"] + 1 if time.time() - u["last_daily"] < 48 * 3600 else 1
    coins = 30 + 10 * min(streak - 1, 6)
    with tx():
        db.execute("UPDATE users SET coins=coins+?, last_daily=?, streak=? WHERE id=?",
                   (coins, time.time(), streak, uid))
        xp, note = grant_xp(uid, 20)
    await reply_game(
        update, ctx,
        f"🎁 جایزه‌ی روزانه‌ت رسید!\n━━━━━━━━━━━━━━\n💰 +{coins} سکه\n✨ +{xp} XP\n"
        f"{'🔥' * min(streak, 7)} {streak} روز پشت‌سرهم\n💡 فردا هم بیا تا جایزه بزرگ‌تر بشه!" + note,
        "daily", 1.0)
    chat_score(update.effective_chat.id, 3)


# ============================== شغل و ماموریت ==============================
@command("شغل", "job", args=True, level=5)
async def cmd_job(update, ctx, args):
    u = get_user(update.effective_user)
    lvl = level_of(u["xp"])
    if not args:
        lines = [f"{n} (از لول {lv}) — {d}" for n, (lv, d) in JOBS.items()]
        return await update.message.reply_text(
            f"💼 شغل فعلی: {u['job'] or 'بیکار'}\n\n" + "\n".join(lines) +
            f"\n\nبرای انتخاب بنویس: شغل کارگر\n(تغییر شغل {JOB_CHANGE_COST} سکه هزینه داره)")
    name = args[0]
    if name not in JOBS:
        return await update.message.reply_text("این شغل وجود نداره. بنویس «شغل» تا لیست رو ببینی.")
    need = JOBS[name][0]
    if lvl < need and not is_admin(u["id"]):
        return await update.message.reply_text(f"🔒 این شغل از لول {need} باز می‌شه.")
    if u["job"] == name:
        return await update.message.reply_text("همین الان همین شغل رو داری.")
    cost = JOB_CHANGE_COST if u["job"] else 0
    with tx():
        if cost and not spend(u["id"], cost):
            ok = False
        else:
            db.execute("UPDATE users SET job=? WHERE id=?", (name, u["id"]))
            ok = True
    if not ok:
        return await update.message.reply_text(f"برای تغییر شغل {cost} سکه لازمه.")
    await update.message.reply_text(f"💼 حالا {name} هستی! ({JOBS[name][1]})")


@command("ماموریت", "missions", level=6)
async def cmd_missions(update, ctx, args):
    uid = get_user(update.effective_user)["id"]
    with tx():
        db.execute("INSERT OR IGNORE INTO daily_stats(user_id, day) VALUES(?, ?)", (uid, today()))
        row = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND day=?", (uid, today())).fetchone()
        claimed = set(filter(None, row["claimed"].split(",")))
        lines, got_coins, got_xp = [], 0, 0
        for key, target, label, coins, xp in MISSIONS:
            prog = row[key]
            if key in claimed:
                status = "✅ جایزه‌ش رو گرفتی"
            elif prog >= target:
                claimed.add(key)
                got_coins += coins
                got_xp += xp
                status = f"🎉 تموم شد! +{coins} سکه و +{xp} XP"
            else:
                status = f"{prog}/{target}"
            lines.append(f"• {label} ({coins} سکه): {status}")
        note = ""
        if got_coins:
            db.execute("UPDATE daily_stats SET claimed=? WHERE user_id=? AND day=?",
                       (",".join(sorted(claimed)), uid, today()))
            add_coins(uid, got_coins)
            _, note = grant_xp(uid, got_xp)
    await update.message.reply_text("📋 ماموریت‌های امروز\n\n" + "\n".join(lines) + note)


# ============================== فروشگاه و کوله ==============================
def shop_main_view(uid):
    u = user_by_id(uid)
    cls_name = CLASSES.get(u["cls"], ("",))[0] if u else ""
    kb = [[Btn(label, f"shop:{uid}:{cat}")] for cat, label in CATEGORIES.items()]
    text = (f"🏪 فروشگاه\n━━━━━━━━━━━━━━\n"
            f"💰 سکه‌ات: {u['coins']:,}\n"
            f"🎭 کلاس: {cls_name}\n\n"
            "دسته مورد نظرت رو انتخاب کن:\n"
            "💡 وسایل مخصوص کلاس خودت فقط برای تو نمایش داده می‌شه.")
    return text, Markup(kb)


def shop_cat_view(cat, u):
    uid, lvl, have = u["id"], level_of(u["xp"]), owned(u["id"])
    lines = [
        f"💰 سکه‌ات: {u['coins']:,}",
        f"⭐ لول تو: {lvl}",
        "",
        f"{CATEGORIES[cat]}",
        "━━━━━━━━━━━━━━",
    ]
    kb, hidden, shown = [], 0, 0
    for key, (name, c, _, minlvl, power, desc) in sorted(ITEMS.items(), key=lambda kv: (kv[1][3], kv[1][2])):
        if c != cat or key in HIDDEN_ITEMS:
            continue
        if not item_usable(u, key):
            hidden += 1
            continue
        shown += 1
        price = item_price(u, key)
        tag = ITEM_RARITY.get(key, "")
        owned_mark = "✅ " if key in have else ""
        req = req_label(key)
        if lvl < minlvl:
            # قفل‌شده — قیمت و اسم، با قفل واضح
            lines.append(f"🔒 {tag}{name}{req} — {price:,} سکه (لول {minlvl})")
        else:
            lines.append(f"{owned_mark}{tag}{name}{req} — {price:,} سکه")
            if cat == "misc" or key not in have:
                kb.append([Btn(f"خرید {name} • {price:,}", f"buy:{uid}:{key}")])
    if shown == 0:
        lines.append("هیچ وسیله‌ای برای کلاس/شغل تو در این دسته نیست.")
    if hidden:
        lines.append(f"\n🔐 {hidden} وسیله‌ی مخصوص کلاس یا شغل‌های دیگه مخفیه.")
    if any(ITEM_RARITY.get(k) for k in ITEMS if ITEMS[k][1] == cat):
        lines.append("\n🟦 نادر  🟪 حماسی  🟧 افسانه‌ای")
    kb.append([Btn("⬅️ برگشت", f"shop:{uid}:main")])
    return "\n".join(lines), Markup(kb)


@command("فروشگاه", "shop")
async def cmd_shop(update, ctx, args):
    uid = get_user(update.effective_user)["id"]
    text, kb = shop_main_view(uid)
    await update.message.reply_text(text, reply_markup=kb)


async def _own_panel(q, owner):
    """دکمه‌های پنل‌های شخصی فقط برای صاحب پیام کار می‌کنن."""
    if q.from_user.id != owner:
        await q.answer("این پنل برای تو نیست؛ خودت دستورش رو بزن.", show_alert=True)
        return False
    return True


async def cb_shop(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or parts[1] != str(q.from_user.id):
        return await q.answer("این پنل برای تو نیست؛ خودت «فروشگاه» رو بزن.", show_alert=True)
    cat = parts[2]
    if cat != "main" and cat not in CATEGORIES:
        return await q.answer()
    u = get_user(q.from_user)
    text, kb = shop_main_view(u["id"]) if cat == "main" else shop_cat_view(cat, u)
    await q.answer()
    await safe_edit(q, text, kb)


def buy_item(uid, key):
    if key not in ITEMS or key in HIDDEN_ITEMS:
        return False, "وسیله نامعتبره."
    name, cat, _, minlvl, power, _ = ITEMS[key]
    with tx():
        u = user_by_id(uid)
        if not item_usable(u, key):
            return False, f"🔐 این وسیله فقط برای {req_text(key)} قابل خریده."
        if level_of(u["xp"]) < minlvl and not is_admin(uid):
            return False, f"🔒 این وسیله از لول {minlvl} باز می‌شه."
        if cat == "misc":
            if qty(uid, key) >= CONSUMABLE_MAX:
                return False, f"حداکثر {CONSUMABLE_MAX} تا می‌تونی داشته باشی."
        elif qty(uid, key) > 0:
            return False, "این وسیله رو قبلاً داری."
        elif db.execute("SELECT 1 FROM market WHERE seller=? AND item=?", (uid, key)).fetchone():
            return False, "این وسیله رو الان توی بازار گذاشتی."
        price = item_price(u, key)
        if not spend(uid, price):
            return False, f"سکه‌ات کافی نیست! (قیمت: {price:,})"
        db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                   "ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+1", (uid, key))
        msg = f"{name} خریدی! ✅"
        if cat in SLOTS:
            cur = db.execute("SELECT item FROM equipped WHERE user_id=? AND slot=?", (uid, cat)).fetchone()
            if not cur or cur["item"] not in ITEMS or enhanced_power(uid, cur["item"]) < enhanced_power(uid, key):
                db.execute("INSERT INTO equipped(user_id, slot, item) VALUES(?,?,?) "
                           "ON CONFLICT(user_id, slot) DO UPDATE SET item=excluded.item", (uid, cat, key))
                msg += " (خودکار فعال شد)"
    return True, msg


async def cb_buy(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or parts[1] != str(q.from_user.id):
        return await q.answer("این پنل برای تو نیست؛ خودت «فروشگاه» رو بزن.", show_alert=True)
    ok, msg = buy_item(q.from_user.id, parts[2])
    await q.answer(msg, show_alert=True)
    if ok:
        text, kb = shop_cat_view(ITEMS[parts[2]][1], user_by_id(q.from_user.id))
        await safe_edit(q, text, kb)


def inventory_view(uid):
    have, eq = owned(uid), equipped_items(uid)
    u_row = user_by_id(uid)
    lines, kb = ["🎒 کوله‌پشتی و تجهیزات", "━━━━━━━━━━━━━━", ""], []
    for slot in SLOTS:
        lines.append(SLOT_LABELS[slot])
        keys = sorted((k for k in have if k in ITEMS and ITEMS[k][1] == slot),
                      key=lambda k: ITEMS[k][4], reverse=True)
        if not keys:
            lines.append("— خالی")
        for key in keys:
            active = eq.get(slot) == key
            ok = item_usable(u_row, key)
            mark = "🟢 فعال: " if active else ("▫️ " if ok else "🔒 ")
            lines.append(mark + f"{gear_name(uid, key)}{req_label(key)} — قدرت {enhanced_power(uid, key)}")
            if not active:
                row = [Btn(f"فعال‌سازی {ITEMS[key][0]}", f"equip:{uid}:{key}")] if ok else []
                row.append(Btn(f"فروش +{int(ITEMS[key][2] * SELL_RATIO):,}", f"sell:{uid}:{key}"))
                kb.append(row)
        lines.append("")
    misc = [(k, n) for k, n in have.items() if k in ITEMS and ITEMS[k][1] == "misc"]
    lines.append("🧰 مصرفی‌ها")
    lines.extend(f"{ITEMS[k][0]} × {n}" for k, n in misc) if misc else lines.append("— خالی")
    if kb:
        kb.append([Btn("🔄 تازه‌سازی", f"inv:{uid}:refresh")])
    return "\n".join(lines), (Markup(kb) if kb else None)


@command("کوله", "موجودی", "تجهیزات", "inventory")
async def cmd_inventory(update, ctx, args):
    uid = get_user(update.effective_user)["id"]
    text, kb = inventory_view(uid)
    await update.message.reply_text(text, reply_markup=kb)


def sell_item(uid, key):
    if key not in ITEMS or ITEMS[key][1] not in SLOTS:
        return False, "این وسیله قابل فروش نیست."
    slot = ITEMS[key][1]
    with tx():
        if qty(uid, key) <= 0:
            return False, "این وسیله رو نداری."
        if equipped_items(uid).get(slot) == key:
            return False, "وسیله‌ی فعال رو نمی‌تونی بفروشی؛ اول یه وسیله‌ی دیگه فعال کن."
        price = int(ITEMS[key][2] * SELL_RATIO)
        db.execute("UPDATE items SET qty=0 WHERE user_id=? AND item=?", (uid, key))
        add_coins(uid, price)
    return True, f"{ITEMS[key][0]} فروخته شد: +{price:,} سکه"


def equip_item(uid, key):
    if key not in ITEMS or ITEMS[key][1] not in SLOTS:
        return False, "وسیله قابل تجهیز نیست."
    if qty(uid, key) <= 0:
        return False, "این وسیله رو نداری."
    if not item_usable(user_by_id(uid), key):
        return False, f"🔐 این وسیله ویژه‌ی {req_text(key)} هست و برای تو قابل استفاده نیست."
    db.execute("INSERT INTO equipped(user_id, slot, item) VALUES(?,?,?) "
               "ON CONFLICT(user_id, slot) DO UPDATE SET item=excluded.item",
               (uid, ITEMS[key][1], key))
    return True, "تجهیزات فعال تغییر کرد! ✅"


async def cb_inventory(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not await _own_panel(q, int(parts[1]) if parts[1].isdigit() else -1):
        return
    action, uid, arg = parts[0], q.from_user.id, parts[2]
    msg = ""
    if action == "equip":
        ok, msg = equip_item(uid, arg)
    elif action == "sell":
        ok, msg = sell_item(uid, arg)
    await q.answer(msg or None, show_alert=bool(msg and action == "sell"))
    text, kb = inventory_view(uid)
    await safe_edit(q, text, kb)


# ============================== بانک ==============================
def bank_cap(level):
    return BANK_CAP_PER_LEVEL * level


def bank_balance(uid):
    """موجودی بانک با اعمال سود ساعتی (داخل تراکنش صدا بزن اگه می‌خوای تغییر بدی)."""
    r = db.execute("SELECT amount, ts FROM bank WHERE user_id=?", (uid,)).fetchone()
    if not r:
        return 0
    amount, ts, now = r["amount"], r["ts"], time.time()
    hours = int((now - ts) // 3600)
    if hours > 0:
        if amount > 0:
            amount = int(amount * (1 + BANK_RATE) ** min(hours, BANK_MAX_HOURS))
        new_ts = ts + hours * 3600 if hours <= BANK_MAX_HOURS else now
        db.execute("UPDATE bank SET amount=?, ts=? WHERE user_id=?", (amount, new_ts, uid))
    return amount


@command("بانک", "bank", level=3)
async def cmd_bank(update, ctx, args):
    u = get_user(update.effective_user)
    lvl = level_of(u["xp"])
    await update.message.reply_text(
        f"🏦 بانک\n\n💰 پول دستت: {u['coins']:,}\n🏦 تو بانک: {bank_balance(u['id']):,}\n"
        f"📦 ظرفیت بانک: {bank_cap(lvl):,} (با بالا رفتن لول بیشتر می‌شه)\n"
        f"📈 سود: {BANK_RATE * 100:.1f}٪ در هر ساعت\n\n"
        "واریز 100 — گذاشتن پول تو بانک\nبرداشت 100 — برداشتن از بانک\n"
        "(به جای عدد می‌تونی بنویسی: همه)")


@command("واریز", "deposit", args=True, level=3)
async def cmd_deposit(update, ctx, args):
    uid = get_user(update.effective_user)["id"]
    with tx():
        u = user_by_id(uid)
        lvl = level_of(u["xp"])
        bal = bank_balance(uid)
        room = max(0, bank_cap(lvl) - bal)
        if room <= 0:
            return await update.message.reply_text(
                f"🏦 بانکت پره! ظرفیتت {bank_cap(lvl):,} سکه‌ست. با بالا رفتن لول بیشتر می‌شه.")
        amt = parse_amount(args[0], min(u["coins"], room)) if args else None
        if not amt or amt <= 0:
            return await update.message.reply_text("مثال: واریز 100  یا  واریز همه")
        if amt > u["coins"]:
            return await update.message.reply_text("پول دستت کافی نیست.")
        if amt > room:
            return await update.message.reply_text(f"ظرفیت بانکت فقط {room:,} سکه جا داره.")
        db.execute("UPDATE users SET coins=coins-? WHERE id=?", (amt, uid))
        db.execute("INSERT INTO bank(user_id, amount, ts) VALUES(?,?,?) "
                   "ON CONFLICT(user_id) DO UPDATE SET amount=amount+excluded.amount, ts=excluded.ts",
                   (uid, amt, time.time()))
    await update.message.reply_text(f"🏦 {amt:,} سکه واریز شد.")


@command("برداشت", "withdraw", args=True, level=3)
async def cmd_withdraw(update, ctx, args):
    uid = get_user(update.effective_user)["id"]
    with tx():
        bal = bank_balance(uid)
        amt = parse_amount(args[0], bal) if args else None
        if not amt or amt <= 0:
            err = "مثال: برداشت 100  یا  برداشت همه"
        elif amt > bal:
            err = "موجودی بانکت کافی نیست."
        else:
            err = None
            db.execute("UPDATE bank SET amount=amount-? WHERE user_id=?", (amt, uid))
            add_coins(uid, amt)
    await update.message.reply_text(err or f"💵 {amt:,} سکه برداشتی.")


# ============================== انتقال پول و جدول‌ها ==============================
def do_transfer(me_id, to_id, amount):
    fee = max(1, int(amount * TRANSFER_FEE))
    with tx():
        me = user_by_id(me_id)
        cap = TRANSFER_DAILY_PER_LEVEL * level_of(me["xp"])
        db.execute("INSERT OR IGNORE INTO daily_stats(user_id, day) VALUES(?, ?)", (me_id, today()))
        sent = db.execute("SELECT sent FROM daily_stats WHERE user_id=? AND day=?",
                          (me_id, today())).fetchone()["sent"]
        if sent + amount > cap:
            return f"سقف انتقال روزانه‌ی تو {cap:,} سکه‌ست (امروز {sent:,} فرستادی)."
        if not spend(me_id, amount + fee):
            return f"پول دستت کافی نیست. ({amount} + {fee} کارمزد)"
        add_coins(to_id, amount)
        db.execute("UPDATE daily_stats SET sent=sent+? WHERE user_id=? AND day=?", (amount, me_id, today()))
    return None


@command("انتقال", "pay", args=True, level=4)
async def cmd_pay(update, ctx, args):
    msg = update.message
    amount = parse_int(args[0]) if args else None
    if not msg.reply_to_message or amount is None:
        return await msg.reply_text("روی پیام طرف ریپلای کن و بنویس: انتقال 50")
    to = msg.reply_to_message.from_user
    me = get_user(update.effective_user)
    if to.is_bot or to.id == me["id"] or amount < 10:
        return await msg.reply_text("انتقال نامعتبره (حداقل ۱۰ سکه).")
    target = user_by_id(to.id)
    if not has_char(target) or is_banned(to.id):
        return await msg.reply_text("این بازیکن نمی‌تونه پول دریافت کنه (شخصیت نساخته).")
    err = do_transfer(me["id"], to.id, amount)
    if err:
        return await msg.reply_text(err)
    fee = max(1, int(amount * TRANSFER_FEE))
    await msg.reply_text(f"💸 {amount} سکه به {target['name']} منتقل شد. (کارمزد: {fee})")


_PLAYER = "cls<>'' AND gender<>'' AND id NOT IN (SELECT user_id FROM banned)"


@command("برترین", "top")
async def cmd_top(update, ctx, args):
    rows = db.execute(f"SELECT name, xp FROM users WHERE {_PLAYER} ORDER BY xp DESC, id LIMIT 10").fetchall()
    text = "🏆 برترین‌ها (بر اساس لول)\n\n" + "\n".join(
        f"{i}. {r['name']} — لول {level_of(r['xp'])} ({r['xp']:,} XP)" for i, r in enumerate(rows, 1))
    await update.message.reply_text(text if rows else "هنوز بازیکنی نیست.")


@command("ثروتمندان", "rich")
async def cmd_rich(update, ctx, args):
    rows = db.execute(
        "SELECT name, coins + COALESCE((SELECT amount FROM bank WHERE user_id=users.id), 0) AS total "
        f"FROM users WHERE {_PLAYER} ORDER BY total DESC, id LIMIT 10").fetchall()
    text = "💎 ثروتمندان (پول + بانک)\n\n" + "\n".join(
        f"{i}. {r['name']} — {r['total']:,}" for i, r in enumerate(rows, 1))
    await update.message.reply_text(text if rows else "هنوز بازیکنی نیست.")


@command("برترین دوئل", "duels")
async def cmd_top_duels(update, ctx, args):
    rows = db.execute(f"SELECT name, duel_wins, duel_losses FROM users WHERE {_PLAYER} "
                      "AND duel_wins>0 ORDER BY duel_wins DESC, duel_losses ASC, id LIMIT 10").fetchall()
    if not rows:
        return await update.message.reply_text("هنوز کسی دوئل نبرده.")
    await update.message.reply_text("⚔️ برترین دوئل‌بازها\n\n" + "\n".join(
        f"{i}. {r['name']} — {r['duel_wins']} برد / {r['duel_losses']} باخت" for i, r in enumerate(rows, 1)))


# ============================== شهر ==============================
def city_view(chat_id):
    lvl = city_level(chat_id)
    text = (f"🏙 سطح شهر: {lvl}/{MAX_CITY}\n⏱ فاصله پوینت: {fmt_time(point_cooldown(lvl))}\n"
            f"(ارتقای شهر از لول {CITY_UPGRADE_LEVEL} باز می‌شه و برای همه‌ی اعضای گروه اثر داره)")
    if lvl >= MAX_CITY:
        return text + "\n✅ شهر به حداکثر سطح رسیده!", None
    return text, Markup([[Btn(f"⬆️ ارتقا ({upgrade_cost(lvl):,} سکه)", "city_up")]])


@command("شهر", "city")
async def cmd_city(update, ctx, args):
    text, kb = city_view(update.effective_chat.id)
    await update.message.reply_text(text, reply_markup=kb)


def upgrade_city(chat_id, uid):
    with tx():
        u = user_by_id(uid)
        if level_of(u["xp"]) < CITY_UPGRADE_LEVEL and not is_admin(uid):
            return False, f"🔒 ارتقای شهر از لول {CITY_UPGRADE_LEVEL} باز می‌شه."
        lvl = city_level(chat_id)
        if lvl >= MAX_CITY:
            return False, "شهر به حداکثر سطح رسیده."
        cost = upgrade_cost(lvl)
        if not spend(uid, cost):
            return False, f"سکه‌ات کافی نیست! ({cost:,})"
        db.execute("INSERT INTO cities(chat_id, level) VALUES(?, 1) "
                   "ON CONFLICT(chat_id) DO UPDATE SET level=level+1", (chat_id,))
    return True, "شهر ارتقا پیدا کرد! 🎉"


async def cb_city_up(update, ctx):
    q = update.callback_query
    chat_id = q.message.chat.id
    ok, msg = upgrade_city(chat_id, q.from_user.id)
    await q.answer(msg, show_alert=True)
    if ok:
        text, kb = city_view(chat_id)
        await safe_edit(q, text, kb)


# ============================== دزدی ==============================
def do_rob(me_id, v_id, v_name):
    with tx():
        me, v = user_by_id(me_id), user_by_id(v_id)
        left = cd_left(me, "last_rob", ROB_COOLDOWN)
        if left > 0:
            return f"⏳ {fmt_time(left)} دیگه می‌تونی دزدی کنی."
        if not has_char(v):
            return "این بازیکن هنوز شخصیت نساخته."
        if level_of(v["xp"]) < 5:
            return "نمی‌تونی از تازه‌کارها (زیر لول ۵) دزدی کنی 😅"
        if v["coins"] < 100:
            return "جیبش تقریباً خالیه، ارزش نداره!"
        safe_left = v["last_robbed"] + ROB_PROTECT - time.time()
        if safe_left > 0:
            return f"🛡 {v_name} تازه دزدی شده؛ تا {fmt_time(safe_left)} دیگه امنه."
        set_time(me_id, "last_rob")
        if qty(v_id, "lock2") > 0:
            use_one(v_id, "lock2")
            fine = min(me["coins"], 120)
            add_coins(me_id, -fine)
            add_coins(v_id, fine)
            return f"🔐 {v_name} قفل آهنین داشت! دزدی شکست خورد و {fine} سکه جریمه شدی و به او رسید."
        if qty(v_id, "lock") > 0:
            use_one(v_id, "lock")
            fine = min(me["coins"], 30)
            add_coins(me_id, -fine)
            return f"🔒 {v_name} قفل داشت! دزدی شکست خورد و {fine} سکه جریمه شدی."
        lvl_me, lvl_v = level_of(me["xp"]), level_of(v["xp"])
        chance = (0.35 + best_power(me_id, "weapon") / 100 - best_power(v_id, "armor") / 200
                  + max(-0.1, min(0.1, (lvl_me - lvl_v) * 0.01)))
        if me["job"] == "راهزن":
            chance += 0.10
        if me["cls"] == "ninja":
            chance += 0.05
        if v["job"] == "نگهبان":
            chance -= 0.10
        chance = max(0.10, min(0.70, chance))
        if random.random() < chance:
            amount = max(1, min(int(v["coins"] * random.uniform(0.08, 0.15)), 300 * lvl_me))
            add_coins(v_id, -amount)
            add_coins(me_id, amount)
            db.execute("UPDATE users SET last_robbed=? WHERE id=?", (time.time(), v_id))
            xp, note = grant_xp(me_id, 15)
            return f"🥷 موفق شدی! {amount} سکه از {v_name} دزدیدی.\n✨ +{xp} XP" + note
        if me["cls"] == "ninja" and random.random() < 0.25:
            xp, note = grant_xp(me_id, 3)
            return f"💨 نینجا بودی و از دست نگهبان‌ها فرار کردی؛ جریمه نشدی.\n✨ +{xp} XP" + note
        fine = min(me["coins"], max(30, int(me["coins"] * 0.10)))
        add_coins(me_id, -fine)
        add_coins(v_id, fine)
        xp, note = grant_xp(me_id, 3)
        return f"🚨 گرفتنت! {fine} سکه جریمه دادی و به {v_name} رسید.\n✨ +{xp} XP" + note


@command("دزدی", "rob", level=8)
async def cmd_rob(update, ctx, args):
    msg = update.message
    if not msg.reply_to_message:
        return await msg.reply_text("روی پیام کسی که می‌خوای ازش دزدی کنی ریپلای کن و بنویس: دزدی")
    vt = msg.reply_to_message.from_user
    me = get_user(update.effective_user)
    if vt.is_bot or vt.id == me["id"]:
        return await msg.reply_text("هدف نامعتبره.")
    victim = user_by_id(vt.id)
    await msg.reply_text(do_rob(me["id"], vt.id, victim["name"] if victim else vt.first_name))


# ============================== دوئل ==============================
def duel_power(u):
    return (best_power(u["id"], "weapon") + best_power(u["id"], "armor") / 2
            + level_of(u["xp"]) / 2 + (5 if u["cls"] == "warrior" else 0))


@command("دوئل", "duel", args=True, level=10)
async def cmd_duel(update, ctx, args):
    msg = update.message
    stake = parse_int(args[0]) if args else None
    if not msg.reply_to_message or stake is None:
        return await msg.reply_text("روی پیام طرف ریپلای کن و بنویس: دوئل 100")
    target = msg.reply_to_message.from_user
    me = get_user(update.effective_user)
    if target.is_bot or target.id == me["id"]:
        return await msg.reply_text("حریف نامعتبره.")
    cap = min(5000, 300 * level_of(me["xp"]))
    if stake < 20 or stake > cap:
        return await msg.reply_text(f"مبلغ دوئل باید بین ۲۰ تا {cap} سکه باشه.")
    if me["coins"] < stake:
        return await msg.reply_text("پول دستت کافی نیست.")
    left = cd_left(me, "last_duel", DUEL_COOLDOWN)
    if left > 0:
        return await msg.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی دوئل بدی.")
    t = user_by_id(target.id)
    if not has_char(t) or is_banned(target.id):
        return await msg.reply_text("حریف هنوز شخصیت نساخته.")
    if level_of(t["xp"]) < 10:
        return await msg.reply_text("حریف باید لول ۱۰ یا بالاتر باشه.")
    with tx():
        set_time(me["id"], "last_duel")
        db.execute("UPDATE duel_requests SET status='expired' WHERE challenger=? AND status='pending'",
                   (me["id"],))
        rid = db.execute(
            "INSERT INTO duel_requests(challenger, target, stake, chat_id, status, created) "
            "VALUES(?,?,?,?, 'pending', ?)",
            (me["id"], target.id, stake, update.effective_chat.id, time.time())).lastrowid
    kb = Markup([[Btn("✅ قبول", f"duel:y:{rid}"), Btn("❌ رد", f"duel:n:{rid}")]])
    await msg.reply_text(
        f"⚔️ {me['name']} به {t['name']} پیشنهاد دوئل با {stake} سکه داد!\n"
        f"{t['name']}، قبول می‌کنی؟ (۵ دقیقه وقت داری)", reply_markup=kb)


def resolve_duel(rid, clicker, answer):
    """برمی‌گردونه: (kind, text) که kind یکی از alert/edit هست."""
    with tx():
        r = db.execute("SELECT * FROM duel_requests WHERE id=?", (rid,)).fetchone()
        if not r:
            return "alert", "دعوت نامعتبره."
        if clicker != r["target"]:
            return "alert", "این دعوت برای تو نیست."
        if r["status"] != "pending":
            return "alert", "این دوئل قبلاً تعیین تکلیف شده."
        c, t = user_by_id(r["challenger"]), user_by_id(r["target"])
        if answer == "n":
            db.execute("UPDATE duel_requests SET status='declined' WHERE id=?", (rid,))
            return "edit", f"❌ {t['name']} دوئل با {c['name']} رو رد کرد."
        if time.time() - r["created"] > DUEL_TTL:
            db.execute("UPDATE duel_requests SET status='expired' WHERE id=?", (rid,))
            return "edit", "⌛ این دعوت منقضی شد."
        stake = r["stake"]
        if c["coins"] < stake or t["coins"] < stake:
            db.execute("UPDATE duel_requests SET status='cancelled' WHERE id=?", (rid,))
            return "edit", "یکی از طرفین سکه‌ی کافی نداره؛ دوئل لغو شد."
        chance = max(0.20, min(0.80, 0.5 + (duel_power(c) - duel_power(t)) / 200))
        win, lose = (c, t) if random.random() < chance else (t, c)
        prize = int(stake * 0.95)  # ۵٪ کارمزد
        db.execute("UPDATE users SET coins=coins-?, duel_losses=duel_losses+1 WHERE id=?", (stake, lose["id"]))
        db.execute("UPDATE users SET coins=coins+?, duel_wins=duel_wins+1 WHERE id=?", (prize, win["id"]))
        db.execute("UPDATE duel_requests SET status='done' WHERE id=?", (rid,))
        _, nw = grant_xp(win["id"], 25)
        _, nl = grant_xp(lose["id"], 8)
    return "edit", (f"⚔️ نتیجه‌ی دوئل\n\n🏆 {win['name']} برنده شد و {prize} سکه گرفت!\n"
                    f"😵 {lose['name']} باخت و {stake} سکه از دست داد.{nw}{nl}")


async def cb_duel(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or parts[1] not in ("y", "n") or not parts[2].isdigit():
        return await q.answer("دعوت نامعتبره.", show_alert=True)
    kind, text = resolve_duel(int(parts[2]), q.from_user.id, parts[1])
    if kind == "alert":
        return await q.answer(text, show_alert=True)
    await q.answer()
    await safe_edit(q, text)
    if "نتیجه‌ی دوئل" in text:
        await send_event_sticker(ctx, q.message.chat_id, "duel", 1.0)


# ============================== شرط‌بندی ==============================
@command("شرط", "bet", args=True, level=12)
async def cmd_bet(update, ctx, args):
    u = get_user(update.effective_user)
    cap = 200 * level_of(u["xp"])
    amount = parse_int(args[0]) if args else None
    if amount is None:
        return await update.message.reply_text(f"مثال: شرط 100\n(حداکثر شرط تو: {cap}، شانس برد ۴۵٪)")
    if amount < 10 or amount > cap:
        return await update.message.reply_text(f"مبلغ شرط باید بین ۱۰ تا {cap} باشه.")
    if u["coins"] < amount:
        return await update.message.reply_text("پول دستت کافی نیست.")
    left = cd_left(u, "last_bet", BET_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی شرط ببندی.")
    won = random.random() < 0.45
    with tx():
        set_time(u["id"], "last_bet")
        if won:
            add_coins(u["id"], amount)
        elif not spend(u["id"], amount):
            return await update.message.reply_text("پول دستت کافی نیست.")
        _, note = grant_xp(u["id"], 2)
    await reply_game(update, ctx, (f"🎰 شانس باهات یار بود! 🤑\n━━━━━━━━━━━━━━\n💰 +{amount:,} سکه" if won
                                   else f"🎰 این دفعه شانس نیاوردی 😢\n━━━━━━━━━━━━━━\n💸 -{amount:,} سکه") + note,
                     "win" if won else "lose")


# ============================== سرداب (وضعیت سمت سرور) ==============================
def dungeon_view(uid, stage, hp, loot):
    text = (f"🕳 سرداب — مرحله {stage}/3\n❤️ جان: {hp}   💰 غنیمت: {loot}\n\n"
            f"یه {random.choice(ENEMIES)} جلوته! چیکار می‌کنی؟")
    kb = Markup([[Btn("⚔️ نبرد (ریسک بالا)", f"dg:{uid}:{stage}:f"),
                  Btn("🕵️ دزدکی (امن‌تر)", f"dg:{uid}:{stage}:s")]])
    return text, kb


@command("سرداب", "dungeon", level=9)
async def cmd_dungeon(update, ctx, args):
    u = get_user(update.effective_user)
    uid = u["id"]
    left = cd_left(u, "last_dungeon", DUNGEON_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی بری سرداب.")
    hp = 100 + best_power(uid, "armor")
    with tx():
        set_time(uid, "last_dungeon")
        db.execute("UPDATE users SET adv_count=adv_count+1 WHERE id=?", (uid,))
        bump(uid, "adv")
        db.execute("INSERT OR REPLACE INTO dungeon_runs(user_id, stage, hp, loot, ts) VALUES(?,1,?,0,?)",
                   (uid, hp, time.time()))
    text, kb = dungeon_view(uid, 1, hp, 0)
    await update.message.reply_text(text, reply_markup=kb)


def dungeon_step(uid, stage, choice):
    with tx():
        run = db.execute("SELECT * FROM dungeon_runs WHERE user_id=?", (uid,)).fetchone()
        if not run or run["stage"] != stage or time.time() - run["ts"] > DUNGEON_TTL:
            return {"kind": "alert", "text": "این مرحله دیگه معتبر نیست."}
        hp, loot = run["hp"], run["loot"]
        u = user_by_id(uid)
        scale = 1 + level_of(u["xp"]) * 0.03
        weapon, armor = best_power(uid, "weapon"), best_power(uid, "armor")
        if choice == "f":
            if random.random() < min(0.55 + weapon / 100, 0.90):
                loot += int(random.randint(40, 90) * scale)
                dmg, log = random.randint(5, 20), "⚔️ دشمن رو شکست دادی و غنیمت گرفتی!"
            else:
                dmg, log = random.randint(20, 45), "💥 دشمن زخمیت کرد و غنیمتی نگرفتی."
        else:
            if random.random() < 0.80:
                loot += int(random.randint(10, 30) * scale)
                dmg, log = random.randint(0, 8), "🕵️ بی‌صدا رد شدی و یه چیزی پیدا کردی."
            else:
                dmg, log = random.randint(10, 25), "👀 دیدنت و بهت حمله کردن."
        dmg = max(0, int(dmg * (1 - armor / 200 - (0.05 if u["cls"] == "warrior" else 0))))
        hp -= dmg
        log += f"\n💔 -{dmg} جان"
        if hp <= 0:
            if qty(uid, "potion2") > 0:
                use_one(uid, "potion2")
                hp = 75 if u["cls"] == "alchemist" else 60
                log += f"\n🧪✨ معجون بزرگ خوردی و با قدرت برگشتی! (جان: {hp})"
            elif qty(uid, "potion") > 0:
                use_one(uid, "potion")
                hp = 40 if u["cls"] == "alchemist" else 25
                log += f"\n🧪 معجون خوردی و از مرگ نجات پیدا کردی! (جان: {hp})"
            else:
                db.execute("DELETE FROM dungeon_runs WHERE user_id=?", (uid,))
                xp, note = grant_xp(uid, 5)
                return {"kind": "end", "text": f"{log}\n\n💀 تو سرداب مردی و غنیمت‌ها از دست رفت.\n✨ +{xp} XP{note}"}
        if stage >= 3:
            total = int((loot + random.randint(30, 80) * scale) * reward_mult(uid))
            db.execute("DELETE FROM dungeon_runs WHERE user_id=?", (uid,))
            add_coins(uid, total)
            xp, note = grant_xp(uid, 40)
            return {"kind": "end", "text": f"{log}\n\n🏆 از سرداب زنده بیرون اومدی!\n💰 جایزه: {total} سکه\n✨ +{xp} XP{note}"}
        db.execute("UPDATE dungeon_runs SET stage=?, hp=?, loot=?, ts=? WHERE user_id=?",
                   (stage + 1, hp, loot, time.time(), uid))
        return {"kind": "next", "log": log, "stage": stage + 1, "hp": hp, "loot": loot}


async def cb_dungeon(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 4 or not parts[1].isdigit() or not parts[2].isdigit() or parts[3] not in ("f", "s"):
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این سرداب مال تو نیست.", show_alert=True)
    res = dungeon_step(uid, int(parts[2]), parts[3])
    if res["kind"] == "alert":
        return await q.answer(res["text"], show_alert=True)
    await q.answer()
    if res["kind"] == "end":
        await safe_edit(q, res["text"])
        return await send_event_sticker(ctx, q.message.chat_id, "win" if "🏆" in res["text"] else "lose", 1.0)
    text, kb = dungeon_view(uid, res["stage"], res["hp"], res["loot"])
    await safe_edit(q, f"{res['log']}\n\n{text}", kb)


# ============================== دوستان ==============================
def are_friends(a, b):
    x, y = sorted((a, b))
    return db.execute("SELECT 1 FROM friends WHERE a=? AND b=?", (x, y)).fetchone() is not None


@command("دوست", "friend")
async def cmd_friend(update, ctx, args):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if not target or target.is_bot or target.id == update.effective_user.id:
        return await msg.reply_text("برای درخواست دوستی، روی پیام بازیکن موردنظر ریپلای کن و بنویس: دوست")
    me, other = get_user(update.effective_user), user_by_id(target.id)
    if not has_char(other):
        return await msg.reply_text("این بازیکن هنوز شخصیت نساخته.")
    if are_friends(me["id"], other["id"]):
        return await msg.reply_text("شما از قبل دوست هستید.")
    db.execute("INSERT OR REPLACE INTO friend_requests(from_id, to_id, chat_id, ts) VALUES(?,?,?,?)",
               (me["id"], other["id"], msg.chat_id, time.time()))
    kb = Markup([[Btn("✅ قبول دوستی", f"friend_accept:{me['id']}:{other['id']}"),
                  Btn("❌ رد", f"friend_reject:{me['id']}:{other['id']}")]])
    await msg.reply_text(f"🤝 {me['name']} برای {other['name']} درخواست دوستی فرستاد.", reply_markup=kb)


async def cb_friend(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return await q.answer()
    action, from_id, to_id = parts[0], int(parts[1]), int(parts[2])
    if q.from_user.id != to_id:
        return await q.answer("این درخواست برای تو نیست.", show_alert=True)
    with tx():
        req = db.execute("SELECT ts FROM friend_requests WHERE from_id=? AND to_id=?", (from_id, to_id)).fetchone()
        if not req:
            return await q.answer("این درخواست قبلاً تعیین تکلیف شده.", show_alert=True)
        db.execute("DELETE FROM friend_requests WHERE from_id=? AND to_id=?", (from_id, to_id))
        expired = time.time() - req["ts"] > 86400
        if action == "friend_accept" and not expired:
            a, b = sorted((from_id, to_id))
            db.execute("INSERT OR IGNORE INTO friends(a, b, since) VALUES(?,?,?)", (a, b, time.time()))
    if expired:
        await q.answer("درخواست منقضی شده بود.")
        return await safe_edit(q, "⌛ درخواست دوستی منقضی شد.")
    if action == "friend_accept":
        await q.answer("درخواست دوستی قبول شد! ❤️")
        return await safe_edit(q, f"🤝 دوستی بین {user_by_id(from_id)['name']} و {user_by_id(to_id)['name']} ثبت شد.")
    await q.answer("درخواست رد شد.")
    await safe_edit(q, "❌ درخواست دوستی رد شد.")


@command("دوستان", "friends")
async def cmd_friends(update, ctx, args):
    uid = update.effective_user.id
    rows = db.execute("SELECT u.* FROM friends f JOIN users u ON u.id=CASE WHEN f.a=? THEN f.b ELSE f.a END "
                      "WHERE f.a=? OR f.b=? ORDER BY u.name", (uid, uid, uid)).fetchall()
    if not rows:
        return await update.message.reply_text("🤝 هنوز دوستی نداری. روی پیام یه بازیکن ریپلای کن و بنویس «دوست».")
    await update.message.reply_text("🤝 فهرست دوستان\n\n" + "\n".join(
        f"• {r['name']} — لول {level_of(r['xp'])} | {CLASSES.get(r['cls'], ('—',))[0]}" for r in rows))


@command("حذف دوست", "unfriend")
async def cmd_unfriend(update, ctx, args):
    rm = update.message.reply_to_message
    if not rm:
        return await update.message.reply_text("برای حذف دوست، روی پیام او ریپلای کن و بنویس: حذف دوست")
    a, b = sorted((update.effective_user.id, rm.from_user.id))
    cur = db.execute("DELETE FROM friends WHERE a=? AND b=?", (a, b))
    await update.message.reply_text("دوستی حذف شد." if cur.rowcount else "این بازیکن توی فهرست دوستانت نیست.")


# ============================== زیرساخت: متا، رویداد، صندوق پیام ==============================
def meta_get(k, default=None):
    r = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(k, v):
    db.execute("INSERT INTO meta(k, v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


_EVENT = {}


def _event_load():
    if not _EVENT:
        _EVENT.update(mult=float(meta_get("event_mult", 1) or 1), until=float(meta_get("event_until", 0) or 0),
                      name=meta_get("event_name", "") or "🎉 رویداد ویژه")
    return _EVENT


def is_golden_friday(now=None):
    now = time.time() if now is None else now
    return time.gmtime(now + 3.5 * 3600).tm_wday == 4   # جمعه به وقت ایران (UTC+3:30)


def event_mult(now=None):
    """(ضریب، برچسب): بزرگ‌ترین بین جمعه‌ی طلایی و رویداد ادمین."""
    now = time.time() if now is None else now
    mult, label = 1.0, ""
    if is_golden_friday(now):
        mult, label = GOLDEN_FRIDAY, "🌟 جمعه‌ی طلایی"
    ev = _event_load()
    if ev["until"] > now and ev["mult"] > mult:
        mult, label = ev["mult"], ev["name"]
    return mult, label


def xp_mult():
    return event_mult()[0] * season_perk("xp")


@command("رویداد", "event", args=True)
async def cmd_event(update, ctx, args):
    if args and is_admin(update.effective_user.id):
        if args[0] in ("پایان", "end", "stop"):
            meta_set("event_until", 0)
            _EVENT.clear()
            return await update.message.reply_text("🛑 رویداد ادمین پایان یافت.")
        try:
            mult = float(args[0])
            hours = float(args[1]) if len(args) > 1 else 1.0
        except ValueError:
            return await update.message.reply_text("مثال: رویداد 2 3 نام‌اختیاری  (۲ برابر برای ۳ ساعت)\nپایان: رویداد پایان")
        if not (1.0 < mult <= 5) or not (0 < hours <= 72):
            return await update.message.reply_text("ضریب باید بین ۱ تا ۵ و مدت بین ۰ تا ۷۲ ساعت باشه.")
        meta_set("event_mult", mult)
        meta_set("event_until", time.time() + hours * 3600)
        meta_set("event_name", " ".join(args[2:]) or "🎉 رویداد ویژه")
        _EVENT.clear()
        await send_event_sticker(ctx, update.effective_chat.id, "welcome", 1.0)
        return await update.message.reply_text(
            f"🎉🔥 رویداد شروع شد!\n━━━━━━━━━━━━━━\nXP و سکه‌ی کار ×{mult:g} تا {hours:g} ساعت دیگه!\nبدوید که فرصت کمه ⚡")
    mult, label = event_mult()
    if mult > 1:
        text = f"{label}\n━━━━━━━━━━━━━━\n✨ XP و سکه‌ی کار ×{mult:g} فعاله!"
        ev = _event_load()
        if ev["until"] > time.time() and ev["mult"] >= mult:
            text += f"\n⏳ تا پایان: {fmt_time(ev['until'] - time.time())}"
    else:
        text = "🎪 الان رویداد ویژه‌ای فعال نیست."
    await update.message.reply_text(text + f"\n\n🌟 هر جمعه (به وقت ایران) «جمعه‌ی طلایی» با XP و سکه‌ی کار ×{GOLDEN_FRIDAY:g} برمی‌گرده!")


# ---------- صندوق پیام: خبر دادن به بازیکن‌هایی که آنلاین نیستن ----------
def notify(uid, text):
    db.execute("INSERT INTO notices(user_id, text, ts) VALUES(?,?,?)", (uid, text, time.time()))


async def deliver_notices(ctx, chat_id, uid):
    rows = db.execute("SELECT id, text FROM notices WHERE user_id=? ORDER BY id LIMIT 5", (uid,)).fetchall()
    if not rows:
        return
    name = (user_by_id(uid) or {"name": ""})["name"]
    await ctx.bot.send_message(chat_id, f"📬 پیام‌های تازه برای {name}\n━━━━━━━━━━━━━━\n" +
                               "\n\n".join(r["text"] for r in rows))
    db.execute(f"DELETE FROM notices WHERE id IN ({','.join('?' * len(rows))})", [r["id"] for r in rows])


def give_item(uid, key):
    """وسیله رو می‌ده؛ اگه جا نداشت یا قبلاً داشت، معادل نصف قیمتش سکه می‌ده. متن نتیجه رو برمی‌گردونه."""
    cap = CONSUMABLE_MAX if ITEMS[key][1] == "misc" else 1
    if qty(uid, key) < cap:
        db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                   "ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+1", (uid, key))
        if ITEMS[key][1] in SLOTS:
            auto_equip(uid, key)
        return f"🎁 {ITEMS[key][0]}"
    cash = ITEMS[key][2] // 2
    add_coins(uid, cash)
    return f"🎁 {ITEMS[key][0]} (قبلاً داشتی؛ {cash:,} سکه گرفتی)"


def auto_equip(uid, key):
    cat = ITEMS[key][1]
    cur = db.execute("SELECT item FROM equipped WHERE user_id=? AND slot=?", (uid, cat)).fetchone()
    if not cur or cur["item"] not in ITEMS or enhanced_power(uid, cur["item"]) < enhanced_power(uid, key):
        db.execute("INSERT INTO equipped(user_id, slot, item) VALUES(?,?,?) "
                   "ON CONFLICT(user_id, slot) DO UPDATE SET item=excluded.item", (uid, cat, key))
        return True
    return False


def fmt_days(sec):
    d, rem = divmod(max(0, int(sec)), 86400)
    h = rem // 3600
    return f"{d} روز و {h} ساعت" if d else f"{h} ساعت و {rem % 3600 // 60} دقیقه"


# ============================== فصل‌ها 🌟 ==============================
SEASON_THEMES = [  # (ایموجی، اسم، داستان، نوع مزیت، مقدار، توضیح مزیت)
    ("🔥", "فصل آتش", "شعله‌ها بیدار شدن و غول‌ها سوزان‌تر از همیشه‌ان!", "boss_dmg", 1.10, "+۱۰٪ آسیب به غول‌ها"),
    ("💰", "فصل زر", "بازارها پر از طلاست؛ هر کار سکه‌ی بیشتری داره!", "work_coins", 1.10, "+۱۰٪ سکه‌ی کار"),
    ("⛈", "فصل طوفان", "آسمون غرش می‌کنه و ماجراجوها غنیمت بیشتری می‌برن!", "adv_coins", 1.10, "+۱۰٪ غنیمت ماجراجویی"),
    ("🌠", "فصل ستاره", "ستاره‌ها راه رو روشن کردن؛ یادگیری سریع‌تر می‌شه!", "xp", 1.10, "+۱۰٪ XP"),
    ("🍀", "فصل شانس", "شانس همراه توئه؛ چرخ شانس سخاوتمندتر می‌چرخه!", "wheel", 1.15, "+۱۵٪ جایزه‌ی سکه‌ی چرخ شانس"),
    ("🏪", "فصل بازرگانان", "تجار تخفیف می‌دن و بازار داغه!", "shop", 0.92, "۸٪ تخفیف فروشگاه و کارمزد کمتر بازار"),
    ("🌑", "فصل سایه", "تاریکی همه‌جا رو گرفته؛ ضربه‌های مرگبار از سایه می‌رسن!", "crit", 0.10, "+۱۰٪ شانس ضربه‌ی بحرانی روی غول‌ها"),
]
_SEASON = {}


def season_now():
    if not _SEASON:
        no = meta_get("season_no")
        if no is None:
            end = time.time() + SEASON_DAYS * 86400
            meta_set("season_no", 1)
            meta_set("season_end", end)
            _SEASON.update(no=1, end=end)
        else:
            _SEASON.update(no=int(no), end=float(meta_get("season_end")))
    return _SEASON


def season_theme(no):
    return SEASON_THEMES[(no - 1) % len(SEASON_THEMES)]


def season_perk(kind):
    th = season_theme(season_now()["no"])
    if th[3] == kind:
        return th[4]
    return 0.0 if kind == "crit" else 1.0


def add_sp(uid, pts):
    if pts > 0:
        db.execute("INSERT INTO season_points(season, user_id, pts) VALUES(?,?,?) "
                   "ON CONFLICT(season, user_id) DO UPDATE SET pts=season_points.pts+excluded.pts",
                   (season_now()["no"], uid, pts))


def sp_of(uid, no=None):
    r = db.execute("SELECT pts FROM season_points WHERE season=? AND user_id=?",
                   (no or season_now()["no"], uid)).fetchone()
    return r["pts"] if r else 0


def sp_rank(uid, no=None):
    no = no or season_now()["no"]
    return db.execute("SELECT COUNT(*)+1 FROM season_points WHERE season=? AND pts>?",
                      (no, sp_of(uid, no))).fetchone()[0]


def season_title(uid):
    r = db.execute("SELECT title FROM season_titles WHERE user_id=? ORDER BY season DESC LIMIT 1", (uid,)).fetchone()
    return r["title"] if r else ""


RANK_REWARD = {1: (25000, "champ1"), 2: (15000, "champ2"), 3: (10000, "champ2")}


def settle_season():
    """فصل جاری رو می‌بنده: رتبه‌ها، جایزه‌ها، لقب‌ها؛ بعد فصل بعدی رو شروع می‌کنه."""
    s = season_now()
    no, th = s["no"], season_theme(s["no"])
    with tx():
        rows = db.execute(
            "SELECT p.user_id, p.pts, u.name FROM season_points p JOIN users u ON u.id=p.user_id "
            "WHERE p.season=? AND p.pts>=? ORDER BY p.pts DESC, p.user_id", (no, SEASON_MIN_PTS)).fetchall()
        for i, r in enumerate(rows):
            place, uid = i + 1, r["user_id"]
            coins, extra = min(5000, r["pts"] // 2), ""
            if place in RANK_REWARD:
                bonus, key = RANK_REWARD[place]
                coins += bonus
                db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                           "ON CONFLICT(user_id, item) DO UPDATE SET qty=1", (uid, key))
                extra = f"\n🎖 جایزه‌ی ویژه: {ITEMS[key][0]}"
            elif place <= 10:
                coins += 4000
            if coins:
                add_coins(uid, coins)
            if place <= 10:
                db.execute("INSERT OR REPLACE INTO season_results(season, place, user_id, name, pts) VALUES(?,?,?,?,?)",
                           (no, place, uid, r["name"], r["pts"]))
            if place <= 3:
                db.execute("INSERT OR REPLACE INTO season_titles(user_id, season, place, title) VALUES(?,?,?,?)",
                           (uid, no, place, f"{'🥇🥈🥉'[place - 1]} قهرمان {th[1]}"))
            if coins or place <= 10:
                notify(uid, f"{th[0]} فصل {no} ({th[1]}) تموم شد!\n🏅 رتبه‌ی تو: {place} با {r['pts']:,} امتیاز\n"
                            f"💰 جایزه: +{coins:,} سکه{extra}")
        meta_set("season_no", no + 1)
        now = time.time()
        # بسته شدن به‌موقع: ریتم فصل‌ها حفظ می‌شه؛ بسته شدن زودتر (دستی) یا بعد از قطعی طولانی: از همین الان
        end = s["end"] + SEASON_DAYS * 86400 if s["end"] <= now else now + SEASON_DAYS * 86400
        if end <= now:
            end = now + SEASON_DAYS * 86400
        meta_set("season_end", end)
    _SEASON.update(no=no + 1, end=end)


def season_result_text(prev):
    th = season_theme(prev)
    rows = db.execute("SELECT * FROM season_results WHERE season=? ORDER BY place LIMIT 5", (prev,)).fetchall()
    lines = [f"{th[0]} فصل {prev} ({th[1]}) تموم شد!", "━━━━━━━━━━━━━━", "🏆 برترین‌های فصل:"]
    lines += [f"{'🥇🥈🥉🏅🏅'[r['place'] - 1]} {r['name']} — {r['pts']:,} امتیاز" for r in rows]
    return "\n".join(lines) + "\n\n🎁 جایزه‌ها به صندوق پیام برنده‌ها رفت."


def season_intro_text():
    s = season_now()
    th = season_theme(s["no"])
    return (f"🌟 فصل {s['no']} شروع شد! {th[0]} {th[1]}\n━━━━━━━━━━━━━━\n{th[2]}\n\n"
            f"✨ مزیت فصل: {th[5]}\n⏳ مدت: {fmt_days(s['end'] - time.time())}\n\n"
            "📊 امتیاز فصل = XP که توی این فصل جمع می‌کنی.\n"
            "🏆 سه نفر اول لقب و آیتم افسانه‌ای می‌گیرن، ده نفر اول جایزه‌ی سکه.\n"
            "🛣 با «جاده» پله‌پله جایزه بگیر و با «فصل» رتبه‌ات رو ببین!")


_season_tick, _market_sweep_t = {}, [0.0]


async def season_tick(ctx, chat_id):
    """پایان فصل، اعلام نتیجه توی هر گروه (فقط یک بار) و جارو کردن بازار؛ خطاها بی‌صدا."""
    try:
        if time.time() >= season_now()["end"]:
            settle_season()
        now = time.monotonic()
        if now - _market_sweep_t[0] > 300:
            _market_sweep_t[0] = now
            market_sweep()
            db.execute("DELETE FROM notices WHERE ts<?", (time.time() - 14 * 86400,))
        last = _season_tick.get(chat_id)
        if last is not None and now - last < 60:
            return
        if len(_season_tick) > 20000:
            _season_tick.clear()
        _season_tick[chat_id] = now
        c = db.execute("SELECT season_seen FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        no = season_now()["no"]
        if not c or c["season_seen"] >= no:
            return
        text = season_intro_text()
        if c["season_seen"] > 0 and db.execute("SELECT 1 FROM season_results WHERE season=?", (no - 1,)).fetchone():
            text = season_result_text(no - 1) + "\n\n" + text
        db.execute("UPDATE chats SET season_seen=? WHERE chat_id=?", (no, chat_id))
        await send_event_sticker(ctx, chat_id, "season", 1.0)
        await ctx.bot.send_message(chat_id, text)
    except Exception as e:
        logging.warning("season_tick: %s", e)


@command("فصل", "season")
async def cmd_season(update, ctx, args):
    u = get_user(update.effective_user)
    s = season_now()
    th = season_theme(s["no"])
    top = db.execute("SELECT p.pts, u.name FROM season_points p JOIN users u ON u.id=p.user_id "
                     "WHERE p.season=? AND p.pts>0 ORDER BY p.pts DESC LIMIT 5", (s["no"],)).fetchall()
    lines = [f"🌟 فصل {s['no']} — {th[0]} {th[1]}", "━━━━━━━━━━━━━━", th[2], "",
             f"✨ مزیت فصل: {th[5]}", f"⏳ مونده: {fmt_days(s['end'] - time.time())}"] + \
            (["🔥 فصل داره تموم می‌شه! آخرین فرصت برای بالا رفتن توی جدول!"] if s["end"] - time.time() < 2 * 86400 else []) + [""] + [
             f"📊 امتیاز تو: {sp_of(u['id']):,}  (رتبه‌ی {sp_rank(u['id'])})"]
    if top:
        lines += ["", "🏆 برترین‌های فصل:"] + [f"{'🥇🥈🥉🏅🏅'[i]} {r['name']} — {r['pts']:,}" for i, r in enumerate(top)]
    lines += ["", "🎁 جایزه‌ی پایان فصل: ۳ نفر اول لقب و آیتم افسانه‌ای، ۱۰ نفر اول سکه",
              "🛣 «جاده» = جایزه‌های پله‌ای  |  «برترین فصل» = جدول ۱۰ نفر"]
    await update.message.reply_text("\n".join(lines))


@command("برترین فصل", "رتبه فصل", "seasontop")
async def cmd_season_top(update, ctx, args):
    s = season_now()
    u = get_user(update.effective_user)
    rows = db.execute("SELECT p.pts, u.name FROM season_points p JOIN users u ON u.id=p.user_id "
                      "WHERE p.season=? AND p.pts>0 ORDER BY p.pts DESC LIMIT 10", (s["no"],)).fetchall()
    if not rows:
        return await update.message.reply_text("🏆 هنوز کسی امتیاز فصل نگرفته. اولین نفر باش!")
    lines = [f"🏆 برترین‌های فصل {s['no']} ({season_theme(s['no'])[1]})", "━━━━━━━━━━━━━━"]
    lines += [f"{'🥇🥈🥉'[i] if i < 3 else str(i + 1) + '.'} {r['name']} — {r['pts']:,}" for i, r in enumerate(rows)]
    lines += ["", f"📍 تو: رتبه‌ی {sp_rank(u['id'])} با {sp_of(u['id']):,} امتیاز"]
    await update.message.reply_text("\n".join(lines))


@command("پایان فصل", "endseason", admin=True)
async def cmd_end_season(update, ctx, args):
    settle_season()
    _season_tick.pop(update.effective_chat.id, None)
    await update.message.reply_text("🔚 فصل به‌صورت دستی بسته شد.")
    await season_tick(ctx, update.effective_chat.id)


# ---------- جاده‌ی فصل: ۱۰ پله جایزه ----------
ROAD = [  # (امتیاز لازم، نوع، مقدار)
    (150, "coins", 1500), (400, "item", "lock"), (800, "coins", 3500), (1300, "item", "potion2"),
    (2000, "coins", 6000), (3000, "item", "lock2"), (4200, "coins", 10000), (5600, "item", "potion2"),
    (7200, "coins", 16000), (9000, "item", "road1"),
]


def road_label(kind, val):
    return f"💰 {val:,} سکه" if kind == "coins" else ITEMS[val][0]


def road_claimed(uid, no=None):
    return {r["tier"] for r in db.execute("SELECT tier FROM road_claims WHERE season=? AND user_id=?",
                                          (no or season_now()["no"], uid))}


def road_view(u, note=""):
    uid, no = u["id"], season_now()["no"]
    th, pts, claimed = season_theme(no), sp_of(uid), road_claimed(uid)
    lines = ([note, ""] if note else []) + [f"🛣 جاده‌ی فصل {no} — {th[0]} {th[1]}", f"🌟 امتیاز تو: {pts:,}", "━━━━━━━━━━━━━━"]
    claimable = []
    for i, (need, kind, val) in enumerate(ROAD):
        if i in claimed:
            mark = "✅"
        elif pts >= need:
            mark, _ = "🎁", claimable.append(i)
        else:
            mark = "🔒"
        lines.append(f"{mark} پله {i + 1} — {need:,}: {road_label(kind, val)}")
    nxt = next((i for i, t in enumerate(ROAD) if t[0] > pts), None)
    if nxt is not None:
        base = ROAD[nxt - 1][0] if nxt else 0
        lines += ["", f"🎯 تا پله‌ی {nxt + 1}: [{bar(pts - base, ROAD[nxt][0] - base)}] {ROAD[nxt][0] - pts:,} امتیاز"]
    else:
        lines += ["", "🏁 همه‌ی پله‌ها رو رد کردی! افسانه‌ای!"]
    kb = [[Btn(f"🎁 پله {i + 1}", f"road_claim:{uid}:{i}") for i in claimable[j:j + 3]] for j in range(0, len(claimable), 3)]
    if len(claimable) > 1:
        kb.append([Btn("🎁 دریافت همه", f"road_claim:{uid}:all")])
    return "\n".join(lines), Markup(kb) if kb else None


def road_claim(uid, idx):
    with tx():
        no = season_now()["no"]
        if not 0 <= idx < len(ROAD):
            return False, "پله‌ی نامعتبره."
        need, kind, val = ROAD[idx]
        if sp_of(uid) < need:
            return False, "هنوز به این پله نرسیدی."
        if not db.execute("INSERT OR IGNORE INTO road_claims(season, user_id, tier) VALUES(?,?,?)",
                          (no, uid, idx)).rowcount:
            return False, "این پله رو قبلاً گرفتی."
        if kind == "coins":
            add_coins(uid, val)
            return True, f"💰 +{val:,} سکه"
        return True, give_item(uid, val)


@command("جاده", "road")
async def cmd_road(update, ctx, args):
    text, kb = road_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


async def cb_road(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    claimed_before = road_claimed(uid)
    idxs = [i for i, t in enumerate(ROAD) if i not in claimed_before and sp_of(uid) >= t[0]] if parts[2] == "all" \
        else ([int(parts[2])] if parts[2].isdigit() else [])
    got, errors = [], []
    for i in idxs:
        ok_, text = road_claim(uid, i)
        (got if ok_ else errors).append(text)
    if not got:
        return await q.answer(errors[0] if errors else "چیزی برای دریافت نیست.", show_alert=True)
    await q.answer("🎁 دریافت شد!")
    note = "🎉 دریافت شد:\n" + "\n".join(got)
    text, kb = road_view(user_by_id(uid), note)
    await safe_edit(q, text, kb)
    await send_event_sticker(ctx, q.message.chat_id, "daily", 1.0)


# ============================== آهنگری ⚒ ==============================
FORGE_STEP = {"weapon": 0.08, "armor": 0.06, "tool": 0.08, "charm": 0.04}


def plus_row(uid, key):
    r = db.execute("SELECT plus, fails FROM item_plus WHERE user_id=? AND item=?", (uid, key)).fetchone()
    return (r["plus"], r["fails"]) if r else (0, 0)


def forge_step(key):
    return max(1, math.ceil(ITEMS[key][4] * FORGE_STEP.get(ITEMS[key][1], 0.05)))


def enhanced_power(uid, key):
    return ITEMS[key][4] + plus_row(uid, key)[0] * forge_step(key)


def gear_name(uid, key):
    plus = plus_row(uid, key)[0]
    return f"{ITEMS[key][0]} +{plus}" if plus else ITEMS[key][0]


def forge_cost(key, plus):
    return max(200, int(ITEMS[key][2] * 0.06 * (plus + 1)))


def do_forge(uid, slot):
    with tx():
        key = equipped_items(uid).get(slot)
        if not key:
            return {"error": "توی این اسلات وسیله‌ی فعالی نداری."}
        plus, fails = plus_row(uid, key)
        if plus >= FORGE_MAX:
            return {"error": "این وسیله به حداکثر تقویت رسیده 🔥"}
        cost = forge_cost(key, plus)
        if not spend(uid, cost):
            return {"error": f"سکه‌ی کافی نداری (هزینه: {cost:,})"}
        chance = min(100, FORGE_CHANCE[plus] + 5 * fails)
        success = random.random() * 100 < chance
        note = ""
        if success:
            db.execute("INSERT INTO item_plus(user_id, item, plus, fails) VALUES(?,?,?,0) "
                       "ON CONFLICT(user_id, item) DO UPDATE SET plus=excluded.plus, fails=0", (uid, key, plus + 1))
            _, note = grant_xp(uid, 5 + plus)
        else:
            db.execute("INSERT INTO item_plus(user_id, item, plus, fails) VALUES(?,?,?,1) "
                       "ON CONFLICT(user_id, item) DO UPDATE SET fails=item_plus.fails+1", (uid, key, plus))
    return {"ok": success, "key": key, "plus": plus + (1 if success else 0), "cost": cost, "chance": chance, "note": note}


def forge_view(u, note=""):
    uid, eq = u["id"], equipped_items(u["id"])
    lines = ([note, ""] if note else []) + ["⚒ آهنگری", "━━━━━━━━━━━━━━", f"💰 سکه‌ات: {u['coins']:,}", ""]
    kb = []
    for sl in SLOTS:
        key = eq.get(sl)
        if not key:
            lines.append(f"{SLOT_LABELS[sl]}: —")
            continue
        plus, fails = plus_row(uid, key)
        lines.append(f"{SLOT_LABELS[sl]}: {gear_name(uid, key)} • قدرت {enhanced_power(uid, key)}")
        if plus >= FORGE_MAX:
            lines.append("   🔥 حداکثر تقویت!")
            continue
        cost, chance = forge_cost(key, plus), min(100, FORGE_CHANCE[plus] + 5 * fails)
        pity = f" (+{5 * fails}٪ جبرانی)" if fails else ""
        lines.append(f"   ⚒ بعدی: +{plus + 1} — {cost:,} سکه — شانس {chance}٪{pity}")
        kb.append([Btn(f"⚒ تقویت {SLOT_LABELS[sl]} ({cost:,})", f"forge:{uid}:{sl}")])
    lines += ["", "💡 شکست فقط هزینه رو می‌گیره و وسیله هیچ‌وقت خراب نمی‌شه؛ هر شکست شانس بعدی رو بیشتر می‌کنه!"]
    return "\n".join(lines), Markup(kb) if kb else None


@command("آهنگری", "forge", level=5)
async def cmd_forge(update, ctx, args):
    text, kb = forge_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


async def cb_forge(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in SLOTS:
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    if level_of(user_by_id(uid)["xp"]) < 5 and not is_admin(uid):
        return await q.answer("آهنگری از لول ۵ باز می‌شه.", show_alert=True)
    res = do_forge(uid, parts[2])
    if "error" in res:
        return await q.answer(res["error"], show_alert=True)
    name = ITEMS[res["key"]][0]
    if res["ok"]:
        await q.answer(f"✅ +{res['plus']} شد!")
        note = f"✅ تقویت موفق! {name} حالا +{res['plus']} شد 🔥" + res["note"]
        await send_event_sticker(ctx, q.message.chat_id, "levelup" if "🎊🎉" in res["note"] else "forge",
                                 1.0 if res["plus"] >= 5 else None)
    else:
        await q.answer("💥 نشد! ولی دفعه‌ی بعد شانست بیشتره")
        note = f"💥 تقویت ناموفق! ({res['cost']:,} سکه رفت)\nوسیله سالمه و شانس بعدی‌ت +۵٪ بیشتره 💪"
        await send_event_sticker(ctx, q.message.chat_id, "lose")
    text, kb = forge_view(user_by_id(uid), note)
    await safe_edit(q, text, kb)


# ============================== بازار بازیکن‌ها 🏪 ==============================
MARKET_CATS = [("all", "🏪 همه"), ("weapon", "⚔️"), ("armor", "🛡"), ("tool", "⛏"), ("charm", "🍀")]


def tradeable(key):
    return key in ITEMS and ITEMS[key][1] in SLOTS and key not in HIDDEN_ITEMS


def market_fee():
    return 0.02 if season_perk("shop") < 1 else MARKET_FEE


def market_sweep():
    """آگهی‌های منقضی رو می‌بنده و وسیله رو به فروشنده برمی‌گردونه."""
    rows = db.execute("SELECT * FROM market WHERE expires<=?", (time.time(),)).fetchall()
    if not rows:
        return 0
    with tx():
        for r in rows:
            if db.execute("DELETE FROM market WHERE id=?", (r["id"],)).rowcount:
                give_item(r["seller"], r["item"])
                notify(r["seller"], f"⌛ آگهی {ITEMS[r['item']][0]} منقضی شد و وسیله به کوله‌ات برگشت.")
    return len(rows)


def list_item(uid, key, pct):
    with tx():
        if not tradeable(key):
            return False, "این وسیله قابل عرضه نیست."
        if pct not in MARKET_PCTS:
            return False, "قیمت نامعتبره."
        if qty(uid, key) <= 0:
            return False, "این وسیله رو نداری."
        if db.execute("SELECT COUNT(*) FROM market WHERE seller=?", (uid,)).fetchone()[0] >= MARKET_MAX_LIST:
            return False, f"حداکثر {MARKET_MAX_LIST} آگهی فعال می‌تونی داشته باشی."
        price, now = max(50, ITEMS[key][2] * pct // 100), time.time()
        db.execute("UPDATE items SET qty=qty-1 WHERE user_id=? AND item=?", (uid, key))
        db.execute("INSERT INTO market(seller, item, price, ts, expires) VALUES(?,?,?,?,?)",
                   (uid, key, price, now, now + MARKET_TTL))
    return True, price


def cancel_listing(uid, lid):
    with tx():
        row = db.execute("SELECT * FROM market WHERE id=? AND seller=?", (lid, uid)).fetchone()
        if not row:
            return False, "این آگهی دیگه وجود نداره."
        db.execute("DELETE FROM market WHERE id=?", (lid,))
        give_item(uid, row["item"])
    return True, f"{ITEMS[row['item']][0]} به کوله‌ات برگشت."


def market_buy(uid, lid):
    with tx():
        row = db.execute("SELECT * FROM market WHERE id=?", (lid,)).fetchone()
        if not row:
            return False, "این آگهی دیگه وجود نداره (فروخته یا لغو شد)."
        if row["expires"] <= time.time():
            return False, "این آگهی منقضی شده."
        key, seller, price, u = row["item"], row["seller"], row["price"], user_by_id(uid)
        if seller == uid:
            return False, "نمی‌تونی آگهی خودت رو بخری."
        if not item_usable(u, key):
            return False, f"🔐 این وسیله ویژه‌ی {req_text(key)} هست."
        if level_of(u["xp"]) < ITEMS[key][3] and not is_admin(uid):
            return False, f"🔒 این وسیله از لول {ITEMS[key][3]} باز می‌شه."
        if qty(uid, key) > 0 or db.execute("SELECT 1 FROM market WHERE seller=? AND item=?", (uid, key)).fetchone():
            return False, "این وسیله رو قبلاً داری."
        premium = max(0, price - ITEMS[key][2])   # مبلغِ بالاتر از قیمت فروشگاه، یعنی عملاً انتقال پول
        if premium:
            cap = TRANSFER_DAILY_PER_LEVEL * level_of(u["xp"])
            db.execute("INSERT OR IGNORE INTO daily_stats(user_id, day) VALUES(?, ?)", (uid, today()))
            sent = db.execute("SELECT sent FROM daily_stats WHERE user_id=? AND day=?", (uid, today())).fetchone()["sent"]
            if sent + premium > cap:
                return False, (f"این آگهی {premium:,} سکه بالاتر از قیمت فروشگاهه و به سقف انتقال روزانه‌ات "
                               f"({cap:,}) حساب می‌شه؛ امروز {sent:,} مصرف کردی.")
        if not spend(uid, price):
            return False, f"سکه‌ات کافی نیست! (قیمت: {price:,})"
        if premium:
            db.execute("UPDATE daily_stats SET sent=sent+? WHERE user_id=? AND day=?", (premium, uid, today()))
        fee = int(price * market_fee())
        add_coins(seller, price - fee)
        db.execute("DELETE FROM market WHERE id=?", (lid,))
        db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                   "ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+1", (uid, key))
        auto_equip(uid, key)
        db.execute("UPDATE users SET market_sales=market_sales+1 WHERE id=?", (seller,))
        notify(seller, f"🏷 {u['name']} وسیله‌ی {ITEMS[key][0]} تو رو {price:,} سکه خرید!\n"
                       f"💰 +{price - fee:,} سکه به حسابت اومد (کارمزد بازار: {fee:,})")
    return True, f"{ITEMS[key][0]} رو {price:,} سکه خریدی! ✅"


def _listing_line(i, r, viewer):
    key = r["item"]
    tag = ITEM_RARITY.get(key, "")
    pct = int(100 * r["price"] / max(1, ITEMS[key][2]))
    lock = "" if level_of(viewer["xp"]) >= ITEMS[key][3] else f" 🔒لول {ITEMS[key][3]}"
    return (f"{i}) {tag + ' ' if tag else ''}{ITEMS[key][0]}{req_label(key)}{lock}\n"
            f"   💰 {r['price']:,} سکه ({pct}٪ قیمت فروشگاه) • 👤 {r['sname']} • ⏳ {fmt_days(r['expires'] - time.time())}\n"
            f"   {ITEMS[key][5]}")


def market_view(u, cat="all", page=0, note=""):
    market_sweep()
    uid = u["id"]
    rows = [r for r in db.execute(
        "SELECT m.*, s.name AS sname FROM market m JOIN users s ON s.id=m.seller ORDER BY m.price, m.id LIMIT 500")
        if (cat == "all" or ITEMS[r["item"]][1] == cat) and (item_usable(u, r["item"]) or r["seller"] == uid)]
    pages = max(1, math.ceil(len(rows) / MARKET_PAGE))
    page = max(0, min(page, pages - 1))
    chunk = rows[page * MARKET_PAGE:(page + 1) * MARKET_PAGE]
    lines = ([note, ""] if note else []) + ["🏪 بازار بازیکن‌ها", "━━━━━━━━━━━━━━",
                                            f"💰 سکه‌ات: {u['coins']:,}   📄 صفحه‌ی {page + 1}/{pages}", ""]
    kb = []
    if not chunk:
        lines.append("😴 هنوز آگهی‌ای نیست. اولین نفر باش و وسیله‌ات رو عرضه کن!")
    for i, r in enumerate(chunk, 1):
        lines.append(_listing_line(i, r, u))
        if r["seller"] != uid:
            kb.append([Btn(f"🛒 {i}) {ITEMS[r['item']][0]} — {r['price']:,}", f"mk_buy:{uid}:{r['id']}:{cat}:{page}")])
    kb.append([Btn(("• " if c == cat else "") + label, f"mk_page:{uid}:{c}:0") for c, label in MARKET_CATS])
    nav = []
    if page > 0:
        nav.append(Btn("◀️ قبلی", f"mk_page:{uid}:{cat}:{page - 1}"))
    if page < pages - 1:
        nav.append(Btn("بعدی ▶️", f"mk_page:{uid}:{cat}:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([Btn("🏷 عرضه‌ی وسیله", f"mk_offer:{uid}"), Btn("📋 آگهی‌های من", f"mk_mine:{uid}")])
    lines += ["", f"💡 فقط وسایل مناسب کلاس/شغل تو نشون داده می‌شه • کارمزد فروش {int(market_fee() * 100)}٪"]
    return "\n".join(lines), Markup(kb)


def offer_view(u, note=""):
    uid = u["id"]
    have = [k for k in owned(uid) if tradeable(k) and qty(uid, k) > 0]
    have.sort(key=lambda k: (ITEMS[k][1], ITEMS[k][2]))
    lines = ([note, ""] if note else []) + ["🏷 عرضه‌ی وسیله توی بازار", "━━━━━━━━━━━━━━",
                                            f"چه وسیله‌ای رو می‌خوای بفروشی؟ (حداکثر {MARKET_MAX_LIST} آگهی، {MARKET_TTL // 3600} ساعت اعتبار)"]
    kb = [[Btn(f"{ITEMS[k][0]} • قدرت {enhanced_power(uid, k)}", f"mk_pick:{uid}:{k}")] for k in have]
    if not have:
        lines.append("\n🎒 وسیله‌ی قابل عرضه‌ای نداری (وسایل ویژه‌ی جایزه‌ها قابل فروش نیستن).")
    kb.append([Btn("⬅️ بازار", f"mk_page:{uid}:all:0")])
    return "\n".join(lines), Markup(kb)


def offer_price_view(u, key):
    uid, base = u["id"], ITEMS[key][2]
    fee = int(market_fee() * 100)
    lines = ["🏷 قیمت‌گذاری", "━━━━━━━━━━━━━━", f"{ITEMS[key][0]}{req_label(key)}", f"💰 قیمت فروشگاه: {base:,}",
             f"🧾 کارمزد بازار: {fee}٪ (از مبلغ فروش کم می‌شه)",
             "⚠️ مبلغ بالاتر از ۱۰۰٪ توی سقف انتقال روزانه‌ی خریدار حساب می‌شه.", "", "قیمت رو انتخاب کن:"]
    kb = [[Btn(f"{p}٪ • {max(50, base * p // 100):,} سکه (دریافتی {max(50, base * p // 100) - int(max(50, base * p // 100) * market_fee()):,})",
               f"mk_list:{uid}:{key}:{p}")] for p in MARKET_PCTS]
    kb.append([Btn("⬅️ برگشت", f"mk_offer:{uid}")])
    return "\n".join(lines), Markup(kb)


def mine_view(u, note=""):
    uid = u["id"]
    rows = db.execute("SELECT * FROM market WHERE seller=? ORDER BY id", (uid,)).fetchall()
    lines = ([note, ""] if note else []) + ["📋 آگهی‌های من", "━━━━━━━━━━━━━━"]
    kb = []
    if not rows:
        lines.append("آگهی فعالی نداری.")
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}) {ITEMS[r['item']][0]} — {r['price']:,} سکه • ⏳ {fmt_days(r['expires'] - time.time())}")
        kb.append([Btn(f"❌ لغو {ITEMS[r['item']][0]}", f"mk_cancel:{uid}:{r['id']}")])
    kb.append([Btn("🏷 عرضه‌ی وسیله", f"mk_offer:{uid}"), Btn("⬅️ بازار", f"mk_page:{uid}:all:0")])
    return "\n".join(lines), Markup(kb)


@command("بازار", "market", level=5)
async def cmd_market(update, ctx, args):
    text, kb = market_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


@command("عرضه", "offer", level=5)
async def cmd_offer(update, ctx, args):
    text, kb = offer_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


@command("آگهی‌های من", "آگهی ها", "آگهی", "mylistings", level=5)
async def cmd_mine(update, ctx, args):
    text, kb = mine_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


async def cb_market(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        return await q.answer()
    uid, act = int(parts[1]), parts[0]
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    if level_of(user_by_id(uid)["xp"]) < 5 and not is_admin(uid):
        return await q.answer("بازار از لول ۵ باز می‌شه.", show_alert=True)
    u = user_by_id(uid)
    cats = {c for c, _ in MARKET_CATS}
    if act == "mk_page" and len(parts) == 4 and parts[2] in cats and parts[3].isdigit():
        text, kb = market_view(u, parts[2], int(parts[3]))
    elif act == "mk_buy" and len(parts) == 5 and parts[2].isdigit() and parts[3] in cats and parts[4].isdigit():
        ok_, msg = market_buy(uid, int(parts[2]))
        if not ok_:
            return await q.answer(msg, show_alert=True)
        await q.answer("✅ خریدی!")
        await send_event_sticker(ctx, q.message.chat_id, "market")
        text, kb = market_view(user_by_id(uid), parts[3], int(parts[4]), "✅ " + msg)
    elif act == "mk_offer":
        text, kb = offer_view(u)
    elif act == "mk_mine":
        text, kb = mine_view(u)
    elif act == "mk_pick" and len(parts) == 3 and tradeable(parts[2]) and qty(uid, parts[2]) > 0:
        text, kb = offer_price_view(u, parts[2])
    elif act == "mk_list" and len(parts) == 4 and parts[3].isdigit():
        ok_, res = list_item(uid, parts[2], int(parts[3]))
        if not ok_:
            return await q.answer(res, show_alert=True)
        await q.answer("✅ آگهی ثبت شد!")
        text, kb = mine_view(user_by_id(uid), f"✅ آگهی ثبت شد! قیمت: {res:,} سکه")
    elif act == "mk_cancel" and len(parts) == 3 and parts[2].isdigit():
        ok_, msg = cancel_listing(uid, int(parts[2]))
        await q.answer(msg, show_alert=not ok_)
        text, kb = mine_view(user_by_id(uid), ("✅ " if ok_ else "") + msg)
    else:
        return await q.answer()
    await safe_edit(q, text, kb)


# ============================== همراه‌ها 🐾 ==============================
SPECIES = {  # کلید: (ایموجی، اسم، نادری ۱ تا ۴، نوع توانایی، پایه٪، شیب٪ در هر لول)
    "dog": ("🐕", "سگ وفادار", 1, "coins", 3, 0.4), "cat": ("🐈", "گربه‌ی شانس", 1, "luck", 3, 0.4),
    "rabbit": ("🐇", "خرگوش چابک", 1, "xp", 3, 0.4), "fox": ("🦊", "روباه حیله‌گر", 1, "loot", 3, 0.4),
    "wolf": ("🐺", "گرگ شکارچی", 2, "dmg", 5, 0.6), "owl": ("🦉", "جغد دانا", 2, "xp", 5, 0.6),
    "boar": ("🐗", "گراز زره‌پوش", 2, "defense", 5, 0.6), "snake": ("🐍", "مار زهری", 2, "dmg", 5, 0.6),
    "eagle": ("🦅", "عقاب تیزبین", 3, "loot", 8, 0.8), "bear": ("🐻", "خرس قدرتمند", 3, "defense", 8, 0.8),
    "lion": ("🦁", "شیر جنگل", 3, "dmg", 8, 0.8), "panther": ("🐆", "یوزپلنگ سریع", 3, "coins", 8, 0.8),
    "dragon": ("🐉", "اژدهای کوچک", 4, "dmg", 12, 1.0), "unicorn": ("🦄", "تک‌شاخ جادویی", 4, "luck", 12, 1.0),
    "phoenix": ("🔥", "ققنوس", 4, "xp", 12, 1.0), "kraken": ("🐙", "کراکن بچه", 4, "coins", 12, 1.0),
}
RARITY_TAG = {1: "⚪ معمولی", 2: "🟦 نادر", 3: "🟪 حماسی", 4: "🟧 افسانه‌ای"}
BONUS_TEXT = {"coins": "سکه‌ی کار", "xp": "XP", "dmg": "آسیب به غول‌ها", "luck": "شانس برد ماجراجویی",
              "loot": "غنیمت ماجراجویی", "defense": "کاهش خسارت ماجراجویی"}
BONUS_CAP = {"coins": 25, "xp": 25, "loot": 30, "dmg": 40, "luck": 10, "defense": 25}
STAGE_MULT = {1: 1.0, 2: 1.15, 3: 1.3}
STAGE_NAME = {1: "🍼 نوزاد", 2: "⚔️ بالغ", 3: "👑 افسانه‌ای"}
EGG_ODDS = {1: [(1, 75), (2, 20), (3, 4.5), (4, 0.5)], 2: [(2, 65), (3, 30), (4, 5)], 3: [(3, 60), (4, 40)]}
HATCH_TIME = {1: 3 * 3600, 2: 6 * 3600, 3: 12 * 3600}
TRIPS = {1: (3600, 0.03), 4: (4 * 3600, 0.12), 8: (8 * 3600, 0.30)}   # ساعت: (مدت، شانس تخم)


def pet_xp_for(level):
    return 40 * (level - 1) * level // 2


def pet_level(xp):
    lvl = 1
    while lvl < PET_MAX_LEVEL and xp >= pet_xp_for(lvl + 1):
        lvl += 1
    return lvl


def pet_stage(level):
    return 1 if level < 10 else 2 if level < 20 else 3


def satiety(p, now=None):
    now = time.time() if now is None else now
    return max(0, min(100, int(100 - (now - p["fed_at"]) / 3600 * 3)))


def mood_factor(sat):
    return 1.0 if sat >= 30 else 0.4 if sat > 0 else 0.0


def pet_away(p, now=None):
    now = time.time() if now is None else now
    return p["trip_kind"] != 0 and p["trip_end"] > now


def pet_pct(p, now=None):
    """درصدِ توانایی فعلی همراه (با لول، تکامل و سیری)."""
    sp, lvl = SPECIES[p["species"]], pet_level(p["xp"])
    raw = (sp[4] + (lvl - 1) * sp[5]) * STAGE_MULT[pet_stage(lvl)] * mood_factor(satiety(p, now))
    return min(BONUS_CAP[sp[3]], raw)


def active_pet(uid):
    return db.execute("SELECT p.* FROM pets p JOIN users u ON u.active_pet=p.id WHERE u.id=? AND p.user_id=u.id",
                      (uid,)).fetchone()


def pet_bonus(uid, kind):
    p = active_pet(uid)
    if not p or p["species"] not in SPECIES or SPECIES[p["species"]][3] != kind or pet_away(p):
        return 0.0
    return pet_pct(p)


def add_pet_xp(p, amount):
    """XP همراه رو اضافه می‌کنه؛ اگه لول‌آپ یا تکامل شد، توی صندوق پیام صاحبش خبر می‌ذاره."""
    if amount <= 0:
        return
    cur = db.execute("SELECT xp FROM pets WHERE id=?", (p["id"],)).fetchone()
    if not cur:
        return
    new = min(pet_xp_for(PET_MAX_LEVEL), cur["xp"] + amount)
    if new == cur["xp"]:
        return
    db.execute("UPDATE pets SET xp=? WHERE id=?", (new, p["id"]))
    old_l, new_l = pet_level(cur["xp"]), pet_level(new)
    if new_l > old_l:
        extra = (f"\n✨ تکامل! حالا {STAGE_NAME[pet_stage(new_l)]} شد و توانایی‌ش قوی‌تر شد!"
                 if pet_stage(new_l) > pet_stage(old_l) else "")
        notify(p["user_id"], f"🐾 {p['name']} به لول {new_l} رسید!{extra}")


def pet_gain(uid, amount):
    p = active_pet(uid)
    if p:
        add_pet_xp(p, amount)


def feed_cost(p):
    return 150 + pet_level(p["xp"]) * 40


def pet_stat(uid):
    rows = db.execute("SELECT xp, species FROM pets WHERE user_id=?", (uid,)).fetchall()
    return (pet_level(max((r["xp"] for r in rows), default=0)) if rows else 0,
            1 if any(SPECIES.get(r["species"], (0, 0, 0))[2] == 4 for r in rows) else 0)


def pet_profile_line(uid):
    p = active_pet(uid)
    if not p or p["species"] not in SPECIES:
        return "🐾 همراه: —"
    return f"🐾 همراه: {SPECIES[p['species']][0]} {html.escape(p['name'])} • لول {pet_level(p['xp'])}"


@command("برترین همراه‌ها", "برترین همراه", "toppets")
async def cmd_top_pets(update, ctx, args):
    rows = db.execute("SELECT p.*, u.name AS owner FROM pets p JOIN users u ON u.id=p.user_id "
                      "ORDER BY p.xp DESC, p.id LIMIT 10").fetchall()
    if not rows:
        return await update.message.reply_text("🐾 هنوز همراهی ثبت نشده. اولین نفر باش و «تخم» رو بزن!")
    lines = ["🏆 برترین همراه‌های سرزمین", "━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows):
        sp, lvl = SPECIES[r["species"]], pet_level(r["xp"])
        lines.append(f"{'🥇🥈🥉'[i] if i < 3 else str(i + 1) + '.'} {sp[0]} {r['name']} {RARITY_TAG[sp[2]].split()[0]} "
                     f"• لول {lvl} • {STAGE_NAME[pet_stage(lvl)]}\n     👤 {r['owner']}")
    await update.message.reply_text("\n".join(lines))


def pet_view(u, note=""):
    uid, now = u["id"], time.time()
    p = active_pet(uid)
    lines = ([note, ""] if note else []) + ["🐾 همراه تو", "━━━━━━━━━━━━━━"]
    if not p:
        lines += ["هنوز همراهی نداری!", "🥚 توی «تخم» جوجه‌کشی کن یا از فروشگاه تخم بخر."]
        return "\n".join(lines), Markup([[Btn("🥚 تخم‌ها", f"pet_eggs:{uid}")]])
    sp, lvl = SPECIES[p["species"]], pet_level(p["xp"])
    sat, away = satiety(p, now), pet_away(p, now)
    lines.append(f"{sp[0]} {p['name']}   {RARITY_TAG[sp[2]]} • {STAGE_NAME[pet_stage(lvl)]}")
    if lvl >= PET_MAX_LEVEL:
        lines.append(f"⭐ لول {lvl} (حداکثر!)")
    else:
        base, nxt = pet_xp_for(lvl), pet_xp_for(lvl + 1)
        lines.append(f"⭐ لول {lvl}  [{bar(p['xp'] - base, nxt - base)}] {p['xp'] - base:,}/{nxt - base:,}")
    mood = ("😋 سیر" if sat >= 60 else "🙂 خوبه" if sat >= 30 else
            "😟 گرسنه‌ست! توانایی‌ش ضعیفه" if sat > 0 else "😵 بی‌حاله! توانایی‌ش خاموشه")
    lines.append(f"🍖 سیری: [{bar(sat, 100)}] {sat}٪ — {mood}")
    lines.append(f"✨ توانایی: +{pet_pct(p, now):.1f}٪ {BONUS_TEXT[sp[3]]}" + ("  (موقع ماموریت خاموشه)" if away else ""))
    if p["trip_kind"]:
        lines.append(f"🧭 توی ماموریته؛ برمی‌گرده: {fmt_time(p['trip_end'] - now)}" if away
                     else "🎁 از ماموریت برگشته! جایزه‌ش آماده‌ست.")
    kb = [[Btn(f"🍖 غذا ({feed_cost(p):,})", f"pet_feed:{uid}"), Btn("🎾 بازی", f"pet_play:{uid}")]]
    if p["trip_kind"] and not away:
        kb.append([Btn("🎁 دریافت جایزه‌ی ماموریت", f"pet_claim:{uid}:{p['id']}")])
    elif not p["trip_kind"]:
        kb.append([Btn(f"🧭 {h} ساعته", f"pet_go:{uid}:{h}") for h in TRIPS])
    kb.append([Btn("🐾 همراه‌ها", f"pet_list:{uid}"), Btn("🥚 تخم‌ها", f"pet_eggs:{uid}")])
    return "\n".join(lines), Markup(kb)


def pets_view(u, note=""):
    uid, now = u["id"], time.time()
    rows = db.execute("SELECT * FROM pets WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    lines = ([note, ""] if note else []) + [f"🐾 همراه‌های تو ({len(rows)}/{PET_MAX})", "━━━━━━━━━━━━━━"]
    kb = []
    if not rows:
        lines.append("هنوز همراهی نداری. «تخم» رو بزن!")
    for i, p in enumerate(rows, 1):
        sp, lvl = SPECIES[p["species"]], pet_level(p["xp"])
        mark = "✅ فعال" if u["active_pet"] == p["id"] else ""
        trip = (" • 🧭 ماموریت" if pet_away(p, now) else " • 🎁 جایزه آماده" if p["trip_kind"] else "")
        lines.append(f"{i}) {sp[0]} {p['name']} {RARITY_TAG[sp[2]].split()[0]} • لول {lvl} • +{pet_pct(p, now):.0f}٪ {BONUS_TEXT[sp[3]]}"
                     f" {mark}{trip}")
        row = []
        if u["active_pet"] != p["id"]:
            row += [Btn(f"🔄 {p['name']}", f"pet_set:{uid}:{p['id']}"), Btn("🕊 رها", f"pet_rel:{uid}:{p['id']}")]
        if p["trip_kind"] and not pet_away(p, now):
            row.append(Btn(f"🎁 {p['name']}", f"pet_claim:{uid}:{p['id']}"))
        if row:
            kb.append(row)
    kb.append([Btn("🐾 همراه", f"pet_menu:{uid}"), Btn("🥚 تخم‌ها", f"pet_eggs:{uid}")])
    return "\n".join(lines), Markup(kb)


def eggs_view(u, note=""):
    uid, now = u["id"], time.time()
    inc = db.execute("SELECT * FROM incubator WHERE user_id=? ORDER BY ready", (uid,)).fetchall()
    npets = db.execute("SELECT COUNT(*) FROM pets WHERE user_id=?", (uid,)).fetchone()[0]
    lines = ([note, ""] if note else []) + ["🥚 تخم‌ها و جوجه‌کشی", "━━━━━━━━━━━━━━",
                                            f"🐾 همراه‌ها: {npets}/{PET_MAX}   🔥 دستگاه: {len(inc)}/{INCUBATOR_SLOTS}", ""]
    kb = []
    have = {t: qty(uid, f"egg{t}") for t in HATCH_TIME}
    if any(have.values()):
        lines.append("🎒 تخم‌های تو:")
    for t, n in have.items():
        if n > 0:
            lines.append(f"{ITEMS[f'egg{t}'][0]} × {n} — {fmt_time(HATCH_TIME[t])} تا شکستن\n   {ITEMS[f'egg{t}'][5]}")
            kb.append([Btn(f"🔥 جوجه‌کشی {ITEMS[f'egg{t}'][0]}", f"egg_start:{uid}:{t}")])
    if not any(have.values()):
        lines.append("🎒 تخمی نداری. از «فروشگاه» (بخش متفرقه) بخر یا از ماموریت و رویدادها بگیر.")
    if inc:
        lines += ["", "🔥 توی دستگاه:"]
    for r in inc:
        ready = r["ready"] <= now
        lines.append(f"{ITEMS[f'egg{r['tier']}'][0]} — " + ("آماده‌ی شکستن! 🐣" if ready else f"{fmt_time(r['ready'] - now)} مونده"))
        if ready:
            kb.append([Btn("🐣 شکستن تخم", f"egg_hatch:{uid}:{r['id']}")])
    kb.append([Btn("🐾 همراه", f"pet_menu:{uid}")])
    return "\n".join(lines), Markup(kb)


def pick_species(tier):
    odds = EGG_ODDS[tier]
    rarity = random.choices([r for r, _ in odds], [w for _, w in odds])[0]
    return random.choice([k for k, v in SPECIES.items() if v[2] == rarity])


def start_incubation(uid, tier):
    with tx():
        key = f"egg{tier}"
        if tier not in HATCH_TIME or qty(uid, key) <= 0:
            return False, "این تخم رو نداری."
        slots = db.execute("SELECT COUNT(*) FROM incubator WHERE user_id=?", (uid,)).fetchone()[0]
        if slots >= INCUBATOR_SLOTS:
            return False, f"دستگاه پره! (حداکثر {INCUBATOR_SLOTS} تخم هم‌زمان)"
        npets = db.execute("SELECT COUNT(*) FROM pets WHERE user_id=?", (uid,)).fetchone()[0]
        if npets + slots >= PET_MAX:
            return False, f"جای همراه نداری (حداکثر {PET_MAX})؛ اول یکی رو رها کن."
        db.execute("UPDATE items SET qty=qty-1 WHERE user_id=? AND item=?", (uid, key))
        db.execute("INSERT INTO incubator(user_id, tier, ready) VALUES(?,?,?)", (uid, tier, time.time() + HATCH_TIME[tier]))
    return True, f"🔥 {ITEMS[key][0]} توی دستگاه گذاشته شد؛ {fmt_time(HATCH_TIME[tier])} دیگه می‌شکنه!"


def hatch_egg(uid, iid):
    with tx():
        row = db.execute("SELECT * FROM incubator WHERE id=? AND user_id=?", (iid, uid)).fetchone()
        if not row:
            return None, "این تخم دیگه نیست."
        if row["ready"] > time.time():
            return None, f"⏳ هنوز {fmt_time(row['ready'] - time.time())} مونده تا بشکنه."
        if db.execute("SELECT COUNT(*) FROM pets WHERE user_id=?", (uid,)).fetchone()[0] >= PET_MAX:
            return None, f"جای همراه نداری (حداکثر {PET_MAX})؛ اول یکی رو رها کن."
        key = pick_species(row["tier"])
        now = time.time()
        cur = db.execute("INSERT INTO pets(user_id, species, name, xp, fed_at, played_at, born) VALUES(?,?,?,?,?,?,?)",
                         (uid, key, SPECIES[key][1], 0, now - FEED_COOLDOWN, 0, now))
        db.execute("DELETE FROM incubator WHERE id=?", (iid,))
        db.execute("UPDATE users SET hatched=hatched+1 WHERE id=?", (uid,))
        if not active_pet(uid):
            db.execute("UPDATE users SET active_pet=? WHERE id=?", (cur.lastrowid, uid))
    return {"id": cur.lastrowid, "species": key}, ""


def do_feed(uid):
    with tx():
        p = active_pet(uid)
        if not p:
            return False, "همراهی نداری! اول «تخم» رو ببین 🥚"
        left = p["fed_at"] + FEED_COOLDOWN - time.time()
        if left > 0:
            return False, f"⏳ {fmt_time(left)} دیگه می‌تونی غذا بدی (الان سیره)."
        cost = feed_cost(p)
        if not spend(uid, cost):
            return False, f"سکه‌ی کافی نداری (هزینه‌ی غذا: {cost:,})"
        db.execute("UPDATE pets SET fed_at=? WHERE id=?", (time.time(), p["id"]))
        add_pet_xp(p, 50 + pet_level(p["xp"]) * 2)
    return True, f"🍖 {p['name']} غذا خورد و حسابی سیر شد! (-{cost:,} سکه)"


def do_play(uid):
    with tx():
        p = active_pet(uid)
        if not p:
            return False, "همراهی نداری! اول «تخم» رو ببین 🥚"
        left = p["played_at"] + PLAY_COOLDOWN - time.time()
        if left > 0:
            return False, f"⏳ {fmt_time(left)} دیگه می‌تونی بازی کنی (الان خسته‌ست)."
        db.execute("UPDATE pets SET played_at=? WHERE id=?", (time.time(), p["id"]))
        add_pet_xp(p, 20)
        found = ""
        if random.random() < 0.08:
            coins = random.randint(20, 100)
            add_coins(uid, coins)
            found = f"\n🎁 {p['name']} یه چیزی پیدا کرد: +{coins} سکه!"
    return True, f"🎾 با {p['name']} بازی کردی! ✨ +20 XP همراه{found}"


def do_trip(uid, hours):
    with tx():
        p = active_pet(uid)
        if not p:
            return False, "همراهی نداری!"
        if hours not in TRIPS:
            return False, "ماموریت نامعتبره."
        if p["trip_kind"]:
            return False, "همراهت الان ماموریت داره؛ اول جایزه‌ش رو بگیر."
        db.execute("UPDATE pets SET trip_kind=?, trip_end=? WHERE id=?", (hours, time.time() + TRIPS[hours][0], p["id"]))
    return True, f"🧭 {p['name']} راهی ماموریت {hours} ساعته شد! (تا برگرده توانایی‌ش خاموشه)"


def claim_trip(uid, pid):
    with tx():
        p = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (pid, uid)).fetchone()
        if not p or not p["trip_kind"]:
            return False, "ماموریتی برای دریافت نیست."
        if p["trip_end"] > time.time():
            return False, f"⏳ هنوز {fmt_time(p['trip_end'] - time.time())} مونده."
        hours, sp, lvl = p["trip_kind"], SPECIES[p["species"]], pet_level(p["xp"])
        coins = int((50 + 10 * lvl) * hours * (1 + 0.1 * sp[2]) * random.uniform(0.8, 1.2))
        add_coins(uid, coins)
        db.execute("UPDATE pets SET trip_kind=0, trip_end=0 WHERE id=?", (pid,))
        add_pet_xp(p, 15 * hours)
        db.execute("UPDATE users SET trips=trips+1 WHERE id=?", (uid,))
        egg = ""
        if random.random() < TRIPS[hours][1]:
            egg = "\n" + give_item(uid, "egg2" if random.random() < 0.15 else "egg1")
    return True, f"🧭 {p['name']} از ماموریت {hours} ساعته برگشت!\n💰 +{coins:,} سکه  ✨ +{15 * hours} XP همراه{egg}"


def clean_pet_name(text):
    name = " ".join("".join(ch for ch in text if ch.isprintable() and ch not in "<>&").split())
    return name[:16].strip()


@command("همراه", "pet", level=3)
async def cmd_pet(update, ctx, args):
    u = get_user(update.effective_user)
    note = ""
    if not u["pet_gift"]:   # هدیه‌ی خوش‌آمد: یه تخم رایگان، فقط یک بار
        with tx():
            db.execute("UPDATE users SET pet_gift=1 WHERE id=?", (u["id"],))
            give_item(u["id"], "egg1")
        note = "🎁 هدیه‌ی خوش‌آمد: یه 🥚 تخم معمولی گرفتی! از «تخم» جوجه‌کشیش کن."
        u = user_by_id(u["id"])
    text, kb = pet_view(u, note)
    await update.message.reply_text(text, reply_markup=kb)


@command("همراه‌ها", "pets", level=3)
async def cmd_pets(update, ctx, args):
    text, kb = pets_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


@command("تخم", "تخم‌ها", "eggs", level=3)
async def cmd_eggs(update, ctx, args):
    text, kb = eggs_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


@command("نام همراه", "namepet", args=True, level=3)
async def cmd_name_pet(update, ctx, args):
    u = get_user(update.effective_user)
    p = active_pet(u["id"])
    if not p:
        return await update.message.reply_text("همراهی نداری! اول «تخم» رو ببین 🥚")
    name = clean_pet_name(" ".join(args))
    if not name:
        return await update.message.reply_text("اسم رو بنویس. مثال: نام همراه فندق  (حداکثر ۱۶ حرف)")
    db.execute("UPDATE pets SET name=? WHERE id=?", (name, p["id"]))
    await update.message.reply_text(f"✏️ اسم همراهت شد: {SPECIES[p['species']][0]} {name}")


async def cb_pet(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        return await q.answer()
    act, uid = parts[0], int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    u = user_by_id(uid)
    if level_of(u["xp"]) < 3 and not is_admin(uid):
        return await q.answer("همراه از لول ۳ باز می‌شه.", show_alert=True)
    chat_id = q.message.chat_id
    arg = parts[2] if len(parts) > 2 else ""
    note = ""
    view = "pet"
    if act == "pet_menu":
        pass
    elif act == "pet_feed":
        ok_, note = do_feed(uid)
        if not ok_:
            return await q.answer(note, show_alert=True)
        await send_event_sticker(ctx, chat_id, "pet")
    elif act == "pet_play":
        ok_, note = do_play(uid)
        if not ok_:
            return await q.answer(note, show_alert=True)
        await send_event_sticker(ctx, chat_id, "pet")
    elif act == "pet_go" and arg.isdigit():
        ok_, note = do_trip(uid, int(arg))
        if not ok_:
            return await q.answer(note, show_alert=True)
    elif act == "pet_claim" and arg.isdigit():
        ok_, note = claim_trip(uid, int(arg))
        if not ok_:
            return await q.answer(note, show_alert=True)
        await send_event_sticker(ctx, chat_id, "daily")
    elif act == "pet_list":
        view = "list"
    elif act == "pet_set" and arg.isdigit():
        p = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (int(arg), uid)).fetchone()
        if not p:
            return await q.answer("این همراه دیگه نیست.", show_alert=True)
        db.execute("UPDATE users SET active_pet=? WHERE id=?", (p["id"], uid))
        note = f"✅ {SPECIES[p['species']][0]} {p['name']} همراه فعالت شد!"
        view = "list"
    elif act == "pet_rel" and arg.isdigit():
        p = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (int(arg), uid)).fetchone()
        if not p or u["active_pet"] == p["id"] or p["trip_kind"]:
            return await q.answer("این همراه رو نمی‌شه رها کرد (فعاله یا ماموریته).", show_alert=True)
        sp = SPECIES[p["species"]]
        kb = Markup([[Btn("🕊 آره، رها کن", f"pet_relyes:{uid}:{p['id']}"), Btn("↩️ نه", f"pet_list:{uid}")]])
        await q.answer()
        return await safe_edit(q, f"🕊 مطمئنی می‌خوای {sp[0]} {p['name']} ({RARITY_TAG[sp[2]]}، لول {pet_level(p['xp'])}) رو رها کنی؟\n"
                                  "این کار برگشت نداره!", kb)
    elif act == "pet_relyes" and arg.isdigit():
        with tx():
            p = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (int(arg), uid)).fetchone()
            if not p or user_by_id(uid)["active_pet"] == p["id"] or p["trip_kind"]:
                return await q.answer("این همراه رو نمی‌شه رها کرد.", show_alert=True)
            db.execute("DELETE FROM pets WHERE id=?", (p["id"],))
        note = f"🕊 {p['name']} رها شد و آزاد رفت..."
        view = "list"
    elif act == "pet_eggs":
        view = "eggs"
    elif act == "egg_start" and arg.isdigit():
        ok_, note = start_incubation(uid, int(arg))
        if not ok_:
            return await q.answer(note, show_alert=True)
        view = "eggs"
    elif act == "egg_hatch" and arg.isdigit():
        res, err = hatch_egg(uid, int(arg))
        if not res:
            return await q.answer(err, show_alert=True)
        sp = SPECIES[res["species"]]
        note = (f"🐣🎉 تخم شکست! {sp[0]} {sp[1]} به دنیا اومد!\n{RARITY_TAG[sp[2]]} • توانایی: {BONUS_TEXT[sp[3]]}")
        await send_event_sticker(ctx, chat_id, "hatch", 1.0)
        view = "eggs"
    else:
        return await q.answer()
    await q.answer()
    u = user_by_id(uid)
    fn = {"pet": pet_view, "list": pets_view, "eggs": eggs_view}[view]
    text, kb = fn(u, note)
    await safe_edit(q, text, kb)


# ============================== غول جهانی 🌍 ==============================
WORLD_BOSSES = [("تایتان آتشین", "🌋", 1.0), ("اژدهای کهکشان", "🐲", 1.2), ("دیو سیاره‌خوار", "☄️", 1.3),
                ("چشم ابدی", "🧿", 1.1), ("ملکه‌ی عنکبوت‌ها", "🕷", 0.9)]
_world_tick, _world_global = {}, [None]


def world_active():
    return db.execute("SELECT * FROM world_boss WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()


def chat_label(cid, here=None):
    c = db.execute("SELECT title, username FROM chats WHERE chat_id=?", (cid,)).fetchone()
    if c and c["username"]:
        return f"{c['title']} (@{c['username']})"
    if c and cid == here:
        return f"{c['title']} (گروه شما)"
    return "🔒 یه گروه خصوصی"


def spawn_world(force=False):
    if world_active():
        return None
    rows = db.execute("SELECT xp FROM users WHERE gender<>'' AND cls<>'' AND id IN "
                      "(SELECT DISTINCT user_id FROM chat_players WHERE ts>=?)", (time.time() - 72 * 3600,)).fetchall()
    if len(rows) < WORLD_MIN_PLAYERS and not force:
        meta_set("world_next", time.time() + 6 * 3600)
        return None
    name, emoji, mult = random.choice(WORLD_BOSSES)
    hp = int(max(1, sum(2500 + 100 * level_of(r["xp"]) for r in rows) or 3 * 3700) * mult)
    now = time.time()
    db.execute("INSERT INTO world_boss(name, emoji, max_hp, hp, t_start, t_end, status) VALUES(?,?,?,?,?,?,'active')",
               (name, emoji, hp, hp, now, now + WORLD_TTL))
    return world_active()


def world_card(b, here=None, uid=None):
    now = time.time()
    pl = db.execute("SELECT d.dmg, u.name FROM world_damage d JOIN users u ON u.id=d.user_id WHERE d.boss_id=? AND d.dmg>0 "
                    "ORDER BY d.dmg DESC LIMIT 5", (b["id"],)).fetchall()
    ch = db.execute("SELECT chat_id, dmg FROM world_chat_damage WHERE boss_id=? AND dmg>0 ORDER BY dmg DESC LIMIT 5",
                    (b["id"],)).fetchall()
    lines = [f"🌍 {b['emoji']} {b['name']} — غول جهانی!", "━━━━━━━━━━━━━━",
             f"❤️ [{bar(b['hp'], b['max_hp'], 12)}]", f"   {b['hp']:,} / {b['max_hp']:,}",
             f"⏳ مونده: {fmt_days(b['t_end'] - now)}"]
    if pl:
        lines += ["", "🏆 برترین مبارزها:"] + [f"{'🥇🥈🥉🏅🏅'[i]} {r['name']} — {r['dmg']:,}" for i, r in enumerate(pl)]
    if ch:
        lines += ["", "🏘 برترین گروه‌ها:"] + [f"{'🥇🥈🥉🏅🏅'[i]} {chat_label(r['chat_id'], here)} — {r['dmg']:,}" for i, r in enumerate(ch)]
    if uid:
        me = db.execute("SELECT dmg, hits FROM world_damage WHERE boss_id=? AND user_id=?", (b["id"], uid)).fetchone()
        if me:
            lines += ["", f"👤 سهم تو: {me['dmg']:,} آسیب ({me['hits']} ضربه)"]
    if here:
        mine = db.execute("SELECT dmg FROM world_chat_damage WHERE boss_id=? AND chat_id=?", (b["id"], here)).fetchone()
        if mine:
            rank = db.execute("SELECT COUNT(*)+1 FROM world_chat_damage WHERE boss_id=? AND dmg>?", (b["id"], mine["dmg"])).fetchone()[0]
            lines.append(f"📍 گروه شما: رتبه‌ی {rank} با {mine['dmg']:,} آسیب")
    lines += ["", f"💡 هر ضربه هر {WORLD_HIT_COOLDOWN // 60} دقیقه. جایزه‌ی پایان نبرد به سهم آسیب تو بستگی داره و "
                  "۵ نفر اول 🐲 تخم افسانه‌ای می‌گیرن!"]
    return "\n".join(lines), Markup([[Btn("⚔️ حمله جهانی!", "world_hit")]])


def world_result_text(b, here=None):
    won = b["status"] == "won"
    pl = db.execute("SELECT d.dmg, u.name FROM world_damage d JOIN users u ON u.id=d.user_id WHERE d.boss_id=? AND d.dmg>0 "
                    "ORDER BY d.dmg DESC LIMIT 5", (b["id"],)).fetchall()
    ch = db.execute("SELECT chat_id, dmg FROM world_chat_damage WHERE boss_id=? AND dmg>0 ORDER BY dmg DESC LIMIT 5",
                    (b["id"],)).fetchall()
    n = db.execute("SELECT COUNT(*) FROM world_damage WHERE boss_id=? AND dmg>0", (b["id"],)).fetchone()[0]
    head = (f"🏆🌍 {b['emoji']} {b['name']} نابود شد!\nهمه‌ی بازیکن‌ها با هم پیروز شدیم! 🎉" if won
            else f"💨🌍 {b['emoji']} {b['name']} فرار کرد!\nدفعه‌ی بعد باید محکم‌تر بزنیم!")
    lines = [head, "━━━━━━━━━━━━━━", f"👥 {n} نفر توی نبرد شرکت کردن"]
    if pl:
        lines += ["", "🏆 برترین مبارزها:"] + [f"{'🥇🥈🥉🏅🏅'[i]} {r['name']} — {r['dmg']:,}" for i, r in enumerate(pl)]
    if ch:
        lines += ["", "🏘 برترین گروه‌ها:"] + [f"{'🥇🥈🥉🏅🏅'[i]} {chat_label(r['chat_id'], here)} — {r['dmg']:,}" for i, r in enumerate(ch)]
    return "\n".join(lines) + "\n\n🎁 جایزه‌ها به صندوق پیام شرکت‌کننده‌ها رفت."


def settle_world(bid, killed):
    """نبرد رو می‌بنده و جایزه‌ها رو بر اساس سهم آسیب تقسیم می‌کنه."""
    with tx():
        b = db.execute("SELECT * FROM world_boss WHERE id=? AND status='active'", (bid,)).fetchone()
        if not b:
            return False
        rows = db.execute("SELECT d.user_id, d.dmg, d.hits, u.xp FROM world_damage d JOIN users u ON u.id=d.user_id "
                          "WHERE d.boss_id=? AND d.dmg>0 ORDER BY d.dmg DESC", (bid,)).fetchall()
        total = sum(r["dmg"] for r in rows)
        pool = int(b["max_hp"] * (0.6 if killed else 0.12))
        place_bonus = {0: 0.10, 1: 0.06, 2: 0.04}
        for i, r in enumerate(rows):
            uid = r["user_id"]
            coins = int(pool * r["dmg"] / total) + (int(pool * place_bonus[i]) if killed and i in place_bonus else 0)
            parts = [f"💰 +{coins:,} سکه"]
            if coins:
                add_coins(uid, coins)
            grant_xp(uid, 40 if killed else 8)
            if killed:
                if i < 5:
                    parts.append(give_item(uid, "egg3"))
                elif r["hits"] >= 5 and level_of(r["xp"]) >= 5:
                    parts.append(give_item(uid, "egg1"))
                if r["dmg"] >= b["max_hp"] * 0.005:
                    parts.append(give_item(uid, "world1"))
                if r["hits"] >= 3:
                    db.execute("UPDATE users SET world_wins=world_wins+1 WHERE id=?", (uid,))
            notify(uid, f"🌍 نبرد با {b['emoji']} {b['name']} تموم شد! " + ("پیروز شدیم 🏆" if killed else "غول فرار کرد 💨") +
                        f"\n🏅 رتبه‌ی تو: {i + 1} با {r['dmg']:,} آسیب\n" + "\n".join(parts))
        db.execute("UPDATE world_boss SET status=?, t_end=? WHERE id=?", ("won" if killed else "lost", time.time(), bid))
        meta_set("world_next", time.time() + random.randint(*WORLD_GAP))
    return True


def do_world_hit(u, chat_id):
    uid = u["id"]
    with tx():
        b = world_active()
        if not b or b["t_end"] <= time.time():
            return {"kind": "alert", "text": "الان غول جهانی‌ای نیست 😴"}
        u = user_by_id(uid)
        left = cd_left(u, "last_world", WORLD_HIT_COOLDOWN)
        if left > 0:
            return {"kind": "alert", "text": f"⏳ {fmt_time(left)} دیگه می‌تونی به غول جهانی حمله کنی."}
        set_time(uid, "last_world")
        dmg, note = boss_damage_roll(u)
        dmg = min(dmg, b["hp"])
        if dmg > 0:
            db.execute("INSERT INTO world_damage(boss_id, user_id, dmg, hits) VALUES(?,?,?,1) "
                       "ON CONFLICT(boss_id, user_id) DO UPDATE SET dmg=world_damage.dmg+excluded.dmg, hits=world_damage.hits+1",
                       (b["id"], uid, dmg))
            db.execute("INSERT INTO world_chat_damage(boss_id, chat_id, dmg) VALUES(?,?,?) "
                       "ON CONFLICT(boss_id, chat_id) DO UPDATE SET dmg=world_chat_damage.dmg+excluded.dmg",
                       (b["id"], chat_id, dmg))
            db.execute("UPDATE world_boss SET hp=hp-? WHERE id=?", (dmg, b["id"]))
            chat_score(chat_id, 1 + dmg // 40)
        xp, lvl_note = grant_xp(uid, 3)
        hp = b["hp"] - dmg
        mine = db.execute("SELECT dmg FROM world_damage WHERE boss_id=? AND user_id=?", (b["id"], uid)).fetchone()
        res = {"kind": "hit", "dmg": dmg, "note": note, "hp": hp, "max": b["max_hp"], "name": b["name"], "emoji": b["emoji"],
               "xp": xp, "lvl": lvl_note, "mine": mine["dmg"] if mine else 0}
        if hp <= 0:
            settle_world(b["id"], True)
            res["kind"] = "kill"
        return res


def world_hit_text(u, res, here=None):
    hp = max(0, res["hp"])
    lines = [f"⚔️ {u['name']} به {res['emoji']} {res['name']} (غول جهانی) حمله کرد!",
             f"💥 {res['dmg']:,} آسیب" if res["dmg"] else "💨 ضربه‌ت خطا رفت!"]
    if res["note"] and res["dmg"]:
        lines.append(res["note"])
    lines += [f"❤️ [{bar(hp, res['max'], 12)}] {hp:,}/{res['max']:,}", f"👤 مجموع آسیب تو: {res['mine']:,}",
              f"✨ +{res['xp']} XP" + res["lvl"]]
    text = "\n".join(lines)
    if res["kind"] == "kill":
        b = db.execute("SELECT * FROM world_boss WHERE name=? AND status='won' ORDER BY id DESC LIMIT 1", (res["name"],)).fetchone()
        text += "\n\n" + (world_result_text(b, here) if b else "")
    return text


async def world_tick(ctx, chat_id):
    """ظهور و فرار غول جهانی و اعلام‌ها توی هر گروه (فقط یک بار)؛ خطاها بی‌صدا."""
    try:
        mono, now = time.monotonic(), time.time()
        if _world_global[0] is None or mono - _world_global[0] > 20:
            _world_global[0] = mono
            b = world_active()
            if b and b["t_end"] <= now:
                settle_world(b["id"], False)
            elif not b:
                nxt = float(meta_get("world_next", 0) or 0)
                if nxt == 0:
                    meta_set("world_next", now + 6 * 3600)   # اولین غول، شش ساعت بعد از شروع فعالیت
                elif now >= nxt:
                    spawn_world()
        last = _world_tick.get(chat_id)
        if last is not None and mono - last < 60:
            return
        if len(_world_tick) > 20000:
            _world_tick.clear()
        _world_tick[chat_id] = mono
        c = db.execute("SELECT world_spawn_seen, world_end_seen FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        if not c:
            return
        b = world_active()
        if b and c["world_spawn_seen"] < b["id"]:
            db.execute("UPDATE chats SET world_spawn_seen=? WHERE chat_id=?", (b["id"], chat_id))
            text, kb = world_card(b, chat_id)
            await send_event_sticker(ctx, chat_id, "world", 1.0)
            await ctx.bot.send_message(chat_id, "🚨🌍 رویداد جهانی! یه غول عظیم‌الجثه به همه‌ی گروه‌ها حمله کرده!\n\n" + text,
                                       reply_markup=kb)
        done = db.execute("SELECT * FROM world_boss WHERE status!='active' ORDER BY id DESC LIMIT 1").fetchone()
        if done and c["world_end_seen"] < done["id"]:
            db.execute("UPDATE chats SET world_end_seen=? WHERE chat_id=?", (done["id"], chat_id))
            if now - done["t_end"] < 86400:
                await send_event_sticker(ctx, chat_id, "worldwin" if done["status"] == "won" else "lose", 1.0)
                await ctx.bot.send_message(chat_id, world_result_text(done, chat_id))
    except Exception as e:
        logging.warning("world_tick: %s", e)


@command("غول جهانی", "worldboss")
async def cmd_world(update, ctx, args):
    u = get_user(update.effective_user)
    here = update.effective_chat.id
    b = world_active()
    if b:
        text, kb = world_card(b, here, u["id"])
        return await update.message.reply_text(text, reply_markup=kb)
    done = db.execute("SELECT * FROM world_boss WHERE status!='active' ORDER BY id DESC LIMIT 1").fetchone()
    if done and time.time() - done["t_end"] < 3 * 86400:
        return await update.message.reply_text(world_result_text(done, here))
    nxt = float(meta_get("world_next", 0) or 0)
    wait = f"\n⏳ حداقل {fmt_days(nxt - time.time())} دیگه" if nxt > time.time() else ""
    await update.message.reply_text("😴 الان غول جهانی‌ای نیست.\n🌍 هر چند روز یه بار یه غول عظیم ظاهر می‌شه و "
                                    "همه‌ی گروه‌ها ۴۸ ساعت با هم می‌جنگن!" + wait)


@command("حمله جهانی", "worldhit", level=5)
async def cmd_world_hit(update, ctx, args):
    u = get_user(update.effective_user)
    here = update.effective_chat.id
    res = do_world_hit(u, here)
    if res["kind"] == "alert":
        return await update.message.reply_text(res["text"])
    await update.message.reply_text(world_hit_text(u, res, here))
    if res["kind"] == "kill":
        await send_event_sticker(ctx, here, "worldwin", 1.0)
    elif "🎊🎉" in res["lvl"]:
        await send_event_sticker(ctx, here, "levelup", 1.0)


async def cb_world(update, ctx):
    q = update.callback_query
    u = get_user(q.from_user)
    here = q.message.chat_id
    if level_of(u["xp"]) < 5 and not is_admin(u["id"]):
        return await q.answer("حمله‌ی جهانی از لول ۵ باز می‌شه.", show_alert=True)
    res = do_world_hit(u, here)
    if res["kind"] == "alert":
        return await q.answer(res["text"], show_alert=True)
    await q.answer(f"💥 {res['dmg']:,} آسیب زدی!" if res["dmg"] else "💨 ضربه‌ت خطا رفت!")
    if res["kind"] == "kill":
        await safe_edit(q, world_hit_text(u, res, here))
        return await send_event_sticker(ctx, here, "worldwin", 1.0)
    last = _boss_edit.get(("w", here))
    if last is None or time.monotonic() - last >= 4:
        _boss_edit[("w", here)] = time.monotonic()
        b = world_active()
        if b:
            text, kb = world_card(b, here, u["id"])
            await safe_edit(q, text, kb)


@command("احضار غول جهانی", "spawnworld", admin=True)
async def cmd_spawn_world(update, ctx, args):
    if world_active():
        return await update.message.reply_text("یه غول جهانی همین الان فعاله.")
    spawn_world(force=True)
    _world_tick.pop(update.effective_chat.id, None)
    await world_tick(ctx, update.effective_chat.id)


@command("پایان غول جهانی", "endworld", admin=True)
async def cmd_end_world(update, ctx, args):
    b = world_active()
    if not b:
        return await update.message.reply_text("غول جهانی فعالی نیست.")
    settle_world(b["id"], False)
    _world_tick.pop(update.effective_chat.id, None)
    await update.message.reply_text("🔚 غول جهانی به‌صورت دستی بسته شد.")
    await world_tick(ctx, update.effective_chat.id)


# ============================== زمان ایران و تقویم شمسی ==============================
JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = {0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه"}
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(x):
    return str(x).translate(_FA)


def tehran_now(now=None):
    return (time.time() if now is None else now) + 3.5 * 3600


def tehran_day(now=None):
    return int(tehran_now(now) // 86400)


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def date_line(now=None):
    t = time.gmtime(tehran_now(now))
    y, m, d = gregorian_to_jalali(t.tm_year, t.tm_mon, t.tm_mday)
    return f"{WEEKDAYS[t.tm_wday]} {fa(d)} {JALALI_MONTHS[m - 1]} {fa(y)}"


# ============================== فال روزانه 🔮 ==============================
FALS = {  # نوع بونوس: متن‌های فال
    "coins": ["امروز سکه‌ها تو رو پیدا می‌کنن، نه تو اون‌ها رو! هر کاری سکه‌ی بیشتری داره 💰",
              "ستاره‌ی تاجرها بالای سرته؛ هر ضربه‌ی چکش طلا می‌شه ✨",
              "کیسه‌ی پولت امروز سنگین‌تر از همیشه برمی‌گرده 🤑",
              "بخت با زحمت‌کش‌هاست؛ امروز کار کن و پر برگرد 🔨"],
    "xp": ["امروز ذهنت تیزتر از شمشیره؛ هر تجربه بهتر می‌چسبه 📚",
           "راز قدیمی‌ها بهت پچ‌پچ می‌کنه و یادگیریت سریع‌تر می‌شه 🌠",
           "امروز روز رشد کردنه؛ هر قدمت یه پله بالاتره 🪜",
           "جغد دانا از دور بهت چشمک زد؛ XP امروز با توئه 🦉"],
    "luck": ["شانس امروز لبخند می‌زنه؛ بزن به دل ماجراجویی 🍀",
             "یونجه‌ی چهاربرگ زیر پاته؛ ریسک‌های امروز جواب می‌دن 🌈",
             "امروز تاس‌ها به نفع توئن 🎲",
             "ستاره‌ی بخت از شرق بالا اومده؛ پیروزی نزدیکه ⭐"],
    "loot": ["غنیمت‌ها امروز بزرگ‌ترن؛ کوله‌ات رو خالی بیار 🎒",
             "گنج‌ها از خواب بیدار شدن و دنبال تو می‌گردن 💎",
             "هر غار امروز یه صندوق اضافه‌تر داره 🗝",
             "دست‌های خالی امروز پر برمی‌گردن 🏴‍☠️"],
    "dmg": ["شمشیرت امروز تیزتره؛ غول‌ها بترسن 🗡",
            "رعد و برق توی مشته؛ ضربه‌هات سنگین‌تر می‌خورن ⚡",
            "امروز روز غول‌کشیه! آسیب‌هات بیشتره 🐉",
            "خشم قهرمان‌ها توی رگ‌هاته 🔥"],
}
FAL_PCT = {"coins": 10, "xp": 10, "loot": 10, "dmg": 10, "luck": 5}


def fal_bonus(uid, kind):
    r = db.execute("SELECT fal_day, fal_kind FROM users WHERE id=?", (uid,)).fetchone()
    if not r or r["fal_day"] != tehran_day() or not r["fal_kind"]:
        return 0.0
    return float(FAL_PCT[r["fal_kind"].split(":")[0]]) if r["fal_kind"].split(":")[0] == kind else 0.0


@command("فال", "fal")
async def cmd_fal(update, ctx, args):
    u = get_user(update.effective_user)
    today, again = tehran_day(), False
    if u["fal_day"] == today and u["fal_kind"]:
        kind, idx = u["fal_kind"].split(":")[0], int(u["fal_kind"].split(":")[1])
        again = True
    else:
        kind = random.choice(list(FALS))
        idx = random.randrange(len(FALS[kind]))
        db.execute("UPDATE users SET fal_day=?, fal_kind=?, fal_n=fal_n+1 WHERE id=?", (today, f"{kind}:{idx}", u["id"]))
    pct = FAL_PCT[kind]
    text = (f"🔮 فال امروزِ {u['name']}\n📅 {date_line()}\n━━━━━━━━━━━━━━\n{FALS[kind][idx]}\n\n"
            f"✨ طالع امروز: +{pct}{'٪' if kind != 'luck' else ' امتیاز'} {BONUS_TEXT[kind]} (تا نیمه‌شب)")
    if again:
        text += "\n\n🌙 فال امروزت رو قبلاً گرفتی؛ فردا فال تازه می‌گیری."
    await update.message.reply_text(text)
    if not again:
        await send_event_sticker(ctx, update.effective_chat.id, "fal", 1.0)


# ============================== ماموریت‌های شروع (آموزش) 🧭 ==============================
TUTORIAL = [  # (کلید، ایموجی، عنوان، راهنما، آمار، هدف، جایزه)
    ("t_work", "🔨", "اولین کار", "بنویس «کار»", "work", 1, ("coins", 300)),
    ("t_adv", "🧭", "اولین ماجراجویی", "بنویس «ماجراجویی»", "adv", 1, ("coins", 400)),
    ("t_daily", "🎁", "جایزه‌ی روزانه", "بنویس «جایزه»", "streak", 1, ("coins", 500)),
    ("t_gear", "🛒", "اولین تجهیزات", "از «فروشگاه» یه وسیله بخر", "gear", 1, ("coins", 600)),
    ("t_lvl3", "⭐", "لول ۳", "XP جمع کن تا به لول ۳ برسی", "level", 3, ("item", "egg1")),
    ("t_pet", "🐣", "اولین همراه", "«همراه» رو بزن؛ تخم رو جوجه‌کشی کن و بشکن", "hatched", 1, ("coins", 800)),
    ("t_wheel", "🎰", "چرخ شانس", "بنویس «چرخ»", "spins", 1, ("coins", 600)),
    ("t_medal", "🏅", "اولین مدال", "کار کن تا مدال بگیری؛ «مدال‌ها» رو ببین", "medals", 1, ("coins", 500)),
    ("t_lvl5", "🌟", "لول ۵", "به لول ۵ برس؛ بازار و آهنگری باز می‌شن!", "level", 5, ("both", (3000, "potion2"))),
]
TUT_FINAL = (2000, "egg2")


def tut_stats(u):
    st = ach_stats(u)
    uid = u["id"]
    st["gear"] = sum(1 for k in owned(uid) if k in ITEMS and ITEMS[k][1] in SLOTS)
    st["medals"] = len(ach_done(uid))
    return st


def tut_rows(uid):
    return {r["step"]: r["state"] for r in db.execute("SELECT step, state FROM tutorial WHERE user_id=?", (uid,))}


def tut_prepare(u):
    """بار اول: بازیکن‌های قدیمی (لول ≥ ۸) آموزش رو رد‌شده حساب می‌شن (بدون جایزه‌ی عقب‌افتاده)."""
    rows = tut_rows(u["id"])
    if "_init" not in rows:
        with tx():
            db.execute("INSERT OR IGNORE INTO tutorial(user_id, step, state) VALUES(?, '_init', 2)", (u["id"],))
            if level_of(u["xp"]) >= 8:
                for t in TUTORIAL:
                    db.execute("INSERT OR IGNORE INTO tutorial(user_id, step, state) VALUES(?,?,2)", (u["id"], t[0]))
        rows = tut_rows(u["id"])
    return rows


def tut_label(reward):
    kind, val = reward
    if kind == "coins":
        return f"💰 {val:,}"
    if kind == "item":
        return ITEMS[val][0]
    return f"💰 {val[0]:,} + {ITEMS[val[1]][0]}"


def tut_give(uid, reward):
    kind, val = reward
    if kind == "coins":
        add_coins(uid, val)
        return f"💰 +{val:,}"
    if kind == "item":
        return give_item(uid, val)
    add_coins(uid, val[0])
    return f"💰 +{val[0]:,} " + give_item(uid, val[1])


def tut_view(u, note=""):
    uid = u["id"]
    rows, st = tut_prepare(u), tut_stats(u)
    claimed = sum(1 for t in TUTORIAL if rows.get(t[0]) == 2)
    lines = ([note, ""] if note else []) + [f"🧭 ماموریت‌های شروع ({claimed}/{len(TUTORIAL)})", "━━━━━━━━━━━━━━"]
    claimable = []
    for key, emoji, title, hint, stat, goal, reward in TUTORIAL:
        if rows.get(key) == 2:
            lines.append(f"✅ {emoji} {title}")
        elif st[stat] >= goal:
            lines.append(f"🎁 {emoji} {title} — آماده‌ی دریافت! ({tut_label(reward)})")
            claimable.append(key)
        else:
            lines.append(f"🔒 {emoji} {title} — {hint}\n     جایزه: {tut_label(reward)}")
    if claimed == len(TUTORIAL):
        lines += ["", "🎓 آفرین! همه‌ی ماموریت‌های شروع رو تموم کردی."]
    else:
        lines += ["", f"🏆 با تموم کردن همه: 💰 {TUT_FINAL[0]:,} + {ITEMS[TUT_FINAL[1]][0]} + مدال 🎓"]
    kb = [[Btn(f"🎁 {next(t[2] for t in TUTORIAL if t[0] == k)}", f"tut_claim:{uid}:{k}")] for k in claimable]
    if len(claimable) > 1:
        kb.append([Btn("🎁 دریافت همه", f"tut_claim:{uid}:all")])
    return "\n".join(lines), Markup(kb) if kb else None


def tut_claim(uid, only=None):
    got, bonus = [], ""
    with tx():
        u = user_by_id(uid)
        rows, st = tut_prepare(u), tut_stats(u)
        for key, emoji, title, hint, stat, goal, reward in TUTORIAL:
            if (only and key != only) or rows.get(key) == 2 or st[stat] < goal:
                continue
            db.execute("INSERT OR REPLACE INTO tutorial(user_id, step, state) VALUES(?,?,2)", (uid, key))
            got.append(f"{emoji} {title}: {tut_give(uid, reward)}")
        rows = tut_rows(uid)
        if got and all(rows.get(t[0]) == 2 for t in TUTORIAL) and "_final" not in rows:
            db.execute("INSERT INTO tutorial(user_id, step, state) VALUES(?, '_final', 2)", (uid,))
            add_coins(uid, TUT_FINAL[0])
            bonus = f"\n🎓 جایزه‌ی پایان آموزش: 💰 +{TUT_FINAL[0]:,} " + give_item(uid, TUT_FINAL[1])
    return got, bonus


async def tut_announce(ctx, chat_id, uid):
    """وقتی یه ماموریت آموزش تموم می‌شه، یک بار خبر می‌ده (برای بازیکن‌های قدیمی هیچ‌وقت)."""
    u = user_by_id(uid)
    if not has_char(u):
        return
    rows = tut_prepare(u)
    if all(rows.get(t[0]) == 2 for t in TUTORIAL):
        return
    st = tut_stats(u)
    fresh = [t for t in TUTORIAL if rows.get(t[0], 0) == 0 and st[t[4]] >= t[5]]
    if not fresh:
        return
    with tx():
        for t in fresh:
            db.execute("INSERT OR REPLACE INTO tutorial(user_id, step, state) VALUES(?,?,1)", (uid, t[0]))
    await ctx.bot.send_message(chat_id, "🎁 ماموریت آموزش انجام شد!\n" + "\n".join(f"{t[1]} {t[2]}" for t in fresh) +
                               "\n👉 «آموزش» رو بزن و جایزه‌ت رو بگیر!")
    await send_event_sticker(ctx, chat_id, "tutorial", 1.0)


@command("آموزش", "tutorial", "شروع سریع", "quickstart")
async def cmd_tutorial(update, ctx, args):
    text, kb = tut_view(get_user(update.effective_user))
    await update.message.reply_text(text, reply_markup=kb)


async def cb_tut(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    got, bonus = tut_claim(uid, None if parts[2] == "all" else parts[2])
    if not got:
        return await q.answer("هنوز این ماموریت تموم نشده یا قبلاً گرفتیش.", show_alert=True)
    await q.answer("🎁 دریافت شد!")
    text, kb = tut_view(user_by_id(uid), "🎉 دریافت شد:\n" + "\n".join(got) + bonus)
    await safe_edit(q, text, kb)
    await send_event_sticker(ctx, q.message.chat_id, "tutorial", 1.0)


# ============================== دعوت دوست + کارت اشتراک‌گذاری 🤝 ==============================
def ref_link(username, uid):
    return f"https://t.me/{username}?start=ref_{uid}"


def share_url(link, text):
    from urllib.parse import quote
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"


def register_ref(u, inviter_id):
    """لینک دعوت یه دوست رو برای بازیکنِ تازه‌وارد ثبت می‌کنه (فقط قبل از ساخت شخصیت، فقط یک بار)."""
    if has_char(u) or u["referred_by"] or inviter_id == u["id"]:
        return False
    inviter = user_by_id(inviter_id)
    if not has_char(inviter):
        return False
    return db.execute("UPDATE users SET referred_by=? WHERE id=? AND referred_by=0", (inviter_id, u["id"])).rowcount > 0


def pay_referrals(uid):
    """وقتی دعوت‌شده به لول ۵ برسه، جایزه‌ی دعوت‌کننده رو می‌ده (یک بار)."""
    u = user_by_id(uid)
    if not has_char(u) or not u["referred_by"] or u["ref_paid"] or level_of(u["xp"]) < 5:
        return
    with tx():
        if not db.execute("UPDATE users SET ref_paid=1 WHERE id=? AND ref_paid=0", (uid,)).rowcount:
            return
        inv = user_by_id(u["referred_by"])
        if not inv or inv["refs"] >= REF_MAX:
            return
        db.execute("UPDATE users SET refs=refs+1 WHERE id=?", (inv["id"],))
        add_coins(inv["id"], REF_REWARD)
        egg = give_item(inv["id"], "egg1")
        notify(inv["id"], f"🎉 دوستت {u['name']} به لول ۵ رسید!\nجایزه‌ی دعوت: 💰 +{REF_REWARD:,} و {egg}\n"
                          f"📊 دعوت‌های موفق: {inv['refs'] + 1}/{REF_MAX}")


def share_card_text(u):
    return (f"⚔️ من {u['name']} هستم؛ {CLASSES[u['cls']][0]} لول {level_of(u['xp'])} توی ربات ماجراجویی!\n"
            "غول می‌کشم، همراه می‌پرورونم و توی فصل‌ها رقابت می‌کنم. بیا با هم بازی کنیم 🔥")


@command("دعوت دوست", "referral", "refer")
async def cmd_refer(update, ctx, args):
    u = get_user(update.effective_user)
    link = ref_link(ctx.bot.username, u["id"])
    pending = db.execute("SELECT COUNT(*) FROM users WHERE referred_by=? AND ref_paid=0 AND gender<>'' AND cls<>''",
                         (u["id"],)).fetchone()[0]
    text = (f"🤝 دعوت دوست\n━━━━━━━━━━━━━━\nلینک اختصاصی تو:\n{link}\n\n"
            f"🎁 دوستت با این لینک شخصیت بسازه: 💰 +{REF_WELCOME:,} و 🥚 تخم هدیه می‌گیره\n"
            f"🏆 وقتی به لول ۵ برسه، تو هم: 💰 +{REF_REWARD:,} و 🥚 تخم می‌گیری\n\n"
            f"📊 دعوت‌های موفق: {u['refs']}/{REF_MAX}   ⏳ در انتظار لول ۵: {pending}")
    kb = Markup([[Btn("📤 فرستادن برای دوستام", url=share_url(link, share_card_text(u)))]])
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


# ============================== صندوق گنج تصادفی 🎁 ==============================
_chest_tick = {}
CHEST_NAMES = {1: "📦 صندوق چوبی", 2: "🎁 صندوق نقره‌ای", 3: "💎 صندوق طلایی"}


def chest_reward(uid, lvl, tier):
    scale = 1 + lvl * 0.05
    if tier == 1:
        coins, extra = int(random.randint(150, 400) * scale), ""
    elif tier == 2:
        coins, extra = int(random.randint(450, 1200) * scale), give_item(uid, random.choice(["potion2", "lock2", "egg1"]))
    else:
        coins, extra = int(3000 * scale), give_item(uid, "egg2")
    add_coins(uid, coins)
    return f"💰 +{coins:,} سکه" + (f" و {extra}" if extra else "")


def claim_chest(uid, cid, chat_id):
    with tx():
        row = db.execute("SELECT * FROM chests WHERE id=? AND chat_id=?", (cid, chat_id)).fetchone()
        if not row:
            return None, "این صندوق دیگه وجود نداره."
        if row["claimed_by"]:
            return None, "یکی زودتر از تو بازش کرد! 😅"
        if time.time() - row["ts"] > CHEST_TTL:
            return None, "⌛ این صندوق قفل شد (مهلتش تموم شد)."
        u = user_by_id(uid)
        if not has_char(u):
            return None, "اول توی پیوی ربات شخصیت بساز 🎭"
        if level_of(u["xp"]) < 2 and not is_admin(uid):
            return None, "از لول ۲ می‌تونی صندوق باز کنی."
        today = tehran_day()
        n = u["chest_n"] if u["chest_day"] == today else 0
        if n >= CHEST_DAILY_MAX:
            return None, f"امروز {CHEST_DAILY_MAX} صندوق باز کردی؛ بقیه رو به دیگران بسپار 😉"
        if not db.execute("UPDATE chests SET claimed_by=?, claimed_ts=? WHERE id=? AND claimed_by=0",
                          (uid, time.time(), cid)).rowcount:
            return None, "یکی زودتر از تو بازش کرد! 😅"
        db.execute("UPDATE users SET chest_day=?, chest_n=? WHERE id=?", (today, n + 1, uid))
        text = chest_reward(uid, level_of(u["xp"]), row["tier"])
    return {"tier": row["tier"], "name": u["name"], "text": text}, ""


async def chest_tick(ctx, chat_id):
    """گاهی یه صندوق گنج وسط گروه ظاهر می‌شه؛ اولین نفری که باز کنه برنده‌ست (خطاها بی‌صدا)."""
    try:
        mono, now = time.monotonic(), time.time()
        last = _chest_tick.get(chat_id)
        if last is not None and mono - last < 30:
            return
        if len(_chest_tick) > 20000:
            _chest_tick.clear()
        _chest_tick[chat_id] = mono
        c = db.execute("SELECT chest_next FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        if not c:
            return
        if c["chest_next"] == 0:   # اولین بار: چند دقیقه‌ی دیگه
            db.execute("UPDATE chats SET chest_next=? WHERE chat_id=?", (now + random.randint(600, 1800), chat_id))
            return
        if c["chest_next"] > now:
            return
        active = db.execute("SELECT COUNT(*) FROM chat_players WHERE chat_id=? AND ts>=?", (chat_id, now - 3 * 3600)).fetchone()[0]
        if active < CHEST_MIN_PLAYERS:
            return
        tier = random.choices([1, 2, 3], [70, 25, 5])[0]
        cid = db.execute("INSERT INTO chests(chat_id, ts, tier) VALUES(?,?,?)", (chat_id, now, tier)).lastrowid
        db.execute("UPDATE chats SET chest_next=? WHERE chat_id=?", (now + random.randint(*CHEST_GAP), chat_id))
        await send_event_sticker(ctx, chat_id, "chest", 1.0)
        await ctx.bot.send_message(
            chat_id, f"🎁✨ یه صندوق گنج پیدا شد!\n{CHEST_NAMES[tier]} — اولین نفری که بازش کنه برنده‌ست!\n"
                     f"⏳ {CHEST_TTL // 60} دقیقه مهلت داری. سریع باش! 🏃",
            reply_markup=Markup([[Btn("🗝 باز کردن صندوق", f"chest_open:{cid}")]]))
    except Exception as e:
        logging.warning("chest_tick: %s", e)


async def cb_chest(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return await q.answer()
    u = get_user(q.from_user)
    res, err = claim_chest(u["id"], int(parts[1]), q.message.chat_id)
    if not res:
        await q.answer(err, show_alert=True)
        if "قفل شد" in err:
            await safe_edit(q, "🔒 این صندوق گنج بدون برنده موند... دفعه‌ی بعد سریع‌تر باشید!")
        return
    await q.answer("🎉 صندوق مال تو شد!")
    await safe_edit(q, f"🎉 {res['name']} صندوق رو باز کرد!\n{CHEST_NAMES[res['tier']]}\n🏆 برنده‌ی صندوق: {res['text']}")
    await send_event_sticker(ctx, q.message.chat_id, "chest", 1.0)


# ============================== گزارش روزانه‌ی گروه 🌅 ==============================
TIPS = [
    "با «آهنگری» تجهیزاتت رو تا +۱۰ تقویت کن؛ شکست هیچ‌وقت وسیله رو خراب نمی‌کنه ⚒",
    "همراهت رو هر روز غذا بده؛ گرسنه که بشه توانایی‌ش خاموش می‌شه 🍖",
    "ماموریت ۸ ساعته‌ی همراه رو شبانه بفرست؛ صبح با سکه و شاید تخم برمی‌گرده 🧭",
    "غول جهانی ۵ نفر اول رو با 🐲 تخم افسانه‌ای جایزه می‌ده 🌍",
    "جمعه‌ها (به وقت ایران) XP و سکه‌ی کار ۱٫۵ برابره 🌟",
    "با «جاده» پله‌پله جایزه‌ی فصل رو بگیر 🛣",
    "وسایل ویژه‌ی کلاس تو توی «فروشگاه» منتظرن؛ هر کلاس سلاح مخصوص خودش رو داره 🛒",
    "توی «بازار» وسایل اضافه‌ت رو به بازیکن‌های دیگه بفروش 🏪",
    "هر دوستی که با «دعوت دوست» بیاد، برات سکه و تخم داره 🤝",
    "«فال» روزانه یه بونوس ۲۴ ساعته بهت می‌ده 🔮",
    "گاهی صندوق گنج وسط گروه ظاهر می‌شه؛ اولین نفر باش! 🎁",
    "با «ازدواج» (از لول ۸) ۵٪ سکه‌ی کار بیشتر می‌گیری 💍",
    "«چرخ» هر ۲۰ ساعت یه بار رایگانه 🎰",
    "مدال‌ها جایزه‌ی سکه دارن؛ «مدال‌ها» رو ببین ببین به کدوم نزدیکی 🏅",
    "قبل از دوئل زره و سلاحت رو چک کن؛ قدرت رزمی توی پروفایله ⚔️",
    "«سرداب» (از لول ۹) چالش مرحله‌ایه؛ معجون بزرگ جونت رو نجات می‌ده 🧪",
    "آیتم‌های 🟧 افسانه‌ای از رویدادها و جایزه‌های ویژه به‌دست میان",
    "توی «تالار افتخار» ببین بهترین‌های سرزمین کی‌ان 🏛",
    "هر چند روز یه غول جهانی میاد؛ گروهت رو بالا ببر! 🌍",
    "«آموزش» رو بزن؛ ماموریت‌های شروع جایزه‌ی خوبی دارن 🧭",
]


def digest_text(chat_id):
    now = time.time()
    lines = ["🌅 گزارش روزانه‌ی سرزمین ماجراجویی", f"📅 {date_line(now)}", "━━━━━━━━━━━━━━"]
    mult, label = event_mult(now)
    if mult > 1:
        lines.append(f"{label}: XP و سکه‌ی کار ×{mult:g} فعاله! 🔥")
    s = season_now()
    th = season_theme(s["no"])
    lines.append(f"🌟 فصل {fa(s['no'])} ({th[0]} {th[1]}) — {fmt_days(s['end'] - now)} مونده")
    top = db.execute("SELECT p.pts, u.name FROM season_points p JOIN users u ON u.id=p.user_id "
                     "WHERE p.season=? AND p.pts>0 ORDER BY p.pts DESC LIMIT 1", (s["no"],)).fetchone()
    if top:
        lines.append(f"   🥇 {top['name']} با {top['pts']:,} امتیاز جلوئه")
    b = db.execute("SELECT * FROM bosses WHERE chat_id=?", (chat_id,)).fetchone()
    if b and b["expires"] > now:
        lines.append(f"🐉 {b['emoji']} {b['name']} توی این گروهه! ({b['hp']:,}/{b['max_hp']:,}) — «حمله»")
    wb = world_active()
    if wb:
        lines.append(f"🌍 غول جهانی {wb['emoji']} {wb['name']}: {max(1, int(100 * wb['hp'] / wb['max_hp']))}٪ جان مونده "
                     f"({fmt_days(wb['t_end'] - now)}) — «حمله جهانی»")
    c = db.execute("SELECT score FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
    if c and c["score"] > 0:
        rank = db.execute("SELECT COUNT(*)+1 FROM chats WHERE score>?", (c["score"],)).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM chats WHERE score>0").fetchone()[0]
        lines.append(f"🏘 رتبه‌ی گروه شما: {fa(rank)} از {fa(total)} ({c['score']:,} امتیاز)")
    lines += ["", f"💡 نکته‌ی امروز: {TIPS[tehran_day(now) % len(TIPS)]}", "",
              "🎁 «جایزه» • 🎰 «چرخ» • 🔮 «فال» رو یادت نره!"]
    return "\n".join(lines)


_digest_tick = {}


async def digest_tick(ctx, chat_id):
    """اولین پیام هر روز (به وقت ایران) توی گروه، گزارش روزانه می‌فرسته (خطاها بی‌صدا)."""
    try:
        mono, now = time.monotonic(), time.time()
        last = _digest_tick.get(chat_id)
        if last is not None and mono - last < 60:
            return
        if len(_digest_tick) > 20000:
            _digest_tick.clear()
        _digest_tick[chat_id] = mono
        c = db.execute("SELECT digest_day, digest_off, added FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        today = tehran_day(now)
        if not c or c["digest_off"] or c["digest_day"] >= today:
            return
        db.execute("UPDATE chats SET digest_day=? WHERE chat_id=?", (today, chat_id))
        if now - c["added"] < 6 * 3600:   # گروهِ تازه‌اضافه‌شده؛ اول خوش‌آمدگویی
            return
        await ctx.bot.send_message(chat_id, digest_text(chat_id))
    except Exception as e:
        logging.warning("digest_tick: %s", e)


async def is_chat_admin(ctx, chat_id, uid):
    if is_admin(uid):
        return True
    try:
        m = await ctx.bot.get_chat_member(chat_id, uid)
        return m.status in ("creator", "administrator")
    except Exception:
        return False


@command("گزارش روزانه", "digest", args=True)
async def cmd_digest(update, ctx, args):
    here = update.effective_chat.id
    c = db.execute("SELECT digest_off FROM chats WHERE chat_id=?", (here,)).fetchone()
    on = bool(c) and not c["digest_off"]
    if args and args[0] in ("خاموش", "روشن", "off", "on"):
        if not await is_chat_admin(ctx, here, update.effective_user.id):
            return await update.message.reply_text("فقط ادمین‌های گروه می‌تونن گزارش روزانه رو روشن یا خاموش کنن.")
        want_on = args[0] in ("روشن", "on")
        db.execute("UPDATE chats SET digest_off=? WHERE chat_id=?", (0 if want_on else 1, here))
        return await update.message.reply_text("🌅 گزارش روزانه روشن شد." if want_on else "🌙 گزارش روزانه خاموش شد.")
    await update.message.reply_text(
        f"🌅 گزارش روزانه الان {'روشنه' if on else 'خاموشه'}.\nادمین‌ها با «گزارش روزانه خاموش» یا «گزارش روزانه روشن» تغییرش می‌دن.\n\n"
        + digest_text(here))


# ============================== تالار افتخار 🏛 ==============================
@command("تالار افتخار", "halloffame", "hof")
async def cmd_hof(update, ctx, args):
    here = update.effective_chat.id
    q = lambda sql, *a: db.execute(sql, a).fetchone()
    lines = ["🏛 تالار افتخار سرزمین ماجراجویی", "━━━━━━━━━━━━━━"]
    r = q("SELECT name, xp FROM users WHERE gender<>'' AND cls<>'' ORDER BY xp DESC LIMIT 1")
    if r:
        lines.append(f"👑 بالاترین لول: {r['name']} — لول {level_of(r['xp'])}")
    r = q("SELECT u.name, u.coins + COALESCE(b.amount, 0) AS w FROM users u LEFT JOIN bank b ON b.user_id=u.id "
          "WHERE u.gender<>'' AND u.cls<>'' ORDER BY w DESC LIMIT 1")
    if r:
        lines.append(f"💰 ثروتمندترین: {r['name']} — {r['w']:,} سکه")
    r = q("SELECT name, duel_wins FROM users WHERE duel_wins>0 ORDER BY duel_wins DESC LIMIT 1")
    if r:
        lines.append(f"⚔️ شکست‌ناپذیر دوئل: {r['name']} — {r['duel_wins']} برد")
    r = q("SELECT name, boss_kills FROM users WHERE boss_kills>0 ORDER BY boss_kills DESC LIMIT 1")
    if r:
        lines.append(f"🐉 غول‌کش برتر: {r['name']} — {r['boss_kills']} غول")
    r = q("SELECT u.name, SUM(d.dmg) AS t FROM world_damage d JOIN users u ON u.id=d.user_id GROUP BY d.user_id ORDER BY t DESC LIMIT 1")
    if r:
        lines.append(f"🌍 قهرمان غول جهانی: {r['name']} — {r['t']:,} آسیب")
    r = q("SELECT p.species, p.name AS pn, p.xp, u.name FROM pets p JOIN users u ON u.id=p.user_id ORDER BY p.xp DESC LIMIT 1")
    if r:
        lines.append(f"🐾 قوی‌ترین همراه: {SPECIES[r['species']][0]} {r['pn']} (لول {pet_level(r['xp'])}) — {r['name']}")
    r = q("SELECT u.name, COUNT(*) AS n FROM achievements a JOIN users u ON u.id=a.user_id GROUP BY a.user_id ORDER BY n DESC LIMIT 1")
    if r:
        lines.append(f"🏅 مدال‌دارترین: {r['name']} — {r['n']} مدال")
    r = q("SELECT name, invites + refs AS n FROM users WHERE invites + refs>0 ORDER BY n DESC LIMIT 1")
    if r:
        lines.append(f"📣 بهترین سفیر: {r['name']} — {r['n']} دعوت")
    r = q("SELECT name, place, season FROM season_results WHERE place=1 ORDER BY season DESC LIMIT 1")
    if r:
        th = season_theme(r["season"])
        lines.append(f"🌟 قهرمان فصل {r['season']} ({th[1]}): {r['name']}")
    r = q("SELECT chat_id, score FROM chats WHERE score>0 ORDER BY score DESC LIMIT 1")
    if r:
        lines.append(f"🏘 برترین گروه: {chat_label(r['chat_id'], here)} — {r['score']:,} امتیاز")
    if len(lines) == 2:
        lines.append("هنوز رکوردی ثبت نشده؛ اولین قهرمان باش! 🏆")
    lines += ["", "📍 اسم تو هم می‌تونه این‌جا بیاد؛ «برترین» و «برترین فصل» رو ببین!"]
    await update.message.reply_text("\n".join(lines))


# ============================== تنظیم خودکار ظاهر ربات (برای جذب از دور) ==============================
PROFILE_COMMANDS = [
    ("start", "شروع و ساخت شخصیت 🎭"), ("tutorial", "ماموریت‌های شروع و جایزه‌ها 🧭"),
    ("help", "راهنمای کامل بازی 📖"), ("profile", "کارت قهرمان و تجهیزات 👑"),
    ("work", "کار کن و سکه بگیر 🔨"), ("adventure", "ماجراجویی و غنیمت 🗺"),
    ("daily", "جایزه‌ی روزانه 🎁"), ("wheel", "چرخ شانس 🎰"), ("fal", "فال امروز 🔮"),
    ("pet", "همراه تو 🐾"), ("eggs", "تخم و جوجه‌کشی 🥚"),
    ("boss", "غول گروه 🐉"), ("attack", "حمله به غول ⚔️"),
    ("worldboss", "غول جهانی 🌍"), ("worldhit", "حمله به غول جهانی 💥"),
    ("shop", "فروشگاه 🛒"), ("inventory", "کوله‌پشتی 🎒"), ("market", "بازار بازیکن‌ها 🏪"), ("forge", "آهنگری ⚒"),
    ("season", "فصل و رتبه‌ی تو 🌟"), ("road", "جاده‌ی فصل 🛣"),
    ("top", "برترین‌ها 🏆"), ("topgroups", "برترین گروه‌ها 🏘"), ("hof", "تالار افتخار 🏛"),
    ("referral", "دعوت دوست و جایزه 🤝"), ("invite", "افزودن ربات به گروه ➕"),
]


def build_profile_commands():
    return [(n, d) for n, d in PROFILE_COMMANDS if REGISTRY.get(_key(n))]


def profile_description():
    text = ("⚔️ سرزمین ماجراجویی!\n"
            "شخصیتت رو بساز، کار کن، غول بکش، همراه بپرور، ازدواج کن و توی فصل‌های ماهانه قهرمان شو.\n\n"
            "🐉 غول جهانی • 🏪 بازار • ⚒ آهنگری • 🐾 همراه • 🎰 چرخ شانس • 🎁 صندوق گنج\n\n"
            "👇 START رو بزن و «آموزش» رو بخون تا ماموریت‌های شروع و جایزه‌هاش رو بگیری.\n"
            "ربات رو به گروهت اضافه کن تا همه با هم بازی کنید!")
    ch = os.getenv("BOT_CHANNEL", "").strip()
    return text + (f"\n📣 کانال: {ch}" if ch else "")


def profile_short_description():
    return "بازی ماجراجویی گروهی: غول جهانی، همراه، بازار، فصل‌ها و کلی هیجان 🔥"


async def setup_bot_profile(bot):
    """توضیحات، «درباره» و منوی دستورهای ربات رو (موقع روشن شدن) تنظیم می‌کنه. هر خطایی بی‌صدا رد می‌شه."""
    if os.getenv("AUTO_PROFILE", "1") == "0":
        return
    from telegram import BotCommand
    for name, call in (
        ("commands", lambda: bot.set_my_commands([BotCommand(n, d) for n, d in build_profile_commands()])),
        ("description", lambda: bot.set_my_description(profile_description())),
        ("short_description", lambda: bot.set_my_short_description(profile_short_description())),
    ):
        try:
            await call()
        except Exception as e:
            logging.info("تنظیم %s ربات ناموفق بود: %s", name, e)


async def _post_init(app):
    await setup_bot_profile(app.bot)


# ============================== مدال‌ها 🏅 ==============================
ACHS = [  # (کلید، ایموجی، اسم، توضیح، آمار، هدف، جایزه‌ی سکه)
    ("work1", "🔨", "تازه‌کار", "۱۰ بار کار کن", "work", 10, 300),
    ("work2", "⚒", "کارگر زحمتکش", "۱۰۰ بار کار کن", "work", 100, 1500),
    ("work3", "🏭", "ارباب کار", "۵۰۰ بار کار کن", "work", 500, 6000),
    ("adv1", "🧭", "مسافر", "۱۰ ماجراجویی انجام بده", "adv", 10, 400),
    ("adv2", "🗺", "ماجراجوی واقعی", "۵۰ ماجراجویی انجام بده", "adv", 50, 2000),
    ("adv3", "🏴‍☠️", "افسانه‌ی ماجراجویی", "۲۰۰ ماجراجویی انجام بده", "adv", 200, 8000),
    ("duel1", "⚔️", "اولین پیروزی", "یه دوئل ببر", "duel", 1, 200),
    ("duel2", "🥊", "جنگجوی میدان", "۱۰ دوئل ببر", "duel", 10, 1500),
    ("duel3", "🏆", "قهرمان دوئل", "۵۰ دوئل ببر", "duel", 50, 8000),
    ("boss1", "🐉", "غول‌کش", "توی کشتن یه غول شرکت کن", "boss", 1, 500),
    ("boss2", "🐲", "شکارچی غول", "توی کشتن ۵ غول شرکت کن", "boss", 5, 3000),
    ("boss3", "👑", "پادشاه غول‌ها", "توی کشتن ۲۰ غول شرکت کن", "boss", 20, 12000),
    ("inv1", "📣", "سفیر", "یه گروه جدید دعوت کن", "invites", 1, 500),
    ("inv2", "🌍", "سفیر بزرگ", "۵ گروه جدید دعوت کن", "invites", 5, 3000),
    ("lvl1", "⭐", "ستاره‌ی نوظهور", "به لول ۵ برس", "level", 5, 500),
    ("lvl2", "🌟", "قهرمان", "به لول ۱۰ برس", "level", 10, 2000),
    ("lvl3", "💫", "اسطوره", "به لول ۲۰ برس", "level", 20, 8000),
    ("lvl4", "🌌", "جاودانه", f"به لول {LEVEL_CAP} برس", "level", LEVEL_CAP, 25000),
    ("rich1", "💰", "ثروتمند", "۱۰ هزار سکه جمع کن (کیف + بانک)", "wealth", 10000, 500),
    ("rich2", "🤑", "میلیونر محلی", "۱۰۰ هزار سکه جمع کن", "wealth", 100000, 3000),
    ("rich3", "💎", "قارون", "۱ میلیون سکه جمع کن", "wealth", 1000000, 20000),
    ("streak1", "🔥", "وفادار", "۷ روز پشت‌سرهم جایزه‌ی روزانه بگیر", "streak", 7, 700),
    ("streak2", "🌋", "فداکار", "۳۰ روز پشت‌سرهم جایزه‌ی روزانه بگیر", "streak", 30, 5000),
    ("love", "💍", "دل‌داده", "ازدواج کن", "married", 1, 1000),
    ("guild", "🏰", "هم‌پیمان", "عضو یه انجمن بشو", "guild", 1, 500),
    ("coll1", "🎒", "جمع‌کننده", "۵ وسیله‌ی مختلف داشته باش", "items", 5, 800),
    ("coll2", "🧰", "گنج‌دار", "۱۵ وسیله‌ی مختلف داشته باش", "items", 15, 4000),
    ("legend", "🟧", "صاحب افسانه", "یه وسیله‌ی افسانه‌ای 🟧 داشته باش", "legend", 1, 3000),
    ("spin1", "🎡", "بخت‌آزما", "۱۰ بار چرخ شانس بچرخون", "spins", 10, 800),
    ("spin2", "🎰", "قمارباز", "۵۰ بار چرخ شانس بچرخون", "spins", 50, 4000),
    ("forge1", "⚒", "آهنگر ماهر", "یه وسیله رو به +۵ برسون", "maxplus", 5, 2000),
    ("forge2", "🔥", "استاد آهنگر", "یه وسیله رو به +۱۰ برسون", "maxplus", 10, 10000),
    ("trade1", "🏷", "فروشنده", "یه وسیله توی بازار بفروش", "sales", 1, 500),
    ("trade2", "🏪", "بازرگان", "۲۰ وسیله توی بازار بفروش", "sales", 20, 5000),
    ("champ", "🏆", "قهرمان فصل", "توی سه نفر برتر یه فصل بشو", "champ", 1, 10000),
    ("road", "🛣", "مسافر جاده", "همه‌ی ۱۰ پله‌ی جاده‌ی یه فصل رو بگیر", "roadfull", 1, 3000),
    ("pet1", "🥚", "جوجه‌کش", "اولین تخمت رو بشکن", "hatched", 1, 500),
    ("pet2", "🐾", "مربی", "۵ تخم بشکن", "hatched", 5, 3000),
    ("pet3", "⭐", "دوست حیوانات", "یه همراه رو به لول ۱۰ برسون", "petlvl", 10, 2000),
    ("pet4", "👑", "اسطوره‌ی همراه", "یه همراه رو به لول ۳۰ برسون", "petlvl", 30, 15000),
    ("pet5", "🟧", "افسانه‌ی زنده", "یه همراه افسانه‌ای 🟧 داشته باش", "legendpet", 1, 5000),
    ("trip1", "🧭", "کاشف", "۱۰ ماموریت همراه رو کامل کن", "trips", 10, 1500),
    ("trip2", "🗺", "کاشف بزرگ", "۵۰ ماموریت همراه رو کامل کن", "trips", 50, 6000),
    ("wb1", "🌍", "سرباز جهان", "۵ ضربه به غول جهانی بزن", "worldhits", 5, 1000),
    ("wb2", "🌠", "فاتح جهان", "توی شکست یه غول جهانی شرکت کن", "world_wins", 1, 8000),
    ("wb3", "🏆", "قهرمان جهان", "توی شکست ۳ غول جهانی شرکت کن", "world_wins", 3, 20000),
    ("chest1", "🎁", "گنج‌یاب", "یه صندوق گنج باز کن", "chests", 1, 500),
    ("chest2", "💎", "شکارچی گنج", "۲۰ صندوق گنج باز کن", "chests", 20, 4000),
    ("friend1", "🤝", "دوست‌ساز", "یه دوست با لینک تو بیاد و به لول ۵ برسه", "refs", 1, 1000),
    ("friend2", "🫂", "رهبر جمع", "۵ دوست جذب کن", "refs", 5, 5000),
    ("friend3", "🌐", "اسطوره‌ی جذب", "۱۵ دوست جذب کن", "refs", 15, 15000),
    ("tut", "🎓", "فارغ‌التحصیل", "همه‌ی ماموریت‌های شروع رو بگیر", "tutdone", 1, 2000),
    ("fal1", "🔮", "فال‌بین", "۷ بار فال بگیر", "fals", 7, 800),
    ("fal2", "🧿", "طالع‌بین", "۳۰ بار فال بگیر", "fals", 30, 4000),
]


def ach_stats(u):
    uid = u["id"]
    bal = db.execute("SELECT amount FROM bank WHERE user_id=?", (uid,)).fetchone()
    have = owned(uid)
    return {"work": u["work_count"], "adv": u["adv_count"], "duel": u["duel_wins"], "boss": u["boss_kills"],
            "invites": u["invites"], "level": level_of(u["xp"]),
            "wealth": u["coins"] + (bal["amount"] if bal else 0), "streak": u["streak"],
            "married": 1 if spouse_of(uid) else 0, "guild": 1 if guild_of(uid) else 0,
            "items": len(have), "legend": 1 if any(ITEM_RARITY.get(k) == "🟧" for k in have) else 0,
            "spins": u["wheel_spins"],
            "maxplus": db.execute("SELECT COALESCE(MAX(plus), 0) FROM item_plus WHERE user_id=?", (uid,)).fetchone()[0],
            "sales": u["market_sales"],
            "champ": 1 if db.execute("SELECT 1 FROM season_titles WHERE user_id=?", (uid,)).fetchone() else 0,
            "roadfull": len(db.execute("SELECT season FROM road_claims WHERE user_id=? GROUP BY season "
                                       "HAVING COUNT(*)=?", (uid, len(ROAD))).fetchall()),
            "hatched": u["hatched"], "trips": u["trips"], "world_wins": u["world_wins"],
            "petlvl": pet_stat(uid)[0], "legendpet": pet_stat(uid)[1],
            "worldhits": db.execute("SELECT COALESCE(SUM(hits), 0) FROM world_damage WHERE user_id=?", (uid,)).fetchone()[0],
            "chests": db.execute("SELECT COUNT(*) FROM chests WHERE claimed_by=?", (uid,)).fetchone()[0],
            "refs": u["refs"], "fals": u["fal_n"],
            "tutdone": 1 if db.execute("SELECT 1 FROM tutorial WHERE user_id=? AND step='_final'", (uid,)).fetchone() else 0}


def ach_done(uid):
    return {r["key"] for r in db.execute("SELECT key FROM achievements WHERE user_id=?", (uid,))}


def check_achievements(uid):
    """مدال‌های تازه‌ی باز شده رو ثبت می‌کنه، جایزه می‌ده و لیستشون رو برمی‌گردونه."""
    u = user_by_id(uid)
    if not has_char(u):
        return []
    done, stats, got = ach_done(uid), None, []
    stats = ach_stats(u)
    new = [a for a in ACHS if a[0] not in done and stats[a[4]] >= a[5]]
    if new:
        with tx():
            for a in new:
                if db.execute("INSERT OR IGNORE INTO achievements(user_id, key, ts) VALUES(?,?,?)",
                              (uid, a[0], time.time())).rowcount:
                    add_coins(uid, a[6])
                    got.append(a)
    return got


def ach_lines(new):
    return [f"{a[1]} {a[2]}\n   {a[3]}\n   💰 +{a[6]:,} سکه" for a in new]


async def send_ach(ctx, chat_id, new):
    """اعلام مدال‌ها؛ تکه‌تکه تا از سقف طول پیام تلگرام بیشتر نشه (مثلاً وقتی آپدیت میاد و ده‌ها مدال یک‌جا باز می‌شه)."""
    lines = ach_lines(new)
    for i in range(0, len(lines), 8):
        head = "🏅 مدال جدید باز شد!" if i == 0 else "🏅 ادامه‌ی مدال‌های جدید"
        await ctx.bot.send_message(chat_id, head + "\n━━━━━━━━━━━━━━\n" + "\n".join(lines[i:i + 8]))
    await send_event_sticker(ctx, chat_id, "achievement", 1.0)


async def ach_announce(ctx, chat_id, uid):
    """بعد از هر دستور: پیام‌های صندوق + مدال‌های تازه رو اعلام می‌کنه (هیچ‌وقت خطا نمی‌ده)."""
    try:
        await deliver_notices(ctx, chat_id, uid)
    except Exception as e:
        logging.info("deliver_notices: %s", e)
    try:
        pay_referrals(uid)
    except Exception as e:
        logging.info("pay_referrals: %s", e)
    try:
        new = check_achievements(uid)
        if new:
            await send_ach(ctx, chat_id, new)
    except Exception as e:
        logging.info("ach_announce: %s", e)
    try:
        await tut_announce(ctx, chat_id, uid)
    except Exception as e:
        logging.info("tut_announce: %s", e)


def ach_badges(uid):
    done = ach_done(uid)
    row = "".join([a[1] for a in ACHS if a[0] in done][:12])
    return f"{len(done)}/{len(ACHS)}  {row}".rstrip()


@command("مدال‌ها", "مدال", "دستاوردها", "دستاورد", "achievements")
async def cmd_achievements(update, ctx, args):
    u = get_user(update.effective_user)
    new = check_achievements(u["id"])
    done, stats = ach_done(u["id"]), ach_stats(u)
    lines = [f"🏅 مدال‌های {u['name']}", f"✅ {len(done)} از {len(ACHS)} مدال", "━━━━━━━━━━━━━━"]
    unlocked = [f"{a[1]} {a[2]}" for a in ACHS if a[0] in done]
    if unlocked:
        lines.append(" • ".join(unlocked))
    locked = [a for a in ACHS if a[0] not in done]
    near = sorted(locked, key=lambda a: -min(1.0, stats[a[4]] / a[5]))[:6]
    if near:
        lines += ["", "🎯 نزدیک‌ترین مدال‌ها:"]
        lines += [f"▫️ {a[1]} {a[2]} — {min(stats[a[4]], a[5]):,}/{a[5]:,}\n    {a[3]}" for a in near]
    if len(locked) > len(near):
        lines += ["", f"🔒 {len(locked) - len(near)} مدال دیگه هم منتظرته!"]
    await update.message.reply_text("\n".join(lines))
    if new:
        await send_ach(ctx, update.effective_chat.id, new)


# ============================== چرخ شانس 🎰 ==============================
WHEEL_PRIZES = [  # (وزن، نوع، مقدار)
    (28, "coins", (150, 300)), (16, "coins", (400, 800)), (6, "coins", (1500, 2500)),
    (14, "xp", (60, 140)),
    (8, "item", "potion"), (4, "item", "potion2"), (6, "item", "lock"), (3, "item", "lock2"),
    (8, "nothing", None),
]
_bg_tasks = set()


def wheel_cost(u):
    return WHEEL_PAID_BASE + level_of(u["xp"]) * 100


def wheel_roll(u, dice):
    """نتیجه‌ی چرخش. عدد تاس ماشین شانس تلگرام (۱ تا ۶۴) جکپات و سه‌تایی‌ها رو مشخص می‌کنه."""
    scale = (1 + level_of(u["xp"]) * 0.05) * season_perk("wheel")
    if dice == 64:
        return {"kind": "coins", "amount": int(10000 * scale), "label": "🎰 جکپات ۷۷۷!! 🤯\n", "big": True}
    if dice in (1, 22, 43):
        return {"kind": "coins", "amount": int(3000 * scale), "label": "🎰 سه‌تایی شد! 🤩\n", "big": True}
    pick = random.uniform(0, sum(p[0] for p in WHEEL_PRIZES))
    for weight, kind, val in WHEEL_PRIZES:
        pick -= weight
        if pick <= 0:
            break
    if kind == "coins":
        return {"kind": "coins", "amount": int(random.randint(*val) * scale), "label": "", "big": val[0] >= 1500}
    if kind == "xp":
        return {"kind": "xp", "amount": random.randint(*val), "label": "", "big": False}
    if kind == "item":
        return {"kind": "item", "item": val, "label": "", "big": val == "potion2"}
    return {"kind": "nothing", "label": "", "big": False}


def do_wheel(uid, dice, paid=False):
    """چرخش رو اعمال می‌کنه. برمی‌گردونه dict با text/note/big یا {'error': ...}."""
    with tx():
        u = user_by_id(uid)
        if paid:
            if not spend(uid, wheel_cost(u)):
                return {"error": f"💸 برای چرخوندن اضافه {wheel_cost(u):,} سکه لازمه."}
        else:
            left = cd_left(u, "last_wheel", WHEEL_COOLDOWN)
            if left > 0:
                return {"error": f"⏳ چرخ رایگانت {fmt_time(left)} دیگه آماده می‌شه."}
            set_time(uid, "last_wheel")
        r = wheel_roll(u, dice)
        note = ""
        if r["kind"] == "coins":
            add_coins(uid, r["amount"])
            text = f"💰 +{r['amount']:,} سکه"
        elif r["kind"] == "xp":
            xp, note = grant_xp(uid, r["amount"])
            text = f"✨ +{xp} XP"
        elif r["kind"] == "item":
            name = ITEMS[r["item"]][0]
            if qty(uid, r["item"]) < CONSUMABLE_MAX:
                db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                           "ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+1", (uid, r["item"]))
                text = f"🎁 {name} گرفتی!"
            else:
                cash = ITEMS[r["item"]][2] // 2
                add_coins(uid, cash)
                text = f"🎁 {name} (کوله‌ات پر بود؛ به جاش {cash:,} سکه گرفتی)"
        else:
            add_coins(uid, 20)
            text = "😅 این بار پوچ بود! ۲۰ سکه‌ی دلداری"
        db.execute("UPDATE users SET wheel_spins=wheel_spins+1 WHERE id=?", (uid,))
    return {"text": r["label"] + text, "note": note, "big": r["big"]}


async def _reveal_wheel(ctx, chat_id, uid, res):
    try:
        await asyncio.sleep(WHEEL_REVEAL_DELAY)
        name = user_by_id(uid)["name"]
        await ctx.bot.send_message(chat_id, f"🎡 نتیجه‌ی چرخ شانس {name}!\n━━━━━━━━━━━━━━\n{res['text']}" + res["note"])
        if "🎊🎉" in res["note"]:
            await send_event_sticker(ctx, chat_id, "levelup", 1.0)
        elif res["big"]:
            await send_event_sticker(ctx, chat_id, "bosswin", 1.0)
        else:
            await send_event_sticker(ctx, chat_id, "wheel")
    except Exception as e:
        logging.info("_reveal_wheel: %s", e)


async def run_wheel(ctx, chat_id, uid, paid):
    dice = random.randint(1, 64)
    try:  # ماشین شانس متحرک تلگرام؛ اگه نشد با عدد تصادفی ادامه می‌دیم
        m = await ctx.bot.send_dice(chat_id, emoji="🎰")
        if m is not None and getattr(m, "dice", None):
            dice = int(m.dice.value)
    except Exception as e:
        logging.info("send_dice ناموفق: %s", e)
    res = do_wheel(uid, dice, paid)
    if "error" in res:
        return await ctx.bot.send_message(chat_id, res["error"])
    task = asyncio.create_task(_reveal_wheel(ctx, chat_id, uid, res))  # بقیه‌ی بازیکن‌ها منتظر انیمیشن نمی‌مونن
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


@command("چرخ", "چرخ شانس", "wheel")
async def cmd_wheel(update, ctx, args):
    u = get_user(update.effective_user)
    left = cd_left(u, "last_wheel", WHEEL_COOLDOWN)
    if left > 0:
        cost = wheel_cost(u)
        return await update.message.reply_text(
            f"🎡 چرخ شانس رایگانت {fmt_time(left)} دیگه آماده می‌شه.\n💸 یا همین الان با {cost:,} سکه بچرخون:",
            reply_markup=Markup([[Btn(f"🎰 چرخوندن با {cost:,} سکه", f"wheel_pay:{u['id']}")]]))
    await run_wheel(ctx, update.effective_chat.id, u["id"], paid=False)


async def cb_wheel(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این دکمه برای تو نیست 😅", show_alert=True)
    u = user_by_id(uid)
    if u["coins"] < wheel_cost(u):
        return await q.answer(f"سکه‌ی کافی نداری ({wheel_cost(u):,}).", show_alert=True)
    await q.answer("🎰 چرخید!")
    await run_wheel(ctx, q.message.chat_id, uid, paid=True)


# ============================== گروه‌ها: غول، دعوت، جدول ==============================
BOSSES = [  # (اسم، ایموجی، ضریب جان)
    ("اژدهای آتشین", "🐉", 1.2), ("پادشاه مردگان", "🧟", 1.0), ("دیو سیاه", "👹", 1.1),
    ("کراکن غول‌پیکر", "🦑", 1.3), ("غول کوهستان", "🧌", 0.9), ("مار هزارسر", "🐍", 1.0),
    ("جادوگر تاریکی", "🧙‍♂️", 0.8),
]
_chat_touch, _boss_tick, _boss_edit = {}, {}, {}


def register_chat(chat, inviter_id=0):
    """وقتی ربات به گروه اضافه می‌شه ثبتش می‌کنه و دعوت‌کننده رو (فقط بار اول) می‌شناسه."""
    now = time.time()
    db.execute(
        "INSERT INTO chats(chat_id, title, username, added, last_active, boss_next, invited_by) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, "
        "username=excluded.username, invited_by=CASE WHEN chats.invited_by=0 AND chats.invite_paid=0 "
        "THEN excluded.invited_by ELSE chats.invited_by END",
        (chat.id, (getattr(chat, "title", None) or "")[:64], getattr(chat, "username", None) or "", now, now,
         now + random.randint(1200, 2400), inviter_id))


def touch_chat(chat, uid):
    """فعالیت گروه و بازیکن‌های فعالش رو ثبت می‌کنه (با محدودیت تا دیتابیس فشار نخوره)."""
    now = time.time()
    if len(_chat_touch) > 20000:
        _chat_touch.clear()
    if now - _chat_touch.get(chat.id, 0) > 60:
        _chat_touch[chat.id] = now
        db.execute(
            "INSERT INTO chats(chat_id, title, username, added, last_active, boss_next) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, username=excluded.username, "
            "last_active=excluded.last_active",
            (chat.id, (getattr(chat, "title", None) or "")[:64], getattr(chat, "username", None) or "", now, now,
             now + random.randint(1200, 3600)))
    key = (chat.id, uid)
    if now - _chat_touch.get(key, 0) > 300:
        _chat_touch[key] = now
        if has_char(user_by_id(uid)):
            db.execute("INSERT OR REPLACE INTO chat_players(chat_id, user_id, ts) VALUES(?,?,?)",
                       (chat.id, uid, now))


def chat_score(chat_id, pts):
    db.execute("UPDATE chats SET score=score+? WHERE chat_id=?", (pts, chat_id))


def boss_card(chat_id):
    b = db.execute("SELECT * FROM bosses WHERE chat_id=?", (chat_id,)).fetchone()
    if not b:
        return None, None
    top = db.execute("SELECT u.name, d.dmg FROM boss_damage d JOIN users u ON u.id=d.user_id "
                     "WHERE d.chat_id=? ORDER BY d.dmg DESC LIMIT 3", (chat_id,)).fetchall()
    lines = [f"{b['emoji']} {b['name']} ظاهر شد!", "━━━━━━━━━━━━━━",
             f"❤️ [{bar(b['hp'], b['max_hp'], 12)}]", f"   {b['hp']:,} / {b['max_hp']:,}",
             f"⏳ تا فرارش: {fmt_time(max(0, b['expires'] - time.time()))}"]
    if top:
        lines += ["", "🏆 بیشترین آسیب:"] + [f"{m} {r['name']} — {r['dmg']:,}" for m, r in zip("🥇🥈🥉", top)]
    lines += ["", "⚔️ با دکمه‌ی زیر یا نوشتن «حمله» بزن!"]
    return "\n".join(lines), Markup([[Btn("⚔️ حمله!", "boss_hit")]])


async def spawn_boss(ctx, chat_id, force=False):
    cutoff = time.time() - 48 * 3600
    rows = db.execute("SELECT u.xp FROM chat_players p JOIN users u ON u.id=p.user_id "
                      "WHERE p.chat_id=? AND p.ts>=?", (chat_id, cutoff)).fetchall()
    if len(rows) < BOSS_MIN_PLAYERS and not force:
        db.execute("UPDATE chats SET boss_next=? WHERE chat_id=?", (time.time() + 3600, chat_id))
        return False
    n = max(2, min(len(rows), 25))
    avg = sum(level_of(r["xp"]) for r in rows) / len(rows) if rows else 5
    name, emoji, mult = random.choice(BOSSES)
    hp = int(n * (300 + 70 * avg) * mult)
    now = time.time()
    db.execute("INSERT OR REPLACE INTO bosses(chat_id, name, emoji, max_hp, hp, spawned, expires) "
               "VALUES(?,?,?,?,?,?,?)", (chat_id, name, emoji, hp, hp, now, now + BOSS_TTL))
    db.execute("DELETE FROM boss_damage WHERE chat_id=?", (chat_id,))
    text, kb = boss_card(chat_id)
    await send_event_sticker(ctx, chat_id, "boss", 1.0)
    await ctx.bot.send_message(chat_id, "🚨 خطر! یه غول به گروه حمله کرد!\n\n" + text, reply_markup=kb)
    return True


def settle_boss(chat_id, killed, killer_id=None):
    """جایزه‌ها رو تقسیم می‌کنه، غول رو پاک می‌کنه و متن نتیجه رو برمی‌گردونه."""
    with tx():
        b = db.execute("SELECT * FROM bosses WHERE chat_id=?", (chat_id,)).fetchone()
        if not b:
            return ""
        rows = db.execute("SELECT d.user_id, d.dmg, u.name FROM boss_damage d JOIN users u ON u.id=d.user_id "
                          "WHERE d.chat_id=? AND d.dmg>0 ORDER BY d.dmg DESC", (chat_id,)).fetchall()
        total = sum(r["dmg"] for r in rows)
        pool = int(b["max_hp"] * BOSS_POOL_RATIO * (1 if killed else 0.2))
        lines, ups = [], []
        for i, r in enumerate(rows):
            coins, extra = int(pool * r["dmg"] / total), []
            if killed and i == 0:
                coins += int(pool * 0.2)
                extra.append("MVP")
            if killed and r["user_id"] == killer_id:
                coins += int(pool * 0.15)
                extra.append("ضربه‌ی آخر")
            add_coins(r["user_id"], coins)
            _, note = grant_xp(r["user_id"], 30 if killed else 6)
            if note:
                ups.append(r["name"])
            if killed:
                db.execute("UPDATE users SET boss_kills=boss_kills+1 WHERE id=?", (r["user_id"],))
            if i < 5:
                medal = "🥇🥈🥉🏅🏅"[i]
                lines.append(f"{medal} {r['name']} — {r['dmg']:,} آسیب ← 💰 {coins:,}" +
                             (f" ({'، '.join(extra)})" if extra else ""))
        mvp_line = ""
        if killed and rows and qty(rows[0]["user_id"], "potion2") < CONSUMABLE_MAX:
            db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                       "ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+1", (rows[0]["user_id"], "potion2"))
            mvp_line = f"\n🎁 هدیه‌ی MVP: 🧪 معجون بزرگ برای {rows[0]['name']}"
        nxt = time.time() + random.randint(*BOSS_GAP)
        if killed:
            db.execute("UPDATE chats SET boss_kills=boss_kills+1, score=score+200, boss_next=? WHERE chat_id=?",
                       (nxt, chat_id))
        else:
            db.execute("UPDATE chats SET boss_next=? WHERE chat_id=?", (nxt, chat_id))
        db.execute("DELETE FROM bosses WHERE chat_id=?", (chat_id,))
        db.execute("DELETE FROM boss_damage WHERE chat_id=?", (chat_id,))
    if killed:
        head = f"🏆🎉 {b['emoji']} {b['name']} نابود شد!\n━━━━━━━━━━━━━━\n"
    elif rows:
        head = f"💨 {b['emoji']} {b['name']} فرار کرد!\n━━━━━━━━━━━━━━\nجایزه‌ی دلداری برای شجاع‌ها:\n"
    else:
        return f"💨 {b['emoji']} {b['name']} بدون اینکه کسی بهش حمله کنه رفت... 😴"
    text = head + "\n".join(lines) + mvp_line
    if ups:
        text += "\n⬆️ لول‌آپ: " + "، ".join(ups)
    return text + (f"\n\n🏰 امتیاز گروه: +200" if killed else "")


async def boss_tick(ctx, chat_id):
    """ظهور غول، فرار غول منقضی و پرداخت جایزه‌ی دعوت (با محدودیت زمانی؛ خطاها بی‌صدا)."""
    now = time.monotonic()
    if len(_boss_tick) > 20000:
        _boss_tick.clear()
    last = _boss_tick.get(chat_id)
    if last is not None and now - last < 45:
        return
    _boss_tick[chat_id] = now
    try:
        await pay_invite(ctx, chat_id)
        b = db.execute("SELECT expires FROM bosses WHERE chat_id=?", (chat_id,)).fetchone()
        if b:
            if b["expires"] <= time.time():
                text = settle_boss(chat_id, False)
                if text:
                    await send_event_sticker(ctx, chat_id, "bossfail", 1.0)
                    await ctx.bot.send_message(chat_id, text)
            return
        c = db.execute("SELECT boss_next FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        if c and c["boss_next"] <= time.time() and random.random() < 0.5:
            await spawn_boss(ctx, chat_id)
    except Exception as e:
        logging.warning("boss_tick: %s", e)


def boss_damage_roll(u):
    lvl, weapon, cls = level_of(u["xp"]), best_power(u["id"], "weapon"), u["cls"]
    if cls != "hunter" and random.random() < 0.08:
        return 0, "💨 ضربه‌ت خطا رفت!"
    base = random.randint(20, 40) + lvl * 3 + weapon * 2
    mult = 1 + {"warrior": 0.15, "mage": 0.20, "hunter": 0.10}.get(cls, 0)
    if cls == "alchemist":
        base += 15
    dmg, note = int(base * mult * season_perk("boss_dmg") * (1 + (pet_bonus(u["id"], "dmg") + fal_bonus(u["id"], "dmg")) / 100)), ""
    if random.random() < 0.10 + (0.15 if cls == "ninja" else 0) + season_perk("crit"):
        dmg, note = dmg * 2, "💥 ضربه‌ی بحرانی!"
    return dmg, note


def do_boss_hit(u, chat_id):
    uid = u["id"]
    with tx():
        b = db.execute("SELECT * FROM bosses WHERE chat_id=?", (chat_id,)).fetchone()
        if not b or b["expires"] <= time.time():
            return {"kind": "alert", "text": "الان غولی توی این گروه نیست 😴"}
        u = user_by_id(uid)
        left = cd_left(u, "last_hit", BOSS_HIT_COOLDOWN)
        if left > 0:
            return {"kind": "alert", "text": f"⏳ {fmt_time(left)} دیگه می‌تونی حمله کنی."}
        set_time(uid, "last_hit")
        dmg, note = boss_damage_roll(u)
        dmg = min(dmg, b["hp"])
        if dmg > 0:
            db.execute("INSERT INTO boss_damage(chat_id, user_id, dmg, hits) VALUES(?,?,?,1) "
                       "ON CONFLICT(chat_id, user_id) DO UPDATE SET dmg=boss_damage.dmg+excluded.dmg, "
                       "hits=boss_damage.hits+1", (chat_id, uid, dmg))
            db.execute("UPDATE bosses SET hp=hp-? WHERE chat_id=?", (dmg, chat_id))
            chat_score(chat_id, 1 + dmg // 40)
        xp, lvl_note = grant_xp(uid, 3)
        hp = b["hp"] - dmg
        res = {"kind": "hit", "dmg": dmg, "note": note, "hp": hp, "max": b["max_hp"], "name": b["name"],
               "emoji": b["emoji"], "xp": xp, "lvl": lvl_note}
        if hp <= 0:
            res["kind"] = "kill"
            res["summary"] = settle_boss(chat_id, True, uid)
        return res


def boss_hit_text(u, res):
    lines = [f"⚔️ {u['name']} به {res['emoji']} {res['name']} حمله کرد!",
             f"💥 {res['dmg']:,} آسیب" if res["dmg"] else "💨 ضربه‌ت خطا رفت!"]
    if res["note"] and res["dmg"]:
        lines.append(res["note"])
    hp = max(0, res["hp"])
    lines.append(f"❤️ [{bar(hp, res['max'], 12)}] {hp:,}/{res['max']:,}")
    lines.append(f"✨ +{res['xp']} XP" + res["lvl"])
    text = "\n".join(lines)
    return text + "\n\n" + res["summary"] if res["kind"] == "kill" else text


@command("حمله", "attack", level=2)
async def cmd_boss_attack(update, ctx, args):
    u = get_user(update.effective_user)
    chat_id = update.effective_chat.id
    res = do_boss_hit(u, chat_id)
    if res["kind"] == "alert":
        return await update.message.reply_text(res["text"])
    await update.message.reply_text(boss_hit_text(u, res))
    if res["kind"] == "kill":
        await send_event_sticker(ctx, chat_id, "bosswin", 1.0)
    elif "🎊🎉" in res["lvl"]:
        await send_event_sticker(ctx, chat_id, "levelup", 1.0)


async def cb_boss(update, ctx):
    q = update.callback_query
    u = get_user(q.from_user)
    chat_id = q.message.chat_id
    if level_of(u["xp"]) < 2 and not is_admin(u["id"]):
        return await q.answer("از لول ۲ می‌تونی به غول حمله کنی.", show_alert=True)
    res = do_boss_hit(u, chat_id)
    if res["kind"] == "alert":
        return await q.answer(res["text"], show_alert=True)
    await q.answer(f"💥 {res['dmg']:,} آسیب زدی!" if res["dmg"] else "💨 ضربه‌ت خطا رفت!")
    if res["kind"] == "kill":
        await safe_edit(q, boss_hit_text(u, res))
        return await send_event_sticker(ctx, chat_id, "bosswin", 1.0)
    now = time.monotonic()
    last = _boss_edit.get(chat_id)
    if last is None or now - last >= 4:  # ویرایش پیام غول رو محدود می‌کنیم تا فلود نشه
        _boss_edit[chat_id] = now
        text, kb = boss_card(chat_id)
        if text:
            await safe_edit(q, text, kb)


@command("غول", "boss")
async def cmd_boss(update, ctx, args):
    text, kb = boss_card(update.effective_chat.id)
    if text:
        return await update.message.reply_text(text, reply_markup=kb)
    await update.message.reply_text(
        "😴 الان غولی توی گروه نیست.\n🐉 هر چند ساعت یه غول ظاهر می‌شه؛ فعال بمونید تا زودتر بیاد!\n"
        "💡 هرچی بازیکن فعال‌تر باشه، غول قوی‌تر و جایزه بیشتره.")


@command("احضار غول", "spawnboss", admin=True)
async def cmd_spawn_boss(update, ctx, args):
    if db.execute("SELECT 1 FROM bosses WHERE chat_id=?", (update.effective_chat.id,)).fetchone():
        return await update.message.reply_text("یه غول همین الان توی گروه هست.")
    await spawn_boss(ctx, update.effective_chat.id, force=True)


# ---------- دعوت با جایزه ----------
async def pay_invite(ctx, chat_id):
    c = db.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
    if not c or c["invite_paid"] or not c["invited_by"]:
        return
    n = db.execute("SELECT COUNT(*) FROM chat_players p JOIN users u ON u.id=p.user_id "
                   "WHERE p.chat_id=? AND u.gender<>'' AND u.cls<>''", (chat_id,)).fetchone()[0]
    inviter = user_by_id(c["invited_by"])
    if n < INVITE_MIN_PLAYERS or not has_char(inviter):
        return
    gift = None
    with tx():
        if not db.execute("UPDATE chats SET invite_paid=1 WHERE chat_id=? AND invite_paid=0", (chat_id,)).rowcount:
            return
        inviter = user_by_id(inviter["id"])
        if inviter["invites"] >= INVITE_MAX:
            return
        total = inviter["invites"] + 1
        db.execute("UPDATE users SET invites=? WHERE id=?", (total, inviter["id"]))
        add_coins(inviter["id"], INVITE_REWARD)
        _, note = grant_xp(inviter["id"], 100)
        key = INVITE_MILESTONES.get(total)
        if key:
            db.execute("INSERT INTO items(user_id, item, qty) VALUES(?,?,1) "
                       "ON CONFLICT(user_id, item) DO UPDATE SET qty=1", (inviter["id"], key))
            gift = ITEMS[key][0]
    text = (f"📣🎁 {inviter['name']} ربات رو به این گروه آورد و {INVITE_REWARD:,} سکه + ۱۰۰ XP جایزه گرفت!\n"
            f"📊 دعوت‌های موفق: {total}/{INVITE_MAX}")
    if gift:
        text += f"\n🎖 جایزه‌ی ویژه: {gift}"
    await send_event_sticker(ctx, chat_id, "daily", 1.0)
    await ctx.bot.send_message(chat_id, text + note)


@command("دعوت", "invite")
async def cmd_invite(update, ctx, args):
    u = get_user(update.effective_user)
    url = f"https://t.me/{ctx.bot.username}?startgroup=true"
    lines = ["📣 دعوت با جایزه", "━━━━━━━━━━━━━━",
             f"ربات رو به یه گروه جدید اضافه کن؛ وقتی {INVITE_MIN_PLAYERS} نفر توش شخصیت بسازن و بازی کنن:",
             f"💰 {INVITE_REWARD:,} سکه + ✨ ۱۰۰ XP", "",
             f"📊 دعوت‌های موفق تو: {u['invites']}/{INVITE_MAX}", "",
             "🎖 جایزه‌های ویژه:"]
    for k, key in sorted(INVITE_MILESTONES.items()):
        lines.append(f"{'✅' if u['invites'] >= k else '▫️'} با {k} دعوت: {ITEMS[key][0]} ({ITEMS[key][5].split(' — ')[0]})")
    await update.message.reply_text("\n".join(lines),
                                    reply_markup=Markup([[Btn("➕ افزودن ربات به گروه", url=url)]]))


# ---------- جدول برترین گروه‌ها ----------
@command("برترین گروه‌ها", "برترین گروه", "topgroups")
async def cmd_top_groups(update, ctx, args):
    here = update.effective_chat.id
    rows = db.execute("SELECT * FROM chats WHERE score>0 ORDER BY score DESC LIMIT 10").fetchall()
    if not rows:
        return await update.message.reply_text("🏆 هنوز امتیازی ثبت نشده. بازی کنید تا گروهتون بالا بره!")
    lines = ["🏆 برترین گروه‌های ماجراجویی", "━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows):
        medal = "🥇🥈🥉"[i] if i < 3 else f"{i + 1}."
        # اسم گروه‌های خصوصی نمایش داده نمی‌شه
        name = (f"{r['title']} (@{r['username']})" if r["username"] else
                (f"{r['title']} (گروه شما)" if r["chat_id"] == here else "🔒 یه گروه خصوصی"))
        lines.append(f"{medal} {name}\n     ⭐ {r['score']:,} امتیاز • 🐉 {r['boss_kills']} غول")
    mine = db.execute("SELECT * FROM chats WHERE chat_id=?", (here,)).fetchone()
    if mine:
        rank = db.execute("SELECT COUNT(*)+1 FROM chats WHERE score>?", (mine["score"],)).fetchone()[0]
        lines += ["", f"📍 گروه شما: رتبه‌ی {rank} با {mine['score']:,} امتیاز",
                  "💡 امتیاز از کار، ماجراجویی، جایزه و کشتن غول‌ها جمع می‌شه."]
    await update.message.reply_text("\n".join(lines))


# ============================== ازدواج 💍 ==============================
def spouse_of(uid):
    """(ردیف همسر، زمان ازدواج) یا None."""
    r = db.execute("SELECT * FROM marriages WHERE a=? OR b=?", (uid, uid)).fetchone()
    if not r:
        return None
    u = user_by_id(r["b"] if r["a"] == uid else r["a"])
    return (u, r["since"]) if u else None


def marry_problem(me, other):
    """None یعنی مشکلی نیست؛ وگرنه متن دلیل."""
    if not has_char(other):
        return "این بازیکن هنوز شخصیت نساخته."
    if {me["gender"], other["gender"]} != {"m", "f"}:
        return "💍 ازدواج فقط بین یک مرد و یک زن ممکنه."
    for p in (me, other):
        if level_of(p["xp"]) < MARRY_LEVEL:
            return f"💍 برای ازدواج هر دو نفر باید حداقل لول {MARRY_LEVEL} باشن ({p['name']} هنوز نرسیده)."
        if spouse_of(p["id"]):
            return f"💔 {p['name']} قبلاً ازدواج کرده."
    return None


@command("ازدواج", "marry", level=MARRY_LEVEL)
async def cmd_marry(update, ctx, args):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if not target or target.is_bot or target.id == update.effective_user.id:
        return await msg.reply_text("💍 برای خواستگاری، روی پیام طرف ریپلای کن و بنویس: ازدواج")
    me, other = get_user(update.effective_user), user_by_id(target.id)
    problem = marry_problem(me, other)
    if problem:
        return await msg.reply_text(problem)
    if me["coins"] < MARRY_COST:
        return await msg.reply_text(f"💸 هزینه‌ی حلقه و مراسم {MARRY_COST:,} سکه‌ست و تو به اندازه‌ی کافی نداری.")
    db.execute("INSERT OR REPLACE INTO marriage_requests(from_id, to_id, chat_id, ts) VALUES(?,?,?,?)",
               (me["id"], other["id"], msg.chat_id, time.time()))
    kb = Markup([[Btn("💍 بله، قبول می‌کنم", f"marry_yes:{me['id']}:{other['id']}"),
                  Btn("💔 نه", f"marry_no:{me['id']}:{other['id']}")]])
    await msg.reply_text(
        f"💍✨ خواستگاری!\n━━━━━━━━━━━━━━\n"
        f"{me['name']} با یه حلقه‌ی درخشان جلوی {other['name']} زانو زد 🥺🌹\n\n"
        f"💎 هزینه‌ی حلقه و مراسم: {MARRY_COST:,} سکه (از خواستگار)\n\n"
        f"{other['name']}، جوابت چیه؟", reply_markup=kb)


def do_marry(from_id, to_id):
    with tx():
        req = db.execute("SELECT ts FROM marriage_requests WHERE from_id=? AND to_id=?",
                         (from_id, to_id)).fetchone()
        if not req:
            return False, "این خواستگاری قبلاً تعیین تکلیف شده."
        db.execute("DELETE FROM marriage_requests WHERE from_id=? AND to_id=?", (from_id, to_id))
        if time.time() - req["ts"] > MARRY_TTL:
            return False, "⌛ خواستگاری منقضی شد."
        me, other = user_by_id(from_id), user_by_id(to_id)
        problem = marry_problem(me, other)
        if problem:
            return False, problem
        if not spend(from_id, MARRY_COST):
            return False, f"💸 {me['name']} سکه‌ی کافی برای حلقه نداره ({MARRY_COST:,})."
        a, b = sorted((from_id, to_id))
        db.execute("INSERT INTO marriages(a, b, since) VALUES(?,?,?)", (a, b, time.time()))
        grant_xp(from_id, 50)
        grant_xp(to_id, 50)
    return True, ""


async def cb_marry(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return await q.answer()
    action, from_id, to_id = parts[0], int(parts[1]), int(parts[2])
    clicker = q.from_user.id
    if action == "marry_yes" and clicker != to_id:
        return await q.answer("این خواستگاری برای تو نیست 😅", show_alert=True)
    if action == "marry_no":
        if clicker not in (from_id, to_id):
            return await q.answer("این خواستگاری برای تو نیست.", show_alert=True)
        cur = db.execute("DELETE FROM marriage_requests WHERE from_id=? AND to_id=?", (from_id, to_id))
        if not cur.rowcount:
            return await q.answer("این خواستگاری قبلاً تعیین تکلیف شده.", show_alert=True)
        await q.answer()
        who = "خواستگار پشیمون شد" if clicker == from_id else "جواب رد داد"
        return await safe_edit(q, f"💔 {user_by_id(clicker)['name']} {who}... خواستگاری تموم شد 🥀")
    ok, text = do_marry(from_id, to_id)
    if not ok:
        await q.answer(text, show_alert=True)
        return await safe_edit(q, f"❌ {text}")
    a, b = user_by_id(from_id), user_by_id(to_id)
    await q.answer("مبارک باشه! 💍")
    await safe_edit(
        q, f"💒🎊 جشن عروسی!\n━━━━━━━━━━━━━━\n{a['name']}  💞  {b['name']}\n"
           "رسماً زن و شوهر شدید! 🥂✨\n\n🎁 هدیه‌ی عروسی: ۵۰ XP برای هر کدوم\n"
           f"💫 مزایا: +{MARRY_BONUS}٪ سکه‌ی کار و دستور «عشق»")
    await send_event_sticker(ctx, q.message.chat_id, "marry", 1.0)
    await ach_announce(ctx, q.message.chat_id, from_id)  # خواستگار هم همون لحظه مدالش رو می‌بینه


@command("همسر", "spouse")
async def cmd_spouse(update, ctx, args):
    me = get_user(update.effective_user)
    sp = spouse_of(me["id"])
    if not sp:
        return await update.message.reply_text(
            f"💔 هنوز همسر نداری.\nاز لول {MARRY_LEVEL} می‌تونی روی پیام طرف مقابل (جنس مخالف) ریپلای کنی و بنویسی: ازدواج")
    mate, since = sp
    days = int((time.time() - since) / 86400)
    await update.message.reply_text(
        f"💍 زندگی مشترک\n━━━━━━━━━━━━━━\n{me['name']}  💞  {mate['name']}\n"
        f"📅 {days} روزه که با هم هستید\n⭐ لول همسرت: {level_of(mate['xp'])} | {CLASSES.get(mate['cls'], ('—',))[0]}\n"
        f"💫 مزیت: +{MARRY_BONUS}٪ سکه‌ی کار")


@command("عشق", "love")
async def cmd_love(update, ctx, args):
    u = get_user(update.effective_user)
    sp = spouse_of(u["id"])
    if not sp:
        return await update.message.reply_text("💔 فقط زن و شوهرها می‌تونن به هم عشق بفرستن. اول «ازدواج» (با ریپلای)!")
    left = cd_left(u, "last_love", LOVE_COOLDOWN)
    if left > 0:
        return await update.message.reply_text(f"⏳ {fmt_time(left)} دیگه می‌تونی عشق بفرستی 💞")
    mate = sp[0]
    gift = random.randint(40, 80) + level_of(u["xp"]) * 2
    with tx():
        set_time(u["id"], "last_love")
        add_coins(u["id"], gift)
        add_coins(mate["id"], gift)
        grant_xp(u["id"], 10)
        grant_xp(mate["id"], 10)
    await reply_game(update, ctx,
                     random.choice(LOVE_LINES).format(a=u["name"], b=mate["name"]) +
                     f"\n━━━━━━━━━━━━━━\n💰 هر کدوم +{gift:,} سکه\n✨ +10 XP برای هر دو", "love", 1.0)


@command("طلاق", "divorce")
async def cmd_divorce(update, ctx, args):
    me = get_user(update.effective_user)
    sp = spouse_of(me["id"])
    if not sp:
        return await update.message.reply_text("💔 تو همسری نداری.")
    kb = Markup([[Btn("💔 بله، طلاق", f"divorce_yes:{me['id']}"), Btn("↩️ پشیمون شدم", f"divorce_no:{me['id']}")]])
    await update.message.reply_text(
        f"💔 مطمئنی می‌خوای از {sp[0]['name']} جدا بشی؟\nهزینه‌ی طلاق: {DIVORCE_COST:,} سکه (از تو)", reply_markup=kb)


async def cb_divorce(update, ctx):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return await q.answer()
    uid = int(parts[1])
    if q.from_user.id != uid:
        return await q.answer("این پیام برای تو نیست.", show_alert=True)
    if parts[0] == "divorce_no":
        await q.answer()
        return await safe_edit(q, "💞 خوشحالیم که موندید!")
    with tx():
        sp = spouse_of(uid)
        if not sp:
            res = (False, "تو همسری نداری.")
        elif not spend(uid, DIVORCE_COST):
            res = (False, f"برای طلاق {DIVORCE_COST:,} سکه لازمه.")
        else:
            a, b = sorted((uid, sp[0]["id"]))
            db.execute("DELETE FROM marriages WHERE a=? AND b=?", (a, b))
            res = (True, sp[0]["name"])
    if not res[0]:
        return await q.answer(res[1], show_alert=True)
    await q.answer()
    await safe_edit(q, f"💔 {user_by_id(uid)['name']} و {res[1]} از هم جدا شدند...\nهر کس راه خودش رو رفت 🥀")
    await send_event_sticker(ctx, q.message.chat_id, "divorce", 1.0)


# ======================= استیکر رویدادها (فقط ادمین) =======================
@command("ثبت استیکر", "addsticker", args=True, admin=True)
async def cmd_add_sticker(update, ctx, args):
    msg = update.message
    rt = msg.reply_to_message
    if not args or args[0] not in EVENT_EMOJI or not rt or not rt.sticker:
        return await msg.reply_text("روی یه استیکر ریپلای کن و بنویس: ثبت استیکر نام‌رویداد\nرویدادها: " +
                                    " ، ".join(EVENT_EMOJI))
    db.execute("INSERT OR IGNORE INTO event_stickers(event, file_id) VALUES(?,?)", (args[0], rt.sticker.file_id))
    await msg.reply_text(f"✅ این استیکر برای رویداد «{args[0]}» ثبت شد.")


@command("حذف استیکر", "delsticker", args=True, admin=True)
async def cmd_del_sticker(update, ctx, args):
    if not args or args[0] not in EVENT_EMOJI:
        return await update.message.reply_text("مثال: حذف استیکر welcome  (همه‌ی استیکرهای ثبت‌شده‌ی اون رویداد پاک می‌شه)")
    cur = db.execute("DELETE FROM event_stickers WHERE event=?", (args[0],))
    await update.message.reply_text(f"🗑 {cur.rowcount} استیکر حذف شد.")


# ============================== انجمن ==============================
@command("ساخت انجمن", "newguild", args=True)
async def cmd_guild_create(update, ctx, args):
    name = re.sub(r"\s+", " ", " ".join(args)).strip()
    if not GUILD_NAME_RE.fullmatch(name):
        return await update.message.reply_text(
            "نام انجمن باید ۳ تا ۲۴ حرف (فارسی/انگلیسی/عدد) باشه.\nمثال: ساخت انجمن نگهبانان شب")
    uid = update.effective_user.id
    with tx():
        if guild_of(uid):
            return await update.message.reply_text("قبل از ساخت انجمن باید از انجمن فعلی خارج بشی.")
        if db.execute("SELECT 1 FROM guilds WHERE name=?", (name,)).fetchone():
            return await update.message.reply_text("این نام انجمن قبلاً انتخاب شده.")
        if GUILD_CREATE_COST and not spend(uid, GUILD_CREATE_COST):
            return await update.message.reply_text(f"ساخت انجمن {GUILD_CREATE_COST:,} سکه هزینه داره.")
        gid = db.execute("INSERT INTO guilds(name, owner_id, created) VALUES(?,?,?)",
                         (name, uid, time.time())).lastrowid
        db.execute("INSERT INTO guild_members(user_id, guild_id, role, joined) VALUES(?,?,?,?)",
                   (uid, gid, "owner", time.time()))
    await update.message.reply_text(f"🏰 انجمن «{name}» ساخته شد!\nشناسه: {gid}\nبرای دعوت دیگران: عضویت {gid}")


@command("عضویت", "joinguild", args=True)
async def cmd_guild_join(update, ctx, args):
    gid = parse_int(args[0]) if args else None
    if gid is None:
        return await update.message.reply_text("مثال: عضویت 12")
    uid = update.effective_user.id
    with tx():
        if guild_of(uid):
            return await update.message.reply_text("تو عضو یه انجمن هستی؛ اول «ترک انجمن» رو بزن.")
        g = db.execute("SELECT * FROM guilds WHERE id=?", (gid,)).fetchone()
        if not g:
            return await update.message.reply_text("انجمن پیدا نشد.")
        n = db.execute("SELECT COUNT(*) FROM guild_members WHERE guild_id=?", (gid,)).fetchone()[0]
        if n >= GUILD_MAX_MEMBERS:
            return await update.message.reply_text(f"ظرفیت این انجمن ({GUILD_MAX_MEMBERS} عضو) تکمیل شده.")
        db.execute("INSERT INTO guild_members(user_id, guild_id, role, joined) VALUES(?,?,?,?)",
                   (uid, gid, "member", time.time()))
    await update.message.reply_text(f"🎉 به انجمن «{g['name']}» پیوستی!")


@command("ترک انجمن", "leaveguild")
async def cmd_guild_leave(update, ctx, args):
    uid = update.effective_user.id
    with tx():
        row = db.execute("SELECT * FROM guild_members WHERE user_id=?", (uid,)).fetchone()
        if not row:
            return await update.message.reply_text("عضو هیچ انجمنی نیستی.")
        if row["role"] == "owner":
            nxt = db.execute("SELECT user_id FROM guild_members WHERE guild_id=? AND user_id<>? "
                             "ORDER BY joined LIMIT 1", (row["guild_id"], uid)).fetchone()
            if nxt:
                db.execute("UPDATE guild_members SET role='owner' WHERE user_id=?", (nxt["user_id"],))
                db.execute("UPDATE guilds SET owner_id=? WHERE id=?", (nxt["user_id"], row["guild_id"]))
            else:
                db.execute("DELETE FROM guilds WHERE id=?", (row["guild_id"],))
        db.execute("DELETE FROM guild_members WHERE user_id=?", (uid,))
    await update.message.reply_text("از انجمن خارج شدی.")


@command("انجمن", "guild", args=True)
async def cmd_guild_info(update, ctx, args):
    uid = update.effective_user.id
    gid = parse_int(args[0]) if args else None
    g = (db.execute("SELECT id, name FROM guilds WHERE id=?", (gid,)).fetchone() if gid is not None
         else guild_of(uid))
    if not g:
        return await update.message.reply_text("انجمن فعالی نداری. برای دیدن انجمن‌ها: انجمن‌ها")
    rows = db.execute("SELECT u.name, u.xp, u.cls, m.role FROM guild_members m JOIN users u ON u.id=m.user_id "
                      "WHERE m.guild_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 ELSE 1 END, u.xp DESC",
                      (g["id"],)).fetchall()
    bonus = min(10, len(rows) // 3)
    await update.message.reply_text(
        f"🏰 {g['name']}\nشناسه: {g['id']}\nاعضا: {len(rows)}/{GUILD_MAX_MEMBERS}\n"
        f"🎁 بونوس کار اعضا: +{bonus}٪ (هر ۳ عضو = ۱٪، حداکثر ۱۰٪)\n\n" +
        "\n".join(f"{'👑' if r['role'] == 'owner' else '•'} {r['name']} — لول {level_of(r['xp'])} | "
                  f"{CLASSES.get(r['cls'], ('—',))[0]}" for r in rows))


@command("انجمن‌ها", "انجمن ها", "guilds")
async def cmd_guild_list(update, ctx, args):
    rows = db.execute(
        "SELECT g.id, g.name, COUNT(m.user_id) AS members, COALESCE(SUM(u.xp),0) AS total "
        "FROM guilds g LEFT JOIN guild_members m ON m.guild_id=g.id LEFT JOIN users u ON u.id=m.user_id "
        "GROUP BY g.id ORDER BY total DESC, g.id LIMIT 15").fetchall()
    if not rows:
        return await update.message.reply_text("هنوز انجمنی ساخته نشده.")
    await update.message.reply_text(
        "🏰 انجمن‌ها (بر اساس مجموع XP)\n\n" + "\n".join(
            f"{r['id']}. {r['name']} — {r['members']}/{GUILD_MAX_MEMBERS} عضو | {r['total']:,} XP" for r in rows) +
        "\n\nبرای عضویت: عضویت شناسه")


# ============================== ادمین ==============================
def get_target(update, args):
    msg = update.message
    if msg.reply_to_message:
        return msg.reply_to_message.from_user.id
    return parse_int(args[0]) if args else None


@command("بده", "give", args=True, admin=True)
async def cmd_give(update, ctx, args):
    """بده 1000 (به خودت) | با ریپلای: بده 500 | بده 500 آیدی"""
    msg = update.message
    raw = (args[0] if args else "").lstrip("-")
    amount = parse_int(raw)
    if amount is None:
        return await msg.reply_text("مثال: بده 1000000")
    if args[0].startswith("-"):
        amount = -amount
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
        get_user(target)
        tid, name = target.id, target.first_name
    elif len(args) > 1 and parse_int(args[1]) is not None:
        tid, name = parse_int(args[1]), args[1]
        db.execute("INSERT OR IGNORE INTO users(id, name) VALUES(?, ?)", (tid, name))
    else:
        get_user(update.effective_user)
        tid, name = update.effective_user.id, "خودت"
    add_coins(tid, amount)
    await msg.reply_text(f"✅ {amount} سکه به {name} اضافه شد.")


@command("لول", "setlevel", args=True, admin=True)
async def cmd_setlevel(update, ctx, args):
    msg = update.message
    n = parse_int(args[0]) if args else None
    if n is None:
        return await msg.reply_text("مثال: لول 20")
    n = max(1, min(LEVEL_CAP, n))
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    get_user(target)
    db.execute("UPDATE users SET xp=? WHERE id=?", (xp_for_level(n), target.id))
    await msg.reply_text(f"✅ لول {target.first_name} شد {n}.")


@command("بن", "ban", args=True, admin=True)
async def cmd_ban(update, ctx, args):
    msg = update.message
    tid = get_target(update, args)
    if tid is None:
        return await msg.reply_text("روی پیام طرف ریپلای کن و بنویس: بن (یا: بن آیدی_عددی)")
    if is_admin(tid):
        return await msg.reply_text("نمی‌تونی ادمین رو بن کنی 😅")
    db.execute("INSERT OR IGNORE INTO banned(user_id) VALUES(?)", (tid,))
    note = ""
    try:
        await ctx.bot.ban_chat_member(update.effective_chat.id, tid)
    except Exception:
        note = "\n(از گروه تلگرام بن نشد؛ ربات باید ادمین گروه با دسترسی بن باشه.)"
    await msg.reply_text(f"🚫 کاربر از بازی بن شد.{note}")


@command("آزاد", "unban", args=True, admin=True)
async def cmd_unban(update, ctx, args):
    msg = update.message
    tid = get_target(update, args)
    if tid is None:
        return await msg.reply_text("روی پیام طرف ریپلای کن و بنویس: آزاد (یا: آزاد آیدی_عددی)")
    db.execute("DELETE FROM banned WHERE user_id=?", (tid,))
    try:
        await ctx.bot.unban_chat_member(update.effective_chat.id, tid, only_if_banned=True)
    except Exception:
        pass
    await msg.reply_text("✅ بن برداشته شد.")


# ============================== پاداش چت ==============================
def chat_reward(user_id, text):
    if len(text) < 5:
        return
    now, day = time.time(), today()
    with tx():
        u = user_by_id(user_id)
        if not has_char(u):
            return
        total = u["chat_reward_total"] if u["chat_reward_day"] == day else 0
        if now - u["chat_reward_ts"] < CHAT_COOLDOWN or total >= CHAT_DAILY_CAP:
            return
        db.execute("UPDATE users SET coins=coins+?, chat_reward_day=?, chat_reward_total=?, "
                   "chat_reward_ts=? WHERE id=?", (CHAT_REWARD, day, total + CHAT_REWARD, now, user_id))


# ============================== اجرا ==============================
CALLBACKS = {
    "shop": cb_shop, "buy": cb_buy, "equip": cb_inventory, "sell": cb_inventory,
    "inv": cb_inventory, "city_up": cb_city_up, "duel": cb_duel, "dg": cb_dungeon,
    "friend_accept": cb_friend, "friend_reject": cb_friend,
    "marry_yes": cb_marry, "marry_no": cb_marry,
    "divorce_yes": cb_divorce, "divorce_no": cb_divorce,
    "boss_hit": cb_boss, "wheel_pay": cb_wheel,
    "mk_page": cb_market, "mk_buy": cb_market, "mk_offer": cb_market, "mk_mine": cb_market,
    "mk_pick": cb_market, "mk_list": cb_market, "mk_cancel": cb_market,
    "forge": cb_forge, "road_claim": cb_road,
    "pet_menu": cb_pet, "pet_feed": cb_pet, "pet_play": cb_pet, "pet_go": cb_pet, "pet_claim": cb_pet,
    "pet_list": cb_pet, "pet_set": cb_pet, "pet_rel": cb_pet, "pet_relyes": cb_pet, "pet_eggs": cb_pet,
    "egg_start": cb_pet, "egg_hatch": cb_pet, "world_hit": cb_world,
    "tut_claim": cb_tut, "chest_open": cb_chest,
}


def main():
    if not TOKEN:
        raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده است؛ توکن را داخل کد ننویسید.")
    cleanup_old()
    backup_db()
    builder = (Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30)
               .write_timeout(30).pool_timeout(30).get_updates_connect_timeout(30)
               .get_updates_read_timeout(30).get_updates_write_timeout(30)
               .get_updates_pool_timeout(30))
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    app = builder.post_init(_post_init).build()
    app.add_handler(MessageHandler(filters.TEXT, router))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.run_polling(bootstrap_retries=-1, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
