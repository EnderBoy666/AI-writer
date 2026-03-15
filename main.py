import gradio as gr
from settings import GradioSettings, DatabaseSettings, ChapterSettings, OutlineSettings, ClueSettings, OutlineGenerationSettings
from database import init_db, add_novel, get_all_novels, get_novel_by_id, update_novel, delete_novel, get_novel_chapters, get_next_chapter_number, get_chapter_by_id, update_chapter, delete_chapter, add_clue, get_novel_clues, update_clue_next_chapter, delete_clue
from generator import generate_outline, generate_outline_streaming, extract_title, generate_chapter, generate_chapter_streaming, extract_clues_from_chapter

# 加载设置
gradio_settings = GradioSettings()
db_settings = DatabaseSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
clue_settings = ClueSettings()
outline_gen_settings = OutlineGenerationSettings()

# 初始化数据库
init_db()

# 批量生成章节的函数
def batch_generate_chapters(novel_id, start_chapter, batch_count, word_count, temperature, clue_threshold, auto_add_clue, clue_count=2):
    # 确保novel_id是整数
    print(f"处理小说选择值: {novel_id}")
    
    if not novel_id:
        return "无效的小说ID"
    
    # 获取小说信息（大纲和总章节数）
    print("正在获取小说信息...")
    import sqlite3
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT outline, total_chapters FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    novel_info = cursor.fetchone()
    conn.close()
    
    if not novel_info:
        return "小说不存在"
    
    novel_outline, total_chapters = novel_info
    print(f"小说总章节数：{total_chapters}")
    
    # 批量生成章节
    generated_chapters = []
    for i in range(batch_count):
        current_chapter = start_chapter + i
        print(f"\n开始生成第{current_chapter}章...")
        # 检查章节编号是否已存在
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT id FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, current_chapter))
        existing_chapter = cursor.fetchone()
        conn.close()
        
        if existing_chapter:
            return f"章节 {current_chapter} 已经存在，请修改起始章节编号"
        
        # 生成章节
        result = generate_chapter(novel_id, current_chapter, word_count, temperature, clue_threshold)
        if isinstance(result, tuple):
            chapter_content, _ = result
            generated_chapters.append(f"第{current_chapter}章")
            
            # 自动添加线索
            if auto_add_clue:
                print(f"正在为第{current_chapter}章添加线索...")
                extracted_clues = extract_clues_from_chapter(chapter_content, current_chapter, novel_outline, total_chapters, clue_count)
                for clue_text, clue_type, first_chapter, next_chapter in extracted_clues:
                    add_clue(novel_id, clue_text, clue_type, first_chapter, next_chapter)
                print("线索添加完成")
        else:
            return f"生成第{current_chapter}章失败: {result}"
    
    # 构建返回信息
    if generated_chapters:
        return f"成功生成章节: {', '.join(generated_chapters)}"
    else:
        return "未生成任何章节"

