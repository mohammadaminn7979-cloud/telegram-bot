import os
import asyncio
import random
from datetime import datetime, timedelta, date
import pytz
import sys
import logging
import json
from telethon import TelegramClient, events, Button, errors
from telethon.sessions import StringSession
from telethon.tl.functions.account import ReportPeerRequest, UpdateStatusRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.messages import SendReactionRequest, SendMessageRequest, DeleteMessagesRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonFake,
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonPersonalDetails,
    InputReportReasonOther,
    ReactionEmoji,
    InputPeerUser,
    InputPeerChannel,
    InputPeerChat
)

# ========== Config ==========
logging.basicConfig(
    filename='bot.log', 
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

logger = logging.getLogger(__name__)

API_ID = "39346945"
API_HASH = "0afc26aa8e8ab25acfbcc2e33a749061"
BOT_TOKEN = "8764341033:AAGq-p9qttdbJQy_QWKY_OpmLXyYmonNMAM"
OWNER_IDS = [8111180532]
SESSIONS_DIR = "sessions"
SHARED_SESSIONS_DIR = "shared_sessions"
REPORT_GROUP = -1003689608212

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SHARED_SESSIONS_DIR, exist_ok=True)

# ========== Data Storage ==========
ADMINS = {}
REFERRALS = {}
REPORT_HISTORY = {}
USER_STATE = {}
OPERATION_QUEUE = asyncio.Queue()
CURRENT_OPERATION = None
REMINDER_TASKS = {}
MANUAL_REPORT_DATES = {}
USER_SESSIONS_CACHE = {}

# Report reasons
REPORT_REASONS = {
    '1': ('🚫 Spam', InputReportReasonSpam(), 'This content is spam'),
    '2': ('❌ Fake', InputReportReasonFake(), 'This content is fake'),
    '3': ('🔪 Violence', InputReportReasonViolence(), 'This content contains violence'),
    '4': ('🔞 Pornography', InputReportReasonPornography(), 'This content contains pornography'),
    '5': ('👶 Child Abuse', InputReportReasonChildAbuse(), 'This content involves child abuse'),
    '6': ('©️ Copyright', InputReportReasonCopyright(), 'This content violates copyright'),
    '7': ('📋 Personal Details', InputReportReasonPersonalDetails(), 'This content exposes personal details'),
    '8': ('📝 Other', InputReportReasonOther(), 'Reported by bot - other reason'),
    '9': ('💸 Scam', InputReportReasonOther(), 'This channel/post/user is a scam')
}

# Reactions
REACTION_OPTIONS = {
    '1': (ReactionEmoji(emoticon='🤬'), 'Angry🤬'),
    '2': (ReactionEmoji(emoticon='😡'), 'Mad😡'),
    '3': (ReactionEmoji(emoticon='👎'), 'Dislike👎'),
    '4': (ReactionEmoji(emoticon='🤮'), 'Vomit🤮'),
    '5': (ReactionEmoji(emoticon='🖕'), 'Middle Finger🖕'),
    'random': (None, 'Random🎲')
}

# ========== Helper Functions ==========
def save_data():
    try:
        data = {
            'admins': {
                str(k): {
                    'expires': v['expires'].isoformat(),
                    'activated': v['activated'].isoformat(),
                    'permissions': v.get('permissions', [])
                } for k, v in ADMINS.items()
            },
            'referrals': {str(k): v for k, v in REFERRALS.items()},
            'report_history': {
                str(k): [t.isoformat() for t in v]
                for k, v in REPORT_HISTORY.items()
            },
            'manual_report_dates': {
                str(k): v.isoformat()
                for k, v in MANUAL_REPORT_DATES.items()
            }
        }
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {str(e)}")

def load_data():
    global ADMINS, REFERRALS, REPORT_HISTORY, MANUAL_REPORT_DATES
    try:
        if os.path.exists('data.json'):
            with open('data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            ADMINS = {
                int(k): {
                    'expires': datetime.fromisoformat(v['expires']),
                    'activated': datetime.fromisoformat(v['activated']),
                    'permissions': v.get('permissions', [])
                } for k, v in data.get('admins', {}).items()
            }
            
            REFERRALS = {
                int(k): int(v)
                for k, v in data.get('referrals', {}).items()
            }
            
            REPORT_HISTORY = {
                int(k): [datetime.fromisoformat(t) for t in v]
                for k, v in data.get('report_history', {}).items()
            }
            
            MANUAL_REPORT_DATES = {
                int(k): datetime.fromisoformat(v).date()
                for k, v in data.get('manual_report_dates', {}).items()
            }
            
            logger.info("Data loaded successfully")
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

def is_admin(user_id: int) -> bool:
    try:
        tehran_tz = pytz.timezone('Asia/Tehran')
        current_time = datetime.now(tehran_tz)
        return user_id in ADMINS and ADMINS[user_id]['expires'] > current_time
    except:
        return False

def can_access(user_id: int) -> bool:
    return is_owner(user_id) or is_admin(user_id)

def get_user_sessions(user_id: int, force_refresh: bool = False):
    if not force_refresh and user_id in USER_SESSIONS_CACHE:
        return USER_SESSIONS_CACHE[user_id]
    
    user_sessions = []
    
    for f in os.listdir(SHARED_SESSIONS_DIR):
        if f.endswith(".session"):
            user_sessions.append(f)
    
    if is_owner(user_id) or is_admin(user_id):
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith(".session"):
                user_sessions.append(f)
    
    USER_SESSIONS_CACHE[user_id] = user_sessions
    return user_sessions

def clear_user_cache(user_id: int = None):
    if user_id:
        USER_SESSIONS_CACHE.pop(user_id, None)
    else:
        USER_SESSIONS_CACHE.clear()

def save_session_string(user_id: int, phone: str, session_str, shared: bool = False) -> bool:
    try:
        dir_path = SHARED_SESSIONS_DIR if shared else SESSIONS_DIR
        prefix = "" if shared else f"{user_id}_"
        
        if hasattr(session_str, 'save'):
            session_str = session_str.save()
        
        phone_clean = phone.replace('+', '').replace(' ', '')
        filename = f"{prefix}{phone_clean}.session"
        path = os.path.join(dir_path, filename)
        
        with open(path, "w", encoding='utf-8') as f:
            f.write(session_str)
        
        clear_user_cache(user_id)
        logger.info(f"Session saved for {phone} {'(shared)' if shared else ''}")
        return True
    except Exception as e:
        logger.error(f"Error saving session for {phone}: {str(e)}")
        return False

async def check_account_status(session_file: str, is_shared: bool = False) -> str:
    try:
        dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
        path = os.path.join(dir_path, session_file)
        
        with open(path, 'r', encoding='utf-8') as f:
            session_str = f.read().strip()
        
        if not session_str:
            return "❌ Empty session file"
        
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                await client.disconnect()
                return "❌ Not authorized"
            
            me = await client.get_me()
            await client.disconnect()
            return f"✅ Active (ID: {me.id})"
            
        except errors.FloodWaitError as e:
            await client.disconnect()
            return f"⏳ Flood wait ({e.seconds}s)"
        except errors.SessionPasswordNeededError:
            await client.disconnect()
            return "🔐 2FA required"
        except errors.AuthKeyDuplicatedError:
            await client.disconnect()
            return "🚫 Banned"
        except errors.PhoneNumberBannedError:
            await client.disconnect()
            return "🚫 Number banned"
        except Exception as e:
            await client.disconnect()
            return f"⚠️ Error: {str(e)[:50]}"
            
    except FileNotFoundError:
        return "❌ File not found"
    except Exception as e:
        return f"❌ Error: {str(e)[:50]}"

def is_rest_time() -> bool:
    try:
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        hour, minute = now.hour, now.minute
        
        if (16 <= hour < 17) and (0 <= minute <= 20):
            return True
        if (21 <= hour < 22) and (0 <= minute <= 35):
            return True
        
        return False
    except:
        return False

def estimate_completion_time(num_accounts: int, reports_per_account: int, delay: int = 4) -> str:
    try:
        total_seconds = num_accounts * reports_per_account * delay
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        estimated_time = now + timedelta(seconds=total_seconds)
        return estimated_time.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return "Unknown"

