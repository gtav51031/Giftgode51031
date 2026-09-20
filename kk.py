import os
import telebot
import requests
import json
import time
import random
import threading
import uuid
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ============================================
# 🔐 إعدادات البوت
# ============================================
BOT_TOKEN = "8710044999:AAGsGCewdnb4sqrwE8dkRfQErKvLklpwP8M"
OWNER_ID = 6366853738
CHANNEL_TG = "thaish12"
CHANNEL_YT = "https://youtube.com/@tahish159?si=5ehTRVzB7WOnOj5s"
BOT_USERNAME = "Rame124673_bot"
INITIAL_POINTS = 50
REFERRAL_POINTS = 20
PROXIES_FILE = "proxies.txt"
USER_PROXIES_FILE = "user_proxies.txt"
DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# ============================================
# 🎨 دالة مساعدة لإنشاء الأزرار الملونة
# ============================================
def btn(text, callback_data=None, url=None, style=None):
    """إنشاء زر ملون بأسلوب Telegram الجديد مع توافق الإصدارات."""
    kwargs = {"text": text}
    if callback_data: kwargs["callback_data"] = callback_data
    if url: kwargs["url"] = url
    if style:
        kwargs["style"] = style  # 'primary', 'success', 'danger'
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("style", None)  # إزالة style لو الإصدار قديم
        return InlineKeyboardButton(**kwargs)

# ============================================
# 📂 دوال تحميل وحفظ البيانات (بدون تغيير)
# ============================================
def get_user_file(user_id, filename):
    return os.path.join(DATA_DIR, f"{filename}_{user_id}.json")

def load_user_points(user_id):
    filepath = get_user_file(user_id, "points")
    if os.path.exists(filepath):
        with open(filepath, "r") as f: return json.load(f).get("points", INITIAL_POINTS)
    return INITIAL_POINTS

def save_user_points(user_id, points):
    with open(get_user_file(user_id, "points"), "w") as f: json.dump({"points": points}, f)

def load_used_numbers(user_id):
    filepath = get_user_file(user_id, "used_numbers")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
            data.setdefault("success", []); data.setdefault("failed", []); data.setdefault("already", [])
            return data
    return {"success": [], "failed": [], "already": []}

def save_used_numbers(user_id, data):
    with open(get_user_file(user_id, "used_numbers"), "w") as f: json.dump(data, f, indent=2)

def load_user_settings(user_id):
    filepath = get_user_file(user_id, "user_settings")
    if os.path.exists(filepath):
        with open(filepath, "r") as f: return json.load(f)
    return {}

def save_user_settings(user_id, data):
    with open(get_user_file(user_id, "user_settings"), "w") as f: json.dump(data, f, indent=2)

def get_user_setting(user_id, key, default=None):
    return load_user_settings(user_id).get(key, default)

def set_user_setting(user_id, key, value):
    data = load_user_settings(user_id); data[key] = value; save_user_settings(user_id, data)

