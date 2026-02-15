import os
from telethon import TelegramClient, events, Button
import random
import re
from telethon.errors import SessionPasswordNeededError, MessageNotModifiedError
from telethon.tl.functions.messages import ReportRequest
import asyncio
from telethon.tl.types import (
    ReportResultChooseOption,
    ReportResultAddComment,
    ReportResultReported,
    InputReportReasonSpam,
    InputReportReasonFake,
    InputReportReasonPornography,
    InputReportReasonChildAbuse,
    InputReportReasonViolence,
    InputReportReasonIllegalDrugs,
    InputReportReasonOther
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError

api_id = 38105105
api_hash = "fc39cfe3faa8fec0a6ecf7513805ce2e"
bot_token = "8296567309:AAEEWurWS5TiKhcrOZrzejL4FOYdKvORICo"

allowed = [8405178472] #مالک ها اینجا بزار کسخل
user_state = {}
user_data = {}
global_busy = {
    "list_accounts": False,
    "report": False,
    "do_report": False,
    "clean_accounts": False,
    "join": False,
    "attack": False
}
cancel_flags = {}

if not os.path.exists("sessions"):
    os.makedirs("sessions")

bot = TelegramClient('report', api_id, api_hash).start(bot_token=bot_token)

REPORT_REASONS = {
    "dont_like": "I don't like it",
    "child_abuse": "Child abuse",
    "violence": "Violence",
    "illegal_goods": "Illegal goods",
    "pornography": "Illegal adult content",
    "personal_info": "Personal information",
    "terrorism": "Terrorism",
    "scam": "Scam or spam",
    "copyright": "Copyright violation",
    "other": "Other",
    "must_remove": "Not legal but must be removed"
}

SUB_REASONS = {
    "illegal_goods": {
        "weapon": "Weapons",
        "drugs": "Drugs",
        "fake_docs": "Fake documents",
        "counterfeit_money": "Counterfeit money",
        "other_goods": "Other goods"
    },
    "pornography": {
        "child": "Child abuse",
        "non_consent": "Non-consensual sexual content",
        "other_porn": "Other illegal sexual content"
    },
    "scam": {
        "phishing": "Phishing",
        "identity": "Identity theft",
        "fraud_sales": "Fraudulent sales",
        "spam": "Spam"
    },
    "personal_info": {
        "private_photos": "Private photos",
        "phone_number": "Phone number",
        "address": "Address",
        "other_info": "Other personal information"
    }
}

def create_client(session_name):
    return TelegramClient(
        session_name,
        api_id,
        api_hash,
        device_model="Samsung Galaxy A54",
        system_version="Android 14",
        app_version="11.13.3 (6081)",
        lang_code="en"
    )

def to_persian_numbers(num_str):
    return num_str.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

async def safe_edit(event, text, buttons=None):
    try:
        old = await event.get_message()
        if (old.message or "").strip() != text.strip() or old.buttons != buttons:
            await event.edit(text, buttons=buttons, parse_mode='markdown')
    except MessageNotModifiedError:
        pass

def main_menu():
    return (
        "**Hello, welcome to the bot!**",
        [
            [Button.inline("Add account", b"add_account"), Button.inline("Remove account", b"remove_account")],
            [Button.inline("List accounts", b"list_accounts"), Button.inline("Report operation", b"do_report")],
            [Button.inline("Join operation", b"do_join"), Button.inline("Attack operation", b"do_attack")]
        ]
    )

def code_keyboard():
    return [
        [Button.inline("1", b"code_1"), Button.inline("2", b"code_2"), Button.inline("3", b"code_3")],
        [Button.inline("4", b"code_4"), Button.inline("5", b"code_5"), Button.inline("6", b"code_6")],
        [Button.inline("7", b"code_7"), Button.inline("8", b"code_8"), Button.inline("9", b"code_9")],
        [Button.inline("Cancel", b"cancel_login"), Button.inline("0", b"code_0"), Button.inline("Submit", b"code_submit")],
    ]

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not event.is_private:
        return
    if event.sender_id not in allowed:
        return
    text, buttons = main_menu()
    await event.respond(text, buttons=buttons, parse_mode='markdown')

@bot.on(events.CallbackQuery(data=b"back_to_menu"))
async def back_to_menu(event):
    user_id = event.sender_id
    user_state[user_id] = None
    user_data.pop(user_id, None)
    text, buttons = main_menu()
    await safe_edit(event, text, buttons)

@bot.on(events.CallbackQuery(data=b"add_account"))
async def add_account(event):
    user_id = event.sender_id
    user_state[user_id] = "waiting_for_number"
    await safe_edit(
        event,
        "**Enter the account number in international format:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.CallbackQuery(data=b"remove_account"))
async def remove_account(event):
    user_id = event.sender_id
    user_state[user_id] = "waiting_for_remove_number"
    await safe_edit(
        event,
        "**Enter the number to remove:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.CallbackQuery(pattern=b"code_"))
async def code_input(event):
    user_id = event.sender_id
    if user_state.get(user_id) != "waiting_for_code":
        return
    digit = event.data.decode().split("_")[1]
    if digit.isdigit():
        user_data[user_id]["code"] += digit
        code_display = to_persian_numbers(user_data[user_id]["code"])
        await safe_edit(event, f"**A code has been sent to your number, enter your code!**\n**Entered code:** `{code_display}`", buttons=code_keyboard())

@bot.on(events.CallbackQuery(data=b"code_submit"))
async def submit_code(event):
    user_id = event.sender_id
    if user_state.get(user_id) != "waiting_for_code":
        return

    code = user_data[user_id]["code"]
    client = user_data[user_id]["client"]
    phone = user_data[user_id]["phone"]

    try:
        await client.sign_in(phone, code)
        await safe_edit(event, f"**Account {phone} logged in successfully!**", buttons=[[Button.inline("Back", b"back_to_menu")]])
        await client.disconnect()
        user_state[user_id] = None
        user_data.pop(user_id, None)
    except SessionPasswordNeededError:
        user_state[user_id] = "waiting_for_2fa"
        await safe_edit(event, "**This account has two-step verification! Please enter the password:**", buttons=[[Button.inline("Cancel", b"cancel_login")]])
    except Exception as e:
        await safe_edit(event, f"**Error during login!**", buttons=[[Button.inline("Back", b"back_to_menu")]])
        print(f"{e}")
        await client.disconnect()
        user_state[user_id] = None
        user_data.pop(user_id, None)

@bot.on(events.CallbackQuery(data=b"cancel_login"))
async def cancel_login(event):
    user_id = event.sender_id
    user_state[user_id] = None
    user_data.pop(user_id, None)
    await safe_edit(event, "**Canceled!**", buttons=[[Button.inline("Back", b"back_to_menu")]])

async def check_account(session_name):
    client = create_client(session_name)
    try:
        await client.connect()
        if await client.is_user_authorized():
            return session_name, True
        else:
            return session_name, False
    except Exception:
        return session_name, False
    finally:
        await client.disconnect()

@bot.on(events.CallbackQuery(data=b"list_accounts"))
async def list_accounts_handler(event):
    user_id = event.sender_id

    if any(global_busy.values()):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["list_accounts"] = True

    try:
        await event.edit("**Please wait...**")

        session_dir = "sessions"
        session_files = [f for f in os.listdir(session_dir) if f.endswith(".session")]
        tasks = [check_account(os.path.join(session_dir, f[:-8])) for f in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy = []
        broken = []

        for session_name, is_healthy in results:
            if isinstance(is_healthy, Exception):
                broken.append("+" + os.path.basename(session_name))
            else:
                phone = "+" + os.path.basename(session_name)
                if is_healthy:
                    healthy.append(phone)
                else:
                    broken.append(phone)

        total = len(healthy) + len(broken)

        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]["healthy_accounts"] = healthy

        await event.edit(
            f"""**Your account status:**

**Total accounts:** `{total}`
**Healthy accounts:** `{len(healthy)}`
**Unhealthy accounts:** `{len(broken)}`""",
            buttons=[
                [Button.inline("List healthy accounts", b"show_healthy_accounts")],
                [Button.inline("Clean unhealthy accounts", b"clean_bad_accounts")],
                [Button.inline("Back", b"back_to_menu")]
            ],
            parse_mode="markdown"
        )
    finally:
        global_busy["list_accounts"] = False

@bot.on(events.CallbackQuery(data=b"show_healthy_accounts"))
async def show_healthy_accounts(event):
    user_id = event.sender_id
    healthy = user_data.get(user_id, {}).get("healthy_accounts", [])

    if not healthy:
        await safe_edit(event, "**No healthy accounts found.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
        return

    text = "**List of healthy accounts:**\n\n" + "\n".join(healthy)
    await safe_edit(event, text, buttons=[[Button.inline("Back", b"back_to_menu")]])

async def clean_account(session_name, session_dir):
    session_path = os.path.join(session_dir, session_name + ".session")
    client = create_client(session_path)
    is_bad = False
    try:
        await client.connect()
        if not await client.is_user_authorized():
            is_bad = True
        else:
            return session_name, False
    except Exception:
        is_bad = True
    finally:
        await client.disconnect()

    if is_bad:
        try:
            os.remove(session_path)
            journal = session_path + "-journal"
            if os.path.exists(journal):
                os.remove(journal)
            return session_name, True
        except Exception as e:
            print(f"Error deleting {session_name}: {e}")
            return session_name, False
    return session_name, False

@bot.on(events.CallbackQuery(data=b"clean_bad_accounts"))
async def clean_bad_accounts_handler(event):
    if global_busy["report"] or global_busy["list_accounts"] or global_busy["do_report"] or global_busy["clean_accounts"]:
        await event.answer("Please wait until the previous operation is complete!", alert=True)
        return

    global_busy["clean_accounts"] = True

    try:
        await event.edit("**Please wait...**")

        session_dir = "sessions"
        session_files = [f[:-8] for f in os.listdir(session_dir) if f.endswith(".session")]
        tasks = [clean_account(session_name, session_dir) for session_name in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        deleted = []
        kept = []

        for session_name, was_deleted in results:
            if isinstance(was_deleted, Exception):
                kept.append("+" + session_name)
            elif was_deleted:
                deleted.append("+" + session_name)
            else:
                kept.append("+" + session_name)

        await event.edit(
            f"""**Cleanup results:**

**Deleted accounts:** `{len(deleted)}`
**Remaining accounts:** `{len(kept)}`""",
            buttons=[[Button.inline("Back", b"back_to_menu")]],
            parse_mode="markdown"
        )

    finally:
        global_busy["clean_accounts"] = False

async def get_healthy_account(session_name):
    client = create_client(session_name)
    try:
        await client.connect()
        if await client.is_user_authorized():
            return "+" + os.path.basename(session_name)
        return None
    except Exception:
        return None
    finally:
        await client.disconnect()

@bot.on(events.CallbackQuery(data=b"do_report"))
async def do_report_handler(event):
    user_id = event.sender_id

    if any(global_busy.values()):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["do_report"] = True

    try:
        await event.edit("**Please wait...**")

        session_dir = "sessions"
        session_files = [os.path.join(session_dir, f[:-8]) for f in os.listdir(session_dir) if f.endswith(".session")]
        tasks = [get_healthy_account(session_name) for session_name in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_accounts = [r for r in results if r and not isinstance(r, Exception)]

        if not healthy_accounts:
            await event.edit("**No healthy accounts found for reporting.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]["healthy_accounts"] = healthy_accounts
        user_data[user_id]["report_total"] = len(healthy_accounts)
        user_state[user_id] = "choose_report_count"

        await event.edit(
            "**Please specify the number of accounts for reporting:**",
            buttons=[
                [Button.inline("All accounts", b"report_all"), Button.inline("Custom number", b"report_custom")],
                [Button.inline("Back", b"back_to_menu")]
            ]
        )

    finally:
        global_busy["do_report"] = False

@bot.on(events.CallbackQuery(data=b"report_custom"))
async def report_custom_count(event):
    user_id = event.sender_id
    total = user_data[user_id]["report_total"]

    user_state[user_id] = "waiting_for_report_count"

    await safe_edit(
        event,
        f"**Enter the desired number from {total}:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.NewMessage)
async def handle_message(event):
    user_id = event.sender_id

    if not event.is_private:
        return
    if user_id not in allowed:
        return

    state = user_state.get(user_id)
    if not state:
        return

    if state == "waiting_for_number":
        phone = event.raw_text.strip()
        if not phone.startswith("+") or not phone[1:].isdigit():
            await event.respond("**Invalid number!**", parse_mode='markdown')
            return

        session_path = os.path.join("sessions", phone.replace("+", ""))
        client = create_client(session_path)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            user_data[user_id] = {
                "client": client,
                "phone": phone,
                "session": session_path,
                "code": "",
                "sent": sent
            }
            user_state[user_id] = "waiting_for_code"
            await event.respond(
                "**A code has been sent to your number, enter your code!**\n**Entered code:**",
                buttons=code_keyboard(),
                parse_mode='markdown'
            )
        except Exception as e:
            await event.respond("**Error sending code!**", parse_mode='markdown')
            print(e)
            await client.disconnect()
            user_state[user_id] = None

    elif state == "waiting_for_remove_number":
        phone = event.raw_text.strip().replace("+", "")
        session_path = os.path.join("sessions", phone + ".session")

        if os.path.exists(session_path):
            os.remove(session_path)
            journal = session_path + "-journal"
            if os.path.exists(journal):
                os.remove(journal)
            await event.respond("**Removed!**", buttons=[[Button.inline("Back", b"back_to_menu")]], parse_mode='markdown')
        else:
            await event.respond("**Does not exist!**", buttons=[[Button.inline("Back", b"back_to_menu")]], parse_mode='markdown')

        user_state[user_id] = None

    elif state == "waiting_for_2fa":
        password = event.raw_text.strip()
        client = user_data[user_id]["client"]
        try:
            await client.sign_in(password=password)
            await event.respond("**Account logged in successfully!**", buttons=[[Button.inline("Back", b"back_to_menu")]], parse_mode='markdown')
            await client.disconnect()
        except Exception as e:
            await event.respond("**Error in two-step password!**", parse_mode='markdown')
            print(e)
            await client.disconnect()
        user_state[user_id] = None
        user_data.pop(user_id, None)

    elif state == "waiting_for_report_count":
        try:
            requested = int(event.raw_text.strip())
            max_count = user_data[user_id]["report_total"]
            if requested <= 0 or requested > max_count:
                raise ValueError()
            user_data[user_id]["report_count"] = requested
            user_state[user_id] = "choose_report_reason"
            await event.respond(
                "**Select your report reason:**",
                buttons=[
                    [Button.inline(REPORT_REASONS["child_abuse"], b"reason_child_abuse"), Button.inline(REPORT_REASONS["violence"], b"reason_violence")],
                    [Button.inline(REPORT_REASONS["illegal_goods"], b"reason_illegal_goods"), Button.inline(REPORT_REASONS["pornography"], b"reason_pornography")],
                    [Button.inline(REPORT_REASONS["scam"], b"reason_scam"), Button.inline(REPORT_REASONS["copyright"], b"reason_copyright")],
                    [Button.inline(REPORT_REASONS["personal_info"], b"reason_personal_info"), Button.inline(REPORT_REASONS["other"], b"reason_other")],
                    [Button.inline("Back", b"back_to_menu")]
                ]
            )
        except ValueError:
            await event.respond("**Invalid number! Please enter only a number.**")

    elif state == "waiting_for_report_text":
        report_text = event.raw_text.strip()
        if len(report_text) < 3:
            await event.respond("**Text is too short. Please enter a more complete text.**")
            return
        user_data[user_id]["report_text"] = report_text
        user_state[user_id] = "waiting_for_repeat_count"
        await event.respond(
            "**Then send the number of reports:**",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

    elif state == "waiting_for_repeat_count":
        try:
            repeat_count = int(event.raw_text.strip())
            if repeat_count <= 0:
                raise ValueError()
            user_data[user_id]["report_repeat"] = repeat_count
            user_state[user_id] = "waiting_for_post_count"
            await event.respond(
                "**How many posts do you want to report? Or use the button below:**",
                buttons=[
                    [Button.inline("All posts", b"report_all_posts")],
                    [Button.inline("Back", b"back_to_menu")]
                ]
            )
        except ValueError:
            await event.respond("**Invalid number!**")

    elif state == "waiting_for_post_count":
        raw = event.raw_text.strip()

        match = re.match(r"https?://t\.me/([\w\d_]+)/(\d+)", raw)
        if match:
            username = "@" + match.group(1)
            post_id = int(match.group(2))

            user_data[user_id]["target_channel"] = username
            user_data[user_id]["specific_post_id"] = post_id
            user_data[user_id]["post_count"] = 1
            user_state[user_id] = None

            op_id = f"{user_id}_{random.randint(100,999)}"
            cancel_flags[op_id] = False
            cancel_cmd = f"/cancel{op_id}"

            await event.respond(
                f"**Details saved successfully, performing report operation, please wait...**\n"
                f"To cancel the operation, send the following command:\n`{cancel_cmd}`"
            )
            await perform_report_operation(user_id, event, op_id)
            return

        if raw.lower() in ["all", "تمام", "all posts"]:
            user_data[user_id]["post_count"] = "all"
            user_state[user_id] = "waiting_for_channel_username"
            await event.respond(
                "**Now send the username of the public channel you want to report:**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
            return

        try:
            post_count = int(raw)
            if post_count <= 0:
                raise ValueError()
            user_data[user_id]["post_count"] = post_count
            user_state[user_id] = "waiting_for_channel_username"
            await event.respond(
                "**Now send the username of the public channel you want to report:**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
        except ValueError:
            await event.respond("**Invalid number or unrecognized link/command!**")

    elif state == "waiting_for_channel_username":
        username = event.raw_text.strip()
        if not username.startswith("@") or len(username) < 5:
            await event.respond("**Invalid username! Example: `@examplechannel`**")
            return
        user_data[user_id]["target_channel"] = username
        user_state[user_id] = None

        op_id = f"{user_id}_{random.randint(100,999)}"
        cancel_flags[op_id] = False
        cancel_cmd = f"/cancel{op_id}"

        await event.respond(
            f"**Details saved successfully, performing report operation, please wait...**\n\n"
            f"**To cancel the operation, send the following command:**\n{cancel_cmd}"
        )
        await perform_report_operation(user_id, event, op_id)

    elif state == "waiting_for_join_count":
        try:
            requested = int(event.raw_text.strip())
            max_count = user_data[user_id]["join_total"]
            if requested <= 0 or requested > max_count:
                raise ValueError()
            user_data[user_id]["join_count"] = requested
            user_state[user_id] = "waiting_for_join_channel"
            await event.respond(
                "**Enter the username of the channel or group to join:**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
        except ValueError:
            await event.respond("**Invalid number!**")

    elif state == "waiting_for_join_channel":
        username = event.raw_text.strip()
        if not username.startswith("@") or len(username) < 5:
            await event.respond("**Invalid username! Example: `@examplechannel`**")
            return

        user_data[user_id]["target_channel"] = username
        user_state[user_id] = None

        op_id = f"{user_id}_{random.randint(100,999)}"
        cancel_flags[op_id] = False
        cancel_cmd = f"/cancel{op_id}"

        await event.respond(
            f"**Details saved successfully, performing join operation, please wait...**\n\n"
            f"**To cancel the operation, send the following command:**\n{cancel_cmd}"
        )
        await perform_join_operation(user_id, event, op_id)

    elif state == "waiting_for_attack_count":
        try:
            requested = int(event.raw_text.strip())
            max_count = user_data[user_id]["attack_total"]
            if requested <= 0 or requested > max_count:
                raise ValueError()
            user_data[user_id]["attack_count"] = requested
            user_state[user_id] = "waiting_for_attack_sends"
            await event.respond(
                "**Enter the number of sends per account:**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
        except ValueError:
            await event.respond("**Invalid number!**")

    elif state == "waiting_for_attack_sends":
        try:
            send_count = int(event.raw_text.strip())
            if send_count <= 0:
                raise ValueError()
            user_data[user_id]["attack_sends"] = send_count
            user_state[user_id] = "waiting_for_attack_group"
            await event.respond(
                "**Send the username of the target group (accounts must be members of that group):**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
        except ValueError:
            await event.respond("**Invalid number!**")

    elif state == "waiting_for_attack_group":
        username = event.raw_text.strip()
        if not username.startswith("@") or len(username) < 5:
            await event.respond("**Invalid username! Example: `@examplegroup`**")
            return
        user_data[user_id]["target_group"] = username
        user_state[user_id] = None

        op_id = f"{user_id}_{random.randint(100,999)}"
        cancel_flags[op_id] = False
        cancel_cmd = f"/cancel{op_id}"

        await event.respond(
            f"**Details saved successfully, performing attack operation, please wait...**\n\n"
            f"**To cancel the operation, send the following command:**\n{cancel_cmd}"
        )
        await perform_attack_operation(user_id, event, op_id)

@bot.on(events.CallbackQuery(data=b"report_all_posts"))
async def handle_all_posts_button(event):
    user_id = event.sender_id

    user_data[user_id]["post_count"] = "all"
    user_state[user_id] = "waiting_for_channel_username"

    await event.edit(
        "**Now send the username of the public channel you want to report:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.CallbackQuery(data=b"report_all"))
async def report_all_handler(event):
    user_id = event.sender_id
    total = user_data.get(user_id, {}).get("report_total", 0)

    user_data[user_id]["report_count"] = total
    user_state[user_id] = "choose_report_reason"

    await event.edit(
        "**Select your report reason:**",
        buttons=[
            [Button.inline("Child abuse", b"reason_child_abuse"), Button.inline("Violence", b"reason_violence")],
            [Button.inline("Illegal goods", b"reason_illegal_goods"), Button.inline("Illegal adult content", b"reason_pornography")],
            [Button.inline("Scam or spam", b"reason_scam"), Button.inline("Copyright violation", b"reason_copyright")],
            [Button.inline("Personal information", b"reason_personal_info"), Button.inline("Terrorism", b"reason_terrorism")],
            [Button.inline("Other", b"reason_other"), Button.inline("Must be removed", b"reason_must_remove")],
            [Button.inline("Back", b"back_to_menu")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"reason_"))
async def report_reason_handler(event):
    user_id = event.sender_id
    reason_key = event.data.decode().split("_", 1)[1]

    if reason_key not in REPORT_REASONS:
        await safe_edit(event, "**Invalid reason.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
        return

    user_data[user_id]["report_reason"] = reason_key

    if reason_key in SUB_REASONS:
        sub_buttons = [
            [Button.inline(v, f"subreason_{reason_key}_{k}".encode())]
            for k, v in SUB_REASONS[reason_key].items()
        ]
        sub_buttons.append([Button.inline("Back", b"back_to_menu")])

        user_state[user_id] = "waiting_for_subreason"

        await safe_edit(
            event,
            "**Select your reason:**",
            buttons=sub_buttons
        )
    else:
        user_state[user_id] = "waiting_for_report_text"

        await safe_edit(
            event,
            "**Send your report text:**",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

@bot.on(events.CallbackQuery(pattern=b"subreason_"))
async def subreason_handler(event):
    user_id = event.sender_id
    try:
        data_str = event.data.decode()

        assert data_str.startswith("subreason_")
        rest = data_str[len("subreason_"):]

        main_key = None
        for key in SUB_REASONS:
            prefix = key + "_"
            if rest.startswith(prefix):
                main_key = key
                sub_key = rest[len(prefix):]
                break

        if not main_key:
            raise ValueError(f"{rest}'")

        if sub_key not in SUB_REASONS[main_key]:
            raise ValueError(f"Subkey '{sub_key}' not found in group '{main_key}'")

        user_data[user_id]["report_subreason"] = sub_key
        user_state[user_id] = "waiting_for_report_text"

        await safe_edit(
            event,
            "**Send your report text:**",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

    except Exception as e:
        print(f"{e}")
        await safe_edit(
            event,
            "**Invalid subreason.**",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

def get_report_reason(reason_key):
    reasons_map = {
        "scam": InputReportReasonFake,
        "pornography": InputReportReasonPornography,
        "child_abuse": InputReportReasonChildAbuse,
        "violence": InputReportReasonViolence,
        "illegal_goods": InputReportReasonIllegalDrugs,
        "personal_info": InputReportReasonOther,
        "other": InputReportReasonOther
    }
    return reasons_map.get(reason_key, InputReportReasonSpam)()

SUB_MATCHES = {
    "weapon": ["weapon"],
    "drugs": ["drug"],
    "fake_docs": ["document"],
    "counterfeit_money": ["counterfeit"],
    "other_goods": ["other goods", "banned"],

    "child": ["child"],
    "non_consent": ["non-consensual", "without consent"],
    "other_porn": ["other illegal sexual", "sexual", "explicit"],

    "private_photos": ["private image", "private"],
    "phone_number": ["phone"],
    "address": ["address"],
    "other_info": ["other personal"],

    "phishing": ["phishing"],
    "identity": ["impersonation", "identity"],
    "fraud_sales": ["fraud", "sales"],
    "spam": ["spam"],

    "child_abuse": ["child"],
    "violence": ["violence"],
    "illegal_goods": ["illegal goods", "weapons", "drugs"],
    "pornography": ["sexual", "adult", "explicit", "illegal adult"],
    "personal_info": ["personal data", "private", "info"],
    "terrorism": ["terrorism"],
    "scam": ["scam", "fraud", "spam"],
    "copyright": ["copyright"],
    "other": ["other"],
    "dont_like": ["don’t like"],
    "must_remove": ["must be taken down", "not illegal"]
}

async def report_with_account(phone, channel_username, text, repeat, post_limit, specific_id, report_main, report_sub, op_id):
    session_path = os.path.join("sessions", phone.replace("+", ""))
    client = create_client(session_path)
    success_count = 0
    fail_count = 0
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise Exception("Account not logged in!")

        entity = await client.get_entity(channel_username)
        valid_posts = []

        if specific_id:
            valid_posts = [specific_id]
        else:
            max_count = None if post_limit == "all" else int(post_limit)
            async for msg in client.iter_messages(entity, limit=max_count):
                if msg and (msg.message or msg.media):
                    valid_posts.append(msg.id)
                if max_count and len(valid_posts) >= max_count:
                    break

        if not valid_posts:
            raise Exception("No reportable posts found!")

        for msg_id in valid_posts:
            if cancel_flags.get(op_id):
                break

            for _ in range(repeat):
                if cancel_flags.get(op_id):
                    break

                try:
                    step1 = await client(ReportRequest(
                        peer=entity,
                        id=[msg_id],
                        option=b'',
                        message=text
                    ))

                    if not isinstance(step1, ReportResultChooseOption):
                        raise Exception("Expected ChooseOption, got something else")

                    main_option = None
                    keywords = SUB_MATCHES.get(report_main, [report_main])
                    for opt in step1.options:
                        if any(k in opt.text.lower() for k in keywords):
                            main_option = opt.option
                            break

                    if not main_option:
                        raise Exception("Main option not found!")

                    step2 = await client(ReportRequest(
                        peer=entity,
                        id=[msg_id],
                        option=main_option,
                        message=text
                    ))

                    final = step2
                    if isinstance(step2, ReportResultAddComment):
                        final = await client(ReportRequest(
                            peer=entity,
                            id=[msg_id],
                            option=step2.option,
                            message=text
                        ))

                    elif isinstance(step2, ReportResultChooseOption):
                        sub_option = None
                        sub_keywords = SUB_MATCHES.get(report_sub, [])

                        for opt in step2.options:
                            if any(k in opt.text.lower() for k in sub_keywords):
                                sub_option = opt.option
                                break

                        if not sub_option and step2.options:
                            sub_option = step2.options[0].option

                        if not sub_option:
                            raise Exception("Subreason not found!")

                        step3 = await client(ReportRequest(
                            peer=entity,
                            id=[msg_id],
                            option=sub_option,
                            message=text
                        ))

                        final = step3
                        if isinstance(step3, ReportResultAddComment):
                            final = await client(ReportRequest(
                                peer=entity,
                                id=[msg_id],
                                option=step3.option,
                                message=text
                            ))

                    if isinstance(final, ReportResultReported):
                        success_count += 1
                    else:
                        fail_count += 1

                except Exception as e:
                    print(f"[{phone}] {e}")
                    fail_count += 1

        await client.disconnect()
        return phone, success_count, fail_count
    except Exception as e:
        print(f"[{phone}] {e}")
        fail_count += 1
        try:
            await client.disconnect()
        except:
            pass
        return phone, success_count, fail_count

async def perform_report_operation(user_id, event, op_id):
    if global_busy["report"]:
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["report"] = True
    try:
        data = user_data.get(user_id)
        if not data:
            await event.respond(
                "**Incomplete information. Operation canceled.**",
                buttons=[[Button.inline("Back", b"back_to_menu")]]
            )
            return

        accounts = data["healthy_accounts"][:data["report_count"]]
        channel_username = data["target_channel"]
        text = data["report_text"]
        repeat = data["report_repeat"]
        post_limit = data["post_count"]
        specific_id = data.get("specific_post_id")
        report_main = data["report_reason"]
        report_sub = data.get("report_subreason")

        tasks = [
            report_with_account(
                phone, channel_username, text, repeat, post_limit,
                specific_id, report_main, report_sub, op_id
            ) for phone in accounts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_success = 0
        total_fail = 0
        used_accounts = []
        account_success_map = {}

        for result in results:
            if isinstance(result, Exception):
                total_fail += 1
                continue
            phone, success_count, fail_count = result
            used_accounts.append(phone)
            total_success += success_count
            total_fail += fail_count
            if success_count > 0:
                account_success_map[phone] = success_count

        if cancel_flags.get(op_id):
            await event.respond("**Operation canceled!**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        success_accounts = sum(1 for acc in used_accounts if account_success_map.get(acc, 0) > 0)
        failed_accounts = len(used_accounts) - success_accounts

        await event.respond(
            f"""**Report operation completed!**

**Total accounts used:** `{len(used_accounts)}`
**Successful accounts:** `{success_accounts}`
**Failed accounts:** `{failed_accounts}`

**Successful reports:** `{total_success}`
**Failed reports:** `{total_fail}`""",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

    finally:
        global_busy["report"] = False
        cancel_flags.pop(op_id, None)

@bot.on(events.NewMessage(pattern=r"^/cancel(\d+_\d+)$"))
async def cancel_handler(event):
    op_id = event.pattern_match.group(1)
    if op_id in cancel_flags:
        cancel_flags[op_id] = True
    else:
        await event.respond("**Operation not found or already completed.**")

async def join_with_account(phone, target, op_id):
    session_path = os.path.join("sessions", phone.replace("+", ""))
    client = create_client(session_path)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise Exception("Account not logged in!")

        try:
            await client(JoinChannelRequest(target))
            return phone, True
        except UserAlreadyParticipantError:
            return phone, True
        except Exception as e:
            print(f"[{phone}] Error: {e}")
            return phone, False
        finally:
            await client.disconnect()
    except Exception as e:
        print(f"[{phone}] {e}")
        try:
            await client.disconnect()
        except:
            pass
        return phone, False

@bot.on(events.CallbackQuery(data=b"do_join"))
async def do_join_handler(event):
    user_id = event.sender_id

    if any(global_busy.values()):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["do_join"] = True

    try:
        await event.edit("**Please wait...**")

        session_dir = "sessions"
        session_files = [os.path.join(session_dir, f[:-8]) for f in os.listdir(session_dir) if f.endswith(".session")]
        tasks = [get_healthy_account(session_name) for session_name in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_accounts = [r for r in results if r and not isinstance(r, Exception)]

        if not healthy_accounts:
            await event.edit("**No healthy accounts found for joining.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]["healthy_accounts"] = healthy_accounts
        user_data[user_id]["join_total"] = len(healthy_accounts)
        user_state[user_id] = "choose_join_count"

        await event.edit(
            "**Please specify the number of accounts for joining:**",
            buttons=[
                [Button.inline("All accounts", b"join_all"), Button.inline("Custom number", b"join_custom")],
                [Button.inline("Back", b"back_to_menu")]
            ]
        )

    finally:
        global_busy["do_join"] = False

@bot.on(events.CallbackQuery(data=b"join_all"))
async def join_all_handler(event):
    user_id = event.sender_id
    total = user_data.get(user_id, {}).get("join_total", 0)

    user_data[user_id]["join_count"] = total
    user_state[user_id] = "waiting_for_join_channel"

    await event.edit(
        "**Enter the username of the channel or group to join:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.CallbackQuery(data=b"join_custom"))
async def join_custom_handler(event):
    user_id = event.sender_id
    total = user_data[user_id]["join_total"]

    user_state[user_id] = "waiting_for_join_count"

    await safe_edit(
        event,
        f"**Enter the desired number from {total}:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

async def perform_join_operation(user_id, event, op_id):
    if global_busy.get("join", False):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["join"] = True
    try:
        data = user_data.get(user_id)
        if not data:
            await event.respond("**Incomplete information. Operation canceled.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        accounts = data["healthy_accounts"][:data["join_count"]]
        target = data["target_channel"]

        tasks = [join_with_account(phone, target, op_id) for phone in accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        joined_accounts = []

        for result in results:
            if isinstance(result, Exception):
                continue
            phone, success = result
            if success:
                joined_accounts.append(phone)

        if cancel_flags.get(op_id):
            await event.respond("**Operation canceled!**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        user_data[user_id]["joined_accounts"] = joined_accounts

        await event.respond(
            f"""**Join operation completed!**

**Number of joined accounts:** `{len(joined_accounts)}`""",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

    finally:
        global_busy["join"] = False
        cancel_flags.pop(op_id, None)

@bot.on(events.CallbackQuery(data=b"do_attack"))
async def do_attack_handler(event):
    user_id = event.sender_id

    if any(global_busy.values()):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["do_attack"] = True

    try:
        await event.edit("**Please wait...**")

        session_dir = "sessions"
        session_files = [os.path.join(session_dir, f[:-8]) for f in os.listdir(session_dir) if f.endswith(".session")]
        tasks = [get_healthy_account(session_name) for session_name in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_accounts = [r for r in results if r and not isinstance(r, Exception)]

        if not healthy_accounts:
            await event.edit("**No healthy accounts found for attack.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]["healthy_accounts"] = healthy_accounts
        user_data[user_id]["attack_total"] = len(healthy_accounts)
        user_state[user_id] = "choose_attack_count"

        await event.edit(
            "**Select the number of accounts:**",
            buttons=[
                [Button.inline("All accounts", b"attack_all"), Button.inline("Custom number", b"attack_custom")],
                [Button.inline("Back", b"back_to_menu")]
            ]
        )

    finally:
        global_busy["do_attack"] = False

@bot.on(events.CallbackQuery(data=b"attack_all"))
async def attack_all_handler(event):
    user_id = event.sender_id
    total = user_data.get(user_id, {}).get("attack_total", 0)

    user_data[user_id]["attack_count"] = total
    user_state[user_id] = "waiting_for_attack_sends"

    await event.edit(
        "**Enter the number of sends per account:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

@bot.on(events.CallbackQuery(data=b"attack_custom"))
async def attack_custom_handler(event):
    user_id = event.sender_id
    total = user_data[user_id]["attack_total"]

    user_state[user_id] = "waiting_for_attack_count"

    await safe_edit(
        event,
        f"**Enter the desired number from {total}:**",
        buttons=[[Button.inline("Back", b"back_to_menu")]]
    )

async def attack_with_account(phone, target_group, send_count, op_id):
    session_path = os.path.join("sessions", phone.replace("+", ""))
    client = create_client(session_path)
    success_count = 0
    fail_count = 0
    source_channel = -1003738807184

    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise Exception("Account not logged in!")

        group_entity = await client.get_entity(target_group)
        channel_entity = await client.get_entity(source_channel)

        messages = []
        async for msg in client.iter_messages(channel_entity, limit=100):
            if msg.message or msg.media:
                messages.append(msg)
            if len(messages) >= send_count:
                break

        if not messages:
            raise Exception("No messages found in the source channel!")

        for _ in range(send_count):
            if cancel_flags.get(op_id):
                break

            msg = random.choice(messages)
            try:
                if msg.media:
                    await client.send_message(group_entity, file=msg.media)
                elif msg.message:
                    await client.send_message(group_entity, message=msg.message)
                success_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[{phone}] Error sending message: {e}")
                fail_count += 1
                await asyncio.sleep(0.5)

        await client.disconnect()
        return phone, success_count, fail_count

    except Exception as e:
        print(f"[{phone}] {e}")
        fail_count += send_count
        try:
            await client.disconnect()
        except:
            pass
        return phone, success_count, fail_count

async def perform_attack_operation(user_id, event, op_id):
    if global_busy.get("attack", False):
        await event.answer("Another operation is in progress!", alert=True)
        return

    global_busy["attack"] = True
    try:
        data = user_data.get(user_id)
        if not data:
            await event.respond("**Incomplete information. Operation canceled.**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        accounts = data["healthy_accounts"][:data["attack_count"]]
        target_group = data["target_group"]
        send_count = data["attack_sends"]

        tasks = [attack_with_account(phone, target_group, send_count, op_id) for phone in accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_success = 0
        total_fail = 0
        used_accounts = []
        account_success_map = {}

        for result in results:
            if isinstance(result, Exception):
                total_fail += send_count
                continue
            phone, success_count, fail_count = result
            used_accounts.append(phone)
            total_success += success_count
            total_fail += fail_count
            account_success_map[phone] = success_count

        if cancel_flags.get(op_id):
            await event.respond("**Operation canceled!**", buttons=[[Button.inline("Back", b"back_to_menu")]])
            return

        success_accounts = sum(1 for acc in used_accounts if account_success_map.get(acc, 0) == send_count)
        failed_accounts = len(used_accounts) - success_accounts

        await event.respond(
            f"""**Operation completed successfully!**

**Accounts used:** `{len(used_accounts)}`
**Successful accounts:** `{success_accounts}`
**Failed accounts:** `{failed_accounts}`

**Successful sends:** `{total_success}`
**Failed sends:** `{total_fail}`""",
            buttons=[[Button.inline("Back", b"back_to_menu")]]
        )

    finally:
        global_busy["attack"] = False
        cancel_flags.pop(op_id, None)

print("Running!")
bot.run_until_disconnected()