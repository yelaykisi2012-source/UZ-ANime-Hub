import logging
import asyncio
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)
import config
import database as db

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------- Yordamchi funksiyalar -----------------
async def is_subscribed(user_id, channel, context):
    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def check_channels(user_id, context):
    for ch in config.REQUIRED_CHANNELS:
        if not await is_subscribed(user_id, ch, context):
            return False
    return True

# ----------------- Qismlarni ko‘rsatish -----------------
async def show_episodes(update, context, series_code, series_data, user_id):
    episodes = await db.get_episodes(series_code)
    if not episodes:
        await update.message.reply_text("Bu seriyada hali qismlar mavjud emas.")
        return

    is_premium_user = await db.check_premium(user_id)
    title = series_data[1]  # series.title

    buttons = []
    row = []
    for ep in episodes:
        ep_num, file_id, is_premium_ep, views = ep
        if not is_premium_user and is_premium_ep:
            button_text = f"{ep_num}🔒"
        else:
            button_text = str(ep_num)
        button = InlineKeyboardButton(button_text, callback_data=f"ep:{series_code}:{ep_num}")
        row.append(button)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    caption = f"🎬 *{title}* – qismlarni tanlang:"
    if not is_premium_user:
        caption += "\n\n🔒 bilan belgilangan qismlar faqat Premium foydalanuvchilar uchun."

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)

