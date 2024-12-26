import telebot
from telebot import types
from datetime import datetime, timedelta
import sqlite3
import pandas as pd

# Инициализация бота
bot = telebot.TeleBot('7875781676:AAGtiHZVPDIM8UToLkX3nD88xkjM-VGyD04')

# Словарь для хранения временных данных
user_states = {}

# Создание базы данных
def init_db():
    conn = sqlite3.connect('campaigns.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS campaigns
        (campaign_name TEXT, 
         start_date DATE,
         notification_date DATE,
         notified BOOLEAN)
    ''')
    conn.commit()
    conn.close()

# Добавление новой кампании
def add_campaign(campaign_name):
    conn = sqlite3.connect('campaigns.db')
    start_date = datetime.now().date()
    
    # Расчет даты уведомления (7 рабочих дней)
    notification_date = start_date
    working_days = 0
    while working_days < 7:
        notification_date += timedelta(days=1)
        if notification_date.weekday() < 5:  # 0-4 это пн-пт
            working_days += 1
    
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO campaigns (campaign_name, start_date, notification_date, notified)
        VALUES (?, ?, ?, ?)
    ''', (campaign_name, start_date, notification_date, False))
    
    conn.commit()
    conn.close()
    return notification_date

# Проверка уведомлений
def check_notifications():
    conn = sqlite3.connect('campaigns.db')
    cursor = conn.cursor()
    today = datetime.now().date()
    
    cursor.execute('''
        SELECT campaign_name, notification_date
        FROM campaigns
        WHERE notification_date <= ? AND notified = False
    ''', (today,))
    
    notifications = cursor.fetchall()
    
    for campaign_name, notification_date in notifications:
        cursor.execute('''
            UPDATE campaigns
            SET notified = True
            WHERE campaign_name = ? AND notification_date = ?
        ''', (campaign_name, notification_date))
    
    conn.commit()
    conn.close()
    return notifications

# Создание главного меню
def create_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('➕ Добавить кампанию')
    btn2 = types.KeyboardButton('📋 Список кампаний')
    btn3 = types.KeyboardButton('❓ Помощь')
    markup.add(btn1, btn2, btn3)
    return markup

# Удаление кампании
def delete_campaign(campaign_name):
    conn = sqlite3.connect('campaigns.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM campaigns WHERE campaign_name = ? AND notified = False', (campaign_name,))
    conn.commit()
    conn.close()

# Создание инлайн-кнопок для списка кампаний
def create_campaigns_markup():
    conn = sqlite3.connect('campaigns.db')
    cursor = conn.cursor()
    cursor.execute('SELECT campaign_name FROM campaigns WHERE notified = False')
    campaigns = cursor.fetchall()
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for campaign in campaigns:
        markup.add(types.InlineKeyboardButton(
            text=f"❌ {campaign[0]}", 
            callback_data=f"delete_{campaign[0]}"
        ))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
                 "Привет! Я помогу отслеживать ваши кампании.\n"
                 "Используйте кнопки меню для управления кампаниями.", 
                 reply_markup=create_main_menu())

@bot.message_handler(func=lambda message: message.text == '➕ Добавить кампанию')
def add_campaign_request(message):
    msg = bot.send_message(message.chat.id, 
                          "Введите название новой кампании:",
                          reply_markup=types.ForceReply())
    user_states[message.chat.id] = 'waiting_for_campaign_name'

@bot.message_handler(func=lambda message: message.text == '📋 Список кампаний')
def list_campaigns(message):
    conn = sqlite3.connect('campaigns.db')
    df = pd.read_sql_query('''
        SELECT campaign_name, start_date, notification_date
        FROM campaigns
        WHERE notified = False
        ORDER BY notification_date
    ''', conn)
    
    if df.empty:
        bot.reply_to(message, "Нет активных кампаний")
    else:
        response = "Активные кампании:\n\n"
        for _, row in df.iterrows():
            response += f"📊 {row['campaign_name']}\n"
            response += f"Дата начала: {row['start_date']}\n"
            response += f"Дата уведомления: {row['notification_date']}\n\n"
        
        bot.send_message(message.chat.id, response, 
                        reply_markup=create_campaigns_markup())
        # Возвращаем основное меню сразу после списка
        bot.send_message(message.chat.id, "Выберите действие:", 
                        reply_markup=create_main_menu())
    
    conn.close()

@bot.message_handler(func=lambda message: message.text == '❓ Помощь')
def help_command(message):
    help_text = """
🤖 Как пользоваться ботом:

➕ Добавить кампанию - добавляет новую кампанию для отслеживания

📋 Список кампаний - показывает все активные кампании и позволяет удалить их

❌ Чтобы удалить кампанию, нажмите на её название в списке кампаний

⏰ Бот автоматически отправит уведомление через 7 рабочих дней после добавления кампании
    """
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'waiting_for_campaign_name')
def handle_campaign_name(message):
    campaign_name = message.text
    notification_date = add_campaign(campaign_name)
    bot.send_message(message.chat.id, 
                f"✅ Кампания '{campaign_name}' добавлена.\n"
                f"📅 Уведомление будет отправлено {notification_date}",
                reply_markup=create_main_menu())
    user_states.pop(message.chat.id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def handle_delete_campaign(call):
    campaign_name = call.data[7:]  # Убираем префикс 'delete_'
    delete_campaign(campaign_name)
    bot.answer_callback_query(call.id, f"Кампания '{campaign_name}' удалена")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, 
                                reply_markup=create_campaigns_markup())
    bot.send_message(call.message.chat.id, 
                          f"✅ Кампания '{campaign_name}' успешно удалена",
                          reply_markup=create_main_menu())

# Функция для отправки уведомлений
def send_notifications(chat_id):
    notifications = check_notifications()
    for campaign_name, _ in notifications:
        bot.send_message(chat_id, 
                        f"⚠️ Напоминание: прошло 7 рабочих дней с момента остановки "
                        f"кампании '{campaign_name}'.\n"
                        f"Пожалуйста, соберите итоговые данные.")

if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    
    # Запуск бота
    bot.polling(none_stop=True)