import os
import json
import time
import random
import string
from datetime import datetime, timedelta
import pytz

# --- File Paths ---
APIS_FILE = "apis.json"
STATS_FILE = "stats.json"
USERS_FILE = "users.json"
USER_DATA_FILE = "user_data.json"
ADMINS_FILE = "admins.json"
BLOCKED_USERS_FILE = "blocked_users.json"
BONUS_CLAIMS_FILE = "bonus_claims.json"
# --- New Files for New Features ---
REFERRALS_FILE = "referrals.json" # To track pending referrals
REDEEM_CODES_FILE = "redeem_codes.json" # To store active redeem codes

# --- Timezone for Daily Bonus Reset ---
BD_TZ = pytz.timezone("Asia/Dhaka")

# --- Helper Functions ---
def load_json(file_path, default_data):
    if not os.path.exists(file_path):
        save_json(file_path, default_data)
        return default_data
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            if not content:
                save_json(file_path, default_data)
                return default_data
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        save_json(file_path, default_data)
        return default_data

def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
        
def random_string(length):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

# --- Data Initialization ---
def initialize_files():
    """Initializes all necessary files."""
    load_json(APIS_FILE, [])
    load_json(STATS_FILE, {"total_users": 0, "total_sms_sent": 0})
    load_json(USERS_FILE, {})
    load_json(ADMINS_FILE, [])
    load_json(BLOCKED_USERS_FILE, [])
    load_json(BONUS_CLAIMS_FILE, {})
    load_json(REFERRALS_FILE, {})
    load_json(REDEEM_CODES_FILE, [])

# --- User Management ---
def add_user_to_db(user):
    users = load_json(USERS_FILE, {})
    user_id_str = str(user.id)
    if user_id_str not in users:
        users[user_id_str] = {"full_name": user.full_name, "username": user.username or "N/A"}
        save_json(USERS_FILE, users)
        
        stats = load_json(STATS_FILE, {"total_users": 0, "total_sms_sent": 0})
        stats["total_users"] = len(users)
        save_json(STATS_FILE, stats)

        user_data = load_json(USER_DATA_FILE, {})
        user_data[user_id_str] = {"sms_sent": 0, "coins": 0}
        save_json(USER_DATA_FILE, user_data)

# --- Coin and Stats Management ---
def get_user_data(user_id):
    user_data = load_json(USER_DATA_FILE, {})
    return user_data.get(str(user_id), {"sms_sent": 0, "coins": 0})

def get_user_coins(user_id):
    return get_user_data(user_id).get("coins", 0)

def use_coin(user_id):
    user_data = load_json(USER_DATA_FILE, {})
    user_id_str = str(user_id)
    if user_id_str not in user_data or user_data[user_id_str].get("coins", 0) < 1:
        return False
    user_data[user_id_str]["coins"] -= 1
    save_json(USER_DATA_FILE, user_data)
    return True

def add_coins(user_id, amount):
    user_data = load_json(USER_DATA_FILE, {})
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        # This case is for referrers who might not be in user_data yet
        # Although add_user_to_db should handle it.
        user_data[user_id_str] = {"sms_sent": 0, "coins": 0}
    
    current_coins = user_data[user_id_str].get("coins", 0)
    user_data[user_id_str]["coins"] = current_coins + amount
    save_json(USER_DATA_FILE, user_data)
    
# --- Referral System ---
def store_pending_referral(referee_id, referrer_id):
    pending_referrals = load_json(REFERRALS_FILE, {})
    pending_referrals[str(referee_id)] = str(referrer_id)
    save_json(REFERRALS_FILE, pending_referrals)

def get_pending_referrer(referee_id):
    pending_referrals = load_json(REFERRALS_FILE, {})
    return pending_referrals.get(str(referee_id))

def complete_referral(referee_id):
    pending_referrals = load_json(REFERRALS_FILE, {})
    if str(referee_id) in pending_referrals:
        del pending_referrals[str(referee_id)]
        save_json(REFERRALS_FILE, pending_referrals)

# --- Redeem Code System ---
def generate_redeem_code():
    codes = load_json(REDEEM_CODES_FILE, [])
    new_code = f"BD-{random_string(4)}-{random_string(4)}"
    while new_code in codes: # Ensure uniqueness
        new_code = f"BD-{random_string(4)}-{random_string(4)}"
    codes.append(new_code)
    save_json(REDEEM_CODES_FILE, codes)
    return new_code

def is_valid_code(code):
    codes = load_json(REDEEM_CODES_FILE, [])
    return code in codes

def use_redeem_code(code):
    codes = load_json(REDEEM_CODES_FILE, [])
    if code in codes:
        codes.remove(code)
        save_json(REDEEM_CODES_FILE, codes)
        return True
    return False

# (Other functions like bonus management remain the same)
def can_claim_bonus(user_id):
    user_id_str = str(user_id)
    claims = load_json(BONUS_CLAIMS_FILE, {})
    if user_id_str not in claims: return True
    last_claim_date = datetime.fromisoformat(claims[user_id_str]).astimezone(BD_TZ).date()
    return datetime.now(BD_TZ).date() > last_claim_date

def claim_bonus(user_id):
    if not can_claim_bonus(user_id): return False
    add_coins(user_id, 3) # <<< পরিবর্তন: 5 কয়েনের পরিবর্তে 3 কয়েন করা হয়েছে
    claims = load_json(BONUS_CLAIMS_FILE, {})
    claims[str(user_id)] = datetime.now(BD_TZ).isoformat()
    save_json(BONUS_CLAIMS_FILE, claims)
    return True

def get_next_bonus_time():
    now = datetime.now(BD_TZ)
    tomorrow = now.date() + timedelta(days=1)
    midnight_naive = datetime.combine(tomorrow, datetime.min.time())
    midnight_aware = BD_TZ.localize(midnight_naive)
    remaining = midnight_aware - now
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"