# ----------------- Qismni qayta ishlash -----------------
async def process_episode(user_id, series_code, episode_number, context, message=None, query=None):
    episode = await db.get_episode(series_code, episode_number)
    if not episode:
        if message:
            await message.reply_text("❌ Bunday qism topilmadi.")
        elif query:
            await query.message.reply_text("❌ Bunday qism topilmadi.")
        return

    file_id = episode[3]
    is_premium_ep = episode[4]

    if is_premium_ep and not await db.check_premium(user_id):
        text = "🔒 Bu qism faqat Premium foydalanuvchilar uchun. Premium olish uchun /buy"
        if message:
            await message.reply_text(text)
        elif query:
            await query.message.reply_text(text)
        return

    if not await db.check_premium(user_id) and not await check_channels(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 Kanalga o‘tish", url=f"https://t.me/{config.REQUIRED_CHANNELS[0].lstrip('@')}")],
            [InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data=f"check_sub_ep:{series_code}:{episode_number}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "❗️ Qismni ko‘rish uchun kanalga obuna bo‘ling:"
        if message:
            await message.reply_text(text, reply_markup=reply_markup)
        elif query:
            await query.message.reply_text(text, reply_markup=reply_markup)
        return

    await db.increment_episode_views(series_code, episode_number)
    if message:
        await message.reply_video(file_id)
    elif query:
        await query.message.reply_video(file_id)

# ----------------- /start -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.full_name)

    args = context.args
    if args:
        code = args[0]
        series = await db.get_series(code)
        if series:
            await show_episodes(update, context, code, series, user.id)
        else:
            await update.message.reply_text("❌ Bunday seriya kodi mavjud emas.")
        return

    text = (
        f"👋 *Assalomu alaykum, {user.first_name}!*\n\n"
        "🎌 *Anime Bot* ga xush kelibsiz!\n\n"
        "🔍 *Anime qidirish:* seriya kodini yuboring (masalan: `platina`).\n"
        "🌟 *Anime Premium:* /buy yoki /premium\n\n"
        "Quyidagi kanalga obuna bo'lishni unutmang:"
    )
    if config.REQUIRED_CHANNELS:
        btn = InlineKeyboardButton("📢 Kanalga obuna bo‘lish", url=f"https://t.me/{config.REQUIRED_CHANNELS[0].lstrip('@')}")
        reply_markup = InlineKeyboardMarkup([[btn]])
    else:
        reply_markup = None
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

# ----------------- Seriya kodini qayta ishlash -----------------
async def handle_series_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    series = await db.get_series(code)
    if not series:
        await update.message.reply_text("❌ Bunday seriya kodi mavjud emas.")
        return
    await show_episodes(update, context, code, series, user_id)

# ----------------- Qism tugmasi callback -----------------
async def episode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    if data[0] != "ep":
        return
    series_code = data[1]
    episode_number = int(data[2])
    user_id = query.from_user.id
    await process_episode(user_id, series_code, episode_number, context, query=query)

# ----------------- "Obuna bo‘ldim" (epizod uchun) -----------------
async def check_sub_ep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    if data[0] != "check_sub_ep":
        return
    series_code = data[1]
    episode_number = int(data[2])
    user_id = query.from_user.id
    if await check_channels(user_id, context):
        await process_episode(user_id, series_code, episode_number, context, query=query)
        await query.message.delete()
    else:
        await query.message.reply_text("❌ Hali ham obuna bo‘lmagansiz. Iltimos, kanalga a’zo bo‘ling va qayta urinib ko‘ring.")

# ----------------- /premium -----------------
async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await db.get_setting('monthly_price', config.DEFAULT_MONTHLY_PRICE)
    text = (
        "✨ *ANIME PREMIUM AFZALLIKLARI* ✨\n\n"
        "✅ *Kanallarga obuna bo‘lmasdan* anime yuklab olish\n"
        "✅ *Reklamalarsiz* tez va qulay foydalanish\n"
        "✅ *Yangi anime* birinchi bo‘lib ko‘rish\n\n"
        f"💳 *Oylik to‘lov:* {price} so‘m\n"
        "⏳ *Muddati:* 30 kun\n\n"
        "Premium sotib olish uchun /buy"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

# ----------------- /buy -----------------
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    price = await db.get_setting('monthly_price', config.DEFAULT_MONTHLY_PRICE)
    card = await db.get_setting('card_number', config.DEFAULT_CARD_NUMBER)
    holder = await db.get_setting('card_holder', config.DEFAULT_CARD_HOLDER)
    payment_id = await db.add_payment(user_id, price)
    text = (
        f"💳 *ANIME PREMIUM SOTIB OLISH* – {price} so‘m\n\n"
        f"📌 *Karta:* `{card}`\n"
        f"📌 *Karta egasi:* {holder}\n\n"
        "To‘lovni amalga oshirgach, quyidagi tugmani bosing. Admin tekshirib, sizga Premium faollashtirib beradi."
    )
    keyboard = [[InlineKeyboardButton("✅ To‘ladim", callback_data=f"confirm_payment:{payment_id}")]]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# ----------------- To‘lovni tasdiqlash (foydalanuvchi) -----------------
async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    if data[0] != "confirm_payment":
        return
    payment_id = int(data[1])
    user = query.from_user
    price = await db.get_setting('monthly_price', config.DEFAULT_MONTHLY_PRICE)
    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash (30 kun)", callback_data=f"confirm_payment_admin:{payment_id}:{user.id}:30")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_payment:{payment_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🔔 *Yangi Premium so‘rovi*\n"
        f"👤 *Foydalanuvchi:* {user.full_name} (@{user.username})\n"
        f"🆔 *ID:* {user.id}\n"
        f"🧾 *To‘lov ID:* {payment_id}\n"
        f"💰 *Summa:* {price} so‘m"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Admin {admin_id} ga xabar yuborilmadi: {e}")
    await query.edit_message_text("✅ So‘rovingiz adminga yuborildi. Tez orada Premium faollashtiriladi.")

# ----------------- Admin tasdiqlash tugmalari -----------------
async def confirm_payment_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.ADMIN_IDS:
        await query.message.reply_text("Siz admin emassiz.")
        return
    data = query.data.split(':')
    if data[0] != "confirm_payment_admin":
        return
    payment_id = int(data[1])
    user_id = int(data[2])
    days = int(data[3])
    new_until = await db.set_premium(user_id, days)
    await db.confirm_payment(payment_id)
    try:
        await context.bot.send_message(
            user_id,
            f"🎉 *Anime Premium faollashtirildi!*\n\nSizga {days} kunlik Premium berildi.\nYangi muddat: {datetime.fromtimestamp(new_until).strftime('%Y-%m-%d')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")
    await query.message.edit_text(query.message.text + "\n\n✅ Premium tasdiqlandi.")

async def reject_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.ADMIN_IDS:
        return
    data = query.data.split(':')
    if data[0] != "reject_payment":
        return
    payment_id = int(data[1])
    await query.message.edit_text(query.message.text + "\n\n❌ To‘lov rad etildi.")

# ----------------- /status -----------------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    remaining = await db.premium_remaining(user_id)
    is_premium = await db.check_premium(user_id)
    status_text = "🌟 *Premium foydalanuvchi*" if is_premium else "👤 *Oddiy foydalanuvchi*"
    text = f"📊 *Holatingiz:* {status_text}\n⏳ *Qolgan muddat:* {remaining}"
    await update.message.reply_text(text, parse_mode='Markdown')

# ----------------- Rasm (chek) yuborilganda -----------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.forward_message(admin_id, user.id, update.message.message_id)
        except Exception as e:
            logger.error(f"Admin {admin_id} ga forward xatosi: {e}")
    price = await db.get_setting('monthly_price', config.DEFAULT_MONTHLY_PRICE)
    payment_id = await db.add_payment(user.id, price)
    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash (30 kun)", callback_data=f"confirm_payment_admin:{payment_id}:{user.id}:30")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_payment:{payment_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"👤 *Foydalanuvchi:* {user.full_name} (@{user.username})\n🆔 ID: {user.id}\n📸 Chek rasmi yubordi.\n🧾 To‘lov ID: {payment_id}"
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Admin {admin_id} ga xabar xatosi: {e}")
    await update.message.reply_text("✅ Chek adminga yuborildi. Tez orada Premium faollashtiriladi.")

# ----------------- Admin buyruqlari -----------------
async def admin_add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
    except:
        await update.message.reply_text("❌ /add_premium <user_id> <kun>")
        return
    new_until = await db.set_premium(user_id, days)
    await update.message.reply_text(f"✅ Foydalanuvchi {user_id} ga {days} kun Premium berildi.")
    try:
        await context.bot.send_message(
            user_id,
            f"🎉 *Anime Premium faollashtirildi!*\n\nSizga {days} kunlik Premium berildi.\nYangi muddat: {datetime.fromtimestamp(new_until).strftime('%Y-%m-%d')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

async def admin_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    try:
        price = int(context.args[0])
    except:
        await update.message.reply_text("❌ /set_price <yangi_narx>")
        return
    await db.set_setting('monthly_price', str(price))
    await update.message.reply_text(f"✅ Oylik narx {price} so‘m qilib belgilandi.")

async def admin_set_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /set_card <karta> <ega_ismi>")
        return
    card = context.args[0]
    holder = ' '.join(context.args[1:])
    await db.set_setting('card_number', card)
    await db.set_setting('card_holder', holder)
    await update.message.reply_text(f"✅ Karta ma'lumotlari yangilandi:\n{card}\n{holder}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute('SELECT COUNT(*) FROM users') as cur:
            total_users = (await cur.fetchone())[0]
        async with conn.execute('SELECT COUNT(*) FROM users WHERE premium_until > ?', (int(time.time()),)) as cur:
            premium_users = (await cur.fetchone())[0]
        async with conn.execute('SELECT COUNT(*) FROM series') as cur:
            total_series = (await cur.fetchone())[0]
        async with conn.execute('SELECT COUNT(*) FROM episodes') as cur:
            total_episodes = (await cur.fetchone())[0]
    text = (
        f"📊 *ANIME BOT STATISTIKASI*\n\n"
        f"👥 *Jami foydalanuvchilar:* {total_users}\n"
        f"🌟 *Premium foydalanuvchilar:* {premium_users}\n"
        f"🎬 *Seriyalar soni:* {total_series}\n"
        f"📼 *Qismlar soni:* {total_episodes}"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_list_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    series_list = await db.list_series()
    if not series_list:
        await update.message.reply_text("Hali seriya qo‘shilmagan.")
        return
    text = "🎬 *SERIYALAR RO‘YXATI:*\n\n"
    for code, title, total in series_list:
        text += f"🔹 *Kod:* `{code}` | {title} | {total} qism\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_delete_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    try:
        code = context.args[0]
    except:
        await update.message.reply_text("❌ /del_series <kod>")
        return
    await db.delete_episodes(code)
    await db.delete_series(code)
    await update.message.reply_text(f"✅ `{code}` kodli seriya va uning barcha qismlari o‘chirildi.", parse_mode='Markdown')

# ----------------- Seriya qo‘shish (interaktiv, media bilan) -----------------
ASK_S_CODE, ASK_S_TITLE, ASK_S_COUNTRY, ASK_S_LANG, ASK_S_YEAR, ASK_S_GENRE, ASK_S_TOTAL, ASK_S_MEDIA = range(8)

async def admin_add_series_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text("Yangi seriya qo‘shish. Seriya kodini yuboring (masalan: `platina`):", parse_mode='Markdown')
    return ASK_S_CODE

async def admin_add_series_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_code'] = update.message.text.strip()
    await update.message.reply_text("Seriya nomini yuboring:")
    return ASK_S_TITLE

async def admin_add_series_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_title'] = update.message.text.strip()
    await update.message.reply_text("Qaysi davlat? (masalan: Yaponiya):")
    return ASK_S_COUNTRY

async def admin_add_series_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_country'] = update.message.text.strip()
    await update.message.reply_text("Tili: (masalan: Oʻzbek tilida):")
    return ASK_S_LANG

async def admin_add_series_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_lang'] = update.message.text.strip()
    await update.message.reply_text("Yili: (masalan: 2025):")
    return ASK_S_YEAR

async def admin_add_series_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_year'] = update.message.text.strip()
    await update.message.reply_text("Janri: (masalan: Fantastika, Sarguzasht):")
    return ASK_S_GENRE

async def admin_add_series_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['s_genre'] = update.message.text.strip()
    await update.message.reply_text("Nechi qismli? (raqam):")
    return ASK_S_TOTAL

async def admin_add_series_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total = int(update.message.text.strip())
    except:
        await update.message.reply_text("Iltimos, faqat son kiriting.")
        return ASK_S_TOTAL
    context.user_data['s_total'] = total
    await update.message.reply_text("Endi anime rasmini yoki qisqa video parchasini yuboring (foto yoki video):")
    return ASK_S_MEDIA

async def admin_add_series_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        media_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        media_type = 'video'
    else:
        await update.message.reply_text("Iltimos, rasm yoki video yuboring.")
        return ASK_S_MEDIA

    success = await db.add_series(
        code=context.user_data['s_code'],
        title=context.user_data['s_title'],
        country=context.user_data['s_country'],
        language=context.user_data['s_lang'],
        year=context.user_data['s_year'],
        genre=context.user_data['s_genre'],
        total_episodes=context.user_data['s_total']
    )
    if success:
        await update.message.reply_text(f"✅ Seriya qo‘shildi! Endi qismlarni qo‘shish uchun /add_episode {context.user_data['s_code']} buyrug‘idan foydalaning.")

        # Kanalga post yuborish (media bilan)
        try:
            channel = config.REQUIRED_CHANNELS[0]
            bot_username = context.bot.username
            post_text = (
                f"🎬 *Yangi anime seriya qo'shildi!*\n\n"
                f"*Nomi:* {context.user_data['s_title']}\n"
                f"*Davlat:* {context.user_data['s_country']}\n"
                f"*Tili:* {context.user_data['s_lang']}\n"
                f"*Yili:* {context.user_data['s_year']}\n"
                f"*Janri:* {context.user_data['s_genre']}\n"
                f"*Qismlar soni:* {context.user_data['s_total']}\n\n"
                f"👇 Tomosha qilish uchun tugmani bosing"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Tomosha qilish", url=f"https://t.me/{bot_username}?start={context.user_data['s_code']}")
            ]])
            if media_type == 'photo':
                await context.bot.send_photo(chat_id=channel, photo=file_id, caption=post_text, parse_mode='Markdown', reply_markup=keyboard)
            else:
                await context.bot.send_video(chat_id=channel, video=file_id, caption=post_text, parse_mode='Markdown', reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Kanalga post yuborishda xatolik: {e}")
            await update.message.reply_text("⚠️ Seriya qo‘shildi, lekin kanalga post yuborishda muammo yuz berdi.")
    else:
        await update.message.reply_text("❌ Bunday kod allaqachon mavjud.")
    return ConversationHandler.END

async def admin_add_series_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END

# ----------------- Qism qo‘shish -----------------
ASK_EP_CODE, ASK_EP_NUMBER, ASK_EP_VIDEO, ASK_EP_PREMIUM = range(4)

async def admin_add_episode_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text("Qism qo‘shish. Seriya kodini yuboring (masalan: `platina`):", parse_mode='Markdown')
    return ASK_EP_CODE

async def admin_add_episode_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ep_series'] = update.message.text.strip()
    series = await db.get_series(context.user_data['ep_series'])
    if not series:
        await update.message.reply_text("❌ Bunday seriya mavjud emas. Qaytadan seriya kodini yuboring.")
        return ASK_EP_CODE
    await update.message.reply_text(f"Seriya topildi: {series[2]}. Qism raqamini yuboring (1 dan {series[7]} gacha):")
    return ASK_EP_NUMBER

async def admin_add_episode_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = int(update.message.text.strip())
    except:
        await update.message.reply_text("Iltimos, son kiriting.")
        return ASK_EP_NUMBER
    context.user_data['ep_number'] = number
    await update.message.reply_text("Endi anime videosini yuboring (video fayl sifatida):")
    return ASK_EP_VIDEO

async def admin_add_episode_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if not video:
        await update.message.reply_text("Iltimos, video fayl yuboring.")
        return ASK_EP_VIDEO
    context.user_data['ep_file_id'] = video.file_id
    keyboard = [
        [InlineKeyboardButton("Ha", callback_data="ep_premium_yes")],
        [InlineKeyboardButton("Yo‘q", callback_data="ep_premium_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bu qism Premium uchunmi?", reply_markup=reply_markup)
    return ASK_EP_PREMIUM

async def admin_add_episode_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ep_premium_yes":
        is_premium = 1
    else:
        is_premium = 0
    series_code = context.user_data['ep_series']
    episode_number = context.user_data['ep_number']
    file_id = context.user_data['ep_file_id']

    success = await db.add_episode(series_code, episode_number, file_id, is_premium)
    if success:
        await query.message.edit_text(f"✅ {series_code} seriyasining {episode_number}-qismi qo‘shildi.")
    else:
        await query.message.edit_text("❌ Xatolik yuz berdi (ehtimol, bu qism allaqachon mavjud).")
    return ConversationHandler.END

async def admin_add_episode_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END

# ----------------- Xatolik handleri -----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ----------------- Asosiy -----------------
def main():
    asyncio.run(db.init_db())
    app = Application.builder().token(config.BOT_TOKEN).build()

    # Oddiy handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("premium", premium_info))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("status", status))

    # Admin handlerlar
    app.add_handler(CommandHandler("add_premium", admin_add_premium))
    app.add_handler(CommandHandler("set_price", admin_set_price))
    app.add_handler(CommandHandler("set_card", admin_set_card))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("series", admin_list_series))
    app.add_handler(CommandHandler("del_series", admin_delete_series))

    # Seriya qo‘shish conversation (media bilan)
    series_conv = ConversationHandler(
        entry_points=[CommandHandler('add_series', admin_add_series_start)],
        states={
            ASK_S_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_code)],
            ASK_S_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_title)],
            ASK_S_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_country)],
            ASK_S_LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_lang)],
            ASK_S_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_year)],
            ASK_S_GENRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_genre)],
            ASK_S_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_series_total)],
            ASK_S_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, admin_add_series_media)],
        },
        fallbacks=[CommandHandler('cancel', admin_add_series_cancel)],
    )
    app.add_handler(series_conv)

    # Qism qo‘shish conversation
    ep_conv = ConversationHandler(
        entry_points=[CommandHandler('add_episode', admin_add_episode_start)],
        states={
            ASK_EP_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_episode_code)],
            ASK_EP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_episode_number)],
            ASK_EP_VIDEO: [MessageHandler(filters.VIDEO, admin_add_episode_video)],
            ASK_EP_PREMIUM: [CallbackQueryHandler(admin_add_episode_premium_callback, pattern="^(ep_premium_yes|ep_premium_no)$")],
        },
        fallbacks=[CommandHandler('cancel', admin_add_episode_cancel)],
    )
    app.add_handler(ep_conv)

    # Callbacklar
    app.add_handler(CallbackQueryHandler(payment_callback, pattern="^confirm_payment:"))
    app.add_handler(CallbackQueryHandler(confirm_payment_admin_callback, pattern="^confirm_payment_admin:"))
    app.add_handler(CallbackQueryHandler(reject_payment_callback, pattern="^reject_payment:"))
    app.add_handler(CallbackQueryHandler(episode_callback, pattern="^ep:"))
    app.add_handler(CallbackQueryHandler(check_sub_ep_callback, pattern="^check_sub_ep:"))

    # Matn va rasm (chek)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_series_code))

    app.add_error_handler(error_handler)

    logger.info("Anime Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()