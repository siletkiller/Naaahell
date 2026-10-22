import os
import re
import sys
import time
import json
import signal
import datetime
import zipfile
import shutil
import subprocess
import threading
import py_compile
import logging
import traceback
import requests
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ================= BASE PATHS & LOGGING SETUP =================
BASE_DIR = os.path.abspath("hosted_bots")
DATA_DIR = os.path.abspath("data")
ROOT_USERS_JSON = os.path.abspath("users.json")
ERROR_LOG_PATH = os.path.abspath("error.log")

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Ensure error.log exists and configure dual logging (file + terminal)
if not os.path.exists(ERROR_LOG_PATH):
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"--- Log session initialized at {datetime.datetime.now()} ---\n")

try:
    os.chmod(ERROR_LOG_PATH, 0o666)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ERROR_LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("HostingBot")

# ================= RENDER HTTP SERVER (HEALTH CHECK) =================
class RenderHealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Silent Killer Bot Hosting Engine is Online 24/7 on Render!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress routine health check terminal logs to keep output clean
        pass

class ReusableTCPServer(HTTPServer):
    allow_reuse_address = True

def run_render_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = ReusableTCPServer(("0.0.0.0", port), RenderHealthCheck)
        logger.info(f"Render HTTP server bound to 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to bind HTTP server to port {port}: {e}\n{traceback.format_exc()}")

# ================= CONFIGURATIONS =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

TOKEN = BOT_TOKEN
DEFAULT_CHANNELS = ["@hentaimainchannel"]
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "Silent_killer_un")
OWNER_ID = int(os.environ.get("OWNER_ID", 6534828985))
ADMIN_IDS = [OWNER_ID]
DEFAULT_UPI = "xyz@fampay"
DEFAULT_DEVELOPER = "Silent_killer_un"

USERS_DB_PATH = os.path.join(DATA_DIR, "users_db.json")
CONFIG_DB_PATH = os.path.join(DATA_DIR, "system_config.json")
ADMIN_LOGS_PATH = os.path.join(DATA_DIR, "admin_logs.json")

DEFAULT_WELCOME_TEXT = (
    "⚡️ 𝐒𝐈𝐋𝐄𝐍𝐓 𝐊𝐈𝐋𝐋𝐄𝐑\n\n"
    "👋 𝐖𝐄𝐋𝐂𝐎𝐌𝐄!\n"
    "Hey ✦ {name} ✦,\n"
    "welcome aboard! 🚀\n\n"
    "┏━━━━━━━━━━━━━━━━┓\n"
    "┃ 📦 𝐏𝐑𝐎𝐅𝐈𝐋𝐄\n"
    "┣━━━━━━━━━━━━━━━━┫\n"
    "┃ 🆔 ID: `{id}`\n"
    "┃ 👑 Username: {username}\n"
    "┃ 💎 Status: {status}\n"
    "┃ 📁 Files: {files} / {max_files}\n"
    "┃ 💾 RAM Limit per Bot: {ram}\n"
    "┗━━━━━━━━━━━━━━━━┛\n\n"
    "💎 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐄𝐍𝐄𝐅𝐈𝐓\n"
    "Auto-approved 24/7 hosting for Premium users! ✅\n\n"
    "🛠️ 𝐘𝐎𝐔 𝐂𝐀𝐍\n"
    "🐍 Host Python (`.py`)\n"
    "🟨 Host JavaScript (`.js`)\n"
    "📦 Upload large files smoothly\n"
    "🗃️ Upload .zip projects - pick which file inside to run\n"
    "🤖 Ask AI about hosting\n\n"
    "👇 Open an option from the menu below."
)

PACKAGE_MAP = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "discord": "discord.py",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "yaml": "pyyaml",
    "dateutil": "python-dateutil"
}

# --- UNIVERSAL BUTTON BUILDERS ---
def KBtn(text, style=None, **kwargs):
    if style:
        try:
            return KeyboardButton(text, style=style, **kwargs)
        except TypeError:
            b = KeyboardButton(text, **kwargs)
            setattr(b, 'style', style)
            return b
    return KeyboardButton(text, **kwargs)

def IBtn(text, style=None, **kwargs):
    if style:
        try:
            return InlineKeyboardButton(text, style=style, **kwargs)
        except TypeError:
            b = InlineKeyboardButton(text, **kwargs)
            setattr(b, 'style', style)
            return b
    return InlineKeyboardButton(text, **kwargs)

try:
    _orig_kbtn_to_dict = KeyboardButton.to_dict
    def _kbtn_to_dict(self):
        d = _orig_kbtn_to_dict(self)
        if getattr(self, 'style', None) and 'style' not in d:
            d['style'] = self.style
        return d
    KeyboardButton.to_dict = _kbtn_to_dict
except Exception:
    pass

try:
    _orig_ibtn_to_dict = InlineKeyboardButton.to_dict
    def _ibtn_to_dict(self):
        d = _orig_ibtn_to_dict(self)
        if getattr(self, 'style', None) and 'style' not in d:
            d['style'] = self.style
        return d
    InlineKeyboardButton.to_dict = _ibtn_to_dict
except Exception:
    pass

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
START_TIME = time.time()
db_lock = threading.Lock()

system_config = {
    "force_channels": list(DEFAULT_CHANNELS),
    "developer_username": DEFAULT_DEVELOPER,
    "payment_upi": DEFAULT_UPI,
    "updates_channel": f"https://t.me/{DEFAULT_CHANNELS[0].lstrip('@')}" if DEFAULT_CHANNELS else "https://t.me/telegram",
    "owner_username": OWNER_USERNAME,
    "auto_approve_files": False,
    "welcome_text": DEFAULT_WELCOME_TEXT,
    "tutorial_video": None,
    "default_max_files": 2,
    "default_ram": "512 MB",
    "premium_max_files": 10,
    "premium_ram": "2048 MB",
    "admin_layout_order": "default",
    "plans": {
        "1m": {"name": "1 Month", "price": "₹100.0", "days": 30},
        "2m": {"name": "2 Months", "price": "₹150", "days": 60},
        "3m": {"name": "3 Months", "price": "₹270", "days": 90},
        "4m": {"name": "4 Months", "price": "₹360", "days": 120},
        "life": {"name": "Lifetime", "price": "₹500", "days": "inf"}
    }
}

users_db = {}
admin_logs = {}
running_processes = {}
crash_history = {}
global_stats = {"total_file_records": 0, "total_active_bots": 0}

# ================= SAFE DATA PERSISTENCE =================
def _safe_json_dump(filepath, data):
    temp_path = f"{filepath}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, default=str)
    os.replace(temp_path, filepath)
    try:
        os.chmod(filepath, 0o666)
    except Exception:
        pass

def save_admin_logs():
    with db_lock:
        try:
            _safe_json_dump(ADMIN_LOGS_PATH, admin_logs)
        except Exception as e:
            logger.error(f"[DB] Error saving admin logs: {e}\n{traceback.format_exc()}")

def load_admin_logs():
    global admin_logs
    if os.path.isfile(ADMIN_LOGS_PATH):
        try:
            with open(ADMIN_LOGS_PATH, "r", encoding="utf-8") as f:
                admin_logs = json.load(f)
        except Exception as e:
            logger.error(f"[DB] Error loading admin logs: {e}\n{traceback.format_exc()}")

def save_db():
    with db_lock:
        try:
            _safe_json_dump(USERS_DB_PATH, users_db)
            _safe_json_dump(ROOT_USERS_JSON, users_db)
            _safe_json_dump(CONFIG_DB_PATH, system_config)
            _safe_json_dump(ADMIN_LOGS_PATH, admin_logs)
        except Exception as e:
            logger.error(f"[DB] Error saving database: {e}\n{traceback.format_exc()}")

def sync_disk_files_to_db():
    if not os.path.isdir(BASE_DIR):
        return
    changed = False
    for uid_folder in os.listdir(BASE_DIR):
        full_folder = os.path.join(BASE_DIR, uid_folder)
        if os.path.isdir(full_folder) and uid_folder.lstrip('-').isdigit():
            uid = int(uid_folder)
            u = get_user(uid)
            user_files = u.setdefault("files", [])
            files_data = u.setdefault("files_data", {})
            approved_files = u.setdefault("approved_files", [])

            for entry in os.listdir(full_folder):
                if entry.endswith(('.py', '.js', '.sh', '.zip')):
                    f_path = os.path.join(full_folder, entry)
                    if os.path.isfile(f_path):
                        if entry not in user_files:
                            user_files.append(entry)
                            changed = True
                        if entry not in files_data:
                            size_kb = round(os.path.getsize(f_path) / 1024, 2)
                            is_auto = system_config.get("auto_approve_files", False) or "Premium" in u.get("status", "")
                            files_data[entry] = {
                                "project_name": "Check Files",
                                "filename": entry,
                                "type": entry.split('.')[-1].lower(),
                                "size": f"{size_kb} KB",
                                "status": "Stopped",
                                "approval": "Approved" if is_auto else "Pending",
                                "upload_time": datetime.datetime.fromtimestamp(os.path.getmtime(f_path)).strftime('%Y-%m-%d %H:%M:%S'),
                                "reject_reason": None,
                                "reject_time": None
                            }
                            if is_auto and entry not in approved_files:
                                approved_files.append(entry)
                            changed = True
    if changed:
        save_db()

def load_db():
    global users_db, system_config
    source_file = None
    if os.path.isfile(USERS_DB_PATH):
        source_file = USERS_DB_PATH
    elif os.path.isfile(ROOT_USERS_JSON):
        source_file = ROOT_USERS_JSON

    if source_file:
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                raw_users = json.load(f)
                users_db = {int(k): v for k, v in raw_users.items() if str(k).lstrip('-').isdigit()}
        except Exception as e:
            logger.error(f"[DB] Error loading users database from {source_file}: {e}")
            corrupted_backup = f"{source_file}.corrupted_{int(time.time())}"
            try:
                shutil.copyfile(source_file, corrupted_backup)
                logger.warning(f"[DB] Corrupted database backed up to {corrupted_backup}")
            except Exception:
                pass

    if os.path.isfile(CONFIG_DB_PATH):
        try:
            with open(CONFIG_DB_PATH, "r", encoding="utf-8") as f:
                system_config.update(json.load(f))
        except Exception as e:
            logger.error(f"[DB] Error loading config database: {e}")

    load_admin_logs()
    sync_disk_files_to_db()
    global_stats["total_file_records"] = sum(len(u.get("files", [])) for u in users_db.values())

def format_ram_string(val):
    val_str = str(val).strip()
    if val_str.isdigit():
        return f"{val_str} MB"
    return val_str

def get_file_hosted_days_str(fdata):
    up_time_str = fdata.get("upload_time")
    if not up_time_str:
        return "Unknown"
    try:
        up_dt = datetime.datetime.strptime(up_time_str, '%Y-%m-%d %H:%M:%S')
        delta = datetime.datetime.now() - up_dt
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if days > 0:
            return f"{days} days {hours} hours ({days} Days)"
        elif hours > 0:
            return f"{hours} hours {minutes} mins (Today)"
        else:
            return f"{minutes} mins (Today)"
    except Exception:
        return "Active"

def get_user(user_id, username="No Username", first_name="User"):
    user_id = int(user_id)
    def_free_files = system_config.get("default_max_files", 2)
    def_free_ram = system_config.get("default_ram", "512 MB")
    def_prem_files = system_config.get("premium_max_files", 10)
    def_prem_ram = system_config.get("premium_ram", "2048 MB")

    if user_id not in users_db:
        users_db[user_id] = {
            "name": first_name if first_name else "User",
            "username": f"@{username}" if username and username != "No Username" else f"ID: {user_id}",
            "status": "Free User",
            "files": [], "files_data": {}, "approved_files": [], "running_files": [],
            "max_files": def_free_files, "ram": def_free_ram, "running_bots": 0,
            "banned": False, "treason_banned": False, "tried_to_ban_owner": False,
            "unban_traitor_warnings": 0, "premium_expiry": None
        }
        save_db()
    else:
        changed = False
        if first_name and first_name != "User" and users_db[user_id].get("name") != first_name:
            users_db[user_id]["name"] = first_name
            changed = True
        if username and username != "No Username" and users_db[user_id].get("username") != f"@{username}":
            users_db[user_id]["username"] = f"@{username}"
            changed = True
        for key, val in [("files_data", {}), ("approved_files", []), ("running_files", []), ("treason_banned", False), ("tried_to_ban_owner", False), ("unban_traitor_warnings", 0)]:
            if key not in users_db[user_id]:
                users_db[user_id][key] = val
                changed = True

        is_prem = "Premium" in users_db[user_id].get("status", "")
        target_max_files = def_prem_files if is_prem else def_free_files
        target_ram = def_prem_ram if is_prem else def_free_ram

        if users_db[user_id].get("max_files") != target_max_files:
            users_db[user_id]["max_files"] = target_max_files
            changed = True
        if users_db[user_id].get("ram") != target_ram:
            users_db[user_id]["ram"] = target_ram
            changed = True

        if changed:
            save_db()

    if user_id == OWNER_ID:
        users_db[user_id]["banned"] = False
        users_db[user_id]["treason_banned"] = False
        users_db[user_id]["tried_to_ban_owner"] = False
        users_db[user_id]["unban_traitor_warnings"] = 0

    return users_db[user_id]

def is_admin(user_id):
    return int(user_id) in ADMIN_IDS or int(user_id) == OWNER_ID

def generate_action_card(action_type, target_id, actor_id, extra_data=None):
    target_id, actor_id = int(target_id), int(actor_id)
    target_u, actor_u = get_user(target_id), get_user(actor_id)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    t_name, t_uname = target_u.get("name", "User"), target_u.get("username", "N/A")
    a_name, a_uname = actor_u.get("name", "Administrator"), actor_u.get("username", f"ID: {actor_id}")

    if action_type == "promote":
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 🛡️ **ADMIN PRIVILEGES GRANTED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🎖️ **New Role:** 🛡️ Bot Administrator\n┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n🎉 **Notice:** You have been promoted to **Administrator** status."
        )
    elif action_type == "demote":
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 🔴 **ADMIN PRIVILEGES REVOKED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🎖️ **New Role:** 👤 Standard User\n┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n⚠️ **Notice:** Your **Administrator privileges** have been revoked."
        )
    elif action_type == "ban":
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 🚫 **ACCOUNT SUSPENSION ENFORCED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🏷️ **Account Status:** ⛔ Permanently Banned\n┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n⛔ **Notice:** You have been banned from using this bot."
        )
    elif action_type == "unban":
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 🟢 **ACCOUNT ACCESS RESTORED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🏷️ **Account Status:** ✅ Active / Free User\n┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n🎉 **Notice:** Your ban has been lifted by administration."
        )
    elif action_type == "prem_add":
        expiry = extra_data.get("expiry", "Active") if extra_data else "Active"
        files = extra_data.get("files", target_u.get("max_files", 10)) if extra_data else target_u.get("max_files", 10)
        ram = extra_data.get("ram", target_u.get("ram", "2048 MB")) if extra_data else target_u.get("ram", "2048 MB")
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 💎 **PREMIUM MEMBERSHIP ACTIVATED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🏷️ **Account Level:** 💎 Premium Member\n┃ ⏳ **Expiry:** `{expiry}`\n┃ 📁 **Project Limit:** `{files} Projects`\n"
            f"┃ 💾 **RAM Allocation:** `{ram}`\n┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n🚀 **Notice:** Premium subscription activated! All bots run 24/7."
        )
    elif action_type == "prem_remove":
        files = extra_data.get("files", target_u.get("max_files", 2)) if extra_data else target_u.get("max_files", 2)
        ram = extra_data.get("ram", target_u.get("ram", "512 MB")) if extra_data else target_u.get("ram", "512 MB")
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ 🔴 **PREMIUM MEMBERSHIP REVOKED**\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃ 👤 **Target User:** {t_name}\n┃ 🆔 **User ID:** `{target_id}`\n┃ 👑 **Username:** {t_uname}\n"
            f"┃ 🏷️ **Account Level:** 👤 Free Tier User\n┃ 📁 **Project Limit:** `{files} Projects`\n┃ 💾 **RAM Allocation:** `{ram}`\n"
            f"┃ 👮‍♂️ **Action By:** {a_name} ({a_uname})\n┃ ⏰ **Timestamp:** `{timestamp}`\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\nℹ️ **Notice:** Your Premium subscription has ended or was revoked."
        )
    return ""

