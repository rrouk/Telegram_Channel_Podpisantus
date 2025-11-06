import telebot
from telebot import types
import re
import sqlite3
import json
import os
import logging
# Настройка логирования в начале файла (должна быть)
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(processName)s - %(name)s - %(levelname)s - %(message)s')

# API_TOKEN должен быть обязательным. Если его нет, скрипт завершится.
API_TOKEN = os.environ.get('TG_BOT_TOKEN')
if not API_TOKEN:
    logging.info("Ошибка: Переменная окружения 'TG_BOT_TOKEN' не установлена.")
    exit(1)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И НАСТРОЙКИ ===

# База данных для хранения настроек каналов
DB_FILE = '/app/channel_signatures.db'

# Словарь для хранения состояний администратора в процессе добавления/редактирования
user_states = {}

# Режимы состояния
STATE_AWAITING_CHANNEL_LINK = 1
STATE_AWAITING_NEW_SIGNATURE = 2
STATE_AWAITING_EDIT_SIGNATURE = 3
STATE_AWAITING_DELETE_CHANNEL_LINK = 4

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ===

def init_db():
    """Инициализирует базу данных, создавая таблицу, если ее нет."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            admin_id INTEGER,
            channel_id INTEGER,
            signature_text TEXT,
            signature_entities TEXT,
            PRIMARY KEY (admin_id, channel_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_channel_signature(admin_id, channel_id, signature_text, signature_entities):
    """Добавляет или обновляет подпись для канала, сохраняя текст и сущности."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Сериализуем сущности в JSON
    serialized_entities = json.dumps([entity.__dict__ for entity in signature_entities])
    cursor.execute('''
        INSERT OR REPLACE INTO channels (admin_id, channel_id, signature_text, signature_entities) VALUES (?, ?, ?, ?)
    ''', (admin_id, channel_id, signature_text, serialized_entities))
    conn.commit()
    conn.close()

def get_channel_signature(channel_id):
    """Возвращает подпись и ее сущности для канала по его ID."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Запрос ищет подпись по channel_id, возвращая также admin_id
    cursor.execute('SELECT admin_id, signature_text, signature_entities FROM channels WHERE channel_id = ?', (channel_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        admin_id, signature_text, serialized_entities = result
        # Десериализуем сущности из JSON
        deserialized_entities = [types.MessageEntity(**e) for e in json.loads(serialized_entities)]
        return admin_id, signature_text, deserialized_entities
    return None, None, None

def get_channels_for_admin(admin_id):
    """Возвращает список всех каналов для конкретного администратора."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id FROM channels WHERE admin_id = ?', (admin_id,))
    channels = [row[0] for row in cursor.fetchall()]
    conn.close()
    return channels

