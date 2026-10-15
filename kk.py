#!/usr/bin/env python3
# kk.py — Main bot + Flask Health + Self-Ping + Robust Polling
import os, sys, json, time, random, sqlite3, threading, uuid, csv, io, logging, html
from datetime import datetime, timedelta
from collections import defaultdict, deque
from queue import PriorityQueue
import requests, telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ═══════════════════════ CONFIG ═══════════════════════
MAIN_BOT_TOKEN     = "8710044999:AAEZH3rH3RmkCw09altcLIrFwFTZEWMlQtg"
OWNER_ID = 6366853738
CHANNEL_TG = "thaish12"
CHANNEL_YT = "https://youtube.com/@tahish159?si=5ehTRVzB7WOnOj5s"
BOT_USERNAME = "Rame124673_bot"

INITIAL_POINTS = 20
REFERRAL_POINTS = 10
DAILY_BASE = 5
DAILY_STREAK_BONUS = 2
DAILY_STREAK_MAX = 10

DB_FILE = "bot.db"
OLD_DATA_DIR = "user_data"
PROXIES_FILE = "proxies.txt"
AUDIT_LOG = "audit.log"
WORKERS = 2
RATE_LIMIT_PER_MIN = 30
USER_PROXY_LIMIT = 2000
SELF_PING_INTERVAL = 600   # كل 10 دقائق

GC_BASE_URL   = "https://giftcode.betelgeuse.app"
GC_LEADERS    = f"{GC_BASE_URL}/api/leaders"
GC_REFER      = f"{GC_BASE_URL}/api/referrer"
GC_REF_CODE   = "4094894"
GC_TOKEN      = os.getenv("GC_TOKEN", "")
GC_AUTO_INTERVAL   = 1800
PORT              = int(os.getenv("PORT", "10000"))

# ═══════════════════════ LOGGING ═══════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger("bot")

# ═══════════════════════ DB ═══════════════════════
_db_lock = threading.Lock()
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")


