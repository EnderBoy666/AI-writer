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
    

    
    # 创建使用统计表
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS usage_statistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,  -- 事件类型：generate_outline, generate_chapter, batch_generate, etc.
        novel_id INTEGER,
        chapter_number INTEGER,
        token_count INTEGER DEFAULT 0,
        word_count INTEGER DEFAULT 0,
        temperature REAL,
        duration_seconds REAL,
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
    SELECT id, title, prompt, outline, total_chapters, chapter_word_count FROM {db_settings.db_table} WHERE id = ?
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
    SELECT id, chapter_number, chapter_title, content, created_at FROM {db_settings.chapter_table} WHERE novel_id = ? ORDER BY chapter_number ASC
    """, (novel_id,))
    chapters = cursor.fetchall()
    conn.close()
    return [list(chapter) for chapter in chapters]

def get_chapter_by_number(novel_id, chapter_number):
    """获取指定章节的完整内容"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, chapter_number, chapter_title, content FROM {db_settings.chapter_table} 
    WHERE novel_id = ? AND chapter_number = ?
    """, (novel_id, chapter_number))
    chapter = cursor.fetchone()
    conn.close()
    return chapter

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
    cursor.execute(f"""
    SELECT id, chapter_number, chapter_title, content FROM {db_settings.chapter_table} WHERE id = ?
    """, (chapter_id,))
    chapter = cursor.fetchone()
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

# 章节大纲相关函数
def add_chapter_outline(novel_id, chapter_number, chapter_title, outline):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO chapter_outlines (novel_id, chapter_number, chapter_title, outline) 
    VALUES (?, ?, ?, ?)
    ON CONFLICT(novel_id, chapter_number) 
    DO UPDATE SET chapter_title = excluded.chapter_title, outline = excluded.outline
    """, (novel_id, chapter_number, chapter_title, outline))
    conn.commit()
    conn.close()


# 使用统计相关函数
def record_usage(event_type, novel_id=None, chapter_number=None, token_count=0, word_count=0, temperature=None, duration_seconds=None):
    """记录使用统计信息"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    INSERT INTO usage_statistics (event_type, novel_id, chapter_number, token_count, word_count, temperature, duration_seconds)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_type, novel_id, chapter_number, token_count, word_count, temperature, duration_seconds))
    conn.commit()
    conn.close()

def get_usage_statistics(start_date=None, end_date=None):
    """获取使用统计数据"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    
    # 基础查询
    base_query = f"SELECT * FROM usage_statistics WHERE 1=1"
    params = []
    
    # 添加日期过滤
    if start_date:
        base_query += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        base_query += " AND date(created_at) <= date(?)"
        params.append(end_date)
    
    cursor.execute(base_query, params)
    records = cursor.fetchall()
    conn.close()
    return records

def get_statistics_summary(start_date=None, end_date=None):
    """获取统计数据摘要"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    
    # 基础查询条件
    base_where = "WHERE 1=1"
    params = []
    
    if start_date:
        base_where += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        base_where += " AND date(created_at) <= date(?)"
        params.append(end_date)
    
    # 总体统计
    cursor.execute(f"""
    SELECT 
        COUNT(*) as total_events,
        SUM(token_count) as total_tokens,
        SUM(word_count) as total_words,
        COUNT(DISTINCT novel_id) as novels_count,
        AVG(temperature) as avg_temperature
    FROM usage_statistics {base_where}
    """, params)
    overall = cursor.fetchone()
    
    # 按事件类型统计
    cursor.execute(f"""
    SELECT 
        event_type,
        COUNT(*) as count,
        SUM(token_count) as tokens,
        SUM(word_count) as words
    FROM usage_statistics {base_where}
    GROUP BY event_type
    """, params)
    by_type = cursor.fetchall()
    
    # 按小说统计（前 10 个）
    cursor.execute(f"""
    SELECT 
        n.title,
        COUNT(us.id) as events,
        SUM(us.token_count) as tokens,
        SUM(us.word_count) as words
    FROM usage_statistics us
    LEFT JOIN {db_settings.db_table} n ON us.novel_id = n.id
    {base_where}
    GROUP BY us.novel_id, n.title
    ORDER BY events DESC
    LIMIT 10
    """, params)
    by_novel = cursor.fetchall()
    
    # 每日趋势（最近 30 天）
    cursor.execute(f"""
    SELECT 
        date(created_at) as date,
        COUNT(*) as events,
        SUM(token_count) as tokens,
        SUM(word_count) as words
    FROM usage_statistics
    WHERE date(created_at) >= date('now', '-30 days')
    GROUP BY date(created_at)
    ORDER BY date DESC
    """)
    daily_trend = cursor.fetchall()
    
    conn.close()
    
    return {
        'overall': overall,
        'by_type': by_type,
        'by_novel': by_novel,
        'daily_trend': daily_trend
    }

def get_total_tokens():
    """获取总 token 使用量"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(token_count), 0) FROM usage_statistics")
    total = cursor.fetchone()[0]
    conn.close()
    return total

def get_total_generations():
    """获取总生成次数"""
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usage_statistics")
    total = cursor.fetchone()[0]
    conn.close()
    return total
