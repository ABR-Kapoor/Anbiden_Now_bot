import asyncio
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, Application
)
from config import BOT_TOKEN, DATABASE_URL
import db

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for user info collection
ASK_NAME, ASK_AGE, ASK_INTEREST = range(3)

# Fast transient state for matchmaking
active_chats = {}        # Maps user_id to current partner user_id
waiting_list = []        # Users waiting for connection

async def setup(app: Application):
    """Post initialization to set up DB pool."""
    logger.info("Setting up database pool...")
    pool = await db.get_db_pool(DATABASE_URL)
    await db.init_db(pool)
    app.bot_data['db_pool'] = pool

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pool = context.bot_data['db_pool']
    
    user = await db.get_user(pool, user_id)

    if user:
        await update.message.reply_text("👋 Welcome back! Use /next to find a partner.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("👋 Welcome! Let's set up your profile.\nWhat’s your name?")
        return ASK_NAME

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Bot Commands:*\n"
        "/start - Start or setup your profile\n"
        "/next - Connect with a new partner\n"
        "/stop - Leave current chat\n"
        "/help - Show this message",
        parse_mode="Markdown"
    )

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("🎂 Age?")
    return ASK_AGE

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = update.message.text.strip()
    if not age.isdigit():
        await update.message.reply_text("⚠️ Enter a valid number.")
        return ASK_AGE
    context.user_data["age"] = int(age)
    await update.message.reply_text("🎯 Interests? (comma separated)")
    return ASK_INTEREST

async def ask_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    interests = update.message.text.strip()
    user_id = update.effective_user.id
    
    name = context.user_data.get("name")
    age = context.user_data.get("age")
    
    pool = context.bot_data['db_pool']
    await db.save_user(pool, user_id, name, age, interests)
    
    await update.message.reply_text("✅ Profile saved!\nUse /next to meet someone new.")
    return ConversationHandler.END

async def connect_users(user_id, context: ContextTypes.DEFAULT_TYPE):
    if user_id not in waiting_list:
        waiting_list.append(user_id)

    if len(waiting_list) >= 2:
        u1 = waiting_list.pop(0)
        u2 = waiting_list.pop(0)

        active_chats[u1] = u2
        active_chats[u2] = u1

        pool = context.bot_data['db_pool']
        u1_data = await db.get_user(pool, u2)  # Partner connected to u1 is u2
        u2_data = await db.get_user(pool, u1)  # Partner connected to u2 is u1

        msg1 = f"🔗 Connected!\n👤 *{u1_data['name']}*, {u1_data['age']} y/o\n🎯 Interests: {u1_data['interests']}"
        msg2 = f"🔗 Connected!\n👤 *{u2_data['name']}*, {u2_data['age']} y/o\n🎯 Interests: {u2_data['interests']}"

        for uid, msg in [(u1, msg1), (u2, msg2)]:
            try:
                await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
                await asyncio.sleep(1.0)
                await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to message {uid}: {e}")

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Disconnect from current partner if any
    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        if partner in active_chats:
            del active_chats[partner]
            try:
                await context.bot.send_message(chat_id=partner, text="⚠️ Your partner left the chat.")
            except:
                pass

    if user_id in waiting_list:
        waiting_list.remove(user_id)

    await context.bot.send_message(chat_id=user_id, text="🔍 Looking for a new partner...")
    await connect_users(user_id, context)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in waiting_list:
        waiting_list.remove(user_id)

    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        if partner in active_chats:
            del active_chats[partner]
            try:
                await context.bot.send_message(chat_id=partner, text="⚠️ Your partner left the chat.")
            except:
                pass

    await update.message.reply_text("❌ You left the chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    partner = active_chats.get(sender)

    if partner:
        await context.bot.send_chat_action(chat_id=partner, action=ChatAction.TYPING)
        await asyncio.sleep(0.5)
        try:
            await context.bot.send_message(chat_id=partner, text=update.message.text)
        except Exception as e:
            logger.error(f"Could not send message to {partner}: {e}")
    else:
        await update.message.reply_text("⚠️ You are not connected. Use /next to find a partner.")

async def forward_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    partner = active_chats.get(sender)

    if partner:
        await context.bot.send_chat_action(chat_id=partner, action=ChatAction.UPLOAD_PHOTO)
        try:
            await context.bot.copy_message(chat_id=partner, from_chat_id=sender, message_id=update.message.message_id)
        except:
            pass

async def forward_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    partner = active_chats.get(sender)

    if partner:
        await context.bot.send_chat_action(chat_id=partner, action=ChatAction.CHOOSE_STICKER)
        try:
            await context.bot.copy_message(chat_id=partner, from_chat_id=sender, message_id=update.message.message_id)
        except:
            pass

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        exit(1)
        
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup).build()

    # Conversation to setup profile
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ASK_INTEREST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_interest)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, forward_photo))
    app.add_handler(MessageHandler(filters.Sticker.ALL, forward_sticker))

    logger.info("🚀 Bot is running...")
    app.run_polling()
