import sqlite3
import json

DB_FILE = 'channel_signatures.db'

def print_db_content():
    """
    Подключается к базе данных и выводит содержимое таблицы 'channels'.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Выбираем все записи из таблицы channels
        cursor.execute('SELECT admin_id, channel_id, signature_text, signature_entities FROM channels')
        rows = cursor.fetchall()

        if not rows:
            print("База данных пуста или таблица 'channels' не содержит записей.")
            return

        print("Содержимое таблицы 'channels':")
        print("-" * 50)
        
        for row in rows:
            admin_id, channel_id, signature_text, signature_entities_json = row
            
            # Декодируем сущности из JSON для удобного отображения
            try:
                entities = json.loads(signature_entities_json)
            except json.JSONDecodeError:
                entities = "Ошибка декодирования"

            print(f"ID Администратора: {admin_id}")
            print(f"ID Канала: {channel_id}")
            print(f"Текст подписи: {signature_text}")
            print(f"Сущности (форматирование): {entities}")
            print("-" * 50)

    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print_db_content()