def _init_db():
    with _db_lock:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            first_name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            lang TEXT DEFAULT 'ar',
            points INTEGER DEFAULT 20,
            streak INTEGER DEFAULT 0,
            last_daily TEXT DEFAULT '',
            youtube_verified INTEGER DEFAULT 0,
            youtube_date TEXT DEFAULT '',
            referral_code TEXT DEFAULT '4094894',
            start_number INTEGER DEFAULT 4084879,
            mode TEXT DEFAULT 'giftcode',
            banned INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, mode TEXT, target TEXT,
            result TEXT, proxy TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_hist_u ON history(user_id);
        CREATE INDEX IF NOT EXISTS ix_hist_ts ON history(ts);
        CREATE TABLE IF NOT EXISTS proxies(
            proxy TEXT PRIMARY KEY,
            owner INTEGER DEFAULT 0,
            success INTEGER DEFAULT 0,
            fail INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_proxies_owner ON proxies(owner);
        CREATE TABLE IF NOT EXISTS referrals(
            new_user INTEGER PRIMARY KEY,
            referrer INTEGER,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS seen_ids(
            uid TEXT PRIMARY KEY,
            ref_code TEXT,
            result TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()


def db_exec(query, params=(), fetch=None):
    with _db_lock:
        cur = conn.execute(query, params)
        if fetch == "one":
            r = cur.fetchone(); conn.commit(); return r
        if fetch == "all":
            r = cur.fetchall(); conn.commit(); return r
        conn.commit()
        return cur


def ensure_user(user_id, first_name="", username=""):
    r = db_exec("SELECT user_id FROM users WHERE user_id=?", (user_id,), "one")
    if not r:
        db_exec("INSERT INTO users(user_id,first_name,username,points) VALUES(?,?,?,?)",
                (user_id, first_name, username, INITIAL_POINTS))
    else:
        db_exec("UPDATE users SET first_name=?, username=? WHERE user_id=?",
                (first_name, username, user_id))


def get_user(user_id):
    return db_exec("SELECT * FROM users WHERE user_id=?", (user_id,), "one")


def set_user(user_id, **kw):
    if not kw: return
    cols = ", ".join(f"{k}=?" for k in kw)
    db_exec(f"UPDATE users SET {cols} WHERE user_id=?", (*kw.values(), user_id))


def add_points(user_id, delta):
    db_exec("UPDATE users SET points=points+? WHERE user_id=?", (delta, user_id))


def get_points(user_id):
    r = db_exec("SELECT points FROM users WHERE user_id=?", (user_id,), "one")
    return r["points"] if r else INITIAL_POINTS


def log_history(user_id, mode, target, result, proxy=""):
    db_exec("INSERT INTO history(user_id,mode,target,result,proxy) VALUES(?,?,?,?,?)",
            (user_id, mode, str(target), result, proxy or ""))


def history_stats(user_id):
    r = db_exec("""SELECT
        SUM(CASE WHEN result='success' THEN 1 ELSE 0 END) AS s,
        SUM(CASE WHEN result='failed' THEN 1 ELSE 0 END) AS f,
        SUM(CASE WHEN result='already' THEN 1 ELSE 0 END) AS a
        FROM history WHERE user_id=?""", (user_id,), "one")
    return {"success": r["s"] or 0, "failed": r["f"] or 0, "already": r["a"] or 0}


def get_setting(key, default=None):
    r = db_exec("SELECT value FROM settings WHERE key=?", (key,), "one")
    return r["value"] if r else default


def set_setting(key, value):
    db_exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (key, str(value)))


def audit(actor, action, target=""):
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {actor} | {action} | {target}\n")
    except Exception:
        pass


# ═══════════ MIGRATION + REIMPORT ═══════════
def migrate_legacy():
    if not os.path.isdir(OLD_DATA_DIR):
        return
    done = get_setting("migrated")
    if done:
        return
    migrated = 0
    for fn in os.listdir(OLD_DATA_DIR):
        try:
            if fn.startswith("points_") and fn.endswith(".json"):
                uid = int(fn.replace("points_", "").replace(".json", ""))
                with open(os.path.join(OLD_DATA_DIR, fn), encoding="utf-8") as f:
                    pts = json.load(f).get("points", INITIAL_POINTS)
                ensure_user(uid)
                set_user(uid, points=pts)
                migrated += 1
            elif fn == "user_sessions.json":
                with open(os.path.join(OLD_DATA_DIR, fn), encoding="utf-8") as f:
                    data = json.load(f)
                for uid, s in data.items():
                    ensure_user(int(uid), s.get("first_name", ""),
                                s.get("username", ""))
        except Exception as e:
            log.warning(f"migrate {fn}: {e}")
    set_setting("migrated", migrated)
    log.info(f"Migrated {migrated} users from JSON")


def reimport_sessions(verbose=False):
    if not os.path.isdir(OLD_DATA_DIR):
        return 0, 0
    added_users = 0
    added_points = 0

    sp = os.path.join(OLD_DATA_DIR, "user_sessions.json")
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                data = json.load(f)
            for uid_str, s in data.items():
                try:
                    uid = int(uid_str)
                except Exception:
                    continue
                existing = db_exec(
                    "SELECT user_id, first_name, username FROM users WHERE user_id=?",
                    (uid,), "one")
                if not existing:
                    ensure_user(uid, s.get("first_name", "") or "",
                                s.get("username", "") or "")
                    added_users += 1
                else:
                    upd = {}
                    if not existing["first_name"] and s.get("first_name"):
                        upd["first_name"] = s["first_name"]
                    if not existing["username"] and s.get("username"):
                        upd["username"] = s["username"]
                    if upd:
                        set_user(uid, **upd)
        except Exception as e:
            log.warning(f"reimport sessions: {e}")

    for fn in os.listdir(OLD_DATA_DIR):
        if not (fn.startswith("points_") and fn.endswith(".json")):
            continue
        try:
            uid = int(fn.replace("points_", "").replace(".json", ""))
        except Exception:
            continue
        try:
            with open(os.path.join(OLD_DATA_DIR, fn), encoding="utf-8") as f:
                pts = json.load(f).get("points", INITIAL_POINTS)
        except Exception:
            continue
        existing = db_exec("SELECT user_id FROM users WHERE user_id=?",
                           (uid,), "one")
        if not existing:
            ensure_user(uid)
            set_user(uid, points=pts)
            added_points += 1

    if verbose:
        log.info(f"reimport: +{added_users} users, +{added_points} points")
    return added_users, added_points


# ═══════════════════════ I18N ═══════════════════════
T = {
    "ar": {
        "welcome": "✨ مرحباً {name}!",
        "points": "نقاطك", "code": "كودك", "mode": "وضع",
        "start_num": "رقم البداية", "proxies": "بروكسياتك",
        "success": "نجاح", "choose": "اختر من القائمة:",
        "not_sub": "🔒 اشترك وأكد يوتيوب.", "sub_first": "اشترك أولاً.",
        "start_attack": "▶️ بدء", "stop_attack": "⏹️ إيقاف",
        "toggle_mode": "🔄 تبديل الوضع", "status": "📊 الحالة",
        "referral": "🔗 رابط الإحالة", "proxy_menu_btn": "🛠️ البروكسيات",
        "proxy_help_btn": "📘 تعليمات البروكسي",
        "owner": "👑 المالك", "set_referral": "🔑 كود الإحالة",
        "set_start": "🔢 رقم البداية", "daily": "🎁 هدية يومية",
        "leaderboard": "🏆 المتصدرون", "quick_menu": "⌨️ قائمة سريعة",
        "my_stats": "📊 إحصائياتي", "lang": "🌐 اللغة",
        "gc_panel_btn": "🎯 لوحة GiftCode",
        "refs_btn": "🏅 المتصدرون بالإحالة",

        "proxy_menu_title": "🛠️ <b>إدارة البروكسيات</b>\n━━━━━━━━━━━━━━━\nاختر العملية:",
        "proxy_add_btn": "➕ إضافة بروكسي",
        "proxy_list_btn": "📋 عرض بروكسياتي",
        "proxy_test_btn": "🧪 اختبار بروكسياتي",
        "proxy_del_btn": "🗑️ حذف بروكسياتي",
        "proxy_back": "🔙 رجوع",

        "my_proxies_title": "📋 <b>بروكسياتك ({total})</b>",
        "my_proxies_empty": "📭 لا توجد بروكسيات محفوظة.\nاستخدم «➕ إضافة بروكسي» أولاً.",
        "my_proxies_stats": "✅ {s} | ❌ {f}",
        "testing_proxies": "🧪 جاري اختبار {n} بروكسي...",
        "test_result": "🧪 <b>نتيجة الاختبار</b>\n━━━━━━━━━━━━━━━\n✅ حي: {alive}\n❌ ميت: {dead}\n📊 الإجمالي: {total}",
        "del_proxies_confirm": "⚠️ <b>تأكيد الحذف</b>\n\nهل تريد حذف <b>كل</b> بروكسياتك الخاصة ({n})؟\n\n<i>لا يمكن التراجع.</i>",
        "del_proxies_yes": "🗑️ نعم، احذف",
        "del_proxies_done": "✅ تم حذف {n} بروكسي",
        "no_own_proxies": "📭 لا توجد بروكسيات خاصة بك.",
        "proxy_limit_reached": "⚠️ وصلت للحد الأقصى ({limit} بروكسي). احذف بعضاً أولاً.",

        "gc_panel_title": "🎯 <b>لوحة GiftCode</b>\nاختر من القائمة:",
        "gc_top_gold": "🥇 متصدرون الذهب",
        "gc_top_diamond": "💎 متصدرون الألماس",
        "gc_tasks": "📋 آخر المهام",
        "gc_top_refs": "🏅 المتصدرون بالإحالة",
        "gc_harvest": "🎯 مسح الإحالات",
        "back": "🔙 رجوع",

        "gold_lb_title": "🏆 <b>أعلى اللاعبين — الذهب (GP)</b>",
        "diamond_lb_title": "💎 <b>أعلى اللاعبين — الألماس</b>",
        "tasks_title": "📋 <b>آخر المهام المكتملة</b>",
        "refs_title": "🏅 <b>أكثر المُحيلين</b>",
        "no_gold": "🏆 <b>لا يوجد متصدرون حالياً.</b>",
        "no_diamond": "💎 <b>لا توجد بيانات.</b>",
        "no_tasks": "📭 <b>لا توجد مهام حديثة.</b>",
        "no_refs": "🏅 <b>لا توجد إحالات بعد.</b>",

        "owner_panel": "👑 <b>لوحة المالك</b>",
        "owner_add_proxy": "➕ بروكسي",
        "owner_list_proxies": "📋 القائمة",
        "owner_test_proxies": "🧪 اختبار",
        "owner_del_proxy": "🗑️ حذف",
        "owner_cleanup": "🧹 تنظيف الميتة",
        "owner_proxy_stats": "📊 إحصائيات",
        "owner_stats": "📈 إحصائيات",
        "owner_edit_points": "🔧 نقاط",
        "owner_broadcast": "📢 بث",
        "owner_live": "📡 مباشر",
        "owner_estop": "🛑 إيقاف طارئ",

        "cancel": "❌ إلغاء",
        "canceled": "❌ ملغي",
        "fetching": "⏳ جلب...",
        "fetch_failed": "❌ فشل الجلب: {err}",
        "owner_only": "للمالك فقط",
        "banned": "🚫 محظور",
        "rate_limit": "⚠️ تمهل",
        "not_subscribed": "❌ لم تشترك",
        "done": "✅ تم",
        "youtube_ok": "✅ يوتيوب",

        "status_on": "ON", "status_off": "OFF",
        "no_points": "💎 0 نقاط",
        "already_running": "يعمل بالفعل",
        "attack_started": "▶️ بدأ",
        "stopping": "⏹️ جاري الإيقاف",
        "no_proxies": ("⚠️ <b>لا توجد بروكسيات في القائمة</b>\n"
                       "━━━━━━━━━━━━━━━\n"
                       "يعمل البوت حالياً <b>باتصال مباشر</b> — النتائج ستكون محدودة.\n\n"
                       "💡 <b>لتحسين النتائج:</b> أضف بروكسي من الزر «🛠️ البروكسيات»."),
        "send_proxy": "🔐 أرسل البروكسي:",
        "send_referral": "🔑 أرسل كود الإحالة:",
        "send_start": "🔢 أرسل رقم البداية:",

        "daily_claimed": "⏰ استلمتها اليوم",
        "daily_reward": "🎁 +{reward} نقطة\n🔥 يوم {streak}",
        "stats_title": "📊 إحصائياتك",
        "lb_title": "🏆 <b>المتصدرون — أفضل 10</b>",
        "nothing": "لا يوجد",
        "edit_points_hint": "🔧 @user points أو uid points",
        "broadcast_hint": "📢 أرسل نص الإعلان:",
        "owner_add_proxy_hint": "أرسل البروكسي (سطر لكل بروكسي):",
        "owner_del_proxy_hint": "أرسل البروكسي للحذف:",
        "proxy_added": "✅ تمت",
        "proxy_exists": "موجود",
        "numbers_only": "❌ أرقام فقط",
        "wrong_format": "صيغة خاطئة",
        "harvesting": "بدأ المسح...",
        "harvest_busy": "⏳ مسح آخر يعمل",
        "harvest_done": ("✅ انتهى المسح\n"
                          "✅ نجح: {ok}\n"
                          "🚫 IP محد: {ip}\n"
                          "🔁 مُحال: {already}\n"
                          "❌ غير صالح: {invalid}\n"
                          "⏭️ متجاوز: {skipped}\n"
                          "💰 Gold: {gold}"),
        "err_generic": "❌ خطأ: {err}",

        "proxy_help_text": (
            "📘 <b>دليل إضافة البروكسيات</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 <b>الصيغ المدعومة:</b>\n"
            "• <code>IP:PORT</code>\n"
            "• <code>user:pass@IP:PORT</code>\n"
            "• <code>http://IP:PORT</code>\n"
            "• <code>http://user:pass@IP:PORT</code>\n\n"
            "⚠️ <b>HTTP فقط</b> — لا SOCKS\n\n"
            "📥 <b>الإضافة بالجملة:</b>\n"
            "أرسل كل بروكسي في <b>سطر منفصل</b>:\n\n"
            "<code>192.168.1.1:8080\n"
            "10.0.0.5:3128\n"
            "172.16.0.3:8000</code>\n\n"
            "✅ = تُضاف كلها دفعة واحدة\n"
            "❌ = لا مسافات، لا فواصل\n\n"
            "🌐 <b>مواقع بروكسيات مجانية:</b>\n"
            "• free-proxy-list.net\n"
            "• proxyscrape.com\n"
            "• geonode.com/free-proxy-list\n"
            "• proxy-list.download\n\n"
            "💡 <b>نصائح:</b>\n"
            "• اختر <b>HTTP</b> و <b>Elite</b>\n"
            "• أضف 100+ للحصول على 10-20 عاملة\n"
            "• المجانية تعيش ساعات — البوت يصفّي الميتة تلقائياً\n"
            "• كلما زاد العدد → زادت النجاحات"),
    },
    "en": {
        "welcome": "✨ Welcome {name}!",
        "points": "Points", "code": "Code", "mode": "Mode",
        "start_num": "Start number", "proxies": "Your proxies",
        "success": "Success", "choose": "Choose:",
        "not_sub": "🔒 Subscribe & verify YouTube.", "sub_first": "Subscribe first.",
        "start_attack": "▶️ Start", "stop_attack": "⏹️ Stop",
        "toggle_mode": "🔄 Toggle Mode", "status": "📊 Status",
        "referral": "🔗 Referral Link", "proxy_menu_btn": "🛠️ Proxies",
        "proxy_help_btn": "📘 Proxy Guide",
        "owner": "👑 Owner", "set_referral": "🔑 Referral Code",
        "set_start": "🔢 Start Number", "daily": "🎁 Daily Gift",
        "leaderboard": "🏆 Leaderboard", "quick_menu": "⌨️ Quick Menu",
        "my_stats": "📊 My Stats", "lang": "🌐 Language",
        "gc_panel_btn": "🎯 GiftCode Panel",
        "refs_btn": "🏅 Top Referrers",

        "proxy_menu_title": "🛠️ <b>Proxy Management</b>\n━━━━━━━━━━━━━━━\nChoose:",
        "proxy_add_btn": "➕ Add Proxy",
        "proxy_list_btn": "📋 My Proxies",
        "proxy_test_btn": "🧪 Test My Proxies",
        "proxy_del_btn": "🗑️ Delete My Proxies",
        "proxy_back": "🔙 Back",

        "my_proxies_title": "📋 <b>Your Proxies ({total})</b>",
        "my_proxies_empty": "📭 No saved proxies.\nUse «➕ Add Proxy» first.",
        "my_proxies_stats": "✅ {s} | ❌ {f}",
        "testing_proxies": "🧪 Testing {n} proxies...",
        "test_result": "🧪 <b>Test Result</b>\n━━━━━━━━━━━━━━━\n✅ Alive: {alive}\n❌ Dead: {dead}\n📊 Total: {total}",
        "del_proxies_confirm": "⚠️ <b>Confirm Delete</b>\n\nDelete <b>all</b> your own proxies ({n})?\n\n<i>Cannot be undone.</i>",
        "del_proxies_yes": "🗑️ Yes, delete",
        "del_proxies_done": "✅ Deleted {n} proxies",
        "no_own_proxies": "📭 No own proxies.",
        "proxy_limit_reached": "⚠️ Reached max ({limit}). Delete some first.",

        "gc_panel_title": "🎯 <b>GiftCode Panel</b>\nChoose:",
        "gc_top_gold": "🥇 Top Gold",
        "gc_top_diamond": "💎 Top Diamonds",
        "gc_tasks": "📋 Recent Tasks",
        "gc_top_refs": "🏅 Top Referrers",
        "gc_harvest": "🎯 Harvest Referrals",
        "back": "🔙 Back",

        "gold_lb_title": "🏆 <b>Top Players — Gold (GP)</b>",
        "diamond_lb_title": "💎 <b>Top Players — Diamonds</b>",
        "tasks_title": "📋 <b>Recent Completed Tasks</b>",
        "refs_title": "🏅 <b>Top Referrers</b>",
        "no_gold": "🏆 <b>No leaderboard yet.</b>",
        "no_diamond": "💎 <b>No data.</b>",
        "no_tasks": "📭 <b>No recent tasks.</b>",
        "no_refs": "🏅 <b>No referrals yet.</b>",

        "owner_panel": "👑 <b>Owner Panel</b>",
        "owner_add_proxy": "➕ Proxy",
        "owner_list_proxies": "📋 List",
        "owner_test_proxies": "🧪 Test",
        "owner_del_proxy": "🗑️ Delete",
        "owner_cleanup": "🧹 Cleanup Dead",
        "owner_proxy_stats": "📊 Proxy Stats",
        "owner_stats": "📈 Stats",
        "owner_edit_points": "🔧 Points",
        "owner_broadcast": "📢 Broadcast",
        "owner_live": "📡 Live",
        "owner_estop": "🛑 E-Stop",

        "cancel": "❌ Cancel",
        "canceled": "❌ Canceled",
        "fetching": "⏳ Fetching...",
        "fetch_failed": "❌ Fetch failed: {err}",
        "owner_only": "Owner only",
        "banned": "🚫 Banned",
        "rate_limit": "⚠️ Slow down",
        "not_subscribed": "❌ Not subscribed",
        "done": "✅ Done",
        "youtube_ok": "✅ YouTube",

        "status_on": "ON", "status_off": "OFF",
        "no_points": "💎 0 points",
        "already_running": "Already running",
        "attack_started": "▶️ Started",
        "stopping": "⏹️ Stopping",
        "no_proxies": ("⚠️ <b>No proxies available</b>\n"
                       "━━━━━━━━━━━━━━━\n"
                       "Running with <b>direct connection</b> — limited results.\n\n"
                       "💡 <b>To improve:</b> add a proxy via «🛠️ Proxies»."),
        "send_proxy": "🔐 Send the proxy:",
        "send_referral": "🔑 Send the referral code:",
        "send_start": "🔢 Send the start number:",

        "daily_claimed": "⏰ Already claimed today",
        "daily_reward": "🎁 +{reward} points\n🔥 Day {streak}",
        "stats_title": "📊 Your Stats",
        "lb_title": "🏆 <b>Leaderboard — Top 10</b>",
        "nothing": "Nothing",
        "edit_points_hint": "🔧 @user points or uid points",
        "broadcast_hint": "📢 Send the broadcast text:",
        "owner_add_proxy_hint": "Send proxies (one per line):",
        "owner_del_proxy_hint": "Send the proxy to delete:",
        "proxy_added": "✅ Added",
        "proxy_exists": "Already exists",
        "numbers_only": "❌ Numbers only",
        "wrong_format": "Wrong format",
        "harvesting": "Harvest started...",
        "harvest_busy": "⏳ Harvest already running",
        "harvest_done": ("✅ Harvest finished\n"
                          "✅ Success: {ok}\n"
                          "🚫 IP limited: {ip}\n"
                          "🔁 Already: {already}\n"
                          "❌ Invalid: {invalid}\n"
                          "⏭️ Skipped: {skipped}\n"
                          "💰 Gold: {gold}"),
        "err_generic": "❌ Error: {err}",

        "proxy_help_text": (
            "📘 <b>Proxy Setup Guide</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 <b>Supported formats:</b>\n"
            "• <code>IP:PORT</code>\n"
            "• <code>user:pass@IP:PORT</code>\n"
            "• <code>http://IP:PORT</code>\n"
            "• <code>http://user:pass@IP:PORT</code>\n\n"
            "⚠️ <b>HTTP only</b> — no SOCKS\n\n"
            "📥 <b>Batch add:</b>\n"
            "Send each proxy on <b>a separate line</b>:\n\n"
            "<code>192.168.1.1:8080\n"
            "10.0.0.5:3128\n"
            "172.16.0.3:8000</code>\n\n"
            "✅ = all added at once\n"
            "❌ = no spaces, no commas\n\n"
            "🌐 <b>Free proxy sites:</b>\n"
            "• free-proxy-list.net\n"
            "• proxyscrape.com\n"
            "• geonode.com/free-proxy-list\n"
            "• proxy-list.download\n\n"
            "💡 <b>Tips:</b>\n"
            "• Pick <b>HTTP</b> + <b>Elite</b>\n"
            "• Add 100+ to get 10-20 alive\n"
            "• Free proxies die fast — bot auto-filters dead ones\n"
            "• More proxies → more success"),
    },
}


def tr(uid, key, **kw):
    u = get_user(uid)
    lang = u["lang"] if u else "ar"
    s = T.get(lang, T["ar"]).get(key, key)
    return s.format(**kw) if kw else s


# ═══════════════════════ RATE LIMIT ═══════════════════════
_rl = defaultdict(deque)


def rate_limited(uid, limit=RATE_LIMIT_PER_MIN):
    now = time.time()
    dq = _rl[uid]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= limit:
        return True
    dq.append(now)
    return False


# ═══════════════════════ PROXIES ═══════════════════════
def load_file_proxies(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def add_proxy(proxy, owner=0):
    if not proxy.startswith("http"):
        proxy = f"http://{proxy}"
    try:
        db_exec("INSERT OR IGNORE INTO proxies(proxy,owner) VALUES(?,?)", (proxy, owner))
        return True
    except Exception:
        return False


def del_proxy(proxy):
    db_exec("DELETE FROM proxies WHERE proxy=?", (proxy,))


def count_owner_proxies(uid):
    r = db_exec("SELECT COUNT(*) c FROM proxies WHERE owner=? AND banned=0",
                (uid,), "one")
    return r["c"] if r else 0


def count_general_proxies():
    r = db_exec("SELECT COUNT(*) c FROM proxies WHERE owner=0 AND banned=0",
                fetch="one")
    return r["c"] if r else 0


def all_proxies(owner=None):
    file_p = load_file_proxies(PROXIES_FILE)
    if owner is None:
        rows = db_exec("SELECT proxy FROM proxies WHERE banned=0", fetch="all")
    else:
        rows = db_exec(
            "SELECT proxy FROM proxies WHERE banned=0 AND (owner=0 OR owner=?)",
            (owner,), "all")
    db_p = [r["proxy"] for r in rows]
    seen = set()
    out = []
    for p in file_p + db_p:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def user_own_proxies(uid, limit=100):
    rows = db_exec(
        """SELECT proxy, success, fail FROM proxies
           WHERE owner=? AND banned=0
           ORDER BY success DESC, added_at DESC LIMIT ?""",
        (uid, limit), "all")
    return rows


def test_proxy(proxy, timeout=6):
    try:
        r = requests.get("https://httpbin.org/ip",
                         proxies={"http": proxy, "https": proxy}, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def batch_test(proxies, workers=20):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(test_proxy, proxies))
    return [p for p, ok in zip(proxies, results) if ok]


def proxy_score(proxy, success):
    if not proxy:
        return
    col = "success" if success else "fail"
    db_exec(f"UPDATE proxies SET {col}={col}+1 WHERE proxy=?", (proxy,))


def best_proxies(n=30, owner=None):
    if owner is None:
        rows = db_exec(
            """SELECT proxy, success, fail FROM proxies
               WHERE banned=0 AND (success+fail)>=2
               ORDER BY CAST(success AS REAL)/(success+fail+1) DESC LIMIT ?""",
            (n,), "all")
    else:
        rows = db_exec(
            """SELECT proxy, success, fail FROM proxies
               WHERE banned=0 AND (owner=0 OR owner=?)
                 AND (success+fail)>=2
               ORDER BY CAST(success AS REAL)/(success+fail+1) DESC LIMIT ?""",
            (owner, n), "all")
    return [r["proxy"] for r in rows]


def pick_proxy(banned, owner=None):
    pool = all_proxies(owner)
    if not pool:
        return None
    available = [p for p in pool if p not in banned]
    if not available:
        return None
    ranked = best_proxies(30, owner)
    preferred = [p for p in ranked if p in available]
    if preferred and random.random() < 0.7:
        return random.choice(preferred)
    return random.choice(available)


# ═══════════════════════ GiftCode CLIENT ═══════════════════════
GC_DEFAULT_HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Accept-Encoding": "gzip",
}


class GiftCodeClient:
    def __init__(self, ref_code=GC_REF_CODE, token=GC_TOKEN,
                 proxies_file=PROXIES_FILE):
        self.ref_code = str(ref_code)
        self.token = token or ""
        self.proxies_file = proxies_file
        self._p_idx = 0
        self._lock = threading.Lock()

    def _load_proxies(self):
        out = []
        for line in load_file_proxies(self.proxies_file):
            if not line.startswith("http"):
                line = "http://" + line
            out.append(line)
        return out

    def _next_proxy(self, exclude=None):
        exclude = exclude or set()
        pool = self._load_proxies()
        if not pool:
            return None
        with self._lock:
            n = len(pool)
            for _ in range(n):
                p = pool[self._p_idx % n]
                self._p_idx += 1
                if p not in exclude:
                    return p
        return None

    def _req(self, method, url, proxy=None, use_token=False, **kw):
        headers = dict(GC_DEFAULT_HEADERS)
        if use_token and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if "headers" in kw:
            headers.update(kw.pop("headers"))
        proxies = {"http": proxy, "https": proxy} if proxy else None
        return requests.request(method, url, headers=headers,
                                proxies=proxies, timeout=20, **kw)

    def fetch_leaders(self):
        r = requests.get(GC_LEADERS, headers=GC_DEFAULT_HEADERS, timeout=15)
        r.raise_for_status()
        d = r.json()

        gold = [{
            "name": p.get("name") or "?",
            "value": p.get("gold", 0) or 0,
        } for p in d.get("top_gold", []) or []]

        diamond = [{
            "name": p.get("name") or "?",
            "value": p.get("diamond", 0) or 0,
        } for p in d.get("top_diamond", []) or []]

        tasks = [{
            "name": t.get("name") or "?",
            "company": t.get("company") or "?",
            "offer": t.get("offer_name") or "?",
            "gold": t.get("gold_earned", 0) or 0,
            "completed": t.get("completed_at") or "",
        } for t in d.get("recent_tasks", []) or []]

        purchases = [{
            "user_id": str(p.get("user_id") or ""),
            "name": p.get("user_name") or "?",
            "product": (p.get("product_title_en") or p.get("product_title_tr") or "?"),
            "currency": p.get("currency") or "",
            "time": p.get("purchase_time") or "",
        } for p in d.get("recent_purchases", []) or []]

        return {"gold": gold, "diamond": diamond,
                "tasks": tasks, "purchases": purchases}

    def collect_ids(self, leaders=None):
        if leaders is None:
            leaders = self.fetch_leaders()
        numeric, hashed = set(), set()
        for p in leaders["purchases"]:
            uid = p.get("user_id") or ""
            if not uid:
                continue
            try:
                if uid.isdigit():
                    numeric.add(int(uid))
                else:
                    hashed.add(uid)
            except Exception:
                continue
        return sorted(numeric), sorted(hashed)

    def refer(self, target_id, proxy=None):
        params = {"referred_user_id": str(target_id), "ref_code": self.ref_code}
        try:
            r = self._req("GET", GC_REFER, proxy=proxy, use_token=True, params=params)
            if r.status_code != 200:
                return {"success": False, "reason": f"HTTP_{r.status_code}"}
            return r.json()
        except Exception as e:
            return {"success": False, "reason": f"CONN:{e}"}

    def harvest(self, max_attempts=None, progress_cb=None, delay=None):
        result = {"ok": 0, "ip_limit": 0, "already": 0, "invalid": 0,
                  "gold": 0, "hits": [], "reason": "", "attempts": 0,
                  "skipped_seen": 0}

        proxy_pool = self._load_proxies()
        if delay is None:
            delay = max(0.5, 3.0 / max(1, len(proxy_pool))) if proxy_pool else 1.0

        try:
            leaders = self.fetch_leaders()
        except Exception as e:
            result["reason"] = f"fetch_failed:{e}"
            return result

        numeric, hashed = self.collect_ids(leaders)
        queue = numeric + hashed

        seen_rows = db_exec("SELECT uid FROM seen_ids WHERE ref_code=?",
                            (self.ref_code,), "all")
        seen = {r["uid"] for r in seen_rows}
        fresh = [uid for uid in queue if str(uid) not in seen]
        result["skipped_seen"] = len(queue) - len(fresh)
        queue = fresh

        if max_attempts:
            queue = queue[:max_attempts]

        total = len(queue)
        banned = set()

        for i, uid in enumerate(queue):
            if proxy_pool and len(banned) >= len(proxy_pool):
                banned.clear()
            proxy = self._next_proxy(exclude=banned) if proxy_pool else None

            res = self.refer(uid, proxy=proxy)
            reason = res.get("reason", "") or ""
            result["attempts"] += 1

            db_result = "failed"
            if res.get("success"):
                g = res.get("referred_gold", 0) or 0
                result["ok"] += 1
                result["gold"] += g
                result["hits"].append({"uid": uid, "gold": g})
                db_result = "success"
            elif "Aynı IP" in reason:
                result["ip_limit"] += 1
                if proxy:
                    banned.add(proxy)
                db_result = "same_ip"
            elif "Zaten" in reason:
                result["already"] += 1
                db_result = "already"
            elif "Geçersiz" in reason:
                result["invalid"] += 1
                db_result = "invalid"
            elif reason.startswith("HTTP_429"):
                if proxy:
                    banned.add(proxy)
                db_result = "rate_limit"

            try:
                db_exec("INSERT OR REPLACE INTO seen_ids(uid,ref_code,result) VALUES(?,?,?)",
                        (str(uid), self.ref_code, db_result))
            except Exception:
                pass

            if progress_cb:
                try:
                    progress_cb(i + 1, total, result["ok"], result["gold"])
                except Exception:
                    pass
            time.sleep(delay)

        return result

    @staticmethod
    def fmt_gold(v):
        try:
            return f"{int(v):,}".replace(",", ".")
        except Exception:
            return str(v)


_gc_client = None


def get_gc():
    global _gc_client
    if _gc_client is None:
        _gc_client = GiftCodeClient()
    return _gc_client


# ═══════════ HTML helpers ═══════════
def _esc(s):
    return html.escape(str(s or ""))


def gc_send(chat_id, text, reply_markup=None):
    try:
        main_bot.send_message(chat_id, text, reply_markup=reply_markup,
                              parse_mode="HTML")
    except Exception:
        plain = (text.replace("<b>", "").replace("</b>", "")
                     .replace("<i>", "").replace("</i>", "")
                     .replace("<code>", "").replace("</code>", ""))
        try:
            main_bot.send_message(chat_id, plain, reply_markup=reply_markup)
        except Exception as e:
            log.error(f"gc_send: {e}")


def send_long(chat_id, text, reply_markup=None, max_len=3800):
    if len(text) <= max_len:
        gc_send(chat_id, text, reply_markup)
        return
    lines = text.split("\n")
    chunks = []
    cur = ""
    for line in lines:
        if len(cur) + len(line) + 1 > max_len:
            chunks.append(cur)
            cur = line
        else:
            cur = cur + "\n" + line if cur else line
    if cur:
        chunks.append(cur)
    for i, ch in enumerate(chunks):
        rm = reply_markup if i == len(chunks) - 1 else None
        gc_send(chat_id, ch, rm)


# ═══════════ Renderers ═══════════
def render_gold(leaders, uid, top=50):
    gold = leaders.get("gold", [])[:top]
    if not gold:
        return tr(uid, "no_gold")
    lines = [tr(uid, "gold_lb_title"), "━━━━━━━━━━━━━━━━━━━━"]
    for i, p in enumerate(gold, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}.".rjust(3)
        lines.append(f"{medal}  {_esc(p['name'])[:22]}")
        lines.append(f"      💰 {_esc(GiftCodeClient.fmt_gold(p['value']))} GP")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_diamond(leaders, uid, top=50):
    d = leaders.get("diamond", [])[:top]
    if not d:
        return tr(uid, "no_diamond")
    lines = [tr(uid, "diamond_lb_title"), "━━━━━━━━━━━━━━━━━━━━"]
    for i, p in enumerate(d, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}.".rjust(3)
        lines.append(f"{medal}  {_esc(p['name'])[:22]}")
        lines.append(f"      💎 {_esc(p['value'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_tasks(leaders, uid, top=20):
    tasks = leaders.get("tasks", [])[:top]
    if not tasks:
        return tr(uid, "no_tasks")
    lines = [tr(uid, "tasks_title"), "━━━━━━━━━━━━━━━━━━━━"]
    for i, t in enumerate(tasks, 1):
        lines.append(f"{i}. <b>{_esc(t['name'])[:22]}</b>")
        lines.append(f"   🏢 {_esc(t['company'])[:20]}")
        lines.append(f"   📌 {_esc(t['offer'])[:30]}")
        lines.append(f"   💰 {_esc(GiftCodeClient.fmt_gold(t['gold']))} GP")
        if t.get("completed"):
            lines.append(f"   🕒 {_esc(t['completed'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_top_refs(uid, limit=10):
    rows = db_exec("""SELECT u.user_id, u.first_name, u.username,
        (SELECT COUNT(*) FROM referrals r WHERE r.referrer=u.user_id) AS c
        FROM users u
        ORDER BY c DESC LIMIT ?""", (limit,), "all")
    rows = [r for r in rows if r["c"] > 0]
    if not rows:
        return tr(uid, "no_refs")
    lines = [tr(uid, "refs_title"), "━━━━━━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}.".rjust(3)
        name = _esc(r["first_name"] or "?")
        if r["username"]:
            name += f"  (@{_esc(r['username'])})"
        lines.append(f"{medal}  {name}")
        lines.append(f"      🎯 {r['c']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ═══════════════════════ Original APIs ═══════════════════════
BASE_URL = "https://giftcode.betelgeuse.app/api/referrer"
TOKEN_API = ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
             "eyJzdWIiOiJndGF2NTEwMzFAZ21haWwuY29tIn0."
             "LR0lbOdO6Qq5d_4X0jKUC6mx18PP1-w2ChvBXQTETw0")


def giftcode_send(code, target, proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.get(BASE_URL,
                         params={"referred_user_id": str(target),
                                 "ref_code": str(code)},
                         headers={"Authorization": TOKEN_API,
                                  "User-Agent": "okhttp/5.3.2"},
                         timeout=15, proxies=proxies)
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                return "success", d.get("referred_gold", 0)
            reason = d.get("reason", "")
            if "Zaten" in reason:
                return "already", reason
            if "Geçersiz" in reason:
                return "invalid", reason
            if "Aynı IP" in reason:
                return "same_ip", reason
            return "failed", reason
        if r.status_code == 429:
            return "rate_limit", "429"
        return "failed", f"HTTP_{r.status_code}"
    except Exception as e:
        return "error", str(e)


FIREBASE_KEY = "AIzaSyDR1RcaMP9IOmIy7i_daFPNr3e7kmWid6o"
FB_URL = "https://us-central1-gift-sheep-b21df.cloudfunctions.net/submitReferral"


def firebase_signup(email, password):
    try:
        r = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signUp",
            params={"key": FIREBASE_KEY},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def firebase_refer(token, code, proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.post(FB_URL,
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json; charset=utf-8",
                                   "User-Agent": "okhttp/3.12.13"},
                          json={"data": {"code": code}},
                          timeout=30, proxies=proxies)
        d = r.json()
        return (d.get("result", {}).get("success", False),
                d.get("result", {}).get("message", ""))
    except Exception as e:
        return False, str(e)


# ═══════════════════════ BOT + FLASK ═══════════════════════
main_bot = telebot.TeleBot(MAIN_BOT_TOKEN, parse_mode=None)

health_app = Flask("health")


@health_app.route("/")
@health_app.route("/health")
def _health_route():
    try:
        n_users = db_exec("SELECT COUNT(*) c FROM users", fetch="one")["c"]
    except Exception:
        n_users = -1
    try:
        n_proxies = db_exec("SELECT COUNT(*) c FROM proxies WHERE banned=0",
                            fetch="one")["c"]
    except Exception:
        n_proxies = -1
    running = sum(1 for u in attack_status if attack_status[u].get("running"))
    return {
        "status": "ok",
        "bot": "running",
        "users": n_users,
        "proxies": n_proxies,
        "active_attacks": running,
        "time": datetime.now().isoformat(),
    }, 200


def run_health_server():
    try:
        health_app.run(host="0.0.0.0", port=PORT,
                       debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        log.error(f"health server: {e}")


attack_status, attack_mode = {}, {}
_cancel = {}
_gc_lock = threading.Lock()
proxy_fallback_notified = {}
_pending_del = {}


def is_owner(uid): return str(uid) == str(OWNER_ID)


def is_banned(uid):
    r = db_exec("SELECT banned FROM users WHERE user_id=?", (uid,), "one")
    return bool(r and r["banned"])


def subscribed_tg(uid):
    if is_owner(uid):
        return True
    try:
        m = main_bot.get_chat_member(f"@{CHANNEL_TG}", uid)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False


def subscribed_yt(uid):
    if is_owner(uid):
        return True
    u = get_user(uid)
    if not u or not u["youtube_verified"]:
        return False
    try:
        d = datetime.fromisoformat(u["youtube_date"])
        if (datetime.now() - d).days > 7:
            return False
    except Exception:
        return False
    return True


def check_subs(uid):
    if is_owner(uid):
        return True, None
    if not subscribed_tg(uid):
        return False, "telegram"
    if not subscribed_yt(uid):
        return False, "youtube"
    return True, None


# ═══════════════════════ MAIN MENU ═══════════════════════
def main_menu(uid, chat_id):
    u = get_user(uid)
    if not u:
        return
    name = u["first_name"] or "user"
    mode = u["mode"]
    start_num = u["start_number"] or 0
    own_proxies = count_owner_proxies(uid)
    gen_proxies = count_general_proxies()
    total_avail = gen_proxies + own_proxies

    kb = InlineKeyboardMarkup(row_width=2)
    if mode == "giftcode":
        kb.add(InlineKeyboardButton(tr(uid, "set_referral"), callback_data="set_referral"),
               InlineKeyboardButton(tr(uid, "set_start"), callback_data="set_start"))
    else:
        kb.add(InlineKeyboardButton(tr(uid, "set_referral"), callback_data="set_referral"))
    kb.add(
        InlineKeyboardButton(tr(uid, "start_attack"), callback_data="start_attack"),
        InlineKeyboardButton(tr(uid, "stop_attack"), callback_data="stop_attack"),
        InlineKeyboardButton(tr(uid, "toggle_mode"), callback_data="toggle_mode"),
        InlineKeyboardButton(tr(uid, "status"), callback_data="status"),
        InlineKeyboardButton(tr(uid, "referral"), callback_data="my_referral"),
        InlineKeyboardButton(tr(uid, "proxy_menu_btn"), callback_data="proxy_menu"),
        InlineKeyboardButton(tr(uid, "daily"), callback_data="daily"),
        InlineKeyboardButton(tr(uid, "leaderboard"), callback_data="leaderboard"),
        InlineKeyboardButton(tr(uid, "my_stats"), callback_data="my_stats"),
        InlineKeyboardButton(tr(uid, "lang"), callback_data="lang_menu"),
        InlineKeyboardButton(tr(uid, "quick_menu"), callback_data="show_quick_menu"),
        InlineKeyboardButton(tr(uid, "gc_panel_btn"), callback_data="gc_panel"),
        InlineKeyboardButton(tr(uid, "refs_btn"), callback_data="gc_top_refs"),
    )
    if is_owner(uid):
        kb.add(InlineKeyboardButton(tr(uid, "owner"), callback_data="owner_commands"))

    stats = history_stats(uid)
    text = (f"{tr(uid,'welcome', name=name)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💎 {tr(uid,'points')}: {u['points']}\n"
            f"🔑 {tr(uid,'code')}: {u['referral_code']}\n"
            f"🔢 {tr(uid,'start_num')}: {start_num}\n"
            f"🌐 {tr(uid,'proxies')}: {total_avail} "
            f"(<i>{gen_proxies}+{own_proxies}</i>)\n"
            f"🔄 {tr(uid,'mode')}: {mode.upper()}\n"
            f"✅ {tr(uid,'success')}: {stats['success']}\n"
            f"🔥 Streak: {u['streak']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{tr(uid,'choose')}")
    try:
        main_bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.error(f"main_menu: {e}")


def quick_menu(uid, chat_id):
    kb = {
        "keyboard": [
            [{"text": "▶️ Start", "color": "success"}],
            [{"text": "⏹️ Stop", "color": "danger"},
             {"text": "📊 Status", "color": "primary"}],
            [{"text": "🎁 Daily", "color": "success"},
             {"text": "🏆 Top", "color": "primary"}],
            [{"text": "📊 Stats", "color": "primary"},
             {"text": "🔗 Link", "color": "primary"}],
            [{"text": "🎯 GiftCode", "color": "success"}],
        ],
        "resize_keyboard": True,
        "is_persistent": False,
    }
    try:
        requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                      json={"chat_id": chat_id, "text": tr(uid, "quick_menu"),
                            "reply_markup": kb}, timeout=10)
    except Exception as e:
        log.error(f"quick: {e}")


# ═══════════════════════ ATTACK ═══════════════════════
def process_giftcode(uid, target, proxy):
    u = get_user(uid)
    code = u["referral_code"]
    res, reason = giftcode_send(code, target, proxy)
    log_history(uid, "giftcode", target,
                res if res in ("success", "already", "failed") else "failed", proxy)
    return res, reason


def process_sheep(uid, target, proxy):
    email = f"fb_{uuid.uuid4().hex[:10]}@temp-mail.org"
    auth = firebase_signup(email, "Test@2026")
    if not auth or "idToken" not in auth:
        return "failed", "firebase_signup"
    u = get_user(uid)
    success, msg = firebase_refer(auth["idToken"], u["referral_code"] or "W27PO5", proxy)
    log_history(uid, "giftsheep", target, "success" if success else "failed", proxy)
    return ("success" if success else "failed"), msg


def attack_loop(uid, chat_id):
    try:
        u = get_user(uid)
        if not u:
            return
        mode = u["mode"]
        current = u["start_number"]

        if not attack_status.get(uid, {}).get("started_once"):
            current += random.randint(0, 500)
            set_user(uid, start_number=current)

        attempts = successes = 0
        banned = set()
        attack_status[uid] = {"running": True, "number": current,
                              "attempts": 0, "success": 0,
                              "started_once": True}
        try:
            main_bot.send_message(chat_id, f"🚀 {mode.upper()}")
        except Exception:
            pass
        time.sleep(1)

        progress_msg = None
        try:
            progress_msg = main_bot.send_message(chat_id, "⏳ ...").message_id
        except Exception:
            pass

        last_update = time.time()

        while attack_status.get(uid, {}).get("running"):
            if _cancel.get(uid):
                break
            if is_banned(uid):
                break
            if not is_owner(uid) and get_points(uid) <= 0:
                try:
                    main_bot.send_message(chat_id, f"⚠️ {get_referral_link(uid)}")
                except Exception:
                    pass
                break

            try:
                proxy = pick_proxy(banned, owner=uid)
            except Exception as e:
                log.error(f"pick_proxy err: {e}")
                proxy = None

            if proxy:
                proxy_fallback_notified.pop(uid, None)
            if not proxy:
                last_notice = proxy_fallback_notified.get(uid, 0)
                if time.time() - last_notice > 600:
                    try:
                        main_bot.send_message(chat_id, tr(uid, "no_proxies"),
                                              parse_mode="HTML")
                        log.info(f"proxy notice sent to {uid}")
                    except Exception as e:
                        log.error(f"proxy notice failed: {e}")
                    proxy_fallback_notified[uid] = time.time()

            attempts += 1
            attack_status[uid]["attempts"] = attempts

            if mode == "giftcode":
                target = str(current)
                current += 1
                attack_status[uid]["number"] = current
                res, reason = process_giftcode(uid, target, proxy)
                if res == "invalid":
                    continue
            else:
                target = uuid.uuid4().hex[:8]
                res, reason = process_sheep(uid, target, proxy)

            if res == "success":
                successes += 1
                attack_status[uid]["success"] = successes
                if not is_owner(uid):
                    add_points(uid, -1)
                if proxy:
                    proxy_score(proxy, True)
                try:
                    main_bot.send_message(OWNER_ID,
                        f"✅ {mode.upper()} | {get_display(uid)}\n"
                        f"ID: {uid}\nRemaining: {get_points(uid)}")
                except Exception:
                    pass
            elif res == "already":
                current += random.randint(5, 40)
                attack_status[uid]["number"] = current
                if proxy:
                    proxy_score(proxy, True)
            elif res == "invalid":
                current += random.randint(3, 15)
                attack_status[uid]["number"] = current
            elif res in ("same_ip", "rate_limit", "error"):
                if proxy:
                    proxy_score(proxy, False)
                    banned.add(proxy)
                else:
                    time.sleep(2)
            elif res == "failed":
                if proxy:
                    proxy_score(proxy, False)
                time.sleep(0.5)

            if time.time() - last_update > 3 and progress_msg:
                rate = (successes / attempts * 100) if attempts else 0
                bar = "█" * int(rate / 10) + "░" * (10 - int(rate / 10))
                try:
                    main_bot.edit_message_text(
                        f"📊 {mode.upper()}\n"
                        f"🎯 #{attempts} | ✅ {successes}\n"
                        f"📈 {rate:.1f}% {bar}\n"
                        f"💎 {get_points(uid)}",
                        chat_id=chat_id, message_id=progress_msg)
                    last_update = time.time()
                except Exception:
                    pass

        attack_status[uid]["running"] = False
        _cancel.pop(uid, None)
        set_user(uid, start_number=current)
        try:
            main_bot.send_message(chat_id, f"⏹️ {successes}/{attempts}")
        except Exception:
            pass
    except Exception as e:
        log.error(f"attack_loop FATAL: {e}")
        attack_status[uid] = {"running": False}
        try:
            main_bot.send_message(chat_id, f"❌ {e}")
        except Exception:
            pass


queue_jobs = PriorityQueue()


def worker():
    while True:
        _, uid, chat_id = queue_jobs.get()
        try:
            attack_loop(uid, chat_id)
        except Exception as e:
            log.error(f"worker: {e}")
        finally:
            queue_jobs.task_done()


for _ in range(WORKERS):
    threading.Thread(target=worker, daemon=True).start()


# ═══════════════════════ Helpers ═══════════════════════
def get_display(uid):
    u = get_user(uid)
    if not u:
        return str(uid)
    n = u["first_name"] or "?"
    return f"{n} (@{u['username']})" if u["username"] else n


def get_referral_link(uid):
    return f"https://t.me/{BOT_USERNAME}?start={uid}"


def find_uid_by_input(s):
    s = s.strip()
    if not s:
        return None
    if s.lstrip("@").isdigit():
        return int(s.lstrip("@"))
    uname = s.lstrip("@").lower()
    r = db_exec("SELECT user_id FROM users WHERE LOWER(username)=?",
                (uname,), "one")
    return r["user_id"] if r else None


# ═══════════════════════ Background loops ═══════════════════════
def auto_harvest_loop():
    time.sleep(60)
    while True:
        try:
            if get_setting("gc_auto_enabled", "0") == "1":
                if not _gc_lock.locked():
                    with _gc_lock:
                        log.info("auto_harvest: starting")
                        res = get_gc().harvest(delay=None)
                        log.info(f"auto_harvest: {res['ok']} ok, "
                                 f"{res['gold']} gold, skipped={res['skipped_seen']}")
                        try:
                            main_bot.send_message(
                                OWNER_ID,
                                f"🤖\n"
                                f"✅ {res['ok']} | 💰 {res['gold']}\n"
                                f"🚫 {res['ip_limit']} | 🔁 {res['already']} | ⏭️ {res['skipped_seen']}")
                        except Exception:
                            pass
        except Exception as e:
            log.error(f"auto_harvest: {e}")
        time.sleep(GC_AUTO_INTERVAL)


def self_ping_loop():
    """يرسل طلب HTTP إلى الرابط العام للبوت كل 10 دقائق — يمنع Render من النوم."""
    time.sleep(90)
    own_url = (os.getenv("RENDER_EXTERNAL_URL")
               or os.getenv("SELF_URL")
               or "").rstrip("/")
    if not own_url:
        log.warning("self_ping: RENDER_EXTERNAL_URL missing — disabled. "
                    "Add it in Render Environment.")
        return
    ping_url = f"{own_url}/health"
    log.info(f"self_ping: pinging {ping_url} every {SELF_PING_INTERVAL}s")
    fails = 0
    while True:
        try:
            r = requests.get(ping_url, timeout=15)
            if r.status_code == 200:
                if fails:
                    log.info(f"self_ping: recovered after {fails} fails")
                fails = 0
            else:
                fails += 1
                log.warning(f"self_ping: status {r.status_code} (fails={fails})")
        except Exception as e:
            fails += 1
            log.warning(f"self_ping: {e} (fails={fails})")
        time.sleep(SELF_PING_INTERVAL)


# ═══════════════════════ MAIN handlers ═══════════════════════
@main_bot.message_handler(commands=["start"])
def main_cmd_start(m):
    uid = m.from_user.id
    ensure_user(uid, m.from_user.first_name or "", m.from_user.username or "")
    if is_banned(uid):
        main_bot.reply_to(m, tr(uid, "banned"))
        return
    ref = None
    if m.text and m.text.startswith("/start"):
        p = m.text.split()
        if len(p) > 1 and p[1].isdigit():
            ref = int(p[1])
    if ref and ref != uid:
        r = db_exec("SELECT new_user FROM referrals WHERE new_user=?", (uid,), "one")
        if not r:
            ok, _ = check_subs(uid)
            if ok:
                db_exec("INSERT OR IGNORE INTO referrals(new_user,referrer) VALUES(?,?)",
                        (uid, ref))
                add_points(ref, REFERRAL_POINTS)
                main_bot.reply_to(m, f"✅ +{REFERRAL_POINTS}")
    ok, kind = check_subs(uid)
    if not ok:
        kb = InlineKeyboardMarkup(row_width=1)
        if kind == "telegram":
            kb.add(InlineKeyboardButton("📢", url=f"https://t.me/{CHANNEL_TG}"))
        if kind == "youtube":
            kb.add(InlineKeyboardButton("🎬", callback_data="verify_youtube"))
        kb.add(InlineKeyboardButton("✅", callback_data="check_sub"))
        main_bot.reply_to(m, tr(uid, "not_sub"), reply_markup=kb)
        return
    main_menu(uid, m.chat.id)


@main_bot.message_handler(func=lambda m: m.text == "▶️ Start")
def main_qs_start(m):
    uid = m.from_user.id
    ensure_user(uid)
    if not attack_status.get(uid, {}).get("running"):
        attack_status[uid] = {"running": True}
        queue_jobs.put((0 if is_owner(uid) else -get_points(uid), uid, m.chat.id))
        main_bot.reply_to(m, tr(uid, "attack_started"))


@main_bot.message_handler(func=lambda m: m.text == "⏹️ Stop")
def main_qs_stop(m):
    uid = m.from_user.id
    _cancel[uid] = True
    if uid in attack_status:
        attack_status[uid]["running"] = False
    main_bot.reply_to(m, tr(uid, "stopping"))


@main_bot.message_handler(func=lambda m: m.text == "📊 Status")
def main_qs_status(m):
    uid = m.from_user.id
    ensure_user(uid)
    st = attack_status.get(uid, {}).get("running", False)
    sts = history_stats(uid)
    u = get_user(uid)
    own = count_owner_proxies(uid)
    gen = count_general_proxies()
    main_bot.reply_to(m, f"📊 {tr(uid,'status')}\n"
                         f"▶️ {tr(uid,'status_on') if st else tr(uid,'status_off')}\n"
                         f"💎 {get_points(uid)}\n"
                         f"🔢 {tr(uid,'start_num')}: {u['start_number'] if u else 0}\n"
                         f"🌐 {tr(uid,'proxies')}: {gen+own} ({gen}+{own})\n"
                         f"✅ {sts['success']}")


@main_bot.message_handler(func=lambda m: m.text == "🎁 Daily")
def main_qs_daily(m):
    do_daily(m.from_user.id, m.chat.id)


@main_bot.message_handler(func=lambda m: m.text == "🏆 Top")
def main_qs_top(m):
    do_leaderboard(m.chat.id, m.from_user.id)


@main_bot.message_handler(func=lambda m: m.text == "📊 Stats")
def main_qs_stats(m):
    do_stats(m.from_user.id, m.chat.id)


@main_bot.message_handler(func=lambda m: m.text == "🔗 Link")
def main_qs_link(m):
    main_bot.reply_to(m, f"🔗 {get_referral_link(m.from_user.id)}")


@main_bot.message_handler(func=lambda m: m.text == "🎯 GiftCode")
def main_qs_gc(m):
    gc_send(m.chat.id, tr(m.from_user.id, "gc_panel_title"))


# ═══════════════════════ Owner commands ═══════════════════════
@main_bot.message_handler(commands=["reimport"])
def main_cmd_reimport(m):
    if not is_owner(m.from_user.id):
        return
    u, p = reimport_sessions(verbose=True)
    main_bot.reply_to(m, f"✅ {u}\n💎 {p}")


@main_bot.message_handler(commands=["sessions"])
def main_cmd_sessions(m):
    if not is_owner(m.from_user.id):
        return
    n = db_exec("SELECT COUNT(*) c FROM users", fetch="one")["c"]
    old = 0
    sp = os.path.join(OLD_DATA_DIR, "user_sessions.json")
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                old = len(json.load(f))
        except Exception:
            old = -1
    main_bot.reply_to(m, f"👥 DB: {n}\n📁 JSON: {old if old >= 0 else 'ERR'}")


@main_bot.message_handler(commands=["sync"])
def main_cmd_sync(m):
    if not is_owner(m.from_user.id):
        return
    u, p = reimport_sessions(verbose=True)
    n = db_exec("SELECT COUNT(*) c FROM users", fetch="one")["c"]
    main_bot.reply_to(m, f"🔄\n+{u}\n+{p}\n={n}")


@main_bot.message_handler(commands=["setallpoints"])
def main_cmd_setallpoints(m):
    if not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        main_bot.reply_to(m,
            "🔧 <b>تعيين نقاط الجميع</b>\n"
            "الاستخدام: <code>/setallpoints 10</code>",
            parse_mode="HTML")
        return
    try:
        val = int(parts[1].strip())
    except ValueError:
        main_bot.reply_to(m, "❌ الرقم غير صحيح.")
        return
    n = db_exec("SELECT COUNT(*) c FROM users", fetch="one")["c"]
    db_exec("UPDATE users SET points=?", (val,))
    main_bot.reply_to(m,
        f"✅ <b>تم التعديل</b>\n"
        f"👥 {n} مستخدم\n"
        f"💎 {val}",
        parse_mode="HTML")
    audit(m.from_user.id, "setallpoints", f"val={val},count={n}")


@main_bot.message_handler(commands=["addallpoints"])
def main_cmd_addallpoints(m):
    if not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        main_bot.reply_to(m, "الاستخدام: /addallpoints +50 أو /addallpoints -10")
        return
    val_s = parts[1].strip().replace(" ", "")
    try:
        val = int(val_s)
    except ValueError:
        main_bot.reply_to(m, "❌ الرقم غير صحيح.")
        return
    n = db_exec("SELECT COUNT(*) c FROM users", fetch="one")["c"]
    db_exec("UPDATE users SET points=points+?", (val,))
    db_exec("UPDATE users SET points=0 WHERE points<0")
    main_bot.reply_to(m,
        f"✅ <b>{'+' if val>0 else ''}{val}</b> لكل المستخدمين\n"
        f"👥 {n} مستخدم",
        parse_mode="HTML")
    audit(m.from_user.id, "addallpoints", f"val={val},count={n}")


@main_bot.message_handler(commands=["points_stats"])
def main_cmd_points_stats(m):
    if not is_owner(m.from_user.id):
        return
    r = db_exec(
        """SELECT COUNT(*) AS total,
                  SUM(points) AS sum,
                  AVG(points) AS avg,
                  MIN(points) AS min,
                  MAX(points) AS max
           FROM users""", fetch="one")
    avg = r["avg"] if r["avg"] is not None else 0
    main_bot.reply_to(m,
        f"💎 <b>إحصائيات النقاط</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 مستخدمون: {r['total']}\n"
        f"💰 المجموع: {r['sum'] or 0}\n"
        f"📊 المتوسط: {avg:.1f}\n"
        f"⬇️ الأدنى: {r['min'] or 0}\n"
        f"⬆️ الأعلى: {r['max'] or 0}",
        parse_mode="HTML")


@main_bot.message_handler(commands=["broadcast"])
def main_cmd_broadcast(m):
    if not is_owner(m.from_user.id):
        return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        main_bot.reply_to(m, "/broadcast TEXT")
        return
    users = db_exec("SELECT user_id FROM users WHERE banned=0", fetch="all")
    sent = failed = 0
    for row in users:
        try:
            main_bot.send_message(row["user_id"], f"📢\n\n{text}")
            sent += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    main_bot.reply_to(m, f"✅ {sent} | ❌ {failed}")
    audit(m.from_user.id, "broadcast", f"sent={sent},failed={failed}")


@main_bot.message_handler(commands=["emergency_stop"])
def main_cmd_estop(m):
    if not is_owner(m.from_user.id):
        return
    n = 0
    for uid in list(attack_status.keys()):
        if attack_status[uid].get("running"):
            attack_status[uid]["running"] = False
            _cancel[uid] = True
            n += 1
    main_bot.reply_to(m, f"🛑 {n}")
    audit(m.from_user.id, "estop", str(n))


@main_bot.message_handler(commands=["export"])
def main_cmd_export(m):
    if not is_owner(m.from_user.id):
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["uid", "name", "username", "points", "success",
                "failed", "streak", "lang"])
    for row in db_exec("SELECT * FROM users", fetch="all"):
        s = history_stats(row["user_id"])
        w.writerow([row["user_id"], row["first_name"], row["username"],
                    row["points"], s["success"], s["failed"],
                    row["streak"], row["lang"]])
    bio = io.BytesIO(buf.getvalue().encode("utf-8"))
    bio.name = "users.csv"
    main_bot.send_document(m.chat.id, bio)


@main_bot.message_handler(commands=["ban"])
def main_cmd_ban(m):
    if not is_owner(m.from_user.id):
        return
    p = m.text.split()
    if len(p) != 2:
        return
    uid = find_uid_by_input(p[1])
    if uid:
        set_user(uid, banned=1)
        main_bot.reply_to(m, f"🚫 {uid}")
    audit(m.from_user.id, "ban", str(uid))


@main_bot.message_handler(commands=["unban"])
def main_cmd_unban(m):
    if not is_owner(m.from_user.id):
        return
    p = m.text.split()
    if len(p) != 2:
        return
    uid = find_uid_by_input(p[1])
    if uid:
        set_user(uid, banned=0)
        main_bot.reply_to(m, f"✅ {uid}")
    audit(m.from_user.id, "unban", str(uid))


@main_bot.message_handler(commands=["live"])
def main_cmd_live(m):
    if not is_owner(m.from_user.id):
        return
    lines = [f"🔴 {get_display(int(uid))} #{attack_status[uid].get('number',0)}"
             for uid in attack_status if attack_status[uid].get("running")]
    main_bot.reply_to(m, "📡\n" + ("\n".join(lines) if lines else "-"))


@main_bot.message_handler(commands=["auto_harvest"])
def main_cmd_auto_harvest(m):
    if not is_owner(m.from_user.id):
        return
    arg = m.text.replace("/auto_harvest", "").strip().lower()
    if arg in ("on", "1", "تشغيل"):
        set_setting("gc_auto_enabled", "1")
        main_bot.reply_to(m, "✅ ON")
    elif arg in ("off", "0", "إيقاف"):
        set_setting("gc_auto_enabled", "0")
        main_bot.reply_to(m, "⏹️ OFF")
    else:
        cur = get_setting("gc_auto_enabled", "0")
        main_bot.reply_to(m, f"{'ON' if cur=='1' else 'OFF'}\n/auto_harvest on|off")


# ═══════════════════════ MAIN callbacks ═══════════════════════
@main_bot.callback_query_handler(func=lambda c: True)
def main_on_callback(c):
    uid = c.from_user.id
    chat_id = c.message.chat.id if c.message else uid
    if is_banned(uid):
        main_bot.answer_callback_query(c.id, tr(uid, "banned"), show_alert=True)
        return
    if rate_limited(uid):
        main_bot.answer_callback_query(c.id, tr(uid, "rate_limit"), show_alert=True)
        return

    try:
        if c.data == "check_sub":
            ok, _ = check_subs(uid)
            if ok:
                main_bot.answer_callback_query(c.id, tr(uid, "done"))
                main_menu(uid, chat_id)
            else:
                main_bot.answer_callback_query(c.id, tr(uid, "not_subscribed"),
                                               show_alert=True)
            return

        if c.data == "verify_youtube":
            set_user(uid, youtube_verified=1,
                     youtube_date=datetime.now().isoformat())
            main_bot.answer_callback_query(c.id, tr(uid, "youtube_ok"), show_alert=True)
            main_menu(uid, chat_id)
            return

        if c.data == "proxy_help":
            main_bot.answer_callback_query(c.id)
            gc_send(chat_id, tr(uid, "proxy_help_text"))
            return

        if c.data == "proxy_menu":
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(tr(uid, "proxy_add_btn"), callback_data="user_add_proxy"),
                InlineKeyboardButton(tr(uid, "proxy_list_btn"), callback_data="user_my_proxies"))
            kb.add(
                InlineKeyboardButton(tr(uid, "proxy_test_btn"), callback_data="user_test_my_proxies"),
                InlineKeyboardButton(tr(uid, "proxy_del_btn"), callback_data="user_del_my_proxies"))
            kb.add(
                InlineKeyboardButton(tr(uid, "proxy_help_btn"), callback_data="proxy_help"))
            kb.add(
                InlineKeyboardButton(tr(uid, "proxy_back"), callback_data="start"))
            gc_send(chat_id, tr(uid, "proxy_menu_title"), kb)
            return

        if c.data == "user_my_proxies":
            main_bot.answer_callback_query(c.id)
            rows = user_own_proxies(uid, limit=80)
            if not rows:
                gc_send(chat_id, tr(uid, "my_proxies_empty"))
                return
            total = count_owner_proxies(uid)
            lines = [tr(uid, "my_proxies_title", total=total), "━━━━━━━━━━━━━━━"]
            for i, r in enumerate(rows, 1):
                s = r["success"] or 0
                f = r["fail"] or 0
                lines.append(f"{i}. <code>{_esc(r['proxy'])}</code>")
                lines.append(f"   {tr(uid, 'my_proxies_stats', s=s, f=f)}")
            if total > len(rows):
                lines.append("")
                lines.append(f"<i>... +{total - len(rows)} أخرى</i>")
            send_long(chat_id, "\n".join(lines))
            return

        if c.data == "user_test_my_proxies":
            rows = user_own_proxies(uid, limit=200)
            if not rows:
                main_bot.answer_callback_query(c.id, tr(uid, "no_own_proxies"),
                                               show_alert=True)
                return
            main_bot.answer_callback_query(c.id, tr(uid, "testing_proxies",
                                                     n=len(rows)))
            proxy_list = [r["proxy"] for r in rows]

            def _test_thread():
                try:
                    alive = batch_test(proxy_list, workers=30)
                    dead = len(proxy_list) - len(alive)
                    gc_send(chat_id, tr(uid, "test_result",
                                        alive=len(alive), dead=dead,
                                        total=len(proxy_list)))
                    alive_set = set(alive)
                    for p in proxy_list:
                        if p not in alive_set:
                            proxy_score(p, False)
                except Exception as e:
                    gc_send(chat_id, tr(uid, "err_generic", err=_esc(e)))

            threading.Thread(target=_test_thread, daemon=True).start()
            return

        if c.data == "user_del_my_proxies":
            n = count_owner_proxies(uid)
            if n == 0:
                main_bot.answer_callback_query(c.id, tr(uid, "no_own_proxies"),
                                               show_alert=True)
                return
            main_bot.answer_callback_query(c.id)
            _pending_del[uid] = True
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(tr(uid, "del_proxies_yes"), callback_data="user_del_confirm"),
                InlineKeyboardButton(tr(uid, "cancel"), callback_data="cancel_step"))
            gc_send(chat_id, tr(uid, "del_proxies_confirm", n=n), kb)
            return

        if c.data == "user_del_confirm":
            if not _pending_del.get(uid):
                main_bot.answer_callback_query(c.id, "⚠️", show_alert=True)
                return
            _pending_del.pop(uid, None)
            n = count_owner_proxies(uid)
            db_exec("DELETE FROM proxies WHERE owner=?", (uid,))
            main_bot.answer_callback_query(c.id, tr(uid, "del_proxies_done", n=n),
                                           show_alert=True)
            return

        if c.data == "toggle_mode":
            u = get_user(uid) or {}
            new = "giftsheep" if u.get("mode") == "giftcode" else "giftcode"
            set_user(uid, mode=new)
            main_bot.answer_callback_query(c.id, f"🔄 {new.upper()}", show_alert=True)
            main_menu(uid, chat_id)
            return

        if c.data == "start_attack":
            if attack_status.get(uid, {}).get("running"):
                main_bot.answer_callback_query(c.id, tr(uid, "already_running"),
                                               show_alert=True)
                return
            if not is_owner(uid) and get_points(uid) <= 0:
                main_bot.answer_callback_query(c.id, tr(uid, "no_points"),
                                               show_alert=True)
                return
            attack_status[uid] = {"running": True}
            _cancel.pop(uid, None)
            prio = 0 if is_owner(uid) else -get_points(uid)
            queue_jobs.put((prio, uid, chat_id))
            main_bot.answer_callback_query(c.id, tr(uid, "attack_started"),
                                           show_alert=True)
            return

        if c.data == "stop_attack":
            _cancel[uid] = True
            if uid in attack_status:
                attack_status[uid]["running"] = False
            main_bot.answer_callback_query(c.id, "⏹️", show_alert=True)
            return

        if c.data == "status":
            st = attack_status.get(uid, {}).get("running", False)
            s = history_stats(uid)
            u = get_user(uid)
            own = count_owner_proxies(uid)
            gen = count_general_proxies()
            main_bot.answer_callback_query(c.id)
            main_bot.send_message(chat_id,
                f"📊\n"
                f"▶️ {tr(uid,'status_on') if st else tr(uid,'status_off')}\n"
                f"💎 {get_points(uid)}\n"
                f"🔢 {tr(uid,'start_num')}: {u['start_number'] if u else 0}\n"
                f"🌐 {tr(uid,'proxies')}: {gen+own} ({gen}+{own})\n"
                f"✅ {s['success']}")
            return

        if c.data == "my_referral":
            main_bot.answer_callback_query(c.id)
            main_bot.send_message(chat_id, f"🔗 {get_referral_link(uid)}")
            return

        if c.data == "my_stats":
            main_bot.answer_callback_query(c.id)
            do_stats(uid, chat_id)
            return

        if c.data == "leaderboard":
            main_bot.answer_callback_query(c.id)
            do_leaderboard(chat_id, uid)
            return

        if c.data == "daily":
            main_bot.answer_callback_query(c.id)
            do_daily(uid, chat_id)
            return

        if c.data == "lang_menu":
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup(row_width=3)
            kb.add(InlineKeyboardButton("🇾🇪 العربية", callback_data="set_lang_ar"),
                   InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"))
            main_bot.send_message(chat_id, "🌐 Language:", reply_markup=kb)
            return

        if c.data.startswith("set_lang_"):
            lang = c.data.replace("set_lang_", "")
            set_user(uid, lang=lang)
            main_bot.answer_callback_query(c.id, f"✅ {lang}")
            main_menu(uid, chat_id)
            return

        if c.data == "show_quick_menu":
            main_bot.answer_callback_query(c.id)
            quick_menu(uid, chat_id)
            return

        if c.data == "cancel_step":
            _pending_del.pop(uid, None)
            _cancel[uid] = True
            main_bot.answer_callback_query(c.id, tr(uid, "canceled"), show_alert=True)
            main_menu(uid, chat_id)
            return

        if c.data == "set_referral":
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton(tr(uid, "cancel"), callback_data="cancel_step"))
            msg = main_bot.send_message(chat_id, tr(uid, "send_referral"),
                                         reply_markup=kb)
            main_bot.register_next_step_handler(msg, step_set_referral)
            return

        if c.data == "set_start":
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton(tr(uid, "cancel"), callback_data="cancel_step"))
            msg = main_bot.send_message(chat_id, tr(uid, "send_start"),
                                         reply_markup=kb)
            main_bot.register_next_step_handler(msg, step_set_start)
            return

        if c.data == "user_add_proxy":
            if count_owner_proxies(uid) >= USER_PROXY_LIMIT:
                main_bot.answer_callback_query(
                    c.id, tr(uid, "proxy_limit_reached", limit=USER_PROXY_LIMIT),
                    show_alert=True)
                return
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(tr(uid, "proxy_help_btn"),
                                         callback_data="proxy_help"))
            kb.add(InlineKeyboardButton(tr(uid, "cancel"),
                                         callback_data="cancel_step"))
            msg = main_bot.send_message(
                chat_id,
                tr(uid, "send_proxy") + "\n\n💡 يمكنك إرسال عدة أسطر — سطر لكل بروكسي",
                reply_markup=kb)
            main_bot.register_next_step_handler(msg, step_add_proxy)
            return

        if c.data == "owner_commands":
            if not is_owner(uid):
                main_bot.answer_callback_query(c.id, tr(uid, "owner_only"), show_alert=True)
                return
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(tr(uid, "owner_add_proxy"), callback_data="owner_add_proxy"),
                InlineKeyboardButton(tr(uid, "owner_list_proxies"), callback_data="owner_list_proxies"),
                InlineKeyboardButton(tr(uid, "owner_test_proxies"), callback_data="owner_test_proxies"),
                InlineKeyboardButton(tr(uid, "owner_del_proxy"), callback_data="owner_del_proxy"),
                InlineKeyboardButton(tr(uid, "owner_cleanup"), callback_data="owner_cleanup"),
                InlineKeyboardButton(tr(uid, "owner_proxy_stats"), callback_data="owner_proxy_stats"),
                InlineKeyboardButton(tr(uid, "owner_stats"), callback_data="owner_stats"),
                InlineKeyboardButton(tr(uid, "owner_edit_points"), callback_data="owner_edit_points"),
                InlineKeyboardButton(tr(uid, "owner_broadcast"), callback_data="owner_broadcast"),
                InlineKeyboardButton(tr(uid, "owner_live"), callback_data="owner_live"),
                InlineKeyboardButton(tr(uid, "owner_estop"), callback_data="owner_estop"),
                InlineKeyboardButton(tr(uid, "back"), callback_data="start"))
            main_bot.send_message(chat_id, tr(uid, "owner_panel"), reply_markup=kb)
            return

        if c.data == "owner_stats":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            do_owner_stats(chat_id)
            return

        if c.data == "owner_live":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            lines = [f"🔴 {get_display(int(x))} #{attack_status[x].get('number',0)}"
                     for x in attack_status if attack_status[x].get("running")]
            main_bot.send_message(chat_id, "📡\n" + ("\n".join(lines) if lines else "-"))
            return

        if c.data == "owner_estop":
            if not is_owner(uid):
                return
            n = 0
            for x in list(attack_status.keys()):
                if attack_status[x].get("running"):
                    attack_status[x]["running"] = False
                    _cancel[x] = True
                    n += 1
            main_bot.answer_callback_query(c.id, f"🛑 {n}", show_alert=True)
            return

        if c.data == "owner_broadcast":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            msg = main_bot.send_message(chat_id, tr(uid, "broadcast_hint"))
            main_bot.register_next_step_handler(msg, step_broadcast)
            return

        if c.data == "owner_edit_points":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            msg = main_bot.send_message(chat_id, tr(uid, "edit_points_hint"))
            main_bot.register_next_step_handler(msg, step_edit_points)
            return

        if c.data == "owner_add_proxy":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            msg = main_bot.send_message(chat_id, tr(uid, "owner_add_proxy_hint"))
            main_bot.register_next_step_handler(msg, step_owner_add_proxy)
            return

        if c.data == "owner_list_proxies":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            rows = db_exec("SELECT proxy, success, fail, owner FROM proxies "
                           "ORDER BY success DESC LIMIT 300", fetch="all")
            if not rows:
                main_bot.send_message(chat_id, "—")
                return
            lines = ["📋 <b>قائمة البروكسيات</b>", "━━━━━━━━━━━━━━━"]
            gen = 0; own = 0
            for i, r in enumerate(rows, 1):
                if r["owner"] == 0:
                    gen += 1
                else:
                    own += 1
                tag = "🌐" if r["owner"] == 0 else f"👤{r['owner']}"
                lines.append(f"{i}. {tag} <code>{_esc(r['proxy'])}</code>")
                lines.append(f"   ✅{r['success']} ❌{r['fail']}")
            lines.insert(2, f"🌐 عامة: {gen} | 👤 خاصة: {own}")
            send_long(chat_id, "\n".join(lines))
            return

        if c.data == "owner_proxy_stats":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            total = db_exec("SELECT COUNT(*) c FROM proxies WHERE banned=0",
                            fetch="one")["c"]
            general = count_general_proxies()
            own = total - general
            with_s = db_exec("SELECT COUNT(*) c FROM proxies WHERE success>0",
                             fetch="one")["c"]
            with_f = db_exec("SELECT COUNT(*) c FROM proxies WHERE fail>0",
                             fetch="one")["c"]
            top = db_exec("""SELECT proxy, success, fail FROM proxies
                             WHERE success>0
                             ORDER BY CAST(success AS REAL)/(success+fail+1) DESC
                             LIMIT 5""", fetch="all")
            lines = [
                "📊 <b>إحصائيات البروكسيات</b>",
                "━━━━━━━━━━━━━━━",
                f"🌐 عامة: {general}",
                f"👤 خاصة: {own}",
                f"📦 إجمالي: {total}",
                f"✅ لها نجاح: {with_s}",
                f"❌ لها فشل: {with_f}",
                "",
                "🏆 <b>الأفضل:</b>",
            ]
            for i, r in enumerate(top, 1):
                lines.append(f"{i}. ✅{r['success']} ❌{r['fail']}")
                lines.append(f"   <code>{_esc(r['proxy'])}</code>")
            send_long(chat_id, "\n".join(lines))
            return

        if c.data == "owner_cleanup":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id, "🧹 ...", show_alert=True)

            def _clean():
                try:
                    db_exec("DELETE FROM proxies WHERE banned=1")
                    db_exec("DELETE FROM proxies WHERE fail>success AND fail>=5")
                    left = db_exec("SELECT COUNT(*) c FROM proxies WHERE banned=0",
                                   fetch="one")["c"]
                    main_bot.send_message(chat_id, f"🧹 تم التنظيف\n📦 متبقٍ: {left}")
                except Exception as e:
                    main_bot.send_message(chat_id, f"❌ {e}")

            threading.Thread(target=_clean, daemon=True).start()
            return

        if c.data == "owner_test_proxies":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id, tr(uid, "fetching"), show_alert=True)
            proxies = all_proxies()
            alive = batch_test(proxies)
            main_bot.send_message(chat_id, f"🧪 {len(alive)}/{len(proxies)}")
            return

        if c.data == "owner_del_proxy":
            if not is_owner(uid):
                return
            main_bot.answer_callback_query(c.id)
            msg = main_bot.send_message(chat_id, tr(uid, "owner_del_proxy_hint"))
            main_bot.register_next_step_handler(msg, step_owner_del_proxy)
            return

        # GiftCode callbacks
        if c.data == "gc_panel":
            main_bot.answer_callback_query(c.id)
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(tr(uid, "gc_top_gold"), callback_data="gc_top_gold"),
                InlineKeyboardButton(tr(uid, "gc_top_diamond"), callback_data="gc_top_diamond"),
                InlineKeyboardButton(tr(uid, "gc_tasks"), callback_data="gc_tasks"),
                InlineKeyboardButton(tr(uid, "gc_top_refs"), callback_data="gc_top_refs"))
            if is_owner(uid):
                kb.add(InlineKeyboardButton(tr(uid, "gc_harvest"), callback_data="gc_harvest"))
            kb.add(InlineKeyboardButton(tr(uid, "back"), callback_data="start"))
            gc_send(chat_id, tr(uid, "gc_panel_title"), kb)
            return

        if c.data == "gc_top_gold":
            main_bot.answer_callback_query(c.id, tr(uid, "fetching"))
            try:
                gc_send(chat_id, render_gold(get_gc().fetch_leaders(), uid, 50))
            except Exception as e:
                gc_send(chat_id, tr(uid, "fetch_failed", err=_esc(e)))
            return

        if c.data == "gc_top_diamond":
            main_bot.answer_callback_query(c.id, tr(uid, "fetching"))
            try:
                gc_send(chat_id, render_diamond(get_gc().fetch_leaders(), uid, 50))
            except Exception as e:
                gc_send(chat_id, tr(uid, "fetch_failed", err=_esc(e)))
            return

        if c.data == "gc_tasks":
            main_bot.answer_callback_query(c.id, tr(uid, "fetching"))
            try:
                gc_send(chat_id, render_tasks(get_gc().fetch_leaders(), uid, 20))
            except Exception as e:
                gc_send(chat_id, tr(uid, "fetch_failed", err=_esc(e)))
            return

        if c.data == "gc_top_refs":
            main_bot.answer_callback_query(c.id)
            gc_send(chat_id, render_top_refs(uid, 10))
            return

        if c.data == "gc_harvest":
            if not is_owner(uid):
                main_bot.answer_callback_query(c.id, tr(uid, "owner_only"), show_alert=True)
                return
            if _gc_lock.locked():
                main_bot.answer_callback_query(c.id, tr(uid, "harvest_busy"), show_alert=True)
                return
            main_bot.answer_callback_query(c.id, tr(uid, "harvesting"))

            def run_harvest():
                with _gc_lock:
                    try:
                        def cb(i, total, ok, gold):
                            if i == total or ok > 0:
                                try:
                                    main_bot.send_message(chat_id,
                                        f"⏳ {i}/{total} | ✅ {ok} | 💰 {gold}")
                                except Exception:
                                    pass
                        res = get_gc().harvest(progress_cb=cb, delay=None)
                        if res.get("reason"):
                            main_bot.send_message(chat_id,
                                tr(uid, "err_generic", err=_esc(res['reason'])))
                            return
                        main_bot.send_message(chat_id, tr(uid, "harvest_done",
                            ok=res['ok'], ip=res['ip_limit'], already=res['already'],
                            invalid=res['invalid'], skipped=res['skipped_seen'],
                            gold=res['gold']))
                        audit(uid, "gc_harvest",
                              f"ok={res['ok']},gold={res['gold']}")
                    except Exception as e:
                        try:
                            main_bot.send_message(chat_id,
                                tr(uid, "err_generic", err=_esc(e)))
                        except Exception:
                            pass

            threading.Thread(target=run_harvest, daemon=True).start()
            return

        if c.data == "start":
            main_bot.answer_callback_query(c.id)
            main_menu(uid, chat_id)
            return

        main_bot.answer_callback_query(c.id)

    except Exception as e:
        log.error(f"main cb err: {e}")
        try:
            main_bot.answer_callback_query(c.id, f"⚠️ {e}", show_alert=True)
        except Exception:
            pass


