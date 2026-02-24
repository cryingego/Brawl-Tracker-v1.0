import sqlite3

# Создаем базу и таблицу при запуске
def init_db():
    conn = sqlite3.connect('brawl_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracked_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            player_tag TEXT,
            UNIQUE(user_id, player_tag) 
        )
    ''')
    conn.commit()
    conn.close()

# Функция добавления тега
def add_player(user_id, tag):
    conn = sqlite3.connect('brawl_data.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO tracked_players (user_id, player_tag) VALUES (?, ?)', (user_id, tag))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Если такой тег уже есть у юзера
    finally:
        conn.close()

# Функция получения всех тегов пользователя
def get_players(user_id):
    conn = sqlite3.connect('brawl_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT player_tag FROM tracked_players WHERE user_id = ?', (user_id,))
    tags = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tags

def delete_player(user_id, tag):
    conn = sqlite3.connect('brawl_data.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tracked_players WHERE user_id = ? AND player_tag = ?', (user_id, tag))
    conn.commit()
    conn.close()