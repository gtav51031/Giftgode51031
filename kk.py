
import os
import telebot
import requests
import json
import time
import random
import threading
import uuid
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify

# ============================================
# 🔐 إعدادات البوت الأساسية
# ============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8738226982:AAFyBMXGSFXz1stdeWQfb4J-hnrW3kr7RKE")
OWNER_ID = int(os.environ.get("OWNER_ID", 6366853738))
CHANNEL_TG = os.environ.get("CHANNEL_TG", "thaish12")
CHANNEL_YT = os.environ.get("CHANNEL_YT", "https://youtube.com/@tahish159?si=5ehTRVzB7WOnOj5s")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Giftsheep1_bot")
TOKEN_API = os.environ.get("TOKEN_API", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJndGF2NTEwMzFAZ21haWwuY29tIn0.LR0lbOdO6Qq5d_4X0jKUC6mx18PP1-w2ChvBXQTETw0")

INITIAL_POINTS = 50
REFERRAL_POINTS = 20
YOUTUBE_VERIFY_KEY = "youtube_verified"
YOUTUBE_VERIFY_DAYS = 7
EXTRA_CHANNELS_FILE = "extra_channels.json"
DELAY_BETWEEN_ATTEMPTS = 10
PROXIES_FILE = "proxies.txt"
USER_PROXIES_FILE = "user_proxies.txt"

# ============================================
# 📂 ملفات البيانات
# ============================================
DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_user_file(user_id, filename):
    return os.path.join(DATA_DIR, f"{filename}_{user_id}.json")

def load_user_points(user_id):
    filepath = get_user_file(user_id, "points")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f).get("points", INITIAL_POINTS)
    return INITIAL_POINTS

def save_user_points(user_id, points):
    with open(get_user_file(user_id, "points"), "w") as f:
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

def get_user_setting(user_id, key, default=None):
    data = load_user_settings(user_id)
    return data.get(key, default)

def set_user_setting(user_id, key, value):
    data = load_user_settings(user_id)
    data[key] = value
    save_user_settings(user_id, data)

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

def load_user_data(user_id):
    filepath = get_user_file(user_id, "gs_data")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_user_data(user_id, data):
    filepath = get_user_file(user_id, "gs_data")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

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
    if not is_subscribed_telegram(new_user_id) or not is_subscribed_youtube(new_user_id):
        return False, "❌ يجب الاشتراك في القناة وتأكيد يوتيوب أولاً!"

    referral_data = load_referral_data()
    if str(new_user_id) in referral_data.get("referred_users", {}):
        return False, "⚠️ هذا المستخدم تمت إحالته مسبقاً!"

    if str(referrer_id) not in referral_data.get("referrals", {}):
        referral_data.setdefault("referrals", {})[str(referrer_id)] = {"count": 0, "points_earned": 0, "users": []}

    referral_data["referrals"][str(referrer_id)]["count"] += 1
    referral_data["referrals"][str(referrer_id)]["points_earned"] += REFERRAL_POINTS
    referral_data["referrals"][str(referrer_id)]["users"].append(str(new_user_id))
    referral_data.setdefault("referred_users", {})[str(new_user_id)] = str(referrer_id)
    save_referral_data(referral_data)

    current_points = load_user_points(referrer_id)
    save_user_points(referrer_id, current_points + REFERRAL_POINTS)
    save_user_points(new_user_id, INITIAL_POINTS)
    return True, f"✅ تمت الإحالة! حصلت على {REFERRAL_POINTS} نقطة."

def get_referral_stats(user_id):
    referral_data = load_referral_data()
    stats = referral_data.get("referrals", {}).get(str(user_id), {"count": 0, "points_earned": 0})
    return stats["count"], stats["points_earned"]

def get_all_referral_stats():
    referral_data = load_referral_data()
    return referral_data.get("referrals", {})

