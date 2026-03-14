import gradio as gr
from settings import GradioSettings, DatabaseSettings, ChapterSettings, OutlineSettings, ClueSettings, OutlineGenerationSettings
from database import init_db, add_novel, get_all_novels, get_novel_by_id, update_novel, delete_novel, get_novel_chapters, get_next_chapter_number, get_chapter_by_id, update_chapter, delete_chapter, add_clue, get_novel_clues, update_clue_next_chapter, delete_clue
from generator import generate_outline, extract_title, generate_chapter, extract_clues_from_chapter

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
                    chapter_interval = gr.Number(
                        label="章节间隔",
                        value=outline_settings.default_chapter_interval,
                        minimum=outline_settings.min_chapter_interval,
                        maximum=outline_settings.max_chapter_interval,
                        step=1
                    )
                    recursion_depth = gr.Number(
                        label="递归深度",
                        value=outline_gen_settings.default_recursion_depth,
                        minimum=outline_gen_settings.min_recursion_depth,
                        maximum=outline_gen_settings.max_recursion_depth,
                        step=1
                    )
                    temperature = gr.Slider(
                        label="温度",
                        minimum=0.1,
                        maximum=1.0,
                        value=0.7,
                        step=0.1
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
            # 选择小说（与管理小说一致）
            novel_list_chapter = gr.Dataframe(
                label="小说列表",
                headers=["ID", "标题", "提示词", "创建时间"],
                datatype=["number", "str", "str", "str"],
                interactive=False
            )
            refresh_novels_btn = gr.Button("刷新小说列表")
            # 显示当前选择的小说ID
            selected_novel_id = gr.Number(label="当前选择的小说ID", interactive=False)
            
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
                    # 批量编写控件
                    batch_chapter_count = gr.Number(
                        label="批量编写章节数",
                        value=1,
                        minimum=1,
                        step=1
                    )
                    auto_add_clue = gr.Checkbox(
                        label="自动添加线索",
                        value=False
                    )
                    clue_count = gr.Number(
                        label="每章线索数量",
                        value=2,
                        minimum=1,
                        maximum=10,
                        step=1
                    )
                    batch_generate_btn = gr.Button("批量生成章节")
                
                with gr.Column():
                    chapter_content = gr.Textbox(
                        label="章节内容",
                        lines=20
                    )
                    chapter_status = gr.Textbox(label="生成状态", interactive=False)
                    show_clue_dialog = gr.State(False)  # 用于控制线索对话框的显示
                    batch_status = gr.Textbox(label="批量生成状态", interactive=False)
            
            # 章节列表
            chapter_list = gr.Dataframe(
                label="章节列表",
                headers=["ID", "章节编号", "章节标题", "创建时间"],
                datatype=["number", "number", "str", "str"],
                interactive=False,
                row_count="dynamic"
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
            
            # 生成章节后询问是否添加线索的对话框
            with gr.Blocks(visible=False) as clue_dialog:
                gr.Markdown("章节生成成功！是否要为该章节添加线索？")
                with gr.Row():
                    yes_btn = gr.Button("是")
                    no_btn = gr.Button("否")
    
    # 绑定生成函数
    generate_btn.click(
        fn=generate_outline,
        inputs=[prompt_input, chapter_count, chapter_word_count, chapter_interval, recursion_depth, temperature],
        outputs=outline_output,
        api_name="generate_outline"
    )
    
    # 绑定保存函数
    def save_novel_to_db(outline):
        if not outline:
            return "大纲不能为空"
        title = extract_title(outline)
        # 确保提示词不为空
        prompt = prompt_input.value if prompt_input.value else f"{title}的小说"
        return add_novel(title, prompt, outline)
    
    save_btn.click(
        fn=save_novel_to_db,
        inputs=outline_output,
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
    
    # 生成章节
    generate_chapter_btn.click(
        fn=generate_chapter,
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
