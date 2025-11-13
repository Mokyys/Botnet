
import telebot
from telebot import types
import sqlite3
import smtplib
from email.mime.text import MIMEText
import re
import os
from itertools import cycle # Для циклического переключения между отправителями

# --- КОНФИГУРАЦИЯ БОТА ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8222076597:AAE8Bbwtc3KzhRCM-grCoXgLGTZNCF61UwE") 

# EMAIL КОНФИГУРАЦИЯ ДЛЯ ЖАЛОБ
SENDER_ACCOUNTS = [
    {
        "email": os.environ.get("SENDER_EMAIL_1", "sender1@gmail.com"),
        "password": os.environ.get("SENDER_PASSWORD_1", "YOUR_APP_PASSWORD_1"),
        "smtp_server": os.environ.get("SMTP_SERVER_1", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT_1", 587))
    },
    {
        "email": os.environ.get("SENDER_EMAIL_2", "sender2@gmail.com"),
        "password": os.environ.get("SENDER_PASSWORD_2", "YOUR_APP_PASSWORD_2"),
        "smtp_server": os.environ.get("SMTP_SERVER_2", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT_2", 587))
    }
]

RECIPIENT_EMAILS = [
    "complaints1@example.com", 
    "complaints2@example.com",
    "complaints3@example.com"
]

# АДМИН ПАНЕЛЬ (только для связи И управления промокодами)
ADMIN_USERNAME = "@fuckradmirow" 
ADMIN_ID = int(os.environ.get("7340922523", 123456789)) # !!! ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ НА ЧИСЛОВОЙ ID АДМИНИСТРАТОРА !!!

# НАСТРОЙКИ РЕФЕРАЛЬНОЙ ПРОГРАММЫ
REFERRAL_BONUS_SNOS = 2 

# ЦЕНЫ ЗА ЖАЛОБЫ
PRICE_10_SNOS = 3 # $
PRICE_25_SNOS = 5 # $

# --- ИНИЦИАЛИЗАЦИЯ БОТА И БД ---
bot = telebot.TeleBot(BOT_TOKEN)
sender_accounts_cycle = cycle(SENDER_ACCOUNTS)
user_data = {} # Временные данные пользователя

def init_db():
    """Инициализация базы данных SQLite и создание таблиц, если они не существуют."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            snos_count INTEGER DEFAULT 0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            sent_snos_count INTEGER DEFAULT 0, 
            balance REAL DEFAULT 0.0 
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            snos_amount INTEGER,
            max_uses INTEGER,
            current_uses INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_promo_uses (
            user_id INTEGER,
            promo_code TEXT,
            PRIMARY KEY (user_id, promo_code)
        )
    ''')
    # Добавляем админа в таблицу админов при первом запуске, если его там нет
    cursor.execute("INSERT OR IGNORE INTO admin_users (user_id) VALUES (?)", (ADMIN_ID,))
    conn.commit()
    conn.close()

init_db()

# --- ФУНКЦИИ ВЗАИМОДЕЙСТВИЯ С БД ---
def get_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data

def add_user(user_id, username, referred_by=None):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                   (user_id, username, referred_by))
    conn.commit()
    conn.close()

def update_snos_count(user_id, count):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET snos_count = ? WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()

def increment_snos_count(user_id, amount):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET snos_count = snos_count + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def increment_sent_snos_count(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET sent_snos_count = sent_snos_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def increment_referrals_count(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_top_referrals(limit=10):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT ?", (limit,))
    top_users = cursor.fetchall()
    conn.close()
    return top_users

# --- Функции управления промокодами ---
def add_promo(code, snos_amount, max_uses):
    """Добавляет новый промокод в базу данных."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO promo_codes (code, snos_amount, max_uses) VALUES (?, ?, ?)",
                       (code, snos_amount, max_uses))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # Если промокод с таким кодом уже существует
        return False
    finally:
        conn.close()

def get_promo(code):
    """Получает информацию о промокоде."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promo_codes WHERE code=?", (code,))
    promo = cursor.fetchone()
    conn.close()
    return promo

def update_promo_uses(code):
    """Увеличивает счетчик использований промокода."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

def record_user_promo_use(user_id, promo_code):
    """Записывает, что пользователь использовал данный промокод."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_promo_uses (user_id, promo_code) VALUES (?, ?)", (user_id, promo_code))
    conn.commit()
    conn.close()

def has_user_used_promo(user_id, promo_code):
    """Проверяет, использовал ли пользователь данный промокод ранее."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_promo_uses WHERE user_id=? AND promo_code=?", (user_id, promo_code))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_all_promos():
    """Возвращает список всех промокодов."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promo_codes")
    promos = cursor.fetchall()
    conn.close()
    return promos

def delete_promo(code):
    """Удаляет промокод из базы данных."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promo_codes WHERE code=?", (code,))
    conn.commit()
    conn.close()

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# --- ФУНКЦИИ ОТПРАВКИ EMAIL ---
def send_complaint_email(target_session, reason_text):
    subject = f"Нарушение правил Telegram: {target_session}"
    escaped_target_session = escape_markdown_v2(target_session)
    body = f"Здравствуйте, этот аккаунт нарушает правила Telegram: {target_session}\n\nПрошу вас разобраться."

    for _ in range(len(SENDER_ACCOUNTS)): 
        sender_account = next(sender_accounts_cycle)
        sender_email = sender_account["email"]
        sender_password = sender_account["password"]
        smtp_server = sender_account["smtp_server"]
        smtp_port = sender_account["smtp_port"]

        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender_email 
        
        all_recipients_success = True

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()  
                server.login(sender_email, sender_password)

                for recipient_email in RECIPIENT_EMAILS:
                    msg['To'] = recipient_email 
                    try:
                        server.send_message(msg)
                        print(f"✅ Жалоба отправлена с {sender_email} на {recipient_email} для {target_session} (причина: {reason_text})")
                    except Exception as e:
                        print(f"❌ Ошибка при отправке письма с {sender_email} на {recipient_email}: {e}")
                        all_recipients_success = False
            
            if all_recipients_success:
                return True, sender_email 
            else:
                print(f"Отправитель {sender_email} не смог отправить на всех получателей. Пробуем следующего...")
                continue 

        except smtplib.SMTPAuthenticationError:
            print(f"❌ Ошибка аутентификации для {sender_email}. Проверьте email и пароль/пароль приложения.")
            continue
        except Exception as e:
            print(f"❌ Общая ошибка SMTP для {sender_email}: {e}")
            continue
    
    return False, None 

