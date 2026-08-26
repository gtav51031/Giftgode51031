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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8710044999:AAGsGCewdnb4sqrwE8dkRfQErKvLklpwP8M")
OWNER_ID = int(os.environ.get("OWNER_ID", 6366853738))
CHANNEL_TG = os.environ.get("CHANNEL_TG", "thaish12")
CHANNEL_YT = os.environ.get("CHANNEL_YT", "https://youtube.com/@tahish159?si=5ehTRVzB7WOnOj5s")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Rame124673_bot")
TOKEN_API = os.environ.get("TOKEN_API", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJndGF2NTEwMzFAZ21haWwuY29tIn0.LR0lbOdO6Qq5d_4X0jKUC6mx18PP1-w2ChvBXQTETw0")

INITIAL_POINTS = 50
YOUTUBE_VERIFY_KEY = "youtube_verified"
YOUTUBE_VERIFY_DAYS = 7
EXTRA_CHANNELS_FILE = "extra_channels.json"
DELAY_BETWEEN_ATTEMPTS = 300  # 5 دقائق

# ============================================
# 📂 ملفات البيانات
# ============================================
DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_user_file(user_id, filename):
    return os.path.join(DATA_DIR, f"{filename}_{user_id}.json")

# ============================================
# ✅ دوال النقاط والإحالات
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

def get_user_setting(user_id, key, default=None):
    data = load_user_settings(user_id)
    return data.get(key, default)

def set_user_setting(user_id, key, value):
    data = load_user_settings(user_id)
    data[key] = value
    save_user_settings(user_id, data)

# ============================================
# 👤 نظام الإحالة الداخلي
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
    if not is_subscribed_youtube(new_user_id):
        return False, "❌ يجب تأكيد اشتراك يوتيوب!"

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

def get_all_referral_stats():
    referral_data = load_referral_data()
    return referral_data.get("referrals", {})

# ============================================
# 🎯 دوال الإحالة (GiftCode - بدون بروكسي)
# ============================================
BASE_URL = "https://giftcode.betelgeuse.app/api/referrer"
DEFAULT_START = 4084879

def send_giftcode_referral(referral_code, user_id):
    params = {"referred_user_id": str(user_id), "ref_code": str(referral_code)}
    headers = {"Authorization": TOKEN_API, "User-Agent": "okhttp/5.3.2"}
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=15)
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

def process_giftcode(user_id, target):
    used_data = load_used_numbers(user_id)
    ref_code = get_user_setting(user_id, "referral_code", "4094894")
    if str(target) in used_data["success"]:
        return {"success": False, "reason": "already_used_success"}
    if str(target) in used_data["failed"]:
        return {"success": False, "reason": "already_used_failed"}
    if str(target) in used_data["already"]:
        return {"success": False, "reason": "already_used_already"}
    result = send_giftcode_referral(ref_code, target)
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
        "already_referred": "هذا الرقم تمت إحالته مسبقاً بواسطة مستخدم آخر",
        "invalid_user": "الرقم غير صالح (ليس مستخدمًا في التطبيق)",
        "same_ip": "نفس عنوان IP تم استخدامه مؤخراً، انتظر 5 دقائق",
        "rate_limited": "تم تجاوز عدد الطلبات، انتظر 5 دقائق",
        "connection_error": "خطأ في الاتصال، سيتم إعادة المحاولة بعد 5 دقائق",
        "already_used_success": "تم إحالة هذا الرقم بنجاح سابقاً",
        "already_used_failed": "فشل سابق لهذا الرقم (لن نعيد المحاولة)",
        "already_used_already": "هذا الرقم محال مسبقاً",
    }
    if reason.startswith("HTTP_"):
        return f"خطأ في الخادم (كود {reason.split('_')[1]})"
    return translations.get(reason, reason)