# 创建 Gradio 界面
with gr.Blocks(title=gradio_settings.title, theme=gradio_settings.theme) as demo:
    # 页面标题和描述
    gr.Markdown(f"# 📚 {gradio_settings.title}")
    gr.Markdown(gradio_settings.description)
    
    # 状态管理，用于存储生成的大纲（纯净版本）
    generated_outline_state = gr.State("")
    
    # 添加标签页
    with gr.Tabs():
        # ========== 生成大纲标签页 ==========
        with gr.Tab("📝 生成大纲", id=1):
            # 参数说明区域
            with gr.Accordion("📖 参数说明和使用建议", open=False):
                gr.Markdown("""
                #### 参数说明
                - **提示词**：小说的核心创意和故事梗概
                - **预计章节数**：整部小说的总章节数量
                - **每章字数**：每章的预期字数
                - **章节间隔**：每隔多少章为一个事件单元（例如：设置为 5 表示每 5 章为一个事件）
                - **拆分次数**：将大纲生成拆分为多少次完成（例如：100 章拆分 5 次，每次生成约 20 章）
                - **温度**：控制生成的随机性（0.1 最保守，1.0 最发散）
                
                #### 使用建议
                | 小说类型 | 章节数范围 | 拆分次数 | 章节间隔 |
                |---------|-----------|---------|---------|
                | 短篇 | <50 章 | 1-2 次 | 2-3 章 |
                | 中长篇 | 50-200 章 | 3-5 次 | 5-10 章 |
                | 超长篇 | >200 章 | 5-10 次 | 10-20 章 |
                
                #### 流式输出特性
                - ✅ 生成过程实时显示进度，包括基础骨架和各段大纲
                - ✅ 每完成一段大纲会立即显示，无需等待全部完成
                - ✅ 可以随时观察生成进度和内容质量
                - ✅ 章节生成支持流式输出，实时显示生成进度和完整内容
                - ✅ 自动保存生成的章节到数据库
                - ✅ 显示线索分析和下次出现章节预测
                """)
            
            # 参数输入区域
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### ⚙️ 参数设置")
                    prompt_input = gr.Textbox(
                        label="📌 提示词",
                        placeholder="例如：一个关于人工智能与人类情感的科幻故事，讲述 AI 逐渐产生自我意识的过程...",
                        lines=4
                    )
                    
                    with gr.Row():
                        chapter_count = gr.Number(
                            label="📊 预计章节数",
                            value=outline_settings.default_chapter_count,
                            minimum=outline_settings.min_chapter_count,
                            maximum=outline_settings.max_chapter_count,
                            step=1
                        )
                        chapter_word_count = gr.Number(
                            label="✍️ 每章字数",
                            value=outline_settings.default_chapter_word_count,
                            minimum=outline_settings.min_chapter_word_count,
                            maximum=outline_settings.max_chapter_word_count,
                            step=100
                        )
                    
                    with gr.Row():
                        chapter_interval = gr.Number(
                            label="🔗 章节间隔",
                            value=outline_settings.default_chapter_interval,
                            minimum=outline_settings.min_chapter_interval,
                            maximum=outline_settings.max_chapter_interval,
                            step=1
                        )
                        split_count = gr.Number(
                            label="🔪 拆分次数",
                            value=outline_gen_settings.default_split_count,
                            minimum=outline_gen_settings.min_split_count,
                            maximum=outline_gen_settings.max_split_count,
                            step=1
                        )
                    
                    temperature = gr.Slider(
                        label="🎲 温度参数",
                        minimum=0.1,
                        maximum=1.0,
                        value=0.7,
                        step=0.1,
                        interactive=True,
                        info="较低值（0.1-0.5）更保守，较高值（0.7-1.0）更有创意"
                    )
                    
                    generate_btn = gr.Button("🚀 生成大纲", variant="primary", size="lg")
                
                with gr.Column(scale=1):
                    gr.Markdown("### 📋 生成结果")
                    outline_output = gr.Textbox(
                        label="小说大纲",
                        lines=25,
                        placeholder="大纲内容将在这里实时显示..."
                    )
            
            # 保存操作区域
            with gr.Row():
                save_btn = gr.Button("💾 保存到数据库", variant="primary", size="lg")
                save_status = gr.Textbox(label="保存状态", interactive=False, show_label=True)
        
        # ========== 管理小说标签页 ==========
        with gr.Tab("📚 管理小说", id=2):
            gr.Markdown("### 📖 小说列表")
            # 小说列表
            novel_list = gr.Dataframe(
                label="小说列表",
                headers=["ID", "标题", "提示词", "创建时间"],
                datatype=["number", "str", "str", "str"],
                interactive=False,
                wrap=True
            )
            
            # 刷新列表按钮
            refresh_btn = gr.Button("🔄 刷新列表", variant="secondary")
            
            gr.Markdown("### 📝 小说详情")
            # 小说详情
            with gr.Row():
                with gr.Column(scale=2):
                    novel_id = gr.Number(label="🆔 小说 ID", interactive=False)
                    novel_title = gr.Textbox(label="📚 小说标题")
                    novel_prompt = gr.Textbox(label="💡 提示词", lines=3)
                    novel_outline = gr.Textbox(label="📋 小说大纲", lines=10)
                
                with gr.Column(scale=1):
                    load_btn = gr.Button("📥 加载小说", variant="secondary")
                    update_btn = gr.Button("✏️ 更新小说", variant="primary")
                    delete_btn = gr.Button("🗑️ 删除小说", variant="stop")
                    action_status = gr.Textbox(label="操作状态", interactive=False)
        
        # ========== 章节管理标签页 ==========
        with gr.Tab("📖 章节管理", id=3):
            # 选择小说区域
            gr.Markdown("### 📚 选择小说")
            novel_list_chapter = gr.Dataframe(
                label="小说列表",
                headers=["ID", "标题", "提示词", "创建时间"],
                datatype=["number", "str", "str", "str"],
                interactive=False,
                wrap=True
            )
            refresh_novels_btn = gr.Button("🔄 刷新小说列表", variant="secondary")
            selected_novel_id = gr.Number(label="📌 当前选择的小说 ID", interactive=False)
            
            # 生成章节区域
            gr.Markdown("### ✍️ 生成章节")
            with gr.Row():
                with gr.Column(scale=1):
                    with gr.Group():
                        gr.Markdown("**📝 章节设置**")
                        chapter_number = gr.Number(
                            label="🔢 章节编号",
                            value=1,
                            minimum=1,
                            step=1
                        )
                        word_count = gr.Slider(
                            label="📏 字数",
                            minimum=500,
                            maximum=chapter_settings.max_word_count,
                            value=chapter_settings.default_word_count,
                            step=100
                        )
                        temperature = gr.Slider(
                            label="🎲 温度",
                            minimum=chapter_settings.min_temperature,
                            maximum=chapter_settings.max_temperature,
                            value=chapter_settings.default_temperature,
                            step=0.1,
                            interactive=True
                        )
                        clue_threshold = gr.Number(
                            label="⚠️ 线索阈值",
                            value=clue_settings.default_clue_threshold,
                            minimum=clue_settings.min_clue_threshold,
                            maximum=clue_settings.max_clue_threshold,
                            step=1,
                            info="接近结尾时收束线索的章节数阈值"
                        )
                    
                    with gr.Group():
                        gr.Markdown("**⚡ 批量生成**")
                        batch_chapter_count = gr.Number(
                            label="📦 批量编写章节数",
                            value=1,
                            minimum=1,
                            step=1
                        )
                        auto_add_clue = gr.Checkbox(
                            label="✅ 自动添加线索",
                            value=False
                        )
                        clue_count = gr.Number(
                            label="🎯 每章线索数量",
                            value=2,
                            minimum=1,
                            maximum=10,
                            step=1
                        )
                    
                    with gr.Row():
                        generate_chapter_btn = gr.Button("🚀 生成章节", variant="primary", size="lg")
                        batch_generate_btn = gr.Button("📦 批量生成", variant="secondary", size="lg")
                
                with gr.Column(scale=2):
                    chapter_content = gr.Textbox(
                        label="📄 章节内容",
                        lines=25,
                        placeholder="生成的章节内容将在这里实时显示..."
                    )
                    chapter_status = gr.Textbox(label="生成状态", interactive=False)
                    show_clue_dialog = gr.State(False)  # 用于控制线索对话框的显示
                    batch_status = gr.Textbox(label="批量生成状态", interactive=False)
            
            # 章节列表区域
            gr.Markdown("### 📋 章节列表")
            chapter_list = gr.Dataframe(
                label="章节列表",
                headers=["ID", "章节编号", "章节标题", "创建时间"],
                datatype=["number", "number", "str", "str"],
                interactive=False,
                row_count="dynamic",
                wrap=True
            )
            refresh_chapters_btn = gr.Button("🔄 刷新章节列表", variant="secondary")
            
            # 章节详情区域
            gr.Markdown("### 📝 章节详情")
            with gr.Row():
                with gr.Column(scale=2):
                    chapter_id = gr.Number(label="🆔 章节 ID", interactive=False)
                    chapter_num = gr.Number(label="🔢 章节编号", minimum=1, step=1)
                    chapter_title = gr.Textbox(label="📚 章节标题")
                    chapter_text = gr.Textbox(label="📄 章节内容", lines=10)
                
                with gr.Column(scale=1):
                    load_chapter_btn = gr.Button("📥 加载章节", variant="secondary")
                    update_chapter_btn = gr.Button("✏️ 更新章节", variant="primary")
                    delete_chapter_btn = gr.Button("🗑️ 删除章节", variant="stop")
                    chapter_action_status = gr.Textbox(label="操作状态", interactive=False)
            
            # 线索管理区域
            with gr.Accordion("🔍 线索管理", open=False):
                gr.Markdown("管理小说中的明潮和暗涌线索，追踪线索的出现和收束")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("**➕ 添加新线索**")
                        clue_text = gr.Textbox(label="📝 线索内容", lines=3, placeholder="描述线索的具体内容...")
                        clue_type = gr.Radio(
                            label="🏷️ 线索类型",
                            choices=["明潮", "暗涌"],
                            value="明潮",
                            info="明潮：明显的情节线索；暗涌：隐藏的伏笔线索"
                        )
                        clue_chapter = gr.Number(
                            label="📍 首次出现章节",
                            value=1,
                            minimum=1,
                            step=1
                        )
                        add_clue_btn = gr.Button("➕ 添加线索", variant="primary")
                        clue_status = gr.Textbox(label="操作状态", interactive=False)
                    
                    with gr.Column(scale=2):
                        gr.Markdown("**📋 线索列表**")
                        clue_list = gr.Dataframe(
                            label="线索列表",
                            headers=["ID", "线索内容", "线索类型", "首次出现章节", "下次出现章节"],
                            datatype=["number", "str", "str", "number", "number"],
                            interactive=False,
                            wrap=True
                        )
                        refresh_clues_btn = gr.Button("🔄 刷新线索列表", variant="secondary")
                
                gr.Markdown("**✏️ 编辑线索**")
                with gr.Row():
                    with gr.Column(scale=2):
                        clue_id = gr.Number(label="🆔 线索 ID", interactive=False)
                        clue_text_edit = gr.Textbox(label="📝 线索内容", lines=3)
                        clue_type_edit = gr.Radio(
                            label="🏷️ 线索类型",
                            choices=["明潮", "暗涌"],
                            value="明潮"
                        )
                        clue_chapter_edit = gr.Number(
                            label="📍 首次出现章节",
                            value=1,
                            minimum=1,
                            step=1
                        )
                    
                    with gr.Column(scale=1):
                        load_clue_btn = gr.Button("📥 加载线索", variant="secondary")
                        update_clue_btn = gr.Button("✏️ 更新线索", variant="primary")
                        delete_clue_btn = gr.Button("🗑️ 删除线索", variant="stop")
                        clue_action_status = gr.Textbox(label="操作状态", interactive=False)
            
            # 生成章节后询问是否添加线索的对话框
            with gr.Blocks(visible=False) as clue_dialog:
                gr.Markdown("✅ **章节生成成功！** 是否要为该章节添加线索？")
                with gr.Row():
                    yes_btn = gr.Button("✅ 是", variant="primary")
                    no_btn = gr.Button("❌ 否", variant="secondary")
    
    # 绑定生成函数（流式输出）
    def generate_and_store(prompt, chapter_count, chapter_word_count, chapter_interval, split_count, temperature):
        # 使用流式生成函数，但收集最终结果用于保存
        full_outline = ""
        for output in generate_outline_streaming(prompt, chapter_count, chapter_word_count, chapter_interval, split_count, temperature):
            full_outline = output  # 保留最新的完整输出
            # 每次 yield 都返回两个值：完整输出（显示）和当前纯净大纲（存储）
            if "=== 完整大纲 ===" in full_outline:
                clean_outline = full_outline.split("=== 完整大纲 ===")[1].strip()
            else:
                clean_outline = ""
            yield output, clean_outline
        
        # 最终返回完整的大纲内容用于状态存储
        if "=== 完整大纲 ===" in full_outline:
            clean_outline = full_outline.split("=== 完整大纲 ===")[1].strip()
        else:
            clean_outline = full_outline
        yield full_outline, clean_outline
    
    generate_btn.click(
        fn=generate_and_store,
        inputs=[prompt_input, chapter_count, chapter_word_count, chapter_interval, split_count, temperature],
        outputs=[outline_output, generated_outline_state],
        api_name="generate_outline"
    )
    
    # 绑定保存函数
    def save_novel_to_db(clean_outline):
        if not clean_outline:
            return "大纲不能为空"
        title = extract_title(clean_outline)
        # 确保提示词不为空
        prompt = prompt_input.value if prompt_input.value else f"{title}的小说"
        return add_novel(title, prompt, clean_outline)
    
    save_btn.click(
        fn=save_novel_to_db,
        inputs=generated_outline_state,
        outputs=save_status
    )
    
    # 绑定刷新小说列表函数
    def refresh_novel_list():
        novels = get_all_novels()
        return novels
    
    refresh_btn.click(
        fn=refresh_novel_list,
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
    # 绑定刷新小说列表函数
    def refresh_novel_list_chapter():
        novels = get_all_novels()
        return novels
    
    refresh_novels_btn.click(
        fn=refresh_novel_list_chapter,
        outputs=novel_list_chapter
    )
    
    # 绑定选择小说函数
    def select_novel_chapter(selected_row, evt: gr.SelectData):
        print(f"Selected row: {selected_row}")
        print(f"Selected row type: {type(selected_row)}")
        print(f"Event index: {evt.index}")
        
        try:
            # 获取选中行的索引
            row_index = evt.index[0]
            print(f"Row index: {row_index}")
            
            # 尝试处理 pandas DataFrame 格式
            if hasattr(selected_row, 'iloc'):
                if selected_row.empty:
                    return 0
                novel_id = int(selected_row.iloc[row_index, 0])
                print(f"Extracted novel_id from DataFrame: {novel_id}")
                return novel_id
            # 尝试处理列表格式
            elif isinstance(selected_row, list):
                if len(selected_row) > 0:
                    if isinstance(selected_row[0], list):
                        # 嵌套列表格式
                        novel_id = int(selected_row[row_index][0])
                        print(f"Extracted novel_id from nested list: {novel_id}")
                        return novel_id
                    else:
                        # 单层列表格式
                        novel_id = int(selected_row[row_index])
                        print(f"Extracted novel_id from list: {novel_id}")
                        return novel_id
        except Exception as e:
            print(f"Error in select_novel_chapter: {e}")
        
        return 0
    
    novel_list_chapter.select(
        fn=select_novel_chapter,
        inputs=novel_list_chapter,
        outputs=selected_novel_id
    )
    
    # 当选择小说时，自动填写下一个章节数
    def update_chapter_number(novel_id):
        if not novel_id:
            return 1
        
        if novel_id:
            return get_next_chapter_number(novel_id)
        return 1
    
    # 绑定小说选择变化事件
    selected_novel_id.change(
        fn=update_chapter_number,
        inputs=selected_novel_id,
        outputs=chapter_number
    )
    
    # 生成章节（流式输出）
    def generate_chapter_wrapper(novel_id, chapter_num, word_count, temperature, clue_threshold):
        # 使用流式生成函数
        for output in generate_chapter_streaming(novel_id, chapter_num, word_count, temperature, clue_threshold):
            # 检查是否是最终的成功标记
            if isinstance(output, tuple) and len(output) == 2:
                # 返回最终内容和成功标志
                yield output[0], True
            else:
                # 返回进度文本
                yield output, False
    
    generate_chapter_btn.click(
        fn=generate_chapter_wrapper,
        inputs=[selected_novel_id, chapter_number, word_count, temperature, clue_threshold],
        outputs=[chapter_content, show_clue_dialog],
        api_name="generate_chapter"
    )
    
    # 显示线索对话框
    def show_clue_dialog_func(show):
        if show:
            return gr.update(visible=True)
        return gr.update(visible=False)
    
    show_clue_dialog.change(
        fn=show_clue_dialog_func,
        inputs=show_clue_dialog,
        outputs=clue_dialog
    )
    
    # 处理"是"按钮点击
    def handle_yes():
        # 可以在这里添加自动填充线索表单的逻辑
        return gr.update(visible=False), False
    
    yes_btn.click(
        fn=handle_yes,
        outputs=[clue_dialog, show_clue_dialog]
    )
    
    # 处理"否"按钮点击
    def handle_no():
        return gr.update(visible=False), False
    
    no_btn.click(
        fn=handle_no,
        outputs=[clue_dialog, show_clue_dialog]
    )
    
    # 批量生成章节
    batch_generate_btn.click(
        fn=batch_generate_chapters,
        inputs=[selected_novel_id, chapter_number, batch_chapter_count, word_count, temperature, clue_threshold, auto_add_clue, clue_count],
        outputs=batch_status,
        api_name="batch_generate_chapters"
    )
    
    # 刷新章节列表
    def refresh_chapters(novel_id):
        if not novel_id:
            return []
        
        if novel_id:
            return get_novel_chapters(novel_id)
        return []
    
    refresh_chapters_btn.click(
        fn=refresh_chapters,
        inputs=selected_novel_id,
        outputs=chapter_list
    )
    
    # 加载章节
    def load_chapter(selected_row, evt: gr.SelectData):
        try:
            # 获取选中行的索引（行号）
            idx = evt.index[0]
            # 从数据框中提取该行的 ID（第一列）
            chapter_id = int(selected_row.iloc[idx, 0])
            # 获取章节内容
            chapter = get_chapter_by_id(chapter_id)
            if chapter:
                return [chapter_id, chapter[0], chapter[1], chapter[2]]
            else:
                return [0, 1, "", ""]
        except Exception as e:
            print(f"Error in load_chapter: {e}")
            return [0, 1, "", ""]
    
    chapter_list.select(
        fn=load_chapter,
        inputs=[chapter_list],
        outputs=[chapter_id, chapter_num, chapter_title, chapter_text]
    )
    
    # 绑定更新章节函数
    update_chapter_btn.click(
        fn=update_chapter,
        inputs=[chapter_id, chapter_num, chapter_title, chapter_text],
        outputs=chapter_action_status
    )
    
    # 绑定删除章节函数
    delete_chapter_btn.click(
        fn=delete_chapter,
        inputs=chapter_id,
        outputs=chapter_action_status
    )
    
    # 绑定添加线索函数
    def add_new_clue(novel_id, text, clue_type, chapter):
        if not novel_id:
            return "请选择小说"
        return add_clue(novel_id, text, clue_type, chapter)
    
    add_clue_btn.click(
        fn=add_new_clue,
        inputs=[selected_novel_id, clue_text, clue_type, clue_chapter],
        outputs=clue_status
    )
    
    # 刷新线索列表
    def refresh_clues(novel_id):
        if not novel_id:
            return []
        return get_novel_clues(novel_id)
    
    refresh_clues_btn.click(
        fn=refresh_clues,
        inputs=selected_novel_id,
        outputs=clue_list
    )
    
    # 加载线索
    def load_clue(selected_row, evt: gr.SelectData):
        try:
            # 获取选中行的索引（行号）
            idx = evt.index[0]
            # 从数据框中提取该行的 ID（第一列）
            clue_id = int(selected_row.iloc[idx, 0])
            # 获取线索内容
            clues = get_novel_clues(novel_id.value)
            for clue in clues:
                if clue[0] == clue_id:
                    return [clue_id, clue[1], clue[2], clue[3]]
            return [0, "", "明潮", 1]
        except Exception as e:
            print(f"Error in load_clue: {e}")
            return [0, "", "明潮", 1]
    
    clue_list.select(
        fn=load_clue,
        inputs=[clue_list],
        outputs=[clue_id, clue_text_edit, clue_type_edit, clue_chapter_edit]
    )
    
    # 绑定更新线索函数
    update_clue_btn.click(
        fn=update_clue_next_chapter,
        inputs=[clue_id, clue_chapter_edit],
        outputs=clue_action_status
    )
    
    # 删除线索
    delete_clue_btn.click(
        fn=delete_clue,
        inputs=clue_id,
        outputs=clue_action_status
    )

    # 初始化
    demo.load(
        fn=refresh_novel_list_chapter,
        outputs=novel_list_chapter
    )

if __name__ == "__main__":
    demo.launch(theme=gradio_settings.theme, share=True)