def load_user_sessions():
    filepath = os.path.join(DATA_DIR, "user_sessions.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f: return json.load(f)
    return {}

def save_user_sessions(sessions):
    with open(os.path.join(DATA_DIR, "user_sessions.json"), "w") as f: json.dump(sessions, f, indent=2)

def load_referral_data():
    filepath = os.path.join(DATA_DIR, "referral_data.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f: return json.load(f)
    return {}

def save_referral_data(data):
    with open(os.path.join(DATA_DIR, "referral_data.json"), "w") as f: json.dump(data, f, indent=2)

def get_referral_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"

def find_user_id_by_input(input_str):
    input_str = input_str.strip()
    if not input_str: return None
    if input_str.lstrip('@').isdigit(): return int(input_str.lstrip('@'))
    username = input_str.lstrip('@').lower()
    sessions = load_user_sessions()
    for uid, data in sessions.items():
        if str(data.get("username", "")).lstrip('@').lower() == username: return int(uid)
    return None

def get_user_display(user_id):
    sessions = load_user_sessions(); data = sessions.get(str(user_id), {})
    name = data.get("first_name", "مجهول"); username = data.get("username", "")
    return f"{name} (@{username})" if username else name

# ============================================
# 🔄 دوال البروكسيات (بدون تغيير)
# ============================================
def load_proxies():
    if not os.path.exists(PROXIES_FILE): return []
    with open(PROXIES_FILE, 'r') as f: return [line.strip() for line in f if line.strip()]

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w') as f: f.write('\n'.join(proxies))

def load_user_proxies():
    if not os.path.exists(USER_PROXIES_FILE): return []
    with open(USER_PROXIES_FILE, 'r') as f: return [line.strip() for line in f if line.strip()]

def save_user_proxies(proxies):
    with open(USER_PROXIES_FILE, 'w') as f: f.write('\n'.join(proxies))

def get_all_proxies(): return load_proxies() + load_user_proxies()

def test_proxy(proxy):
    try:
        r = requests.get('https://httpbin.org/ip', proxies={'http': proxy, 'https': proxy}, timeout=5)
        return r.status_code == 200
    except: return False

def get_next_proxy(banned_proxies=None):
    if banned_proxies is None: banned_proxies = set()
    proxies = get_all_proxies(); random.shuffle(proxies)
    for proxy in proxies:
        if proxy in banned_proxies: continue
        if test_proxy(proxy): return proxy, banned_proxies
        else: banned_proxies.add(proxy)
    return None, banned_proxies

# ============================================
# 🎯 GiftCode & GiftSheep (بدون تغيير في المنطق)
# ============================================
BASE_URL = "https://giftcode.betelgeuse.app/api/referrer"
DEFAULT_START = 4084879
TOKEN_API = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJndGF2NTEwMzFAZ21haWwuY29tIn0.LR0lbOdO6Qq5d_4X0jKUC6mx18PP1-w2ChvBXQTETw0"
FIREBASE_API_KEY = "AIzaSyDR1RcaMP9IOmIy7i_daFPNr3e7kmWid6o"
REFERRAL_URL_FB = "https://us-central1-gift-sheep-b21df.cloudfunctions.net/submitReferral"

def send_giftcode_referral(referral_code, user_id, proxy=None):
    params = {"referred_user_id": str(user_id), "ref_code": str(referral_code)}
    headers = {"Authorization": TOKEN_API, "User-Agent": "okhttp/5.3.2"}
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=15, proxies=proxies)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"): return {"success": True, "gold": data.get("referred_gold", 0)}
            reason = data.get("reason", "")
            if "Zaten referanslı" in reason: return {"success": False, "reason": "already_referred"}
            elif "Geçersiz kullanıcı" in reason: return {"success": False, "reason": "invalid_user"}
            elif "Aynı IP" in reason: return {"success": False, "reason": "same_ip"}
            else: return {"success": False, "reason": reason}
        elif response.status_code == 429: return {"success": False, "reason": "rate_limited"}
        else: return {"success": False, "reason": f"HTTP_{response.status_code}"}
    except: return {"success": False, "reason": "connection_error"}

def process_giftcode(user_id, target, proxy=None):
    used_data = load_used_numbers(user_id)
    ref_code = get_user_setting(user_id, "referral_code", "4094894")
    result = send_giftcode_referral(ref_code, target, proxy)
    if result.get("success"): used_data["success"].append(str(target)); save_used_numbers(user_id, used_data)
    elif result.get("reason") == "already_referred": used_data["already"].append(str(target)); save_used_numbers(user_id, used_data)
    elif result.get("reason") == "invalid_user": pass
    else: used_data["failed"].append(str(target)); save_used_numbers(user_id, used_data)
    return result

def translate_reason(reason):
    translations = {"already_referred": "هذا الرقم تمت إحالته مسبقاً", "invalid_user": "الرقم غير صالح", "same_ip": "نفس IP تم استخدامه مؤخراً", "rate_limited": "تم تجاوز عدد الطلبات", "connection_error": "خطأ في الاتصال"}
    return translations.get(reason, reason)

def create_firebase_account(email, password):
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
    params = {"key": FIREBASE_API_KEY}; payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        resp = requests.post(url, params=params, json=payload, timeout=30); data = resp.json()
        if resp.status_code == 200: return data
        return {"error": data.get('error', {}).get('message', 'Unknown')}
    except Exception as e: return {"error": str(e)}

def send_firebase_referral(access_token, referral_code, proxy=None):
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'okhttp/3.12.13'}
    payload = {"data": {"code": referral_code}}; proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        resp = requests.post(REFERRAL_URL_FB, json=payload, headers=headers, timeout=30, proxies=proxies)
        result = resp.json(); success = result.get('result', {}).get('success', False); message = result.get('result', {}).get('message', '')
        return success, message
    except Exception as e: return False, f"Connection error: {e}"

