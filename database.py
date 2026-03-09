import sqlite3
from settings import DatabaseSettings

# 加载数据库设置
db_settings = DatabaseSettings()

# 初始化数据库
def init_db():
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    
    # 检查novels表是否存在
    cursor.execute(f"""
    SELECT name FROM sqlite_master WHERE type='table' AND name='{db_settings.db_table}';
    """)
    table_exists = cursor.fetchone() is not None
    
    if not table_exists:
        # 创建小说表
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_settings.db_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            outline TEXT NOT NULL,
            total_chapters INTEGER,
            chapter_word_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    else:
        # 检查是否需要添加total_chapters字段
        cursor.execute(f"""
        PRAGMA table_info({db_settings.db_table});
        """)
        columns = [column[1] for column in cursor.fetchall()]
        if 'total_chapters' not in columns:
            cursor.execute(f"""
            ALTER TABLE {db_settings.db_table} ADD COLUMN total_chapters INTEGER;
            """)
        if 'chapter_word_count' not in columns:
            cursor.execute(f"""
            ALTER TABLE {db_settings.db_table} ADD COLUMN chapter_word_count INTEGER;
            """)
    
    # 创建章节表
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {db_settings.chapter_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id INTEGER NOT NULL,
        chapter_number INTEGER NOT NULL,
        chapter_title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES {db_settings.db_table} (id)
    )
    """)
    
    # 创建线索表
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS clues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id INTEGER NOT NULL,
        clue_text TEXT NOT NULL,
        clue_type TEXT NOT NULL,  -- 明潮或暗涌
        first_chapter INTEGER NOT NULL,
        next_chapter INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES {db_settings.db_table} (id)
    )
    """)
    
    conn.commit()
    conn.close()

# 数据库操作函数
def add_novel(title, prompt, outline, total_chapters=None, chapter_word_count=None):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO {db_settings.db_table} (title, prompt, outline, total_chapters, chapter_word_count) VALUES (?, ?, ?, ?, ?)
    """, (title, prompt, outline, total_chapters, chapter_word_count))
    conn.commit()
    conn.close()
    return "小说已保存到数据库"

def get_all_novels():
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, title, prompt, created_at FROM {db_settings.db_table} ORDER BY created_at DESC
    """)
    novels = cursor.fetchall()
    conn.close()
    return novels

def get_novel_by_id(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT title, prompt, outline FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    novel = cursor.fetchone()
    conn.close()
    return novel

def update_novel(novel_id, title, prompt, outline):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    UPDATE {db_settings.db_table} SET title = ?, prompt = ?, outline = ? WHERE id = ?
    """, (title, prompt, outline, novel_id))
    conn.commit()
    conn.close()
    return "小说已更新"

def delete_novel(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    # 删除小说的所有章节
    cursor.execute(f"""
    DELETE FROM {db_settings.chapter_table} WHERE novel_id = ?
    """, (novel_id,))
    # 删除小说
    cursor.execute(f"""
    DELETE FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    conn.commit()
    conn.close()
    return "小说已删除"

# 章节相关函数
def add_chapter(novel_id, chapter_number, chapter_title, content):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO {db_settings.chapter_table} (novel_id, chapter_number, chapter_title, content) VALUES (?, ?, ?, ?)
    """, (novel_id, chapter_number, chapter_title, content))
    conn.commit()
    conn.close()
    return "章节已保存"

def get_novel_chapters(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, chapter_number, chapter_title, created_at FROM {db_settings.chapter_table} WHERE novel_id = ? ORDER BY chapter_number ASC
    """, (novel_id,))
    chapters = cursor.fetchall()
    conn.close()
    # 将元组转换为列表，确保DataFrame组件能正确显示
    return [list(chapter) for chapter in chapters]

def get_next_chapter_number(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT MAX(chapter_number) FROM {db_settings.chapter_table} WHERE novel_id = ?
    """, (novel_id,))
    max_chapter = cursor.fetchone()[0]
    conn.close()
    return (max_chapter + 1) if max_chapter else 1

def get_chapter_by_id(chapter_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    print(f"get_chapter_by_id called with chapter_id: {chapter_id}")  # 调试信息
    cursor.execute(f"""
    SELECT chapter_number, chapter_title, content FROM {db_settings.chapter_table} WHERE id = ?
    """, (chapter_id,))
    chapter = cursor.fetchone()
    print(f"Retrieved chapter: {chapter}")  # 调试信息
    conn.close()
    return chapter

def update_chapter(chapter_id, chapter_number, chapter_title, content):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    UPDATE {db_settings.chapter_table} SET chapter_number = ?, chapter_title = ?, content = ? WHERE id = ?
    """, (chapter_number, chapter_title, content, chapter_id))
    conn.commit()
    conn.close()
    return "章节已更新"

def delete_chapter(chapter_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    DELETE FROM {db_settings.chapter_table} WHERE id = ?
    """, (chapter_id,))
    conn.commit()
    conn.close()
    return "章节已删除"

# 线索相关函数
def add_clue(novel_id, clue_text, clue_type, first_chapter, next_chapter=None):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO clues (novel_id, clue_text, clue_type, first_chapter, next_chapter) VALUES (?, ?, ?, ?, ?)
    """, (novel_id, clue_text, clue_type, first_chapter, next_chapter))
    conn.commit()
    conn.close()
    return "线索已保存"

def get_novel_clues(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, clue_text, clue_type, first_chapter, next_chapter FROM clues WHERE novel_id = ?
    """, (novel_id,))
    clues = cursor.fetchall()
    conn.close()
    return clues

def update_clue_next_chapter(clue_id, next_chapter):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    UPDATE clues SET next_chapter = ? WHERE id = ?
    """, (next_chapter, clue_id))
    conn.commit()
    conn.close()
    return "线索已更新"

def delete_clue(clue_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    DELETE FROM clues WHERE id = ?
    """, (clue_id,))
    conn.commit()
    conn.close()
    return "线索已删除"