# --- Хелперы для MarkdownV2 ---
def escape_markdown_v2(text):
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    """Возвращает основную клавиатуру бота."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Снести"))
    keyboard.add(types.KeyboardButton("Реферальная программа"), types.KeyboardButton("Топ рефералов"))
    keyboard.add(types.KeyboardButton("Мой профиль"), types.KeyboardButton("Купить жалобы"))
    keyboard.add(types.KeyboardButton("Активировать промокод"), types.KeyboardButton("Помощь")) 
    return keyboard

def get_snos_reason_keyboard():
    """Возвращает инлайн-клавиатуру для выбора причины жалобы."""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("Авторские права", callback_data="snos_reason_copyright"),
        types.InlineKeyboardButton("Спам/Нарушение правил", callback_data="snos_reason_spam")
    )
    keyboard.add(types.InlineKeyboardButton("Отменить", callback_data="cancel_snos"))
    return keyboard

def get_buy_snos_keyboard():
    """Возвращает инлайн-клавиатуру для выбора пакетов жалоб."""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(f"10 жалоб / {PRICE_10_SNOS}$", callback_data="buy_snos_10"),
        types.InlineKeyboardButton(f"25 жалоб / {PRICE_25_SNOS}$", callback_data="buy_snos_25")
    )
    return keyboard


# --- ОБРАБОТЧИКИ КОМАНД И ТЕКСТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Отправляет приветствие пользователю при первом запуске."""
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user.username else f"id{user_id}"
    
    referred_by_id = None
    if len(message.text.split()) > 1:
        ref_param = message.text.split()[1]
        if ref_param.startswith("ref_"):
            try:
                referred_by_id = int(ref_param.replace("ref_", ""))
            except ValueError:
                referred_by_id = None
    
    user = get_user(user_id)
    if not user:
        add_user(user_id, username, referred_by_id)
        if referred_by_id and referred_by_id != user_id: 
            referrer = get_user(referred_by_id)
            if referrer:
                increment_referrals_count(referred_by_id)
                increment_snos_count(referred_by_id, REFERRAL_BONUS_SNOS)
                try:
                    escaped_username = escape_markdown_v2(username)
                    bot.send_message(referred_by_id,
                                     f"🎉 Поздравляем\\! По вашей реферальной ссылке зарегистрировался новый пользователь @{escaped_username}\\. "
                                     f"Вам начислено `{REFERRAL_BONUS_SNOS}` бесплатных сносов\\!",
                                     parse_mode="MarkdownV2")
                except Exception as e:
                    print(f"Не удалось отправить уведомление рефереру {referred_by_id}: {e}")
            else:
                print(f"Реферер с ID {referred_by_id} не найден.")
    
    welcome_text = (
        f"Привет\\! Хочешь бесплатно снести аккаунт\\?\n"
        f"Тебе к нам, низкий прайс\\!\n\n"
        f"Я помогу тебе отправить жалобу\\.\n"
        f"Выбери действие ниже или напиши /help для получения инструкций\\."
    )
    bot.send_message(user_id, welcome_text, parse_mode="MarkdownV2", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['help'])