def log_admin_action(admin_id, action_title, details=""):
    admin_id = int(admin_id)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    adm_user = get_user(admin_id)
    adm_key = str(admin_id)
    if adm_key not in admin_logs:
        admin_logs[adm_key] = []
    admin_logs[adm_key].append({"action": action_title, "details": details, "timestamp": timestamp})
    save_admin_logs()

    if admin_id != OWNER_ID:
        total_actions = len(admin_logs[adm_key])
        owner_alert = (
            f"🚨 ══════ **ADMIN ACTIVITY DOSSIER** ══════ 🚨\n\n"
            f"👮‍♂️ **ADMINISTRATOR PROFILE:**\n"
            f"• 👤 **Name:** {adm_user.get('name')}\n• 👑 **Username:** {adm_user.get('username')}\n"
            f"• 🆔 **Admin ID:** `{admin_id}`\n• 🏷 **Status:** {adm_user.get('status')}\n"
            f"• 📁 **Files Hosted:** `{len(adm_user.get('files', []))}`\n• 🤖 **Active Bots:** `{adm_user.get('running_bots')}`\n"
            f"• 💾 **RAM Allocation:** `{adm_user.get('ram')}`\n• 📊 **Total Actions:** `{total_actions}`\n\n"
            f"⚡ **ACTION DETAILS:**\n• 📌 **Operation:** {action_title}\n• 📝 **Data:** {details}\n• ⏰ **Timestamp:** `{timestamp}`\n"
            f"══════════════════════════════════════"
        )
        try:
            bot.send_message(OWNER_ID, owner_alert, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to deliver admin alert to owner: {e}")

def get_unjoined_channels(user_id):
    if is_admin(user_id):
        return []
    unjoined = []
    for ch in system_config.get("force_channels", []):
        if not ch or ch.lower() in ["none", "off", "disable"]:
            continue
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unjoined.append(ch)
        except Exception:
            unjoined.append(ch)
    return unjoined

def check_subscription(user_id):
    return len(get_unjoined_channels(user_id)) == 0

def send_force_sub_message(chat_id, user_id):
    unjoined = get_unjoined_channels(user_id)
    if not unjoined:
        return True
    markup = InlineKeyboardMarkup(row_width=1)
    for idx, ch in enumerate(unjoined, start=1):
        ch_url = ch if ch.startswith("https://") else f"https://t.me/{ch.lstrip('@')}"
        markup.add(IBtn(f"🔗 Join Channel {idx} ({ch})", style="primary", url=ch_url))
    markup.add(IBtn("✅ I've Joined - Check Again", style="success", callback_data="check_sub"))
    text = (
        "Access Restricted!\n\n"
        "To use **✧ Sɪʟᴇɴᴛ Kɪʟʟᴇʀ ✧ Hosting Bot**, you must join our official channel(s) first:\n\n"
        + "\n".join([f"• `{c}`" for c in unjoined]) +
        "\n\nTap each channel link below to join, then press **I've Joined - Check Again**."
    )
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    return False

def contact_owner_to_unban_keyboard():
    owner = system_config.get('owner_username', OWNER_USERNAME).lstrip('@')
    markup = InlineKeyboardMarkup()
    markup.add(IBtn("💬 Talk to Owner to Request Unban", style="primary", url=f"https://t.me/{owner}"))
    return markup

def owner_pardon_markup(target_id):
    markup = InlineKeyboardMarkup()
    markup.add(IBtn("🟢 Unban & Pardon Admin", style="success", callback_data=f"owner_pardon_{target_id}"))
    return markup

def owner_ban_markup(target_id):
    markup = InlineKeyboardMarkup()
    markup.add(IBtn("🔴 Instantly Ban Admin", style="danger", callback_data=f"owner_ban_admin_{target_id}"))
    return markup

def bottom_reply_keyboard(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KBtn("📢 Updates Channel", style="primary"), KBtn("⌚ Uptime", style="primary"))
    markup.row(KBtn("📤 Upload File", style="primary"), KBtn("📁 Check Files", style="primary"))
    markup.row(KBtn("⚡ Bot Speed", style="primary"), KBtn("📊 Statistics", style="primary"))
    markup.row(KBtn("💎 Premium Plans", style="success"), KBtn("📞 Contact Owner", style="primary"))
    markup.row(KBtn("👨‍💻 Bot Developer", style="primary"), KBtn("❓ Help", style="primary"))
    markup.row(KBtn("✧ Silent Killer ✧ AI", style="primary"))
    if is_admin(user_id):
        markup.row(KBtn("☣️ Admin Control", style="danger"))
    return markup

def premium_plans_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    for code, p in system_config["plans"].items():
        markup.add(IBtn(f"{p['name']} - {p['price']}", style="success", callback_data=f"buy_{code}"))
    markup.add(IBtn("🔙 Back to Main", style="danger", callback_data="back_to_main"))
    return markup

def admin_plans_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    for code, p in system_config["plans"].items():
        markup.add(IBtn(f"✏️ Edit {p['name']}", style="primary", callback_data=f"edit_plan_{code}"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def count_pending_files():
    cnt = 0
    for u in users_db.values():
        for fdata in u.get("files_data", {}).values():
            if fdata.get("approval") == "Pending":
                cnt += 1
    return cnt

def count_active_hosted_files():
    return sum(1 for (uid, fn), p in running_processes.items() if p["proc"].poll() is None)

def admin_panel_keyboard(user_id=None):
    auto_approve_status = "🟢 ON" if system_config["auto_approve_files"] else "🔴 OFF"
    auto_style = "success" if system_config["auto_approve_files"] else "danger"
    total_files = sum(len(u.get("files", [])) for u in users_db.values())
    pending_cnt = count_pending_files()
    active_cnt = count_active_hosted_files()
    channels_count = len(system_config.get("force_channels", []))

    markup = InlineKeyboardMarkup()
    markup.row(
        IBtn("👥 View All Users", style="primary", callback_data="admin_users"),
        IBtn("📢 Broadcast", style="primary", callback_data="admin_broadcast")
    )
    markup.row(
        IBtn(f"📁 Files ({total_files})", style="primary", callback_data="admin_view_files"),
        IBtn(f"⏳ Pending Files ({pending_cnt})", style="primary", callback_data="admin_pending_files")
    )
    markup.row(
        IBtn(f"🚀 Hosted Files ({active_cnt})", style="primary", callback_data="admin_hosted_files"),
        IBtn("🔄 Refresh Bot", style="success", callback_data="admin_refresh_all")
    )
    markup.row(
        IBtn("🟢 Add Admin", style="success", callback_data="admin_add_admin"),
        IBtn("🔴 Remove Admin", style="danger", callback_data="admin_remove_admin")
    )
    markup.row(
        IBtn("🟢 Add Premium", style="success", callback_data="admin_make_premium"),
        IBtn("🔴 Remove Premium", style="danger", callback_data="admin_remove_premium")
    )
    markup.row(
        IBtn("🟢 Unban User", style="success", callback_data="admin_unban"),
        IBtn("🔴 Ban User", style="danger", callback_data="admin_ban")
    )
    markup.row(
        IBtn(f"Auto Approve File: {auto_approve_status}", style=auto_style, callback_data="admin_toggle_auto")
    )
    markup.row(
        IBtn("📦 Change Host Limits", style="primary", callback_data="admin_set_host_limits"),
        IBtn("✏️ Manage Plans", style="primary", callback_data="admin_manage_plans")
    )
    markup.row(
        IBtn(f"🔗 Force Channels ({channels_count})", style="primary", callback_data="admin_manage_channels"),
        IBtn("📢 Edit Updates Link", style="primary", callback_data="admin_set_updates")
    )
    markup.row(
        IBtn("👨‍💻 Edit Developer", style="primary", callback_data="admin_set_developer"),
        IBtn("👤 Edit Owner Info", style="primary", callback_data="admin_set_owner")
    )
    markup.row(
        IBtn("💳 Change UPI ID", style="primary", callback_data="admin_set_upi"),
        IBtn("📝 Edit Welcome Text", style="primary", callback_data="admin_set_welcome")
    )
    markup.row(
        IBtn("📹 Set Tutorial Video", style="primary", callback_data="admin_set_tutorial"),
        IBtn("🔀 Rearrange Layout", style="primary", callback_data="admin_rearrange_layout")
    )

    if user_id is not None and int(user_id) == OWNER_ID:
        markup.row(IBtn("🕵️ Admin Activity Logs", style="primary", callback_data="admin_audit_logs"))

    markup.row(IBtn("🔙 Back to Main", style="danger", callback_data="back_to_main"))
    return markup

def admin_host_limits_keyboard():
    def_free_files = system_config.get("default_max_files", 2)
    def_free_ram = system_config.get("default_ram", "512 MB")
    def_prem_files = system_config.get("premium_max_files", 10)
    def_prem_ram = system_config.get("premium_ram", "2048 MB")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        IBtn(f"📁 Free Files ({def_free_files})", style="primary", callback_data="set_def_files_prompt"),
        IBtn(f"💾 Free RAM ({def_free_ram})", style="primary", callback_data="set_def_ram_prompt")
    )
    markup.add(
        IBtn(f"💎 Prem Files ({def_prem_files})", style="success", callback_data="set_prem_files_prompt"),
        IBtn(f"💾 Prem RAM ({def_prem_ram})", style="success", callback_data="set_prem_ram_prompt")
    )
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def admin_tutorial_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    vid_id = system_config.get("tutorial_video")
    if vid_id:
        markup.add(
            IBtn("▶️ Watch Current Video", style="primary", callback_data="show_tutorial_video"),
            IBtn("📤 Replace Video", style="success", callback_data="tut_upload_prompt")
        )
        markup.add(
            IBtn("🗑️ Delete Video", style="danger", callback_data="tut_delete"),
            IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back")
        )
    else:
        markup.add(
            IBtn("📤 Upload Video", style="success", callback_data="tut_upload_prompt"),
            IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back")
        )
    return markup

def admin_activity_selection_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    for idx, adm_id in enumerate(ADMIN_IDS, start=1):
        adm_info = get_user(adm_id)
        role_tag = "👑 Owner" if adm_id == OWNER_ID else f"🛡️ Admin {idx}"
        act_count = len(admin_logs.get(str(adm_id), []))
        markup.add(IBtn(f"{role_tag}: {adm_info.get('name')} ({adm_info.get('username')}) [{act_count} actions]", style="primary", callback_data=f"view_adm_acts_{adm_id}"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def show_admin_activities(chat_id, target_admin_id, message_id=None):
    target_admin_id = int(target_admin_id)
    adm_info = get_user(target_admin_id)
    role_tag = "👑 Primary Owner" if target_admin_id == OWNER_ID else "🛡️ Bot Administrator"
    logs = admin_logs.get(str(target_admin_id), [])
    header = (
        f"🕵️ **Detailed Admin Activity Dossier**\n\n"
        f"🏷 **Role:** {role_tag}\n• 👤 **Name:** {adm_info.get('name')}\n• 👑 **Username:** {adm_info.get('username')}\n"
        f"• 🆔 **Admin ID:** `{target_admin_id}`\n• 📊 **Total Actions:** `{len(logs)}`\n\n━━━━━━━━ Action History ━━━━━━━━\n"
    )
    if not logs:
        body = "*(No actions logged for this administrator yet)*"
    else:
        recent = logs[-20:]
        body = "\n\n".join([f"**{i+1}.** ⏰ `{a['timestamp']}`\n   ⚡ **{a['action']}**\n   📝 {a['details']}" for i, a in enumerate(reversed(recent))])

    full_text = header + body
    if len(full_text) > 4000:
        full_text = full_text[:3950] + "\n\n...(truncated)"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(IBtn("🔄 Refresh", style="primary", callback_data=f"view_adm_acts_{target_admin_id}"), IBtn("🧹 Clear Logs", style="danger", callback_data=f"clear_adm_acts_{target_admin_id}"))
    markup.add(IBtn("🔙 Back to Admins List", style="danger", callback_data="admin_audit_logs"))
    if message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=full_text, reply_markup=markup, parse_mode="Markdown")
            return
        except Exception:
            pass
    bot.send_message(chat_id, full_text, reply_markup=markup, parse_mode="Markdown")

def admin_force_channels_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("➕ Add New Channel", style="success", callback_data="admin_add_force_channel"))
    for idx, ch in enumerate(system_config.get("force_channels", [])):
        markup.add(IBtn(f"🗑️ Remove {ch}", style="danger", callback_data=f"admin_del_force_ch_{idx}"))
    if system_config.get("force_channels"):
        markup.add(IBtn("🧹 Clear All Channels", style="danger", callback_data="admin_clear_all_force_ch"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def admins_list_keyboard(viewer_id=None):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually", style="success", callback_data="admin_type_new_admin_id"))
    for adm_id in ADMIN_IDS:
        adm_info = get_user(adm_id)
        role_badge = "👑 Owner" if adm_id == OWNER_ID else "🛡️ Admin"
        markup.add(IBtn(f"{role_badge}: {adm_info.get('name')} (`{adm_id}`)", style="primary", callback_data=f"show_admin_prof_{adm_id}"))
    for uid, uinfo in users_db.items():
        if uid not in ADMIN_IDS and uid != OWNER_ID:
            if (uinfo.get("treason_banned") or uinfo.get("tried_to_ban_owner")) and viewer_id != OWNER_ID:
                continue
            markup.add(IBtn(f"➕ Promote: {uinfo.get('name')} (`{uid}`)", style="success", callback_data=f"promote_user_{uid}"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def admin_remove_selection_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually", style="danger", callback_data="admin_type_remove_admin_id"))
    for adm_id in ADMIN_IDS:
        adm_info = get_user(adm_id)
        name = adm_info.get("name", "Admin")
        role_tag = "👑 Owner" if adm_id == OWNER_ID else "🛡️ Admin"
        markup.add(IBtn(f"🔴 Demote {role_tag}: {name} (`{adm_id}`)", style="danger", callback_data=f"remove_admin_direct_{adm_id}"))
    markup.add(IBtn("🔙 Back to Admin", style="primary", callback_data="admin_back"))
    return markup

def user_ban_selection_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually", style="danger", callback_data="admin_type_ban_id"))
    for uid, uinfo in users_db.items():
        if uid == OWNER_ID or uinfo.get("banned", False):
            continue
        role_tag = "🛡️ Admin" if uid in ADMIN_IDS else "👤 User"
        markup.add(IBtn(f"🔴 Ban {role_tag}: {uinfo.get('name')} (`{uid}`)", style="danger", callback_data=f"ban_user_direct_{uid}"))
    markup.add(IBtn("🔙 Back to Admin", style="primary", callback_data="admin_back"))
    return markup

def user_unban_selection_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually", style="success", callback_data="admin_type_unban_id"))
    found = False
    for uid, uinfo in users_db.items():
        if uinfo.get("banned", False):
            found = True
            status_tag = "⛔ Traitor" if (uinfo.get("treason_banned") or uinfo.get("tried_to_ban_owner")) else "🚫 Banned"
            markup.add(IBtn(f"🟢 Unban {status_tag}: {uinfo.get('name')} (`{uid}`)", style="success", callback_data=f"unban_user_direct_{uid}"))
    if not found:
        markup.add(IBtn("📭 No Banned Users Found", style="primary", callback_data="nobanned"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def user_premium_control_keyboard(target_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        IBtn("➕ Add 1 Day", style="success", callback_data=f"prem_add_1_{target_id}"),
        IBtn("➕ Add 7 Days", style="success", callback_data=f"prem_add_7_{target_id}"),
        IBtn("➕ Add 15 Days", style="success", callback_data=f"prem_add_15_{target_id}"),
        IBtn("➕ Add 30 Days", style="success", callback_data=f"prem_add_30_{target_id}"),
        IBtn("➕ Add 60 Days", style="success", callback_data=f"prem_add_60_{target_id}"),
        IBtn("➕ Add 90 Days", style="success", callback_data=f"prem_add_90_{target_id}"),
        IBtn("♾️ Permanent", style="success", callback_data=f"prem_add_inf_{target_id}"),
        IBtn("🔴 Remove Premium", style="danger", callback_data=f"prem_remove_{target_id}")
    )
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def user_select_for_premium_keyboard(action_type="add"):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually (Any User)", style="success", callback_data="admin_type_prem_id"))
    for uid, uinfo in users_db.items():
        is_prem = "Premium" in uinfo.get('status', '')
        markup.add(IBtn(f"{'💎' if is_prem else '👤'} {uinfo['username']} (`{uid}`)", style="primary", callback_data=f"select_prem_user_{uid}"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def user_select_premium_for_removal_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(IBtn("✍️ Type User ID Manually", style="danger", callback_data="admin_type_remove_prem_id"))
    for uid, uinfo in users_db.items():
        if "Premium" in uinfo.get('status', ''):
            markup.add(IBtn(f"💎 {uinfo['username']} (`{uid}`)", style="danger", callback_data=f"select_prem_user_{uid}_remove"))
    markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
    return markup

def send_user_premium_dashboard(chat_id, target_id, message_id=None, is_edit=False):
    target_id = int(target_id)
    u = get_user(target_id)
    expiry_str = "Permanent" if u.get("premium_expiry") == "inf" else (datetime.datetime.fromtimestamp(u["premium_expiry"]).strftime('%Y-%m-%d %H:%M') if u.get("premium_expiry") and u["premium_expiry"] > time.time() else "Not Active / Expired")
    info_text = (
        f"💎 **User Premium Dashboard**\n\n"
        f"👤 **User ID:** `{target_id}`\n👑 **Username:** {u['username']}\n🏷 **Status:** {u['status']}\n"
        f"⏳ **Expiry Date:** `{expiry_str}`\n📁 **Uploaded Files:** {len(u['files'])}/{u['max_files']}\n💾 **RAM Allocation:** {u['ram']}\n\n"
        f"Select actions below to manage subscription:"
    )
    try:
        photos = bot.get_user_profile_photos(target_id, limit=1)
        if photos.total_count > 0:
            if is_edit and message_id:
                try:
                    bot.delete_message(chat_id, message_id)
                except Exception:
                    pass
            bot.send_photo(chat_id, photo=photos.photos[0][-1].file_id, caption=info_text, parse_mode="Markdown", reply_markup=user_premium_control_keyboard(target_id))
            return
    except Exception:
        pass
    if is_edit and message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=info_text, parse_mode="Markdown", reply_markup=user_premium_control_keyboard(target_id))
            return
        except Exception:
            pass
    bot.send_message(chat_id, info_text, parse_mode="Markdown", reply_markup=user_premium_control_keyboard(target_id))

def user_files_keyboard(user_id):
    u = get_user(user_id)
    files = u.get("files", [])
    files_data = u.get("files_data", {})
    markup = InlineKeyboardMarkup(row_width=1)
    if not files:
        markup.add(IBtn("📭 No Files Found", style="primary", callback_data="nofiles"))
    else:
        for idx, filename in enumerate(files):
            fdata = files_data.get(filename, {})
            ext = fdata.get("type", filename.split('.')[-1].strip())
            approval = fdata.get("approval", "Pending")
            is_running = (user_id, filename) in running_processes and running_processes[(user_id, filename)]["proc"].poll() is None
            if approval == "Rejected":
                badge = f"❌ {filename} ({ext}) - 🔴"
            elif is_running:
                badge = f"🟢 {filename} ({ext}) - 🟢"
            elif approval == "Approved":
                badge = f"⚪ {filename} ({ext}) - 🔴"
            else:
                badge = f"⏳ {filename} ({ext}) - ⚪"
            markup.add(IBtn(badge, style="primary", callback_data=f"manage_file_{idx}"))
    markup.add(IBtn("🔙 Back to Main", style="danger", callback_data="back_to_main"))
    return markup

def single_file_control_keyboard(user_id, file_idx):
    u = get_user(user_id)
    if file_idx >= len(u["files"]):
        markup = InlineKeyboardMarkup()
        markup.add(IBtn("🔙 Back to Files", style="danger", callback_data="back_to_files"))
        return markup
    filename = u["files"][file_idx]
    fdata = u.get("files_data", {}).get(filename, {})
    approval = fdata.get("approval", "Pending")
    is_running = (user_id, filename) in running_processes and running_processes[(user_id, filename)]["proc"].poll() is None

    markup = InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(IBtn("⏹️ Stop", style="danger", callback_data=f"stop_file_{file_idx}"), IBtn("🔄 Restart", style="primary", callback_data=f"restart_file_{file_idx}"))
    else:
        markup.add(IBtn("▶️ Start", style="success", callback_data=f"run_file_{file_idx}"), IBtn("🔄 Restart", style="primary", callback_data=f"restart_file_{file_idx}"))
    markup.add(IBtn("📜 View Logs", style="primary", callback_data=f"logs_file_{file_idx}"), IBtn("🗑️ Delete", style="danger", callback_data=f"del_file_{file_idx}"))
    if filename.endswith('.zip'):
        markup.add(IBtn("🎯 Pick Run File", style="primary", callback_data=f"zipentry_{file_idx}"))
    status_label = "Status: ❌ Rejected" if approval == "Rejected" else ("Status: 🟢 Running" if is_running else ("Status: 🔴 Stopped" if approval == "Approved" else "Status: ⏳ Pending Approval"))
    markup.add(IBtn(status_label, style="primary", callback_data=f"filestatus_{file_idx}"))
    markup.add(IBtn("🔙 Back to Files", style="danger", callback_data="back_to_files"))
    return markup

# --- Deep Project Discovery & Auto-Repair Engine ---
def deep_scan_and_repair_script(file_path):
    if not file_path.endswith('.py') or not os.path.isfile(file_path):
        return True, None, "File validated."
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
    except Exception as e:
        return False, None, f"Error reading file: {e}"

    modified = False
    repaired_details = []

    lines = code.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        fixed_line = line
        if re.match(r'^(limport|iimport|mport)\b', stripped):
            fixed_line = re.sub(r'^(limport|iimport|mport)\b', 'import', line)
            modified = True
            repaired_details.append(f"Fixed typo `{stripped.split()[0]}` ➔ `import`")
        elif re.match(r'^fromm\b', stripped):
            fixed_line = re.sub(r'^fromm\b', 'from', line)
            modified = True
            repaired_details.append("Fixed typo `fromm` ➔ `from`")
        new_lines.append(fixed_line)
    code = "\n".join(new_lines)

    missing_imports = []
    if "requests." in code and "import requests" not in code:
        missing_imports.append("import requests")
    if "telebot." in code and "import telebot" not in code and "from telebot" not in code:
        missing_imports.append("import telebot")
    if "json." in code and "import json" not in code:
        missing_imports.append("import json")
    if "os." in code and "import os" not in code:
        missing_imports.append("import os")
    if "sys." in code and "import sys" not in code:
        missing_imports.append("import sys")
    if "time." in code and "import time" not in code:
        missing_imports.append("import time")

    if missing_imports:
        code = "\n".join(missing_imports) + "\n" + code
        modified = True
        repaired_details.append("Added missing import(s): " + ", ".join(missing_imports))

    if modified:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
        except Exception:
            pass

    try:
        py_compile.compile(file_path, doraise=True)
        repair_msg = ("\n• " + "\n• ".join(repaired_details)) if repaired_details else ""
        return True, repair_msg, "Deep scan verified syntax."
    except py_compile.PyCompileError as e:
        return False, None, str(e).strip()

def discover_project_entry(folder_path):
    folder_path = os.path.abspath(folder_path)
    py_candidates = ["main.py", "bot.py", "app.py", "run.py", "index.py", "server.py"]
    js_candidates = ["index.js", "bot.js", "main.js", "app.js", "server.js"]
    sh_candidates = ["start.sh", "run.sh"]

    for f in py_candidates:
        p = os.path.join(folder_path, f)
        if os.path.isfile(p):
            return "py", p, folder_path
    for f in js_candidates:
        p = os.path.join(folder_path, f)
        if os.path.isfile(p):
            return "js", p, folder_path
    for f in sh_candidates:
        p = os.path.join(folder_path, f)
        if os.path.isfile(p):
            return "sh", p, folder_path

    for root, _, files in os.walk(folder_path):
        for f in py_candidates:
            if f in files:
                return "py", os.path.join(root, f), root
        for f in js_candidates:
            if f in files:
                return "js", os.path.join(root, f), root
        for f in sh_candidates:
            if f in files:
                return "sh", os.path.join(root, f), root

    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.endswith('.py'):
                return "py", os.path.join(root, f), root
            if f.endswith('.js'):
                return "js", os.path.join(root, f), root
            if f.endswith('.sh'):
                return "sh", os.path.join(root, f), root
    return None, None, None

def get_zip_executable_candidates(folder_path):
    candidates = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.endswith(('.py', '.js', '.sh')):
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, folder_path)
                candidates.append((rel_p, full_p))
    return candidates

def auto_install_dependencies(folder_path):
    for root, _, files in os.walk(folder_path):
        if "requirements.txt" in files:
            req_file = os.path.join(root, "requirements.txt")
            flag = os.path.join(root, ".deps_installed")
            if not os.path.isfile(flag):
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"], timeout=120, check=False)
                    with open(flag, "w") as f:
                        f.write("installed")
                except Exception as e:
                    logger.error(f"Error installing requirements.txt in {root}: {e}")
        if "package.json" in files:
            flag = os.path.join(root, ".node_installed")
            if not os.path.isfile(flag):
                try:
                    subprocess.run(["npm", "install"], cwd=root, timeout=120, check=False)
                    with open(flag, "w") as f:
                        f.write("installed")
                except Exception as e:
                    logger.error(f"Error running npm install in {root}: {e}")

def try_auto_install_missing_module(err_text):
    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", err_text)
    if match:
        mod_name = match.group(1)
        pkg_name = PACKAGE_MAP.get(mod_name, mod_name)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg_name, "--quiet"], timeout=60, check=False)
            return True, pkg_name
        except Exception as e:
            logger.error(f"Error auto-installing package {pkg_name}: {e}")
    return False, None

def purge_user_file_completely(user_id, filename):
    user_id = int(user_id)
    stop_bot_process(user_id, filename)
    u = get_user(user_id)
    if filename in u.get("files", []):
        u["files"].remove(filename)
    if filename in u.get("approved_files", []):
        u["approved_files"].remove(filename)
    if filename in u.get("running_files", []):
        u["running_files"].remove(filename)
    if filename in u.get("files_data", {}):
        del u["files_data"][filename]
    save_db()

    user_dir = os.path.abspath(os.path.join(BASE_DIR, str(user_id)))
    for p in [os.path.join(user_dir, filename), os.path.join(user_dir, f"{filename}.log")]:
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass
    ext_dir = os.path.join(user_dir, os.path.splitext(filename)[0])
    if os.path.isdir(ext_dir):
        try:
            shutil.rmtree(ext_dir)
        except Exception:
            pass

# --- 24/7 Real Process Runner ---
def start_bot_process(user_id, filename):
    user_id = int(user_id)
    user_dir = os.path.abspath(os.path.join(BASE_DIR, str(user_id)))
    file_path = os.path.join(user_dir, filename)
    log_path = os.path.join(user_dir, f"{filename}.log")

    if not os.path.exists(file_path):
        return False, f"File `{filename}` not found on server disk."

    if (user_id, filename) in running_processes:
        old_proc = running_processes[(user_id, filename)]["proc"]
        if old_proc.poll() is None:
            return True, "Process is actively running 24/7!"

    cmd = None
    run_cwd = user_dir
    filename_clean = filename.strip()
    u = get_user(user_id)
    fdata = u.get("files_data", {}).get(filename, {})

    if filename_clean.endswith('.py'):
        ok_scan, rep_msg, scan_err = deep_scan_and_repair_script(file_path)
        if not ok_scan:
            return False, f"Python Syntax Error detected:\n`{scan_err}`"
        cmd = [sys.executable, "-u", file_path]

    elif filename_clean.endswith('.js'):
        cmd = ["node", file_path]

    elif filename_clean.endswith('.sh'):
        os.chmod(file_path, 0o755)
        cmd = ["bash", file_path]

    elif filename_clean.endswith('.zip'):
        extracted_folder = os.path.join(user_dir, os.path.splitext(filename_clean)[0])
        if not os.path.isdir(extracted_folder):
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extracted_folder)
            except Exception as e:
                return False, f"Error extracting ZIP archive: {e}"

        auto_install_dependencies(extracted_folder)
        custom_entry = fdata.get("custom_entry")
        if custom_entry and os.path.isfile(custom_entry):
            target_file = custom_entry
            run_cwd = os.path.dirname(custom_entry)
            lang = "py" if target_file.endswith('.py') else ("js" if target_file.endswith('.js') else "sh")
        else:
            lang, target_file, run_cwd = discover_project_entry(extracted_folder)

        if lang == "py":
            ok_scan, _, scan_err = deep_scan_and_repair_script(target_file)
            if not ok_scan:
                return False, f"Python Syntax Error in `{os.path.basename(target_file)}`:\n`{scan_err}`"
            cmd = [sys.executable, "-u", target_file]
        elif lang == "js":
            cmd = ["node", target_file]
        elif lang == "sh":
            os.chmod(target_file, 0o755)
            cmd = ["bash", target_file]
        else:
            return False, "Could not locate entry script in ZIP (e.g. main.py, bot.py or index.js)!"

    if not cmd:
        return False, "Unsupported script format!"

    try:
        if os.path.isfile(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                    tail = lf.readlines()[-500:]
                with open(log_path, "w", encoding="utf-8") as lf:
                    lf.writelines(tail)
            except Exception:
                pass

        log_out = open(log_path, "a", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = run_cwd
        preexec = os.setsid if hasattr(os, "setsid") else None

        proc = subprocess.Popen(
            cmd,
            cwd=run_cwd,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            env=env,
            preexec_fn=preexec,
            shell=False
        )
        running_processes[(user_id, filename)] = {"proc": proc, "log": log_path, "handle": log_out}

        time.sleep(0.3)
        if proc.poll() is not None:
            err_snippet = "Unknown startup error."
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = [l.strip() for l in lf.readlines() if l.strip()]
                    if lines:
                        err_snippet = lines[-1]
            except Exception:
                pass

            installed, _ = try_auto_install_missing_module(err_snippet)
            if installed:
                return start_bot_process(user_id, filename)
            return False, f"Process stopped immediately! Error:\n`{err_snippet}`"

        if filename not in u.setdefault("running_files", []):
            u["running_files"].append(filename)
        u.setdefault("files_data", {}).setdefault(filename, {})["status"] = "Running"
        u["running_bots"] = sum(1 for (uid, _), p in running_processes.items() if uid == user_id and p["proc"].poll() is None)
        save_db()
        return True, "Process started 24/7 successfully!"
    except Exception as e:
        logger.error(f"Execution failed for {filename} (User: {user_id}): {e}")
        return False, f"Execution failed: {str(e)}"

def stop_bot_process(user_id, filename):
    user_id = int(user_id)
    if (user_id, filename) in running_processes:
        proc_data = running_processes.pop((user_id, filename))
        proc = proc_data["proc"]
        try:
            if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.terminate()
            else:
                proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass

        if "handle" in proc_data:
            try:
                proc_data["handle"].close()
            except Exception:
                pass

        u = get_user(user_id)
        if filename in u.get("running_files", []):
            u["running_files"].remove(filename)
        if filename in u.get("files_data", {}):
            u["files_data"][filename]["status"] = "Stopped"
        u["running_bots"] = sum(1 for (uid, _), p in running_processes.items() if uid == user_id and p["proc"].poll() is None)
        save_db()
        return True
    return False

# --- Comprehensive Watchdog ---
def process_watchdog():
    while True:
        try:
            time.sleep(5)
            dead_instances = []
            for (uid, fn), pdata in list(running_processes.items()):
                ret = pdata["proc"].poll()
                if ret is not None:
                    dead_instances.append(((uid, fn), ret, pdata["log"], pdata.get("handle")))

            for (uid, fn), code, log_path, handle in dead_instances:
                if (uid, fn) in running_processes:
                    del running_processes[(uid, fn)]
                if handle:
                    try:
                        handle.close()
                    except Exception:
                        pass

                u = get_user(uid)
                if fn in u.get("running_files", []):
                    u["running_files"].remove(fn)
                if fn in u.get("files_data", {}):
                    u["files_data"][fn]["status"] = "Stopped"
                u["running_bots"] = sum(1 for (u_id, _), p in running_processes.items() if u_id == uid and p["proc"].poll() is None)
                save_db()

                now_ts = time.time()
                history = crash_history.setdefault((uid, fn), [])
                history.append(now_ts)
                crash_history[(uid, fn)] = [t for t in history if now_ts - t < 60]
                if len(crash_history[(uid, fn)]) > 3:
                    continue

                err_snippet = "No error output captured in log file."
                if os.path.isfile(log_path):
                    try:
                        with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                            lines = [l.strip() for l in lf.readlines() if l.strip()]
                            if lines:
                                err_snippet = "\n".join(lines[-8:])
                    except Exception:
                        pass

                if len(err_snippet) > 700:
                    err_snippet = err_snippet[-700:]

                installed, _ = try_auto_install_missing_module(err_snippet)
                if installed:
                    start_bot_process(uid, fn)
                    continue

                now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                alert_msg = (
                    f"⚠️ **Process Alert: 24/7 Bot Stopped** ⚠️\n\n"
                    f"Your hosted file exited unexpectedly:\n\n"
                    f"📁 **File:** `{fn}`\n"
                    f"📊 **Exit Code:** `{code}`\n"
                    f"⏰ **Time:** `{now_time}`\n\n"
                    f"🔍 **Last Console Output / Error:**\n"
                    f"```text\n{err_snippet}\n```\n"
                    f"💡 *Tip: Check your script dependencies, token, or syntax and restart your instance below.*"
                )

                markup = None
                if fn in u.get("files", []):
                    f_idx = u["files"].index(fn)
                    markup = InlineKeyboardMarkup(row_width=2)
                    markup.add(
                        IBtn("▶️ Restart Process", style="success", callback_data=f"run_file_{f_idx}"),
                        IBtn("📜 View Logs", style="primary", callback_data=f"logs_file_{f_idx}")
                    )
                    markup.add(
                        IBtn("📁 Manage Files", style="primary", callback_data="back_to_files")
                    )

                try:
                    bot.send_message(uid, alert_msg, parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Watchdog iteration error: {e}\n{traceback.format_exc()}")

def auto_rehost_all_approved_bots():
    rehosted_count = 0
    now = time.time()

    for uid, uinfo in list(users_db.items()):
        if uinfo.get("banned", False):
            continue
        if uinfo.get("premium_expiry") and uinfo["premium_expiry"] != "inf" and uinfo["premium_expiry"] < now:
            uinfo["status"] = "Free User"
            uinfo["premium_expiry"] = None
            save_db()

        is_prem = "Premium" in uinfo.get("status", "")
        approved_list = uinfo.get("approved_files", [])
        running_list = uinfo.get("running_files", [])
        files_data = uinfo.get("files_data", {})

        for fn in uinfo.get("files", []):
            fdata = files_data.get(fn, {})
            if fdata.get("approval") == "Rejected":
                continue
            if is_prem or fn in approved_list or fn in running_list or fdata.get("approval") == "Approved" or system_config.get("auto_approve_files"):
                ok, _ = start_bot_process(uid, fn)
                if ok:
                    rehosted_count += 1
                    if fn not in uinfo.setdefault("approved_files", []):
                        uinfo["approved_files"].append(fn)
                    fdata["approval"] = "Approved"
                    fdata["status"] = "Running"
    save_db()
    return rehosted_count

def send_admin_personal_profile(chat_id, target_admin_id):
    target_admin_id = int(target_admin_id)
    u = get_user(target_admin_id)
    is_owner = (target_admin_id == OWNER_ID)
    role_badge = "👑 Primary Owner (Protected)" if is_owner else "🛡️ Bot Administrator"
    expiry_str = "Permanent" if u.get("premium_expiry") == "inf" else (datetime.datetime.fromtimestamp(u["premium_expiry"]).strftime('%Y-%m-%d %H:%M') if u.get("premium_expiry") and u["premium_expiry"] > time.time() else "N/A")

    caption = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 🛡️ **ADMIN PERSONAL PROFILE**\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃ 🏷 **Role:** {role_badge}\n"
        f"┃ 👤 **Name:** {u.get('name', 'Admin')}\n"
        f"┃ 👑 **Username:** {u['username']}\n"
        f"┃ 🆔 **User ID:** `{target_admin_id}`\n"
        f"┃ 💎 **Account Level:** {u['status']}\n"
        f"┃ ⏳ **Premium Expiry:** `{expiry_str}`\n"
        f"┃ 📁 **Uploaded Files:** {len(u['files'])}/{u['max_files']}\n"
        f"┃ 🤖 **Running Bots:** {u['running_bots']}\n"
        f"┃ 💾 **RAM Allocated:** {u['ram']}\n"
        f"┃ 🚫 **Banned:** {'Yes' if u.get('banned') else 'No (Immune)' if is_owner else 'No'}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━┛"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    if not is_owner:
        markup.add(IBtn("🔴 Demote / Remove Admin", style="danger", callback_data=f"remove_admin_direct_{target_admin_id}"))
    markup.add(IBtn("🔙 Back to Admins List", style="primary", callback_data="admin_add_admin"))

    try:
        photos = bot.get_user_profile_photos(target_admin_id, limit=1)
        if photos.total_count > 0:
            bot.send_photo(chat_id, photo=photos.photos[0][-1].file_id, caption=caption, parse_mode="Markdown", reply_markup=markup)
            return
    except Exception:
        pass
    bot.send_message(chat_id, f"*(No Telegram profile photo found for this admin)*\n\n{caption}", parse_mode="Markdown", reply_markup=markup)

def trigger_treason_punishment(rogue_id, action_type="ban"):
    rogue_id = int(rogue_id)
    if rogue_id == OWNER_ID:
        return
    rogue_user = get_user(rogue_id)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if rogue_id in ADMIN_IDS:
        ADMIN_IDS.remove(rogue_id)
    rogue_user["banned"] = True
    rogue_user["treason_banned"] = True
    rogue_user["tried_to_ban_owner"] = True
    rogue_user["status"] = "Blacklisted Traitor 🚫"
    for fn in list(rogue_user.get("running_files", [])):
        stop_bot_process(rogue_id, fn)
    save_db()

    rogue_warning = (
        f"🛑 **SECURITY PROTOCOL: TREASON ENFORCED** 🛑\n\n"
        f"⚠️ **Access Terminated Immediately:**\n"
        f"You attempted to `{action_type.upper()}` the Supreme Bot Owner!\n\n"
        f"• Your admin privileges have been stripped.\n"
        f"• Your account is permanently counter-banned from using this bot.\n"
        f"• All your running bot instances have been terminated.\n"
        f"• **Pardon Status:** Only the Supreme Owner can pardon you."
    )
    try:
        bot.send_message(rogue_id, rogue_warning, parse_mode="Markdown", reply_markup=contact_owner_to_unban_keyboard())
    except Exception:
        pass

    owner_dossier = (
        f"🚨 **SECURITY ALERT: OWNER ATTACK BLOCKED!** 🚨\n\n"
        f"An administrator tried to `{action_type.upper()}` you!\n\n"
        f"┏━━━━━━━━━━ Offender Details ━━━━━━━━━━\n"
        f"┣ 👤 **Name:** {rogue_user.get('name', 'Admin')}\n"
        f"┣ 👑 **Username:** {rogue_user.get('username', 'N/A')}\n"
        f"┣ 🆔 **User ID:** `{rogue_id}`\n"
        f"┣ 📁 **Files Hosted:** {len(rogue_user.get('files', []))}\n"
        f"┣ 🤖 **Running Bots:** {rogue_user.get('running_bots', 0)}\n"
        f"┣ ⏱️ **Timestamp:** `{timestamp}`\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛡️ **Defensive Countermeasures Taken:**\n"
        f"✅ Your Owner account was fully protected.\n"
        f"✅ Offender `{rogue_id}` was demoted from Admin.\n"
        f"✅ Offender was counter-banned permanently with Supreme Lock."
    )
    try:
        photos = bot.get_user_profile_photos(rogue_id, limit=1)
        if photos.total_count > 0:
            bot.send_photo(OWNER_ID, photo=photos.photos[0][-1].file_id, caption=owner_dossier, parse_mode="Markdown", reply_markup=owner_pardon_markup(rogue_id))
            return
    except Exception:
        pass
    try:
        bot.send_message(OWNER_ID, owner_dossier, parse_mode="Markdown", reply_markup=owner_pardon_markup(rogue_id))
    except Exception:
        pass

# ================= TELEGRAM HANDLERS =================
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username, message.from_user.first_name)
    if user.get("banned", False) and user_id != OWNER_ID:
        if user.get("treason_banned", False):
            bot.send_message(
                message.chat.id,
                "⛔ **HIGH SECURITY LOCKDOWN**\n\n"
                "Your account was permanently terminated for attempting to compromise or unban threats against the Supreme Bot Owner.\n"
                "🛡️ *Pardon Authorization:* **SUPREME OWNER ONLY**.",
                parse_mode="Markdown", reply_markup=contact_owner_to_unban_keyboard()
            )
        else:
            bot.send_message(message.chat.id, "⛔ **Access Denied:** You have been permanently banned from using this bot.", parse_mode="Markdown")
        return

    if not check_subscription(user_id):
        send_force_sub_message(message.chat.id, user_id)
        return

    name = message.from_user.first_name
    caption = system_config.get("welcome_text", DEFAULT_WELCOME_TEXT).replace("{name}", str(name))\
                      .replace("{id}", str(user_id))\
                      .replace("{username}", str(user['username']))\
                      .replace("{status}", str(user['status']))\
                      .replace("{files}", str(len(user['files'])))\
                      .replace("{max_files}", str(user['max_files']))\
                      .replace("{ram}", str(user['ram']))

    try:
        photos = bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            bot.send_photo(message.chat.id, photo=photos.photos[0][-1].file_id, caption=caption, reply_markup=bottom_reply_keyboard(user_id), parse_mode="Markdown")
            return
    except Exception:
        pass
    bot.send_message(message.chat.id, caption, reply_markup=bottom_reply_keyboard(user_id), parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username, message.from_user.first_name)
    if (user.get("banned", False) and user_id != OWNER_ID) or not is_admin(user_id):
        bot.reply_to(message, "⛔ You are not authorized to use the admin panel.")
        return

    channels = system_config.get("force_channels", [])
    ch_text = ", ".join(channels) if channels else "None (Disabled)"
    dev_username = system_config.get('developer_username', DEFAULT_DEVELOPER)
    dev_display = "Not Set" if dev_username == "None" else f"@{dev_username.lstrip('@')}"
    updates_ch = system_config.get('updates_channel', 'Not Set')
    owner = system_config['owner_username']
    total_premiums = sum(1 for u in users_db.values() if "Premium" in u.get("status", ""))
    total_files = sum(len(u.get("files", [])) for u in users_db.values())
    active_hosted = count_active_hosted_files()

    admin_text = (
        f"⚙️ **Admin Control Panel**\n\n"
        f"🔗 Force-Join Channels ({len(channels)}): `{ch_text}`\n"
        f"📁 Total Files Uploaded: `{total_files}`\n"
        f"🚀 Active Running Bots: `{active_hosted}`\n"
        f"👨‍💻 Current Developer: `{dev_display}`\n"
        f"📢 Updates Link: `{updates_ch}`\n"
        f"👤 Current Owner: `@{owner.lstrip('@')}`\n"
        f"💳 Payment UPI ID: `{system_config['payment_upi']}`\n"
        f"💎 Active Premium Users: `{total_premiums}`\n"
        f"🛡️ Total Admins: `{len(ADMIN_IDS)}`\n"
        f"👥 Total Active Users: `{len(users_db)}`\n\n"
        f"Select an option below:"
    )
    bot.send_message(
        message.chat.id, admin_text,
        reply_markup=admin_panel_keyboard(user_id),
        parse_mode="Markdown", disable_web_page_preview=True
    )

@bot.message_handler(commands=['ban'])
def handle_ban_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return
    parts = message.text.strip().split()
    if len(parts) > 1:
        message.text = parts[1]
        process_ban_user(message)
    else:
        msg = bot.reply_to(message, "✍️ Send the target **User ID** to ban them:")
        bot.register_next_step_handler(msg, process_ban_user)

@bot.message_handler(commands=['unban'])
def handle_unban_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return
    parts = message.text.strip().split()
    if len(parts) > 1:
        message.text = parts[1]
        process_unban_user(message)
    else:
        msg = bot.reply_to(message, "✍️ Send the target **User ID** to unban them:")
        bot.register_next_step_handler(msg, process_unban_user)

@bot.message_handler(commands=['id'])
def send_id(message):
    bot.reply_to(message, f"🆔 Your Telegram User ID is: `{message.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(
        message,
        "🛠️ **Hosting Help & FAQ**\n\n"
        "• Send any `.py`, `.js`, or full `.zip` project archive directly to this bot.\n"
        "• All files are saved securely on server disk.\n"
        "• Go to **Check Files** to control execution, restart, pick main file in zip, and view real-time logs.\n"
        "• If a script crashes, the bot will automatically send an alert with error logs.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['cancel'])
def cancel_action(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    bot.reply_to(message, "✅ Current action cancelled.", reply_markup=bottom_reply_keyboard(message.from_user.id))

# --- Reply Keyboard Text Handling ---
@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username, message.from_user.first_name)
    if user.get("banned", False) and user_id != OWNER_ID:
        return
    if not check_subscription(user_id):
        send_force_sub_message(message.chat.id, user_id)
        return

    text = message.text

    if text in ["📢 Updates Channel", "📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ"]:
        updates_link = system_config.get('updates_channel', "https://t.me/telegram")
        markup = InlineKeyboardMarkup()
        markup.add(IBtn("📢 JOIN UPDATES CHANNEL", style="success", url=updates_link))
        bot.send_message(
            message.chat.id,
            "📢 **Click below to join our official updates channel for announcements and bot updates!**",
            reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True
        )

    elif text in ["⌚ Uptime", "⌚ Uᴘᴛɪᴍᴇ"]:
        uptime_seconds = int(time.time() - START_TIME)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        bot.send_message(message.chat.id, f"⏱️ **Bot Uptime:** {days}d {hours}h {minutes}m {seconds}s", parse_mode="Markdown")

    elif text in ["📤 Upload File", "📤 Uᴘʟᴏᴀᴅ Fɪʟᴇ"]:
        bot.send_message(
            message.chat.id,
            "📤 **Send your Python (`.py`), JavaScript (`.js`), or `.zip` project file.**\n\n"
            "📦 Large files and zipped multi-file bots are supported!\n"
            "🗃️ *For .zip files, you can pick which file inside to execute.* \n"
            "💎 **__Premium users: files are auto-approved & auto-hosted 24/7!__**",
            parse_mode="Markdown"
        )

    elif text in ["📁 Check Files", "🗂️ Cʜᴇᴄᴋ Fɪʟᴇs"]:
        if not user["files"]:
            bot.send_message(message.chat.id, "📁 **Your Files:**\n\n(No hosted files uploaded yet. Send a file to start!)", parse_mode="Markdown")
        else:
            list_text = "📁 **Your Files:**\n\n"
            files_data = user.get("files_data", {})
            for fn in user["files"]:
                fdata = files_data.get(fn, {})
                approval = fdata.get("approval", "Pending")
                is_running = (user_id, fn) in running_processes and running_processes[(user_id, fn)]["proc"].poll() is None
                if approval == "Rejected":
                    status_str = "❌ Rejected"
                elif is_running:
                    status_str = "🟢 Running"
                elif approval == "Approved":
                    status_str = "🔴 Stopped"
                else:
                    status_str = "⏳ Pending"
                list_text += f"• `{fn}` - **{status_str}**\n"
            bot.send_message(message.chat.id, list_text, reply_markup=user_files_keyboard(user_id), parse_mode="Markdown")

    elif text in ["⚡ Bot Speed", "⚡ Bᴏᴛ Sᴘᴇᴇᴅ"]:
        start_t = time.time()
        msg = bot.send_message(message.chat.id, "⚡ Testing speed...")
        end_t = time.time()
        ping_ms = round((end_t - start_t) * 1000, 2)
        speed_text = f"⚡ **Bot Speed & Status:**\n\nAPI Response Time: `{ping_ms} ms`\nBot Status: Unlocked\nYour Level: {user['status']}"
        bot.edit_message_text(speed_text, message.chat.id, msg.message_id, parse_mode="Markdown")

    elif text in ["📊 Statistics", "📊 Sᴛᴀᴛɪsᴛɪᴄs"]:
        active_cnt = sum(1 for (uid, fn), p in running_processes.items() if p["proc"].poll() is None)
        stats_text = (
            f"📊 **Bot Statistics:**\n\n"
            f"Total Users: `{len(users_db)}`\n"
            f"Total Files Uploaded: `{global_stats['total_file_records']}`\n"
            f"Total Active Processes: `{active_cnt}`\n"
            f"Your Running Bots: `{user['running_bots']}`"
        )
        bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

    elif text in ["💎 Premium Plans", "💎 Pʀᴇᴍɪᴜᴍ Pʟᴀɴs"]:
        plans = system_config["plans"]
        plans_text = f"💎 **Premium Plans - ✧ Sɪʟᴇɴᴛ Kɪʟʟᴇ r ✧**\n\n"
        for code, p in plans.items():
            days_label = f"{p['days']} days" if p['days'] != "inf" else "Permanent"
            plans_text += f"• **{p['name']}:** {p['price']} — {days_label}\n"
        plans_text += "\nChoose a plan below:"
        bot.send_message(message.chat.id, plans_text, reply_markup=premium_plans_keyboard(), parse_mode="Markdown")

    elif text in ["📞 Contact Owner", "📞 Cᴏɴᴛᴀᴄᴛ Oᴡɴᴇʀ"]:
        owner = system_config['owner_username']
        markup = InlineKeyboardMarkup()
        markup.add(IBtn("💬 SEND MESSAGE", style="success", url=f"https://t.me/{owner.lstrip('@')}"))
        bot.send_message(
            message.chat.id,
            "💬 **Have any questions or need support? Click the button below to message the owner directly!**",
            reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True
        )

    elif text in ["✧ Silent Killer ✧ AI", "✧ Sɪʟᴇɴᴛ Kɪʟʟᴇʀ ✧ AI"]:
        bot.send_message(message.chat.id, "🤖 **Ai Assistant:** I am your assistant. Send your code scripts or ask me questions regarding your hosting configuration!", parse_mode="Markdown")

    elif text in ["👨‍💻 Bot Developer", "👨‍💻 Bᴏᴛ Dᴇᴠᴇʟᴏᴘᴇʀ"]:
        dev = system_config.get('developer_username', DEFAULT_DEVELOPER)
        if dev == "None":
            bot.send_message(message.chat.id, "👨‍💻 Developer info is currently not set.", parse_mode="Markdown")
        else:
            markup = InlineKeyboardMarkup()
            markup.add(IBtn("💬 Contact Developer", style="success", url=f"https://t.me/{dev.lstrip('@')}"))
            bot.send_message(
                message.chat.id,
                f"👨‍💻 **Bot Developer Profile**\n\n"
                f"• **Lead Developer:** `@{dev.lstrip('@')}`\n"
                f"• **Platform:** ✧ Sɪʟᴇɴᴛ Kɪʟʟᴇ r ✧ Hosting Bot\n\n"
                f"Click the button below to contact the developer directly for custom bots, feature requests, or technical support:",
                reply_markup=markup, parse_mode="Markdown"
            )

    elif text in ["❓ Help", "❓ Hᴇʟᴘ"]:
        markup = InlineKeyboardMarkup(row_width=1)
        if system_config.get("tutorial_video"):
            markup.add(IBtn("📹 Tutorial Video", style="primary", callback_data="show_tutorial_video"))
        owner = system_config.get('owner_username', OWNER_USERNAME).lstrip('@')
        markup.add(IBtn("💬 Ask the admin how to host", style="primary", url=f"https://t.me/{owner}"))
        help_text = (
            "❓ **How to Host Your File**\n\n"
            "1️⃣ Upload your `.py`, `.js`, `.sh`, or `.zip` file directly to this chat.\n"
            "2️⃣ The bot will securely save it. If you are Premium or Auto-Approve is ON, it will start instantly 24/7.\n"
            "3️⃣ If not, wait for an Admin to approve it.\n"
            "4️⃣ Use **📁 Check Files** to manage your bots (Start, Stop, Restart, View Logs).\n\n"
            "Need more help? Choose an option below:"
        )
        bot.send_message(message.chat.id, help_text, reply_markup=markup, parse_mode="Markdown")

    elif text in ["☣️ Admin Control", "☣️ Aᴅᴍɪɴ Cᴏɴᴛʀᴏʟ"]:
        if not is_admin(user_id):
            return
        admin_command(message)

# --- Callbacks ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    user = get_user(user_id, call.from_user.username, call.from_user.first_name)

    if user.get("banned", False) and user_id != OWNER_ID:
        bot.answer_callback_query(call.id, "⛔ Access Terminated: You are banned!", show_alert=True)
        return

    if call.data.startswith("owner_ban_admin_"):
        if call.from_user.id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ Supreme Owner authorization required!", show_alert=True)
            return
        target_uid = int(call.data.split('_')[3])
        target_u = get_user(target_uid)
        if target_uid in ADMIN_IDS:
            ADMIN_IDS.remove(target_uid)
        target_u["banned"] = True
        target_u["treason_banned"] = True
        target_u["tried_to_ban_owner"] = True
        target_u["status"] = "Blacklisted Traitor 🚫"
        for fn in list(target_u.get("running_files", [])):
            stop_bot_process(target_uid, fn)
        save_db()
        log_admin_action(OWNER_ID, "Owner Banned Admin", f"Target Admin ID: `{target_uid}`")
        bot.answer_callback_query(call.id, f"✅ Admin {target_uid} instantly banned!", show_alert=True)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        return

    if call.data == "check_sub":
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, "✅ Verified! Welcome aboard.")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            bot.send_message(
                call.message.chat.id,
                "🎉 **Verification Successful!**\n\nThank you for joining our official channel(s). All hosting features and commands are now unlocked!",
                parse_mode="Markdown"
            )
            fake_message = call.message
            fake_message.from_user = call.from_user
            send_welcome(fake_message)
        else:
            bot.answer_callback_query(call.id, "❌ You haven't joined all required channels yet!", show_alert=True)
            send_force_sub_message(call.message.chat.id, user_id)
        return

    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "❌ Please join all official channels first!", show_alert=True)
        send_force_sub_message(call.message.chat.id, user_id)
        return

    elif call.data == "admin_users":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        total_users = len(users_db)
        if total_users == 0:
            bot.send_message(call.message.chat.id, "👥 **User Directory is currently empty.**", parse_mode="Markdown")
            return
        bot.send_message(call.message.chat.id, f"👥 **Total Registered Users: {total_users}**\n\nFetching profile cards with photos...", parse_mode="Markdown")
        for uid, uinfo in users_db.items():
            is_adm = "Yes (Owner)" if uid == OWNER_ID else ("Yes" if uid in ADMIN_IDS else "No")
            expiry_str = "Permanent" if uinfo.get("premium_expiry") == "inf" else (datetime.datetime.fromtimestamp(uinfo["premium_expiry"]).strftime('%Y-%m-%d %H:%M') if uinfo.get("premium_expiry") else "N/A")
            card_text = (
                f"👤 **ID:** `{uid}`\n"
                f"👑 **Username:** {uinfo['username']}\n"
                f"🏷 **Status:** {uinfo['status']}\n"
                f"⏳ **Expires:** `{expiry_str}`\n"
                f"🛡️ **Admin:** {is_adm}\n"
                f"📁 **Files:** {len(uinfo['files'])}/{uinfo['max_files']}\n"
                f"💾 **RAM:** {uinfo['ram']}\n"
                f"🚫 **Banned:** {uinfo.get('banned', False)}"
            )
            markup = InlineKeyboardMarkup(row_width=3)
            talk_url = f"https://t.me/{uinfo['username'].lstrip('@')}" if str(uinfo.get('username','')).startswith('@') else f"tg://user?id={uid}"
            markup.add(
                IBtn("💬 Talk", style="primary", url=talk_url),
                IBtn("🔴 Ban", style="danger", callback_data=f"ban_user_direct_{uid}"),
                IBtn("🟢 Unban", style="success", callback_data=f"unban_user_direct_{uid}")
            )
            sent_photo = False
            try:
                photos = bot.get_user_profile_photos(uid, limit=1)
                if photos.total_count > 0:
                    bot.send_photo(call.message.chat.id, photo=photos.photos[0][-1].file_id, caption=card_text, reply_markup=markup, parse_mode="Markdown")
                    sent_photo = True
            except Exception:
                pass
            if not sent_photo:
                bot.send_message(call.message.chat.id, card_text, reply_markup=markup, parse_mode="Markdown")
            time.sleep(0.15)

    elif call.data == "admin_pending_files":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        pending_list = []
        for uid, uinfo in users_db.items():
            for fn, fdata in uinfo.get("files_data", {}).items():
                if fdata.get("approval") == "Pending":
                    pending_list.append((uid, fn, fdata))
        if not pending_list:
            bot.send_message(call.message.chat.id, "📭 **No files are currently waiting for approval.**", parse_mode="Markdown")
            return
        bot.send_message(call.message.chat.id, f"⏳ **Files Waiting for Review ({len(pending_list)}):**", parse_mode="Markdown")
        for uid, fn, fdata in pending_list:
            u = get_user(uid)
            file_hash = hashlib.md5(fn.encode()).hexdigest()[:8]
            caption = (
                f"⏳ **Pending Review File**\n\n"
                f"👤 **User:** {u.get('name')} (`{uid}`)\n"
                f"👑 **Username:** {u.get('username')}\n"
                f"📄 **File:** `{fn}`\n"
                f"📊 **Type:** `{fdata.get('type')}`\n"
                f"💾 **Allocated RAM:** `{u.get('ram')}`"
            )
            markup = InlineKeyboardMarkup(row_width=3)
            markup.add(
                IBtn("✅ Approve", style="success", callback_data=f"adm_app_{uid}_{file_hash}"),
                IBtn("❌ Reject", style="danger", callback_data=f"adm_rej_{uid}_{file_hash}"),
                IBtn("📥 Download", style="primary", callback_data=f"adm_dl_{uid}_{file_hash}")
            )
            bot.send_message(call.message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")
            time.sleep(0.15)

    elif call.data == "admin_hosted_files":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        active_hosted_list = []
        for (uid, fn), pdata in list(running_processes.items()):
            if pdata["proc"].poll() is None:
                u = get_user(uid)
                fdata = u.get("files_data", {}).get(fn, {})
                active_hosted_list.append((uid, fn, fdata, u))

        if not active_hosted_list:
            bot.send_message(call.message.chat.id, "📭 **No files are currently being actively hosted 24/7 on the server.**", parse_mode="Markdown")
            return

        bot.send_message(call.message.chat.id, f"🚀 **Active 24/7 Hosted Files ({len(active_hosted_list)} Instances Running):**", parse_mode="Markdown")
        for uid, fn, fdata, u in active_hosted_list:
            file_hash = hashlib.md5(fn.encode()).hexdigest()[:8]
            ext = fdata.get("type", fn.split('.')[-1].strip())
            f_size = fdata.get("size", "Unknown")
            days_hosted_str = get_file_hosted_days_str(fdata)
            talk_url = f"https://t.me/{u['username'].lstrip('@')}" if str(u.get('username','')).startswith('@') else f"tg://user?id={uid}"

            caption_card = (
                f"┏━━━━━━━━ Active Hosted Bot ━━━━━━━━┓\n"
                f"┣ 📁 **File:** `{fn}`\n"
                f"┣ 📊 **Type:** `{ext}` | **Size:** `{f_size}`\n"
                f"┣ ⏱️ **Hosted For:** `{days_hosted_str}`\n"
                f"┣ 🟢 **Execution Status:** Running 24/7\n"
                f"┣ 👤 **Hosted By:** {u.get('name', 'User')}\n"
                f"┣ 👑 **Username:** {u.get('username', 'N/A')}\n"
                f"┣ 🆔 **User ID:** `{uid}`\n"
                f"┣ 💎 **Tier:** {u.get('status', 'Free User')}\n"
                f"┣ 📦 **Total Projects:** `{len(u.get('files', []))}/{u.get('max_files')}`\n"
                f"┣ 💾 **RAM Allocation:** `{u.get('ram')}`\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
            )

            action_markup = InlineKeyboardMarkup(row_width=3)
            action_markup.add(
                IBtn("📥 Download", style="primary", callback_data=f"adm_dl_{uid}_{file_hash}"),
                IBtn("💬 Talk to User", style="primary", url=talk_url),
                IBtn("🛑 Cancel Host", style="danger", callback_data=f"adm_cancel_host_{uid}_{file_hash}")
            )
            bot.send_message(call.message.chat.id, caption_card, reply_markup=action_markup, parse_mode="Markdown")
            time.sleep(0.15)

    elif call.data.startswith("adm_cancel_host_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[3]), parts[4]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            bot.answer_callback_query(call.id, "❌ File not found in user database.", show_alert=True)
            return

        stop_bot_process(target_uid, target_fn)
        if target_fn in target_u.get("approved_files", []):
            target_u["approved_files"].remove(target_fn)
        if target_fn in target_u.setdefault("files_data", {}):
            target_u["files_data"][target_fn]["approval"] = "Stopped"
            target_u["files_data"][target_fn]["status"] = "Stopped"
        save_db()

        log_admin_action(user_id, "Cancelled Hosted File", f"File: `{target_fn}` | User ID: `{target_uid}`")
        bot.answer_callback_query(call.id, f"🛑 Hosting cancelled for `{target_fn}`! (File kept safe on disk)", show_alert=True)
        try:
            bot.edit_message_text(
                call.message.text + f"\n\n🛑 **HOSTING CANCELLED BY ADMIN**\n*File is safely stored on server, execution terminated.*",
                call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=None
            )
        except Exception:
            pass
        try:
            bot.send_message(
                target_uid,
                f"🛑 **Notice: Hosting Cancelled by Admin**\n\n📁 **File:** `{target_fn}`\n"
                f"Your 24/7 hosting for this file has been halted by administration.\n"
                f"💾 *Note: Your file is still safely saved in your account. You can check it under '📁 Check Files'.*",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif call.data == "admin_refresh_all":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id, "🔄 Refreshing all bots, disk files, and databases...", show_alert=False)
        load_db()
        rehosted_count = auto_rehost_all_approved_bots()
        active_cnt = count_active_hosted_files()
        total_files = sum(len(u.get("files", [])) for u in users_db.values())
        log_admin_action(user_id, "System Refresh", f"Refreshed all files, rehosted: {rehosted_count}, active: {active_cnt}")

        refresh_report = (
            f"✅ **Bot System Refreshed Successfully!**\n\n"
            f"• 📁 **Total Files Synced on Disk:** `{total_files}`\n"
            f"• 🚀 **Active 24/7 Running Bots:** `{active_cnt}`\n"
            f"• 🔄 **Bots Rehosted / Verified:** `{rehosted_count}`\n"
            f"• 💾 **Database & Storage Status:** 100% Synced & Protected\n"
            f"• ⏰ **Refreshed At:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_panel_keyboard(user_id))
        except Exception:
            pass
        bot.send_message(call.message.chat.id, refresh_report, parse_mode="Markdown")

    elif call.data == "admin_manage_plans":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="✏️ **Subscription Plans Manager**\nSelect a plan below to edit its name, price, or duration:",
            reply_markup=admin_plans_menu(), parse_mode="Markdown"
        )

    elif call.data == "admin_set_host_limits":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        def_free_files = system_config.get("default_max_files", 2)
        def_free_ram = system_config.get("default_ram", "512 MB")
        def_prem_files = system_config.get("premium_max_files", 10)
        def_prem_ram = system_config.get("premium_ram", "2048 MB")
        info_limits = (
            f"📦 **Hosting Limits Configuration**\n\n"
            f"🆓 **Free Tier Current Limits:**\n"
            f"• Max Projects per User: `{def_free_files}`\n"
            f"• RAM Limit per Bot: `{def_free_ram}`\n\n"
            f"💎 **Premium Tier Current Limits:**\n"
            f"• Max Projects per User: `{def_prem_files}`\n"
            f"• RAM Limit per Bot: `{def_prem_ram}`\n\n"
            f"Tap any button below to update limits dynamically for all users:"
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=info_limits, reply_markup=admin_host_limits_keyboard(), parse_mode="Markdown"
        )

    elif call.data == "set_def_files_prompt":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Reply with the new **Free User max files limit** (e.g. `3`, `5`, `7`, `777`):")
        bot.register_next_step_handler(msg, process_set_default_files)

    elif call.data == "set_def_ram_prompt":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Reply with the new **Free User RAM limit** (e.g. `123`, `512 MB`, `1024 MB`, `2064`):")
        bot.register_next_step_handler(msg, process_set_default_ram)

    elif call.data == "set_prem_files_prompt":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Reply with the new **Premium User max files limit** (e.g. `15`, `20`, `50`):")
        bot.register_next_step_handler(msg, process_set_premium_files)

    elif call.data == "set_prem_ram_prompt":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Reply with the new **Premium User RAM limit** (e.g. `2048 MB`, `4096 MB`, `4 GB`):")
        bot.register_next_step_handler(msg, process_set_premium_ram)

    elif call.data == "admin_rearrange_layout":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            IBtn("1️⃣ Default Balanced Layout", style="primary", callback_data="set_layout_default"),
            IBtn("2️⃣ Hosting & Files First", style="primary", callback_data="set_layout_files_first"),
            IBtn("3️⃣ Config & Settings First", style="primary", callback_data="set_layout_config_first"),
            IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back")
        )
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="🔀 **Admin Panel Layout Customizer**\nChoose how you want buttons positioned:",
            reply_markup=markup, parse_mode="Markdown"
        )

    elif call.data.startswith("set_layout_"):
        if not is_admin(user_id):
            return
        new_order = call.data.replace("set_layout_", "")
        system_config["admin_layout_order"] = new_order
        save_db()
        bot.answer_callback_query(call.id, "✅ Layout updated!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="⚙️ **Admin Control Panel**\nLayout order refreshed successfully.",
            reply_markup=admin_panel_keyboard(user_id), parse_mode="Markdown"
        )

    elif call.data == "admin_audit_logs":
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ Supreme Owner authorization required!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="🕵️ **Administrator Activity Audit**\n\nSelect an administrator below to inspect actions:",
            reply_markup=admin_activity_selection_keyboard(), parse_mode="Markdown"
        )

    elif call.data.startswith("view_adm_acts_"):
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ Supreme Owner authorization required!", show_alert=True)
            return
        target_adm_id = int(call.data.split('_')[3])
        bot.answer_callback_query(call.id)
        show_admin_activities(call.message.chat.id, target_adm_id, message_id=call.message.message_id)

    elif call.data.startswith("clear_adm_acts_"):
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ Supreme Owner authorization required!", show_alert=True)
            return
        target_adm_id = int(call.data.split('_')[3])
        if str(target_adm_id) in admin_logs:
            admin_logs[str(target_adm_id)] = []
            save_admin_logs()
        bot.answer_callback_query(call.id, f"🧹 Cleared activity logs for Admin {target_adm_id}!", show_alert=True)
        show_admin_activities(call.message.chat.id, target_adm_id, message_id=call.message.message_id)

    elif call.data == "admin_set_tutorial":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        vid_id = system_config.get("tutorial_video")
        status_txt = "🟢 **Active & Uploaded**" if vid_id else "🔴 **Not Set**"
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"📹 **Manage Tutorial Video**\n\n• Status: {status_txt}\n\nUse the buttons below to upload, replace, or preview the video:",
            reply_markup=admin_tutorial_keyboard(), parse_mode="Markdown"
        )

    elif call.data == "tut_upload_prompt":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup()
        markup.add(IBtn("❌ Cancel", style="danger", callback_data="admin_set_tutorial"))
        msg = bot.send_message(call.message.chat.id, "📹 **Please upload or forward the tutorial video file right now:**", reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_set_tutorial)

    elif call.data == "tut_delete":
        if not is_admin(user_id):
            return
        system_config["tutorial_video"] = None
        save_db()
        log_admin_action(user_id, "Deleted Tutorial Video", "Tutorial video deleted")
        bot.answer_callback_query(call.id, "✅ Tutorial video deleted!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="📹 **Manage Tutorial Video**\n\n• Status: 🔴 **Not Set**\n\nTutorial video removed.",
            reply_markup=admin_tutorial_keyboard(), parse_mode="Markdown"
        )

    elif call.data == "show_tutorial_video":
        vid_id = system_config.get("tutorial_video")
        if vid_id:
            bot.answer_callback_query(call.id, "📹 Sending tutorial video...")
            try:
                bot.send_video(call.message.chat.id, vid_id, caption="📹 **Tutorial Video**", parse_mode="Markdown")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Failed to send video: {e}")
        else:
            bot.answer_callback_query(call.id, "❌ No tutorial video currently set.", show_alert=True)

    elif call.data == "admin_view_files":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        total_files = sum(len(u.get("files", [])) for u in users_db.values())
        if total_files == 0:
            bot.send_message(call.message.chat.id, "📭 **No files have been uploaded to the server yet.**", parse_mode="Markdown")
            return
        bot.send_message(call.message.chat.id, f"📁 **Scanning Server Storage ({total_files} Files Total)...**", parse_mode="Markdown")
        for uid, uinfo in list(users_db.items()):
            files_list = uinfo.get("files", [])
            if not files_list:
                continue
            files_data = uinfo.get("files_data", {})
            user_display_name = uinfo.get("name", "User")
            username_display = uinfo.get("username", "N/A")
            user_status = uinfo.get("status", "Free User")
            total_user_files = len(files_list)
            for f_idx, fn in enumerate(files_list):
                file_hash = hashlib.md5(fn.encode()).hexdigest()[:8]
                fdata = files_data.get(fn, {})
                ext = fdata.get("type", fn.split('.')[-1].strip())
                f_size = fdata.get("size", "Unknown")
                f_time = fdata.get("upload_time", "N/A")
                approval_state = fdata.get("approval", "Pending")
                is_running = (uid, fn) in running_processes and running_processes[(uid, fn)]["proc"].poll() is None
                running_status_str = "🟢 Running 24/7" if is_running else "🔴 Stopped"
                approval_badge = "✅ Approved" if approval_state == "Approved" else ("❌ Declined" if approval_state == "Rejected" else "⏳ Pending")

                caption_text = (
                    f"┏━━━━━━ File & User Details ━━━━━━┓\n"
                    f"┣ 👤 Name: {user_display_name}\n"
                    f"┣ 👑 Username: {username_display}\n"
                    f"┣ 🆔 User ID: {uid}\n"
                    f"┣ 💎 Account Level: {user_status}\n"
                    f"┣ 📁 Total Files Uploaded by User: {total_user_files}\n"
                    f"┣ 📄 File Name: {fn}\n"
                    f"┣ 📊 Type: {ext} | Size: {f_size}\n"
                    f"┣ 🔄 Execution Status: {running_status_str}\n"
                    f"┣ 📝 Approval: {approval_badge}\n"
                    f"┣ ⏰ Uploaded At: {f_time}\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
                )
                action_markup = InlineKeyboardMarkup(row_width=3)
                action_markup.add(
                    IBtn("✅ Approve", style="success", callback_data=f"adm_app_{uid}_{file_hash}"),
                    IBtn("❌ Decline", style="danger", callback_data=f"adm_rej_{uid}_{file_hash}"),
                    IBtn("📥 Download", style="primary", callback_data=f"adm_dl_{uid}_{file_hash}")
                )
                bot.send_message(call.message.chat.id, caption_text, reply_markup=action_markup)
                time.sleep(0.15)

    elif call.data.startswith("adm_app_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[2]), parts[3]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            return
        if target_fn not in target_u.setdefault("approved_files", []):
            target_u["approved_files"].append(target_fn)
        if target_fn in target_u.setdefault("files_data", {}):
            target_u["files_data"][target_fn]["approval"] = "Approved"
        save_db()
        ok, start_msg = start_bot_process(target_uid, target_fn)
        log_admin_action(user_id, "Approved File (Files Hub)", f"File: `{target_fn}` | Owner ID: `{target_uid}`")
        bot.answer_callback_query(call.id, "✅ File approved and running 24/7!", show_alert=True)
        try:
            bot.send_message(
                target_uid,
                f"🎉 **File Approved by Admin!**\n\n📁 **File:** `{target_fn}`\n"
                f"Your file has been approved and is now actively hosted 24/7! Check **Check Files** menu to view live console logs.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif call.data.startswith("adm_rej_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[2]), parts[3]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            return
        purge_user_file_completely(target_uid, target_fn)
        log_admin_action(user_id, "Declined & Purged File (Files Hub)", f"File: `{target_fn}` | User ID: `{target_uid}`")
        bot.answer_callback_query(call.id, "❌ File declined & purged from server disk!", show_alert=True)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        try:
            bot.send_message(
                target_uid,
                f"❌ **File Declined & Deleted!**\n\n📁 **File:** `{target_fn}`\n"
                f"**Notice:** Your file was declined and has been completely deleted from server disk storage.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif call.data.startswith("adm_dl_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[2]), parts[3]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            return
        file_path = os.path.join(BASE_DIR, str(target_uid), target_fn)
        if os.path.isfile(file_path):
            with open(file_path, "rb") as df:
                bot.send_document(call.message.chat.id, df, caption=f"📄 **File:** `{target_fn}`\n👤 **Owner ID:** `{target_uid}`", parse_mode="Markdown")

    elif call.data.startswith("owner_pardon_"):
        if call.from_user.id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ Supreme Owner authorization required!", show_alert=True)
            return
        target_uid = int(call.data.split('_')[2])
        target_u = get_user(target_uid)
        target_u["banned"] = False
        target_u["treason_banned"] = False
        target_u["tried_to_ban_owner"] = False
        target_u["unban_traitor_warnings"] = 0
        target_u["status"] = "Free User"
        save_db()
        log_admin_action(OWNER_ID, "Owner Pardoned User", f"Target ID: `{target_uid}`")
        bot.answer_callback_query(call.id, f"✅ User {target_uid} pardoned and unbanned!", show_alert=True)
        try:
            bot.send_message(target_uid, "🎉 **Pardon Granted by Supreme Owner!** Restrictions lifted.", parse_mode="Markdown")
        except Exception:
            pass

    elif call.data == "admin_add_admin":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🛡️ **Admin Management:** Select user to promote:", reply_markup=admins_list_keyboard(user_id), parse_mode="Markdown")

    elif call.data == "admin_remove_admin":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔴 **Remove Admin:** Select admin to demote:", reply_markup=admin_remove_selection_keyboard(), parse_mode="Markdown")

    elif call.data.startswith("show_admin_prof_"):
        if not is_admin(user_id):
            return
        target_admin_id = int(call.data.split('_')[3])
        bot.answer_callback_query(call.id)
        send_admin_personal_profile(call.message.chat.id, target_admin_id)

    elif call.data.startswith("promote_user_"):
        if not is_admin(user_id):
            return
        target_id = int(call.data.split('_')[2])
        target_user = get_user(target_id)
        sender_user = get_user(user_id, call.from_user.username, call.from_user.first_name)
        if sender_user.get("treason_banned", False) or sender_user.get("tried_to_ban_owner", False):
            bot.answer_callback_query(call.id, "⛔ Access Denied: Traitors cannot promote admins!", show_alert=True)
            return
        if (target_user.get("treason_banned", False) or target_user.get("tried_to_ban_owner", False)) and user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "🛑 BLOCKED: Cannot promote a user who attacked Owner!", show_alert=True)
            return
        if target_id not in ADMIN_IDS:
            ADMIN_IDS.append(target_id)
            if user_id == OWNER_ID:
                target_user["treason_banned"] = False
                target_user["tried_to_ban_owner"] = False
                target_user["banned"] = False
            save_db()
            log_admin_action(user_id, "Promoted User to Admin", f"Promoted User ID: `{target_id}`")
            bot.answer_callback_query(call.id, f"✅ User {target_id} added as Admin!")
            promote_card = generate_action_card("promote", target_id, user_id)
            bot.send_message(call.message.chat.id, promote_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, promote_card, parse_mode="Markdown")
            except Exception:
                pass
            send_admin_personal_profile(call.message.chat.id, target_id)

    elif call.data.startswith("remove_admin_direct_"):
        if not is_admin(user_id):
            return
        target_id = int(call.data.split('_')[3])
        if target_id == OWNER_ID:
            if user_id == OWNER_ID:
                bot.answer_callback_query(call.id, "👑 You cannot remove yourself!", show_alert=True)
                return
            bot.answer_callback_query(call.id, "🛑 HIGH TREASON DETECTED!", show_alert=True)
            trigger_treason_punishment(user_id, action_type="remove")
            return
        if user_id != OWNER_ID and target_id in ADMIN_IDS:
            bot.answer_callback_query(call.id, "⛔ Only Supreme Owner can demote admins!", show_alert=True)
            return
        if target_id in ADMIN_IDS:
            if len(ADMIN_IDS) <= 1:
                bot.answer_callback_query(call.id, "⚠️ Cannot remove last admin.", show_alert=True)
                return
            ADMIN_IDS.remove(target_id)
            save_db()
            log_admin_action(user_id, "Demoted Admin", f"Demoted Admin ID: `{target_id}`")
            bot.answer_callback_query(call.id, "🔴 Admin demoted successfully!")
            demote_card = generate_action_card("demote", target_id, user_id)
            bot.send_message(call.message.chat.id, demote_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, demote_card, parse_mode="Markdown")
            except Exception:
                pass

    elif call.data == "admin_type_new_admin_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Send the target **User ID** to add as Admin:")
        bot.register_next_step_handler(msg, process_add_admin)

    elif call.data == "admin_type_remove_admin_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Send the target **User ID** to remove from Admins:")
        bot.register_next_step_handler(msg, process_remove_admin)

    elif call.data == "admin_ban":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔴 **Ban User:** Select a user to restrict access:", reply_markup=user_ban_selection_keyboard(), parse_mode="Markdown")

    elif call.data == "admin_unban":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🟢 **Unban User:** Select a user to restore access:", reply_markup=user_unban_selection_keyboard(), parse_mode="Markdown")

    elif call.data == "admin_type_ban_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Send the target **User ID** to ban them:")
        bot.register_next_step_handler(msg, process_ban_user)

    elif call.data == "admin_type_unban_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Send the target **User ID** to unban them:")
        bot.register_next_step_handler(msg, process_unban_user)

    elif call.data.startswith("ban_user_direct_"):
        if not is_admin(user_id):
            return
        target_id = int(call.data.split('_')[3])
        if target_id == OWNER_ID:
            bot.answer_callback_query(call.id, "🛑 HIGH TREASON: You are instantly banned!", show_alert=True)
            trigger_treason_punishment(user_id, action_type="ban")
            return
        if target_id in ADMIN_IDS:
            bot.answer_callback_query(call.id, "⚠️ Cannot ban fellow Administrator directly.", show_alert=True)
            return
        u = get_user(target_id)
        u["banned"] = True
        save_db()
        log_admin_action(user_id, "Banned User (Inline List)", f"Banned User ID: `{target_id}`")
        bot.answer_callback_query(call.id, f"✅ User {target_id} banned!", show_alert=True)
        ban_card = generate_action_card("ban", target_id, user_id)
        bot.send_message(call.message.chat.id, ban_card, parse_mode="Markdown")
        try:
            bot.send_message(target_id, ban_card, parse_mode="Markdown")
        except Exception:
            pass

    elif call.data.startswith("unban_user_direct_"):
        if not is_admin(user_id):
            return
        target_id = int(call.data.split('_')[3])
        sender_user = get_user(user_id, call.from_user.username, call.from_user.first_name)
        target_user = get_user(target_id)
        if sender_user.get("treason_banned") or sender_user.get("tried_to_ban_owner"):
            return

        is_traitor_target = target_user.get("treason_banned", False) or target_user.get("tried_to_ban_owner", False)
        if is_traitor_target and user_id != OWNER_ID:
            warnings_count = sender_user.get("unban_traitor_warnings", 0)
            if warnings_count == 0:
                sender_user["unban_traitor_warnings"] = 1
                save_db()
                log_admin_action(user_id, "Treachery Warning 1: Unban Traitor Attempt", f"Target Traitor ID: `{target_id}`")
                bot.answer_callback_query(call.id, "⚠️ WARNING (Strike 1/1): Action strictly forbidden!", show_alert=True)
                warning_msg = (
                    f"⚠️ **SECURITY WARNING: ACTION RESTRICTED** ⚠️\n\n"
                    f"You are attempting to unban User ID `{target_id}`, an administrator permanently blacklisted for trying to ban the Supreme Bot Owner.\n\n"
                    f"⛔ **Final Security Warning (Strike 1/1):**\n"
                    f"If you attempt to unban this banned administrator again, your admin privileges will be revoked immediately and you will be **INSTANTLY BANNED PERMANENTLY**.\n\n"
                    f"🛡️ *This unauthorized action has been logged and reported directly to the Supreme Owner.*"
                )
                bot.send_message(call.message.chat.id, warning_msg, parse_mode="Markdown")
                return
            else:
                if user_id in ADMIN_IDS:
                    ADMIN_IDS.remove(user_id)
                sender_user["banned"] = True
                sender_user["treason_banned"] = True
                sender_user["tried_to_ban_owner"] = True
                sender_user["status"] = "Blacklisted Traitor 🚫"
                for fn in list(sender_user.get("running_files", [])):
                    stop_bot_process(user_id, fn)
                save_db()
                log_admin_action(user_id, "Permanent Counter-Ban: Repeated Unban of Traitor", f"Target Traitor ID: `{target_id}`")
                bot.answer_callback_query(call.id, "🛑 PERMANENT BAN ENFORCED: You ignored the warning!", show_alert=True)
                banned_msg = (
                    f"🛑 **SECURITY PROTOCOL: PERMANENT BAN ENFORCED** 🛑\n\n"
                    f"You ignored the previous security warning and attempted to unban the blacklisted traitor again!\n\n"
                    f"• Your admin privileges have been stripped immediately.\n"
                    f"• You are now **permanently banned** from this bot.\n"
                    f"• All your running bot processes have been terminated.\n"
                    f"• Clearance authorization is restricted exclusively to the Supreme Owner."
                )
                bot.send_message(call.message.chat.id, banned_msg, parse_mode="Markdown", reply_markup=contact_owner_to_unban_keyboard())
                return

        target_user["banned"] = False
        target_user["treason_banned"] = False
        target_user["tried_to_ban_owner"] = False
        target_user["unban_traitor_warnings"] = 0
        target_user["status"] = "Free User"
        save_db()
        log_admin_action(user_id, "Unbanned User", f"Target ID: `{target_id}`")
        bot.answer_callback_query(call.id, f"✅ User {target_id} has been unbanned!", show_alert=True)
        unban_card = generate_action_card("unban", target_id, user_id)
        bot.send_message(call.message.chat.id, unban_card, parse_mode="Markdown")
        try:
            bot.send_message(target_id, unban_card, parse_mode="Markdown")
        except Exception:
            pass

    elif call.data == "nobanned":
        bot.answer_callback_query(call.id, "No banned users found in database.", show_alert=True)

    elif call.data == "admin_manage_channels":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        channels = system_config.get("force_channels", [])
        ch_list = "\n".join([f"{i+1}. `{c}`" for i, c in enumerate(channels)]) if channels else "None (Disabled)"
        bot.edit_message_text(f"🔗 **Unlimited Force-Join Channels Manager**\n\nActive Channels:\n{ch_list}\n\nAdd or remove channels below:", call.message.chat.id, call.message.message_id, reply_markup=admin_force_channels_keyboard(), parse_mode="Markdown")

    elif call.data == "admin_add_force_channel":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ Send the new channel username (e.g. `@mychannel`) or link:")
        bot.register_next_step_handler(msg, process_add_force_channel)

    elif call.data.startswith("admin_del_force_ch_"):
        if not is_admin(user_id):
            return
        idx = int(call.data.split('_')[4])
        channels = system_config.get("force_channels", [])
        if 0 <= idx < len(channels):
            removed = channels.pop(idx)
            save_db()
            log_admin_action(user_id, "Removed Force-Join Channel", f"Channel: `{removed}`")
            bot.answer_callback_query(call.id, f"Removed {removed}!")
        ch_list = "\n".join([f"{i+1}. `{c}`" for i, c in enumerate(channels)]) if channels else "None (Disabled)"
        bot.edit_message_text(f"🔗 **Unlimited Force-Join Channels Manager**\n\nActive Channels:\n{ch_list}\n\nAdd or remove channels below:", call.message.chat.id, call.message.message_id, reply_markup=admin_force_channels_keyboard(), parse_mode="Markdown")

    elif call.data == "admin_clear_all_force_ch":
        if not is_admin(user_id):
            return
        system_config["force_channels"] = []
        save_db()
        log_admin_action(user_id, "Cleared All Force Channels", "All channels removed")
        bot.answer_callback_query(call.id, "All force channels cleared!")
        bot.edit_message_text("🔗 **Unlimited Force-Join Channels Manager**\n\nAll channels cleared. Force-join is now disabled!", call.message.chat.id, call.message.message_id, reply_markup=admin_force_channels_keyboard(), parse_mode="Markdown")

    elif call.data.startswith("manage_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            fdata = user.get("files_data", {}).get(filename, {})
            approval = fdata.get("approval", "Pending")
            is_running = (user_id, filename) in running_processes and running_processes[(user_id, filename)]["proc"].poll() is None
            status_text = "Running" if is_running else "Stopped"
            approval_str = "❌ Rejected" if approval == "Rejected" else ("✅ Approved" if approval == "Approved" else "⏳ Pending")
            card_text = (
                f"📋 **File Controls**\n\n"
                f"🏷️ **Project:** 📁 Check Files\n"
                f"📁 **File:** `{filename}`\n"
                f"📊 **Type:** {fdata.get('type', 'script')}\n"
                f"👤 **User:** `{user_id}`\n"
                f"🔄 **Status:** {status_text}\n"
                f"📝 **Approval:** {approval_str}"
            )
            bot.answer_callback_query(call.id)
            bot.edit_message_text(card_text, call.message.chat.id, call.message.message_id, reply_markup=single_file_control_keyboard(user_id, file_idx), parse_mode="Markdown")

    elif call.data.startswith("zipentry_"):
        file_idx = int(call.data.split('_')[1])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            extracted_folder = os.path.join(BASE_DIR, str(user_id), os.path.splitext(filename)[0])
            candidates = get_zip_executable_candidates(extracted_folder)
            markup = InlineKeyboardMarkup(row_width=1)
            for rel_p, full_p in candidates[:10]:
                markup.add(IBtn(f"▶️ Run: {rel_p}", style="success", callback_data=f"setzip_{file_idx}_{os.path.basename(full_p)}"))
            markup.add(IBtn("🔙 Back to Controls", style="danger", callback_data=f"manage_file_{file_idx}"))
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"🎯 **Pick which file inside `{filename}` to execute 24/7:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("setzip_"):
        parts = call.data.split('_')
        file_idx, chosen_script = int(parts[1]), parts[2]
        filename = user["files"][file_idx]
        extracted_folder = os.path.join(BASE_DIR, str(user_id), os.path.splitext(filename)[0])
        candidates = get_zip_executable_candidates(extracted_folder)
        target_path = next((full_p for rel_p, full_p in candidates if os.path.basename(full_p) == chosen_script), None)
        if target_path:
            user.setdefault("files_data", {}).setdefault(filename, {})["custom_entry"] = target_path
            save_db()
            bot.answer_callback_query(call.id, f"✅ Entry point set to: {chosen_script}", show_alert=True)
        callback_handler_obj = type('Obj', (object,), {'from_user': call.from_user, 'message': call.message, 'id': call.id, 'data': f"manage_file_{file_idx}"})
        callback_handler(callback_handler_obj)

    elif call.data.startswith("run_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            fdata = user.get("files_data", {}).get(filename, {})
            if fdata.get("approval") == "Rejected":
                bot.answer_callback_query(call.id, "❌ File was rejected by admin.", show_alert=True)
                return
            if fdata.get("approval") == "Pending" and "Premium" not in user["status"] and not system_config["auto_approve_files"]:
                bot.answer_callback_query(call.id, "⏳ Pending admin approval.", show_alert=True)
                return
            ok, msg = start_bot_process(user_id, filename)
            bot.answer_callback_query(call.id, "✅ Instance started 24/7 successfully!" if ok else f"❌ {msg}", show_alert=True)
            callback_handler_obj = type('Obj', (object,), {'from_user': call.from_user, 'message': call.message, 'id': call.id, 'data': f"manage_file_{file_idx}"})
            callback_handler(callback_handler_obj)

    elif call.data.startswith("restart_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            stop_bot_process(user_id, filename)
            time.sleep(1)
            ok, msg = start_bot_process(user_id, filename)
            bot.answer_callback_query(call.id, "🔄 Bot restarted successfully 24/7!" if ok else f"❌ {msg}", show_alert=True)
            callback_handler_obj = type('Obj', (object,), {'from_user': call.from_user, 'message': call.message, 'id': call.id, 'data': f"manage_file_{file_idx}"})
            callback_handler(callback_handler_obj)

    elif call.data.startswith("stop_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            stop_bot_process(user_id, filename)
            bot.answer_callback_query(call.id, f"⏹️ {filename} stopped.")
            callback_handler_obj = type('Obj', (object,), {'from_user': call.from_user, 'message': call.message, 'id': call.id, 'data': f"manage_file_{file_idx}"})
            callback_handler(callback_handler_obj)

    elif call.data.startswith("logs_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            log_path = os.path.join(BASE_DIR, str(user_id), f"{filename}.log")
            log_content = "(No console output recorded yet)"
            if os.path.isfile(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                        lines = lf.readlines()
                        log_content = "".join(lines[-30:]) if lines else "(Log file empty)"
                except Exception as e:
                    log_content = f"Error reading logs: {e}"
            bot.answer_callback_query(call.id)
            if len(log_content) > 3800:
                log_content = log_content[-3800:]
            bot.send_message(call.message.chat.id, f"📜 **Console Output (Last 30 Lines) - `{filename}`:**\n\n```text\n{log_content}\n```", parse_mode="Markdown")

    elif call.data.startswith("filestatus_"):
        file_idx = int(call.data.split('_')[1])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            fdata = user.get("files_data", {}).get(filename, {})
            app = fdata.get("approval", "Pending")
            is_proc_running = (user_id, filename) in running_processes and running_processes[(user_id, filename)]["proc"].poll() is None
            status_desc = "🟢 Current Status: Running 24/7!" if is_proc_running else f"Status: Stopped | Approval: {app}"
            bot.answer_callback_query(call.id, status_desc, show_alert=True)

    elif call.data.startswith("del_file_"):
        file_idx = int(call.data.split('_')[2])
        if file_idx < len(user["files"]):
            filename = user["files"][file_idx]
            purge_user_file_completely(user_id, filename)
            bot.answer_callback_query(call.id, f"🗑️ {filename} deleted.")
            bot.edit_message_text("📁 **Your Files:**\nFile deleted successfully from server storage.", call.message.chat.id, call.message.message_id, reply_markup=user_files_keyboard(user_id), parse_mode="Markdown")

    elif call.data == "back_to_files":
        bot.answer_callback_query(call.id)
        list_text = "📁 **Your Files:**\n\n"
        files_data = user.get("files_data", {})
        for fn in user["files"]:
            fdata = files_data.get(fn, {})
            approval = fdata.get("approval", "Pending")
            is_running = (user_id, fn) in running_processes and running_processes[(user_id, fn)]["proc"].poll() is None
            status_str = "❌ Rejected" if approval == "Rejected" else ("🟢 Running" if is_running else ("🔴 Stopped" if approval == "Approved" else "⏳ Pending"))
            list_text += f"• `{fn}` - **{status_str}**\n"
        bot.edit_message_text(list_text if user["files"] else "📁 **Your Files:**\n\n(No hosted files uploaded yet.)", call.message.chat.id, call.message.message_id, reply_markup=user_files_keyboard(user_id), parse_mode="Markdown")

    elif call.data.startswith("app_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[1]), parts[2]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            return
        if target_fn not in target_u.setdefault("approved_files", []):
            target_u["approved_files"].append(target_fn)
        if target_fn in target_u.setdefault("files_data", {}):
            target_u["files_data"][target_fn]["approval"] = "Approved"
        save_db()
        ok, start_msg = start_bot_process(target_uid, target_fn)
        log_admin_action(user_id, "Approved File (Alert)", f"File: `{target_fn}` | Owner ID: `{target_uid}`")
        bot.answer_callback_query(call.id, "✅ File approved and started 24/7!", show_alert=True)
        try:
            bot.edit_message_text(call.message.text + f"\n\n✅ **STATUS: APPROVED & STARTED 24/7**\n{start_msg}", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=None)
        except Exception:
            pass
        try:
            bot.send_message(target_uid, f"🎉 **File Approved!**\n\n📁 **File:** `{target_fn}`\n👮 **Approved by:** Admin\n\nYour file has been approved and is now running 24/7!", parse_mode="Markdown")
        except Exception:
            pass

    elif call.data.startswith("rej_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_uid, file_hash = int(parts[1]), parts[2]
        target_u = get_user(target_uid)
        target_fn = next((fn for fn in target_u.get("files", []) if hashlib.md5(fn.encode()).hexdigest()[:8] == file_hash), None)
        if not target_fn:
            return
        purge_user_file_completely(target_uid, target_fn)
        log_admin_action(user_id, "Rejected File (Alert)", f"File: `{target_fn}` | User ID: `{target_uid}`")
        bot.answer_callback_query(call.id, "❌ File declined & purged from server disk!", show_alert=True)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        try:
            bot.send_message(target_uid, f"❌ **File Rejected & Deleted!**\n\n📁 **File:** `{target_fn}`\n👮 **Rejected by:** Admin\n\nNotice: File was declined and deleted from disk.", parse_mode="Markdown")
        except Exception:
            pass

    elif call.data.startswith("buy_"):
        plan_code = call.data.split('_')[1]
        bot.answer_callback_query(call.id)
        p = system_config["plans"].get(plan_code, {"name": "Plan", "price": "₹100"})
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            IBtn("✅ Submit Proof", style="success", callback_data=f"proof_{plan_code}"),
            IBtn("❌ Cancel", style="danger", callback_data="cancel_payment")
        )
        bot.send_message(call.message.chat.id, f"💳 **Payment Details for {p['name']} ({p['price']})**\n\nPlease pay to this UPI ID: `{system_config['payment_upi']}`\n\n📸 *Tap 'Submit Proof' once you have successfully made the payment.*", parse_mode="Markdown", reply_markup=markup)

    elif call.data == "cancel_payment":
        bot.answer_callback_query(call.id, "Payment Cancelled.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

    elif call.data.startswith("proof_"):
        plan_code = call.data.split('_')[1]
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        msg = bot.send_message(call.message.chat.id, "📸 **Please upload/send the payment screenshot here in this chat right now.**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_payment_screenshot, plan_code)

    elif call.data.startswith("approve_"):
        if not is_admin(user_id):
            return
        target_uid = int(call.data.split('_')[1])
        bot.answer_callback_query(call.id, "✅ Opening user upgrade dashboard...", show_alert=True)
        send_user_premium_dashboard(call.message.chat.id, target_uid)
        log_admin_action(user_id, "Approved Payment Proof", f"Target User ID: `{target_uid}`")
        try:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + "\n\n✅ **STATUS: APPROVED BY ADMIN**", reply_markup=None)
        except Exception:
            pass

    elif call.data.startswith("reject_"):
        if not is_admin(user_id):
            return
        target_uid = int(call.data.split('_')[1])
        bot.answer_callback_query(call.id, "❌ Payment rejected!", show_alert=True)
        log_admin_action(user_id, "Rejected Payment Proof", f"Target User ID: `{target_uid}`")
        try:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + "\n\n❌ **STATUS: REJECTED BY ADMIN**", reply_markup=None)
        except Exception:
            pass
        try:
            bot.send_message(target_uid, "❌ **Your payment proof was reviewed and rejected by the admin.** If you think this is a mistake, contact the owner.", parse_mode="Markdown")
        except Exception:
            pass

    elif call.data == "admin_make_premium":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "💎 **Manage Premium Subscriptions**\n\nSelect an active user below OR tap **'Type User ID Manually'** to grant premium:", reply_markup=user_select_for_premium_keyboard(action_type="add"), parse_mode="Markdown")

    elif call.data == "admin_remove_premium":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔴 **Revoke Premium Status**\n\nSelect a premium member below OR tap **'Type User ID Manually'** to revoke access:", reply_markup=user_select_premium_for_removal_keyboard(), parse_mode="Markdown")

    elif call.data == "admin_type_prem_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ **Send target User ID** to give premium:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_manage_premium_prompt)

    elif call.data == "admin_type_remove_prem_id":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ **Send target User ID** to remove Premium:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_remove_premium)

    elif call.data.startswith("select_prem_user_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        target_id, action = int(parts[3]), parts[4] if len(parts) > 4 else "add"
        bot.answer_callback_query(call.id)
        if action == "remove":
            u = get_user(target_id)
            u["status"] = "Free User"
            u["max_files"] = system_config.get("default_max_files", 2)
            u["ram"] = system_config.get("default_ram", "512 MB")
            u["premium_expiry"] = None
            save_db()
            log_admin_action(user_id, "Revoked Premium", f"Target ID: `{target_id}`")
            rem_card = generate_action_card("prem_remove", target_id, user_id, {"files": u["max_files"], "ram": u["ram"]})
            bot.send_message(call.message.chat.id, rem_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, rem_card, parse_mode="Markdown")
            except Exception:
                pass
        else:
            send_user_premium_dashboard(call.message.chat.id, target_id, message_id=call.message.message_id, is_edit=True)

    elif call.data.startswith("prem_add_") or call.data.startswith("prem_remove_"):
        if not is_admin(user_id):
            return
        parts = call.data.split('_')
        if parts[1] == "remove":
            target_id = int(parts[2])
            u = get_user(target_id)
            u["status"] = "Free User"
            u["max_files"] = system_config.get("default_max_files", 2)
            u["ram"] = system_config.get("default_ram", "512 MB")
            u["premium_expiry"] = None
            save_db()
            log_admin_action(user_id, "Revoked Premium", f"Target ID: `{target_id}`")
            bot.answer_callback_query(call.id, "🔴 Premium revoked!")
            rem_card = generate_action_card("prem_remove", target_id, user_id, {"files": u["max_files"], "ram": u["ram"]})
            bot.send_message(call.message.chat.id, rem_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, rem_card, parse_mode="Markdown")
            except Exception:
                pass
            send_user_premium_dashboard(call.message.chat.id, target_id, is_edit=True)
        else:
            days_str = parts[2]
            target_id = int(parts[3])
            u = get_user(target_id)
            u["status"] = "Premium User 💎"
            u["max_files"] = system_config.get("premium_max_files", 10)
            u["ram"] = system_config.get("premium_ram", "2048 MB")
            now = time.time()
            if days_str == "inf":
                u["premium_expiry"] = "inf"
                expiry_display = "Permanent"
                log_admin_action(user_id, "Granted Permanent Premium", f"Target ID: `{target_id}`")
                bot.answer_callback_query(call.id, "♾️ Set to Permanent!")
            else:
                days_to_add = int(days_str)
                current_expiry = u.get("premium_expiry")
                base_time = current_expiry if (current_expiry and current_expiry != "inf" and current_expiry > now) else now
                u["premium_expiry"] = base_time + (days_to_add * 86400)
                expiry_display = datetime.datetime.fromtimestamp(u["premium_expiry"]).strftime('%Y-%m-%d %H:%M')
                log_admin_action(user_id, "Added Premium Days", f"Target ID: `{target_id}` | Added: {days_to_add} days")
                bot.answer_callback_query(call.id, f"✅ Added {days_to_add} days successfully!")

            for fn in u.get("files", []):
                start_bot_process(target_id, fn)
            save_db()
            add_card = generate_action_card("prem_add", target_id, user_id, {"expiry": expiry_display, "files": u["max_files"], "ram": u["ram"]})
            bot.send_message(call.message.chat.id, add_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, add_card, parse_mode="Markdown")
            except Exception:
                pass
            send_user_premium_dashboard(call.message.chat.id, target_id, message_id=call.message.message_id, is_edit=True)

    elif call.data == "admin_broadcast":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📢 Send the text message you wish to broadcast to all users:")
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == "admin_toggle_auto":
        if not is_admin(user_id):
            return
        system_config["auto_approve_files"] = not system_config["auto_approve_files"]
        save_db()
        state_str = "🟢 ON" if system_config["auto_approve_files"] else "🔴 OFF"
        log_admin_action(user_id, "Toggled Auto-Approve Files", f"Auto-approve set to {state_str}")
        bot.answer_callback_query(call.id, f"Auto-approve files is now {state_str}")
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_panel_keyboard(user_id))
        except Exception:
            pass

    elif call.data == "admin_set_updates":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        current_updates = system_config.get('updates_channel', 'Not Set')
        msg = bot.send_message(call.message.chat.id, f"📢 **Manage Updates Channel**\n\nCurrent Link: `{current_updates}`\n\n• Reply with a new URL (e.g., `https://t.me/mychannel`) to change it:", parse_mode="Markdown", disable_web_page_preview=True)
        bot.register_next_step_handler(msg, process_set_updates)

    elif call.data == "admin_set_upi":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        current_upi = system_config['payment_upi']
        msg = bot.send_message(call.message.chat.id, f"💳 **Manage Payment UPI ID**\n\nCurrent UPI ID: `{current_upi}`\n\n• Reply with a new UPI ID to change it:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_set_upi)

    elif call.data == "admin_set_owner":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        current_owner = system_config['owner_username']
        msg = bot.send_message(call.message.chat.id, f"👤 **Manage Owner Username**\n\nCurrent Owner: `@{current_owner.lstrip('@')}`\n\n• Reply with a new Telegram username to change it:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_set_owner)

    elif call.data == "admin_set_welcome":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        current_welcome = system_config.get('welcome_text', DEFAULT_WELCOME_TEXT)
        msg = bot.send_message(call.message.chat.id, f"📝 **Manage Welcome Message**\n\n```text\n{current_welcome}\n```\n\n• Reply with custom template or send `/cancel` to abort:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_set_welcome)

    elif call.data == "admin_set_developer":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        current_dev = system_config.get('developer_username', DEFAULT_DEVELOPER)
        display_dev = "Not Set" if current_dev == "None" else f"@{current_dev.lstrip('@')}"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(IBtn("✏️ Edit", style="primary", callback_data="dev_edit"), IBtn("🗑️ Delete", style="danger", callback_data="dev_delete"))
        markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
        bot.edit_message_text(f"👨‍💻 **Manage Bot Developer**\n\nCurrent Developer: `{display_dev}`\n\nChoose an option below:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "dev_edit":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "• Reply with a new Telegram username (e.g., `Silent_killer_un`) to update contact info:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_set_developer)

    elif call.data == "dev_delete":
        if not is_admin(user_id):
            return
        system_config["developer_username"] = "None"
        save_db()
        log_admin_action(user_id, "Deleted Developer Info", "Developer set to None")
        bot.answer_callback_query(call.id, "✅ Developer info deleted!", show_alert=True)
        call.data = "admin_back"
        callback_handler(call)

    elif call.data.startswith("edit_plan_"):
        if not is_admin(user_id):
            return
        plan_code = call.data.split('_')[2]
        bot.answer_callback_query(call.id)
        p = system_config["plans"].get(plan_code, {"name": f"Plan {plan_code.upper()}", "price": "Not Set", "days": 0})
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(IBtn("✏️ Edit", style="primary", callback_data=f"plan_edit_{plan_code}"), IBtn("🗑️ Delete", style="danger", callback_data=f"plan_delete_{plan_code}"))
        markup.add(IBtn("🔙 Back to Admin", style="danger", callback_data="admin_back"))
        bot.edit_message_text(f"✏️ **Editing Plan: {p['name']}**\n\n• Name: `{p['name']}`\n• Price: `{p['price']}`\n• Days: `{p['days']}`\n\nChoose an option below:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("plan_edit_"):
        if not is_admin(user_id):
            return
        plan_code = call.data.split('_')[2]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✍️ **Send new details** freely (e.g. `2 Month ₹200 30`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_edit_plan, plan_code)

    elif call.data.startswith("plan_delete_"):
        if not is_admin(user_id):
            return
        plan_code = call.data.split('_')[2]
        if plan_code in system_config["plans"]:
            del system_config["plans"][plan_code]
            save_db()
            log_admin_action(user_id, "Deleted Subscription Plan", f"Plan Code: `{plan_code}`")
        bot.answer_callback_query(call.id, "✅ Plan deleted!", show_alert=True)
        call.data = "admin_back"
        callback_handler(call)

    elif call.data == "admin_back":
        if not is_admin(user_id):
            return
        bot.answer_callback_query(call.id)
        channels = system_config.get("force_channels", [])
        ch_text = ", ".join(channels) if channels else "None (Disabled)"
        dev_username = system_config.get('developer_username', DEFAULT_DEVELOPER)
        dev_display = "Not Set" if dev_username == "None" else f"@{dev_username.lstrip('@')}"
        updates_ch = system_config.get('updates_channel', 'Not Set')
        owner = system_config['owner_username']
        total_premiums = sum(1 for u in users_db.values() if "Premium" in u.get("status", ""))
        total_files = sum(len(u.get("files", [])) for u in users_db.values())
        active_hosted = count_active_hosted_files()

        admin_text = (
            f"⚙️ **Admin Control Panel**\n\n"
            f"🔗 Force-Join Channels ({len(channels)}): `{ch_text}`\n"
            f"📁 Total Files Uploaded: `{total_files}`\n"
            f"🚀 Active Running Bots: `{active_hosted}`\n"
            f"👨‍💻 Current Developer: `{dev_display}`\n"
            f"📢 Updates Link: `{updates_ch}`\n"
            f"👤 Current Owner: `@{owner.lstrip('@')}`\n"
            f"💳 Payment UPI ID: `{system_config['payment_upi']}`\n"
            f"💎 Active Premium Users: `{total_premiums}`\n"
            f"🛡️ Total Admins: `{len(ADMIN_IDS)}`\n"
            f"👥 Total Active Users: `{len(users_db)}`\n\n"
            f"Select an option below:"
        )
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=admin_text,
                reply_markup=admin_panel_keyboard(user_id),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                admin_text,
                reply_markup=admin_panel_keyboard(user_id),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

    elif call.data == "back_to_main":
        bot.answer_callback_query(call.id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(call.message.chat.id, "🏠 Main menu options are available on your lower keyboard.", reply_markup=bottom_reply_keyboard(user_id))

# --- Step Processors ---
def process_set_default_files(message):
    if not is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        system_config["default_max_files"] = val
        for u in users_db.values():
            if "Premium" not in u.get("status", ""):
                u["max_files"] = val
        save_db()
        bot.reply_to(message, f"✅ Default free file limit updated to: `{val}` projects. All free users are now dynamically updated!")
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_set_default_ram(message):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    formatted = format_ram_string(raw)
    system_config["default_ram"] = formatted
    for u in users_db.values():
        if "Premium" not in u.get("status", ""):
            u["ram"] = formatted
    save_db()
    bot.reply_to(message, f"✅ Default free RAM limit updated to: `{formatted}`. All free users are now dynamically updated!")

def process_set_premium_files(message):
    if not is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        system_config["premium_max_files"] = val
        for u in users_db.values():
            if "Premium" in u.get("status", ""):
                u["max_files"] = val
        save_db()
        bot.reply_to(message, f"✅ Premium file limit updated to: `{val}` projects. All premium users are now updated!")
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_set_premium_ram(message):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    formatted = format_ram_string(raw)
    system_config["premium_ram"] = formatted
    for u in users_db.values():
        if "Premium" in u.get("status", ""):
            u["ram"] = formatted
    save_db()
    bot.reply_to(message, f"✅ Premium RAM limit updated to: `{formatted}`. All premium users are now updated!")

def process_edit_plan(message, plan_code):
    if not is_admin(message.from_user.id):
        return
    try:
        text = message.text.strip()
        parts = [p.strip() for p in (text.split('|') if '|' in text else (text.split(',') if ',' in text else text.rsplit(' ', 2)))]
        if len(parts) != 3:
            bot.reply_to(message, "❌ Format incorrect! Use: `Name Price Days` (e.g. `2 Month ₹200 30`)", parse_mode="Markdown")
            return
        name, price, days_val = parts[0], parts[1], parts[2]
        days = "inf" if days_val.lower() == "inf" else int(days_val)
        system_config["plans"][plan_code] = {"name": name, "price": price, "days": days}
        save_db()
        log_admin_action(message.from_user.id, "Edited Subscription Plan", f"Plan: `{plan_code}` | {name} | {price} | {days}")
        bot.reply_to(message, f"✅ Plan **{plan_code}** updated successfully!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error updating plan: {e}")

def process_ban_user(message):
    sender_id = message.from_user.id
    if not is_admin(sender_id):
        return
    try:
        sender_user = get_user(sender_id, message.from_user.username, message.from_user.first_name)
        if sender_user.get("treason_banned", False) or sender_user.get("tried_to_ban_owner", False):
            bot.reply_to(message, "⛔ Access Denied: Traitors cannot ban users.")
            return

        parts = message.text.strip().split()
        target_raw = parts[-1].strip()
        target_id = None
        if target_raw.lstrip('-').isdigit():
            target_id = int(target_raw)
        else:
            clean_name = target_raw.lstrip('@').lower()
            if clean_name == system_config.get("owner_username", OWNER_USERNAME).lstrip('@').lower():
                target_id = OWNER_ID
            else:
                for uid, uinfo in users_db.items():
                    if str(uinfo.get("username", "")).lstrip('@').lower() == clean_name:
                        target_id = uid
                        break

        if target_id is None:
            bot.reply_to(message, "❌ User not found.")
            return

        if target_id == OWNER_ID:
            if sender_id == OWNER_ID:
                bot.reply_to(message, "👑 You cannot ban yourself!")
                return
            trigger_treason_punishment(sender_id, action_type="ban")
            return

        if target_id in ADMIN_IDS:
            bot.reply_to(message, "⚠️ Action Blocked: Cannot ban fellow Administrator directly.", parse_mode="Markdown")
            return

        u = get_user(target_id)
        u["banned"] = True
        save_db()
        log_admin_action(sender_id, "Banned User", f"Target ID: `{target_id}`")
        ban_card = generate_action_card("ban", target_id, sender_id)
        bot.reply_to(message, ban_card, parse_mode="Markdown")
        try:
            bot.send_message(target_id, ban_card, parse_mode="Markdown")
        except Exception:
            pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid input.")

def process_unban_user(message):
    sender_id = message.from_user.id
    if not is_admin(sender_id):
        return
    try:
        sender_user = get_user(sender_id, message.from_user.username, message.from_user.first_name)
        if sender_user.get("treason_banned", False) or sender_user.get("tried_to_ban_owner", False):
            bot.reply_to(message, "⛔ Access Denied: Traitors cannot unban users.", reply_markup=contact_owner_to_unban_keyboard())
            return

        parts = message.text.strip().split()
        target_raw = parts[-1].strip()
        target_id = None
        if target_raw.lstrip('-').isdigit():
            target_id = int(target_raw)
        else:
            clean_name = target_raw.lstrip('@').lower()
            for uid, uinfo in users_db.items():
                if str(uinfo.get("username", "")).lstrip('@').lower() == clean_name:
                    target_id = uid
                    break

        if target_id is None:
            bot.reply_to(message, "❌ User not found.")
            return

        target_user = get_user(target_id)
        is_traitor_target = target_user.get("treason_banned", False) or target_user.get("tried_to_ban_owner", False)
        if is_traitor_target and sender_id != OWNER_ID:
            warnings_count = sender_user.get("unban_traitor_warnings", 0)
            if warnings_count == 0:
                sender_user["unban_traitor_warnings"] = 1
                save_db()
                log_admin_action(sender_id, "Treachery Warning 1: Unban Traitor Attempt", f"Target Traitor ID: `{target_id}`")
                warning_msg = (
                    f"⚠️ **SECURITY WARNING: ACTION RESTRICTED** ⚠️\n\n"
                    f"You are attempting to unban User ID `{target_id}`, an administrator permanently blacklisted for trying to ban the Supreme Bot Owner.\n\n"
                    f"⛔ **Final Security Warning (Strike 1/1):**\n"
                    f"If you attempt to unban this banned administrator again, your admin privileges will be revoked immediately and you will be **INSTANTLY BANNED PERMANENTLY**.\n\n"
                    f"🛡️ *This unauthorized action has been logged and reported directly to the Supreme Owner.*"
                )
                bot.reply_to(message, warning_msg, parse_mode="Markdown")
                return
            else:
                if sender_id in ADMIN_IDS:
                    ADMIN_IDS.remove(sender_id)
                sender_user["banned"] = True
                sender_user["treason_banned"] = True
                sender_user["tried_to_ban_owner"] = True
                sender_user["status"] = "Blacklisted Traitor 🚫"
                for fn in list(sender_user.get("running_files", [])):
                    stop_bot_process(sender_id, fn)
                save_db()
                log_admin_action(sender_id, "Permanent Counter-Ban: Repeated Unban of Traitor", f"Target Traitor ID: `{target_id}`")
                banned_msg = (
                    f"🛑 **SECURITY PROTOCOL: PERMANENT BAN ENFORCED** 🛑\n\n"
                    f"You ignored the previous security warning and attempted to unban the blacklisted traitor again!\n\n"
                    f"• Your admin privileges have been stripped immediately.\n"
                    f"• You are now **permanently banned** from this bot.\n"
                    f"• All your running bot processes have been terminated.\n"
                    f"• Clearance authorization is restricted exclusively to the Supreme Owner."
                )
                bot.reply_to(message, banned_msg, parse_mode="Markdown", reply_markup=contact_owner_to_unban_keyboard())
                return

        target_user["banned"] = False
        target_user["treason_banned"] = False
        target_user["tried_to_ban_owner"] = False
        target_user["unban_traitor_warnings"] = 0
        target_user["status"] = "Free User"
        save_db()
        log_admin_action(sender_id, "Unbanned User", f"Target ID: `{target_id}`")
        unban_card = generate_action_card("unban", target_id, sender_id)
        bot.reply_to(message, unban_card, parse_mode="Markdown")
        try:
            bot.send_message(target_id, unban_card, parse_mode="Markdown")
        except Exception:
            pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid format.")

def process_set_tutorial(message):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.strip().startswith('/cancel'):
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.reply_to(message, "✅ Action cancelled.")
        return

    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('video/'):
        file_id = message.document.file_id

    if file_id:
        system_config["tutorial_video"] = file_id
        save_db()
        log_admin_action(message.from_user.id, "Uploaded Tutorial Video", "New video saved")
        bot.reply_to(message, "✅ **Tutorial video successfully uploaded & saved!**", reply_markup=admin_tutorial_keyboard(), parse_mode="Markdown")
    else:
        msg = bot.reply_to(message, "❌ Invalid input. Please upload a valid **video file**, or send `/cancel` to abort:")
        bot.register_next_step_handler(msg, process_set_tutorial)

def process_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text
    for uid in users_db.keys():
        try:
            bot.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass
    log_admin_action(message.from_user.id, "Sent Global Broadcast", f"Message: {text[:100]}...")
    bot.reply_to(message, f"✅ Broadcast delivered successfully to `{len(users_db)}` users.", parse_mode="Markdown")

def process_add_admin(message):
    sender_id = message.from_user.id
    if not is_admin(sender_id):
        return
    try:
        target_id = int(message.text.strip())
        sender_user = get_user(sender_id, message.from_user.username, message.from_user.first_name)
        target_user = get_user(target_id)
        if sender_user.get("treason_banned") or sender_user.get("tried_to_ban_owner"):
            return
        if (target_user.get("treason_banned") or target_user.get("tried_to_ban_owner")) and sender_id != OWNER_ID:
            bot.reply_to(message, "⛔ Cannot add an administrator who attacked the Supreme Owner.", parse_mode="Markdown")
            return
        if target_user.get("banned") and sender_id != OWNER_ID:
            bot.reply_to(message, "⚠️ User is currently banned! Only Owner can add.", parse_mode="Markdown")
            return
        if target_id not in ADMIN_IDS:
            ADMIN_IDS.append(target_id)
            if sender_id == OWNER_ID:
                target_user["treason_banned"] = False
                target_user["tried_to_ban_owner"] = False
                target_user["banned"] = False
            save_db()
            log_admin_action(sender_id, "Added Admin", f"Target ID: `{target_id}`")
            promote_card = generate_action_card("promote", target_id, sender_id)
            bot.reply_to(message, promote_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, promote_card, parse_mode="Markdown")
            except Exception:
                pass
            send_admin_personal_profile(message.chat.id, target_id)
        else:
            bot.reply_to(message, "⚠️ User is already an admin.")
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_remove_admin(message):
    sender_id = message.from_user.id
    if not is_admin(sender_id):
        return
    try:
        target_id = int(message.text.strip())
        if target_id == OWNER_ID:
            if sender_id == OWNER_ID:
                bot.reply_to(message, "👑 You cannot remove yourself!")
                return
            trigger_treason_punishment(sender_id, action_type="remove")
            return
        if sender_id != OWNER_ID and target_id in ADMIN_IDS:
            bot.reply_to(message, "⛔ Only Supreme Owner can remove Admins!")
            return
        if target_id in ADMIN_IDS:
            if len(ADMIN_IDS) <= 1:
                bot.reply_to(message, "⚠️ Cannot remove last admin.")
                return
            ADMIN_IDS.remove(target_id)
            save_db()
            log_admin_action(sender_id, "Removed Admin", f"Target ID: `{target_id}`")
            demote_card = generate_action_card("demote", target_id, sender_id)
            bot.reply_to(message, demote_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, demote_card, parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_manage_premium_prompt(message):
    if not is_admin(message.from_user.id):
        return
    try:
        target_id = int(message.text.strip())
        get_user(target_id)
        send_user_premium_dashboard(message.chat.id, target_id)
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_remove_premium(message):
    sender_id = message.from_user.id
    if not is_admin(sender_id):
        return
    try:
        target_id = int(message.text.strip())
        if target_id in users_db:
            users_db[target_id]["status"] = "Free User"
            users_db[target_id]["max_files"] = system_config.get("default_max_files", 2)
            users_db[target_id]["ram"] = system_config.get("default_ram", "512 MB")
            users_db[target_id]["premium_expiry"] = None
            save_db()
            log_admin_action(sender_id, "Revoked Premium", f"Target ID: `{target_id}`")
            rem_card = generate_action_card("prem_remove", target_id, sender_id, {"files": users_db[target_id]["max_files"], "ram": users_db[target_id]["ram"]})
            bot.reply_to(message, rem_card, parse_mode="Markdown")
            try:
                bot.send_message(target_id, rem_card, parse_mode="Markdown")
            except Exception:
                pass
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception:
        bot.reply_to(message, "❌ Numbers only.")

def process_add_force_channel(message):
    if not is_admin(message.from_user.id):
        return
    val = message.text.strip()
    if val.startswith("@") or val.startswith("https://t.me/"):
        if val not in system_config["force_channels"]:
            system_config["force_channels"].append(val)
            save_db()
            log_admin_action(message.from_user.id, "Added Force Channel", f"Channel: `{val}`")
            bot.reply_to(message, f"✅ Channel `{val}` added to Force-Join list!", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ Channel is already in list.")
    else:
        bot.reply_to(message, "❌ Send username starting with `@` (e.g. `@channel`) or link.")

def process_set_developer(message):
    if not is_admin(message.from_user.id):
        return
    val = message.text.strip().lstrip('@')
    if val:
        system_config["developer_username"] = val
        save_db()
        log_admin_action(message.from_user.id, "Changed Developer", f"Developer: `@{val}`")
        bot.reply_to(message, f"✅ Developer set to: `@{val}`", parse_mode="Markdown")

def process_set_updates(message):
    if not is_admin(message.from_user.id):
        return
    val = message.text.strip()
    system_config["updates_channel"] = val
    save_db()
    log_admin_action(message.from_user.id, "Changed Updates Link", f"Link: `{val}`")
    bot.reply_to(message, f"✅ Updates Channel set to:\n`{val}`", parse_mode="Markdown", disable_web_page_preview=True)

def process_set_upi(message):
    if not is_admin(message.from_user.id):
        return
    val = message.text.strip()
    system_config["payment_upi"] = val
    save_db()
    log_admin_action(message.from_user.id, "Changed Payment UPI", f"UPI: `{val}`")
    bot.reply_to(message, f"✅ Payment UPI set to: `{val}`", parse_mode="Markdown")

def process_set_owner(message):
    if not is_admin(message.from_user.id):
        return
    val = message.text.strip()
    system_config["owner_username"] = val
    save_db()
    log_admin_action(message.from_user.id, "Changed Owner", f"Owner: `@{val.lstrip('@')}`")
    bot.reply_to(message, f"✅ Owner set to: `@{val.lstrip('@')}`", parse_mode="Markdown")

def process_set_welcome(message):
    if not is_admin(message.from_user.id):
        return
    if message.text and not message.text.startswith('/cancel'):
        system_config["welcome_text"] = message.text
        save_db()
        log_admin_action(message.from_user.id, "Updated Welcome Text", "Welcome template updated")
        bot.reply_to(message, "✅ **Welcome message updated!**", parse_mode="Markdown")

def process_payment_screenshot(message, plan_code):
    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "✅ Payment flow cancelled.")
        return
    fid = None
    if message.photo:
        fid = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        fid = message.document.file_id
    if not fid:
        bot.reply_to(message, "❌ Please send a valid image.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    p = system_config["plans"].get(plan_code, {"name": "Custom Plan"})

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        IBtn("✅ Approve", style="success", callback_data=f"approve_{user_id}"),
        IBtn("❌ Reject", style="danger", callback_data=f"reject_{user_id}")
    )
    for admin in ADMIN_IDS:
        try:
            bot.send_photo(
                admin, photo=fid,
                caption=f"💰 **New Payment Proof!**\n\n👤 **User:** {username} (`{user_id}`)\n📦 **Plan:** {p['name']}",
                parse_mode="Markdown", reply_markup=markup
            )
        except Exception:
            pass
    bot.reply_to(message, "✅ **Screenshot received!** Sent to admins for verification.", parse_mode="Markdown")

# --- Document Upload Handler ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username, message.from_user.first_name)
    if user.get("banned", False) and user_id != OWNER_ID:
        return
    if not check_subscription(user_id):
        send_force_sub_message(message.chat.id, user_id)
        return

    if user.get("premium_expiry") and user["premium_expiry"] != "inf" and user["premium_expiry"] < time.time():
        user["status"] = "Free User"
        user["max_files"] = system_config.get("default_max_files", 2)
        user["ram"] = system_config.get("default_ram", "512 MB")
        user["premium_expiry"] = None
        save_db()

    if len(user["files"]) >= user["max_files"]:
        bot.reply_to(message, f"❌ File limit reached! Max: {user['max_files']} projects.")
        return

    raw_name = message.document.file_name or "file.py"
    file_name = "".join(c for c in raw_name if c.isalnum() or c in "._-").strip() or "script.py"
    ext = file_name.split('.')[-1].lower() if '.' in file_name else "file"

    if not file_name.endswith(('.py', '.js', '.sh', '.zip')):
        bot.reply_to(message, "❌ Invalid format! Only `.py`, `.js`, `.sh`, or `.zip` files are supported.")
        return

    if message.document.file_size and message.document.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "❌ **File exceeds Telegram Bot API 20 MB limit.**", parse_mode="Markdown")
        return

    status_msg = bot.reply_to(message, "⏳ **Streaming & saving file securely to server disk...**", parse_mode="Markdown")
    try:
        file_info = bot.get_file(message.document.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        user_dir = os.path.abspath(os.path.join(BASE_DIR, str(user_id)))
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, file_name)

        with requests.get(file_url, stream=True, timeout=90) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        if file_name.endswith('.zip'):
            extract_folder = os.path.join(user_dir, os.path.splitext(file_name)[0])
            os.makedirs(extract_folder, exist_ok=True)
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(extract_folder)

        if file_name not in user["files"]:
            user["files"].append(file_name)
            global_stats["total_file_records"] += 1

        is_auto = system_config["auto_approve_files"] or "Premium" in user["status"]
        timestamp_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        user.setdefault("files_data", {})[file_name] = {
            "project_name": "Check Files",
            "filename": file_name,
            "type": ext,
            "size": f"{round((message.document.file_size or 0) / 1024, 2)} KB",
            "status": "Stopped",
            "approval": "Approved" if is_auto else "Pending",
            "upload_time": timestamp_now,
            "reject_reason": None,
            "reject_time": None
        }

        if is_auto:
            if file_name not in user.setdefault("approved_files", []):
                user["approved_files"].append(file_name)
            save_db()
            ok, start_msg = start_bot_process(user_id, file_name)
            if ok:
                user["files_data"][file_name]["status"] = "Running"
                save_db()
                bot.edit_message_text(
                    f"✅ **Project ka naam set ho gaya: 📁 Check Files 🎉**\n\n"
                    f"✅ **File `{file_name}` uploaded and approved 24/7!**\n"
                    f"• Status: 🟢 **Running 24/7**\n"
                    f"Open **Check Files** menu to inspect live console output or restart.",
                    message.chat.id, status_msg.message_id, parse_mode="Markdown"
                )
            else:
                user["files_data"][file_name]["status"] = "Stopped"
                save_db()
                bot.edit_message_text(
                    f"✅ **Project ka naam set ho gaya: 📁 Check Files 🎉**\n\n"
                    f"⚠️ **File `{file_name}` approved, but startup failed:**\n`{start_msg}`\n\nOpen **Check Files** -> **View Logs** for details.",
                    message.chat.id, status_msg.message_id, parse_mode="Markdown"
                )
        else:
            save_db()
            file_hash = hashlib.md5(file_name.encode()).hexdigest()[:8]
            app_markup = InlineKeyboardMarkup(row_width=2)
            app_markup.add(
                IBtn("✅ Approve", style="success", callback_data=f"app_{user_id}_{file_hash}"),
                IBtn("❌ Reject", style="danger", callback_data=f"rej_{user_id}_{file_hash}")
            )
            for admin in ADMIN_IDS:
                try:
                    bot.send_message(
                        admin,
                        f"📁 **New File Uploaded for 24/7 Hosting Review!**\n\n"
                        f"👤 **User:** {user['username']} (`{user_id}`)\n"
                        f"📄 **File:** `{file_name}`\n"
                        f"📊 **Type:** `{ext}`\n"
                        f"💾 **Allocated RAM:** {user['ram']}",
                        parse_mode="Markdown", reply_markup=app_markup
                    )
                except Exception:
                    pass
            bot.edit_message_text(
                f"✅ **Project ka naam set ho gaya: 📁 Check Files 🎉**\n\n"
                f"✅ **File `{file_name}` uploaded successfully!**\n"
                f"⏳ Pending approval by administrator...",
                message.chat.id, status_msg.message_id, parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error uploading file for user {user_id}: {e}\n{traceback.format_exc()}")
        bot.edit_message_text(f"❌ Error uploading file: {str(e)}", message.chat.id, status_msg.message_id)

# ================= BOOTSTRAP INITIALIZATION =================
if __name__ == "__main__":
    logger.info("Initializing hosting engine...")

    # Start web server for Render health checks in background thread
    web_server_thread = threading.Thread(target=run_render_web_server, daemon=True)
    web_server_thread.start()
    logger.info(f"[RENDER] Web server active on port {os.environ.get('PORT', 10000)}")

    # Load users database and configs
    load_db()

    # Rehost all running bots
    auto_rehost_all_approved_bots()

    # Launch watchdog thread
    watchdog_thread = threading.Thread(target=process_watchdog, daemon=True)
    watchdog_thread.start()

    logger.info("✧ Sɪʟᴇɴᴛ Kɪʟʟᴇ r ✧ Hosting Bot is active, persistent, and running 24/7 on Render...")

    try:
        bot.remove_webhook()
    except Exception as e:
        logger.warning(f"[STARTUP] Webhook check notice: {e}")

    # Polling loop with resilient auto-reconnect logic
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Telegram polling dropped: {e}\n{traceback.format_exc()}")
            time.sleep(5)