# ═══════════════════════ Features ═══════════════════════
def do_daily(uid, chat_id):
    u = get_user(uid)
    if not u:
        return
    last = u["last_daily"]
    streak = u["streak"]
    now = datetime.now()
    last_dt = None
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:
            last_dt = None
        if last_dt and last_dt.date() == now.date():
            main_bot.send_message(chat_id, tr(uid, "daily_claimed"))
            return
    streak = streak + 1 if last_dt and (now - last_dt).days == 1 else 1
    reward = DAILY_BASE + min(streak, DAILY_STREAK_MAX) * DAILY_STREAK_BONUS
    set_user(uid, last_daily=now.isoformat(), streak=streak)
    add_points(uid, reward)
    main_bot.send_message(chat_id, tr(uid, "daily_reward", reward=reward, streak=streak))


def do_leaderboard(chat_id, uid):
    rows = db_exec("""SELECT u.user_id, u.first_name, u.username, u.points,
        (SELECT COUNT(*) FROM history h
         WHERE h.user_id=u.user_id AND h.result='success') s
        FROM users u WHERE u.banned=0 ORDER BY s DESC LIMIT 10""", fetch="all")
    if not rows:
        main_bot.send_message(chat_id, tr(uid, "nothing"))
        return
    lines = [tr(uid, "lb_title"), "━━━━━━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}.".rjust(3)
        name = r["first_name"] or "?"
        if r["username"]:
            name += f"  (@{r['username']})"
        lines.append(f"{medal}  {html.escape(name)[:30]}")
        lines.append(f"      ✅ {r['s']} | 💎 {r['points']}")
        lines.append("")
    try:
        main_bot.send_message(chat_id, "\n".join(lines).rstrip(), parse_mode="HTML")
    except Exception:
        main_bot.send_message(chat_id, "\n".join(lines).rstrip())


def do_stats(uid, chat_id):
    s = history_stats(uid)
    total = s["success"] + s["failed"] + s["already"]
    rate = (s["success"] / total * 100) if total else 0
    u = get_user(uid)
    own = count_owner_proxies(uid)
    gen = count_general_proxies()
    main_bot.send_message(chat_id,
        f"{tr(uid,'stats_title')}\n━━━━━━━━━━━\n"
        f"✅ {s['success']}\n❌ {s['failed']}\n🔁 {s['already']}\n"
        f"📈 {rate:.1f}%\n💎 {u['points']}\n"
        f"🌐 {tr(uid,'proxies')}: {gen+own} ({gen}+{own})\n"
        f"🔥 Streak: {u['streak']}")


def do_owner_stats(chat_id):
    rows = db_exec("SELECT user_id, first_name, username, points FROM users "
                   "ORDER BY points DESC", fetch="all")
    if not rows:
        main_bot.send_message(chat_id, "—")
        return
    header = (f"📈 {len(rows)}\n"
              f"💎 {sum(r['points'] for r in rows)}\n\n")
    body = ""
    for i, r in enumerate(rows[:50], 1):
        s = history_stats(r["user_id"])
        name = r["first_name"] or "?"
        if r["username"]:
            name += f" (@{r['username']})"
        body += (f"{i}. {name}\n 🆔 {r['user_id']} "
                 f"💎{r['points']} ✅{s['success']}\n")
    main_bot.send_message(chat_id, (header + body)[:4000])


# ═══════════════════════ Steps ═══════════════════════
def step_set_referral(m):
    if _cancel.pop(m.from_user.id, None):
        return
    set_user(m.from_user.id, referral_code=m.text.strip())
    main_bot.reply_to(m, f"✅ {m.text.strip()}")
    main_menu(m.from_user.id, m.chat.id)


def step_set_start(m):
    if _cancel.pop(m.from_user.id, None):
        return
    if m.text.strip().isdigit():
        set_user(m.from_user.id, start_number=int(m.text.strip()))
        main_bot.reply_to(m, f"✅ {m.text.strip()}")
    else:
        main_bot.reply_to(m, tr(m.from_user.id, "numbers_only"))
    main_menu(m.from_user.id, m.chat.id)


def step_add_proxy(m):
    if _cancel.pop(m.from_user.id, None):
        return
    uid = m.from_user.id
    text = (m.text or "").strip()
    if not text:
        return

    current = count_owner_proxies(uid)
    if current >= USER_PROXY_LIMIT:
        main_bot.reply_to(m, tr(uid, "proxy_limit_reached", limit=USER_PROXY_LIMIT))
        return

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    added = 0
    skipped = 0
    for line in lines:
        if line.startswith("#"):
            continue
        if current + added >= USER_PROXY_LIMIT:
            break
        if add_proxy(line, uid):
            added += 1
        else:
            skipped += 1

    if added:
        msg = f"✅ {added}"
        if skipped:
            msg += f" | ⚠️ {skipped}"
        main_bot.reply_to(m, msg)
        try:
            main_bot.send_message(
                OWNER_ID,
                f"🔐 {added} بروكسي من {uid}" + (f" (+{skipped} موجود)" if skipped else ""))
        except Exception:
            pass
    else:
        main_bot.reply_to(m, tr(uid, "proxy_exists"))


def step_owner_add_proxy(m):
    text = (m.text or "").strip()
    if not text:
        return
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    added = 0
    skipped = 0
    for line in lines:
        if line.startswith("#"):
            continue
        if add_proxy(line, 0):
            added += 1
        else:
            skipped += 1
    msg = f"✅ {added}"
    if skipped:
        msg += f" | ⚠️ {skipped}"
    main_bot.reply_to(m, msg)


def step_owner_del_proxy(m):
    del_proxy(m.text.strip())
    main_bot.reply_to(m, "✅")


def step_edit_points(m):
    raw = (m.text or "").strip()
    parts = raw.split()
    if len(parts) < 2:
        main_bot.reply_to(m, tr(m.from_user.id, "wrong_format"))
        return

    identifier = parts[0]
    rest = "".join(parts[1:])

    try:
        pts = int(rest)
    except ValueError:
        main_bot.reply_to(m, tr(m.from_user.id, "numbers_only"))
        return

    target_uid = find_uid_by_input(identifier)
    if not target_uid:
        main_bot.reply_to(m, "❌ المستخدم غير موجود. تأكد أنه استخدم /start")
        return

    if rest.startswith("+"):
        add_points(target_uid, abs(pts))
        new_val = get_points(target_uid)
        main_bot.reply_to(m,
            f"✅ +{abs(pts)} → {target_uid}\n💎 الجديد: {new_val}")
    elif rest.startswith("-"):
        add_points(target_uid, -abs(pts))
        new_val = get_points(target_uid)
        main_bot.reply_to(m,
            f"✅ -{abs(pts)} → {target_uid}\n💎 الجديد: {new_val}")
    else:
        set_user(target_uid, points=pts)
        main_bot.reply_to(m, f"✅ {target_uid} = {pts}")


def step_broadcast(m):
    text = m.text.strip()
    if not text:
        return
    users = db_exec("SELECT user_id FROM users WHERE banned=0", fetch="all")
    sent = failed = 0
    for row in users:
        try:
            main_bot.send_message(row["user_id"], f"📢\n\n{text}")
            sent += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    main_bot.reply_to(m, f"✅ {sent} | ❌ {failed}")


# ═══════════ ROBUST POLLING ═══════════
def robust_poller():
    last_id = 0
    consecutive_409 = 0
    notified_409 = False

    try:
        main_bot.delete_webhook(drop_pending_updates=False)
        log.info("webhook cleared for polling")
    except Exception as e:
        log.warning(f"delete_webhook: {e}")

    try:
        init_updates = main_bot.get_updates(offset=-1, timeout=5)
        if init_updates:
            last_id = init_updates[-1].update_id
    except Exception:
        pass

    while True:
        try:
            updates = main_bot.get_updates(
                offset=last_id + 1,
                timeout=25,
                long_polling_timeout=20,
                allowed_updates=["message", "callback_query",
                                 "edited_message"],
            )
            consecutive_409 = 0
            notified_409 = False

            for u in updates:
                last_id = u.update_id
                try:
                    main_bot.process_new_updates([u])
                except Exception as e:
                    log.error(f"process #{u.update_id}: {e}")

        except Exception as e:
            err = str(e)
            if "409" in err or "Conflict" in err:
                consecutive_409 += 1
                wait = min(45, 3 * consecutive_409)
                log.warning(f"409 #{consecutive_409} — wait {wait}s")
                if consecutive_409 >= 3 and not notified_409:
                    try:
                        main_bot.send_message(
                            OWNER_ID,
                            "⚠️ <b>تحذير 409</b>\n"
                            "━━━━━━━━━━━━━━━\n"
                            "بوت آخر يعمل بنفس التوكن!\n\n"
                            "📌 <b>أوقف:</b>\n"
                            "• FPS.ms\n"
                            "• أي استضافة أخرى\n"
                            "• جهازك الشخصي\n\n"
                            "<i>البوت يستمر في المحاولة تلقائياً.</i>",
                            parse_mode="HTML")
                    except Exception:
                        pass
                    notified_409 = True
                time.sleep(wait)
            elif "timed out" in err.lower():
                pass
            else:
                log.error(f"poll error: {err}")
                time.sleep(5)


# ═══════════════════════ MAIN ═══════════════════════
if __name__ == "__main__":
    _init_db()
    migrate_legacy()
    u, p = reimport_sessions(verbose=True)
    log.info(f"Starting bot | GC token: {'OK' if GC_TOKEN else 'MISSING'} "
             f"| reimport +{u}u +{p}p")

    # Flask health
    threading.Thread(target=run_health_server, daemon=True).start()
    log.info(f"Health server on 0.0.0.0:{PORT}")

    # Self-ping (لا يحتاج cron-job خارجي)
    threading.Thread(target=self_ping_loop, daemon=True).start()

    # auto harvest
    threading.Thread(target=auto_harvest_loop, daemon=True).start()

    log.info("Robust polling starting...")
    robust_poller()