def send_help(message):
    """Отправляет информацию о боте и его командах."""
    user_id = message.from_user.id
    help_text = (
        f"⭐ \\*Как работает бот:\\*\n\n"
        f"1️⃣ Нажмите кнопку *\"Снести\"*\n"
        f"2️⃣ Выберите причину жалобы\\.\n"
        f"3️⃣ Отправьте @username или ссылку на аккаунт/канал\\.\n"
        f"4️⃣ Я отправлю жалобы на 3 почты поддержки Telegram\\.\n\n"
        f"💰 \\*Купить жалобы:\\*\n"
        f"🔸 `{10}` жалоб за `{PRICE_10_SNOS}$`\n"
        f"🔸 `{25}` жалоб за `{PRICE_25_SNOS}$`\n"
        f"Для покупки свяжитесь с администратором {ADMIN_USERNAME} и отправьте ему подтверждение оплаты\\.\n\n"
        f"🔗 \\*Реферальная программа:\\*\n"
        f"Приглашайте друзей и получайте `{REFERRAL_BONUS_SNOS}` бесплатных сносов за каждого\\!\n\n"
        f"✨ \\*Промокоды:\\*\n"
        f"Используйте команду \"Активировать промокод\" для получения дополнительных жалоб\\.\n\n"
        f"❓ \\*Другое:*\n"
        f"🔸 *Мой профиль*: Просмотр вашей статистики\\.\n"
        f"🔸 *Топ рефералов*: Список лучших пригласителей\\.\n\n"
        f"Если у вас возникли вопросы, свяжитесь с администратором {ADMIN_USERNAME}\\."
    )
    bot.send_message(user_id, help_text, parse_mode="MarkdownV2", reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: message.text == "Снести")