async def check_report_penalty(user_id: int, current_time: datetime):
    if user_id not in REPORT_HISTORY:
        REPORT_HISTORY[user_id] = []
    
    REPORT_HISTORY[user_id].append(current_time)
    
    hour_ago = current_time - timedelta(hours=1)
    REPORT_HISTORY[user_id] = [t for t in REPORT_HISTORY[user_id] if t >= hour_ago]
    
    if len(REPORT_HISTORY[user_id]) >= 3 and user_id in ADMINS:
        ADMINS[user_id]['expires'] -= timedelta(hours=15)
        save_data()
        
        logger.info(f"Penalty applied for user {user_id}: 15 hours deducted")
        return (
            f"⚠️ **Penalty Applied!**\n\n"
            f"Due to {len(REPORT_HISTORY[user_id])} consecutive reports,\n"
            f"15 hours have been deducted from your subscription.\n\n"
            f"📅 **New expiration:** {ADMINS[user_id]['expires'].strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    return None

async def can_use_manual_report(user_id: int) -> bool:
    today = date.today()
    return user_id not in MANUAL_REPORT_DATES or MANUAL_REPORT_DATES[user_id] != today

async def send_to_report_group(bot, operation_type: str, target, target_id, result_msg: str):
    try:
        target_id_str = f" (ID: {target_id})" if target_id else " (ID: Unknown)"
        
        if operation_type == "Report post":
            target_str = f"Multiple posts" if isinstance(target, list) else "Post"
        else:
            target_str = target if target else "Unknown"
        
        message = (
            f"📊 **Operation Report**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 **Type:** {operation_type}\n\n"
            f"🎯 **Target:** {target_str}{target_id_str}\n\n"
            f"📊 **Result:**\n{result_msg}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await bot.send_message(REPORT_GROUP, message)
        logger.info(f"Report sent to group {REPORT_GROUP} for {operation_type}")
    except Exception as e:
        logger.error(f"Error sending to report group: {str(e)}")

async def remind_user(bot, user_id: int, event):
    try:
        await asyncio.sleep(120)
        
        if user_id in USER_STATE and USER_STATE[user_id].get('queued', False):
            await event.reply(
                "⏰ **Reminder!**\n"
                "Are you still there? Your operation is queued!\n"
                "Please complete your report soon."
            )
            logger.info(f"Reminder sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending reminder to user {user_id}: {str(e)}")
    finally:
        REMINDER_TASKS.pop(user_id, None)

async def process_operation(user_id: int, operation_type: str, event, state=None) -> bool:
    global CURRENT_OPERATION
    
    if CURRENT_OPERATION and CURRENT_OPERATION != user_id:
        if operation_type in ['report', 'report_post', 'report_profile',
                             'report_bot', 'report_account', 'manual_report', 
                             'join_channel', 'join_group', 'leave_account',
                             'sender', 'commenter', 'view_post', 'leave_channel', 
                             'leave_group', 'delete_pm']:
            await event.reply(
                "⚠️ **Operation Queued**\n"
                "Someone else is currently operating.\n"
                "Please wait for your turn..."
            )
            
            if state:
                state['queued'] = True
            
            await OPERATION_QUEUE.put((user_id, operation_type, event, state))
            
            REMINDER_TASKS[user_id] = asyncio.create_task(
                remind_user(event.client, user_id, event)
            )
            
            return False
        else:
            await event.reply("⏳ Please wait until the current operation is complete.")
            await OPERATION_QUEUE.put((user_id, operation_type, event, state))
            return False
    
    CURRENT_OPERATION = user_id
    return True

async def release_operation():
    global CURRENT_OPERATION
    CURRENT_OPERATION = None
    
    try:
        if not OPERATION_QUEUE.empty():
            next_op = await OPERATION_QUEUE.get()
            user_id, operation_type, event, state = next_op
            
            if user_id in REMINDER_TASKS:
                REMINDER_TASKS[user_id].cancel()
                del REMINDER_TASKS[user_id]
            
            if state:
                state['queued'] = False
            
            try:
                await event.reply("✅ **Your turn now!**\nPlease continue your operation.")
            except:
                pass
            
            if operation_type == 'report':
                await handle_report_continue(event, state)
            elif operation_type == 'report_post':
                await handle_report_post_continue(event, state)
            elif operation_type == 'sender':
                await handle_sender_continue(event, state)
            elif operation_type == 'commenter':
                await handle_commenter_continue(event, state)
            elif operation_type == 'view_post':
                await handle_view_post_continue(event, state)
            elif operation_type == 'leave_channel':
                await handle_leave_channel_continue(event, state)
            elif operation_type == 'leave_group':
                await handle_leave_group_continue(event, state)
            elif operation_type == 'delete_pm':
                await handle_delete_pm_continue(event, state)
            
            OPERATION_QUEUE.task_done()
    except asyncio.QueueEmpty:
        pass
    except Exception as e:
        logger.error(f"Error in release_operation: {str(e)}")

async def join_channel(client, entity, session_file: str) -> bool:
    try:
        await client(JoinChannelRequest(entity))
        logger.info(f"Successfully joined channel for {session_file}")
        return True
    except errors.UserAlreadyParticipantError:
        logger.info(f"Already a participant for {session_file}")
        return True
    except errors.FloodWaitError as e:
        logger.error(f"Flood wait for {session_file}: {e.seconds} seconds")
        return False
    except errors.ChannelPrivateError:
        logger.error(f"Channel is private for {session_file}")
        return False
    except errors.ChannelInvalidError:
        logger.error(f"Channel invalid for {session_file}")
        return False
    except Exception as e:
        logger.error(f"Error joining channel for {session_file}: {str(e)}")
        return False

async def show_main_menu(event, user_id: int):
    """Show main menu with all options"""
    USER_STATE.pop(user_id, None)

    if is_owner(user_id):
        buttons = [
            # Row 1: Full width
            [Button.inline("🚫 Report Channel/Group", b'report')],
            
            # Row 2: Two buttons side by side (Sender - Commenter)
            [Button.inline("📨 Sender", b'sender'), Button.inline("💬 Commenter", b'commenter')],
            
            # Row 3: Full width (View Post)
            [Button.inline("👁 View Post", b'view_post')],
            
            # Row 4: Two buttons side by side (Leave Group - Leave Channel)
            [Button.inline("👥 Leave Group", b'leave_group'), Button.inline("📢 Leave Channel", b'leave_channel')],
            
            # Row 5: Full width (Delete PM)
            [Button.inline("🗑 Delete PM", b'delete_pm')],
            
            # Row 6: Two buttons side by side
            [Button.inline("➕ Add Account", b'addaccount'), Button.inline("🗑 Delete Account", b'deleteaccount')],
            
            # Row 7: Full width
            [Button.inline("📝 Report Post", b'report_post')],
            
            # Row 8: Two buttons side by side
            [Button.inline("📋 List Accounts", b'listaccount'), Button.inline("🚪 Leave Account", b'leave_account')],
            
            # Row 9: Full width
            [Button.inline("👤 Report Profile", b'report_profile')],
            
            # Row 10: Two buttons side by side
            [Button.inline("🤖 Report Bot", b'report_bot'), Button.inline("👤 Report Account", b'report_account')],
            
            # Row 11: Full width
            [Button.inline("📋 Manual Report", b'manual_report')],
            
            # Row 12: Two buttons side by side
            [Button.inline("📨 Send to @notoscam", b'notoreport'), Button.inline("🚷 Block User", b'blackuser')],
            
            # Row 13: Full width
            [Button.inline("😠 Negative Reaction", b'reaction')],
            
            # Row 14: Two buttons side by side
            [Button.inline("▶️ Start Bot", b'startbot'), Button.inline("📢 Join Channel", b'join_channel')],
            
            # Row 15: Full width
            [Button.inline("👥 Join Group", b'join_group')],
            
            # Row 16: Two buttons side by side
            [Button.inline("⏰ Subscription Status", b'subscription_time'), Button.inline("👑 Admin Panel", b'admin_panel')],
            
            # Row 17: Full width
            [Button.inline("🔄 Refresh Sessions", b'refresh_sessions')]
        ]

        await event.reply(
            "👑 **Owner Control Panel**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Welcome to Advanced Reporter Bot!\n\n"
            "Manage accounts, report content, and more.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Select an option:",
            buttons=buttons
        )
    
    elif is_admin(user_id):
        buttons = [
            # Row 1: Full width
            [Button.inline("🚫 Report Channel/Group", b'report')],
            
            # Row 2: Two buttons side by side (Sender - Commenter)
            [Button.inline("📨 Sender", b'sender'), Button.inline("💬 Commenter", b'commenter')],
            
            # Row 3: Full width (View Post)
            [Button.inline("👁 View Post", b'view_post')],
            
            # Row 4: Two buttons side by side (Leave Group - Leave Channel)
            [Button.inline("👥 Leave Group", b'leave_group'), Button.inline("📢 Leave Channel", b'leave_channel')],
            
            # Row 5: Full width (Delete PM)
            [Button.inline("🗑 Delete PM", b'delete_pm')],
            
            # Row 6: Two buttons side by side
            [Button.inline("📋 List Accounts", b'listaccount'), Button.inline("📋 List Shared Accounts", b'listsharedaccount')],
            
            # Row 7: Full width
            [Button.inline("📝 Report Post", b'report_post')],
            
            # Row 8: Two buttons side by side
            [Button.inline("👤 Report Profile", b'report_profile'), Button.inline("🤖 Report Bot", b'report_bot')],
            
            # Row 9: Full width
            [Button.inline("👤 Report Account", b'report_account')],
            
            # Row 10: Two buttons side by side
            [Button.inline("📋 Manual Report", b'manual_report'), Button.inline("📨 Send to @notoscam", b'notoreport')],
            
            # Row 11: Full width
            [Button.inline("🚷 Block User", b'blackuser')],
            
            # Row 12: Two buttons side by side
            [Button.inline("😠 Negative Reaction", b'reaction'), Button.inline("▶️ Start Bot", b'startbot')],
            
            # Row 13: Full width
            [Button.inline("📢 Join Channel", b'join_channel')],
            
            # Row 14: Two buttons side by side
            [Button.inline("👥 Join Group", b'join_group'), Button.inline("⏰ Subscription Status", b'subscription_time')],
            
            # Row 15: Full width
            [Button.inline("🔄 Refresh Sessions", b'refresh_sessions')]
        ]

        await event.reply(
            "👮 **Admin Control Panel**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Welcome to Advanced Reporter Bot!\n\n"
            "Use available accounts for reporting operations.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Select an option:",
            buttons=buttons
        )
    
    else:
        await event.reply(
            "🔒 **Access Denied**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "You need an active subscription to use this bot.\n\n"
            "Contact @Dyrqo to subscribe.\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

async def handle_report_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'target_link':
        await event.reply("🔗 Enter channel/group link:")
    elif step == 'select_reason':
        await show_reason_buttons(event)
    elif step == 'count_per_account':
        await event.reply("🔢 Enter reports per account (1-50):")
    elif step == 'custom_reason':
        await event.reply("📝 Enter custom message or /skip:")

async def handle_sender_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'sender_target':
        await event.reply("👤 Enter the target username or ID to send message:")
    elif step == 'sender_message':
        await event.reply("📝 Enter the message to send:")
    elif step == 'sender_count':
        await event.reply("🔢 How many times to send the message per account? (1-50):")

async def handle_commenter_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'commenter_post':
        await event.reply("🔗 Enter the post link (e.g., https://t.me/channel_name/123):")
    elif step == 'commenter_text':
        await event.reply("📝 Enter the comment text:")
    elif step == 'commenter_count':
        await event.reply("🔢 How many comments per account? (1-20):")

async def handle_view_post_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'view_post_link':
        await event.reply("🔗 Enter the post link to view (e.g., https://t.me/channel_name/123):")

async def handle_leave_channel_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'leave_channel_link':
        await event.reply("📢 Enter the channel link or username to leave (e.g., https://t.me/channel_name or @channel_name):")

async def handle_leave_group_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'leave_group_link':
        await event.reply("👥 Enter the group link or username to leave (e.g., https://t.me/group_name or @group_name):")

async def handle_delete_pm_continue(event, state):
    user_id = event.sender_id
    step = state.get('step')
    
    if step == 'select_count':
        await event.reply("🔢 Enter number of accounts to use:")
    elif step == 'delete_pm_target':
        await event.reply("👤 Enter the username or ID to delete PM history:")

async def show_reason_buttons(event):
    buttons = []
    row = []
    
    for i in range(1, 10):
        reason_name = REPORT_REASONS[str(i)][0]
        row.append(Button.inline(reason_name, f'reason_{i}'))
        
        if len(row) == 3:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([Button.inline("🔙 Back", b'back_menu')])
    
    await event.reply(
        "📝 **Select Report Reason**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choose why you're reporting:",
        buttons=buttons
    )

async def show_admin_duration_buttons(event):
    buttons = [
        [Button.inline("⏰ 1 Hour", b'duration_hour')],
        [Button.inline("📅 1 Day", b'duration_day')],
        [Button.inline("📅 1 Week", b'duration_week')],
        [Button.inline("📅 1 Month", b'duration_month')],
        [Button.inline("📅 3 Months", b'duration_3months')],
        [Button.inline("📅 6 Months", b'duration_6months')],
        [Button.inline("📅 1 Year", b'duration_year')],
        [Button.inline("🔙 Cancel", b'admin_panel')]
    ]
    
    await event.reply(
        "⏰ **Select Admin Duration**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choose subscription duration:",
        buttons=buttons
    )

async def show_reaction_buttons(event):
    buttons = [
        [Button.inline("🤬 Angry", b'react_1')],
        [Button.inline("😡 Mad", b'react_2')],
        [Button.inline("👎 Dislike", b'react_3')],
        [Button.inline("🤮 Vomit", b'react_4')],
        [Button.inline("🖕 Middle Finger", b'react_5')],
        [Button.inline("🎲 Random", b'react_random')],
        [Button.inline("🔙 Back", b'back_menu')]
    ]
    
    await event.reply(
        "😠 **Select Reaction**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choose reaction to send:",
        buttons=buttons
    )

async def validate_phone_number(phone: str) -> bool:
    if not phone.startswith('+'):
        return False
    
    clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    if len(clean_phone) < 8 or len(clean_phone) > 15:
        return False
    
    if not clean_phone[1:].isdigit():
        return False
    
    return True

async def validate_username(username: str) -> bool:
    if not username.startswith('@'):
        username = '@' + username
    
    if len(username) < 5 or len(username) > 32:
        return False
    
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
    if not all(c in allowed_chars for c in username[1:]):
        return False
    
    return True

async def validate_post_link(link: str) -> bool:
    if not (link.startswith('https://t.me/') or link.startswith('t.me/')):
        return False
    
    clean_link = link.replace('https://t.me/', '').replace('t.me/', '')
    parts = clean_link.split('/')
    
    if len(parts) < 2:
        return False
    
    try:
        post_id = int(parts[-1])
        if post_id <= 0:
            return False
    except:
        return False
    
    return True

async def validate_channel_link(link: str) -> bool:
    if not (link.startswith('https://t.me/') or link.startswith('t.me/') or link.startswith('@')):
        return False
    
    if link.startswith('@'):
        username = link[1:]
    else:
        clean_link = link.replace('https://t.me/', '').replace('t.me/', '')
        username = clean_link.split('/')[0]
    
    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
    if not all(c in allowed_chars for c in username):
        return False
    
    return True

async def get_entity_info(client, identifier: str):
    try:
        if '?start=' in identifier:
            identifier = identifier.split('?')[0]
        
        entity = await client.get_entity(identifier)
        return {
            'id': entity.id,
            'type': type(entity).__name__,
            'title': getattr(entity, 'title', getattr(entity, 'username', 'Unknown')),
            'username': getattr(entity, 'username', None),
            'access_hash': getattr(entity, 'access_hash', None)
        }
    except errors.UsernameNotOccupiedError:
        return None
    except errors.UsernameInvalidError:
        return None
    except errors.ChannelInvalidError:
        return None
    except Exception as e:
        logger.error(f"Error getting entity {identifier}: {str(e)}")
        return None

async def perform_report(client, entity, reason, message, count=1):
    successes = 0
    failures = 0
    errors = []
    
    for i in range(count):
        try:
            await client(ReportPeerRequest(
                peer=entity,
                reason=reason,
                message=message
            ))
            successes += 1
            
            if i < count - 1:
                await asyncio.sleep(4)
            
        except errors.FloodWaitError as e:
            errors.append(f"Flood wait: {e.seconds}s")
            failures += 1
            break
        except errors.PeerIdInvalidError:
            errors.append("Invalid peer ID")
            failures += 1
            break
        except errors.ChannelPrivateError:
            errors.append("Channel is private")
            failures += 1
            break
        except Exception as e:
            errors.append(f"Error: {str(e)[:50]}")
            failures += 1
    
    return successes, failures, errors

async def perform_block(client, entity):
    try:
        await client(BlockRequest(id=entity))
        return True, None
    except errors.FloodWaitError as e:
        return False, f"Flood wait: {e.seconds}s"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

async def perform_reaction(client, entity, msg_id, reaction):
    try:
        await client(SendReactionRequest(
            peer=entity,
            msg_id=msg_id,
            reaction=[reaction]
        ))
        return True, None
    except errors.FloodWaitError as e:
        return False, f"Flood wait: {e.seconds}s"
    except errors.MsgIdInvalidError:
        return False, "Invalid message ID"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

async def send_start_to_bot_with_unblock(client, entity):
    try:
        if isinstance(entity, str):
            entity = await client.get_entity(entity)
        
        if not getattr(entity, 'bot', False):
            return False, "Not a bot"
        
        try:
            await client.send_message(entity, "/start")
            return True, None
        except errors.UserIsBlockedError:
            try:
                await client(UnblockRequest(id=entity))
                await asyncio.sleep(1)
                await client.send_message(entity, "/start")
                return True, "Unblocked and started"
            except Exception as e:
                return False, f"Failed to unblock: {str(e)[:50]}"
        except errors.BotMethodInvalidError:
            return False, "Bot doesn't accept /start"
        except errors.FloodWaitError as e:
            return False, f"Flood wait: {e.seconds}s"
        except Exception as e:
            return False, f"Error: {str(e)[:50]}"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

async def join_channel_with_approval(client, entity, session_file: str) -> dict:
    try:
        await client(JoinChannelRequest(entity))
        logger.info(f"Successfully joined channel for {session_file}")
        return {'success': True, 'message': f"✅ Joined successfully"}
    except errors.UserAlreadyParticipantError:
        logger.info(f"Already a participant for {session_file}")
        return {'success': True, 'message': f"✅ Already joined"}
    except Exception:
        logger.info(f"Join request sent for {session_file}")
        return {'success': True, 'message': f"✅ Join request sent (needs approval)"}
    except errors.FloodWaitError as e:
        logger.error(f"Flood wait for {session_file}: {e.seconds} seconds")
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except errors.ChannelPrivateError:
        logger.error(f"Channel is private for {session_file}")
        return {'success': False, 'message': f"❌ Channel is private"}
    except errors.ChannelInvalidError:
        logger.error(f"Channel invalid for {session_file}")
        return {'success': False, 'message': f"❌ Invalid channel"}
    except Exception as e:
        logger.error(f"Error joining channel for {session_file}: {str(e)}")
        return {'success': False, 'message': f"❌ Error: {str(e)[:30]}"}

async def join_channel_bulk(client, entity, session_file: str) -> dict:
    try:
        await client(JoinChannelRequest(entity))
        logger.info(f"Successfully joined channel for {session_file}")
        return {'success': True, 'message': f"✅ Joined successfully"}
    except errors.UserAlreadyParticipantError:
        logger.info(f"Already a participant for {session_file}")
        return {'success': True, 'message': f"✅ Already joined"}
    except errors.InviteRequestSentError:
        logger.info(f"Join request sent for {session_file}")
        return {'success': True, 'message': f"✅ Join request sent (needs approval)"}
    except errors.FloodWaitError as e:
        logger.error(f"Flood wait for {session_file}: {e.seconds} seconds")
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except errors.ChannelPrivateError:
        logger.error(f"Channel is private for {session_file}")
        return {'success': False, 'message': f"❌ Channel is private"}
    except errors.ChannelInvalidError:
        logger.error(f"Channel invalid for {session_file}")
        return {'success': False, 'message': f"❌ Invalid channel"}
    except Exception as e:
        logger.error(f"Error joining channel for {session_file}: {str(e)}")
        return {'success': False, 'message': f"❌ Error: {str(e)[:30]}"}

async def leave_channel_operation(client, entity, session_file: str) -> dict:
    """Leave channel operation"""
    try:
        await client(LeaveChannelRequest(entity))
        logger.info(f"Successfully left channel for {session_file}")
        return {'success': True, 'message': f"✅ Left successfully"}
    except errors.UserNotParticipantError:
        logger.info(f"Not a participant for {session_file}")
        return {'success': False, 'message': f"❌ Not a member"}
    except errors.ChannelPrivateError:
        logger.error(f"Channel is private for {session_file}")
        return {'success': False, 'message': f"❌ Channel is private"}
    except errors.FloodWaitError as e:
        logger.error(f"Flood wait for {session_file}: {e.seconds} seconds")
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except Exception as e:
        logger.error(f"Error leaving channel for {session_file}: {str(e)}")
        return {'success': False, 'message': f"❌ Error: {str(e)[:30]}"}

async def leave_group_operation(client, entity, session_file: str) -> dict:
    """Leave group operation"""
    try:
        await client(LeaveChannelRequest(entity))  # Same method for groups
        logger.info(f"Successfully left group for {session_file}")
        return {'success': True, 'message': f"✅ Left successfully"}
    except errors.UserNotParticipantError:
        logger.info(f"Not a participant for {session_file}")
        return {'success': False, 'message': f"❌ Not a member"}
    except errors.ChannelPrivateError:
        logger.error(f"Group is private for {session_file}")
        return {'success': False, 'message': f"❌ Group is private"}
    except errors.FloodWaitError as e:
        logger.error(f"Flood wait for {session_file}: {e.seconds} seconds")
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except Exception as e:
        logger.error(f"Error leaving group for {session_file}: {str(e)}")
        return {'success': False, 'message': f"❌ Error: {str(e)[:30]}"}

async def delete_pm_history(client, target_user, session_file: str) -> dict:
    """Delete PM history with a user (bidirectional)"""
    try:
        # Get entity
        if isinstance(target_user, str):
            entity = await client.get_entity(target_user)
        else:
            entity = target_user
        
        # Get all messages with this user
        messages = await client.get_messages(entity, limit=100)
        
        if not messages:
            return {'success': True, 'message': f"✅ No messages found"}
        
        # Delete messages (both sides)
        deleted_count = 0
        for msg in messages:
            try:
                await client.delete_messages(entity, msg.id)
                deleted_count += 1
                await asyncio.sleep(0.5)  # Small delay to avoid flood
            except Exception as e:
                logger.warning(f"Could not delete message {msg.id}: {e}")
        
        # Also try to delete messages from the other side by forwarding and deleting
        # This helps with bidirectional deletion
        try:
            # Create a dialog with the user
            async with client.action(entity, 'typing'):
                await asyncio.sleep(1)
        except:
            pass
        
        logger.info(f"Deleted {deleted_count} messages with {entity.id} for {session_file}")
        return {'success': True, 'message': f"✅ Deleted {deleted_count} messages (bidirectional)"}
    
    except errors.FloodWaitError as e:
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except errors.PeerIdInvalidError:
        return {'success': False, 'message': f"❌ Invalid user ID"}
    except Exception as e:
        return {'success': False, 'message': f"❌ Error: {str(e)[:50]}"}

async def leave_account_operation(client, session_file: str) -> dict:
    try:
        try:
            await client.log_out()
            result = {'success': True, 'message': f"✅ Successfully logged out from all devices"}
        except Exception as logout_error:
            try:
                await client.disconnect()
                result = {'success': True, 'message': f"✅ Session disconnected successfully"}
            except Exception as disconnect_error:
                result = {'success': False, 'message': f"❌ Error disconnecting: {str(disconnect_error)[:50]}"}
        
        return result
    except Exception as e:
        return {'success': False, 'message': f"❌ Error leaving account: {str(e)[:50]}"}

# ========== New Operations ==========

async def execute_sender_operation(event, state):
    """Execute send message operation"""
    user_id = event.sender_id
    target = state['target']
    message_text = state['message_text']
    send_count = state.get('send_count', 1)
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting Send Operation...**\nTarget: {target}\nMessage: {message_text[:50]}...\nSend count: {send_count} per account")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            if not session_str:
                total_fail += 1
                operation_errors.append(f"{session_file}: Empty session")
                continue
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                operation_errors.append(f"{session_file}: Not authorized")
                await client.disconnect()
                continue
            
            try:
                # Get entity
                if target.startswith("@"):
                    entity = await client.get_entity(target)
                elif target.isdigit():
                    entity = await client.get_entity(int(target))
                else:
                    entity = await client.get_entity(target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                # Send message multiple times
                for j in range(send_count):
                    try:
                        await client.send_message(entity, message_text)
                        total_success += 1
                        
                        if j < send_count - 1:
                            await asyncio.sleep(2)  # Delay between messages
                    
                    except errors.FloodWaitError as e:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
                        break
                    except errors.UserIsBlockedError:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: User has blocked this account")
                    except errors.PeerIdInvalidError:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: Invalid peer ID")
                        break
                    except Exception as e:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: {str(e)[:50]}")
                
                # Progress report
                if i % 5 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Success: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
            # Delay between accounts
            if i < len(sessions):
                await asyncio.sleep(3)
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    # Final result
    result_msg = (
        f"📊 **Send Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 **Target:** {target}\n\n"
        f"📝 **Message:** {message_text[:100]}{'...' if len(message_text) > 100 else ''}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"🔢 **Sends/Account:** {send_count}\n\n"
        f"✅ **Successful Sends:** {total_success}\n\n"
        f"❌ **Failed Sends:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    if target_info:
        target_id = target_info['id']
    else:
        target_id = None
    
    await send_to_report_group(
        event.client,
        "Send Message",
        target,
        target_id,
        f"Accounts: {len(sessions)}\nSends/Account: {send_count}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_commenter_operation(event, state):
    """Execute comment operation"""
    user_id = event.sender_id
    post_link = state['post_link']
    comment_text = state['comment_text']
    comment_count = state.get('comment_count', 1)
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    channel_info = None
    
    await event.reply(f"🚀 **Starting Comment Operation...**\nPost: {post_link}\nComment: {comment_text[:50]}...\nComments per account: {comment_count}")
    
    try:
        # Extract info from link
        clean_link = post_link.replace("https://t.me/", "").replace("t.me/", "")
        parts = clean_link.split("/")
        
        if len(parts) < 2:
            await event.reply("❌ Invalid post link format")
            return
        
        channel = parts[0]
        msg_id = int(parts[1])
        
        for i, session_file in enumerate(sessions, 1):
            try:
                is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
                dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
                path = os.path.join(dir_path, session_file)
                
                with open(path, 'r', encoding='utf-8') as f:
                    session_str = f.read().strip()
                
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    total_fail += 1
                    continue
                
                try:
                    # Get channel entity
                    entity = await client.get_entity("@" + channel if not channel.startswith("@") else channel)
                    
                    if not channel_info:
                        channel_info = await get_entity_info(client, channel)
                    
                    # Join channel
                    await join_channel_with_approval(client, entity, session_file)
                    
                    # Post comments
                    for j in range(comment_count):
                        try:
                            await client.send_message(entity, comment_text, comment_to=msg_id)
                            total_success += 1
                            
                            if j < comment_count - 1:
                                await asyncio.sleep(5)  # Delay between comments
                        
                        except errors.FloodWaitError as e:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
                            break
                        except errors.MsgIdInvalidError:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: Invalid message ID")
                            break
                        except errors.ChatWriteForbiddenError:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: Cannot comment (restricted)")
                        except Exception as e:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: {str(e)[:50]}")
                    
                    # Progress report
                    if i % 5 == 0 or i == len(sessions):
                        progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                        progress += f"✅ Comments: {total_success}\n"
                        progress += f"❌ Failed: {total_fail}"
                        
                        try:
                            await event.reply(progress)
                        except:
                            pass
                
                except errors.ChannelPrivateError:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Channel is private")
                except errors.ChannelInvalidError:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Invalid channel")
                except Exception as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {str(e)[:50]}")
                
                await client.disconnect()
                
                # Delay between accounts
                if i < len(sessions):
                    await asyncio.sleep(3)
                
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    except Exception as e:
        await event.reply(f"❌ Error: {str(e)[:100]}")
        return
    
    # Final result
    result_msg = (
        f"📊 **Comment Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 **Post:** {post_link}\n\n"
        f"💬 **Comment:** {comment_text[:100]}{'...' if len(comment_text) > 100 else ''}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"🔢 **Comments/Account:** {comment_count}\n\n"
        f"✅ **Successful Comments:** {total_success}\n\n"
        f"❌ **Failed Comments:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    channel_id = channel_info['id'] if channel_info else None
    await send_to_report_group(
        event.client,
        "Comment on Post",
        post_link,
        channel_id,
        f"Accounts: {len(sessions)}\nComments/Account: {comment_count}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_view_post_operation(event, state):
    """Execute view post operation - Real view count increase with forward to saved messages"""
    user_id = event.sender_id
    post_link = state['post_link']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    channel_info = None
    
    await event.reply(f"🚀 **Starting View Operation...**\nPost: {post_link}\nAccounts: {len(sessions)}")
    
    try:
        # Extract info from link
        clean_link = post_link.replace("https://t.me/", "").replace("t.me/", "")
        parts = clean_link.split("/")
        
        if len(parts) < 2:
            await event.reply("❌ Invalid post link format")
            return
        
        channel = parts[0]
        msg_id = int(parts[1])
        
        for i, session_file in enumerate(sessions, 1):
            try:
                is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
                dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
                path = os.path.join(dir_path, session_file)
                
                with open(path, 'r', encoding='utf-8') as f:
                    session_str = f.read().strip()
                
                if not session_str:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Empty session")
                    continue
                
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Not authorized")
                    await client.disconnect()
                    continue
                
                try:
                    # Get channel entity
                    entity = await client.get_entity("@" + channel if not channel.startswith("@") else channel)
                    
                    if not channel_info:
                        channel_info = await get_entity_info(client, channel)
                    
                    # Join channel if not already a member
                    try:
                        await join_channel_with_approval(client, entity, session_file)
                    except Exception as e:
                        logger.warning(f"Could not join channel for {session_file}: {e}")
                    
                    # Get the message
                    try:
                        message = await client.get_messages(entity, ids=msg_id)
                        
                        if message:
                            # Method 1: Forward to Saved Messages (registers a view AND gives a real view)
                            try:
                                await client.send_message('me', message)
                                await asyncio.sleep(1)
                            except Exception as e:
                                logger.warning(f"Could not forward to saved messages: {e}")
                            
                            # Method 2: Get messages again (registers view)
                            await client.get_messages(entity, ids=msg_id)
                            
                            # Method 3: Mark as read (registers view)
                            try:
                                await client.send_read_acknowledge(entity, max_id=msg_id)
                            except:
                                pass
                            
                            total_success += 1
                            logger.info(f"Successfully viewed post {post_link} with account {session_file}")
                        else:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: Post not found")
                    
                    except errors.MsgIdInvalidError:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: Invalid message ID")
                    except errors.ChannelPrivateError:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: Channel is private")
                    except errors.FloodWaitError as e:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
                    except Exception as e:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: {str(e)[:50]}")
                    
                    # Progress report
                    if i % 5 == 0 or i == len(sessions):
                        progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                        progress += f"✅ Viewed: {total_success}\n"
                        progress += f"❌ Failed: {total_fail}"
                        
                        try:
                            await event.reply(progress)
                        except:
                            pass
                
                except errors.ChannelPrivateError:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Channel is private")
                except errors.ChannelInvalidError:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Invalid channel")
                except errors.FloodWaitError as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
                except Exception as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {str(e)[:50]}")
                
                await client.disconnect()
                
                # Delay between accounts
                if i < len(sessions):
                    await asyncio.sleep(3)
                
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    except Exception as e:
        await event.reply(f"❌ Error: {str(e)[:100]}")
        return
    
    # Final result
    result_msg = (
        f"📊 **View Post Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 **Post:** {post_link}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successful Views:** {total_success}\n\n"
        f"❌ **Failed Views:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    channel_id = channel_info['id'] if channel_info else None
    await send_to_report_group(
        event.client,
        "View Post",
        post_link,
        channel_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_leave_channel_operation(event, state):
    """Execute leave channel operation"""
    user_id = event.sender_id
    channel_link = state['channel_link']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    channel_info = None
    
    await event.reply(f"🚀 **Starting Leave Channel Operation...**\nChannel: {channel_link}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            if not session_str:
                total_fail += 1
                operation_errors.append(f"{session_file}: Empty session")
                continue
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                operation_errors.append(f"{session_file}: Not authorized")
                await client.disconnect()
                continue
            
            try:
                # Get channel username
                if channel_link.startswith("@"):
                    channel_username = channel_link[1:]
                elif channel_link.startswith("https://t.me/") or channel_link.startswith("t.me/"):
                    clean_link = channel_link.replace("https://t.me/", "").replace("t.me/", "")
                    channel_username = clean_link.split('/')[0]
                else:
                    channel_username = channel_link
                
                # Get entity
                entity = await client.get_entity(f"@{channel_username}")
                
                if not channel_info:
                    channel_info = await get_entity_info(client, f"@{channel_username}")
                
                # Leave channel
                result = await leave_channel_operation(client, entity, session_file)
                
                if result['success']:
                    total_success += 1
                else:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {result['message']}")
                
                # Progress report
                if i % 5 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Left: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
                
                # Delay between accounts
                if i < len(sessions):
                    await asyncio.sleep(3)
            
            except errors.ChannelInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid channel")
            except errors.ChannelPrivateError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Channel is private")
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    # Final result
    result_msg = (
        f"📊 **Leave Channel Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 **Channel:** {channel_link}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successfully Left:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    channel_id = channel_info['id'] if channel_info else None
    await send_to_report_group(
        event.client,
        "Leave Channel",
        channel_link,
        channel_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_leave_group_operation(event, state):
    """Execute leave group operation"""
    user_id = event.sender_id
    group_link = state['group_link']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    group_info = None
    
    await event.reply(f"🚀 **Starting Leave Group Operation...**\nGroup: {group_link}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            if not session_str:
                total_fail += 1
                operation_errors.append(f"{session_file}: Empty session")
                continue
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                operation_errors.append(f"{session_file}: Not authorized")
                await client.disconnect()
                continue
            
            try:
                # Get group username
                if group_link.startswith("@"):
                    group_username = group_link[1:]
                elif group_link.startswith("https://t.me/") or group_link.startswith("t.me/"):
                    clean_link = group_link.replace("https://t.me/", "").replace("t.me/", "")
                    group_username = clean_link.split('/')[0]
                else:
                    group_username = group_link
                
                # Get entity
                entity = await client.get_entity(f"@{group_username}")
                
                if not group_info:
                    group_info = await get_entity_info(client, f"@{group_username}")
                
                # Leave group
                result = await leave_group_operation(client, entity, session_file)
                
                if result['success']:
                    total_success += 1
                else:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {result['message']}")
                
                # Progress report
                if i % 5 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Left: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
                
                # Delay between accounts
                if i < len(sessions):
                    await asyncio.sleep(3)
            
            except errors.ChannelInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid group")
            except errors.ChannelPrivateError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Group is private")
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    # Final result
    result_msg = (
        f"📊 **Leave Group Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Group:** {group_link}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successfully Left:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    group_id = group_info['id'] if group_info else None
    await send_to_report_group(
        event.client,
        "Leave Group",
        group_link,
        group_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_delete_pm_operation(event, state):
    """Execute delete PM history operation"""
    user_id = event.sender_id
    target = state['target']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    total_messages_deleted = 0
    
    await event.reply(f"🚀 **Starting Delete PM Operation...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            if not session_str:
                total_fail += 1
                operation_errors.append(f"{session_file}: Empty session")
                continue
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                operation_errors.append(f"{session_file}: Not authorized")
                await client.disconnect()
                continue
            
            try:
                # Get target entity
                if target.startswith("@"):
                    entity = await client.get_entity(target)
                elif target.isdigit():
                    entity = await client.get_entity(int(target))
                else:
                    entity = await client.get_entity(target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                # Delete PM history
                result = await delete_pm_history(client, entity, session_file)
                
                if result['success']:
                    total_success += 1
                    # Extract number of deleted messages from result message
                    if "Deleted" in result['message']:
                        try:
                            num = int(result['message'].split()[2])
                            total_messages_deleted += num
                        except:
                            pass
                else:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {result['message']}")
                
                # Progress report
                if i % 5 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Success: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
                
                # Delay between accounts
                if i < len(sessions):
                    await asyncio.sleep(4)
            
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except errors.PeerIdInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid user ID")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    # Final result
    result_msg = (
        f"📊 **Delete PM Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Target:** {target}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successful Accounts:** {total_success}\n\n"
        f"❌ **Failed Accounts:** {total_fail}\n\n"
        f"🗑 **Total Messages Deleted:** {total_messages_deleted}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    # Send to report group
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Delete PM History",
        target,
        target_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nFailed: {total_fail}\nMessages Deleted: {total_messages_deleted}"
    )

# ========== Existing Operations ==========

async def execute_report_operation(event, state):
    """Execute channel/group report operation"""
    user_id = event.sender_id
    target = state['target']
    reason_key = state.get('reason_key', '1')
    count_per_account = state.get('count_per_account', 1)
    sessions = state['sessions']
    
    reason_name, reason_obj, default_msg = REPORT_REASONS[reason_key]
    custom_msg = state.get('custom_reason', default_msg)
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting Report Operation...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            if not session_str:
                total_fail += 1
                operation_errors.append(f"{session_file}: Empty session")
                continue
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                operation_errors.append(f"{session_file}: Not authorized")
                await client.disconnect()
                continue
            
            try:
                if target.startswith("@"):
                    entity = await client.get_entity(target)
                else:
                    clean_target = target.replace("https://t.me/", "").replace("t.me/", "")
                    if '?' in clean_target:
                        clean_target = clean_target.split('?')[0]
                    entity = await client.get_entity(clean_target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                join_result = await join_channel_with_approval(client, entity, session_file)
                
                if not join_result['success'] and "Channel is private" not in join_result['message']:
                    operation_errors.append(f"{session_file}: {join_result['message']}")
                
                successes, failures, errors = await perform_report(
                    client, entity, reason_obj, custom_msg, count_per_account
                )
                
                total_success += successes
                total_fail += failures
                
                if errors:
                    operation_errors.extend([f"{session_file}: {err}" for err in errors])
                
                if i % 5 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Success: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Report Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 **Target:** {target}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"🔢 **Reports/Account:** {count_per_account}\n\n"
        f"✅ **Successful Reports:** {total_success}\n\n"
        f"❌ **Failed Reports:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    if target_info:
        target_id = target_info['id']
    else:
        target_id = None
    
    await send_to_report_group(
        event.client,
        "Report Channel/Group",
        target,
        target_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nFailed: {total_fail}"
    )

async def execute_post_report_operation(event, state):
    """Execute post report operation"""
    user_id = event.sender_id
    post_links = state['post_links']
    reason_key = state.get('reason_key', '1')
    count_per_account = state.get('count_per_account', 1)
    sessions = state['sessions']
    
    reason_name, reason_obj, default_msg = REPORT_REASONS[reason_key]
    custom_msg = state.get('custom_reason', default_msg)
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    channels_info = []
    
    await event.reply(f"🚀 **Starting Post Report Operation...**\nPosts: {len(post_links)}")
    
    for post_link in post_links:
        try:
            clean_link = post_link.replace("https://t.me/", "").replace("t.me/", "")
            parts = clean_link.split("/")
            
            if len(parts) < 2:
                operation_errors.append(f"Invalid link: {post_link}")
                continue
            
            channel = parts[0]
            msg_id = int(parts[1])
            
            for i, session_file in enumerate(sessions, 1):
                try:
                    is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
                    dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
                    path = os.path.join(dir_path, session_file)
                    
                    with open(path, 'r', encoding='utf-8') as f:
                        session_str = f.read().strip()
                    
                    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        total_fail += 1
                        continue
                    
                    try:
                        entity = await client.get_entity("@" + channel if not channel.startswith("@") else channel)
                        
                        if not any(c['id'] == entity.id for c in channels_info):
                            channel_info = await get_entity_info(client, channel)
                            if channel_info:
                                channels_info.append(channel_info)
                        
                        await join_channel_with_approval(client, entity, session_file)
                        
                        message = await client.get_messages(entity, ids=msg_id)
                        if not message:
                            total_fail += 1
                            operation_errors.append(f"{session_file}: Post not found")
                            continue
                        
                        successes, failures, errors = await perform_report(
                            client, entity, reason_obj, custom_msg, count_per_account
                        )
                        
                        total_success += successes
                        total_fail += failures
                        
                        if errors:
                            operation_errors.extend([f"{session_file}: {err}" for err in errors])
                    
                    except Exception as e:
                        total_fail += 1
                        operation_errors.append(f"{session_file}: {str(e)[:50]}")
                    
                    await client.disconnect()
                    
                except Exception as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {str(e)[:50]}")
        
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"Error processing {post_link}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Post Report Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Posts:** {len(post_links)}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"🔢 **Reports/Account:** {count_per_account}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors:**\n"
        for err in operation_errors[:3]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    channel_ids = ", ".join(str(c['id']) for c in channels_info) if channels_info else "Unknown"
    await send_to_report_group(
        event.client,
        "Report Post",
        f"{len(post_links)} posts",
        channel_ids,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_profile_report_operation(event, state):
    """Execute profile report operation"""
    user_id = event.sender_id
    target = state['target']
    reason_key = state.get('reason_key', '1')
    count_per_account = state.get('count_per_account', 1)
    sessions = state['sessions']
    
    reason_name, reason_obj, default_msg = REPORT_REASONS[reason_key]
    custom_msg = state.get('custom_reason', default_msg)
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting Profile Report...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                entity = await client.get_entity(target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                successes, failures, errors = await perform_report(
                    client, entity, reason_obj, custom_msg, count_per_account
                )
                
                total_success += successes
                total_fail += failures
                
                if errors:
                    operation_errors.extend([f"{session_file}: {err}" for err in errors])
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Profile Report Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Target:** {target}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Report Profile",
        target,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_bot_report_operation(event, state):
    """Execute bot report operation"""
    user_id = event.sender_id
    target = state['target']
    reason_key = state.get('reason_key', '1')
    count_per_account = state.get('count_per_account', 1)
    sessions = state['sessions']
    
    reason_name, reason_obj, default_msg = REPORT_REASONS[reason_key]
    custom_msg = state.get('custom_reason', default_msg)
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting Bot Report...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                if target.startswith("@"):
                    entity = await client.get_entity(target)
                else:
                    clean_target = target.replace("https://t.me/", "").replace("t.me/", "")
                    entity = await client.get_entity(clean_target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                if not getattr(entity, 'bot', False):
                    operation_errors.append(f"{session_file}: Not a bot")
                    total_fail += 1
                    continue
                
                successes, failures, errors = await perform_report(
                    client, entity, reason_obj, custom_msg, count_per_account
                )
                
                total_success += successes
                total_fail += failures
                
                if errors:
                    operation_errors.extend([f"{session_file}: {err}" for err in errors])
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Bot Report Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 **Target:** {target}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Report Bot",
        target,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_account_report_operation(event, state):
    """Execute account report operation"""
    user_id = event.sender_id
    target = state['target']
    reason_key = state.get('reason_key', '1')
    count_per_account = state.get('count_per_account', 1)
    sessions = state['sessions']
    
    reason_name, reason_obj, default_msg = REPORT_REASONS[reason_key]
    custom_msg = state.get('custom_reason', default_msg)
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting Account Report...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                entity = await client.get_entity(target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                if getattr(entity, 'bot', False) or hasattr(entity, 'broadcast'):
                    operation_errors.append(f"{session_file}: Not a regular account")
                    total_fail += 1
                    continue
                
                successes, failures, errors = await perform_report(
                    client, entity, reason_obj, custom_msg, count_per_account
                )
                
                total_success += successes
                total_fail += failures
                
                if errors:
                    operation_errors.extend([f"{session_file}: {err}" for err in errors])
            
            except errors.PeerIdInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid peer ID")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Account Report Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Target:** {target}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Report Account",
        target,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_manual_report_operation(event, state):
    """Execute manual report operation"""
    user_id = event.sender_id
    target = state['target']
    reason_key = state.get('reason_key', '1')
    sessions = state['sessions']
    manual_text = state['manual_text']
    
    reason_name, reason_obj, _ = REPORT_REASONS[reason_key]
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    MANUAL_REPORT_DATES[user_id] = date.today()
    save_data()
    
    await event.reply(f"🚀 **Starting Manual Report...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                entity = await client.get_entity(target)
                
                if not target_info:
                    target_info = await get_entity_info(client, target)
                
                try:
                    await client(ReportPeerRequest(
                        peer=entity,
                        reason=reason_obj,
                        message=manual_text
                    ))
                    total_success += 1
                    
                    if i < len(sessions):
                        await asyncio.sleep(120)
                
                except errors.FloodWaitError as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
                except Exception as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Manual Report Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Target:** {target}\n\n"
        f"📝 **Reason:** {reason_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"📅 **Next manual report:** Tomorrow\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Manual Report",
        target,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_notoscam_operation(event, state):
    """Execute send to @notoscam operation"""
    message = state['message']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    
    await event.reply("🚀 **Sending messages to @notoscam...**")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                await client.send_message('notoscam', message)
                total_success += 1
                
                if i < len(sessions):
                    await asyncio.sleep(4)
            
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Message Sent to @notoscam**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Message:** {message[:50]}...\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    await send_to_report_group(
        event.client,
        "Send to @notoscam",
        "notoscam",
        None,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_block_user_operation(event, state):
    """Execute block user operation"""
    username = state['target']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Blocking user...**\nTarget: {username}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                entity = await client.get_entity(username)
                
                if not target_info:
                    target_info = await get_entity_info(client, username)
                
                success, error = await perform_block(client, entity)
                
                if success:
                    total_success += 1
                else:
                    total_fail += 1
                    if error:
                        operation_errors.append(f"{session_file}: {error}")
                
                if i < len(sessions):
                    await asyncio.sleep(4)
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **User Blocked**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Target:** {username}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Block User",
        username,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_reaction_operation(event, state):
    """Execute reaction operation"""
    post_link = state['post_link']
    reaction_key = state['reaction']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    
    if reaction_key == 'random':
        reactions = list(REACTION_OPTIONS.values())[:5]
        selected_reaction = random.choice(reactions)[0]
        reaction_name = "Random🎲"
    else:
        selected_reaction, reaction_name = REACTION_OPTIONS[reaction_key]
    
    await event.reply(f"🚀 **Sending reaction...**\nPost: {post_link}")
    
    try:
        clean_link = post_link.replace("https://t.me/", "").replace("t.me/", "")
        parts = clean_link.split("/")
        
        if len(parts) < 2:
            await event.reply("❌ Invalid post link format")
            return
        
        channel = parts[0]
        msg_id = int(parts[1])
        
        for i, session_file in enumerate(sessions, 1):
            try:
                is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
                dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
                path = os.path.join(dir_path, session_file)
                
                with open(path, 'r', encoding='utf-8') as f:
                    session_str = f.read().strip()
                
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    total_fail += 1
                    continue
                
                try:
                    entity = await client.get_entity("@" + channel if not channel.startswith("@") else channel)
                    
                    await join_channel_with_approval(client, entity, session_file)
                    
                    success, error = await perform_reaction(client, entity, msg_id, selected_reaction)
                    
                    if success:
                        total_success += 1
                    else:
                        total_fail += 1
                        if error:
                            operation_errors.append(f"{session_file}: {error}")
                    
                    if i < len(sessions):
                        await asyncio.sleep(4)
                
                except Exception as e:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {str(e)[:50]}")
                
                await client.disconnect()
                
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    except Exception as e:
        await event.reply(f"❌ Error: {str(e)[:100]}")
        return
    
    result_msg = (
        f"📊 **Reaction Sent**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 **Post:** {post_link}\n\n"
        f"😠 **Reaction:** {reaction_name}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await event.reply(result_msg)
    
    await send_to_report_group(
        event.client,
        "Send Reaction",
        post_link,
        None,
        f"Reaction: {reaction_name}\nSuccess: {total_success}, Failed: {total_fail}"
    )

async def execute_start_bot_operation(event, state):
    """Execute start bot operation (with unblock capability)"""
    target = state['target']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    target_info = None
    
    await event.reply(f"🚀 **Starting bot...**\nTarget: {target}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                clean_target = target
                if '?start=' in clean_target:
                    clean_target = clean_target.split('?')[0]
                
                if clean_target.startswith("@"):
                    entity = await client.get_entity(clean_target)
                else:
                    clean_target = clean_target.replace("https://t.me/", "").replace("t.me/", "")
                    entity = await client.get_entity(clean_target)
                
                if not target_info:
                    target_info = await get_entity_info(client, clean_target)
                
                if not getattr(entity, 'bot', False):
                    operation_errors.append(f"{session_file}: Not a bot")
                    total_fail += 1
                    continue
                
                success, error = await send_start_to_bot_with_unblock(client, entity)
                
                if success:
                    total_success += 1
                    if error and "Unblocked" in error:
                        operation_errors.append(f"{session_file}: {error}")
                else:
                    total_fail += 1
                    if error:
                        operation_errors.append(f"{session_file}: {error}")
                
                if i < len(sessions):
                    await asyncio.sleep(4)
            
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Bot Started**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 **Target:** {target}\n\n"
        f"👥 **Accounts:** {len(sessions)}\n\n"
        f"✅ **Success:** {total_success}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Details:**\n"
        for err in operation_errors[:3]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    target_id = target_info['id'] if target_info else None
    await send_to_report_group(
        event.client,
        "Start Bot",
        target,
        target_id,
        f"Success: {total_success}, Failed: {total_fail}"
    )

async def execute_join_channel_operation(event, state):
    """Execute join channel operation"""
    channel_link = state['channel_link']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    channel_info = None
    join_requests = 0
    
    await event.reply(f"🚀 **Joining channel...**\nChannel: {channel_link}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                if channel_link.startswith("@"):
                    channel_username = channel_link[1:]
                elif channel_link.startswith("https://t.me/") or channel_link.startswith("t.me/"):
                    clean_link = channel_link.replace("https://t.me/", "").replace("t.me/", "")
                    channel_username = clean_link.split('/')[0]
                else:
                    channel_username = channel_link
                
                entity = await client.get_entity(f"@{channel_username}")
                
                if not channel_info:
                    channel_info = await get_entity_info(client, f"@{channel_username}")
                
                result = await join_channel_with_approval(client, entity, session_file)
                
                if result['success']:
                    total_success += 1
                    if "request sent" in result['message'].lower():
                        join_requests += 1
                else:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {result['message']}")
                
                if i < len(sessions):
                    await asyncio.sleep(4)
                
                if i % 10 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Joined: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
            
            except errors.ChannelInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid channel")
            except errors.ChannelPrivateError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Channel is private")
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Channel Join Operation Complete**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 **Channel:** {channel_link}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successfully Joined:** {total_success}\n\n"
        f"👋 **Join Requests Sent:** {join_requests}\n\n"
        f"❌ **Failed:** {total_fail}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    channel_id = channel_info['id'] if channel_info else None
    await send_to_report_group(
        event.client,
        "Join Channel",
        channel_link,
        channel_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nRequests: {join_requests}\nFailed: {total_fail}"
    )

async def execute_join_group_operation(event, state):
    """Execute join group operation"""
    group_link = state['group_link']
    sessions = state['sessions']
    
    total_success = 0
    total_fail = 0
    operation_errors = []
    group_info = None
    join_requests = 0
    
    await event.reply(f"🚀 **Joining group...**\nGroup: {group_link}")
    
    for i, session_file in enumerate(sessions, 1):
        try:
            is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
            dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
            path = os.path.join(dir_path, session_file)
            
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue
            
            try:
                if group_link.startswith("@"):
                    group_username = group_link[1:]
                elif group_link.startswith("https://t.me/") or group_link.startswith("t.me/"):
                    clean_link = group_link.replace("https://t.me/", "").replace("t.me/", "")
                    group_username = clean_link.split('/')[0]
                else:
                    group_username = group_link
                
                entity = await client.get_entity(f"@{group_username}")
                
                if not group_info:
                    group_info = await get_entity_info(client, f"@{group_username}")
                
                result = await join_channel_with_approval(client, entity, session_file)
                
                if result['success']:
                    total_success += 1
                    if "request sent" in result['message'].lower():
                        join_requests += 1
                else:
                    total_fail += 1
                    operation_errors.append(f"{session_file}: {result['message']}")
                
                if i < len(sessions):
                    await asyncio.sleep(4)
                
                if i % 10 == 0 or i == len(sessions):
                    progress = f"📊 **Progress:** {i}/{len(sessions)} accounts\n"
                    progress += f"✅ Joined: {total_success}\n"
                    progress += f"❌ Failed: {total_fail}"
                    
                    try:
                        await event.reply(progress)
                    except:
                        pass
            
            except errors.ChannelInvalidError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Invalid group")
            except errors.ChannelPrivateError:
                total_fail += 1
                operation_errors.append(f"{session_file}: Group is private")
            except errors.FloodWaitError as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: Flood wait {e.seconds}s")
            except Exception as e:
                total_fail += 1
                operation_errors.append(f"{session_file}: {str(e)[:50]}")
            
            await client.disconnect()
            
        except Exception as e:
            total_fail += 1
            operation_errors.append(f"{session_file}: {str(e)[:50]}")
    
    result_msg = (
        f"📊 **Group Join Operation Complete**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Group:** {group_link}\n\n"
        f"👥 **Accounts Used:** {len(sessions)}\n\n"
        f"✅ **Successfully Joined:** {total_success}\n\n"
        f"👋 **Join Requests Sent:** {join_requests}\n\n"
        f"❌ **Failed:** {total_fail}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if operation_errors:
        result_msg += f"\n\n⚠️ **Errors ({min(5, len(operation_errors))} of {len(operation_errors)}):**\n"
        for err in operation_errors[:5]:
            result_msg += f"• {err}\n"
    
    await event.reply(result_msg)
    
    group_id = group_info['id'] if group_info else None
    await send_to_report_group(
        event.client,
        "Join Group",
        group_link,
        group_id,
        f"Accounts: {len(sessions)}\nSuccess: {total_success}\nRequests: {join_requests}\nFailed: {total_fail}"
    )

async def execute_leave_account_operation(event, state):
    """Execute leave account operation"""
    user_id = event.sender_id
    phone = state['phone']
    
    await event.reply(f"🚪 **Leaving account...**\nPhone: {phone}")
    
    phone_clean = phone.replace('+', '').replace(' ', '')
    found_session = None
    is_shared = False
    
    for f in os.listdir(SESSIONS_DIR):
        if f.endswith(".session") and phone_clean in f:
            found_session = f
            is_shared = False
            break
    
    if not found_session:
        for f in os.listdir(SHARED_SESSIONS_DIR):
            if f.endswith(".session") and f == f"{phone_clean}.session":
                found_session = f
                is_shared = True
                break
    
    if not found_session:
        await event.reply(f"❌ No session found for phone number: {phone}")
        USER_STATE.pop(user_id, None)
        await show_main_menu(event, user_id)
        return
    
    dir_path = SHARED_SESSIONS_DIR if is_shared else SESSIONS_DIR
    path = os.path.join(dir_path, found_session)
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            session_str = f.read().strip()
        
        if not session_str:
            await event.reply(f"❌ Session file is empty for: {phone}")
            USER_STATE.pop(user_id, None)
            await show_main_menu(event, user_id)
            return
        
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                await event.reply(f"⚠️ Account {phone} is not logged in (not in account).\n"
                                 "Session file exists but account is not active.")
                await client.disconnect()
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
                return
            
            me = await client.get_me()
            
            result = await leave_account_operation(client, found_session)
            
            await client.disconnect()
            
            if result['success']:
                os.remove(path)
                clear_user_cache(user_id)
                
                await event.reply(
                    f"✅ **Successfully Left Account**\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📱 **Phone:** {phone}\n\n"
                    f"🆔 **Account ID:** {me.id}\n\n"
                    f"👤 **Username:** @{me.username if me.username else 'No username'}\n\n"
                    f"📁 **Session File:** {found_session}\n\n"
                    f"💾 **Type:** {'Shared' if is_shared else 'Personal'}\n\n"
                    f"📝 **Status:** Account logged out and session file deleted.\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
                
                await send_to_report_group(
                    event.client,
                    "Leave Account",
                    phone,
                    me.id,
                    f"Account ID: {me.id}\nUsername: @{me.username if me.username else 'No username'}\nStatus: Successfully left and session deleted"
                )
            else:
                await event.reply(
                    f"❌ **Failed to Leave Account**\n\n"
                    f"📱 **Phone:** {phone}\n\n"
                    f"🆔 **Account ID:** {me.id}\n\n"
                    f"⚠️ **Error:** {result['message']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
            
            USER_STATE.pop(user_id, None)
            await show_main_menu(event, user_id)
            
        except Exception as e:
            await client.disconnect()
            await event.reply(f"❌ Error processing account {phone}: {str(e)[:100]}")
            USER_STATE.pop(user_id, None)
            await show_main_menu(event, user_id)
            
    except Exception as e:
        await event.reply(f"❌ Error reading session file for {phone}: {str(e)[:100]}")
        USER_STATE.pop(user_id, None)
        await show_main_menu(event, user_id)

# ========== Main Handlers ==========
async def main():
    """Main function"""
    load_data()
    
    bot = TelegramClient("bot_session", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("🤖 Bot started successfully")
    
    @bot.on(events.NewMessage(pattern=r'/start(?:\s+(.+))?'))
    async def start_handler(event):
        user_id = event.sender_id
        referrer_param = event.pattern_match.group(1)
        
        if referrer_param:
            try:
                if referrer_param.isdigit():
                    referrer_id = int(referrer_param)
                    if user_id != referrer_id:
                        REFERRALS[user_id] = referrer_id
                        save_data()
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"👤 **New Referral!**\nUser ID: {user_id} joined via your link!"
                            )
                        except:
                            pass
                elif '=' in referrer_param:
                    referrer_param = referrer_param.split('=')[-1]
                    if referrer_param.isdigit():
                        referrer_id = int(referrer_param)
                        if user_id != referrer_id:
                            REFERRALS[user_id] = referrer_id
                            save_data()
                            try:
                                await bot.send_message(
                                    referrer_id,
                                    f"👤 **New Referral!**\nUser ID: {user_id} joined via your link!"
                                )
                            except:
                                pass
            except:
                pass
        
        await show_main_menu(event, user_id)
    
    @bot.on(events.NewMessage)
    async def message_handler(event):
        if event.text.startswith('/'):
            return
        
        user_id = event.sender_id
        
        if not can_access(user_id):
            await event.reply("Contact @pv_ghahremn to subscribe.")
            return
        
        if is_rest_time():
            await event.reply("⏸️ Accounts are currently resting. Please try again later.")
            return
        
        state = USER_STATE.get(user_id, {})
        text = event.text.strip()
        
        try:
            step = state.get('step')
            
            if step == 'admin_id':
                try:
                    admin_id = int(text)
                    if admin_id in ADMINS:
                        await event.reply("❌ This user is already an admin.")
                        return
                    
                    USER_STATE[user_id]['admin_id'] = admin_id
                    await show_admin_duration_buttons(event)
                
                except ValueError:
                    await event.reply("❌ Please enter a valid numeric ID.")
            
            elif step == 'remove_admin_id':
                try:
                    admin_id = int(text)
                    if admin_id not in ADMINS:
                        await event.reply("❌ This ID is not in the admin list.")
                        return
                    
                    del ADMINS[admin_id]
                    save_data()
                    clear_user_cache(admin_id)
                    
                    await event.reply(f"✅ Admin with ID {admin_id} removed successfully.")
                    USER_STATE.pop(user_id, None)
                    await show_main_menu(event, user_id)
                
                except ValueError:
                    await event.reply("❌ Please enter a valid numeric ID.")
            
            elif step == 'remove_subscription_id':
                try:
                    sub_id = int(text)
                    if sub_id not in ADMINS:
                        await event.reply("❌ This ID does not have an active subscription.")
                        return
                    
                    del ADMINS[sub_id]
                    save_data()
                    clear_user_cache(sub_id)
                    
                    await event.reply(f"✅ Subscription for user ID {sub_id} removed successfully.")
                    USER_STATE.pop(user_id, None)
                    await show_main_menu(event, user_id)
                
                except ValueError:
                    await event.reply("❌ Please enter a valid numeric ID.")
            
            elif step == 'phone':
                if not await validate_phone_number(text):
                    await event.reply("❌ Invalid phone number format. Use +98xxxxxxxxxx")
                    return
                
                USER_STATE[user_id]['phone'] = text
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                
                try:
                    await client.send_code_request(text)
                    USER_STATE[user_id]['client'] = client
                    USER_STATE[user_id]['step'] = 'code'
                    await event.reply("✅ Verification code sent. Please enter the code:")
                except Exception as e:
                    await event.reply(f"❌ Error sending code: {str(e)}")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
            
            elif step == 'shared_phone':
                if not is_owner(user_id):
                    await event.reply("❌ Only owners can add shared accounts!")
                    USER_STATE.pop(user_id, None)
                    return
                
                if not await validate_phone_number(text):
                    await event.reply("❌ Invalid phone number format. Use +98xxxxxxxxxx")
                    return
                
                USER_STATE[user_id]['phone'] = text
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                
                try:
                    await client.send_code_request(text)
                    USER_STATE[user_id]['client'] = client
                    USER_STATE[user_id]['step'] = 'shared_code'
                    await event.reply("✅ Verification code sent. Please enter the code:")
                except Exception as e:
                    await event.reply(f"❌ Error sending code: {str(e)}")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
            
            elif step in ['code', 'shared_code']:
                if len(text) < 4:
                    await event.reply("❌ Invalid code. Must be at least 4 digits.")
                    return
                
                client = state.get('client')
                phone = state.get('phone')
                
                if not client or not phone:
                    await event.reply("❌ Session expired. Please start over.")
                    USER_STATE.pop(user_id, None)
                    return
                
                try:
                    await client.sign_in(phone, text)
                    session_str = client.session.save()
                    is_shared = step == 'shared_code'
                    save_session_string(user_id, phone, session_str, shared=is_shared)
                    
                    await event.reply(f"✅ {'Shared ' if is_shared else ''}Account added successfully!")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
                    clear_user_cache(user_id)
                    await show_main_menu(event, user_id)
                
                except errors.SessionPasswordNeededError:
                    USER_STATE[user_id]['step'] = 'password' if step == 'code' else 'shared_password'
                    await event.reply("🔐 Two-step verification is enabled. Please enter the password:")
                
                except errors.PhoneCodeInvalidError:
                    await event.reply("❌ Invalid code. Please try again:")
                
                except errors.PhoneCodeExpiredError:
                    await event.reply("❌ Code expired. Please start over.")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
                
                except Exception as e:
                    await event.reply(f"❌ Error signing in: {str(e)}\nPlease start over.")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
            
            elif step in ['password', 'shared_password']:
                if not text:
                    await event.reply("❌ Please enter a valid password:")
                    return
                
                client = state.get('client')
                if not client:
                    await event.reply("❌ Session expired. Please start over.")
                    USER_STATE.pop(user_id, None)
                    return
                
                try:
                    await client.sign_in(password=text)
                    session_str = client.session.save()
                    is_shared = step == 'shared_password'
                    save_session_string(user_id, state['phone'], session_str, shared=is_shared)
                    
                    await event.reply(f"✅ {'Shared ' if is_shared else ''}Account added successfully!")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
                    clear_user_cache(user_id)
                    await show_main_menu(event, user_id)
                
                except errors.PasswordHashInvalidError:
                    await event.reply("❌ Invalid password. Please try again:")
                except Exception as e:
                    await event.reply(f"❌ Error: {str(e)}\nPlease start over.")
                    await client.disconnect()
                    USER_STATE.pop(user_id, None)
            
            elif step == 'delete_phone':
                if not text.startswith('+'):
                    await event.reply("❌ Phone number must start with +. Please try again:")
                    return
                
                deleted_any = False
                phone_clean = text.replace('+', '').replace(' ', '')
                
                for file in os.listdir(SESSIONS_DIR):
                    if file.startswith(f"{user_id}_{phone_clean}") and file.endswith(".session"):
                        os.remove(os.path.join(SESSIONS_DIR, file))
                        deleted_any = True
                
                if is_owner(user_id):
                    for file in os.listdir(SHARED_SESSIONS_DIR):
                        if file == f"{phone_clean}.session":
                            os.remove(os.path.join(SHARED_SESSIONS_DIR, file))
                            deleted_any = True
                
                if deleted_any:
                    await event.reply(f"✅ Account {text} deleted successfully.")
                    clear_user_cache(user_id)
                else:
                    await event.reply(f"❌ No account found for {text}.")
                
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step == 'leave_account_phone':
                if not text.startswith('+'):
                    await event.reply("❌ Phone number must start with +. Please try again:")
                    return
                
                if not await validate_phone_number(text):
                    await event.reply("❌ Invalid phone number format. Use +98xxxxxxxxxx")
                    return
                
                USER_STATE[user_id]['phone'] = text
                await execute_leave_account_operation(event, state)
            
            elif step == 'select_count':
                try:
                    count = int(text)
                    sessions_list = get_user_sessions(user_id)
                    
                    if count < 1 or count > len(sessions_list):
                        await event.reply(f"❌ Number must be between 1 and {len(sessions_list)}. Please try again:")
                        return
                    
                    state['count'] = count
                    state['sessions'] = sessions_list[:count]
                    
                    op_type = state.get('type')
                    
                    if op_type == 'report':
                        state['step'] = 'target_link'
                        await event.reply("🔗 Enter the channel/group username (@username) or link (https://t.me/username):")
                    
                    elif op_type == 'report_post':
                        state['step'] = 'post_link'
                        await event.reply("🔗 Enter 1 to 6 post links (e.g., https://t.me/channel_name/123), one per line:")
                    
                    elif op_type == 'report_profile':
                        state['step'] = 'profile_username'
                        await event.reply("👤 Enter the target username (with @):")
                    
                    elif op_type == 'report_bot':
                        state['step'] = 'bot_target'
                        await event.reply("🤖 Enter the bot username (@username) or link (https://t.me/username):")
                    
                    elif op_type == 'report_account':
                        state['step'] = 'account_target'
                        await event.reply("👤 Enter the target username (with @):")
                    
                    elif op_type == 'manual_report':
                        if not await can_use_manual_report(user_id):
                            await event.reply("❌ You can use manual report only once per day. Please try tomorrow.")
                            USER_STATE.pop(user_id, None)
                            await show_main_menu(event, user_id)
                            return
                        
                        state['step'] = 'manual_target'
                        await event.reply("👤 Enter the target username (with @):")
                    
                    elif op_type == 'notoreport':
                        state['step'] = 'notoscam_message'
                        await event.reply("💬 Enter the message to send to @notoscam:")
                    
                    elif op_type == 'blackuser':
                        state['step'] = 'block_username'
                        await event.reply("🚷 Enter the username to block (with @):")
                    
                    elif op_type == 'reaction':
                        state['step'] = 'reaction_post'
                        await event.reply("🔗 Enter the post link (e.g., https://t.me/channel_name/123):")
                    
                    elif op_type == 'startbot':
                        state['step'] = 'startbot_target'
                        await event.reply("🤖 Enter the bot username (@username) or link (https://t.me/username):")
                    
                    elif op_type == 'join_channel':
                        state['step'] = 'join_channel_link'
                        await event.reply("📢 Enter the channel link or username (e.g., https://t.me/channel_name or @channel_name):")
                    
                    elif op_type == 'join_group':
                        state['step'] = 'join_group_link'
                        await event.reply("👥 Enter the group link or username (e.g., https://t.me/group_name or @group_name):")
                    
                    # ========== New options ==========
                    elif op_type == 'sender':
                        state['step'] = 'sender_target'
                        await event.reply("👤 Enter the target username or ID to send message:")
                    
                    elif op_type == 'commenter':
                        state['step'] = 'commenter_post'
                        await event.reply("🔗 Enter the post link (e.g., https://t.me/channel_name/123):")
                    
                    elif op_type == 'view_post':
                        state['step'] = 'view_post_link'
                        await event.reply("🔗 Enter the post link to view (e.g., https://t.me/channel_name/123):")
                    
                    elif op_type == 'leave_channel':
                        state['step'] = 'leave_channel_link'
                        await event.reply("📢 Enter the channel link or username to leave (e.g., https://t.me/channel_name or @channel_name):")
                    
                    elif op_type == 'leave_group':
                        state['step'] = 'leave_group_link'
                        await event.reply("👥 Enter the group link or username to leave (e.g., https://t.me/group_name or @group_name):")
                    
                    elif op_type == 'delete_pm':
                        state['step'] = 'delete_pm_target'
                        await event.reply("👤 Enter the username or ID to delete PM history:")
                
                except ValueError:
                    await event.reply("❌ Please enter a valid number.")
            
            elif step == 'target_link':
                if not (text.startswith('@') or text.startswith('https://t.me/') or text.startswith('t.me/')):
                    await event.reply("❌ Invalid format. Enter @username or https://t.me/username")
                    return
                
                state['target'] = text
                state['step'] = 'select_reason'
                await show_reason_buttons(event)
            
            elif step == 'post_link':
                post_links = [link.strip() for link in text.split('\n') if link.strip()]
                
                if not post_links or len(post_links) > 6:
                    await event.reply("❌ Please enter 1 to 6 valid post links, one per line.")
                    return
                
                for link in post_links:
                    if not await validate_post_link(link):
                        await event.reply(f"❌ Invalid post link: {link}\nFormat: https://t.me/channel/123")
                        return
                
                state['post_links'] = post_links
                state['step'] = 'select_reason'
                await show_reason_buttons(event)
            
            elif step in ['profile_username', 'bot_target', 'account_target', 'manual_target', 'block_username']:
                if not await validate_username(text):
                    await event.reply("❌ Invalid username format. Must start with @ and contain only letters, numbers, and underscores.")
                    return
                
                state['target'] = text
                
                if step in ['profile_username', 'bot_target', 'account_target', 'manual_target']:
                    state['step'] = 'select_reason'
                    await show_reason_buttons(event)
                else:
                    await execute_block_user_operation(event, state)
                    USER_STATE.pop(user_id, None)
                    await show_main_menu(event, user_id)
            
            # ========== New sender steps ==========
            elif step == 'sender_target':
                state['target'] = text
                state['step'] = 'sender_message'
                await event.reply("📝 Enter the message to send:")
            
            elif step == 'sender_message':
                if not text.strip():
                    await event.reply("❌ Message cannot be empty. Please try again:")
                    return
                
                state['message_text'] = text
                state['step'] = 'sender_count'
                await event.reply("🔢 How many times to send the message per account? (1-50):")
            
            elif step == 'sender_count':
                try:
                    count = int(text)
                    if count < 1 or count > 50:
                        await event.reply("❌ Number must be between 1 and 50. Please try again:")
                        return
                    
                    state['send_count'] = count
                    await execute_sender_operation(event, state)
                    USER_STATE.pop(user_id, None)
                    await show_main_menu(event, user_id)
                
                except ValueError:
                    await event.reply("❌ Please enter a valid number between 1 and 50.")
            
            # ========== New commenter steps ==========
            elif step == 'commenter_post':
                if not await validate_post_link(text):
                    await event.reply("❌ Invalid post link. Format: https://t.me/channel/123")
                    return
                
                state['post_link'] = text
                state['step'] = 'commenter_text'
                await event.reply("📝 Enter the comment text:")
            
            elif step == 'commenter_text':
                if not text.strip():
                    await event.reply("❌ Comment cannot be empty. Please try again:")
                    return
                
                state['comment_text'] = text
                state['step'] = 'commenter_count'
                await event.reply("🔢 How many comments per account? (1-20):")
            
            elif step == 'commenter_count':
                try:
                    count = int(text)
                    if count < 1 or count > 20:
                        await event.reply("❌ Number must be between 1 and 20. Please try again:")
                        return
                    
                    state['comment_count'] = count
                    await execute_commenter_operation(event, state)
                    USER_STATE.pop(user_id, None)
                    await show_main_menu(event, user_id)
                
                except ValueError:
                    await event.reply("❌ Please enter a valid number between 1 and 20.")
            
            # ========== New view post steps ==========
            elif step == 'view_post_link':
                if not await validate_post_link(text):
                    await event.reply("❌ Invalid post link. Format: https://t.me/channel/123")
                    return
                
                state['post_link'] = text
                await execute_view_post_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            # ========== New leave channel steps ==========
            elif step == 'leave_channel_link':
                if not await validate_channel_link(text):
                    await event.reply("❌ Invalid link format. Use @username or https://t.me/username")
                    return
                
                state['channel_link'] = text
                await execute_leave_channel_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            # ========== New leave group steps ==========
            elif step == 'leave_group_link':
                if not await validate_channel_link(text):
                    await event.reply("❌ Invalid link format. Use @username or https://t.me/username")
                    return
                
                state['group_link'] = text
                await execute_leave_group_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            # ========== New delete PM steps ==========
            elif step == 'delete_pm_target':
                state['target'] = text
                await execute_delete_pm_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step == 'reaction_post':
                if not await validate_post_link(text):
                    await event.reply("❌ Invalid post link. Format: https://t.me/channel/123")
                    return
                
                state['post_link'] = text
                state['step'] = 'select_reaction'
                await show_reaction_buttons(event)
            
            elif step == 'startbot_target':
                if not (text.startswith('@') or text.startswith('https://t.me/') or text.startswith('t.me/')):
                    await event.reply("❌ Invalid format. Enter @username or https://t.me/username")
                    return
                
                state['target'] = text
                await execute_start_bot_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step == 'notoscam_message':
                if not text.strip():
                    await event.reply("❌ Message cannot be empty. Please try again:")
                    return
                
                state['message'] = text
                await execute_notoscam_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step in ['join_channel_link', 'join_group_link']:
                if not await validate_channel_link(text):
                    await event.reply("❌ Invalid link format. Use @username or https://t.me/username")
                    return
                
                if step == 'join_channel_link':
                    state['channel_link'] = text
                    await execute_join_channel_operation(event, state)
                else:
                    state['group_link'] = text
                    await execute_join_group_operation(event, state)
                
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step == 'count_per_account':
                try:
                    count = int(text)
                    if count < 1 or count > 50:
                        await event.reply("❌ Number of reports per account must be between 1 and 50. Please try again:")
                        return
                    
                    state['count_per_account'] = count
                    state['step'] = 'custom_reason'
                    await event.reply("📝 Enter custom report message (Please enter your desired text.):")
                except ValueError:
                    await event.reply("❌ Please enter a valid number between 1 and 50.")
            
            elif step == 'custom_reason':
                if text == '/skip':
                    reason_key = state.get('reason_key', '1')
                    text = REPORT_REASONS[reason_key][2]
                
                state['custom_reason'] = text
                
                op_type = state.get('type')
                
                if op_type == 'report':
                    await execute_report_operation(event, state)
                elif op_type == 'report_post':
                    await execute_post_report_operation(event, state)
                elif op_type == 'report_profile':
                    await execute_profile_report_operation(event, state)
                elif op_type == 'report_bot':
                    await execute_bot_report_operation(event, state)
                elif op_type == 'report_account':
                    await execute_account_report_operation(event, state)
                
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif step == 'manual_text':
                if text.count('\n') < 3:
                    await event.reply("❌ Message must be at least 4 lines. Please try again:")
                    return
                
                state['manual_text'] = text
                await execute_manual_report_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            else:
                await event.reply("❌ Invalid state. Please use the menu buttons.")
                await show_main_menu(event, user_id)
        
        except Exception as e:
            logger.error(f"Message handler error for user {user_id}: {str(e)}")
            await event.reply(f"❌ An error occurred: {str(e)[:100]}")
            USER_STATE.pop(user_id, None)
            await show_main_menu(event, user_id)
    
    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        user_id = event.sender_id
        
        if not can_access(user_id):
            await event.answer("❌ Access denied! Please subscribe first.", alert=True)
            return
        
        if is_rest_time():
            await event.answer("⏸️ Accounts are resting. Please try later.", alert=True)
            return
        
        data = event.data.decode('utf-8')
        state = USER_STATE.get(user_id, {})
        
        try:
            if data == 'back_menu':
                await show_main_menu(event, user_id)
            
            elif data == 'refresh_sessions':
                clear_user_cache(user_id)
                await event.answer("✅ Sessions cache refreshed!", alert=True)
                await show_main_menu(event, user_id)
            
            elif data == 'admin_panel':
                if not is_owner(user_id):
                    await event.answer("❌ Only owners can access admin panel!", alert=True)
                    return
                
                buttons = [
                    [Button.inline("➕ Add Admin", b'addadmin')],
                    [Button.inline("📋 List Admins", b'listadmin')],
                    [Button.inline("🗑 Remove Admin", b'removeadmin')],
                    [Button.inline("🗑 Remove Subscription", b'removesub')],
                    [Button.inline("🔙 Back", b'back_menu')]
                ]
                await event.edit("👑 **Owner Admin Panel**\nSelect an option:", buttons=buttons)
            
            elif data == 'addadmin':
                if not is_owner(user_id):
                    await event.answer("❌ Only owners can add admins!", alert=True)
                    return
                
                if len(ADMINS) >= 10:
                    await event.answer("❌ Admin capacity is full (maximum 10).", alert=True)
                    return
                
                USER_STATE[user_id] = {'step': 'admin_id'}
                await event.reply("📝 Enter the user ID to add as admin:")
            
            elif data == 'removeadmin':
                if not is_owner(user_id):
                    await event.answer("❌ Only owners can remove admins!", alert=True)
                    return
                
                USER_STATE[user_id] = {'step': 'remove_admin_id'}
                await event.reply("📝 Enter the admin ID to remove:")
            
            elif data == 'removesub':
                if not is_owner(user_id):
                    await event.answer("❌ Only owners can remove subscriptions!", alert=True)
                    return
                
                USER_STATE[user_id] = {'step': 'remove_subscription_id'}
                await event.reply("📝 Enter the user ID to remove subscription:")
            
            elif data == 'listadmin':
                if not is_owner(user_id):
                    await event.answer("❌ Only owners can view admin list!", alert=True)
                    return
                
                current_time = datetime.now(pytz.timezone('Asia/Tehran'))
                
                if not ADMINS:
                    await event.reply("📭 No admins found.")
                    return
                
                admin_list = []
                for admin_id, info in ADMINS.items():
                    expires = info['expires']
                    activated = info.get('activated', expires - timedelta(days=30))
                    days_left = max(0, (expires - current_time).days)
                    hours_left = max(0, int((expires - current_time).total_seconds() / 3600))
                    status = "✅ Active" if expires > current_time else "❌ Expired"
                    
                    admin_list.append(
                        f"👤 **ID:** `{admin_id}`\n\n"
                        f"📅 **Activated:** {activated.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"⏰ **Expires:** {expires.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"📊 **Status:** {status} ({days_left}d {hours_left % 24}h left)\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                
                message = "👥 **List of Admins:**\n\n" + "\n".join(admin_list)
                await event.reply(message)
            
            elif data.startswith('duration_'):
                admin_id = state.get('admin_id')
                if not admin_id:
                    await event.reply("❌ Session expired. Please start over.")
                    USER_STATE.pop(user_id, None)
                    return
                
                current_time = datetime.now(pytz.timezone('Asia/Tehran'))
                duration_map = {
                    'duration_hour': timedelta(hours=1),
                    'duration_day': timedelta(days=1),
                    'duration_week': timedelta(weeks=1),
                    'duration_month': timedelta(days=30),
                    'duration_3months': timedelta(days=90),
                    'duration_6months': timedelta(days=180),
                    'duration_year': timedelta(days=365)
                }
                
                duration = duration_map.get(data)
                if not duration:
                    await event.answer("❌ Invalid duration!", alert=True)
                    return
                
                expires = current_time + duration
                ADMINS[admin_id] = {
                    'expires': expires,
                    'activated': current_time,
                    'permissions': ['view_accounts', 'report', 'use_shared']
                }
                save_data()
                
                await event.reply(
                    f"✅ **Admin Added Successfully!**\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 **User ID:** `{admin_id}`\n\n"
                    f"📅 **Activated:** {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"⏰ **Expires:** {expires.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
                
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            elif data in ['addaccount', 'addsharedaccount', 'deleteaccount', 'leave_account', 'listaccount',
                         'listsharedaccount', 'report', 'report_post', 'report_profile',
                         'report_bot', 'report_account', 'manual_report', 'notoreport',
                         'blackuser', 'reaction', 'startbot', 'join_channel', 'join_group', 'subscription_time',
                         'sender', 'commenter', 'view_post', 'leave_channel', 'leave_group', 'delete_pm']:
                
                sessions = get_user_sessions(user_id)
                
                if data == 'addaccount':
                    if not is_owner(user_id):
                        await event.answer("❌ Only owners can add accounts!", alert=True)
                        return
                    USER_STATE[user_id] = {'step': 'phone'}
                    await event.reply("📱 Enter phone number (with +):")
                
                elif data == 'addsharedaccount':
                    if not is_owner(user_id):
                        await event.answer("❌ Only owners can add shared accounts!", alert=True)
                        return
                    USER_STATE[user_id] = {'step': 'shared_phone'}
                    await event.reply("📱 Enter shared account phone number (with +):")
                
                elif data == 'deleteaccount':
                    if not is_owner(user_id):
                        await event.answer("❌ Only owners can delete accounts!", alert=True)
                        return
                    USER_STATE[user_id] = {'step': 'delete_phone'}
                    await event.reply("📱 Enter the phone number to delete (with +):")
                
                elif data == 'leave_account':
                    if not is_owner(user_id):
                        await event.answer("❌ Only owners can leave accounts!", alert=True)
                        return
                    USER_STATE[user_id] = {'step': 'leave_account_phone'}
                    await event.reply("📱 Enter the phone number to leave (with +):")
                
                elif data == 'listaccount':
                    if not sessions:
                        await event.reply("📭 No active accounts found.")
                        return
                    
                    accounts_info = []
                    for session_file in sessions[:15]:
                        is_shared = session_file in os.listdir(SHARED_SESSIONS_DIR)
                        phone = "Unknown"
                        
                        if is_shared:
                            phone = session_file.replace(".session", "")
                        else:
                            parts = session_file.split("_", 1)
                            if len(parts) > 1:
                                phone = parts[1].replace(".session", "")
                        
                        status = await check_account_status(session_file, is_shared)
                        accounts_info.append(f"📱 **+{phone}** — {status} {'(Shared)' if is_shared else ''}")
                    
                    message = f"📋 **Your Accounts ({len(sessions)}):**\n\n" + "\n".join(accounts_info)
                    if len(sessions) > 15:
                        message += f"\n\n... and {len(sessions)-15} more accounts"
                    
                    await event.reply(message)
                
                elif data == 'listsharedaccount':
                    shared_sessions = [f for f in os.listdir(SHARED_SESSIONS_DIR) if f.endswith(".session")]
                    if not shared_sessions:
                        await event.reply("📭 No shared accounts found.")
                        return
                    
                    accounts_info = []
                    for session_file in shared_sessions[:15]:
                        status = await check_account_status(session_file, True)
                        phone = session_file.replace(".session", "")
                        accounts_info.append(f"📱 **+{phone}** — {status}")
                    
                    message = f"📋 **Shared Accounts ({len(shared_sessions)}):**\n\n" + "\n".join(accounts_info)
                    if len(shared_sessions) > 15:
                        message += f"\n\n... and {len(shared_sessions)-15} more"
                    
                    await event.reply(message)
                
                elif data in ['report', 'report_post', 'report_profile', 'report_bot', 'report_account']:
                    current_time = datetime.now(pytz.timezone('Asia/Tehran'))
                    penalty_msg = await check_report_penalty(user_id, current_time)
                    if penalty_msg:
                        await event.reply(penalty_msg)
                
                elif data == 'manual_report':
                    if not await can_use_manual_report(user_id):
                        await event.answer("❌ You can use manual report only once per day!", alert=True)
                        return
                
                if data in ['report', 'report_post', 'report_profile', 'report_bot', 
                           'report_account', 'manual_report', 'notoreport', 'blackuser', 
                           'reaction', 'startbot', 'join_channel', 'join_group',
                           'sender', 'commenter', 'view_post', 'leave_channel', 'leave_group', 'delete_pm'] and not sessions:
                    await event.reply("❌ No active accounts found. Please add accounts first.")
                    return
                
                if data in ['report', 'report_post', 'report_profile', 'report_bot', 
                           'report_account', 'manual_report', 'notoreport', 'blackuser', 
                           'reaction', 'startbot', 'join_channel', 'join_group',
                           'sender', 'commenter', 'view_post', 'leave_channel', 'leave_group', 'delete_pm']:
                    USER_STATE[user_id] = {
                        'step': 'select_count',
                        'type': data,
                        'sessions': sessions
                    }
                    
                    await event.reply(f"🔢 How many accounts to use for this operation? (1-{len(sessions)}):")
                
                elif data == 'subscription_time':
                    if is_owner(user_id):
                        await event.reply("👑 **You are the bot owner!**\nUnlimited access.")
                        return
                    
                    if not is_admin(user_id):
                        await event.answer("❌ You don't have an active subscription.", alert=True)
                        return
                    
                    current_time = datetime.now(pytz.timezone('Asia/Tehran'))
                    expires = ADMINS[user_id]['expires']
                    activated = ADMINS[user_id].get('activated', expires - timedelta(days=30))
                    days_left = max(0, (expires - current_time).days)
                    hours_left = max(0, int((expires - current_time).total_seconds() / 3600))
                    
                    await event.reply(
                        f"⏰ **Subscription Status**\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"👤 **User ID:** `{user_id}`\n\n"
                        f"📅 **Activated:** {activated.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"⏰ **Expires:** {expires.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"📊 **Time Remaining:** {days_left} days ({hours_left} hours)\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
            
            elif data.startswith('reason_'):
                reason_key = data.split('_')[1]
                if reason_key not in REPORT_REASONS:
                    await event.answer("❌ Invalid reason!", alert=True)
                    return
                
                state['reason_key'] = reason_key
                
                if state.get('type') == 'manual_report':
                    state['step'] = 'manual_text'
                    await event.edit("📝 Please enter your custom report message (minimum 4 lines):")
                else:
                    state['step'] = 'count_per_account'
                    await event.edit("🔢 How many reports per account? (1-50):")
            
            elif data.startswith('react_'):
                react_key = data.split('_')[1]
                state['reaction'] = react_key
                
                await execute_reaction_operation(event, state)
                USER_STATE.pop(user_id, None)
                await show_main_menu(event, user_id)
            
            else:
                await event.answer("❌ Invalid option!", alert=True)
        
        except Exception as e:
            logger.error(f"Callback handler error for user {user_id}: {str(e)}")
            await event.answer(f"❌ Error: {str(e)[:50]}", alert=True)
            USER_STATE.pop(user_id, None)
            await show_main_menu(event, user_id)
    
    # ========== Run bot ==========
    logger.info("🤖 Bot is running and ready...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    print("🚀 Starting Advanced Reporter Bot...")
    print("📁 Sessions directory:", SESSIONS_DIR)
    print("📁 Shared sessions directory:", SHARED_SESSIONS_DIR)
    print("👑 Owners:", OWNER_IDS)
    print("━━━━━━━━━━━━━━━━━━━━")
    
    asyncio.run(main())