# ============================================
# 🤖 البوت ومعالجة الأوامر
# ============================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

def is_owner(user_id): return str(user_id) == str(OWNER_ID)

def is_subscribed_telegram(user_id):
    if is_owner(user_id): return True
    try:
        chat_member = bot.get_chat_member(f"@{CHANNEL_TG}", user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except: return False

def is_subscribed_youtube(user_id):
    if is_owner(user_id): return True
    data = load_user_settings(user_id); verified = data.get("youtube_verified", False)
    if verified:
        last = data.get("youtube_verify_date")
        if last:
            try:
                days = (datetime.now() - datetime.fromisoformat(last)).days
                if days > 7: return False
            except: return False
    return verified

def check_subscriptions(user_id):
    if is_owner(user_id): return True, None
    if not is_subscribed_telegram(user_id): return False, "telegram"
    if not is_subscribed_youtube(user_id): return False, "youtube"
    return True, None

def process_referral_new_user(new_user_id, referrer_id):
    if str(new_user_id) == str(referrer_id): return False, "لا يمكنك إحالة نفسك!"
    if not is_subscribed_telegram(new_user_id) or not is_subscribed_youtube(new_user_id): return False, "يجب الاشتراك أولاً!"
    referral_data = load_referral_data()
    if str(new_user_id) in referral_data.get("referred_users", {}): return False, "تمت إحالته مسبقاً!"
    if str(referrer_id) not in referral_data.get("referrals", {}):
        referral_data.setdefault("referrals", {})[str(referrer_id)] = {"count": 0, "points_earned": 0, "users": []}
    referral_data["referrals"][str(referrer_id)]["count"] += 1
    referral_data["referrals"][str(referrer_id)]["points_earned"] += REFERRAL_POINTS
    referral_data["referrals"][str(referrer_id)]["users"].append(str(new_user_id))
    referral_data.setdefault("referred_users", {})[str(new_user_id)] = str(referrer_id)
    save_referral_data(referral_data)
    current = load_user_points(referrer_id); save_user_points(referrer_id, current + REFERRAL_POINTS)
    save_user_points(new_user_id, INITIAL_POINTS)
    return True, f"حصلت على {REFERRAL_POINTS} نقطة!"

# ============================================
# 🚀 حلقة الهجوم
# ============================================
attack_status = {}; attack_mode = {}

def attack_loop(user_id, chat_id):
    uid = str(user_id); mode = attack_mode.get(uid, 'giftcode')
    start = int(get_user_setting(user_id, "start_number", DEFAULT_START)); current = start
    attempts = 0; successes = 0; banned = set()
    attack_status[uid] = {"running": True, "number": current}
    bot.send_message(chat_id, f"🚀 بدء الهجوم بوضع {mode.upper()}")
    while attack_status[uid]["running"]:
        points = load_user_points(user_id)
        if points <= 0 and not is_owner(user_id):
            link = get_referral_link(user_id)
            keyboard = InlineKeyboardMarkup(); keyboard.add(btn("🔗 رابط الإحالة", callback_data="my_referral", style="primary"))
            bot.send_message(chat_id, f"⚠️ نفدت نقاطك! شارك الرابط:\n`{link}`", parse_mode="Markdown", reply_markup=keyboard); break
        proxy, banned = get_next_proxy(banned)
        if not proxy:
            bot.send_message(chat_id, "⚠️ لا توجد بروكسيات! انتظر 5 دقائق أو أضف بروكسي.")
            time.sleep(300); banned = set(); continue
        attempts += 1; bot.send_message(chat_id, f"⏳ محاولة #{attempts}...")
        if mode == 'giftcode':
            target = str(current); current += 1; attack_status[uid]["number"] = current
            result = process_giftcode(user_id, target, proxy)
            if not result.get("success") and result.get("reason") in ["invalid_user", "already_referred"]: continue
        else:
            suffix = uuid.uuid4().hex[:8]; email = f"fb_{suffix}@temp-mail.org"
            auth = create_firebase_account(email, "Test@2026")
            if not auth or 'error' in auth: continue
            token = auth.get('idToken')
            if not token: continue
            user_code = get_user_setting(user_id, "referral_code", "W27PO5")
            if not user_code: bot.send_message(chat_id, "⚠️ أدخل كود الإحالة أولاً!"); break
            success, msg = send_firebase_referral(token, user_code, proxy)
            result = {"success": True, "gold": 0} if success else {"success": False, "reason": msg}
        if result.get("success"):
            successes += 1; new_pts = load_user_points(user_id) - 1; save_user_points(user_id, new_pts)
            bot.send_message(chat_id, f"🎉 نجاح! 💎 النقاط: {new_pts}")
            try:
                display = get_user_display(user_id)
                bot.send_message(OWNER_ID, f"✅ نجاح {mode.upper()}\n👤 {display}\n🆔 {user_id}\n💎 المتبقي: {new_pts}")
            except: pass
        else:
            reason = result.get("reason", "غير معروف"); arabic = translate_reason(reason)
            bot.send_message(chat_id, f"⚠️ فشل: {arabic}")
            if reason in ["same_ip", "rate_limited", "connection_error"]: banned.add(proxy); continue
            elif reason in ["already_used_success", "already_used_failed", "already_used_already"]: continue
            else: time.sleep(2)
    attack_status[uid]["running"] = False
    bot.send_message(chat_id, f"⏹️ توقف. نجاح: {successes} من {attempts}")

# ============================================
# 📨 أوامر البوت
# ============================================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id; first_name = message.from_user.first_name or "مستخدم"; uid = str(user_id)
    referrer_id = None
    if message.text and message.text.startswith('/start'):
        parts = message.text.split()
        if len(parts) > 1 and parts[1].isdigit(): referrer_id = int(parts[1])
    sessions = load_user_sessions()
    if uid not in sessions:
        sessions[uid] = {"first_name": first_name, "username": message.from_user.username or ""}; save_user_sessions(sessions)
    else:
        changed = False
        if sessions[uid].get("first_name") != first_name: sessions[uid]["first_name"] = first_name; changed = True
        if sessions[uid].get("username", "") != (message.from_user.username or ""): sessions[uid]["username"] = message.from_user.username or ""; changed = True
        if changed: save_user_sessions(sessions)
    sub_ok, sub_type = check_subscriptions(user_id); referral_data = load_referral_data()
    if referrer_id and uid not in referral_data.get("referred_users", {}):
        if not is_subscribed_telegram(user_id) or not is_subscribed_youtube(user_id):
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(btn("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_TG}", style="primary"))
            kb.add(btn("🎬 اشترك في يوتيوب", callback_data="verify_youtube", style="danger"))
            kb.add(btn("✅ تأكيد", callback_data=f"confirm_referral_{referrer_id}", style="success"))
            bot.reply_to(message, "🔒 اشترك أولاً.", reply_markup=kb); return
        else:
            success, msg = process_referral_new_user(user_id, referrer_id); bot.reply_to(message, msg)
    if not sub_ok:
        kb = InlineKeyboardMarkup(row_width=1)
        if sub_type == "telegram": kb.add(btn("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_TG}", style="primary"))
        elif sub_type == "youtube": kb.add(btn("🎬 اشترك في يوتيوب", callback_data="verify_youtube", style="danger"))
        kb.add(btn("✅ تحقق", callback_data="check_sub", style="success"))
        bot.reply_to(message, "🔒 اشترك وأكد يوتيوب.", reply_markup=kb); return
    kb = InlineKeyboardMarkup(row_width=2); mode = attack_mode.get(uid, 'giftcode')
    if mode == 'giftcode':
        kb.add(btn("🔑 كود الإحالة", callback_data="set_referral", style="primary"), btn("🔢 رقم البداية", callback_data="set_start", style="primary"))
    else: kb.add(btn("🔑 كود الإحالة", callback_data="set_referral", style="primary"))
    kb.add(btn("▶️ بدء", callback_data="start_attack", style="success"), btn("⏹️ إيقاف", callback_data="stop_attack", style="danger"))
    kb.add(btn("🔄 تبديل الوضع", callback_data="toggle_mode", style="primary"), btn("📊 الحالة", callback_data="status", style="primary"))
    kb.add(btn("🔗 رابط الإحالة", callback_data="my_referral", style="primary"), btn("➕ إضافة بروكسي", callback_data="user_add_proxy", style="success"))
    if is_owner(user_id): kb.add(btn("👑 قائمة المالك", callback_data="owner_commands", style="danger"))
    points = load_user_points(user_id); used = load_used_numbers(user_id); code = get_user_setting(user_id, "referral_code", "4094894")
    bot.reply_to(message, f"✨ مرحباً {first_name}!\n━━━━━━━━━━━━━━━\n💎 نقاطك: {points}\n🔑 كودك: {code}\n🔄 وضع: {mode.upper()}\n✅ نجاح: {len(used['success'])}\n━━━━━━━━━━━━━━━\nاختر من القائمة:", reply_markup=kb)

# ============================================
# 🖱️ معالج الأزرار (تم إصلاحه)
# ============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id; chat_id = call.message.chat.id; uid = str(user_id)
    try:
        if call.data == "user_add_proxy":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🔐 أرسل البروكسي (http://user:pass@ip:port):")
            bot.register_next_step_handler(msg, user_add_proxy_step, user_id); return
        if call.data.startswith("confirm_referral_"):
            ref_id = int(call.data.replace("confirm_referral_", ""))
            success, msg = process_referral_new_user(user_id, ref_id)
            bot.answer_callback_query(call.id, msg, show_alert=True); return
        if call.data == "toggle_mode":
            mode = attack_mode.get(uid, 'giftcode'); new = 'giftsheep' if mode == 'giftcode' else 'giftcode'
            attack_mode[uid] = new; bot.answer_callback_query(call.id, f"تم التبديل إلى {new.upper()}", show_alert=True)
            start_command(call.message); return
        if call.data == "start_attack":
            if attack_status.get(uid, {}).get("running", False): bot.answer_callback_query(call.id, "يعمل بالفعل!", show_alert=True); return
            points = load_user_points(user_id)
            if points <= 0 and not is_owner(user_id): bot.answer_callback_query(call.id, "نقاطك 0!", show_alert=True); return
            attack_status[uid] = {"running": True}; t = threading.Thread(target=attack_loop, args=(user_id, chat_id)); t.daemon = True; t.start()
            bot.answer_callback_query(call.id, "تم البدء!", show_alert=True); return
        if call.data == "stop_attack":
            if attack_status.get(uid, {}).get("running", False): attack_status[uid]["running"] = False; bot.answer_callback_query(call.id, "جاري الإيقاف...", show_alert=True)
            else: bot.answer_callback_query(call.id, "لا يوجد هجوم!", show_alert=True)
            return
        if call.data == "status":
            bot.answer_callback_query(call.id); points = load_user_points(user_id); used = load_used_numbers(user_id)
            mode = attack_mode.get(uid, 'giftcode'); running = attack_status.get(uid, {}).get("running", False)
            bot.send_message(chat_id, f"📊 الحالة:\n🔄 {mode.upper()}\n▶️ {'يعمل' if running else 'متوقف'}\n💎 نقاط: {points}\n✅ نجاح: {len(used['success'])}"); return
        if call.data == "my_referral":
            bot.answer_callback_query(call.id); link = get_referral_link(user_id)
            bot.reply_to(call.message, f"🔗 رابطك:\n`{link}`", parse_mode="Markdown"); return
        if call.data == "set_referral":
            bot.answer_callback_query(call.id); msg = bot.send_message(chat_id, "🔑 أرسل كود الإحالة:")
            bot.register_next_step_handler(msg, set_referral_step, user_id); return
        if call.data == "set_start":
            bot.answer_callback_query(call.id); msg = bot.send_message(chat_id, "🔢 أرسل رقم البداية (أرقام فقط):")
            bot.register_next_step_handler(msg, set_start_step, user_id); return
        if call.data == "check_sub":
            ok, _ = check_subscriptions(user_id)
            if ok: bot.answer_callback_query(call.id, "تم التحقق!", show_alert=True); start_command(call.message)
            else: bot.answer_callback_query(call.id, "لم تشترك!", show_alert=True)
            return
        if call.data == "verify_youtube":
            set_user_setting(user_id, "youtube_verified", True); set_user_setting(user_id, "youtube_verify_date", datetime.now().isoformat())
            bot.answer_callback_query(call.id, "تم تأكيد يوتيوب!", show_alert=True); start_command(call.message); return
        if call.data == "start":
            bot.answer_callback_query(call.id); start_command(call.message); return
        if call.data == "owner_commands":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "هذه القائمة للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id)
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(btn("➕ إضافة بروكسي", callback_data="owner_add_proxy", style="success"), btn("📋 قائمة البروكسيات", callback_data="owner_list_proxies", style="primary"))
            kb.add(btn("🗑️ حذف بروكسي", callback_data="owner_del_proxy", style="danger"), btn("📈 الإحصائيات", callback_data="owner_stats", style="primary"))
            kb.add(btn("🔧 تعديل النقاط", callback_data="owner_edit_points", style="success"), btn("🔙 رجوع", callback_data="start", style="danger"))
            bot.reply_to(call.message, "👑 قائمة المالك:", reply_markup=kb); return
        if call.data == "owner_stats":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id); sessions = load_user_sessions()
            if not sessions: bot.reply_to(call.message, "لا يوجد مستخدمون حتى الآن."); return
            users_list = []
            for uid_key, data in sessions.items():
                try:
                    points = load_user_points(int(uid_key)); used = load_used_numbers(int(uid_key))
                except: continue
                users_list.append({"uid": uid_key, "name": data.get("first_name", "مجهول"), "username": data.get("username", ""), "points": points, "success": len(used.get("success", [])), "failed": len(used.get("failed", [])), "already": len(used.get("already", []))})
            users_list.sort(key=lambda x: x["points"], reverse=True)
            total_points = sum(u["points"] for u in users_list); total_success = sum(u["success"] for u in users_list); total_failed = sum(u["failed"] for u in users_list)
            header = (f"📈 إحصائيات المشتركين\n━━━━━━━━━━━━━━━\n👥 عدد المستخدمين: {len(users_list)}\n💎 مجموع النقاط: {total_points}\n✅ مجموع النجاح: {total_success}\n❌ مجموع الفشل: {total_failed}\n━━━━━━━━━━━━━━━\n\n")
            body = ""
            for i, u in enumerate(users_list, 1):
                body += f"{i}. 👤 {u['name']}"
                if u["username"]: body += f" (@{u['username']})"
                body += f"\n     🆔 {u['uid']}\n     💎 {u['points']}  |  ✅ {u['success']}  |  ❌ {u['failed']}  |  🔁 {u['already']}\n\n"
            full = header + body; max_len = 4000
            if len(full) <= max_len: bot.send_message(chat_id, full)
            else:
                bot.send_message(chat_id, header); chunk = ""
                for line in body.split("\n"):
                    if len(chunk) + len(line) + 1 > max_len: bot.send_message(chat_id, chunk); chunk = ""
                    chunk += line + "\n"
                if chunk.strip(): bot.send_message(chat_id, chunk)
            return
        if call.data == "owner_edit_points":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, "🔧 تعديل نقاط مستخدم\n━━━━━━━━━━━━━━━\nأرسل بالصيغة التالية:\n`@username النقاط`\nأو\n`user_id النقاط`\n\nمثال:\n`@ali 100`\n`6366853738 100`", parse_mode="Markdown")
            bot.register_next_step_handler(call.message, edit_points_step); return
        if call.data == "owner_add_proxy":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id); msg = bot.send_message(chat_id, "أرسل البروكسي (http://user:pass@ip:port):")
            bot.register_next_step_handler(msg, add_proxy_step); return
        if call.data == "owner_list_proxies":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id); proxies = get_all_proxies()
            bot.reply_to(call.message, "\n".join(proxies) if proxies else "لا يوجد بروكسيات."); return
        if call.data == "owner_del_proxy":
            if not is_owner(user_id): bot.answer_callback_query(call.id, "للمالك فقط.", show_alert=True); return
            bot.answer_callback_query(call.id); msg = bot.send_message(chat_id, "أرسل البروكسي للحذف:")
            bot.register_next_step_handler(msg, del_proxy_step); return
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"⚠️ خطأ في معالجة الزر: {e}")
        try: bot.answer_callback_query(call.id)
        except: pass