def delete_channel_signature(admin_id, channel_id):
    """Удаляет канал и его подпись из базы."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM channels WHERE admin_id = ? AND channel_id = ?', (admin_id, channel_id))
    conn.commit()
    conn.close()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def utf16_units_len(s: str) -> int:
    """Возвращает длину строки в количестве UTF-16 code units."""
    return len(s.encode('utf-16-le')) // 2

# === ИНИЦИАЛИЗАЦИЯ БОТА ===

bot = telebot.TeleBot(API_TOKEN)

# --- Обработчик команд администратора ---
# Теперь команды доступны всем, но работают только с их каналами
@bot.message_handler(commands=['start', 'add', 'edit', 'delete', 'list', 'help', 'info'])
def handle_commands(message):
    user_id = message.from_user.id
    if message.text.startswith('/start'):
        response_text = "Привет! \nЯ бот для добавления подписей в ваши каналы. Чтобы начать, добавьте меня в свой канал с правами администратора (для редактирования сообщений).\n\n"
        response_text += "Доступные команды:\n"
        response_text += "/add - Добавить новый канал и подпись\n"
        response_text += "/edit - Изменить подпись существующего канала\n"
        response_text += "/delete - Удалить канал и его подпись из базы бота\n"
        response_text += "/list - Показать список ваших каналов\n"
        response_text += "/info - Показать информацию об ограничениях\n"
        response_text += "/help - Показать список команд бота\n\n"
        response_text += "Моя ссылка: https://t.me/Podpisantus_bot\n"
        response_text += f"Мой никнейм: @Podpisantus_bot\n\n"
        response_text += "Связь с разработчиком: @PostToMe_bot"

        bot.send_message(message.chat.id, response_text)

    elif message.text == '/add':
        user_states[user_id] = {'state': STATE_AWAITING_CHANNEL_LINK, 'channel_id': None}
        bot.send_message(message.chat.id, "Пожалуйста, отправьте никнейм канала (например, @my_channel), где я буду добавлять подпись.")

    elif message.text == '/edit':
        user_states[user_id] = {'state': STATE_AWAITING_EDIT_SIGNATURE, 'channel_id': None}
        bot.send_message(message.chat.id, "Пожалуйста, отправьте никнейм канала (например, @my_channel), подпись которого нужно изменить.")

    elif message.text == '/info':
        response_text = "*Ограничения по длине постов и подписей:*\n\n"
        response_text += "Бот объединяет текст вашего поста с подписью. Важно учитывать лимиты Telegram, чтобы подпись добавлялась корректно.\n\n"
        response_text += "• *Текстовые посты:*\n"
        response_text += "Общая длина текста не должна превышать *4096 символов*.\n\n"
        response_text += "• *Посты с медиафайлами:*\n"
        response_text += "Общая длина подписи (caption) не должна превышать *1024 символа*.\n\n"
        response_text += "*Если длина поста превысит эти ограничения - бот не сможет добавить подпись!*"
        bot.send_message(message.chat.id, response_text, parse_mode='Markdown')

    elif message.text == '/delete':
        user_states[user_id] = {'state': STATE_AWAITING_DELETE_CHANNEL_LINK, 'channel_id': None}
        bot.send_message(message.chat.id, "Пожалуйста, отправьте никнейм канала (например, @my_channel), который нужно удалить.")

    elif message.text == '/list':
        channels = get_channels_for_admin(user_id)
        if not channels:
            bot.send_message(message.chat.id, "База данных каналов пуста.")
            return

        response_text = "Список ваших каналов в базе:\n"
        for channel_id in channels:
            try:
                chat_info = bot.get_chat(channel_id)
                channel_username = f" (@{chat_info.username})" if chat_info.username else ""
                response_text += f"- {chat_info.title} (ID: {channel_id}){channel_username}\n"
            except Exception:
                response_text += f"- Неизвестный канал (ID: {channel_id})\n"
        bot.send_message(message.chat.id, response_text)

    elif message.text == '/help':
        response_text = "Привет! \nЯ бот для добавления подписей в ваши каналы. Чтобы начать, добавьте меня в свой канал с правами администратора (для редактирования сообщений).\n\n"
        response_text += "Доступные команды:\n"
        response_text += "/add - Добавить новый канал и подпись\n"
        response_text += "/edit - Изменить подпись существующего канала\n"
        response_text += "/delete - Удалить канал и его подпись из базы бота\n"
        response_text += "/list - Показать список ваших каналов\n"
        response_text += "/info - Показать информацию об ограничениях\n"
        response_text += "/help - Показать список команд бота\n\n"
        response_text += "Моя ссылка: https://t.me/Podpisantus_bot\n"
        response_text += f"Мой никнейм: @Podpisantus_bot\n\n"
        response_text += "Связь с разработчиком: @PostToMe_bot"

        bot.send_message(message.chat.id, response_text)


@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_replies(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        bot.send_message(message.chat.id, "Не понимаю эту команду. Используйте /start для списка команд.")
        return

    state_info = user_states[user_id]
    current_state = state_info['state']
    text = message.text

    if current_state == STATE_AWAITING_CHANNEL_LINK:
        try:
            chat = bot.get_chat(text)
            channel_id = chat.id

            me = bot.get_chat_member(channel_id, bot.get_me().id)
            if not me.can_edit_messages:
                bot.send_message(message.chat.id, "Я не являюсь администратором в этом канале или у меня нет прав на редактирование сообщений. Операция отменена.")
                del user_states[user_id]
                return

            state_info['channel_id'] = channel_id
            state_info['state'] = STATE_AWAITING_NEW_SIGNATURE
            bot.send_message(message.chat.id, f"Канал '{chat.title}' успешно добавлен. Теперь отправьте текст подписи с форматированием, как вы хотите его видеть.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Не удалось найти канал или получить информацию. Проверьте, что ссылка верна и я добавлен в канал. ")
            del user_states[user_id]
            return

    elif current_state == STATE_AWAITING_NEW_SIGNATURE:
        channel_id = state_info['channel_id']
        signature_text = text
        signature_entities = message.entities if message.entities else []
        add_channel_signature(user_id, channel_id, signature_text, signature_entities)
        bot.send_message(message.chat.id, "Подпись для нового канала успешно сохранена.")
        del user_states[user_id]

    elif current_state == STATE_AWAITING_EDIT_SIGNATURE:
        try:
            chat = bot.get_chat(text)
            channel_id = chat.id

            admin_id_from_db, current_signature, signature_entities = get_channel_signature(channel_id)

            if not admin_id_from_db or admin_id_from_db != user_id:
                bot.send_message(message.chat.id, "Этот канал не найден в вашей базе данных. Используйте /add, чтобы добавить его.")
                del user_states[user_id]
                return

            if current_signature:
                state_info['channel_id'] = channel_id
                state_info['state'] = STATE_AWAITING_NEW_SIGNATURE

                header_text = f"Текущая подпись для канала '{chat.title}':\n\n"
                full_text = header_text + current_signature
                offset_units = utf16_units_len(header_text)

                combined_entities = []
                for entity in signature_entities:
                    new_entity = types.MessageEntity(
                        type=entity.type,
                        offset=entity.offset + offset_units,
                        length=entity.length,
                        url=entity.url,
                        user=entity.user,
                        language=entity.language,
                        custom_emoji_id=entity.custom_emoji_id
                    )
                    combined_entities.append(new_entity)

                bot.send_message(
                    message.chat.id,
                    text=full_text,
                    entities=combined_entities
                )
                bot.send_message(message.chat.id, "Отправьте новую подпись.")
            else:
                bot.send_message(message.chat.id, "Этот канал не найден в вашей базе данных. Используйте /add, чтобы добавить его.")
                del user_states[user_id]
        except Exception as e:
            print(f"Ошибка при редактировании подписи: {e}")
            bot.send_message(message.chat.id, "Не удалось найти канал. Убедитесь, что ссылка верна. Операция отменена.")
            del user_states[user_id]

    elif current_state == STATE_AWAITING_DELETE_CHANNEL_LINK:
        try:
            chat = bot.get_chat(text)
            channel_id = chat.id

            admin_id_from_db, _, _ = get_channel_signature(channel_id)
            if admin_id_from_db == user_id:
                delete_channel_signature(user_id, channel_id)
                bot.send_message(message.chat.id, f"Канал '{chat.title}' успешно удален из базы данных.")
            else:
                bot.send_message(message.chat.id, "Этот канал не найден в вашей базе данных. Ничего не удалено.")
            del user_states[user_id]
        except Exception:
            bot.send_message(message.chat.id, "Не удалось найти канал. Убедитесь, что ссылка верна. Операция отменена.")
            del user_states[user_id]

# --- Обработчик новых постов в канале (доработанный) ---
@bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document', 'audio'])
def handle_new_channel_post(message):
    channel_id = message.chat.id

    # Проверка на сообщения из медиа-групп, у которых нет подписи
    if message.media_group_id and not message.caption:
        return  # Если это часть альбома и нет подписи, просто выходим

    admin_id, signature_text, signature_entities = get_channel_signature(channel_id)

    if not signature_text:
        return

    message_id = message.message_id

    signature_with_spacing = "\n\n" + signature_text

    if message.content_type == 'text':
        original_text = message.text or ""
        original_entities = message.entities if message.entities else []

        start_offset_units = utf16_units_len(original_text + "\n\n")

        for entity in signature_entities:
            entity.offset += start_offset_units

        new_text = original_text + signature_with_spacing
        combined_entities = list(original_entities) + signature_entities

        try:
            bot.edit_message_text(
                chat_id=channel_id,
                message_id=message_id,
                text=new_text,
                entities=combined_entities,
                disable_web_page_preview=True
            )
            print(f"Пост #{message_id} в канале {channel_id} успешно отредактирован.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.info(f"Ошибка при редактировании текстового поста в канале {channel_id}: {e}")

    elif message.content_type in ['photo', 'video', 'document', 'audio']:
        original_caption = message.caption or ""
        original_caption_entities = message.caption_entities if message.caption_entities else []

        start_offset_units = utf16_units_len(original_caption + "\n\n")

        for entity in signature_entities:
            entity.offset += start_offset_units

        new_caption = original_caption + signature_with_spacing
        combined_entities = list(original_caption_entities) + signature_entities

        try:
            bot.edit_message_caption(
                chat_id=channel_id,
                message_id=message_id,
                caption=new_caption,
                caption_entities=combined_entities
            )
            logging.info(f"Подпись к медиа-посту: {message_id} в канале {channel_id} успешно отредактирована.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.info(f"Ошибка при редактировании подписи медиа-поста в канале {channel_id}: {e}")



# === Запуск бота ===
print("Бот запущен...")

while True:
    try:
        # none_stop=True - уже обеспечивает перезапуск для большинства ошибок
        # но обертывание в try/except защищает от фатальных ошибок
        init_db()
        logging.info("Бот запущен и ожидает новые посты и команды...")
        bot.polling(none_stop=True, interval=0, timeout=40)

    except Exception as e:
        # Логирование критической ошибки
        logging.info(f"*** КРИТИЧЕСКАЯ ОШИБКА ВНЕ ПОЛЛИНГА: {e} ***")
        # Ждём перед попыткой перезапуска
        time.sleep(15)
