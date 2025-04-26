import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import logging
from datetime import datetime
import signal
import sys

# Bot configuration
API_ID=1234567
API_HASH='API_HASH'
BOT_TOKEN='TOKEN'
ADMIN_ID=123456789

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

def init_db():
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            # جدول کاربران (بدون تغییر)
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                card_or_wallet TEXT,
                sheba_number TEXT,
                group_leader_name TEXT,
                balance REAL DEFAULT 0,
                approved_count INTEGER DEFAULT 0,
                registered_at TEXT
            )''')
            
            # جدول شمارهها (بدون تغییر)
            c.execute('''CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                content_type TEXT,
                status TEXT DEFAULT 'pending',
                submitted_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            # جدول جزئیات تأیید شماره (اصلاح‌شده: حذف total_items)
            c.execute('''CREATE TABLE IF NOT EXISTS submission_details (
                submission_id INTEGER PRIMARY KEY,
                approved_items INTEGER,  -- تعداد آیتم‌های تأییدشده
                FOREIGN KEY(submission_id) REFERENCES submissions(id)
            )''')
            
            # جدول پیام‌های پشتیبانی (بدون تغییر)
            c.execute('''CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                direction TEXT,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            # جدول وضعیت ربات (بدون تغییر)
            c.execute('''CREATE TABLE IF NOT EXISTS bot_status (
                id INTEGER PRIMARY KEY DEFAULT 1,
                is_active BOOLEAN DEFAULT 1
            )''')
            
            # جدول کانال‌های اجباری (بدون تغییر)
            c.execute('''CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                invite_link TEXT
            )''')
            
            # ایجاد ایندکس‌ها
            c.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON submissions(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_support_user_id ON support_messages(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_submission_details ON submission_details(submission_id)')
            
            # مقداردهی اولیه bot_status
            c.execute("INSERT OR IGNORE INTO bot_status (id, is_active) VALUES (1, 1)")
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise

def add_required_channel(channel_id, channel_name, invite_link):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO required_channels (channel_id, channel_name, invite_link) VALUES (?, ?, ?)",
                (channel_id, channel_name, invite_link)
            )
            conn.commit()
            logger.info(f"Added required channel: {channel_name} ({channel_id})")
    except sqlite3.Error as e:
        logger.error(f"Error adding required channel: {e}")

# مثال: اضافه کردن کانال
# add_required_channel("-1001234567890", "YourChannel", "https://t.me/YourChannel")

async def check_membership(client, user_id):
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT channel_id, channel_name, invite_link FROM required_channels")
            channels = c.fetchall()
        
        for channel_id, channel_name, invite_link in channels:
            try:
                member = await client.get_chat_member(int(channel_id), user_id)
                if member.status in ["left", "kicked"]:
                    return False, channel_name, invite_link
            except Exception as e:
                logger.error(f"Error checking membership for channel {channel_id}: {e}")
                return False, channel_name, invite_link
        
        return True, None, None
    except sqlite3.Error as e:
        logger.error(f"Database error in check_membership: {e}")
        return False, None, None

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
    
async def handle_reset_approved_count(client:Client, callback_query):
    await callback_query.message.reply(
        "🔄 لطفاً ID کاربر را برای صفر کردن تعداد تأیید شده‌ها وارد کنید:\n"
        f"مثال: {callback_query.from_user.id}"
    )
    set_user_state(callback_query.from_user.id, "waiting_for_reset_approved")
    await callback_query.answer()

async def handle_reset_approved_count_process(client, message):
    try:
        user_id = int(message.text.strip())
        
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            # بررسی وجود کاربر
            c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not c.fetchone():
                await message.reply(f"❌ کاربر با شناسه {user_id} یافت نشد.")
                return
            
            # صفر کردن تعداد تأیید شده‌ها
            c.execute(
                "UPDATE users SET approved_count = 0 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
        
        await message.reply(f"✅ تعداد تأیید شده‌های کاربر {user_id} با موفقیت صفر شد.")
        clear_user_state(message.from_user.id)
        
        # اطلاع‌رسانی به کاربر
        try:
            await client.send_message(
                user_id,
                "🔄 تعداد تأیید شده‌های شما توسط ادمین صفر شد."
            )
            logger.info(f"User {user_id} notified of approved count reset")
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")
            await message.reply(f"❌ خطا در ارسال پیام به کاربر {user_id}: {str(e)}")
        
    except ValueError:
        await message.reply("❌ فرمت نامعتبر. لطفاً یک ID معتبر وارد کنید (مثال: 12345)")
    except sqlite3.Error as e:
        logger.error(f"Database error in reset approved count: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Error in reset approved count: {e}")
        await message.reply("❌ خطایی رخ داد.")

# Start command
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    logger.info(f"Start command from user {user_id}")
    
    if not is_bot_active():
        await message.reply("❌ ربات در حال حاضر غیرفعال است.")
        return
    
    # بررسی عضویت
    is_member, channel_name, invite_link = await check_membership(client, user_id)
    
    if not is_member:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"عضویت در {channel_name}", url=invite_link)],
            [InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")]
        ])
        await message.reply(
            f"❗️ برای استفاده از ربات، لطفاً ابتدا در کانال {channel_name} عضو شوید.",
            reply_markup=keyboard
        )
        set_user_state(user_id, "awaiting_membership")
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
        [InlineKeyboardButton("📤 ارسال شماره", callback_data="submit_content"),
        InlineKeyboardButton("📋 پروفایل من", callback_data="my_profile")],
        [InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data="edit_profile"),
        InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
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
                [InlineKeyboardButton(f"👥 کاربران ({user_count})", callback_data="view_users"),
                InlineKeyboardButton(f"🤖 وضعیت ربات: {bot_status}", callback_data="toggle_bot")],

                [InlineKeyboardButton("💸 مدیریت موجودی", callback_data="manage_balances"),
                InlineKeyboardButton("🔄 صفر کردن تعداد تأیید شده‌ها", callback_data="reset_approved_count")],

                [InlineKeyboardButton("📨 پیام‌های پشتیبانی", callback_data="view_support"),
                InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="broadcast_message")],
                [InlineKeyboardButton("📩 ارسال پیام شخصی", callback_data="private_message")]
            ])
            
            await message.reply("🔧 پنل ادمین", reply_markup=keyboard)
    except sqlite3.Error as e:
        logger.error(f"Database error in admin panel: {e}")
        await message.reply("❌ خطای پایگاه داده.")

async def handle_broadcast_message(client, callback_query):
    await callback_query.message.reply("📢 لطفاً متن پیام همگانی را وارد کنید:")
    set_user_state(callback_query.from_user.id, "waiting_for_broadcast")
    await callback_query.answer()

async def handle_private_message(client, callback_query):
    await callback_query.message.reply(
        "📩 لطفاً شناسه کاربر (ID) یا نام کامل (نام و نام خانوادگی) را وارد کنید:"
    )
    set_user_state(callback_query.from_user.id, "waiting_for_private_user")
    await callback_query.answer()

async def handle_broadcast(client, message):
    admin_id = message.from_user.id
    if get_user_state(admin_id) != "waiting_for_broadcast":
        return

    try:
        broadcast_text = message.text.strip()
        if not broadcast_text:
            await message.reply("❌ متن پیام نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
            return

        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()

        success_count = 0
        for user in users:
            try:
                await client.send_message(user[0], f"📢 اطلاعیه:\n\n{broadcast_text}")
                success_count += 1
                logger.info(f"Broadcast sent to user {user[0]}")
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user[0]}: {e}")

        await message.reply(f"✅ پیام همگانی به {success_count} کاربر ارسال شد.")
        clear_user_state(admin_id)

    except sqlite3.Error as e:
        logger.error(f"Database error in broadcast: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Error in broadcast: {e}")
        await message.reply("❌ خطا در ارسال پیام همگانی.")

async def handle_private_user(client, message):
    admin_id = message.from_user.id
    if get_user_state(admin_id) != "waiting_for_private_user":
        return

    try:
        user_input = message.text.strip()
        target_user_id = None

        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            # بررسی اگر ورودی ID عددی است
            try:
                target_user_id = int(user_input)
                c.execute("SELECT user_id FROM users WHERE user_id = ?", (target_user_id,))
                if not c.fetchone():
                    await message.reply(f"❌ کاربر با شناسه {target_user_id} یافت نشد.")
                    return
            except ValueError:
                # جستجو بر اساس نام
                name_parts = user_input.split()
                if len(name_parts) < 2:
                    await message.reply("❌ لطفاً نام کامل (نام و نام خانوادگی) را وارد کنید.")
                    return
                
                first_name, last_name = name_parts[0], " ".join(name_parts[1:])
                c.execute(
                    "SELECT user_id FROM users WHERE first_name = ? AND last_name = ?",
                    (first_name, last_name)
                )
                user = c.fetchone()
                if not user:
                    await message.reply(f"❌ کاربر با نام {user_input} یافت نشد.")
                    return
                target_user_id = user[0]

        await message.reply("📩 لطفاً متن پیام را وارد کنید:")
        set_user_state(admin_id, "waiting_for_private_message", {"target_user_id": target_user_id})

    except sqlite3.Error as e:
        logger.error(f"Database error in private user: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Error in private user: {e}")
        await message.reply("❌ خطا در پردازش.")

async def handle_private_message_send(client, message):
    admin_id = message.from_user.id
    state = get_user_state(admin_id)
    state_data = get_state_data(admin_id)

    if state != "waiting_for_private_message" or not state_data:
        return

    try:
        target_user_id = state_data["target_user_id"]
        message_text = message.text.strip()

        if not message_text:
            await message.reply("❌ متن پیام نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
            return

        # ارسال پیام به کاربر
        try:
            await client.send_message(target_user_id, f"📩 پیام از ادمین:\n\n{message_text}")
            await message.reply(f"✅ پیام به کاربر {target_user_id} ارسال شد.")
            logger.info(f"Private message sent to user {target_user_id}")
        except Exception as e:
            logger.error(f"Failed to send private message to user {target_user_id}: {e}")
            await message.reply(f"❌ خطا در ارسال پیام به کاربر {target_user_id}.")

        clear_user_state(admin_id)

    except Exception as e:
        logger.error(f"Error in private message send: {e}")
        await message.reply("❌ خطا در ارسال پیام.")

# Callback query handler
@app.on_callback_query()
async def handle_callback(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    try:
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
        elif data == "broadcast_message" and user_id == ADMIN_ID:
            await handle_broadcast_message(client, callback_query)
        elif data == "private_message" and user_id == ADMIN_ID:
            await handle_private_message(client, callback_query)
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
        elif data == "edit_group_leader":
            await callback_query.message.reply("✏️ لطفاً نام سرگروه جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_group_leader")
        elif data == "edit_card_or_wallet":
            await callback_query.message.reply("💳 لطفاً شماره کارت یا آدرس کیف پول جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_card_or_wallet")
        elif data == "edit_sheba":
            await callback_query.message.reply("🏦 لطفاً شماره شبا جدید خود را وارد کنید:")
            set_user_state(user_id, "editing_sheba")
        elif data == "reset_approved_count" and user_id == ADMIN_ID:
            await handle_reset_approved_count(client, callback_query)

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
                [InlineKeyboardButton("✏️ ویرایش نام سرگروه", callback_data="edit_group_leader")],
                [InlineKeyboardButton("💳 ویرایش شماره کارت یا آدرس کیف پول", callback_data="edit_card_or_wallet")],
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
    user_id = callback_query.from_user.id
    try:
        await callback_query.message.reply("📤 لطفاً لیست شماره های خود را ارسال کنید.\n"
                                           "(توجه لیست شما باید شماره های سالم و چک شده باشد همچنین کمتر از 50 شماره و بیشتر از 100 شماره در یک لیست تایید نخواهد شد.)❌")
        set_user_state(user_id, "waiting_for_content")
        await callback_query.answer()  # پاسخ به callback
    except Exception as e:
        logger.error(f"Error in submit content callback: {e}")
        # فقط اگر خطا مربوط به callback نباشد، پاسخ دهیم
        if "QUERY_ID_INVALID" not in str(e):
            try:
                await callback_query.answer("❌ خطا در پردازش ارسال شماره", show_alert=True)
            except Exception as inner_e:
                logger.error(f"Failed to send error response for submit_content: {inner_e}")
        # ارسال پیام خطا به کاربر
        try:
            await callback_query.message.reply("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception as reply_e:
            logger.error(f"Failed to reply to user {user_id}: {reply_e}")

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
                    f"نام سرگروه: {user[5] or 'مشخص نشده'}\n"
                    f"شماره کارت یا آدرس کیف پول: {user[3] or 'مشخص نشده'}\n"
                    f"شماره شبا: {user[4] or 'مشخص نشده'}\n"
                    f"موجودی: {user[6]:,.0f} تومان\n"
                    f"تعداد شماره تایید شده: {user[7]}\n"
                    f"تاریخ ثبت نام: {user[8]}"
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
            # await show_admin_panel(callback_query.message)
            
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
            # تغییر approved_numbers به approved_count
            c.execute("SELECT user_id, first_name, last_name, approved_count, balance FROM users")
            users = c.fetchall()
            
            if not users:
                await callback_query.message.reply("❌ کاربری یافت نشد.")
                return
            
            users_text = "👥 لیست کاربران:\n\n"
            for user in users:
                users_text += (
                    f"🆔 ID: `{user[0]}`\n"
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
        action, submission_id = callback_query.data.split("_")
        submission_id = int(submission_id)
        admin_id = callback_query.from_user.id

        if admin_id != ADMIN_ID:
            await callback_query.answer("❌ شما مجاز به انجام این عملیات نیستید.", show_alert=True)
            logger.warning(f"Unauthorized approval attempt by user {admin_id}")
            return

        with sqlite3.connect("bot_db.db") as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, content, content_type, status FROM submissions WHERE id = ?", (submission_id,))
            submission = c.fetchone()

            if not submission:
                await callback_query.answer("❌ شماره یافت نشد.", show_alert=True)
                logger.warning(f"Submission {submission_id} not found")
                return

            user_id, content, content_type, status = submission

            if status != "pending":
                await callback_query.answer(f"❌ این شماره قبلاً {status} شده است.", show_alert=True)
                logger.warning(f"Attempt to modify non-pending submission {submission_id}")
                return

            if action == "approve":
                # درخواست تعداد آیتم‌های تأییدشده
                await callback_query.message.reply(
                    "✅ لطفاً تعداد آیتم‌های تأییدشده را وارد کنید:\n"
                    "مثال: 90"
                )
                set_user_state(admin_id, "waiting_for_approval_details", {"submission_id": submission_id, "user_id": user_id})
                await callback_query.answer()
                return

            elif action == "reject":
                # به‌روزرسانی وضعیت شماره
                c.execute("UPDATE submissions SET status = 'rejected' WHERE id = ?", (submission_id,))
                conn.commit()
                logger.info(f"Submission {submission_id} rejected for user {user_id}")

                # اطلاع به کاربر
                try:
                    if content_type == "text":
                        await client.send_message(user_id, f"❌ لیست شما رد شد:\n\n{content}")
                    else:
                        await client.send_photo(user_id, photo=content, caption="❌ عکس شما رد شد!")
                    logger.info(f"User {user_id} notified of rejection for submission {submission_id}")
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id} of rejection: {e}")
                    await client.send_message(ADMIN_ID, f"❌ خطا در اطلاع‌رسانی به کاربر {user_id} برای رد شماره {submission_id}")

                await callback_query.message.edit_text(f"❌ لیست کاربر {user_id} رد شد (ID: {submission_id})")
                await callback_query.answer("❌ شماره رد شد.", show_alert=True)

    except sqlite3.Error as e:
        logger.error(f"Database error in approval process: {e}")
        await callback_query.answer("❌ خطای پایگاه داده.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in approval process: {e}")
        await callback_query.answer("❌ خطا در پردازش.", show_alert=True)

async def handle_approval_details(client, message):
    admin_id = message.from_user.id
    state = get_user_state(admin_id)
    state_data = get_state_data(admin_id)

    if state != "waiting_for_approval_details" or not state_data:
        return

    try:
        submission_id = state_data["submission_id"]
        user_id = state_data["user_id"]

        # دریافت تعداد آیتم‌های تأییدشده
        approved_items = message.text.strip()
        
        # اعتبارسنجی ورودی
        try:
            approved_items = int(approved_items)
            if approved_items < 0:
                await message.reply("❌ تعداد تأییدشده نمی‌تواند منفی باشد. لطفاً عدد معتبر وارد کنید:")
                return
        except ValueError:
            await message.reply("❌ فرمت نامعتبر. لطفاً یک عدد معتبر وارد کنید (مثال: 90):")
            return

        with sqlite3.connect("bot_db.db") as conn:
            c = conn.cursor()
            # به‌روزرسانی وضعیت شماره
            c.execute("UPDATE submissions SET status = 'approved' WHERE id = ?", (submission_id,))
            # ذخیره تعداد آیتم‌های تأییدشده (بدون total_items)
            c.execute(
                "INSERT INTO submission_details (submission_id, approved_items) VALUES (?, ?)",
                (submission_id, approved_items)
            )
            # به‌روزرسانی تعداد کل تأییدشده‌های کاربر
            c.execute(
                "UPDATE users SET approved_count = approved_count + ? WHERE user_id = ?",
                (approved_items, user_id)
            )
            conn.commit()
            logger.info(f"Submission {submission_id} approved with {approved_items} items for user {user_id}")

        # دریافت نوع شماره و شماره
        c.execute("SELECT content_type, content FROM submissions WHERE id = ?", (submission_id,))
        content_type, content = c.fetchone()

        # اطلاع به کاربر
        try:
            if content_type == "text":
                await client.send_message(
                    user_id,
                    f"✅ لیست شما تأیید شد:\n\n{content}\n\nتعداد تأییدشده: {approved_items}"
                )
            else:
                await client.send_photo(
                    user_id,
                    photo=content,
                    caption=f"✅ عکس شما تأیید شد!\n\nتعداد تأییدشده: {approved_items}"
                )
            logger.info(f"User {user_id} notified of approval for submission {submission_id}")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
            await client.send_message(ADMIN_ID, f"❌ خطا در اطلاع‌رسانی به کاربر {user_id}")

        # ارسال پیام جدید به ادمین
        try:
            await message.reply(
                f"✅ لیست کاربر {user_id} تأیید شد (ID: {submission_id})\nتعداد تأییدشده: {approved_items}",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Failed to send admin message: {e}")

        clear_user_state(admin_id)

    except sqlite3.Error as e:
        logger.error(f"Database error in approval details: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Error in approval details: {e}")
        await message.reply("❌ خطا در پردازش.")

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
        elif state == "waiting_for_group_leader":
            await handle_group_leader(message)
        elif state == "waiting_for_card_or_wallet":
            await handle_card_or_wallet(message)
        elif state == "waiting_for_sheba":
            await handle_sheba_number(message)
        
        # Edit states
        elif state == "editing_first_name":
            await handle_first_name(message, edit_mode=True)
        elif state == "editing_last_name":
            await handle_last_name(message, edit_mode=True)
        elif state == "editing_group_leader":
            await handle_group_leader(message, edit_mode=True)
        elif state == "editing_card_or_wallet":
            await handle_card_or_wallet(message, edit_mode=True)
        elif state == "editing_sheba":
            await handle_sheba_number(message, edit_mode=True)
        
        # Content submission
        elif state == "waiting_for_content":
            await handle_content_submission(client, message)
        
        # Support messages
        elif state == "waiting_for_support":
            await handle_support_message(client, message)
        
        # Admin states
        elif user_id == ADMIN_ID:
            if state == "waiting_for_balance_update":
                await handle_balance_update(client, message)
            elif state == "waiting_for_reply":
                await handle_admin_reply(client, message)
            elif state == "waiting_for_broadcast":
                await handle_broadcast(client, message)
            elif state == "waiting_for_private_user":
                await handle_private_user(client, message)
            elif state == "waiting_for_private_message":
                await handle_private_message_send(client, message)
            elif state == "waiting_for_approval_details":
                await handle_approval_details(client, message)
            elif state == "waiting_for_reset_approved":
                await handle_reset_approved_count_process(client, message)

    except Exception as e:
        logger.error(f"Error in message handler for user {user_id}, state {state}: {e}")
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
                await message.reply("👤 لطفاً نام سرگروه خود را وارد کنید:")
                set_user_state(message.from_user.id, "waiting_for_group_leader")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in last name: {e}")
        await message.reply("❌ خطای پایگاه داده.")

async def handle_group_leader(message, edit_mode=False):
    group_leader_name = message.text.strip()
    if not group_leader_name:
        await message.reply("❌ نام سرگروه نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
        return
    
    user_id = message.from_user.id
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            # بررسی وجود کاربر
            c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not c.fetchone():
                await message.reply("❌ کاربر یافت نشد. لطفاً ابتدا ثبت‌نام کنید.")
                clear_user_state(user_id)
                logger.error(f"User {user_id} not found in database for group_leader update")
                return
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET group_leader_name = ? WHERE user_id = ?",
                    (group_leader_name, user_id)
                )
                conn.commit()
                await message.reply("✅ نام سرگروه شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(user_id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET group_leader_name = ? WHERE user_id = ?",
                    (group_leader_name, user_id)
                )
                conn.commit()
                await message.reply("💳 لطفاً شماره کارت یا آدرس کیف پول خود را وارد کنید:")
                set_user_state(user_id, "waiting_for_card_or_wallet")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in group_leader for user {user_id}: {e}")
        await message.reply("❌ خطای پایگاه داده رخ داد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.")
    except Exception as e:
        logger.error(f"Unexpected error in group_leader for user {user_id}: {e}")
        await message.reply("❌ خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.")

async def handle_card_or_wallet(message, edit_mode=False):
    card_or_wallet = message.text.strip()
    if not card_or_wallet:
        await message.reply("❌ شماره کارت یا آدرس کیف پول نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید:")
        return
    
    try:
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            
            if edit_mode:
                c.execute(
                    "UPDATE users SET card_or_wallet = ? WHERE user_id = ?",
                    (card_or_wallet, message.from_user.id)
                )
                conn.commit()
                await message.reply("✅ شماره کارت یا آدرس کیف پول شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET card_or_wallet = ? WHERE user_id = ?",
                    (card_or_wallet, message.from_user.id)
                )
                conn.commit()
                await message.reply("🏦 لطفاً شماره شبا خود را وارد کنید:")
                set_user_state(message.from_user.id, "waiting_for_sheba")
                
    except sqlite3.Error as e:
        logger.error(f"Database error in card_or_wallet for user {message.from_user.id}: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Unexpected error in card_or_wallet for user {message.from_user.id}: {e}")
        await message.reply("❌ خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.")

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
                    (sheba_number, message.from_user.id)
                )
                conn.commit()
                await message.reply("✅ شماره شبا شما با موفقیت به‌روزرسانی شد.")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
            else:
                c.execute(
                    "UPDATE users SET sheba_number = ? WHERE user_id = ?",
                    (sheba_number, message.from_user.id)
                )
                conn.commit()
                await message.reply("✅ ثبت نام شما با موفقیت انجام شد!")
                clear_user_state(message.from_user.id)
                await show_main_menu(message)
                
    except sqlite3.Error as e:
        logger.error(f"Database error in sheba_number for user {message.from_user.id}: {e}")
        await message.reply("❌ خطای پایگاه داده.")
    except Exception as e:
        logger.error(f"Unexpected error in sheba_number for user {message.from_user.id}: {e}")
        await message.reply("❌ خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.")

# Content submission handler
async def handle_content_submission(client, message):
    user_id = message.from_user.id
    if get_user_state(user_id) != "waiting_for_content":
        return

    try:
        # بررسی نوع شماره
        content = None
        content_type = None
        if message.text:
            content = message.text.strip()
            content_type = "text"
            if not content:
                await message.reply("❌ متن نمی‌تواند خالی باشد. لطفاً لیست خود را وارد کنید:")
                logger.warning(f"Empty text content attempt by user {user_id}")
                return
        elif message.photo:
            content = message.photo.file_id
            content_type = "photo"
        else:
            await message.reply("❌ نوع لیست ارسالی پشتیبانی نمی‌شود. لطفاً متن یا عکس ارسال کنید.")
            logger.warning(f"Unsupported content type by user {user_id}")
            return

        # ثبت شماره در پایگاه داده
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO submissions (user_id, content, content_type, submitted_at, status) VALUES (?, ?, ?, ?, ?)",
                (user_id, content, content_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending")
            )
            submission_id = c.lastrowid
            conn.commit()
            logger.info(f"Content submission {submission_id} from user {user_id} stored")

        # پاسخ به کاربر
        await message.reply("✅ لیست شما با موفقیت ارسال شد و در انتظار تأیید است.")
        clear_user_state(user_id)

        # دریافت نام کاربر برای نمایش در پیام ادمین
        with sqlite3.connect('bot_db.db') as conn:
            c = conn.cursor()
            c.execute("SELECT first_name, last_name FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
            user_name = f"{user[0]} {user[1]}" if user else "ناشناس"

        # ارسال به ادمین
        try:
            if content_type == "text":
                await client.send_message(
                    ADMIN_ID,
                    f"📨 لیست جدید از کاربر {user_name} (ID: {user_id}, Submission ID: {submission_id}):\n\n{content}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{submission_id}")],
                        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{submission_id}")]
                    ])
                )
            else:
                await client.send_photo(
                    ADMIN_ID,
                    photo=content,
                    caption=f"📸 عکس جدید از کاربر {user_name} (ID: {user_id}, Submission ID: {submission_id})",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{submission_id}")],
                        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{submission_id}")]
                    ])
                )
            logger.info(f"Content submission {submission_id} sent to admin")
        except Exception as e:
            logger.error(f"Failed to send content to admin: {e}")
            await client.send_message(user_id, "❌ خطا در ارسال شماره به ادمین. لطفاً دوباره تلاش کنید.")
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
        await message.reply("❌ خطا در ارسال شماره.")

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
            
            # بررسی وجود کاربر
            c.execute("SELECT user_id FROM users WHERE user_id = ?", (target_user_id,))
            if not c.fetchone():
                await message.reply(f"❌ کاربر با شناسه {target_user_id} یافت نشد.")
                return
            
            # اگر موجودی صفر شود، تعداد تأیید شده‌ها نیز صفر شود
            if new_balance == 0:
                c.execute(
                    "UPDATE users SET balance = ?, approved_count = 0 WHERE user_id = ?",
                    (new_balance, target_user_id)
                )
            else:
                c.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (new_balance, target_user_id)
                )
            conn.commit()
        
        balance_message = f"✅ موجودی کاربر {target_user_id} به {new_balance:,.0f} تومان به‌روزرسانی شد."
        if new_balance == 0:
            balance_message += f"\n✅ تعداد تأیید شده‌های کاربر نیز صفر شد."
        await message.reply(balance_message)
        clear_user_state(message.from_user.id)
        
        # اطلاع‌رسانی به کاربر
        try:
            user_message = f"💰 موجودی حساب شما به {new_balance:,.0f} تومان به‌روزرسانی شد."
            if new_balance == 0:
                user_message += "\n🔄 تعداد تأیید شده‌های شما نیز صفر شد."
            await client.send_message(target_user_id, user_message)
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
    init_db()
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    logger.info("Starting bot...")
    app.run()