# ============================================
# 🔄 دوال البروكسيات
# ============================================
def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    with open(PROXIES_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w') as f:
        f.write('\n'.join(proxies))

def load_user_proxies():
    if not os.path.exists(USER_PROXIES_FILE):
        return []
    with open(USER_PROXIES_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def save_user_proxies(proxies):
    with open(USER_PROXIES_FILE, 'w') as f:
        f.write('\n'.join(proxies))

def get_all_proxies():
    return load_proxies() + load_user_proxies()

def test_proxy(proxy):
    try:
        r = requests.get('https://httpbin.org/ip', proxies={'http': proxy, 'https': proxy}, timeout=5)
        if r.status_code == 200:
            return True
    except:
        pass
    return False

def get_next_proxy(banned_proxies=None):
    if banned_proxies is None:
        banned_proxies = set()
    all_proxies = get_all_proxies()
    random.shuffle(all_proxies)
    for proxy in all_proxies:
        if proxy in banned_proxies:
            continue
        if test_proxy(proxy):
            return proxy, banned_proxies
        else:
            banned_proxies.add(proxy)
    return None, banned_proxies

# ============================================
# 🎯 دوال GiftCode
# ============================================
BASE_URL = "https://giftcode.betelgeuse.app/api/referrer"
DEFAULT_START = 4084879

def send_giftcode_referral(referral_code, user_id, proxy=None):
    params = {"referred_user_id": str(user_id), "ref_code": str(referral_code)}
    headers = {"Authorization": TOKEN_API, "User-Agent": "okhttp/5.3.2"}
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=15, proxies=proxies)
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
        return {"success": False, "reason": "connection_error", "error": str(e)}

def process_giftcode(user_id, target, proxy=None):
    used_data = load_used_numbers(user_id)
    ref_code = get_user_setting(user_id, "referral_code", "4094894")
    result = send_giftcode_referral(ref_code, target, proxy)
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

def translate_reason(reason):
    translations = {
        "already_referred": "هذا الرقم تمت إحالته مسبقاً",
        "invalid_user": "الرقم غير صالح",
        "same_ip": "نفس IP تم استخدامه مؤخراً، انتظر 5 دقائق",
        "rate_limited": "تم تجاوز عدد الطلبات، انتظر 5 دقائق",
        "connection_error": "خطأ في الاتصال",
        "already_used_success": "تم إحالة هذا الرقم بنجاح سابقاً",
        "already_used_failed": "فشل سابق لهذا الرقم",
        "already_used_already": "هذا الرقم محال مسبقاً",
    }
    if reason.startswith("HTTP_"):
        return f"خطأ في الخادم (كود {reason.split('_')[1]})"
    return translations.get(reason, reason)

# ============================================
# 🔥 دوال GiftSheep (Firebase)
# ============================================
FIREBASE_API_KEY = "AIzaSyDR1RcaMP9IOmIy7i_daFPNr3e7kmWid6o"
REFERRAL_URL_FB = "https://us-central1-gift-sheep-b21df.cloudfunctions.net/submitReferral"

def create_firebase_account(email, password):
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
    params = {"key": FIREBASE_API_KEY}
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        resp = requests.post(url, params=params, json=payload, timeout=30)
        data = resp.json()
        if resp.status_code == 200:
            return data
        else:
            return {"error": data.get('error', {}).get('message', 'Unknown')}
    except Exception as e:
        return {"error": str(e)}

def send_firebase_referral(access_token, referral_code, proxy=None):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'okhttp/3.12.13'
    }
    payload = {"data": {"code": referral_code}}
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        resp = requests.post(REFERRAL_URL_FB, json=payload, headers=headers, timeout=30, proxies=proxies)
        try:
            result = resp.json()
            success = result.get('result', {}).get('success', False)
            message = result.get('result', {}).get('message', '')
            return success, message
        except:
            return False, f"Response not JSON: {resp.text[:50]}"
    except Exception as e:
        return False, f"Connection error: {e}"