# ============================================
# 📝 الخطوات النصية (بدون تغيير)
# ============================================
def set_referral_step(message, user_id):
    set_user_setting(user_id, "referral_code", message.text.strip()); bot.reply_to(message, f"✅ تم تعيين الكود: {message.text.strip()}")

def set_start_step(message, user_id):
    if message.text.strip().isdigit(): set_user_setting(user_id, "start_number", int(message.text.strip())); bot.reply_to(message, f"✅ تم تعيين رقم البداية: {message.text.strip()}")
    else: bot.reply_to(message, "❌ أرقام فقط!")

def user_add_proxy_step(message, user_id):
    proxy = message.text.strip()
    if not proxy.startswith("http"): proxy = f"http://{proxy}"
    user_proxies = load_user_proxies()
    if proxy not in user_proxies:
        user_proxies.append(proxy); save_user_proxies(user_proxies)
        try: bot.send_message(OWNER_ID, f"🔐 بروكسي جديد من {message.from_user.first_name} (ID: {user_id}):\n`{proxy}`", parse_mode="Markdown")
        except: pass
        bot.reply_to(message, "✅ تمت إضافة البروكسي!")
    else: bot.reply_to(message, "موجود مسبقاً.")

def add_proxy_step(message):
    if not is_owner(message.from_user.id): return
    proxy = message.text.strip()
    if not proxy.startswith("http"): proxy = f"http://{proxy}"
    proxies = load_proxies()
    if proxy not in proxies: proxies.append(proxy); save_proxies(proxies); bot.reply_to(message, "✅ تمت الإضافة.")
    else: bot.reply_to(message, "موجود مسبقاً.")

