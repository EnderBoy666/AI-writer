import gradio as gr
import sqlite3
from ollama import Client
from settings import OllamaSettings, GradioSettings, DatabaseSettings, ChapterSettings, OutlineSettings, ClueSettings

# 加载设置
ollama_settings = OllamaSettings()
gradio_settings = GradioSettings()
db_settings = DatabaseSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
clue_settings = ClueSettings()

# 初始化Ollama客户端
client = Client(host=ollama_settings.base_url)

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

# 初始化数据库
init_db()

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
    return chapters

def get_chapter_by_id(chapter_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT chapter_number, chapter_title, content FROM {db_settings.chapter_table} WHERE id = ?
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

# 生成章节的函数
def generate_chapter(novel_id, chapter_number, word_count, temperature, clue_threshold=3):
    # 确保novel_id是整数
    print(f"novel_id type: {type(novel_id)}, value: {novel_id}")  # 调试信息
    if isinstance(novel_id, list):
        # 检查列表中的元素
        if novel_id and isinstance(novel_id[0], str):
            # 尝试从字符串中提取数字
            try:
                novel_id = int(novel_id[0])
            except ValueError:
                return "无效的小说ID"
        else:
            return "无效的小说ID"
    elif isinstance(novel_id, str):
        # 尝试从字符串中提取数字
        try:
            novel_id = int(novel_id)
        except ValueError:
            return "无效的小说ID"
    else:
        try:
            novel_id = int(novel_id)
        except (ValueError, TypeError):
            return "无效的小说ID"
    
    # 获取小说信息
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT title, outline, total_chapters FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    novel = cursor.fetchone()
    conn.close()
    
    if not novel:
        return "小说不存在"
    
    novel_title, outline, total_chapters = novel
    
    # 获取上一章节内容
    previous_chapter = None
    if chapter_number > 1:
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT content FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, chapter_number - 1))
        previous = cursor.fetchone()
        conn.close()
        if previous:
            previous_chapter = previous[0]
    
    # 获取小说的线索
    clues = get_novel_clues(novel_id)
    active_clues = []
    for clue in clues:
        clue_id, clue_text, clue_type, first_chapter, next_chapter = clue
        # 如果线索应该在本章或之前出现，且尚未在本章之后安排出现
        if (next_chapter is None or next_chapter <= chapter_number):
            active_clues.append((clue_id, clue_text, clue_type, first_chapter))
    
    # 构建系统提示
    system_prompt = f"你是一位专业的小说作家，擅长根据大纲和上一章节生成新的章节。请根据以下信息生成第{chapter_number}章：\n"
    system_prompt += f"小说标题：{novel_title}\n"
    system_prompt += f"小说大纲：{outline}\n"
    if previous_chapter:
        system_prompt += f"上一章节内容：{previous_chapter}\n"
    
    # 添加线索信息
    if active_clues:
        system_prompt += "\n当前需要考虑的线索：\n"
        for _, clue_text, clue_type, first_chapter in active_clues:
            system_prompt += f"- {clue_type}：{clue_text}（首次出现于第{first_chapter}章）\n"
    
    # 添加章节数和阈值信息
    if total_chapters:
        system_prompt += f"\n小说总章节数：{total_chapters}章\n"
        system_prompt += f"当前是第{chapter_number}章\n"
        # 检查是否接近结尾
        if total_chapters - chapter_number <= clue_threshold:
            system_prompt += f"注意：已接近小说结尾（剩余{total_chapters - chapter_number}章），请适当收束线索。\n"
    
    system_prompt += f"\n请生成第{chapter_number}章，字数约{word_count}字，风格保持一致，情节连贯。"
    
    # 生成章节
    response = client.generate(
        model=ollama_settings.model,
        prompt=system_prompt,
        options={"temperature": temperature, "max_tokens": word_count * 2}  # 假设每个字平均2个token
    )
    
    chapter_content = response["response"]
    
    # 提取章节标题
    chapter_title = f"第{chapter_number}章"
    lines = chapter_content.split('\n')
    for line in lines:
        if line.startswith(f"第{chapter_number}章"):
            chapter_title = line.strip()
            break
    
    # 保存章节
    add_chapter(novel_id, chapter_number, chapter_title, chapter_content)
    
    # 更新线索的下次出现时间
    if total_chapters:
        for clue_id, _, _, first_chapter in active_clues:
            # 预估下次线索出现的章节
            # 基于线索首次出现的章节和总章节数
            chapters_passed = chapter_number - first_chapter
            if chapters_passed > 0:
                # 简单算法：平均间隔章节数
                avg_interval = max(1, (total_chapters - first_chapter) // 3)  # 假设线索出现3次
                next_chapter_estimate = chapter_number + avg_interval
                # 确保不超过总章节数
                next_chapter_estimate = min(next_chapter_estimate, total_chapters)
                update_clue_next_chapter(clue_id, next_chapter_estimate)
    
    # 添加线索分析结果到章节内容末尾
    if active_clues and total_chapters:
        chapter_content += "\n\n=== 线索分析 ===\n"
        chapter_content += f"当前章节：第{chapter_number}章\n"
        chapter_content += f"小说总章节数：{total_chapters}章\n"
        if total_chapters - chapter_number <= clue_threshold:
            chapter_content += f"提示：已接近小说结尾，剩余{total_chapters - chapter_number}章\n"
        chapter_content += "\n活跃线索及预估下次出现章节：\n"
        for clue_id, clue_text, clue_type, first_chapter in active_clues:
            # 获取更新后的下次出现章节
            conn = sqlite3.connect(db_settings.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT next_chapter FROM clues WHERE id = ?", (clue_id,))
            next_chapter = cursor.fetchone()[0]
            conn.close()
            chapter_content += f"- {clue_type}：{clue_text} → 预计下次出现于第{next_chapter}章\n"
    
    return chapter_content

# 生成小说大纲的函数
def generate_outline(prompt, chapter_count, chapter_word_count):
    system_prompt = f"你是一位专业的小说编辑，擅长根据提示词生成详细的小说大纲。请根据用户提供的提示词，生成一个结构完整、逻辑清晰的小说大纲，包括：\n1. 小说标题\n2. 故事梗概\n3. 主要角色\n4. 章节大纲（共{chapter_count}章，每章约{chapter_word_count}字）\n5. 故事高潮和结局，禁止使用markdown格式"
    
    response = client.generate(
        model=ollama_settings.model,
        prompt=f"{system_prompt}\n\n提示词：{prompt}",
        options={"temperature": 0.7, "max_tokens": 3000}
    )
    
    return response["response"]

# 从大纲中提取标题
def extract_title(outline):
    lines = outline.split('\n')
    for line in lines:
        if line.startswith('1. 小说标题') or line.startswith('小说标题'):
            title = line.split('：')[1].strip() if '：' in line else line.split(':')[1].strip()
            return title
    return "未知标题"

# 创建Gradio界面
with gr.Blocks(title=gradio_settings.title) as demo:
    gr.Markdown(f"# {gradio_settings.title}")
    gr.Markdown(gradio_settings.description)
    
    # 添加标签页
    with gr.Tabs():
        # 生成大纲标签页
        with gr.Tab("生成大纲"):
            with gr.Row():
                with gr.Column():
                    prompt_input = gr.Textbox(
                        label="输入提示词",
                        placeholder="例如：一个关于人工智能与人类情感的科幻故事",
                        lines=3
                    )
                    chapter_count = gr.Number(
                        label="预计章节数",
                        value=outline_settings.default_chapter_count,
                        minimum=outline_settings.min_chapter_count,
                        maximum=outline_settings.max_chapter_count,
                        step=1
                    )
                    chapter_word_count = gr.Number(
                        label="每章字数",
                        value=outline_settings.default_chapter_word_count,
                        minimum=outline_settings.min_chapter_word_count,
                        maximum=outline_settings.max_chapter_word_count,
                        step=100
                    )
                    generate_btn = gr.Button("生成大纲")
                
                with gr.Column():
                    outline_output = gr.Textbox(
                        label="小说大纲",
                        lines=20
                    )
            
            # 保存到数据库
            save_btn = gr.Button("保存到数据库")
            save_status = gr.Textbox(label="保存状态", interactive=False)
        
        # 管理小说标签页
        with gr.Tab("管理小说"):
            # 小说列表
            novel_list = gr.Dataframe(
                label="小说列表",
                headers=["ID", "标题", "提示词", "创建时间"],
                datatype=["number", "str", "str", "str"],
                interactive=False
            )
            
            # 刷新列表按钮
            refresh_btn = gr.Button("刷新列表")
            
            # 小说详情
            with gr.Row():
                with gr.Column():
                    novel_id = gr.Number(label="小说ID", interactive=False)
                    novel_title = gr.Textbox(label="小说标题")
                    novel_prompt = gr.Textbox(label="提示词", lines=3)
                    novel_outline = gr.Textbox(label="小说大纲", lines=10)
                
                with gr.Column():
                    load_btn = gr.Button("加载小说")
                    update_btn = gr.Button("更新小说")
                    delete_btn = gr.Button("删除小说")
                    action_status = gr.Textbox(label="操作状态", interactive=False)
        
        # 章节管理标签页
        with gr.Tab("章节管理"):
            # 选择小说
            novel_selector = gr.Dropdown(
                label="选择小说",
                choices=[],
                interactive=True,
                allow_custom_value=True
            )
            refresh_novels_btn = gr.Button("刷新小说列表")
            
            # 生成章节部分
            with gr.Row():
                with gr.Column():
                    chapter_number = gr.Number(
                        label="章节编号",
                        value=1,
                        minimum=1,
                        step=1
                    )
                    word_count = gr.Slider(
                        label="字数",
                        minimum=500,
                        maximum=chapter_settings.max_word_count,
                        value=chapter_settings.default_word_count,
                        step=100
                    )
                    temperature = gr.Slider(
                        label="温度",
                        minimum=chapter_settings.min_temperature,
                        maximum=chapter_settings.max_temperature,
                        value=chapter_settings.default_temperature,
                        step=0.1
                    )
                    clue_threshold = gr.Number(
                        label="线索阈值",
                        value=clue_settings.default_clue_threshold,
                        minimum=clue_settings.min_clue_threshold,
                        maximum=clue_settings.max_clue_threshold,
                        step=1
                    )
                    generate_chapter_btn = gr.Button("生成章节")
                
                with gr.Column():
                    chapter_content = gr.Textbox(
                        label="章节内容",
                        lines=20
                    )
                    chapter_status = gr.Textbox(label="生成状态", interactive=False)
            
            # 章节列表
            chapter_list = gr.Dataframe(
                label="章节列表",
                headers=["ID", "章节编号", "章节标题", "创建时间"],
                datatype=["number", "number", "str", "str"],
                interactive=False
            )
            refresh_chapters_btn = gr.Button("刷新章节列表")
            
            # 章节详情
            with gr.Row():
                with gr.Column():
                    chapter_id = gr.Number(label="章节ID", interactive=False)
                    chapter_num = gr.Number(label="章节编号", minimum=1, step=1)
                    chapter_title = gr.Textbox(label="章节标题")
                    chapter_text = gr.Textbox(label="章节内容", lines=10)
                
                with gr.Column():
                    load_chapter_btn = gr.Button("加载章节")
                    update_chapter_btn = gr.Button("更新章节")
                    delete_chapter_btn = gr.Button("删除章节")
                    chapter_action_status = gr.Textbox(label="操作状态", interactive=False)
            
            # 线索管理部分
            gr.Markdown("## 线索管理")
            with gr.Row():
                with gr.Column():
                    clue_text = gr.Textbox(label="线索内容", lines=3)
                    clue_type = gr.Radio(
                        label="线索类型",
                        choices=["明潮", "暗涌"],
                        value="明潮"
                    )
                    clue_chapter = gr.Number(
                        label="首次出现章节",
                        value=1,
                        minimum=1,
                        step=1
                    )
                    add_clue_btn = gr.Button("添加线索")
                    clue_status = gr.Textbox(label="线索操作状态", interactive=False)
                
                with gr.Column():
                    clue_list = gr.Dataframe(
                        label="线索列表",
                        headers=["ID", "线索内容", "线索类型", "首次出现章节", "下次出现章节"],
                        datatype=["number", "str", "str", "number", "number"],
                        interactive=False
                    )
                    refresh_clues_btn = gr.Button("刷新线索列表")
            
            # 线索详情
            with gr.Row():
                with gr.Column():
                    clue_id = gr.Number(label="线索ID", interactive=False)
                    clue_text_edit = gr.Textbox(label="线索内容", lines=3)
                    clue_type_edit = gr.Radio(
                        label="线索类型",
                        choices=["明潮", "暗涌"],
                        value="明潮"
                    )
                    clue_chapter_edit = gr.Number(
                        label="首次出现章节",
                        value=1,
                        minimum=1,
                        step=1
                    )
                
                with gr.Column():
                    load_clue_btn = gr.Button("加载线索")
                    update_clue_btn = gr.Button("更新线索")
                    delete_clue_btn = gr.Button("删除线索")
                    clue_action_status = gr.Textbox(label="线索操作状态", interactive=False)
    
    # 绑定生成函数
    generate_btn.click(
        fn=generate_outline,
        inputs=[prompt_input, chapter_count, chapter_word_count],
        outputs=outline_output
    )
    
    # 绑定保存函数
    def save_novel(prompt, outline, chapter_count, chapter_word_count):
        title = extract_title(outline)
        result = add_novel(title, prompt, outline, chapter_count, chapter_word_count)
        return result
    
    save_btn.click(
        fn=save_novel,
        inputs=[prompt_input, outline_output, chapter_count, chapter_word_count],
        outputs=save_status
    )
    
    # 绑定刷新列表函数
    refresh_btn.click(
        fn=get_all_novels,
        outputs=novel_list
    )
    
    # 绑定加载小说函数
    def load_novel(selected_row):
        if selected_row.empty:
            return [0, "", "", ""]
        novel_id = int(selected_row.iloc[0, 0])
        novel = get_novel_by_id(novel_id)
        if novel:
            return [novel_id, novel[0], novel[1], novel[2]]
        return [0, "", "", ""]
    
    novel_list.select(
        fn=load_novel,
        inputs=novel_list,
        outputs=[novel_id, novel_title, novel_prompt, novel_outline]
    )
    
    # 绑定更新小说函数
    update_btn.click(
        fn=update_novel,
        inputs=[novel_id, novel_title, novel_prompt, novel_outline],
        outputs=action_status
    )
    
    # 绑定删除小说函数
    delete_btn.click(
        fn=delete_novel,
        inputs=novel_id,
        outputs=action_status
    )
    
    # 章节管理相关绑定
    # 获取小说列表用于下拉选择
    def get_novel_choices():
        novels = get_all_novels()
        return [(str(novel[0]), novel[1]) for novel in novels]
    
    # 刷新小说下拉列表
    refresh_novels_btn.click(
        fn=get_novel_choices,
        outputs=novel_selector
    )
    
    # 生成章节
    generate_chapter_btn.click(
        fn=generate_chapter,
        inputs=[novel_selector, chapter_number, word_count, temperature, clue_threshold],
        outputs=chapter_content
    )
    
    # 刷新章节列表
    def refresh_chapters(novel_id_str):
        if not novel_id_str:
            return []
        # 确保novel_id_str是字符串或整数
        if isinstance(novel_id_str, list):
            novel_id_str = novel_id_str[0] if novel_id_str else 0
        novel_id = int(novel_id_str)
        return get_novel_chapters(novel_id)
    
    refresh_chapters_btn.click(
        fn=refresh_chapters,
        inputs=novel_selector,
        outputs=chapter_list
    )
    
    # 加载章节
    def load_chapter(selected_row):
        if selected_row.empty:
            return [0, 1, "", ""]
        chapter_id = int(selected_row.iloc[0, 0])
        chapter = get_chapter_by_id(chapter_id)
        if chapter:
            return [chapter_id, chapter[0], chapter[1], chapter[2]]
        return [0, 1, "", ""]
    
    chapter_list.select(
        fn=load_chapter,
        inputs=chapter_list,
        outputs=[chapter_id, chapter_num, chapter_title, chapter_text]
    )
    
    # 更新章节
    update_chapter_btn.click(
        fn=update_chapter,
        inputs=[chapter_id, chapter_num, chapter_title, chapter_text],
        outputs=chapter_action_status
    )
    
    # 删除章节
    delete_chapter_btn.click(
        fn=delete_chapter,
        inputs=chapter_id,
        outputs=chapter_action_status
    )
    
    # 线索管理相关绑定
    # 添加线索
    def add_new_clue(novel_id_str, text, clue_type, chapter):
        if not novel_id_str:
            return "请选择小说"
        # 确保novel_id_str是字符串或整数
        if isinstance(novel_id_str, list):
            novel_id_str = novel_id_str[0] if novel_id_str else 0
        novel_id = int(novel_id_str)
        return add_clue(novel_id, text, clue_type, chapter)
    
    add_clue_btn.click(
        fn=add_new_clue,
        inputs=[novel_selector, clue_text, clue_type, clue_chapter],
        outputs=clue_status
    )
    
    # 刷新线索列表
    def refresh_clues(novel_id_str):
        if not novel_id_str:
            return []
        # 确保novel_id_str是字符串或整数
        if isinstance(novel_id_str, list):
            novel_id_str = novel_id_str[0] if novel_id_str else 0
        novel_id = int(novel_id_str)
        return get_novel_clues(novel_id)
    
    refresh_clues_btn.click(
        fn=refresh_clues,
        inputs=novel_selector,
        outputs=clue_list
    )
    
    # 加载线索
    def load_clue(selected_row):
        if selected_row.empty:
            return [0, "", "明潮", 1]
        clue_id = int(selected_row.iloc[0, 0])
        # 获取线索详情
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT clue_text, clue_type, first_chapter FROM clues WHERE id = ?", (clue_id,))
        clue = cursor.fetchone()
        conn.close()
        if clue:
            return [clue_id, clue[0], clue[1], clue[2]]
        return [0, "", "明潮", 1]
    
    clue_list.select(
        fn=load_clue,
        inputs=clue_list,
        outputs=[clue_id, clue_text_edit, clue_type_edit, clue_chapter_edit]
    )
    
    # 更新线索
    def update_clue(clue_id, text, clue_type, chapter):
        if not clue_id:
            return "请选择线索"
        # 更新线索
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE clues SET clue_text = ?, clue_type = ?, first_chapter = ? WHERE id = ?", (text, clue_type, chapter, clue_id))
        conn.commit()
        conn.close()
        return "线索已更新"
    
    update_clue_btn.click(
        fn=update_clue,
        inputs=[clue_id, clue_text_edit, clue_type_edit, clue_chapter_edit],
        outputs=clue_action_status
    )
    
    # 删除线索
    delete_clue_btn.click(
        fn=delete_clue,
        inputs=clue_id,
        outputs=clue_action_status
    )

if __name__ == "__main__":
    demo.launch(theme=gradio_settings.theme)