def refresh_firebase_token(refresh_token):
    url = "https://securetoken.googleapis.com/v1/token"
    params = {"key": FIREBASE_API_KEY}
    payload = {"grantType": "refresh_token", "refreshToken": refresh_token}
    try:
        resp = requests.post(url, params=params, data=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token"), data.get("refresh_token")
    except:
        pass
    return None, None

# ============================================
# 🤖 دوال البوت
# ============================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

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
    return True, None

# ============================================
# 🚀 حلقة الهجوم
# ============================================
attack_status = {}
attack_mode = {}

def attack_loop(user_id, chat_id):
    user_id_str = str(user_id)
    mode = attack_mode.get(user_id_str, 'giftcode')
    start_number = int(get_user_setting(user_id, "start_number", DEFAULT_START))
    current_number = start_number
    attempts = 0
    successes = 0
    banned_proxies = set()
    attack_status[user_id_str] = {"running": True, "number": current_number}

    bot.send_message(chat_id, f"🚀 بدء الهجوم بوضع {mode.upper()} (مع إدارة البروكسيات)")

    while attack_status[user_id_str]["running"]:
        points = load_user_points(user_id)
        if points <= 0 and not is_owner(user_id):
            referral_link = get_referral_link(user_id)
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral"))
            bot.send_message(chat_id, f"⚠️ **نفدت نقاطك!**\nشارك رابط الإحالة للحصول على {REFERRAL_POINTS} نقطة:\n`{referral_link}`", parse_mode="Markdown", reply_markup=keyboard)
            break

        proxy, banned_proxies = get_next_proxy(banned_proxies)
        if not proxy:
            bot.send_message(chat_id, "⚠️ لا توجد بروكسيات شغالة. انتظر 5 دقائق أو أضف بروكسي جديد.")
            time.sleep(300)
            banned_proxies = set()
            continue

        attempts += 1
        bot.send_message(chat_id, f"⏳ محاولة #{attempts}...")

        if mode == 'giftcode':
            target = str(random.randint(4000000, 9999999))
            attack_status[user_id_str]["number"] = target
            result = process_giftcode(user_id, target, proxy)
        else:
            random_suffix = uuid.uuid4().hex[:8]
            email = f"fb_{random_suffix}@temp-mail.org"
            auth_data = create_firebase_account(email, "Test@2026")
            if not auth_data or 'error' in auth_data:
                bot.send_message(chat_id, f"❌ فشل إنشاء حساب: {auth_data.get('error', 'Unknown')}")
                continue
            id_token = auth_data.get('idToken')
            if not id_token:
                continue

            # استخدام كود الإحالة الخاص بالمستخدم
            user_ref_code = get_user_setting(user_id, "referral_code", "W27PO5")
            success, msg = send_firebase_referral(id_token, user_ref_code, proxy)
            if success:
                result = {"success": True, "gold": 0}
            else:
                result = {"success": False, "reason": msg}

        if result.get("success"):
            successes += 1
            gold = result.get("gold", 0)
            new_points = load_user_points(user_id) - 1
            save_user_points(user_id, new_points)
            bot.send_message(chat_id, f"🎉 نجاح! (+{gold} GP)\n💎 نقاط متبقية: {new_points}")
            bot.send_message(OWNER_ID, f"✅ نجاح {mode.upper()} من {user_id}")
        else:
            reason = result.get("reason", "غير معروف")
            arabic_reason = translate_reason(reason)
            bot.send_message(chat_id, f"⚠️ فشل: {arabic_reason}")

            if reason in ["same_ip", "rate_limited", "connection_error"]:
                banned_proxies.add(proxy)
                continue
            elif reason in ["already_used_success", "already_used_failed", "already_used_already"]:
                continue
            else:
                time.sleep(2)

    attack_status[user_id_str]["running"] = False
    bot.send_message(chat_id, f"⏹️ توقف الهجوم. إجمالي النجاحات: {successes} من {attempts} محاولة.")

# ============================================
# 📨 أوامر البوت
# ============================================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "مستخدم"

    referrer_id = None
    if message.text and message.text.startswith('/start'):
        parts = message.text.split()
        if len(parts) > 1 and parts[1].isdigit():
            referrer_id = int(parts[1])

    sessions = load_user_sessions()
    user_id_str = str(user_id)
    if user_id_str not in sessions:
        sessions[user_id_str] = {"first_name": first_name, "username": message.from_user.username or "", "joined": datetime.now().isoformat()}
        save_user_sessions(sessions)

    sub_ok, sub_type = check_all_subscriptions(user_id)
    referral_data = load_referral_data()

    if referrer_id and user_id_str not in referral_data.get("referred_users", {}):
        if not is_subscribed_telegram(user_id) or not is_subscribed_youtube(user_id):
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_TG}"))
            keyboard.add(InlineKeyboardButton("🎬 تأكيد يوتيوب", callback_data="verify_youtube"))
            keyboard.add(InlineKeyboardButton("✅ تأكيد الإحالة", callback_data=f"confirm_referral_{referrer_id}"))
            bot.reply_to(message, f"👋 أهلاً {first_name}!\nتمت دعوتك، اشترك في القناة وأكد يوتيوب أولاً.", reply_markup=keyboard)
            return
        else:
            success, msg = process_referral_new_user(user_id, referrer_id)
            bot.reply_to(message, f"🔗 تمت الإحالة!\n{msg}")

    if not sub_ok:
        keyboard = InlineKeyboardMarkup(row_width=1)
        if sub_type == "telegram":
            keyboard.add(InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_TG}"))
        elif sub_type == "youtube":
            keyboard.add(InlineKeyboardButton("🎬 تأكيد يوتيوب", callback_data="verify_youtube"))
        keyboard.add(InlineKeyboardButton("✅ تحقق", callback_data="check_sub"))
        bot.reply_to(message, "🔒 اشترك في القناة وأكد يوتيوب.", reply_markup=keyboard)
        return

    current_mode = attack_mode.get(user_id_str, 'giftcode')
    points = load_user_points(user_id)
    used = load_used_numbers(user_id)
    user_ref_code = get_user_setting(user_id, "referral_code", "غير محدد")

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔑 كود الإحالة", callback_data="set_referral"),
        InlineKeyboardButton("🔢 رقم البداية", callback_data="set_start"),
        InlineKeyboardButton("▶️ بدء الهجوم", callback_data="start_attack"),
        InlineKeyboardButton("⏹️ إيقاف الهجوم", callback_data="stop_attack"),
        InlineKeyboardButton("🔄 تبديل الوضع", callback_data="toggle_mode"),
        InlineKeyboardButton("📊 الحالة", callback_data="status"),
        InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral"),
        InlineKeyboardButton("➕ إضافة بروكسي", callback_data="user_add_proxy")
    )

    if is_owner(user_id):
        keyboard.add(InlineKeyboardButton("👑 المالك", callback_data="owner_commands"))

    bot.reply_to(message,
        f"✅ مرحباً {first_name}!\n"
        f"💎 النقاط: {points}\n"
        f"🔑 كود إحالتك: {user_ref_code}\n"
        f"🔄 الوضع: {current_mode.upper()}\n"
        f"✅ نجاح: {len(used['success'])}\n"
        f"⚠️ محال: {len(used['already'])}\n"
        f"❌ فشل: {len(used['failed'])}\n\n"
        f"اختر الأمر:",
        reply_markup=keyboard
    )