def handle_snos_button(message):
    """Обрабатывает нажатие кнопки 'Снести', проверяет баланс и запрашивает причину для жалобы."""
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.send_message(user_id, "Пожалуйста, нажмите /start, чтобы зарегистрироваться\\.", parse_mode="MarkdownV2")
        return

    snos_count = user[2] 
    
    if snos_count <= 0:
        bot.send_message(user_id,
                         "У вас нет доступных сносов\\. Вы можете получить их, участвуя в реферальной программе, купив их или активировав промокод\\.",
                         parse_mode="MarkdownV2",
                         reply_markup=get_main_keyboard())
        return

    bot.send_message(user_id, "Выберите причину жалобы:", parse_mode="MarkdownV2", reply_markup=get_snos_reason_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("snos_reason_"))
def callback_snos_reason(call):
    """Обрабатывает выбор причины жалобы, сохраняет её и запрашивает цель."""
    user_id = call.from_user.id
    reason = call.data.replace("snos_reason_", "")
    
    user_data[user_id] = {'reason': reason} 
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text=f"Выбрана причина: `{escape_markdown_v2(reason)}`\\.\n\n"
                               "Отправьте @username или ссылку на аккаунт/канал, на который нужно отправить жалобу (например, `@example_user` или `https://t.me/example_channel`):", 
                          parse_mode="MarkdownV2",
                          reply_markup=get_snos_keyboard())
    bot.register_next_step_handler(call.message, process_snos_target)