def del_proxy_step(message):
    if not is_owner(message.from_user.id): return
    proxy = message.text.strip(); proxies = load_proxies()
    if proxy in proxies: proxies.remove(proxy); save_proxies(proxies); bot.reply_to(message, "✅ تم الحذف.")
    else: bot.reply_to(message, "❌ غير موجود.")

def edit_points_step(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2: bot.reply_to(message, "❌ الصيغة: `@username النقاط` أو `user_id النقاط`", parse_mode="Markdown"); return
    identifier = parts[0]
    try: new_points = int(parts[1])
    except: bot.reply_to(message, "❌ النقاط يجب أن تكون رقماً."); return
    target_id = find_user_id_by_input(identifier)
    if not target_id: bot.reply_to(message, f"❌ لم أجد مستخدماً بالمعرف: {identifier}\nتأكد أن المستخدم استخدم /start مرة على الأقل."); return
    save_user_points(target_id, new_points); display = get_user_display(target_id)
    bot.reply_to(message, f"✅ تم تعديل النقاط بنجاح\n━━━━━━━━━━━━━━━\n👤 {display}\n🆔 {target_id}\n💎 النقاط الجديدة: {new_points}")

# ============================================
# 🖥️ Flask
# ============================================
app = Flask(__name__)
@app.route('/')
def home(): return "bot running", 200
@app.route('/health')
def health(): return "ok", 200
def run_flask(): app.run(host="0.0.0.0", port=8080)

# ============================================
# ▶️ التشغيل
# ============================================
if __name__ == "__main__":
    try: bot.remove_webhook(); print("✅ تم حذف الويب هوك.")
    except Exception as e: print(f"⚠️ {e}")
    threading.Thread(target=run_flask, daemon=True).start(); print("✅ البوت يعمل!")
    while True:
        try: bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e: print(f"⚠️ خطأ: {e} — إعادة المحاولة بعد 5 ثوانٍ..."); time.sleep(5)