# ============================================
# 🔥 دوال GiftSheep (Firebase - بدون بروكسي)
# ============================================
FIREBASE_API_KEY = "AIzaSyDR1RcaMP9IOmIy7i_daFPNr3e7kmWid6o"
REFERRAL_URL_FB = "https://us-central1-gift-sheep-b21df.cloudfunctions.net/submitReferral"
TARGET_CODE_FB = "W27PO5"

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

def send_firebase_referral(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'okhttp/3.12.13'
    }
    payload = {"data": {"code": TARGET_CODE_FB}}
    try:
        resp = requests.post(REFERRAL_URL_FB, json=payload, headers=headers, timeout=30)
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
# 🤖 دوال البوت الأساسية
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
    extra_ok, channel = is_subscribed_extra(user_id)
    if not extra_ok:
        return False, f"extra_{channel}"
    return True, None

# ============================================
# 🚀 حلقة الهجوم الموحدة (بدون بروكسيات)
# ============================================
attack_status = {}
attack_mode = {}  # 'giftcode' أو 'giftsheep'

def attack_loop(user_id, chat_id):
    user_id_str = str(user_id)
    mode = attack_mode.get(user_id_str, 'giftcode')
    start_number = int(get_user_setting(user_id, "start_number", DEFAULT_START))
    current_number = start_number
    attempts = 0
    successes = 0
    attack_status[user_id_str] = {"running": True, "number": current_number}

    bot.send_message(chat_id, f"🚀 بدء الهجوم بوضع {mode.upper()} (بدون بروكسيات، تأخير 5 دقائق بين المحاولات)")

    user_data = load_user_sessions().get(user_id_str, {})
    user_name = user_data.get("first_name", "مستخدم")

    while attack_status[user_id_str]["running"]:
        sub_ok, sub_type = check_all_subscriptions(user_id)
        if not sub_ok:
            if sub_type == "telegram":
                bot.send_message(chat_id, f"❌ اشترك في قناة التلجرام: @{CHANNEL_TG}")
            elif sub_type == "youtube":
                bot.send_message(chat_id, f"❌ أكد اشتراك يوتيوب (زر التأكيد)")
            elif sub_type and sub_type.startswith("extra_"):
                channel = sub_type.replace("extra_", "")
                bot.send_message(chat_id, f"❌ اشترك في القناة الإضافية: @{channel}")
            else:
                bot.send_message(chat_id, "❌ اشترك في جميع القنوات المطلوبة.")
            break

        points = load_user_points(user_id)
        if points <= 0 and not is_owner(user_id):
            referral_link = get_referral_link(user_id)
            keyboard = InlineKeyboardMarkup()
            btn_link = InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral")
            keyboard.add(btn_link)
            bot.send_message(chat_id,
                f"⚠️ نفدت نقاطك! شارك رابط الإحالة:\n`{referral_link}`",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            break

        attempts += 1
        bot.send_message(chat_id, f"⏳ محاولة #{attempts}...")

        if mode == 'giftcode':
            target = str(current_number)
            current_number += 1
            attack_status[user_id_str]["number"] = current_number
            result = process_giftcode(user_id, target)
        else:
            random_suffix = uuid.uuid4().hex[:8]
            email = f"fb_{random_suffix}@temp-mail.org"
            auth_data = create_firebase_account(email, "Test@2026")
            if not auth_data or 'error' in auth_data:
                bot.send_message(chat_id, f"❌ فشل إنشاء حساب Firebase: {auth_data.get('error', 'Unknown')}")
                bot.send_message(chat_id, f"⏳ انتظار {DELAY_BETWEEN_ATTEMPTS//60} دقائق...")
                time.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            id_token = auth_data.get('idToken')
            refresh_token = auth_data.get('refreshToken')
            if not id_token:
                bot.send_message(chat_id, "❌ لا يوجد توكن.")
                time.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            success, msg = send_firebase_referral(id_token)
            if not success and "token" in msg.lower():
                new_token, new_refresh = refresh_firebase_token(refresh_token)
                if new_token:
                    id_token = new_token
                    refresh_token = new_refresh
                    success, msg = send_firebase_referral(id_token)

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
            bot.send_message(OWNER_ID, f"✅ نجاح {mode.upper()} من {user_name} (ID: {user_id}) -> +{gold} GP")
        else:
            reason = result.get("reason", "غير معروف")
            arabic_reason = translate_reason(reason)
            bot.send_message(chat_id, f"⚠️ فشل: {arabic_reason}")

        if attack_status[user_id_str]["running"]:
            bot.send_message(chat_id, f"⏳ انتظار {DELAY_BETWEEN_ATTEMPTS//60} دقائق قبل المحاولة التالية...")
            time.sleep(DELAY_BETWEEN_ATTEMPTS)

    attack_status[user_id_str]["running"] = False
    bot.send_message(chat_id, f"⏹️ توقف الهجوم. إجمالي النجاحات: {successes} من {attempts} محاولة.")

# ============================================
# 📨 أوامر المستخدمين
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
        sessions[user_id_str] = {
            "first_name": first_name,
            "username": message.from_user.username or "",
            "joined": datetime.now().isoformat()
        }
        save_user_sessions(sessions)

    sub_ok, sub_type = check_all_subscriptions(user_id)
    referral_data = load_referral_data()

    if referrer_id and user_id_str not in referral_data.get("referred_users", {}):
        if not is_subscribed_telegram(user_id) or not is_subscribed_youtube(user_id):
            keyboard = InlineKeyboardMarkup(row_width=1)
            btn_tg = InlineKeyboardButton("📢 اشترك في قناة التلجرام", url=f"https://t.me/{CHANNEL_TG}")
            btn_yt = InlineKeyboardButton("🎬 تأكيد يوتيوب", callback_data="verify_youtube")
            btn_confirm = InlineKeyboardButton("✅ تأكيد الإحالة", callback_data=f"confirm_referral_{referrer_id}")
            keyboard.add(btn_tg, btn_yt, btn_confirm)
            bot.reply_to(message,
                f"👋 أهلاً {first_name}!\nتمت دعوتك، اشترك في القناة وأكد يوتيوب أولاً.",
                reply_markup=keyboard
            )
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
        elif sub_type and sub_type.startswith("extra_"):
            ch = sub_type.replace("extra_", "")
            keyboard.add(InlineKeyboardButton(f"📢 اشترك في @{ch}", url=f"https://t.me/{ch}"))
        keyboard.add(InlineKeyboardButton("✅ تحقق", callback_data="check_sub"))
        bot.reply_to(message, "🔒 اشترك في جميع القنوات وأكد يوتيوب.", reply_markup=keyboard)
        return

    # القائمة الرئيسية
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_set_ref = InlineKeyboardButton("🔑 كود الإحالة", callback_data="set_referral")
    btn_set_start = InlineKeyboardButton("🔢 رقم البداية", callback_data="set_start")
    btn_start = InlineKeyboardButton("▶️ بدء الهجوم", callback_data="start_attack")
    btn_stop = InlineKeyboardButton("⏹️ إيقاف الهجوم", callback_data="stop_attack")
    btn_mode = InlineKeyboardButton("🔄 تبديل الوضع", callback_data="toggle_mode")
    btn_status = InlineKeyboardButton("📊 الحالة", callback_data="status")
    btn_referral = InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral")
    keyboard.add(btn_set_ref, btn_set_start)
    keyboard.add(btn_start, btn_stop)
    keyboard.add(btn_mode, btn_status)
    keyboard.add(btn_referral)

    if is_owner(user_id):
        keyboard.add(InlineKeyboardButton("👑 المالك", callback_data="owner_commands"))

    current_mode = attack_mode.get(user_id_str, 'giftcode')
    mode_text = "GiftCode" if current_mode == 'giftcode' else "GiftSheep"

    ref_code = get_user_setting(user_id, "referral_code", "غير محدد")
    start_num = get_user_setting(user_id, "start_number", DEFAULT_START)
    points = load_user_points(user_id)
    used = load_used_numbers(user_id)
    referral_count, referral_points = get_referral_stats(user_id)

    bot.reply_to(message,
        f"✅ مرحباً {first_name}!\n"
        f"📋 الإعدادات:\n"
        f"🔑 الكود: {ref_code}\n"
        f"🔢 البداية: {start_num}\n"
        f"💎 النقاط: {points}\n"
        f"🔗 إحالاتك: {referral_count} (ربحت {referral_points} نقطة)\n"
        f"✅ نجاح: {len(used['success'])}\n"
        f"⚠️ محال: {len(used['already'])}\n"
        f"❌ فشل: {len(used['failed'])}\n"
        f"🔄 الوضع الحالي: {mode_text}\n\n"
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

    # تأكيد الإحالة
    if call.data.startswith("confirm_referral_"):
        referrer_id = int(call.data.replace("confirm_referral_", ""))
        if not is_subscribed_telegram(user_id) or not is_subscribed_youtube(user_id):
            bot.answer_callback_query(call.id, "❌ اشترك في التيليجرام وأكد يوتيوب!", show_alert=True)
            return
        success, msg = process_referral_new_user(user_id, referrer_id)
        bot.answer_callback_query(call.id, msg[:100], show_alert=True)
        start_command(call.message)
        return

    # تبديل الوضع
    if call.data == "toggle_mode":
        current = attack_mode.get(user_id_str, 'giftcode')
        new_mode = 'giftsheep' if current == 'giftcode' else 'giftcode'
        attack_mode[user_id_str] = new_mode
        bot.answer_callback_query(call.id, f"🔄 تم التبديل إلى {new_mode.upper()}", show_alert=True)
        start_command(call.message)
        return

    # بدء الهجوم
    if call.data == "start_attack":
        points = load_user_points(user_id)
        if not is_owner(user_id) and points <= 0:
            bot.answer_callback_query(call.id, "⚠️ نقاطك 0! أضف نقاطاً.", show_alert=True)
            return
        if attack_status.get(user_id_str, {}).get("running", False):
            bot.answer_callback_query(call.id, "⚠️ هجوم يعمل بالفعل!", show_alert=True)
            return
        if not get_user_setting(user_id, "referral_code"):
            bot.answer_callback_query(call.id, "❌ عين كود الإحالة أولاً!", show_alert=True)
            return

        attack_status[user_id_str] = {"running": True}
        thread = threading.Thread(target=attack_loop, args=(user_id, chat_id))
        thread.daemon = True
        thread.start()
        bot.answer_callback_query(call.id, "▶️ تم البدء!", show_alert=True)
        return

    # إيقاف الهجوم
    if call.data == "stop_attack":
        if attack_status.get(user_id_str, {}).get("running", False):
            attack_status[user_id_str]["running"] = False
            bot.answer_callback_query(call.id, "⏹️ جاري الإيقاف...", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "⚠️ لا يوجد هجوم نشط!", show_alert=True)
        return

    # الحالة
    if call.data == "status":
        points = load_user_points(user_id)
        used = load_used_numbers(user_id)
        running = attack_status.get(user_id_str, {}).get("running", False)
        mode = attack_mode.get(user_id_str, 'giftcode')
        bot.send_message(chat_id,
            f"📊 الحالة:\n"
            f"🔄 الوضع: {mode.upper()}\n"
            f"▶️ الهجوم: {'يعمل' if running else 'متوقف'}\n"
            f"💎 نقاط: {points}\n"
            f"✅ نجاح: {len(used['success'])}"
        )
        return

    # رابط الإحالة
    if call.data == "my_referral":
        link = get_referral_link(user_id)
        count, pts = get_referral_stats(user_id)
        bot.reply_to(call.message, f"🔗 رابطك:\n`{link}`\n\n👥 {count} إحالة | 💎 {pts} نقطة", parse_mode="Markdown")
        return

    # تعيين كود الإحالة
    if call.data == "set_referral":
        bot.answer_callback_query(call.id, "✏️ أرسل الكود:")
        msg = bot.send_message(chat_id, "🔑 أرسل كود الإحالة:")
        bot.register_next_step_handler(msg, set_referral_step, user_id)
        return

    # تعيين رقم البداية
    if call.data == "set_start":
        bot.answer_callback_query(call.id, "✏️ أرسل الرقم:")
        msg = bot.send_message(chat_id, "🔢 أرسل رقم البداية:")
        bot.register_next_step_handler(msg, set_start_step, user_id)
        return

    # التحقق من الاشتراك
    if call.data == "check_sub":
        sub_ok, _ = check_all_subscriptions(user_id)
        if sub_ok:
            bot.answer_callback_query(call.id, "✅ تم التحقق!", show_alert=True)
            start_command(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ تأكد من الاشتراك وتأكيد يوتيوب!", show_alert=True)
        return

    # تأكيد يوتيوب
    if call.data == "verify_youtube":
        set_user_setting(user_id, YOUTUBE_VERIFY_KEY, True)
        set_user_setting(user_id, "youtube_verify_date", datetime.now().isoformat())
        bot.answer_callback_query(call.id, "✅ تم تأكيد يوتيوب (صالحة 7 أيام)!", show_alert=True)
        start_command(call.message)
        return

    # ========== أوامر المالك ==========
    if call.data == "owner_commands":
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ للمالك فقط!", show_alert=True)
            return
        show_owner_menu(call.message)
        return

    # إدارة القنوات
    if call.data == "owner_add_channel":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل معرف القناة:")
        msg = bot.send_message(chat_id, "أرسل معرف القناة (بدون @):")
        bot.register_next_step_handler(msg, add_channel_step)
        return

    if call.data == "owner_list_channels":
        if not is_owner(user_id): return
        channels = load_extra_channels()
        if channels:
            bot.reply_to(call.message, "📋 القنوات الإجبارية:\n" + "\n".join([f"@{ch}" for ch in channels]))
        else:
            bot.reply_to(call.message, "📭 لا توجد قنوات إجبارية.")
        return

    if call.data == "owner_remove_channel":
        if not is_owner(user_id): return
        channels = load_extra_channels()
        if not channels:
            bot.reply_to(call.message, "📭 لا توجد قنوات لحذفها.")
            return
        keyboard = InlineKeyboardMarkup()
        for ch in channels:
            keyboard.add(InlineKeyboardButton(f"🗑️ @{ch}", callback_data=f"remove_channel_{ch}"))
        keyboard.add(InlineKeyboardButton("🔙 إلغاء", callback_data="owner_commands"))
        bot.reply_to(call.message, "اختر قناة لحذفها:", reply_markup=keyboard)
        return

    if call.data.startswith("remove_channel_"):
        if not is_owner(user_id): return
        ch = call.data.replace("remove_channel_", "")
        channels = load_extra_channels()
        if ch in channels:
            channels.remove(ch)
            save_extra_channels(channels)
            bot.answer_callback_query(call.id, f"✅ تم حذف @{ch}", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "⚠️ غير موجود", show_alert=True)
        return

    # البث
    if call.data == "owner_broadcast":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل النص:")
        msg = bot.send_message(chat_id, "أرسل رسالة البث:")
        bot.register_next_step_handler(msg, broadcast_step)
        return

    # الإحصائيات العامة
    if call.data == "owner_stats":
        if not is_owner(user_id): return
        sessions = load_user_sessions()
        total = len(sessions)
        active = sum(1 for uid in sessions if check_all_subscriptions(int(uid))[0])
        bot.reply_to(call.message, f"📊 إحصائيات عامة:\n👥 إجمالي المستخدمين: {total}\n🟢 نشط: {active}")
        return

    # إحصائيات الإحالات
    if call.data == "owner_referral_stats":
        if not is_owner(user_id): return
        referral_data = get_all_referral_stats()
        if not referral_data:
            bot.reply_to(call.message, "📭 لا توجد إحالات حتى الآن.")
            return
        text = "📊 **إحصائيات الإحالات لكل مستخدم:**\n\n"
        for uid, data in referral_data.items():
            sessions = load_user_sessions()
            user_info = sessions.get(uid, {})
            name = user_info.get("first_name", "مجهول")
            text += f"👤 {name} (ID: {uid}):\n"
            text += f"   - عدد الإحالات: {data['count']}\n"
            text += f"   - نقاط مكتسبة: {data['points_earned']}\n"
            if data['users']:
                text += f"   - المستخدمون: {', '.join(data['users'][:5])}\n"
            text += "\n"
        bot.reply_to(call.message, text[:4000], parse_mode="Markdown")
        return

    # عرض المستخدمين (معدل لعرض الكل)
    if call.data == "owner_list_users":
        if not is_owner(user_id): return
        sessions = load_user_sessions()
        if not sessions:
            bot.reply_to(call.message, "📭 لا يوجد مستخدمون مسجلون حتى الآن.")
            return
        text = "👥 **قائمة المستخدمين المسجلين:**\n\n"
        for uid, data in sessions.items():
            name = data.get("first_name", "مجهول")
            username = data.get("username", "")
            points = load_user_points(int(uid))
            text += f"👤 {name}"
            if username:
                text += f" (@{username})"
            text += f" | 🆔 {uid} | 💎 {points}\n"
        bot.reply_to(call.message, text[:4000], parse_mode="Markdown")
        return

    # تعديل النقاط (المعدل ليدعم اسم المستخدم)
    if call.data == "owner_edit_points":
        if not is_owner(user_id): return
        bot.answer_callback_query(call.id, "✏️ أرسل اسم المستخدم (بدون @) أو المعرف الرقمي:")
        msg = bot.send_message(chat_id, "🔧 أرسل **اسم المستخدم** (مثل: `Rex_0157` أو `@Rex_0157`) أو **المعرف الرقمي**.\nاستخدم زر '👥 عرض المستخدمين' لمعرفة الأسماء.")
        bot.register_next_step_handler(msg, edit_points_get_user)
        return

    # مسح الجلسات
    if call.data == "owner_clear_sessions":
        if not is_owner(user_id): return
        save_user_sessions({})
        bot.answer_callback_query(call.id, "🧹 تم مسح الجلسات!", show_alert=True)
        return

    # المساعدة
    if call.data == "owner_help":
        help_text = (
            "👑 **أوامر المالك:**\n\n"
            "➕ إضافة قناة إجبارية\n"
            "📋 عرض القنوات الإجبارية\n"
            "🗑️ حذف قناة إجبارية\n"
            "📢 بث رسالة للجميع\n"
            "📊 إحصائيات عامة\n"
            "📊 إحصائيات الإحالات\n"
            "👥 عرض المستخدمين\n"
            "🔧 تعديل نقاط (باسم المستخدم أو المعرف)\n"
            "🧹 مسح جلسات المستخدمين"
        )
        bot.reply_to(call.message, help_text, parse_mode="Markdown")
        return

    # أي أمر آخر
    bot.answer_callback_query(call.id, "⚠️ أمر غير معروف")

# ============================================
# 👑 قائمة المالك الكاملة
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
        InlineKeyboardButton("❓ مساعدة", callback_data="owner_help")
    )
    bot.reply_to(message, "👑 **قائمة المالك:**", reply_markup=keyboard, parse_mode="Markdown")

# ============================================
# 📝 دوال الخطوات النصية (المعدلة)
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

def add_channel_step(message):
    if not is_owner(message.from_user.id): return
    ch = message.text.strip().replace("@", "")
    if ch:
        channels = load_extra_channels()
        if ch not in channels:
            channels.append(ch)
            save_extra_channels(channels)
            bot.reply_to(message, f"✅ تمت إضافة @{ch}")
        else:
            bot.reply_to(message, f"⚠️ @{ch} موجودة مسبقاً.")

def broadcast_step(message):
    if not is_owner(message.from_user.id): return
    text = message.text.strip()
    if not text:
        bot.reply_to(message, "❌ لا يمكن إرسال رسالة فارغة.")
        return
    sessions = load_user_sessions()
    count = 0
    for uid in sessions.keys():
        try:
            bot.send_message(int(uid), f"📢 إعلان من المالك:\n\n{text}")
            count += 1
            time.sleep(0.1)
        except:
            pass
    bot.reply_to(message, f"✅ تم الإرسال إلى {count} مستخدم.")

def find_user_by_username(username):
    """تبحث عن المستخدم الذي يطابق اسم المستخدم (بدون @) وتعرف معرفه."""
    username = username.strip().lstrip('@').lower()
    sessions = load_user_sessions()
    for uid, data in sessions.items():
        if data.get("username", "").lower() == username:
            return int(uid), data
    return None, None

def edit_points_get_user(message):
    if not is_owner(message.from_user.id): return
    user_input = message.text.strip()
    # محاولة التعرف على المعرف الرقمي
    if user_input.isdigit():
        target_id = int(user_input)
        sessions = load_user_sessions()
        if str(target_id) in sessions:
            bot.reply_to(message, f"✏️ المستخدم {target_id} موجود. أرسل القيمة (موجب للإضافة، سالب للخصم):")
            bot.register_next_step_handler(message, edit_points_set_value, target_id)
            return
        else:
            bot.reply_to(message, f"❌ لا يوجد مستخدم بهذا المعرف: {target_id}.\nاستخدم اسم المستخدم بدلاً من ذلك، أو '👥 عرض المستخدمين' للتحقق.")
            return
    else:
        # البحث عن طريق اسم المستخدم
        target_id, user_data = find_user_by_username(user_input)
        if target_id:
            name = user_data.get("first_name", "مجهول")
            bot.reply_to(message, f"✏️ تم العثور على {name} (ID: {target_id}). أرسل القيمة (موجب للإضافة، سالب للخصم):")
            bot.register_next_step_handler(message, edit_points_set_value, target_id)
            return
        else:
            bot.reply_to(message, f"❌ لم يتم العثور على مستخدم باسم '{user_input}'.\nتأكد من الاسم أو استخدم المعرف الرقمي.\nاستخدم '👥 عرض المستخدمين' لمعرفة الأسماء الصحيحة.")
            return

def edit_points_set_value(message, target_id):
    if not is_owner(message.from_user.id): return
    try:
        val = int(message.text.strip())
        current = load_user_points(target_id)
        new = max(0, current + val)
        save_user_points(target_id, new)
        sessions = load_user_sessions()
        user_info = sessions.get(str(target_id), {})
        name = user_info.get("first_name", "مجهول")
        username = user_info.get("username", "")
        reply_text = f"✅ تم تعديل نقاط {name}"
        if username:
            reply_text += f" (@{username})"
        reply_text += f" (ID: {target_id}): {current} -> {new}"
        bot.reply_to(message, reply_text)
        # إرسال إشعار للمستخدم (اختياري)
        try:
            bot.send_message(target_id, f"🔔 تم تحديث رصيد نقاطك.\nرصيدك الحالي: {new}")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ قيمة غير صالحة. أرسل رقماً (موجب أو سالب).")

# ============================================
# 🖥️ خادم Flask
# ============================================
app = Flask(__name__)
@app.route('/')
def index():
    return jsonify({"status": "bot is running"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ============================================
# 🚀 تشغيل البوت
# ============================================
if __name__ == "__main__":
    print("="*60)
    print("🤖 بوت الإحالات المتطور (بدون بروكسيات)")
    print(f"👤 المالك: {OWNER_ID}")
    print(f"📢 قناة التلجرام: @{CHANNEL_TG}")
    print(f"🎬 يوتيوب: {CHANNEL_YT}")
    print("="*60)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    while True:
        try:
            bot.polling(none_stop=True, interval=1)
        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            time.sleep(5)