# ============================================
# 🖱️ معالجة الأزرار
# ============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_id_str = str(user_id)

    if call.data == "user_add_proxy":
        msg = bot.send_message(chat_id, "🔐 أرسل البروكسي (http://user:pass@ip:port):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, user_add_proxy_step, user_id)
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("confirm_referral_"):
        referrer_id = int(call.data.replace("confirm_referral_", ""))
        if not is_subscribed_telegram(user_id) or not is_subscribed_youtube(user_id):
            bot.answer_callback_query(call.id, "❌ اشترك في القناة وأكد يوتيوب!", show_alert=True)
            return
        success, msg = process_referral_new_user(user_id, referrer_id)
        bot.answer_callback_query(call.id, msg[:100], show_alert=True)
        start_command(call.message)
        return

    if call.data == "toggle_mode":
        current = attack_mode.get(user_id_str, 'giftcode')
        new_mode = 'giftsheep' if current == 'giftcode' else 'giftcode'
        attack_mode[user_id_str] = new_mode
        bot.answer_callback_query(call.id, f"🔄 تم التبديل إلى {new_mode.upper()}", show_alert=True)
        start_command(call.message)
        return

    if call.data == "start_attack":
        points = load_user_points(user_id)
        if points <= 0 and not is_owner(user_id):
            bot.answer_callback_query(call.id, "⚠️ نقاطك 0!", show_alert=True)
            return
        if attack_status.get(user_id_str, {}).get("running", False):
            bot.answer_callback_query(call.id, "⚠️ هجوم يعمل بالفعل!", show_alert=True)
            return
        attack_status[user_id_str] = {"running": True}
        thread = threading.Thread(target=attack_loop, args=(user_id, chat_id))
        thread.daemon = True
        thread.start()
        bot.answer_callback_query(call.id, "▶️ تم البدء!", show_alert=True)
        return

    if call.data == "stop_attack":
        if attack_status.get(user_id_str, {}).get("running", False):
            attack_status[user_id_str]["running"] = False
            bot.answer_callback_query(call.id, "⏹️ جاري الإيقاف...", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "⚠️ لا يوجد هجوم نشط!", show_alert=True)
        return

    if call.data == "status":
        points = load_user_points(user_id)
        used = load_used_numbers(user_id)
        running = attack_status.get(user_id_str, {}).get("running", False)
        mode = attack_mode.get(user_id_str, 'giftcode')
        bot.send_message(chat_id, f"📊 الحالة:\n🔄 الوضع: {mode.upper()}\n▶️ الهجوم: {'يعمل' if running else 'متوقف'}\n💎 نقاط: {points}\n✅ نجاح: {len(used['success'])}")
        bot.answer_callback_query(call.id)
        return

    if call.data == "my_referral":
        link = get_referral_link(user_id)
        bot.reply_to(call.message, f"🔗 رابطك:\n`{link}`\n\nشاركه لتحصل على {REFERRAL_POINTS} نقطة!", parse_mode="Markdown")
        return

    if call.data == "set_referral":
        msg = bot.send_message(chat_id, "🔑 أرسل كود الإحالة:")
        bot.register_next_step_handler(msg, set_referral_step, user_id)
        bot.answer_callback_query(call.id)
        return

    if call.data == "set_start":
        msg = bot.send_message(chat_id, "🔢 أرسل رقم البداية:")
        bot.register_next_step_handler(msg, set_start_step, user_id)
        bot.answer_callback_query(call.id)
        return

    if call.data == "check_sub":
        sub_ok, _ = check_all_subscriptions(user_id)
        if sub_ok:
            bot.answer_callback_query(call.id, "✅ تم التحقق!", show_alert=True)
            start_command(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ تأكد من الاشتراك!", show_alert=True)
        return

    if call.data == "verify_youtube":
        set_user_setting(user_id, YOUTUBE_VERIFY_KEY, True)
        set_user_setting(user_id, "youtube_verify_date", datetime.now().isoformat())
        bot.answer_callback_query(call.id, "✅ تم تأكيد يوتيوب!", show_alert=True)
        start_command(call.message)
        return

    # ========== أوامر المالك ==========
    if call.data == "owner_commands":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ للمالك فقط!", show_alert=True)
            return
        show_owner_menu(call.message)
        return

    if call.data == "owner_add_proxy":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل البروكسي")
        msg = bot.send_message(chat_id, "أرسل البروكسي:")
        bot.register_next_step_handler(msg, add_proxy_step)
        return

    if call.data == "owner_list_proxies":
        if not is_owner(user_id): return
        proxies = get_all_proxies()
        if proxies:
            bot.reply_to(call.message, "📋 **البروكسيات الحالية:**\n" + "\n".join(proxies))
        else:
            bot.reply_to(call.message, "📭 لا توجد بروكسيات.")
        return

    if call.data == "owner_test_proxies":
        if not is_owner(user_id): return
        proxies = get_all_proxies()
        if not proxies:
            bot.reply_to(call.message, "📭 لا توجد بروكسيات.")
            return
        bot.send_message(chat_id, "🧪 جاري اختبار البروكسيات...")
        good = []
        bad = []
        for p in proxies:
            if test_proxy(p):
                good.append(p)
            else:
                bad.append(p)
        bot.reply_to(call.message, f"✅ الشغالة: {len(good)}\n❌ الفاشلة: {len(bad)}")
        return

    if call.data == "owner_del_proxy":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل البروكسي للحذف")
        msg = bot.send_message(chat_id, "أرسل البروكسي الذي تريد حذفه:")
        bot.register_next_step_handler(msg, del_proxy_step)
        return

    if call.data == "owner_help":
        help_text = "👑 **أوامر المالك:**\n\n➕ إضافة قناة\n📋 عرض القنوات\n🗑️ حذف قناة\n📢 بث\n📊 إحصائيات عامة\n📊 إحصائيات الإحالات\n👥 عرض المستخدمين\n🔧 تعديل نقاط\n🧹 مسح الجلسات\n🔐 إدارة البروكسيات"
        bot.reply_to(call.message, help_text, parse_mode="Markdown")
        return

    bot.answer_callback_query(call.id, "⚠️ أمر غير معروف")

# ============================================
# 👑 قائمة المالك
# ============================================
def show_owner_menu(message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ إضافة قناة", callback_data="owner_add_channel"),
        InlineKeyboardButton("📋 عرض القنوات", callback_data="owner_list_channels"),
        InlineKeyboardButton("🗑️ حذف قناة", callback_data="owner_remove_channel"),
        InlineKeyboardButton("📢 بث", callback_data="owner_broadcast"),
        InlineKeyboardButton("📊 إحصائيات عامة", callback_data="owner_stats"),
        InlineKeyboardButton("📊 إحصائيات الإحالات", callback_data="owner_referral_stats"),
        InlineKeyboardButton("👥 عرض المستخدمين", callback_data="owner_list_users"),
        InlineKeyboardButton("🔧 تعديل نقاط", callback_data="owner_edit_points"),
        InlineKeyboardButton("🧹 مسح الجلسات", callback_data="owner_clear_sessions"),
        InlineKeyboardButton("🔐 إدارة البروكسيات", callback_data="owner_proxy_commands"),
        InlineKeyboardButton("❓ مساعدة", callback_data="owner_help")
    )
    bot.reply_to(message, "👑 **قائمة المالك:**", reply_markup=keyboard, parse_mode="Markdown")

# ============================================
# 📝 دوال الخطوات النصية
# ============================================
def set_referral_step(message, user_id):
    set_user_setting(user_id, "referral_code", message.text.strip())
    bot.reply_to(message, f"✅ تم تعيين الكود: {message.text.strip()}")

def set_start_step(message, user_id):
    if message.text.strip().isdigit():
        set_user_setting(user_id, "start_number", int(message.text.strip()))
        bot.reply_to(message, f"✅ تم تعيين رقم البداية: {message.text.strip()}")
    else:
        bot.reply_to(message, "❌ أرقام فقط!")

def user_add_proxy_step(message, user_id):
    proxy_text = message.text.strip()
    if not proxy_text.startswith("http://") and not proxy_text.startswith("https://"):
        proxy_text = f"http://{proxy_text}"
    proxies = load_user_proxies()
    if proxy_text not in proxies:
        proxies.append(proxy_text)
        save_user_proxies(proxies)
        bot.send_message(OWNER_ID, f"🔐 أضاف مستخدم بروكسي:\n👤 {message.from_user.first_name} (ID: {user_id})\n🔗 `{proxy_text}`", parse_mode="Markdown")
        bot.reply_to(message, "✅ تم إضافة البروكسي بنجاح!")
    else:
        bot.reply_to(message, "⚠️ هذا البروكسي موجود مسبقاً.")

def add_proxy_step(message):
    if not is_owner(message.from_user.id): return
    proxy = message.text.strip()
    if not proxy.startswith("http://") and not proxy.startswith("https://"):
        proxy = f"http://{proxy}"
    proxies = load_proxies()
    if proxy not in proxies:
        proxies.append(proxy)
        save_proxies(proxies)
        bot.reply_to(message, "✅ تمت إضافة البروكسي.")
    else:
        bot.reply_to(message, "⚠️ موجود مسبقاً.")

def del_proxy_step(message):
    if not is_owner(message.from_user.id): return
    proxy = message.text.strip()
    proxies = load_proxies()
    if proxy in proxies:
        proxies.remove(proxy)
        save_proxies(proxies)
        bot.reply_to(message, "✅ تم الحذف.")
    else:
        user_proxies = load_user_proxies()
        if proxy in user_proxies:
            user_proxies.remove(proxy)
            save_user_proxies(user_proxies)
            bot.reply_to(message, "✅ تم الحذف من بروكسيات المستخدمين.")
        else:
            bot.reply_to(message, "⚠️ غير موجود.")

# ============================================
# 🖥️ خادم Flask والتشغيل
# ============================================
app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"status": "bot is running"}), 200

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    while True:
        try:
            requests.get("https://giftgode51031.onrender.com/health", timeout=5)
            print("✅ تم إرسال طلب keep-alive")
        except Exception as e:
            print(f"⚠️ فشل keep-alive: {e}")
        time.sleep(600)

if __name__ == "__main__":
    print("="*60)
    print("🤖 بوت الإحالات المتطور (GiftCode + GiftSheep)")
    print(f"👤 المالك: {OWNER_ID}")
    print(f"📢 قناة التلجرام: @{CHANNEL_TG}")
    print("="*60)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    keep_alive_thread = threading.Thread(target=keep_alive)
    keep_alive_thread.daemon = True
    keep_alive_thread.start()

    while True:
        try:
            bot.polling(none_stop=True, interval=1)
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e}")
            time.sleep(5)