def process_snos_target(message):
    """Обрабатывает введенную пользователем цель для жалобы и отправляет ее."""
    user_id = message.from_user.id
    target = message.text.strip()

    if target.lower() == "отменить":
        bot.send_message(user_id, "Отправка жалобы отменена\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]
        return
    
    user = get_user(user_id)
    if not user:
        bot.send_message(user_id, "Что\\-то пошло не так\\. Пожалуйста, нажмите /start\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]
        return

    snos_count = user[2]
    if snos_count <= 0:
        bot.send_message(user_id,
                         "У вас больше нет доступных сносов\\. Пожалуйста, пополните баланс\\.",
                         parse_mode="MarkdownV2",
                         reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]
        return

    if user_id not in user_data or 'reason' not in user_data[user_id]:
        bot.send_message(user_id, "Ошибка: не удалось определить причину жалобы\\. Начните заново, нажав кнопку 'Снести'\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())
        return

    if not (target.startswith("@") or target.startswith("https://t.me/")):
        msg = bot.send_message(user_id, "Пожалуйста, введите корректный @username или ссылку\\. Попробуйте ещё раз:", parse_mode="MarkdownV2", reply_markup=get_snos_keyboard())
        bot.register_next_step_handler(msg, process_snos_target)
        return
    
    reason_text = user_data[user_id]['reason']
    del user_data[user_id] 
    
    bot.send_message(user_id, f"Отправляю жалобы на `{escape_markdown_v2(target)}` по причине `{escape_markdown_v2(reason_text)}`\\.\\.\\.", parse_mode="MarkdownV2")
    
    success, sender_email_used = send_complaint_email(target, reason_text)

    if success:
        new_snos_count = snos_count - 1
        update_snos_count(user_id, new_snos_count)
        increment_sent_snos_count(user_id) 
        bot.send_message(user_id,
                         f"✅ Жалобы на `{escape_markdown_v2(target)}` успешно отправлены на {len(RECIPIENT_EMAILS)} почты от аккаунта `{escape_markdown_v2(sender_email_used)}`\\!\n"
                         f"У вас осталось `{new_snos_count}` сносов\\.",
                         parse_mode="MarkdownV2",
                         reply_markup=get_main_keyboard())
    else:
        bot.send_message(user_id,
                         f"❌ Не удалось отправить жалобы на `{escape_markdown_v2(target)}`\\.\n"
                         "Пожалуйста, попробуйте позже или свяжитесь с администратором\\.",
                         parse_mode="MarkdownV2",
                         reply_markup=get_main_keyboard())


@bot.callback_query_handler(func=lambda call: call.data == "cancel_snos")
def callback_cancel_snos(call):
    """Обрабатывает отмену операции сноса через инлайн-кнопку."""
    user_id = call.from_user.id
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text="Отправка жалобы отменена\\.", parse_mode="MarkdownV2", reply_markup=None)
    bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=get_main_keyboard())
    if user_id in user_data: del user_data[user_id]


@bot.message_handler(func=lambda message: message.text == "Реферальная программа")
def handle_referral_program(message):
    """Отображает информацию о реферальной программе и генерирует реферальную ссылку."""
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.send_message(user_id, "Пожалуйста, нажмите /start, чтобы зарегистрироваться\\.", parse_mode="MarkdownV2")
        return

    referrals_count = user[4] 
    
    bot_info = bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    bot.send_message(user_id,
                     f"🌟 \\*Ваша реферальная программа:\\*\n\n"
                     f"Приглашайте друзей и получайте бесплатные сносы\\!\n"
                     f"За каждого приглашенного пользователя вы получаете \\*{REFERRAL_BONUS_SNOS} бесплатных сносов\\*\\.\n\n"
                     f"🔗 \\*Ваша реферальная ссылка:\\*\n`{referral_link}`\n\n"
                     f"👥 \\*Приглашено вами:\\* `{referrals_count}` человек\\(а\\)\\.",
                     parse_mode="MarkdownV2",
                     reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "Топ рефералов")
def handle_top_referrals(message):
    """Отображает список топ-рефералов."""
    user_id = message.from_user.id
    top_users = get_top_referrals()

    if not top_users:
        bot.send_message(user_id, "Список топ рефералов пока пуст\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())
        return

    response = "🏆 \\*Топ рефералов:\\*\n\n"
    for i, (username, count) in enumerate(top_users):
        escaped_username = escape_markdown_v2(username if username else 'Неизвестно')
        response += f"{i+1}\\. @{escaped_username}: `{count}` приглашений\n"
    
    bot.send_message(user_id, response, parse_mode="MarkdownV2", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "Мой профиль")
def handle_my_profile(message):
    """Отображает профиль пользователя с информацией о сносах и рефералах."""
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.send_message(user_id, "Пожалуйста, нажмите /start, чтобы зарегистрироваться\\.", parse_mode="MarkdownV2")
        return
    
    username = user[1]
    snos_count = user[2]        # Сколько осталось
    referred_by = user[3]
    referrals_count = user[4]
    sent_snos_count = user[5]   # Сколько снесли

    profile_text = f"👤 \\*Ваш профиль:\\*\n" \
                   f"ID: `{user_id}`\n" \
                   f"Имя пользователя: @{escape_markdown_v2(username)}\n" \
                   f"Доступно сносов: `{snos_count}`\n" \
                   f"Всего снесено: `{sent_snos_count}`\n" \
                   f"Приглашено вами: `{referrals_count}` человек\\(а\\)\n"
    
    if referred_by:
        referrer_user = get_user(referred_by)
        if referrer_user and referrer_user[1]:
            profile_text += f"Пригласил\\(а\\) вас: @{escape_markdown_v2(referrer_user[1])}\n"
        else:
            profile_text += f"Пригласил\\(а\\) вас: Пользователь с ID `{referred_by}`\n"

    bot.send_message(user_id, profile_text, parse_mode="MarkdownV2", reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: message.text == "Купить жалобы")
def handle_buy_snos_button(message):
    """Отображает информацию о покупке жалоб и предлагает варианты."""
    bot.send_message(message.chat.id,
                     f"💳 \\*Купить жалобы:\\*\n\n"
                     f"Вы можете приобрести дополнительные жалобы\\:\n"
                     f"🔸 `{10}` жалоб за `{PRICE_10_SNOS}$`\n"
                     f"🔸 `{25}` жалоб за `{PRICE_25_SNOS}$`\n\n"
                     f"Для покупки, пожалуйста, свяжитесь с администратором {ADMIN_USERNAME} и отправьте ему подтверждение оплаты\\.\n"
                     f"После проверки администратор добавит жалобы на ваш баланс\\.",
                     parse_mode="MarkdownV2",
                     reply_markup=get_buy_snos_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_snos_"))
def callback_buy_snos(call):
    """Обрабатывает выбор пакета жалоб для покупки (инлайн-кнопки)."""
    snos_amount = call.data.split('_')[2]
    price = PRICE_10_SNOS if snos_amount == "10" else PRICE_25_SNOS

    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text=f"Вы выбрали пакет `{snos_amount}` жалоб за `{price}$`\\.\n\n"
                               f"Пожалуйста, свяжитесь с администратором {ADMIN_USERNAME} и отправьте ему подтверждение оплаты\\.\n"
                               f"После проверки администратор добавит жалобы на ваш баланс\\.",
                          parse_mode="MarkdownV2",
                          reply_markup=get_buy_snos_keyboard()) 

@bot.message_handler(func=lambda message: message.text == "Активировать промокод")
def handle_activate_promo_button(message):
    """Запрашивает промокод у пользователя."""
    msg = bot.send_message(message.chat.id, "Введите промокод:", parse_mode="MarkdownV2", reply_markup=get_snos_keyboard()) # Используем временную кнопку "Отменить"
    bot.register_next_step_handler(msg, process_promo_code)

def process_promo_code(message):
    """Обрабатывает введенный пользователем промокод."""
    user_id = message.from_user.id
    promo_code_input = message.text.strip().upper()

    if promo_code_input.lower() == "отменить":
        bot.send_message(user_id, "Активация промокода отменена\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())
        return

    promo = get_promo(promo_code_input)

    if not promo:
        msg = bot.send_message(user_id, f"Промокод `{escape_markdown_v2(promo_code_input)}` не найден\\.", parse_mode="MarkdownV2", reply_markup=get_snos_keyboard())
        bot.register_next_step_handler(msg, process_promo_code)
        return

    code, snos_amount, max_uses, current_uses = promo

    if current_uses >= max_uses:
        msg = bot.send_message(user_id, f"Промокод `{escape_markdown_v2(code)}` истек \\(больше нет доступных использований\\)\\.", parse_mode="MarkdownV2", reply_markup=get_snos_keyboard())
        bot.register_next_step_handler(msg, process_promo_code)
        return

    if has_user_used_promo(user_id, code):
        msg = bot.send_message(user_id, f"Вы уже активировали промокод `{escape_markdown_v2(code)}` ранее\\.", parse_mode="MarkdownV2", reply_markup=get_snos_keyboard())
        bot.register_next_step_handler(msg, process_promo_code)
        return

    # Активируем промокод
    increment_snos_count(user_id, snos_amount)
    update_promo_uses(code)
    record_user_promo_use(user_id, code)
    
    current_snos = get_user(user_id)[2] # Получаем текущий баланс сносов
    bot.send_message(user_id,
                     f"🎉 Промокод `{escape_markdown_v2(code)}` успешно активирован\\! Вы получили `{snos_amount}` жалоб\\.\n"
                     f"Ваш текущий баланс: `{current_snos}` жалоб\\.",
                     parse_mode="MarkdownV2",
                     reply_markup=get_main_keyboard())

# --- АДМИН ПАНЕЛЬ (ВОЗВРАЩЕНА ДЛЯ ПРОМОКОДОВ) ---
@bot.message_handler(commands=['addpromo'])
def add_promo_admin(message):
    """Админ-команда для добавления промокода."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "У вас нет прав администратора для выполнения этой команды\\.", parse_mode="MarkdownV2")
        return

    args = message.text.split()
    if len(args) != 4:
        bot.send_message(user_id, "Использование: `/addpromo <code> <количество\\_жалоб> <максимум\\_использований>`\n"
                                  "Пример: `/addpromo KRIMINAL 1000 2`", parse_mode="MarkdownV2")
        return

    code = args[1].upper()
    try:
        snos_amount = int(args[2])
        max_uses = int(args[3])
        if snos_amount <= 0 or max_uses <= 0:
            raise ValueError("Количество жалоб и использований должны быть положительными числами\\.")
    except ValueError as e:
        bot.send_message(user_id, f"Ошибка в параметрах: `{escape_markdown_v2(str(e))}`", parse_mode="MarkdownV2")
        return
    
    if get_promo(code):
        bot.send_message(user_id, f"Промокод `{escape_markdown_v2(code)}` уже существует\\.", parse_mode="MarkdownV2")
        return

    if add_promo(code, snos_amount, max_uses):
        bot.send_message(user_id, f"✅ Промокод `{escape_markdown_v2(code)}` добавлен\\! "
                                  f"Дает `{snos_amount}` жалоб, максимум `{max_uses}` использований\\.", parse_mode="MarkdownV2")
    else:
        bot.send_message(user_id, f"❌ Не удалось добавить промокод `{escape_markdown_v2(code)}`\\.", parse_mode="MarkdownV2")

@bot.message_handler(commands=['listpromos'])
def list_promos_admin(message):
    """Админ-команда для просмотра всех промокодов."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "У вас нет прав администратора для выполнения этой команды\\.", parse_mode="MarkdownV2")
        return

    promos = get_all_promos()
    if not promos:
        bot.send_message(user_id, "Список промокодов пуст\\.", parse_mode="MarkdownV2")
        return

    response = "📋 \\*Список промокодов:\\*\n\n"
    for promo in promos:
        code, snos_amount, max_uses, current_uses = promo
        response += f"`{escape_markdown_v2(code)}`: `{snos_amount}` жалоб, использовано `{current_uses}` из `{max_uses}`\n"
    
    bot.send_message(user_id, response, parse_mode="MarkdownV2")

@bot.message_handler(commands=['delpromo'])
def del_promo_admin(message):
    """Админ-команда для удаления промокода."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "У вас нет прав администратора для выполнения этой команды\\.", parse_mode="MarkdownV2")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.send_message(user_id, "Использование: `/delpromo <code>`\n"
                                  "Пример: `/delpromo KRIMINAL`", parse_mode="MarkdownV2")
        return

    code = args[1].upper()
    
    if not get_promo(code):
        bot.send_message(user_id, f"Промокод `{escape_markdown_v2(code)}` не найден\\.", parse_mode="MarkdownV2")
        return

    delete_promo(code)
    bot.send_message(user_id, f"✅ Промокод `{escape_markdown_v2(code)}` успешно удален\\.", parse_mode="MarkdownV2")


@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
    """Обрабатывает любые текстовые сообщения, не являющиеся командами или нажатиями кнопок."""
    if message.text.lower() == "помощь":
        send_help(message)
    else:
        bot.send_message(message.chat.id, "Я не понимаю эту команду\\. Используйте кнопки или /start \\/help\\.", parse_mode="MarkdownV2", reply_markup=get_main_keyboard())


# Запуск бота
if __name__ == '__main__':
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or ":" not in BOT_TOKEN:
        print("!!! ОШИБКА: BOT_TOKEN не установлен или некорректен. Пожалуйста, получите токен от BotFather и обновите переменную BOT_TOKEN. !!!")
        exit()
    if not SENDER_ACCOUNTS or not all(acc.get("email") and acc.get("password") for acc in SENDER_ACCOUNTS):
        print("!!! ВНИМАНИЕ: Не все данные для SENDER_ACCOUNTS установлены. Отправка жалоб может не работать. !!!")
    if not RECIPIENT_EMAILS:
        print("!!! ВНИМАНИЕ: Список RECIPIENT_EMAILS пуст. Жалобы не будут никуда отправляться. !!!")
    
    print("Бот запущен...")
    bot.polling(none_stop=True)
