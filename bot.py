import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import logging
from datetime import datetime
import signal
import sys

# Bot configuration
API_ID = 12345678
API_HASH = "API_HASH"
BOT_TOKEN = "BOT_TOKN"
ADMIN_ID = 5794368579

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize bot
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State management
user_states = {}

def set_user_state(user_id, state, data=None):
    user_states[user_id] = {
        'state': state,
        'data': data or {},
        'timestamp': datetime.now()
    }
    logger.info(f"Set state for user {user_id}: {state}")

def get_state_data(user_id):
    if user_id in user_states:
        return user_states[user_id].get('data', {})
    return {}

def get_user_state(user_id):
    if user_id in user_states:
        # Remove expired states (1 hour timeout)
        if (datetime.now() - user_states[user_id]['timestamp']).seconds > 3600:
            del user_states[user_id]
            return None
        return user_states[user_id]['state']
    return None

def clear_user_state(user_id):
    if user_id in user_states:
        del user_states[user_id]
        logger.info(f"Cleared state for user {user_id}")

# Database setup
def init_db():
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            # Users table
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                card_number TEXT,
                sheba_number TEXT,
                balance REAL DEFAULT 0,
                approved_numbers INTEGER DEFAULT 0,
                registered_at TEXT
            )''')
            
            # Submissions table
            c.execute('''CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                content_type TEXT,
                status TEXT DEFAULT 'pending',
                submitted_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            # Support messages table
            c.execute('''CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                direction TEXT,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            # Bot status table
            c.execute('''CREATE TABLE IF NOT EXISTS bot_status (
                id INTEGER PRIMARY KEY DEFAULT 1,
                is_active BOOLEAN DEFAULT 1
            )''')
            
            # Create indexes for performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON submissions(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_support_user_id ON support_messages(user_id)')
            
            # Initialize bot status
            c.execute("INSERT OR IGNORE INTO bot_status (id, is_active) VALUES (1, 1)")
            
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise

# Check bot status
def is_bot_active():
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT is_active FROM bot_status WHERE id = 1")
            result = c.fetchone()
            return bool(result[0]) if result else True
    except sqlite3.Error as e:
        logger.error(f"Database error in is_bot_active: {e}")
        return False

# Start command
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    logger.info(f"Start command from user {user_id}")
    
    if not is_bot_active():
        await message.reply("❌ ربات در حال حاضر غیرفعال است.")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
            
            if not user:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 ثبت نام", callback_data="register")]
                ])
                await message.reply(
                    "👋 به ربات خوش آمدید! لطفاً ثبت نام کنید.",
                    reply_markup=keyboard
                )
            else:
                await show_main_menu(message)
    except sqlite3.Error as e:
        logger.error(f"Database error in start: {e}")
        await message.reply("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

# Main menu
async def show_main_menu(message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 ارسال محتوا", callback_data="submit_content")],
        [InlineKeyboardButton("📋 پروفایل من", callback_data="my_profile")],
        [InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data="edit_profile")],
        [InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
        [InlineKeyboardButton("💰 موجودی", callback_data="check_balance")]
    ])
    
    await message.reply("📋 منوی اصلی", reply_markup=keyboard)

# Admin panel
@app.on_message(filters.command("admin") & filters.user(ADMIN_ID) & filters.private)
async def admin_panel(client, message):
    logger.info(f"Admin command from {message.from_user.id}")
    await show_admin_panel(message)

async def show_admin_panel(message):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) FROM users")
            user_count = c.fetchone()[0]
            
            c.execute("SELECT is_active FROM bot_status WHERE id = 1")
            bot_status = "آنلاین" if c.fetchone()[0] else "آفلاین"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"👥 کاربران ({user_count})", callback_data="view_users")],
                [InlineKeyboardButton(f"🤖 وضعیت ربات: {bot_status}", callback_data="toggle_bot")],
                [InlineKeyboardButton("💸 مدیریت موجودی", callback_data="manage_balances")],
                [InlineKeyboardButton("📨 پیام‌های پشتیبانی", callback_data="view_support")]
            ])
            
            await message.reply("🔧 پنل ادمین", reply_markup=keyboard)
    except sqlite3.Error as e:
        logger.error(f"Database error in admin panel: {e}")
        await message.reply("❌ خطای پایگاه داده.")

# Callback query handler
@app.on_callback_query()
async def handle_callback(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    try:
        # ابتدا فوراً به callback پاسخ دهید
        await callback_query.answer()
        
        if not is_bot_active() and data != "toggle_bot":
            return

        if data == "register":
            await handle_register(callback_query)
        elif data == "submit_content":
            await handle_submit_content(client, callback_query)
        elif data == "my_profile":
            await handle_my_profile(callback_query)
        elif data == "edit_profile":
            await handle_edit_profile(client, callback_query)
        elif data == "back_to_main":
            await show_main_menu(callback_query.message)
        elif data == "support":
            await handle_support_callback(client, callback_query)
        elif data == "check_balance":
            await handle_check_balance(client, callback_query)
        elif data == "toggle_bot" and user_id == ADMIN_ID:
            await handle_toggle_bot(client, callback_query)
        elif data == "view_users" and user_id == ADMIN_ID:
            await handle_view_users(client, callback_query)
        elif data == "manage_balances" and user_id == ADMIN_ID:
            await handle_manage_balances(client, callback_query)
        elif data == "view_support" and user_id == ADMIN_ID:
            await handle_view_support(client, callback_query)
        elif data == "cancel_reply":
            await handle_cancel_reply(client, callback_query)
        elif data.startswith("reply_"):
            await handle_reply_callback(client, callback_query)
        elif data.startswith("approve_") or data.startswith("reject_"):
            await handle_content_approval(client, callback_query)
        elif data == "edit_first_name":
            await callback_query.message.reply("✏️ لطفاً نام جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_first_name")
        elif data == "edit_last_name":
            await callback_query.message.reply("✏️ لطفاً نام خانوادگی جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_last_name")
        elif data == "edit_card":
            await callback_query.message.reply("💳 لطفاً شماره کارت جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_card")
        elif data == "edit_sheba":
            await callback_query.message.reply("🏦 لطفاً شماره شبا جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_sheba")    
        
    except Exception as e:
        logger.error(f"Error in callback {data}: {e}")

async def handle_edit_profile(client, callback_query):
    user_id = callback_query.from_user.id
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
            
            if not user:
                await callback_query.message.reply("❌ شما هنوز ثبت نام نکرده‌اید!")
                return
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ ویرایش نام", callback_data="edit_first_name")],
                [InlineKeyboardButton("✏️ ویرایش نام خانوادگی", callback_data="edit_last_name")],
                [InlineKeyboardButton("💳 ویرایش شماره کارت", callback_data="edit_card")],
                [InlineKeyboardButton("🏦 ویرایش شماره شبا", callback_data="edit_sheba")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
            ])
            
            await callback_query.message.reply("✏️ لطفاً بخشی که می‌خواهید ویرایش کنید را انتخاب کنید:", reply_markup=keyboard)
            await callback_query.answer()
            
    except sqlite3.Error as e:
        logger.error(f"Database error in edit profile: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
        await callback_query.answer()

# Registration handlers
async def handle_register(callback_query):
    user_id = callback_query.from_user.id
    
    with sqlite3.connect('bot_db.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if c.fetchone():
            await callback_query.message.reply("✅ شما قبلاً ثبت نام کرده‌اید!")
            await show_main_menu(callback_query.message)
        else:
            await callback_query.message.reply("📝 لطفاً نام خود را وارد کنید:")
            set_user_state(user_id, "waiting_for_first_name")
    
    await callback_query.answer()

# Content submission handlers
async def handle_submit_content(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        await callback_query.message.reply("📤 لطفاً محتوای خود را ارسال کنید (متن یا عکس):")
        set_user_state(user_id, "waiting_for_content")
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in submit content callback: {e}")
        await callback_query.answer("❌ خطا در پردازش ارسال محتوا", show_alert=True)

# Profile handlers
async def handle_my_profile(callback_query):
    user_id = callback_query.from_user.id
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
            
            if user:
                profile_text = (
                    f"📋 پروفایل\n\n"
                    f"نام: {user[1]}\n"
                    f"نام خانوادگی: {user[2]}\n"
                    f"شماره کارت: {user[3]}\n"
                    f"شماره شبا: {user[4]}\n"
                    f"موجودی: {user[5]:,.0f} تومان\n"
                    f"تعداد محتواهای تایید شده: {user[6]}\n"
                    f"تاریخ ثبت نام: {user[7]}"
                )
                await callback_query.message.reply(profile_text)
            else:
                await callback_query.message.reply("❌ کاربر یافت نشد.")
    except sqlite3.Error as e:
        logger.error(f"Database error in profile: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
    
    await callback_query.answer()

# Support handlers
async def handle_support_callback(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        await callback_query.message.reply("💬 لطفاً پیام خود را برای پشتیبانی ارسال کنید:")
        set_user_state(user_id, "waiting_for_support")
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in support callback: {e}")
        await callback_query.answer("❌ خطا در پردازش درخواست پشتیبانی", show_alert=True)

# Balance handlers
async def handle_check_balance(client, callback_query):
    user_id = callback_query.from_user.id
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance = c.fetchone()
            
            if balance:
                await callback_query.message.reply(f"💰 موجودی شما: {balance[0]:,.0f} تومان")
            else:
                await callback_query.message.reply("❌ کاربر یافت نشد.")
    except sqlite3.Error as e:
        logger.error(f"Database error in balance: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
    
    await callback_query.answer()

# Admin handlers
async def handle_toggle_bot(client, callback_query):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT is_active FROM bot_status WHERE id = 1")
            current_status = c.fetchone()[0]
            new_status = not current_status
            
            c.execute("UPDATE bot_status SET is_active = ? WHERE id = 1", (new_status,))
            conn.commit()
            
            status_text = "آنلاین" if new_status else "آفلاین"
            status_emoji = "🟢" if new_status else "🔴"
            
            # اطلاع به ادمین
            await callback_query.message.reply(f"{status_emoji} ربات {status_text} شد!")
            await show_admin_panel(callback_query.message)
            
            # اطلاع به همه کاربران
            try:
                c.execute("SELECT user_id FROM users")
                users = c.fetchall()
                
                notification_text = (
                    f"{status_emoji} ربات {status_text} شد!\n\n"
                    f"در حال حاضر ربات {'آماده به کار است' if new_status else 'موقتاً غیرفعال شده است'}."
                )
                
                for user in users:
                    try:
                        await client.send_message(user[0], notification_text)
                        logger.info(f"Notification sent to user {user[0]}")
                    except Exception as e:
                        logger.error(f"Failed to notify user {user[0]}: {e}")
                        
                logger.info(f"Bot status changed to {status_text}, notifications sent to {len(users)} users")
                
            except Exception as e:
                logger.error(f"Error sending notifications: {e}")
                await client.send_message(ADMIN_ID, f"خطا در ارسال اطلاعیه به کاربران: {e}")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in toggle bot: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
    
    await callback_query.answer()

async def handle_view_users(client, callback_query):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, first_name, last_name, approved_numbers, balance FROM users")
            users = c.fetchall()
            
            if not users:
                await callback_query.message.reply("❌ کاربری یافت نشد.")
                return
            
            users_text = "👥 لیست کاربران:\n\n"
            for user in users:
                users_text += (
                    f"🆔 ID: {user[0]}\n"
                    f"👤 نام: {user[1]} {user[2]}\n"
                    f"✅ تعداد تایید شده: {user[3]}\n"
                    f"💰 موجودی: {user[4]:,.0f} تومان\n"
                    f"────────────────────\n"
                )
            
            await callback_query.message.reply(users_text)
    except sqlite3.Error as e:
        logger.error(f"Database error in view users: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
    
    await callback_query.answer()

async def handle_manage_balances(client, callback_query):
    await callback_query.message.reply(
        "💸 لطفاً ID کاربر و مبلغ جدید را به این فرمت وارد کنید:\n"
        "12345 100000\n"
        "(شناسه کاربر و مبلغ به تومان)"
    )
    set_user_state(callback_query.from_user.id, "waiting_for_balance_update")
    await callback_query.answer()

async def handle_view_support(client, callback_query):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("""
                SELECT user_id, message, direction, created_at 
                FROM support_messages 
                ORDER BY created_at DESC 
                LIMIT 10
            """)
            messages = c.fetchall()
            
            if not messages:
                await callback_query.message.reply("❌ پیام پشتیبانی یافت نشد.")
                return
            
            messages_text = "📨 آخرین پیام‌های پشتیبانی:\n\n"
            for msg in messages:
                direction = "👤 کاربر به ادمین" if msg[2] == "user_to_admin" else "👨‍💼 ادمین به کاربر"
                messages_text += (
                    f"🆔 کاربر: {msg[0]}\n"
                    f"📝 {direction}\n"
                    f"⏰ زمان: {msg[3]}\n"
                    f"📩 پیام: {msg[1]}\n"
                    f"────────────────────\n"
                )
            
            await callback_query.message.reply(messages_text)
    except sqlite3.Error as e:
        logger.error(f"Database error in view support: {e}")
        await callback_query.message.reply("❌ خطای پایگاه داده.")
    
    await callback_query.answer()

async def handle_cancel_reply(client, callback_query):
    clear_user_state(callback_query.from_user.id)
    await callback_query.message.reply("❌ پاسخ دادن لغو شد.")
    await callback_query.answer()

# Reply to support handlers
async def handle_reply_callback(client, callback_query):
    try:
        # استخراج user_id از callback_data
        user_id = int(callback_query.data.split("_")[1])
        
        # ذخیره state به صورت صحیح
        set_user_state(callback_query.from_user.id, "waiting_for_reply", {"target_user_id": user_id})
        
        await callback_query.message.reply(
            f"✍️ در حال پاسخ به کاربر {user_id}. لطفاً پاسخ خود را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_reply")]
            ])
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in reply callback: {e}")
        await callback_query.answer("❌ خطا در پردازش درخواست", show_alert=True)

# Approve/Reject handlers
async def handle_content_approval(client, callback_query):
    try:
        # ابتدا فوراً به callback پاسخ دهید
        await callback_query.answer()
        
        action, submission_id = callback_query.data.split("_")
        submission_id = int(submission_id)
        admin_id = callback_query.from_user.id

        if admin_id != ADMIN_ID:
            logger.warning(f"Unauthorized approval attempt by user {admin_id}")
            return

        with sqlite3.connect("bot_db.db") as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, content, content_type, status FROM submissions WHERE id = ?", (submission_id,))
            submission = c.fetchone()

            if not submission:
                logger.warning(f"Submission {submission_id} not found")
                return

            user_id, content, content_type, status = submission

            if status != "pending":
                logger.warning(f"Attempt to modify non-pending submission {submission_id}")
                return

            new_status = "approved" if action == "approve" else "rejected"
            emoji = "✅" if action == "approve" else "❌"
            action_text = "تایید" if action == "approve" else "رد"  # استفاده از کاراکترهای ساده‌تر

            # به‌روزرسانی وضعیت محتوا
            c.execute(f"UPDATE submissions SET status = ? WHERE id = ?", (new_status, submission_id))
            
            if action == "approve":
                c.execute("UPDATE users SET approved_numbers = approved_numbers + 1 WHERE user_id = ?", (user_id,))
            
            conn.commit()
            logger.info(f"Submission {submission_id} {new_status} for user {user_id}")

            # اطلاع به کاربر
            try:
                if content_type == "text":
                    await client.send_message(user_id, f"{emoji} محتوای شما {action_text} شد:\n\n{content}")
                else:
                    await client.send_photo(user_id, photo=content, caption=f"{emoji} عکس شما {action_text} شد!")
                logger.info(f"User {user_id} notified of {action_text} for submission {submission_id}")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
                await client.send_message(ADMIN_ID, f"خطا در اطلاع‌رسانی به کاربر {user_id}")

            # ویرایش پیام ادمین
            try:
                if hasattr(callback_query.message, 'photo'):
                    await callback_query.message.edit_caption(
                        caption=f"{emoji} محتوای کاربر {user_id} {action_text} شد (ID: {submission_id})",
                        reply_markup=None
                    )
                else:
                    await callback_query.message.edit_text(
                        text=f"{emoji} محتوای کاربر {user_id} {action_text} شد (ID: {submission_id})",
                        reply_markup=None
                    )
            except Exception as e:
                logger.error(f"Failed to edit admin message: {e}")

    except Exception as e:
        logger.error(f"Error in approval process: {e}")

# Message handlers
@app.on_message(filters.private & ~filters.command(["start", "admin"]))
async def handle_message(client, message):
    if not is_bot_active():
        await message.reply("❌ ربات در حال حاضر غیرفعال است.")
        return
    
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state:
        return
    
    try:
        # Registration states
        if state == "waiting_for_first_name":
            await handle_first_name(message)
        elif state == "waiting_for_last_name":
            await handle_last_name(message)
        elif state == "waiting_for_card":
            await handle_card_number(message)
        elif state == "waiting_for_sheba":
            await handle_sheba_number(message)
        
        # Edit states (using the same handlers as registration)
        elif state == "editing_first_name":
            new_first_name = message.text.strip()
            if not new_first_name:
                await message.reply("❌ نام نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
                return
            
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE users SET first_name = ? WHERE user_id = ?",
                    (new_first_name, user_id)
                )
                conn.commit()
            
            await message.reply("✅ نام شما با موفقیت به‌روزرسانی شد.")
            clear_user_state(user_id)
            await show_main_menu(message)
        
        # ویرایش نام خانوادگی
        elif state == "editing_last_name":
            new_last_name = message.text.strip()
            if not new_last_name:
                await message.reply("❌ نام خانوادگی نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
                return
            
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE users SET last_name = ? WHERE user_id = ?",
                    (new_last_name, user_id)
                )
                conn.commit()
            
            await message.reply("✅ نام خانوادگی شما با موفقیت به‌روزرسانی شد.")
            clear_user_state(user_id)
            await show_main_menu(message)
        
        # ویرایش شماره کارت
        elif state == "editing_card":
            new_card = message.text.strip()
            if not new_card or not new_card.isdigit():
                await message.reply("❌ شماره کارت باید عددی باشد. لطفاً دوباره وارد کنید:")
                return
            
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE users SET card_number = ? WHERE user_id = ?",
                    (new_card, user_id)
                )
                conn.commit()
            
            await message.reply("✅ شماره کارت شما با موفقیت به‌روزرسانی شد.")
            clear_user_state(user_id)
            await show_main_menu(message)
        
        # ویرایش شماره شبا
        elif state == "editing_sheba":
            new_sheba = message.text.strip()
            if not new_sheba or not new_sheba.startswith("IR") or len(new_sheba) != 26:
                await message.reply("❌ شماره شبا باید با IR شروع شود و 26 کاراکتر باشد. لطفاً دوباره وارد کنید:")
                return
            
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE users SET sheba_number = ? WHERE user_id = ?",
                    (new_sheba, user_id)
                )
                conn.commit()
            
            await message.reply("✅ شماره شبا شما با موفقیت به‌روزرسانی شد.")
            clear_user_state(user_id)
            await show_main_menu(message)
        
        # Content submission
        elif state == "waiting_for_content":
            await handle_content_submission(client, message)
        
        # Support messages
        elif state == "waiting_for_support":
            await handle_support_message(client, message)
        
        # Admin states
        elif user_id == ADMIN_ID and state == "waiting_for_balance_update":
            await handle_balance_update(client, message)
        elif user_id == ADMIN_ID and state == "waiting_for_reply":
            await handle_admin_reply(client, message)
            
    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        await message.reply("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

# Registration handlers (now used for both registration and editing)
async def handle_first_name(message, edit_mode=False):
    first_name = message.text.strip()
    if not first_name:
        await message.reply("❌ نام نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET first_name = ? WHERE user_id = ?",
                    (first_name, message.from_user.id))
                conn.commit()
                await message.reply("✅ نام شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute("INSERT OR REPLACE INTO users (user_id, first_name, registered_at) VALUES (?, ?, ?)",
                    (message.from_user.id, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                await message.reply("📝 لطفاً نام خانوادگی خود را وارد کنید:")
                set_user_state(message.from_user.id, "waiting_for_last_name")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in first name: {e}")
        await message.reply("❌ خطای پایگاه داده.")

async def handle_last_name(message, edit_mode=False):
    last_name = message.text.strip()
    if not last_name:
        await message.reply("❌ نام خانوادگی نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET last_name = ? WHERE user_id = ?",
                    (last_name, message.from_user.id))
                conn.commit()
                await message.reply("✅ نام خانوادگی شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET last_name = ? WHERE user_id = ?",
                    (last_name, message.from_user.id))
                conn.commit()
                await message.reply("💳 لطفاً شماره کارت خود را وارد کنید:")
                set_user_state(message.from_user.id, "waiting_for_card")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in last name: {e}")
        await message.reply("❌ خطای پایگاه داده.")

async def handle_card_number(message, edit_mode=False):
    card_number = message.text.strip()
    if not card_number or not card_number.isdigit():
        await message.reply("❌ شماره کارت باید عددی باشد. لطفاً دوباره وارد کنید:")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET card_number = ? WHERE user_id = ?",
                    (card_number, message.from_user.id))
                conn.commit()
                await message.reply("✅ شماره کارت شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET card_number = ? WHERE user_id = ?",
                    (card_number, message.from_user.id))
                conn.commit()
                await message.reply("🏦 لطفاً شماره شبا خود را وارد کنید:")
                set_user_state(message.from_user.id, "waiting_for_sheba")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in card number: {e}")
        await message.reply("❌ خطای پایگاه داده.")

async def handle_sheba_number(message, edit_mode=False):
    sheba_number = message.text.strip()
    if not sheba_number or not sheba_number.startswith("IR") or len(sheba_number) != 26:
        await message.reply("❌ شماره شبا باید با IR شروع شود و 26 کاراکتر باشد. لطفاً دوباره وارد کنید:")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET sheba_number = ? WHERE user_id = ?",
                    (sheba_number, message.from_user.id))
                conn.commit()
                await message.reply("✅ شماره شبا شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET sheba_number = ? WHERE user_id = ?",
                    (sheba_number, message.from_user.id))
                conn.commit()
                await message.reply("✅ ثبت نام شما با موفقیت انجام شد!")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
                
    except sqlite3.Error as e:
        logger.error(f"Database error in sheba number: {e}")
        await message.reply("❌ خطای پایگاه داده.")

# Content submission handler
@app.on_message(filters.private & (filters.text | filters.photo) & ~filters.command(["start", "admin"]))
async def handle_content_submission(client, message):
    user_id = message.from_user.id
    if get_user_state(user_id) != "waiting_for_content":
        return

    try:
        # بررسی نوع محتوا
        content = None
        content_type = None
        if message.text:
            content = message.text.strip()
            content_type = "text"
            if not content:
                await message.reply("❌ متن نمی‌تواند خالی باشد. لطفاً محتوای خود را وارد کنید:")
                logger.warning(f"Empty text content attempt by user {user_id}")
                return
        elif message.photo:
            content = message.photo.file_id
            content_type = "photo"
        else:
            await message.reply("❌ نوع محتوای ارسالی پشتیبانی نمی‌شود. لطفاً متن یا عکس ارسال کنید.")
            logger.warning(f"Unsupported content type by user {user_id}")
            return

        # ثبت محتوا در پایگاه داده
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO submissions (user_id, content, content_type, submitted_at, status) VALUES (?, ?, ?, ?, ?)",
                (user_id, content, content_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending")
            )
            conn.commit()
            submission_id = c.lastrowid
            logger.info(f"Content submission {submission_id} from user {user_id} stored")

        # پاسخ به کاربر
        await message.reply("✅ محتوای شما با موفقیت ارسال شد و در انتظار تأیید است.")
        clear_user_state(user_id)

        # ارسال به ادمین
        try:
            if content_type == "text":
                await client.send_message(
                    ADMIN_ID,
                    f"📨 محتوای جدید از کاربر {user_id} (ID: {submission_id}):\n\n{content}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{submission_id}")],
                        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{submission_id}")]
                    ])
                )
            else:
                await client.send_photo(
                    ADMIN_ID,
                    photo=content,
                    caption=f"📸 عکس جدید از کاربر {user_id} (ID: {submission_id})",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{submission_id}")],
                        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{submission_id}")]
                    ])
                )
            logger.info(f"Content submission {submission_id} sent to admin")
        except Exception as e:
            logger.error(f"Failed to send content to admin: {e}")
            await client.send_message(user_id, "❌ خطا در ارسال محتوا به ادمین. لطفاً دوباره تلاش کنید.")
            # حذف محتوا از پایگاه داده در صورت خطا
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
                conn.commit()
                logger.info(f"Submission {submission_id} deleted due to admin notification failure")
            return

    except sqlite3.Error as e:
        logger.error(f"Database error in content submission: {e}")
        await message.reply("❌ خطای پایگاه داده. لطفاً دوباره تلاش کنید.")
    except Exception as e:
        logger.error(f"Error in content submission: {e}")
        await message.reply("❌ خطا در ارسال محتوا.")

# Support message handler
@app.on_message(filters.private & filters.text & ~filters.command(["start", "admin"]))
async def handle_support_message(client, message):
    user_id = message.from_user.id
    if get_user_state(user_id) != "waiting_for_support":
        return

    try:
        message_text = message.text.strip()
        if not message_text:
            await message.reply("❌ پیام نمی‌تواند خالی باشد. لطفاً پیام خود را وارد کنید:")
            logger.warning(f"Empty support message attempt by user {user_id}")
            return

        # ثبت پیام در پایگاه داده
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO support_messages (user_id, message, direction, created_at) VALUES (?, ?, ?, ?)",
                (user_id, message_text, "user_to_admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            logger.info(f"Support message from user {user_id} stored")

        # ارسال پیام به ادمین
        try:
            await client.send_message(
                ADMIN_ID,
                f"📩 پیام پشتیبانی جدید از کاربر {user_id}:\n\n{message_text}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 پاسخ", callback_data=f"reply_{user_id}")]
                ])
            )
            logger.info(f"Support message sent to admin from user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send support message to admin: {e}")
            await message.reply("❌ خطا در ارسال پیام به ادمین. لطفاً بعداً تلاش کنید.")
            return

        # پاسخ به کاربر
        await message.reply("✅ پیام شما با موفقیت به پشتیبانی ارسال شد.")
        clear_user_state(user_id)

    except sqlite3.Error as e:
        logger.error(f"Database error in support message: {e}")
        await message.reply("❌ خطای پایگاه داده. لطفاً دوباره تلاش کنید.")
    except Exception as e:
        logger.error(f"Error in support message: {e}")
        await message.reply("❌ خطا در پردازش پیام پشتیبانی.")

# Admin balance update handler
async def handle_balance_update(client, message):
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError("Invalid format")
        
        target_user_id = int(parts[0])
        new_balance = float(parts[1])
        
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            # Check if user exists
            c.execute("SELECT user_id FROM users WHERE user_id = ?", (target_user_id,))
            if not c.fetchone():
                await message.reply(f"❌ کاربر با شناسه {target_user_id} یافت نشد.")
                return
            
            # Update balance
            c.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, target_user_id))
            conn.commit()
        
        await message.reply(f"✅ موجودی کاربر {target_user_id} به {new_balance:,.0f} تومان به‌روزرسانی شد.")
        clear_user_state(message.from_user.id)
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"💰 موجودی حساب شما به {new_balance:,.0f} تومان به‌روزرسانی شد."
            )
            logger.info(f"User {target_user_id} notified of balance update")
        except Exception as e:
            logger.error(f"Error notifying user {target_user_id}: {e}")
            await message.reply(f"❌ خطا در ارسال پیام به کاربر {target_user_id}: {str(e)}")
        
    except ValueError:
        await message.reply("❌ فرمت نامعتبر. لطفاً به این فرمت وارد کنید:\nشناسه_کاربر مبلغ\nمثال: 12345 100000")
    except sqlite3.Error as e:
        logger.error(f"Database error in balance update: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Error in balance update: {e}")
        await message.reply("❌ خطایی در به‌روزرسانی موجودی رخ داد.")

# Admin reply handler
async def handle_admin_reply(client, message):
    state = get_user_state(message.from_user.id)
    state_data = get_state_data(message.from_user.id)
    
    if state == "waiting_for_reply" and state_data and "target_user_id" in state_data:
        try:
            user_id = state_data["target_user_id"]
            reply_text = message.text.strip()

            if not reply_text:
                await message.reply("❌ پیام پاسخ نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
                logger.warning(f"Empty reply attempt by admin for user {user_id}")
                return

            # Verify user exists
            with sqlite3.connect('bot_db.db') as conn:
                c = conn.cursor()
                c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if not c.fetchone():
                    await message.reply(f"❌ کاربر با شناسه {user_id} یافت نشد.")
                    clear_user_state(message.from_user.id)
                    logger.error(f"User {user_id} not found for reply")
                    return

                # Store reply in database
                c.execute(
                    "INSERT INTO support_messages (user_id, message, direction, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, reply_text, "admin_to_user", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                logger.info(f"Support reply stored for user {user_id}")

            # Send reply to user
            try:
                await client.send_message(user_id, f"📩 پاسخ پشتیبانی:\n\n{reply_text}")
                await message.reply(f"✅ پاسخ شما به کاربر {user_id} ارسال شد.")
                logger.info(f"Reply sent to user {user_id}")
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                await message.reply(f"❌ خطا در ارسال پیام به کاربر {user_id}: {str(e)}")

            clear_user_state(message.from_user.id)

        except sqlite3.Error as e:
            logger.error(f"Database error in admin reply: {e}")
            await message.reply("❌ خطای پایگاه داده.")
            clear_user_state(message.from_user.id)
        except Exception as e:
            logger.error(f"Error in admin reply: {e}")
            await message.reply("❌ خطا در ارسال پاسخ.")
            clear_user_state(message.from_user.id)

# Run the bot
if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    
    # Start the bot
    logger.info("Starting bot...")
    app.run()