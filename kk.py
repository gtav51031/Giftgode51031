import os
import telebot
import requests
import json
import time
import random
import threading
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify

# ============================================
# 🔐 إعدادات البوت الأساسية
# ============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8710044999:AAGsGCewdnb4sqrwE8dkRfQErKvLklpwP8M")
OWNER_ID = int(os.environ.get("OWNER_ID", 6366853738))
CHANNEL_TG = os.environ.get("CHANNEL_TG", "thaish12")
CHANNEL_YT = os.environ.get("CHANNEL_YT", "https://youtube.com/@tahish159?si=5ehTRVzB7WOnOj5s")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Rame124673_bot")
TOKEN_API = os.environ.get("TOKEN_API", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJndGF2NTEwMzFAZ21haWwuY29tIn0.LR0lbOdO6Qq5d_4X0jKUC6mx18PP1-w2ChvBXQTETw0")

INITIAL_POINTS = 50
ATTACK_DELAY = 0.1
YOUTUBE_VERIFY_KEY = "youtube_verified"
YOUTUBE_VERIFY_DAYS = 7
EXTRA_CHANNELS_FILE = "extra_channels.json"

# ============================================
# 👥 المستخدمون النشطون
# ============================================
active_users = {}

def update_user_activity(user_id):
    active_users[user_id] = time.time()

def get_active_users():
    now = time.time()
    active_list = []
    for uid, last_time in list(active_users.items()):
        if now - last_time < 300:
            active_list.append((uid, last_time))
        else:
            del active_users[uid]
    active_list.sort(key=lambda x: x[1], reverse=True)
    return active_list

def format_time_ago(timestamp):
    seconds = int(time.time() - timestamp)
    if seconds < 60:
        return f"منذ {seconds} ثانية"
    minutes = seconds // 60
    if minutes < 60:
        return f"منذ {minutes} دقيقة"
    hours = minutes // 60
    return f"منذ {hours} ساعة"

# ============================================
# 📂 ملفات البيانات
# ============================================
PROXIES_FILE = "proxies.txt"
DEAD_PROXIES_FILE = "dead_proxies.txt"
PAID_PROXIES_FILE = "paid_proxies.txt"  # ملف منفصل للبروكسيات المدفوعة
DATA_DIR = "user_data"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_user_file(user_id, filename):
    return os.path.join(DATA_DIR, f"{filename}_{user_id}.json")

# ============================================
# ✅ دالة تحميل النقاط التلقائية
# ============================================
def load_user_points(user_id):
    used = load_used_numbers(user_id)
    successes = len(used.get("success", []))
    correct_points = max(0, INITIAL_POINTS - successes)

    filepath = get_user_file(user_id, "points")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
            current_points = data.get("points", INITIAL_POINTS)
            if current_points != correct_points:
                save_user_points(user_id, correct_points)
            return correct_points
    else:
        save_user_points(user_id, correct_points)
        return correct_points

def save_user_points(user_id, points):
    filepath = get_user_file(user_id, "points")
    with open(filepath, "w") as f:
        json.dump({"points": points}, f)

def load_used_numbers(user_id):
    filepath = get_user_file(user_id, "used_numbers")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
            data.setdefault("success", [])
            data.setdefault("failed", [])
            data.setdefault("already", [])
            return data
    return {"success": [], "failed": [], "already": []}

def save_used_numbers(user_id, data):
    filepath = get_user_file(user_id, "used_numbers")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def load_user_sessions():
    filepath = os.path.join(DATA_DIR, "user_sessions.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_user_sessions(sessions):
    filepath = os.path.join(DATA_DIR, "user_sessions.json")
    with open(filepath, "w") as f:
        json.dump(sessions, f, indent=2)

def load_user_settings(user_id):
    filepath = get_user_file(user_id, "user_settings")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_user_settings(user_id, data):
    filepath = get_user_file(user_id, "user_settings")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

# ============================================
# 📦 دوال البروكسيات العامة + الخاصة
# ============================================
BACKUP_PROXIES = [
    "http://20.78.118.91:8561", "http://20.27.11.248:8561", "http://8.215.25.3:2080",
]

def load_proxies():
    """تحميل البروكسيات العامة (مع إصلاح التنسيق)"""
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, "r") as f:
            proxies = [p.strip() for p in f.readlines() if p.strip()]
            formatted = []
            for p in proxies:
                if not p.startswith("http://") and not p.startswith("https://"):
                    p = f"http://{p}"
                formatted.append(p)
            if formatted:
                return formatted
    return BACKUP_PROXIES.copy()

def save_proxies(proxies_list):
    with open(PROXIES_FILE, "w") as f:
        f.write("\n".join(proxies_list))

def load_paid_proxies():
    """تحميل البروكسيات المدفوعة (الخاصة)"""
    if os.path.exists(PAID_PROXIES_FILE):
        with open(PAID_PROXIES_FILE, "r") as f:
            proxies = [p.strip() for p in f.readlines() if p.strip()]
            formatted = []
            for p in proxies:
                if not p.startswith("http://") and not p.startswith("https://"):
                    p = f"http://{p}"
                formatted.append(p)
            return formatted
    return []

def save_paid_proxies(proxies_list):
    with open(PAID_PROXIES_FILE, "w") as f:
        f.write("\n".join(proxies_list))

def add_paid_proxy(proxy):
    """إضافة بروكسي مدفوع إلى القائمة الخاصة"""
    paid = load_paid_proxies()
    if proxy not in paid:
        paid.append(proxy)
        save_paid_proxies(paid)
        return True
    return False

def remove_paid_proxy(proxy):
    """حذف بروكسي مدفوع يدوياً"""
    paid = load_paid_proxies()
    if proxy in paid:
        paid.remove(proxy)
        save_paid_proxies(paid)
        return True
    return False

def load_all_proxies():
    """دمج البروكسيات العامة والخاصة (الخاصة أولاً)"""
    normal = load_proxies()
    paid = load_paid_proxies()
    all_proxies = paid + [p for p in normal if p not in paid]
    return all_proxies

def load_dead_proxies():
    if os.path.exists(DEAD_PROXIES_FILE):
        with open(DEAD_PROXIES_FILE, "r") as f:
            return [p.strip() for p in f.readlines() if p.strip()]
    return []

def save_dead_proxies(dead_list):
    with open(DEAD_PROXIES_FILE, "w") as f:
        f.write("\n".join(dead_list))

# ============================================
# 🎯 إعدادات الإحالات
# ============================================
BASE_URL = "https://giftcode.betelgeuse.app/api/referrer"
DEFAULT_START = 4084879

def send_referral(referral_code, user_id, proxy=None):
    params = {"referred_user_id": str(user_id), "ref_code": str(referral_code)}
    headers = {"Authorization": TOKEN_API, "User-Agent": "okhttp/5.3.2"}
    proxies_dict = {"http": proxy, "https": proxy} if proxy else None
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, proxies=proxies_dict, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return {"success": True, "gold": data.get("referred_gold", 0)}
            reason = data.get("reason", "")
            if "Zaten referanslı" in reason:
                return {"success": False, "reason": "already_referred"}
            elif "Geçersiz kullanıcı" in reason:
                return {"success": False, "reason": "invalid_user"}
            elif "Aynı IP" in reason:
                return {"success": False, "reason": "same_ip"}
            else:
                return {"success": False, "reason": reason}
        elif response.status_code == 429:
            return {"success": False, "reason": "rate_limited"}
        else:
            return {"success": False, "reason": f"HTTP_{response.status_code}"}
    except Exception as e:
        return {"success": False, "reason": "proxy_dead", "error": str(e)}

# ============================================
# 🗂️ دوال القنوات الإضافية
# ============================================
def load_extra_channels():
    if os.path.exists(EXTRA_CHANNELS_FILE):
        with open(EXTRA_CHANNELS_FILE, "r") as f:
            return json.load(f)
    return []

def save_extra_channels(channels):
    with open(EXTRA_CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2)

def is_subscribed_extra(user_id):
    extra_channels = load_extra_channels()
    for channel in extra_channels:
        try:
            chat_member = bot.get_chat_member(f"@{channel}", user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False, channel
        except:
            return False, channel
    return True, None

# ============================================
# 👤 نظام الإحالة الداخلي (المُصحح)
# ============================================
def load_referral_data():
    filepath = os.path.join(DATA_DIR, "referral_data.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_referral_data(data):
    filepath = os.path.join(DATA_DIR, "referral_data.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def get_referral_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"

def process_referral_new_user(new_user_id, referrer_id):
    if str(new_user_id) == str(referrer_id):
        return False, "❌ لا يمكنك إحالة نفسك!"

    if not is_subscribed_telegram(new_user_id):
        return False, "❌ يجب الاشتراك في قناة التلجرام أولاً!"

    referral_data = load_referral_data()

    if str(new_user_id) in referral_data.get("referred_users", {}):
        return False, "⚠️ هذا المستخدم تمت إحالته مسبقاً!"

    if str(referrer_id) not in referral_data.get("referrals", {}):
        referral_data.setdefault("referrals", {})[str(referrer_id)] = {
            "count": 0,
            "points_earned": 0,
            "users": []
        }

    referral_data["referrals"][str(referrer_id)]["count"] += 1
    referral_data["referrals"][str(referrer_id)]["points_earned"] += 10
    referral_data["referrals"][str(referrer_id)]["users"].append(str(new_user_id))
    referral_data.setdefault("referred_users", {})[str(new_user_id)] = str(referrer_id)
    save_referral_data(referral_data)

    current_points = load_user_points(referrer_id)
    save_user_points(referrer_id, current_points + 10)
    save_user_points(new_user_id, INITIAL_POINTS)

    return True, f"✅ تمت الإحالة بنجاح! حصلت على 10 نقاط."

def get_referral_stats(user_id):
    referral_data = load_referral_data()
    stats = referral_data.get("referrals", {}).get(str(user_id), {"count": 0, "points_earned": 0})
    return stats["count"], stats["points_earned"]

# ============================================
# 🤖 دوال البوت الأساسية
# ============================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
proxies = load_proxies()
paid_proxies = load_paid_proxies()
dead_proxies = load_dead_proxies()

def is_owner(user_id):
    return str(user_id) == str(OWNER_ID)

def is_subscribed_telegram(user_id):
    if is_owner(user_id):
        return True
    try:
        chat_member = bot.get_chat_member(f"@{CHANNEL_TG}", user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except:
        return False

def is_subscribed_youtube(user_id):
    if is_owner(user_id):
        return True
    data = load_user_settings(user_id)
    verified = data.get(YOUTUBE_VERIFY_KEY, False)
    if verified:
        last_verify = data.get("youtube_verify_date")
        if last_verify:
            try:
                days_passed = (datetime.now() - datetime.fromisoformat(last_verify)).days
                if days_passed > YOUTUBE_VERIFY_DAYS:
                    return False
            except:
                return False
    return verified

def check_all_subscriptions(user_id):
    if is_owner(user_id):
        return True, None
    if not is_subscribed_telegram(user_id):
        return False, "telegram"
    if not is_subscribed_youtube(user_id):
        return False, "youtube"
    extra_ok, channel = is_subscribed_extra(user_id)
    if not extra_ok:
        return False, f"extra_{channel}"
    return True, None

def get_user_setting(user_id, key, default=None):
    data = load_user_settings(user_id)
    return data.get(key, default)

def set_user_setting(user_id, key, value):
    data = load_user_settings(user_id)
    data[key] = value
    save_user_settings(user_id, data)

def translate_reason(reason):
    translations = {
        "already_referred": "هذا الرقم تمت إحالته مسبقاً بواسطة مستخدم آخر",
        "invalid_user": "الرقم غير صالح (ليس مستخدمًا في التطبيق)",
        "same_ip": "نفس عنوان IP تم استخدامه مؤخراً، يرجى تغيير البروكسي",
        "rate_limited": "تم تجاوز عدد الطلبات المسموح بها، انتظر قليلاً",
        "proxy_dead": "البروكسي لا يعمل، تم تخطيه",
        "already_used_success": "هذا الرقم سبق أن تمت إحالته بنجاح بواسطتك",
        "already_used_failed": "هذا الرقم سبق أن فشلت محاولة إحالته (لن نعيد المحاولة)",
        "already_used_already": "هذا الرقم محال مسبقاً (مسجل في القائمة)",
    }
    if reason.startswith("HTTP_"):
        return f"خطأ في الخادم (كود {reason.split('_')[1]})"
    return translations.get(reason, reason)

def process_referral(user_id, target, proxy):
    used_data = load_used_numbers(user_id)
    ref_code = get_user_setting(user_id, "referral_code", "4094894")
    if str(target) in used_data["success"]:
        return {"success": False, "reason": "already_used_success"}
    if str(target) in used_data["failed"]:
        return {"success": False, "reason": "already_used_failed"}
    if str(target) in used_data["already"]:
        return {"success": False, "reason": "already_used_already"}
    result = send_referral(ref_code, target, proxy)
    if result.get("success"):
        used_data["success"].append(str(target))
        save_used_numbers(user_id, used_data)
    elif result.get("reason") == "already_referred":
        used_data["already"].append(str(target))
        save_used_numbers(user_id, used_data)
    else:
        used_data["failed"].append(str(target))
        save_used_numbers(user_id, used_data)
    return result

attack_status = {}

def attack_loop(user_id, chat_id):
    global proxies, dead_proxies
    user_id_str = str(user_id)
    start_number = int(get_user_setting(user_id, "start_number", DEFAULT_START))
    current_number = start_number
    proxy_index = 0
    attempts = 0
    successes = 0
    skipped_proxies = []  # قائمة البروكسيات المتخطية مؤقتاً (خاصة)
    attack_status[user_id_str] = {"running": True, "number": current_number}
    
    while attack_status[user_id_str]["running"]:
        sub_ok, sub_type = check_all_subscriptions(user_id)
        if not sub_ok:
            if sub_type == "telegram":
                bot.send_message(chat_id, f"❌ يرجى الاشتراك في قناة التلجرام الأساسية: @{CHANNEL_TG}")
            elif sub_type == "youtube":
                bot.send_message(chat_id, f"❌ يرجى الاشتراك في قناة اليوتيوب: {CHANNEL_YT}")
            elif sub_type and sub_type.startswith("extra_"):
                channel = sub_type.replace("extra_", "")
                bot.send_message(chat_id, f"❌ يرجى الاشتراك في القناة الإضافية: @{channel}")
            else:
                bot.send_message(chat_id, "❌ يرجى الاشتراك في جميع القنوات المطلوبة.")
            break

        points = load_user_points(user_id)
        if points <= 0 and not is_owner(user_id):
            referral_link = get_referral_link(user_id)
            keyboard = InlineKeyboardMarkup()
            btn_link = InlineKeyboardButton("🔗 انسخ رابط الإحالة", callback_data="my_referral")
            keyboard.add(btn_link)
            bot.send_message(chat_id,
                f"⚠️ **لقد نفدت نقاطك!**\n\n"
                f"📢 شارك رابط الإحالة الخاص بك مع أصدقائك:\n"
                f"`{referral_link}`\n\n"
                f"💡 كل شخص ينضم من خلال هذا الرابط **ويشترك في قناتي**، ستحصل على 10 نقاط!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            break

        # تحميل جميع البروكسيات (مع الخاصة)
        all_proxies = load_all_proxies()
        if not all_proxies:
            bot.send_message(chat_id, "❌ لا يوجد بروكسيات! تم إيقاف الهجوم.")
            break

        # اختيار بروكسي (تجنب التالف والمتخطي)
        proxy = None
        for _ in range(len(all_proxies) * 3):
            candidate = all_proxies[proxy_index % len(all_proxies)]
            proxy_index += 1
            if candidate in dead_proxies or candidate in skipped_proxies:
                continue
            proxy = candidate
            break

        if not proxy:
            # إذا نفدت البروكسيات، حاول إعادة استخدام المتخطية
            if skipped_proxies:
                proxy = skipped_proxies.pop(0)
                bot.send_message(chat_id, f"🔄 إعادة استخدام بروكسي متخطي: {proxy}")
            else:
                bot.send_message(chat_id, "⚠️ جميع البروكسيات تالفة أو متخطية! قم بإضافة بروكسيات جديدة.")
                break

        target = str(current_number)
        current_number += 1
        attack_status[user_id_str]["number"] = current_number
        attempts += 1
        bot.send_message(chat_id, f"⏳ جاري محاولة #{attempts} على الرقم {target}...")
        bot.send_message(chat_id, f"🌐 استخدام بروكسي: {proxy}")
        
        result = process_referral(user_id, target, proxy)
        
        if result.get("success"):
            successes += 1
            gold = result.get("gold", 0)
            new_points = load_user_points(user_id) - 1
            save_user_points(user_id, new_points)
            bot.send_message(chat_id, f"🎉 تم الإهداء من قبل هيمو! (+{gold} GP)\n💎 نقاطك المتبقية: {new_points}")
            sessions = load_user_sessions()
            user_data = sessions.get(str(user_id), {})
            first_name = user_data.get("first_name", "مستخدم")
            bot.send_message(OWNER_ID, f"✅ نجاح! المستخدم {first_name} -> {target} | +{gold} GP")
        else:
            reason = result.get("reason", "غير معروف")
            arabic_reason = translate_reason(reason)
            if reason in ["proxy_dead", "same_ip", "rate_limited"]:
                bot.send_message(chat_id, f"⚠️ {arabic_reason}، ننتقل للتالي")
                
                # التحقق: هل هذا بروكسي مدفوع (يحتوي على @ أو موجود في قائمة المدفوعة)؟
                is_paid = '@' in proxy if proxy else False
                # أو التحقق من وجوده في قائمة المدفوعة
                if not is_paid:
                    paid_list = load_paid_proxies()
                    is_paid = proxy in paid_list if proxy else False
                
                if is_paid:
                    # بروكسي مدفوع: لا نحذفه، فقط نتخطاه مؤقتاً
                    if proxy and proxy not in skipped_proxies:
                        skipped_proxies.append(proxy)
                    bot.send_message(chat_id, f"⏭️ تم تخطي البروكسي الخاص مؤقتاً: {proxy}")
                else:
                    # بروكسي عادي: نحذفه نهائياً
                    if proxy and proxy not in dead_proxies:
                        dead_proxies.append(proxy)
                        # حذفه من القائمة النشطة العامة
                        if proxy in proxies:
                            proxies.remove(proxy)
                            save_proxies(proxies)
                    bot.send_message(chat_id, f"🗑️ تم حذف البروكسي العادي: {proxy}")
                
                current_number -= 1
                continue
            elif reason in ["already_used_success", "already_used_failed", "already_used_already"]:
                bot.send_message(chat_id, f"ℹ️ {arabic_reason} (تم التخطي)")
                continue
            else:
                bot.send_message(chat_id, f"😞 فشلت المحاولة: {arabic_reason}")
        time.sleep(ATTACK_DELAY)
        if attempts % 10 == 0:
            used = load_used_numbers(user_id)
            bot.send_message(chat_id,
                f"📊 إحصاءات: {successes} نجاح من {attempts} محاولة | "
                f"آخر رقم: {target} | نجاح كلي: {len(used['success'])}"
            )
    attack_status[user_id_str]["running"] = False
    bot.send_message(chat_id, f"⏹️ تم إيقاف الهجوم. إجمالي النجاحات: {successes} من {attempts} محاولة.")

# ============================================
# 📨 أوامر المستخدمين
# ============================================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "مستخدم"

    update_user_activity(user_id)

    referrer_id = None
    if message.text and message.text.startswith('/start'):
        parts = message.text.split()
        if len(parts) > 1 and parts[1].isdigit():
            referrer_id = int(parts[1])

    sessions = load_user_sessions()
    user_id_str = str(user_id)
    if user_id_str not in sessions:
        sessions[user_id_str] = {
            "first_name": first_name,
            "username": message.from_user.username or "",
            "joined": datetime.now().isoformat()
        }
        save_user_sessions(sessions)

    sub_ok, sub_type = check_all_subscriptions(user_id)
    referral_data = load_referral_data()

    if referrer_id and user_id_str not in referral_data.get("referred_users", {}):
        if not is_subscribed_telegram(user_id):
            keyboard = InlineKeyboardMarkup(row_width=1)
            btn_tg = InlineKeyboardButton("📢 اشترك في قناة التلجرام", url=f"https://t.me/{CHANNEL_TG}")
            btn_yt = InlineKeyboardButton("🎬 اشترك في يوتيوب", url=CHANNEL_YT)
            btn_extra = InlineKeyboardButton("✅ اشتركت واريد تأكيد الإحالة", callback_data=f"confirm_referral_{referrer_id}")
            keyboard.add(btn_tg, btn_yt)
            keyboard.add(btn_extra)
            bot.reply_to(message,
                f"👋 أهلاً {first_name}!\n\n"
                f"🔗 تمت دعوتك بواسطة مستخدم آخر.\n"
                f"🔒 **يجب الاشتراك في قناة التلجرام أولاً** لتأكيد الإحالة والحصول على المكافآت.\n"
                f"بعد الاشتراك، اضغط على زر تأكيد الإحالة.",
                reply_markup=keyboard
            )
            return
        else:
            success, msg = process_referral_new_user(user_id, referrer_id)
            bot.reply_to(message, f"🔗 تمت الإحالة!\n\n{msg}")

    if not sub_ok:
        keyboard = InlineKeyboardMarkup(row_width=1)
        if sub_type == "telegram":
            btn_tg = InlineKeyboardButton("📢 اشترك في القناة الأساسية", url=f"https://t.me/{CHANNEL_TG}")
            keyboard.add(btn_tg)
        elif sub_type == "youtube":
            btn_yt = InlineKeyboardButton("🎬 اشترك في يوتيوب", url=CHANNEL_YT)
            btn_verify = InlineKeyboardButton("✅ لقد اشتركت (تأكيد)", callback_data="verify_youtube")
            keyboard.add(btn_yt)
            keyboard.add(btn_verify)
        elif sub_type and sub_type.startswith("extra_"):
            channel = sub_type.replace("extra_", "")
            btn_extra = InlineKeyboardButton(f"📢 اشترك في @{channel}", url=f"https://t.me/{channel}")
            keyboard.add(btn_extra)
        else:
            btn_tg = InlineKeyboardButton("📢 اشترك في القناة الأساسية", url=f"https://t.me/{CHANNEL_TG}")
            btn_yt = InlineKeyboardButton("🎬 اشترك في يوتيوب", url=CHANNEL_YT)
            keyboard.add(btn_tg)
            keyboard.add(btn_yt)
            extra_channels = load_extra_channels()
            for ch in extra_channels:
                btn_extra = InlineKeyboardButton(f"📢 اشترك في @{ch}", url=f"https://t.me/{ch}")
                keyboard.add(btn_extra)

        btn_check = InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")
        keyboard.add(btn_check)

        bot.reply_to(message,
            f"👋 أهلاً {first_name}!\n\n"
            f"🔒 **يجب الاشتراك في جميع القنوات المطلوبة** أولاً.\n"
            f"بعد الاشتراك، اضغط على زر التحقق.",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_set_ref = InlineKeyboardButton("🔑 تعيين كود الإحالة", callback_data="set_referral")
    btn_set_start = InlineKeyboardButton("🔢 تعيين رقم البداية", callback_data="set_start")
    btn_start_attack = InlineKeyboardButton("▶️ بدء الهجوم", callback_data="start_attack")
    btn_stop_attack = InlineKeyboardButton("⏹️ إيقاف الهجوم", callback_data="stop_attack")
    btn_status = InlineKeyboardButton("📊 الحالة", callback_data="status")
    btn_referral = InlineKeyboardButton("🔗 رابط الإحالة الخاص بي", callback_data="my_referral")
    btn_my_paid_proxies = InlineKeyboardButton("📋 بروكسياتي الخاصة", callback_data="my_paid_proxies")  # للمستخدمين العاديين
    keyboard.add(btn_set_ref, btn_set_start)
    keyboard.add(btn_start_attack, btn_stop_attack)
    keyboard.add(btn_status, btn_referral)
    keyboard.add(btn_my_paid_proxies)

    if is_owner(user_id):
        btn_owner = InlineKeyboardButton("👑 أوامر المالك", callback_data="owner_commands")
        keyboard.add(btn_owner)

    ref_code = get_user_setting(user_id, "referral_code", "غير محدد")
    start_num = get_user_setting(user_id, "start_number", DEFAULT_START)
    points = load_user_points(user_id)
    used = load_used_numbers(user_id)
    referral_count, referral_points = get_referral_stats(user_id)

    bot.reply_to(message,
        f"✅ مرحباً {first_name}!\n\n"
        f"📋 الإعدادات الحالية:\n"
        f"🔑 كود الإحالة: {ref_code}\n"
        f"🔢 رقم البداية: {start_num}\n"
        f"💎 النقاط: {points}\n"
        f"🔗 إحالاتك: {referral_count} (ربحت {referral_points} نقطة)\n"
        f"✅ نجاح: {len(used['success'])}\n"
        f"⚠️ محال: {len(used['already'])}\n"
        f"❌ فشل: {len(used['failed'])}\n"
        f"🌐 بروكسيات عامة: {len(load_proxies())}\n"
        f"🔒 بروكسيات خاصة: {len(load_paid_proxies())}\n\n"
        f"اضغط على الزر المناسب:",
        reply_markup=keyboard
    )

@bot.message_handler(commands=['get_my_id'])
def get_my_id(message):
    user_id = message.from_user.id
    bot.reply_to(message,
        f"🆔 **معرفك هو:** `{user_id}`\n\n"
        f"🔑 **OWNER_ID في الكود:** `{OWNER_ID}`\n"
        f"📌 **هل هما متطابقان؟** {'✅ نعم' if str(user_id) == str(OWNER_ID) else '❌ لا'}\n\n"
        f"إذا كانا غير متطابقين، غيّر `OWNER_ID` في الكود إلى `{user_id}`.",
        parse_mode="Markdown"
    )

# ============================================
# 👑 عرض أوامر المالك (أزرار)
# ============================================
def show_owner_menu(message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_add_proxy = InlineKeyboardButton("➕ إضافة بروكسي", callback_data="owner_add_proxy")
    btn_add_paid_proxy = InlineKeyboardButton("🔒 إضافة بروكسي خاص", callback_data="owner_add_paid_proxy")
    btn_bulk_proxy = InlineKeyboardButton("📦 إضافة بروكسيات (دفعة)", callback_data="owner_add_bulk")
    btn_refresh = InlineKeyboardButton("🔄 تحديث البروكسيات", callback_data="owner_refresh")
    btn_list = InlineKeyboardButton("📋 عرض البروكسيات", callback_data="owner_list")
    btn_check = InlineKeyboardButton("🔍 فحص البروكسيات", callback_data="owner_check")
    btn_clear_dead = InlineKeyboardButton("🗑️ حذف التالفة", callback_data="owner_clear_dead")
    btn_delete_paid = InlineKeyboardButton("🗑️ حذف بروكسي خاص (يدوياً)", callback_data="owner_delete_paid")
    btn_stats = InlineKeyboardButton("📊 الإحصائيات", callback_data="owner_stats")
    btn_clear_sessions = InlineKeyboardButton("🧹 مسح الجلسات", callback_data="owner_clear_sessions")
    btn_help = InlineKeyboardButton("❓ المساعدة", callback_data="owner_help")
    btn_add_channel = InlineKeyboardButton("➕ إضافة قناة إجبارية", callback_data="owner_add_channel")
    btn_list_channels = InlineKeyboardButton("📋 عرض القنوات الإجبارية", callback_data="owner_list_channels")
    btn_remove_channel = InlineKeyboardButton("🗑️ حذف قناة إجبارية", callback_data="owner_remove_channel")
    btn_broadcast = InlineKeyboardButton("📢 بث رسالة للجميع", callback_data="owner_broadcast")
    btn_active = InlineKeyboardButton("👥 المستخدمون النشطون", callback_data="owner_active_users")
    btn_referral_stats = InlineKeyboardButton("📊 إحصائيات الإحالات", callback_data="owner_referral_stats")
    btn_reset_points = InlineKeyboardButton("🔄 إعادة تعيين النقاط للجميع", callback_data="owner_reset_points")

    keyboard.add(btn_add_proxy, btn_add_paid_proxy)
    keyboard.add(btn_bulk_proxy, btn_refresh)
    keyboard.add(btn_list, btn_check)
    keyboard.add(btn_clear_dead, btn_delete_paid)
    keyboard.add(btn_stats, btn_clear_sessions)
    keyboard.add(btn_add_channel, btn_list_channels)
    keyboard.add(btn_remove_channel, btn_broadcast)
    keyboard.add(btn_active, btn_referral_stats)
    keyboard.add(btn_reset_points)
    keyboard.add(btn_help)

    bot.reply_to(message, "👑 **قائمة أوامر المالك** (اختر الأمر):", reply_markup=keyboard, parse_mode="Markdown")

# ============================================
# 🖱️ معالجة الأزرار
# ============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    global proxies, dead_proxies, paid_proxies
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    update_user_activity(user_id)

    # ========== تأكيد الإحالة بعد الاشتراك ==========
    if call.data.startswith("confirm_referral_"):
        referrer_id = int(call.data.replace("confirm_referral_", ""))
        if not is_subscribed_telegram(user_id):
            bot.answer_callback_query(call.id, "❌ اشترك في قناة التلجرام أولاً!", show_alert=True)
            return
        success, msg = process_referral_new_user(user_id, referrer_id)
        if success:
            bot.answer_callback_query(call.id, "✅ تمت الإحالة بنجاح! حصلت على 10 نقاط.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"❌ {msg}", show_alert=True)
        bot.send_message(chat_id, f"🔗 نتيجة الإحالة:\n\n{msg}")
        start_command(call.message)
        return

    # ========== أزرار المالك ==========
    if call.data == "owner_commands":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ هذا الزر للمالك فقط!", show_alert=True)
            return
        bot.answer_callback_query(call.id, "📋 جاري عرض الأوامر...")
        show_owner_menu(call.message)
        return

    if call.data == "owner_add_channel":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل معرف القناة (بدون @):")
        msg = bot.send_message(chat_id, "📢 أرسل معرف القناة التي تريد إضافتها (مثال: mychannel) :")
        bot.register_next_step_handler(msg, add_channel_step)
        return

    if call.data == "owner_list_channels":
        if not is_owner(user_id): return
        channels = load_extra_channels()
        if not channels:
            bot.reply_to(call.message, "📭 لا توجد قنوات إضافية حالياً.")
        else:
            text = "📋 **القنوات الإجبارية الإضافية:**\n\n"
            for i, ch in enumerate(channels, 1):
                text += f"{i}. @{ch}\n"
            bot.reply_to(call.message, text, parse_mode="Markdown")
        return

    if call.data == "owner_remove_channel":
        if not is_owner(user_id): return
        channels = load_extra_channels()
        if not channels:
            bot.reply_to(call.message, "📭 لا توجد قنوات لحذفها.")
            return
        keyboard = InlineKeyboardMarkup()
        for ch in channels:
            keyboard.add(InlineKeyboardButton(f"🗑️ حذف @{ch}", callback_data=f"remove_channel_{ch}"))
        keyboard.add(InlineKeyboardButton("🔙 إلغاء", callback_data="owner_commands"))
        bot.reply_to(call.message, "اختر القناة التي تريد حذفها:", reply_markup=keyboard)
        return

    if call.data.startswith("remove_channel_"):
        if not is_owner(user_id): return
        channel = call.data.replace("remove_channel_", "")
        channels = load_extra_channels()
        if channel in channels:
            channels.remove(channel)
            save_extra_channels(channels)
            bot.answer_callback_query(call.id, f"✅ تم حذف القناة @{channel}")
            bot.reply_to(call.message, f"✅ تم حذف القناة: @{channel}")
        else:
            bot.answer_callback_query(call.id, "⚠️ هذه القناة غير موجودة")
        return

    if call.data == "owner_broadcast":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل الرسالة التي تريد بثها:")
        msg = bot.send_message(chat_id, "📢 أرسل النص الذي تريد إرساله لجميع المستخدمين:")
        bot.register_next_step_handler(msg, broadcast_step)
        return

    if call.data == "owner_add_proxy":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل البروكسي العام الجديد:")
        msg = bot.send_message(chat_id, "🌐 أرسل البروكسي العام (مثال: 192.168.1.1:8080):")
        bot.register_next_step_handler(msg, add_proxy_step)
        return

    if call.data == "owner_add_paid_proxy":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل البروكسي الخاص (المدفوع):")
        msg = bot.send_message(chat_id, "🔒 أرسل البروكسي المدفوع بصيغة `user:pass@IP:PORT` (مثال: `user:pass@192.168.1.1:8080`)")
        bot.register_next_step_handler(msg, add_paid_proxy_step)
        return

    if call.data == "owner_add_bulk":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "📦 أرسل قائمة البروكسيات:")
        msg = bot.send_message(chat_id, "🌐 أرسل قائمة البروكسيات (كل بروكسي في سطر) أو أرسل ملف نصي:")
        bot.register_next_step_handler(msg, process_bulk_proxies)
        return

    if call.data == "owner_refresh":
        if not is_owner(user_id): return
        proxies = load_proxies()
        paid_proxies = load_paid_proxies()
        bot.answer_callback_query(call.id, f"✅ تم التحديث! العامة: {len(proxies)} | الخاصة: {len(paid_proxies)}", show_alert=True)
        return

    if call.data == "owner_list":
        if not is_owner(user_id): return
        all_proxies = load_all_proxies()
        if not all_proxies:
            bot.reply_to(call.message, "📭 لا يوجد بروكسيات.")
            return
        text = "🌐 البروكسيات:\n\n"
        # عرض الخاصة أولاً
        paid = load_paid_proxies()
        if paid:
            text += "🔒 **بروكسيات خاصة:**\n"
            for i, p in enumerate(paid, 1):
                # إخفاء الباسورد في العرض
                if '@' in p:
                    parts = p.replace('http://', '').split('@')
                    if len(parts) == 2:
                        user_pass = parts[0].split(':')
                        if len(user_pass) == 2:
                            display = f"{user_pass[0]}:****@{parts[1]}"
                            text += f"   {i}. `{display}`\n"
                        else:
                            text += f"   {i}. `{p}`\n"
                    else:
                        text += f"   {i}. `{p}`\n"
                else:
                    text += f"   {i}. `{p}`\n"
            text += "\n"
        
        normal = load_proxies()
        if normal:
            text += "🌐 **بروكسيات عامة:**\n"
            for i, p in enumerate(normal, 1):
                text += f"   {i}. `{p}`\n"
        bot.reply_to(call.message, text, parse_mode="Markdown")
        return

    if call.data == "owner_check":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "🔍 جاري فحص البروكسيات...")
        check_proxies(call.message)
        return

    if call.data == "owner_clear_dead":
        if not is_owner(user_id): return
        if not dead_proxies:
            bot.answer_callback_query(call.id, "📭 لا يوجد بروكسيات تالفة!", show_alert=True)
            return
        dead_proxies = []
        save_dead_proxies([])
        bot.answer_callback_query(call.id, "🗑️ تم حذف جميع البروكسيات التالفة!", show_alert=True)
        return

    # ========== حذف بروكسي خاص يدوياً (للمالك) ==========
    if call.data == "owner_delete_paid":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ هذا الزر للمالك فقط!", show_alert=True)
            return
        paid = load_paid_proxies()
        if not paid:
            bot.reply_to(call.message, "📭 لا يوجد بروكسيات خاصة لحذفها.")
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        for p in paid:
            # عرض مختصر
            display = p
            if '@' in p:
                parts = p.replace('http://', '').split('@')
                if len(parts) == 2:
                    user_pass = parts[0].split(':')
                    if len(user_pass) == 2:
                        display = f"{user_pass[0]}:****@{parts[1]}"
            keyboard.add(InlineKeyboardButton(f"🗑️ حذف {display}", callback_data=f"delete_paid_{p}"))
        keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="owner_commands"))
        bot.reply_to(call.message, "اختر البروكسي الخاص الذي تريد حذفه نهائياً:", reply_markup=keyboard)
        return

    if call.data.startswith("delete_paid_"):
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ للمالك فقط!", show_alert=True)
            return
        proxy_to_delete = call.data.replace("delete_paid_", "")
        # استعادة البروكسي الأصلي (لأنه قد يكون تم تشفيره في الزر)
        paid = load_paid_proxies()
        # قد يكون هناك اختلاف في التنسيق بسبب إضافة http://
        matching_proxies = [p for p in paid if p == proxy_to_delete or p.replace('http://', '') == proxy_to_delete]
        if matching_proxies:
            original = matching_proxies[0]
            paid.remove(original)
            save_paid_proxies(paid)
            # حذفه من القائمة النشطة أيضاً
            if original in proxies:
                proxies.remove(original)
                save_proxies(proxies)
            bot.answer_callback_query(call.id, f"✅ تم حذف البروكسي الخاص: {original}", show_alert=True)
            bot.reply_to(call.message, f"✅ تم حذف البروكسي الخاص:\n`{original}`")
        else:
            bot.answer_callback_query(call.id, "⚠️ هذا البروكسي غير موجود", show_alert=True)
        return

    # ========== عرض بروكسيات المستخدم الخاصة ==========
    if call.data == "my_paid_proxies":
        # نعرض البروكسيات الخاصة بكل المستخدمين (لأن المستخدم العادي لا يملك قائمة خاصة به)
        # لكن يمكننا عرض قائمة المدفوعة التي أضافها المالك (لأن المستخدمين لا يضيفونها)
        # سأقوم بعرض البروكسيات الخاصة كاملة مع إخفاء الباسورد
        paid = load_paid_proxies()
        if not paid:
            bot.reply_to(call.message, "📭 لا يوجد بروكسيات خاصة حالياً.")
            return
        text = "🔒 **البروكسيات الخاصة المتاحة:**\n\n"
        for i, p in enumerate(paid, 1):
            if '@' in p:
                parts = p.replace('http://', '').split('@')
                if len(parts) == 2:
                    user_pass = parts[0].split(':')
                    if len(user_pass) == 2:
                        display = f"{user_pass[0]}:****@{parts[1]}"
                        text += f"{i}. `{display}`\n"
                    else:
                        text += f"{i}. `{p}`\n"
                else:
                    text += f"{i}. `{p}`\n"
            else:
                text += f"{i}. `{p}`\n"
        bot.reply_to(call.message, text, parse_mode="Markdown")
        return

    # ========== إحصائيات عامة ==========
    if call.data == "owner_stats":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ هذا الزر للمالك فقط!", show_alert=True)
            return

        loading_msg = bot.send_message(chat_id, "📊 **جاري تحميل الإحصائيات...** يرجى الانتظار.")

        def send_stats():
            try:
                sessions = load_user_sessions()
                if not sessions:
                    bot.edit_message_text(
                        "📊 **لا يوجد مستخدمون مسجلون حتى الآن.**\n\nقم بدعوة أصدقائك لاستخدام البوت عن طريق إرسال `/start`.",
                        chat_id=chat_id,
                        message_id=loading_msg.message_id,
                        parse_mode='HTML'
                    )
                    return

                text = "<b>📊 الإحصائيات العامة</b>\n\n"
                total_users = len(sessions)
                active = 0
                total_success = 0
                users_data = []

                for user_id_str, data in sessions.items():
                    uid = int(user_id_str)
                    sub_ok, _ = check_all_subscriptions(uid)
                    if sub_ok:
                        active += 1

                    username = data.get("username", "غير معروف")
                    first_name = data.get("first_name", "مستخدم")
                    points = load_user_points(uid)
                    used = load_used_numbers(uid)
                    successes = len(used["success"])
                    total_success += successes

                    users_data.append({
                        "first_name": first_name,
                        "username": username,
                        "points": points,
                        "successes": successes
                    })

                users_data.sort(key=lambda x: x["successes"], reverse=True)

                for i, user in enumerate(users_data[:20], 1):
                    text += f"{i}. 👤 {user['first_name']} (@{user['username']})\n"
                    text += f"   💎 النقاط: {user['points']} | ✅ نجاح: {user['successes']}\n"
                    text += "   -------------------------\n"

                if len(users_data) > 20:
                    text += f"\n... وعرض {len(users_data) - 20} مستخدم آخر (الأقل إحالات).\n"

                text += f"\n<b>📊 الملخص:</b>\n"
                text += f"👥 إجمالي المستخدمين: {total_users}\n"
                text += f"🟢 النشطين (مشتركين): {active}\n"
                text += f"🔴 غير النشطين (غير مشتركين): {total_users - active}\n"
                text += f"✅ إجمالي الإحالات الناجحة: {total_success}\n"
                text += f"🌐 بروكسيات عامة: {len(load_proxies())}\n"
                text += f"🔒 بروكسيات خاصة: {len(load_paid_proxies())}\n"
                text += f"💀 تالفة: {len(dead_proxies)}\n"
                extra = load_extra_channels()
                text += f"📢 قنوات إضافية: {len(extra)}"

                if len(text) > 4000:
                    bot.edit_message_text(
                        text[:4000],
                        chat_id=chat_id,
                        message_id=loading_msg.message_id,
                        parse_mode='HTML'
                    )
                    remaining = text[4000:]
                    for i in range(0, len(remaining), 4000):
                        bot.send_message(chat_id, remaining[i:i+4000], parse_mode='HTML')
                else:
                    bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=loading_msg.message_id,
                        parse_mode='HTML'
                    )

                print(f"✅ تم إرسال الإحصائيات بنجاح. عدد المستخدمين: {total_users}")
            except Exception as e:
                print(f"❌ خطأ في الإحصائيات: {e}")
                try:
                    bot.edit_message_text(
                        f"⚠️ حدث خطأ أثناء جمع الإحصائيات:\n{str(e)[:200]}",
                        chat_id=chat_id,
                        message_id=loading_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    bot.send_message(chat_id, f"⚠️ حدث خطأ: {str(e)[:100]}")

        threading.Thread(target=send_stats, daemon=True).start()
        return

    # ========== ✅ المستخدمون النشطون ==========
    if call.data == "owner_active_users":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ هذا الزر للمالك فقط!", show_alert=True)
            return

        active_list = get_active_users()

        if not active_list:
            bot.reply_to(call.message, "👥 **لا يوجد مستخدمون نشطون حالياً.**\n\n(النشاط يُحسب خلال آخر 5 دقائق)")
            return

        text = f"👥 **المستخدمون النشطون حالياً:** ({len(active_list)})\n\n"
        for uid, last_time in active_list:
            sessions = load_user_sessions()
            user_data = sessions.get(str(uid), {})
            name = user_data.get("first_name", "مستخدم")
            username = user_data.get("username", "")
            time_ago = format_time_ago(last_time)
            if username:
                text += f"• {name} (@{username}) - نشط {time_ago}\n"
            else:
                text += f"• {name} - نشط {time_ago}\n"

        bot.reply_to(call.message, text, parse_mode="Markdown")
        return

    # ========== عرض رابط الإحالة الخاص بالمستخدم ==========
    if call.data == "my_referral":
        referral_link = get_referral_link(user_id)
        count, points = get_referral_stats(user_id)
        text = (
            f"🔗 **رابط الإحالة الخاص بك:**\n"
            f"`{referral_link}`\n\n"
            f"📌 **إحصائيات إحالاتك:**\n"
            f"👥 عدد الإحالات: {count}\n"
            f"💎 النقاط المكتسبة: {points}\n\n"
            f"💡 انشر هذا الرابط لأصدقائك، كل شخص ينضم من خلال الرابط **ويشترك في قناتي**، ستحصل على 10 نقاط!"
        )
        bot.reply_to(call.message, text, parse_mode="Markdown")
        return

    if call.data == "owner_clear_sessions":
        if not is_owner(user_id): return
        save_user_sessions({})
        bot.answer_callback_query(call.id, "🧹 تم مسح جميع الجلسات!", show_alert=True)
        return

    if call.data == "owner_help":
        if not is_owner(user_id): return
        help_text = (
            "👑 **أوامر المالك:**\n\n"
            "🔹 إضافة بروكسي (زر)\n"
            "🔹 إضافة بروكسي خاص (مدفوع) (زر)\n"
            "🔹 إضافة بروكسيات دفعة (زر)\n"
            "🔹 تحديث البروكسيات (زر)\n"
            "🔹 عرض البروكسيات (زر)\n"
            "🔹 فحص البروكسيات (زر)\n"
            "🔹 حذف التالفة (زر)\n"
            "🔹 حذف بروكسي خاص يدوياً (زر)\n"
            "🔹 الإحصائيات (زر)\n"
            "🔹 مسح الجلسات (زر)\n"
            "🔹 إضافة قناة إجبارية (زر)\n"
            "🔹 عرض القنوات الإجبارية (زر)\n"
            "🔹 حذف قناة إجبارية (زر)\n"
            "🔹 بث رسالة للجميع (زر)\n"
            "🔹 المستخدمون النشطون (زر)\n"
            "🔹 إحصائيات الإحالات (زر)\n"
            "🔹 إعادة تعيين النقاط للجميع (زر)\n\n"
            "📌 الأوامر النصية:\n"
            "/start - القائمة الرئيسية\n"
            "/get_my_id - معرفة رقمك"
        )
        bot.reply_to(call.message, help_text, parse_mode="Markdown")
        return

    # ========== أزرار التحقق من الاشتراك ==========
    if call.data == "check_sub":
        sub_ok, sub_type = check_all_subscriptions(user_id)
        if sub_ok:
            bot.answer_callback_query(call.id, "✅ تم التحقق! جاري فتح البوت...", show_alert=True)
            start_command(call.message)
        else:
            if sub_type == "telegram":
                bot.answer_callback_query(call.id, f"❌ اشترك في قناة التلجرام الأساسية: @{CHANNEL_TG}", show_alert=True)
            elif sub_type == "youtube":
                bot.answer_callback_query(call.id, "❌ اشترك في قناة اليوتيوب ثم اضغط على زر التأكيد!", show_alert=True)
            elif sub_type and sub_type.startswith("extra_"):
                channel = sub_type.replace("extra_", "")
                bot.answer_callback_query(call.id, f"❌ اشترك في القناة الإضافية: @{channel}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ اشترك في جميع القنوات المطلوبة!", show_alert=True)
        return

    if call.data == "verify_youtube":
        if is_subscribed_telegram(user_id):
            set_user_setting(user_id, YOUTUBE_VERIFY_KEY, True)
            set_user_setting(user_id, "youtube_verify_date", datetime.now().isoformat())
            bot.answer_callback_query(call.id, "✅ تم تأكيد اشتراكك في يوتيوب!", show_alert=True)
            start_command(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ اشترك في قناة التلجرام أولاً!", show_alert=True)
        return

    # ========== أزرار المستخدمين ==========
    if call.data == "set_referral":
        bot.answer_callback_query(call.id, "✏️ أرسل كود الإحالة الجديد:")
        msg = bot.send_message(chat_id, "🔑 أرسل كود الإحالة (يمكن أن يحتوي على أرقام وحروف):")
        bot.register_next_step_handler(msg, set_referral_step, user_id)
        return

    if call.data == "set_start":
        bot.answer_callback_query(call.id, "✏️ أرسل رقم البداية الجديد:")
        msg = bot.send_message(chat_id, "🔢 أرسل رقم البداية (أرقام فقط):")
        bot.register_next_step_handler(msg, set_start_step, user_id)
        return

    if call.data == "start_attack":
        points = load_user_points(user_id)
        if not is_owner(user_id) and points <= 0:
            referral_link = get_referral_link(user_id)
            keyboard = InlineKeyboardMarkup()
            btn_link = InlineKeyboardButton("🔗 انسخ رابط الإحالة", callback_data="my_referral")
            keyboard.add(btn_link)
            bot.send_message(chat_id,
                f"⚠️ **لقد نفدت نقاطك!**\n\n"
                f"📢 شارك رابط الإحالة الخاص بك مع أصدقائك:\n"
                f"`{referral_link}`\n\n"
                f"💡 كل شخص ينضم من خلال هذا الرابط **ويشترك في قناتي**، ستحصل على 10 نقاط!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "⚠️ نقاطك 0! شارك رابط الإحالة للحصول على نقاط جديدة.", show_alert=True)
            return

        user_id_str = str(user_id)
        if user_id_str in attack_status and attack_status[user_id_str].get("running", False):
            bot.answer_callback_query(call.id, "⚠️ الهجوم يعمل بالفعل!", show_alert=True)
            return
        ref_code = get_user_setting(user_id, "referral_code", None)
        if not ref_code:
            bot.answer_callback_query(call.id, "❌ يرجى تعيين كود الإحالة أولاً!", show_alert=True)
            return
        bot.answer_callback_query(call.id, "▶️ بدء الهجوم...")
        attack_status[user_id_str] = {"running": True, "number": get_user_setting(user_id, "start_number", DEFAULT_START)}
        thread = threading.Thread(target=attack_loop, args=(user_id, chat_id))
        thread.daemon = True
        thread.start()
        attack_status[user_id_str]["thread"] = thread
        bot.send_message(chat_id, "🚀 تم بدء الهجوم التلقائي! سيتم إرسال التحديثات هنا.")
        return

    if call.data == "stop_attack":
        user_id_str = str(user_id)
        if user_id_str in attack_status and attack_status[user_id_str].get("running", False):
            attack_status[user_id_str]["running"] = False
            bot.answer_callback_query(call.id, "⏹️ جاري إيقاف الهجوم...", show_alert=True)
            bot.send_message(chat_id, "⏹️ تم إيقاف الهجوم.")
        else:
            bot.answer_callback_query(call.id, "⚠️ لا يوجد هجوم نشط!", show_alert=True)
        return

    if call.data == "status":
        user_id_str = str(user_id)
        ref_code = get_user_setting(user_id, "referral_code", "غير محدد")
        start_num = get_user_setting(user_id, "start_number", DEFAULT_START)
        running = attack_status.get(user_id_str, {}).get("running", False)
        current_num = attack_status.get(user_id_str, {}).get("number", start_num)
        points = load_user_points(user_id)
        used = load_used_numbers(user_id)
        bot.answer_callback_query(call.id, "📊 جاري عرض الحالة...")
        bot.send_message(chat_id,
            f"📊 الحالة الحالية:\n\n"
            f"🔑 كود الإحالة: {ref_code}\n"
            f"🔢 رقم البداية: {start_num}\n"
            f"📌 الرقم التالي: {current_num}\n"
            f"🔄 حالة الهجوم: {'▶️ يعمل' if running else '⏹️ متوقف'}\n"
            f"💎 النقاط: {points}\n"
            f"✅ نجاح: {len(used['success'])}\n"
            f"⚠️ محال: {len(used['already'])}\n"
            f"❌ فشل: {len(used['failed'])}\n"
            f"🌐 بروكسيات عامة: {len(load_proxies())}\n"
            f"🔒 بروكسيات خاصة: {len(load_paid_proxies())}"
        )
        return

    bot.answer_callback_query(call.id, "⚠️ أمر غير معروف")

# ============================================
# دوال الخطوات النصية
# ============================================
def add_channel_step(message):
    if not is_owner(message.from_user.id):
        return
    channel = message.text.strip().replace("@", "")
    if not channel:
        bot.reply_to(message, "❌ يرجى إدخال معرف القناة بشكل صحيح.")
        return
    channels = load_extra_channels()
    if channel in channels:
        bot.reply_to(message, f"⚠️ القناة @{channel} موجودة مسبقاً.")
        return
    channels.append(channel)
    save_extra_channels(channels)
    bot.reply_to(message, f"✅ تم إضافة القناة الإجبارية: @{channel}\nسيُطلب من جميع المستخدمين الاشتراك فيها.")

def broadcast_step(message):
    if not is_owner(message.from_user.id):
        return
    text = message.text.strip()
    if not text:
        bot.reply_to(message, "❌ لا يمكن إرسال رسالة فارغة.")
        return
    sessions = load_user_sessions()
    if not sessions:
        bot.reply_to(message, "📭 لا يوجد مستخدمون لإرسال الرسالة إليهم.")
        return
    bot.reply_to(message, f"📢 جاري إرسال الرسالة إلى {len(sessions)} مستخدم...")
    success_count = 0
    for user_id_str in sessions.keys():
        try:
            bot.send_message(int(user_id_str), f"📢 **إعلان من المالك:**\n\n{text}", parse_mode="Markdown")
            success_count += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"فشل إرسال إلى {user_id_str}: {e}")
    bot.reply_to(message, f"✅ تم إرسال الرسالة إلى {success_count} من {len(sessions)} مستخدم.")

def add_proxy_step(message):
    if not is_owner(message.from_user.id):
        return
    proxy = message.text.strip()
    if not proxy.startswith("http://") and not proxy.startswith("https://"):
        proxy = f"http://{proxy}"
    
    if proxy not in proxies:
        proxies.append(proxy)
        save_proxies(proxies)
        bot.reply_to(message, f"✅ تم إضافة بروكسي عام:\n`{proxy}`\n🌐 العدد الإجمالي: {len(proxies)}")
    else:
        bot.reply_to(message, f"⚠️ هذا البروكسي موجود مسبقاً.")

def add_paid_proxy_step(message):
    if not is_owner(message.from_user.id):
        return
    proxy = message.text.strip()
    if not proxy.startswith("http://") and not proxy.startswith("https://"):
        proxy = f"http://{proxy}"
    
    # التحقق من وجود @ (user:pass@IP:PORT)
    if '@' not in proxy:
        bot.reply_to(message, "❌ البروكسي الخاص يجب أن يكون بصيغة `user:pass@IP:PORT`")
        return
    
    if add_paid_proxy(proxy):
        bot.reply_to(message, f"✅ تم إضافة بروكسي خاص:\n`{proxy}`\n🔒 عدد البروكسيات الخاصة: {len(load_paid_proxies())}")
    else:
        bot.reply_to(message, f"⚠️ هذا البروكسي الخاص موجود مسبقاً.")

def process_bulk_proxies(message):
    global proxies
    if not is_owner(message.from_user.id):
        return
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            content = downloaded_file.decode('utf-8')
            proxies_list = [p.strip() for p in content.split('\n') if p.strip()]
        except Exception as e:
            bot.reply_to(message, f"⚠️ خطأ في قراءة الملف: {e}")
            return
    else:
        content = message.text.strip()
        if not content:
            bot.reply_to(message, "❌ لم ترسل أي بروكسيات!")
            return
        proxies_list = [p.strip() for p in content.split('\n') if p.strip()]

    if not proxies_list:
        bot.reply_to(message, "❌ لم يتم العثور على بروكسيات صالحة!")
        return

    formatted = []
    paid_list = []
    for p in proxies_list:
        if not p.startswith("http://") and not p.startswith("https://"):
            p = f"http://{p}"
        # إذا كان يحتوي على @ فهو بروكسي خاص
        if '@' in p:
            paid_list.append(p)
        else:
            formatted.append(p)

    # إضافة العامة
    current = load_proxies()
    current_set = set(current)
    added = 0
    for p in formatted:
        if p not in current_set:
            current.append(p)
            current_set.add(p)
            added += 1
    save_proxies(current)
    proxies = current

    # إضافة الخاصة
    current_paid = load_paid_proxies()
    current_paid_set = set(current_paid)
    added_paid = 0
    for p in paid_list:
        if p not in current_paid_set:
            current_paid.append(p)
            current_paid_set.add(p)
            added_paid += 1
    save_paid_proxies(current_paid)

    bot.reply_to(message,
        f"✅ تم إضافة {added} بروكسي عام جديد.\n"
        f"🔒 تم إضافة {added_paid} بروكسي خاص جديد.\n"
        f"🌐 العدد الإجمالي عامة: {len(current)} | خاصة: {len(current_paid)}"
    )

def check_proxies(message):
    global proxies, dead_proxies
    all_proxies = load_all_proxies()
    if not all_proxies:
        bot.reply_to(message, "📭 لا يوجد بروكسيات لفحصها.")
        return

    bot.reply_to(message, f"🔍 جاري فحص {len(all_proxies)} بروكسي... قد يستغرق هذا دقيقة.")

    working = []
    dead = []
    total = len(all_proxies)

    for i, p in enumerate(all_proxies, 1):
        bot.send_message(message.chat.id, f"⏳ اختبار {i}/{total}: {p}")
        try:
            test_params = {"referred_user_id": "9999999", "ref_code": "4094894"}
            test_headers = {"Authorization": TOKEN_API, "User-Agent": "okhttp/5.3.2"}
            test_proxies = {"http": p, "https": p}

            response = requests.get(
                BASE_URL,
                params=test_params,
                headers=test_headers,
                proxies=test_proxies,
                timeout=10
            )

            if response.status_code == 200:
                working.append(p)
                bot.send_message(message.chat.id, f"   ✅ صالح (استجابة {response.status_code})")
            else:
                dead.append(p)
                bot.send_message(message.chat.id, f"   ❌ تالف (كود {response.status_code})")

        except requests.exceptions.Timeout:
            dead.append(p)
            bot.send_message(message.chat.id, f"   ⏰ تالف (انتهت المهلة)")
        except Exception as e:
            dead.append(p)
            bot.send_message(message.chat.id, f"   💀 تالف (خطأ: {str(e)[:30]})")

        time.sleep(0.5)

    # تحديث القوائم
    save_proxies(working)
    save_dead_proxies(dead)
    proxies = working
    dead_proxies = dead

    # لا نحذف البروكسيات الخاصة من القائمة الخاصة حتى لو كانت تالفة
    # بل نضيفها إلى dead_proxies لمنع استخدامها

    bot.reply_to(message,
        f"✅ فحص البروكسيات اكتمل.\n"
        f"🟢 صالح للاستخدام: {len(working)}\n"
        f"💀 تالف: {len(dead)}\n"
        f"تم نقل التالفة إلى dead_proxies.txt\n\n"
        f"💡 نصيحة: إذا كان العدد الصالح قليلاً، ابحث عن بروكسيات جديدة."
    )

def set_referral_step(message, user_id):
    try:
        value = message.text.strip()
        if not value:
            bot.reply_to(message, "❌ يرجى إدخال كود الإحالة (لا تتركه فارغاً)!")
            return
        set_user_setting(user_id, "referral_code", value)
        bot.reply_to(message, f"✅ تم تعيين كود الإحالة إلى: {value}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ خطأ: {e}")

def set_start_step(message, user_id):
    try:
        value = message.text.strip()
        if not value.isdigit():
            bot.reply_to(message, "❌ يرجى إدخال أرقام فقط!")
            return
        set_user_setting(user_id, "start_number", int(value))
        bot.reply_to(message, f"✅ تم تعيين رقم البداية إلى: {value}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ خطأ: {e}")

# ============================================
# 🖥️ خادم Flask
# ============================================
app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"status": "bot is running", "uptime": "24/7"}), 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
            break
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"⚠️ المنفذ {port} مشغول، نجرب {port + 1}...")
                port += 1
            else:
                print(f"❌ خطأ في تشغيل الخادم: {e}")
                break
    else:
        print("❌ لم نجد منفذاً متاحاً بعد 10 محاولات.")

# ============================================
# 🚀 تشغيل البوت
# ============================================
if __name__ == "__main__":
    print("="*60)
    print("🤖 بوت الإحالات - النسخة النهائية (مع دعم البروكسيات الخاصة)")
    print(f"👤 المالك: {OWNER_ID}")
    print(f"📢 قناة التلجرام الأساسية: @{CHANNEL_TG}")
    print(f"🎬 قناة اليوتيوب: {CHANNEL_YT}")
    print(f"🌐 بروكسيات عامة: {len(load_proxies())}")
    print(f"🔒 بروكسيات خاصة: {len(load_paid_proxies())}")
    print(f"💀 تالفة: {len(load_dead_proxies())}")
    extra = load_extra_channels()
    print(f"📢 قنوات إضافية: {len(extra)}")
    print("="*60)
    print("🚀 البوت يعمل...")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    while True:
        try:
            bot.polling(none_stop=True, interval=1)
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e}")
            time.sleep(5)
