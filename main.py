import gradio as gr
from settings import GradioSettings, DatabaseSettings, ChapterSettings, OutlineSettings, ClueSettings, OutlineGenerationSettings, CompressionGenerationSettings
from database import init_db, add_novel, get_all_novels, get_novel_by_id, update_novel, delete_novel, get_novel_chapters, get_next_chapter_number, get_chapter_by_id, update_chapter, delete_chapter, add_chapter, add_clue, get_novel_clues, update_clue_next_chapter, delete_clue, record_usage, get_statistics_summary, get_total_tokens, get_total_generations, get_chapter_by_number
from generator import generate_outline_streaming, extract_title, generate_chapter, generate_chapter_streaming, extract_clues_from_chapter, generate_chapter_with_compression, batch_generate_chapters_with_compression
from agent_system import Coordinator
from exporter import export_novel, NovelExporter

# 初始化多 Agent 协作系统
agent_coordinator = Coordinator()

# 加载设置
gradio_settings = GradioSettings()
db_settings = DatabaseSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
clue_settings = ClueSettings()
outline_gen_settings = OutlineGenerationSettings()
compression_settings = CompressionGenerationSettings()
chapter_settings = ChapterSettings()

# 初始化数据库
init_db()

# 批量生成章节的函数
def batch_generate_chapters(novel_id, start_chapter, batch_count, word_count, temperature, clue_threshold, auto_add_clue, error_handling="❌ 停止生成", clue_count=2, additional_prompt="", retry_count=3, use_agent_mode=False, agent_target_audience="普通读者", agent_content_style="传统叙事", agent_max_tokens=8000, generate_next_chapter_guidance=False, previous_chapter_count=1):
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    print(f"错误处理方式：{error_handling}")
    print(f"批量生成参数：起始章节={start_chapter}, 数量={batch_count}, 重试次数={retry_count}")
    print(f"使用 Agent 模式：{use_agent_mode}")
    print(f"传入历史章节数：{previous_chapter_count}")
    print(f"Agent Max Tokens：{agent_max_tokens}")
    if additional_prompt:
        print(f"附加提示词：{additional_prompt}")
    
    if not novel_id:
        return "无效的小说 ID"
    
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
    failed_chapters = []
    skipped_chapters = []
    retry_attempts = retry_count  # 使用用户设置的重试次数
    
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
            if error_handling == "⏭️ 跳过错误章节":
                print(f"章节 {current_chapter} 已存在，跳过...")
                skipped_chapters.append(current_chapter)
                continue
            else:
                return f"章节 {current_chapter} 已经存在，请修改起始章节编号"
        
        # 生成章节
        success = False
        chapter_content = ""
        
        for attempt in range(retry_attempts):
            print(f"第{attempt + 1}次尝试生成第{current_chapter}章...")
            
            # 根据是否启用 agent 模式选择不同的生成函数
            if use_agent_mode:
                # Agent 模式
                try:
                    # 获取小说信息（读取总纲）
                    novel = get_novel_by_id(int(novel_id))
                    if not novel:
                        print(f"小说不存在")
                        break
                    
                    novel_title, novel_outline_full = novel[0], novel[2]
                    
                    # 获取历史章节内容和指导文字
                    previous_chapters = []
                    previous_chapter_guidance = None
                    if current_chapter > 1:
                        start_chapter_num = max(1, current_chapter - previous_chapter_count)
                        chapters = get_novel_chapters(novel_id)
                        for ch in chapters:
                            if start_chapter_num <= ch[1] < current_chapter:
                                previous_chapters.append({
                                    'chapter_number': ch[1],
                                    'content': ch[3],
                                    'guidance': ch[4]
                                })
                        
                        if previous_chapters:
                            previous_chapter_guidance = previous_chapters[-1]['guidance']
                    

                    
                    # 调用多 Agent 系统
                    result = agent_coordinator.generate_chapter(
                        chapter_number=int(current_chapter),
                        chapter_theme=f"第{current_chapter}章",
                        novel_outline=novel_outline_full,
                        active_clues=None,
                        previous_chapters=previous_chapters,
                        previous_chapter_guidance=previous_chapter_guidance,
                        target_audience=agent_target_audience,
                        content_style=agent_content_style,
                        target_word_count=int(word_count),
                        temperature=float(temperature),
                        generate_next_chapter_guidance=generate_next_chapter_guidance,
                        max_tokens=int(agent_max_tokens)
                    )
                    
                    if result.get('success'):
                        chapter_content_data = result.get('chapter_content', {})
                        chapter_title = chapter_content_data.get('chapter_title', f'第{current_chapter}章')
                        chapter_content = chapter_content_data.get('polished_content', chapter_content_data.get('chapter_content', ''))
                        
                        # 格式化章节内容（添加标题和线索标记）
                        formatted_content = f"{chapter_title}\n0\n{chapter_content}"
                        
                        # 保存章节到数据库
                        try:
                            next_chapter_guidance = result.get('next_chapter_guidance')
                            add_chapter(novel_id, current_chapter, chapter_title, formatted_content, next_chapter_guidance)
                            chapter_content = formatted_content
                            success = True
                            print(f"第{current_chapter}章（Agent 模式）已保存")
                            print(f"[调试] 格式化后章节内容长度：{len(formatted_content)}字")
                            break
                        except Exception as save_error:
                            print(f"保存第{current_chapter}章失败：{save_error}")
                    else:
                        print(f"第{attempt + 1}次 Agent 生成失败：{result.get('error', '未知错误')}")
                        
                except Exception as e:
                    print(f"第{attempt + 1}次 Agent 生成出错：{str(e)}")
            else:
                # 普通模式
                result = generate_chapter(novel_id, current_chapter, word_count, temperature, clue_threshold, additional_prompt=additional_prompt, generate_next_chapter_guidance=generate_next_chapter_guidance, previous_chapter_count=previous_chapter_count)
                
                if isinstance(result, tuple):
                    chapter_content, _ = result
                    # 验证章节内容是否有效
                    if chapter_content and len(chapter_content.strip()) > 50:
                        success = True
                        break
                    else:
                        print(f"第{attempt + 1}次生成的内容无效，内容长度：{len(chapter_content.strip())}")
                else:
                    print(f"第{attempt + 1}次生成失败：{result}")
            
            if attempt < retry_attempts - 1:
                print(f"等待重试...")
                import time
                time.sleep(1)  # 等待 1 秒后重试
        
        if success:
            # 章节已由 generate_chapter 函数保存，无需重复保存
            generated_chapters.append(current_chapter)
            print(f"第{current_chapter}章生成并保存成功")
            
            # 自动添加线索
            if auto_add_clue:
                print(f"正在为第{current_chapter}章添加线索...")
                print(f"[调试] auto_add_clue=True，开始提取线索")
                print(f"[调试] chapter_content长度：{len(chapter_content) if chapter_content else 0}字")
                print(f"[调试] novel_outline长度：{len(novel_outline) if novel_outline else 0}字")
                print(f"[调试] total_chapters：{total_chapters}")
                print(f"[调试] clue_count：{clue_count}")
                extracted_clues = extract_clues_from_chapter(chapter_content, current_chapter, novel_outline, total_chapters, clue_count)
                print(f"[调试] 提取到线索数量：{len(extracted_clues) if extracted_clues else 0}")
                if extracted_clues:
                    for clue_text, clue_type, first_chapter, next_chapter in extracted_clues:
                        print(f"[调试] 添加线索：类型={clue_type}, 内容={clue_text[:50]}..., 首次出现章节={first_chapter}, 下次出现章节={next_chapter}")
                        add_clue(novel_id, clue_text, clue_type, first_chapter, next_chapter)
                    print(f"成功添加 {len(extracted_clues)} 条线索")
                else:
                    print("警告：未能提取到任何线索")
                print("线索添加完成")
                
        else:
            print(f"第{current_chapter}章生成失败")
            failed_chapters.append(current_chapter)
            
            # 根据错误处理方式决定下一步
            if error_handling == "❌ 停止生成":
                return f"生成第{current_chapter}章失败，已停止批量生成"
            elif error_handling == "💾 保存上一章内容":
                # 尝试获取上一章内容并保存
                if i > 0 and generated_chapters:
                    previous_chapter = generated_chapters[-1]
                    try:
                        conn = sqlite3.connect(db_settings.db_path)
                        cursor = conn.cursor()
                        cursor.execute(f"""
                        SELECT content FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
                        """, (novel_id, previous_chapter))
                        previous_content = cursor.fetchone()
                        
                        if previous_content:
                            # 从内容中提取第一行作为标题
                            prev_title = previous_content[0].split('\n')[0].strip() if previous_content[0] else f"第{current_chapter}章"
                            cursor.execute(f"""
                            INSERT INTO {db_settings.chapter_table} (novel_id, chapter_number, chapter_title, content, created_at)
                            VALUES (?, ?, ?, ?, datetime('now'))
                            """, (novel_id, current_chapter, prev_title, previous_content[0]))
                            conn.commit()
                            print(f"第{current_chapter}章保存为上一章内容")
                            generated_chapters.append(current_chapter)
                        
                        conn.close()
                    except Exception as e:
                        print(f"保存上一章内容失败：{e}")
    
    # 构建返回信息
    result_parts = []
    if generated_chapters:
        result_parts.append(f"成功生成章节：{', '.join([f'第{ch}章' for ch in generated_chapters])}")
    if failed_chapters:
        result_parts.append(f"失败章节：{', '.join([f'第{ch}章' for ch in failed_chapters])}")
    if skipped_chapters:
        result_parts.append(f"跳过章节：{', '.join([f'第{ch}章' for ch in skipped_chapters])}")
    
    if result_parts:
        return "\n".join(result_parts)
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
                            label=" 情节节点数",
                            value=5,
                            minimum=3,
                            maximum=50,
                            step=1,
                            info="将大纲分为几个主要情节节点（例如：5 个节点）"
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
                    
                    generate_btn = gr.Button("🚀 生成大纲", variant="primary", size="lg", scale=1)
                
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
            novel_list_dropdown = gr.Dropdown(
                label="📖 选择小说",
                choices=[],
                interactive=True,
                info="从下拉列表中选择要管理的小说"
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
                    novel_total_chapters = gr.Number(
                        label="📊 总章节数",
                        value=5,
                        minimum=1,
                        maximum=10000,
                        step=1,
                        info="修改小说的总章节数"
                    )
                
                with gr.Column(scale=1):
                    update_btn = gr.Button("✏️ 更新小说", variant="primary")
                    delete_btn = gr.Button("🗑️ 删除小说", variant="stop")
                    action_status = gr.Textbox(label="操作状态", interactive=False)
        
        # ========== 章节管理标签页 ==========
        with gr.Tab("📖 章节管理", id=3):
            # 选择小说区域
            gr.Markdown("### 📚 选择小说")
            with gr.Row():
                with gr.Column(scale=3):
                    novel_list_dropdown_chapter = gr.Dropdown(
                        label="📖 选择小说",
                        choices=[],
                        interactive=True,
                        info="从下拉列表中选择要管理章节的小说"
                    )
                with gr.Column(scale=1):
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
                        previous_chapter_count = gr.Number(
                            label="📚 传入历史章节数",
                            value=1,
                            minimum=1,
                            maximum=50,
                            step=1,
                            info="生成新章节时，传入前面多少章的内容作为上下文（1表示仅传入上一章）"
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
                        additional_prompt = gr.Textbox(
                            label="💡 附加提示词",
                            placeholder="可选：为章节生成添加额外的要求或说明（如：增加对话、描写细节等）",
                            lines=3,
                            value=chapter_settings.default_additional_prompt
                        )
                    
                    with gr.Group():
                        gr.Markdown("**⚡ 批量生成**")
                        with gr.Row():
                            batch_chapter_count = gr.Number(
                                label="📦 每次生成章节数",
                                value=5,
                                minimum=1,
                                maximum=50,
                                step=1,
                                info="每次从大纲中读取并生成多少章"
                            )
                            auto_add_clue = gr.Checkbox(
                                label="✅ 自动添加线索",
                                value=False
                            )
                        with gr.Row():
                            clue_count = gr.Number(
                                label="🎯 每章线索数量",
                                value=2,
                                minimum=1,
                                maximum=10,
                                step=1
                            )
                            retry_count = gr.Number(
                                label="🔄 失败重试次数",
                                value=chapter_settings.default_retry_count,
                                minimum=chapter_settings.min_retry_count,
                                maximum=chapter_settings.max_retry_count,
                                step=1,
                                info="生成失败时自动重试的最大次数"
                            )
                        error_handling = gr.Radio(
                            label="🛡️ 错误处理方式",
                            choices=["❌ 停止生成", "⏭️ 跳过错误章节", "💾 保存上一章内容"],
                            value="❌ 停止生成",
                            info="当章节生成失败时的处理方式"
                        )
                    
                    # 多 Agent 模式选项
                    with gr.Accordion("🤖 多 Agent 协作模式", open=False):
                        gr.Markdown("使用多 Agent 协作系统生成章节，包含规划、撰写、润色、审核四个环节")
                        use_agent_mode = gr.Checkbox(
                            label="✅ 启用多 Agent 协作模式",
                            value=False,
                            info="启用后将使用多 Agent 系统，基于总纲自动生成（速度较慢但质量更高）"
                        )
                        agent_target_audience = gr.Dropdown(
                            label="👥 目标读者",
                            choices=["普通读者", "青少年", "成年人", "专业读者"],
                            value="普通读者",
                            visible=False
                        )
                        agent_content_style = gr.Dropdown(
                            label="🎨 内容风格",
                            choices=["传统叙事", "轻松幽默", "悬疑紧张", "温馨治愈", "史诗宏大"],
                            value="传统叙事",
                            visible=False
                        )
                        agent_max_tokens = gr.Number(
                            label="📏 最大 Token 数",
                            value=8000,
                            minimum=2000,
                            maximum=32000,
                            step=1000,
                            visible=False,
                            info="润色和审核阶段的最大 Token 数（字数多时需调大此值，避免响应被截断）"
                        )
                        generate_next_chapter_guidance = gr.Checkbox(
                            label="📝 生成下一章指导文字",
                            value=False,
                            visible=False,
                            info="生成本章后为下一章提供指导建议"
                        )
                    
                    # 多 Agent 模式 UI 控制
                    def on_agent_mode_change(use_agent):
                        return {
                            agent_target_audience: gr.update(visible=use_agent),
                            agent_content_style: gr.update(visible=use_agent),
                            agent_max_tokens: gr.update(visible=use_agent),
                            generate_next_chapter_guidance: gr.update(visible=use_agent)
                        }
                    
                    use_agent_mode.change(
                        fn=on_agent_mode_change,
                        inputs=use_agent_mode,
                        outputs=[agent_target_audience, agent_content_style, agent_max_tokens, generate_next_chapter_guidance]
                    )
                    
                    with gr.Row():
                        generate_chapter_btn = gr.Button("🚀 生成单章", variant="primary", size="lg")
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
            with gr.Row():
                with gr.Column(scale=3):
                    chapter_list_dropdown = gr.Dropdown(
                        label="📖 选择章节",
                        choices=[],
                        interactive=True,
                        info="从下拉列表中选择要管理的章节"
                    )
                with gr.Column(scale=1):
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
                        clue_next_chapter = gr.Number(
                            label="🔁 回收章节",
                            value=None,
                            minimum=1,
                            step=1,
                            info="该线索预计下次出现的章节（可选，留空表示未设定）"
                        )
                        add_clue_btn = gr.Button("➕ 添加线索", variant="primary")
                        clue_status = gr.Textbox(label="操作状态", interactive=False)
                    
                    with gr.Column(scale=2):
                        gr.Markdown("**📋 线索列表**")
                        with gr.Row():
                            with gr.Column(scale=3):
                                clue_list_dropdown = gr.Dropdown(
                                    label="📖 选择线索",
                                    choices=[],
                                    interactive=True,
                                    info="从下拉列表中选择要管理的线索"
                                )
                            with gr.Column(scale=1):
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
                        clue_next_chapter_edit = gr.Number(
                            label="🔁 回收章节",
                            value=None,
                            minimum=1,
                            step=1,
                            info="该线索预计下次出现的章节（可选，留空表示未设定）"
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
        
        # ========== 压缩生成章节标签页 ==========
        with gr.Tab("🔄 压缩生成", id=4):
            gr.Markdown("### 📦 基于上下文压缩的章节生成")
            gr.Markdown("""
            **功能说明**：
            - 当章节数超过设定阈值时，自动对前文进行压缩摘要
            - 保留最近若干章的详细内容用于上下文
            - 适用于长篇小说的连续生成，避免上下文过长
            
            **工作原理**：
            1. 检查已有章节数是否超过压缩阈值
            2. 如果超过，将旧章节压缩为摘要，保留最近 N 章的详细内容
            3. 使用压缩后的上下文生成新章节
            """)
            
            # 选择小说区域
            gr.Markdown("### 📚 选择小说")
            with gr.Row():
                with gr.Column(scale=3):
                    novel_list_dropdown_compression = gr.Dropdown(
                        label="📖 选择小说",
                        choices=[],
                        interactive=True,
                        info="从下拉列表中选择要生成章节的小说"
                    )
                with gr.Column(scale=1):
                    refresh_novels_compression_btn = gr.Button("🔄 刷新小说列表", variant="secondary")
            
            selected_novel_id_compression = gr.Number(
                label="📌 当前选择的小说 ID", 
                interactive=False
            )
            
            # 压缩生成参数设置
            gr.Markdown("### ⚙️ 压缩生成设置")
            with gr.Row():
                with gr.Column(scale=1):
                    with gr.Group():
                        gr.Markdown("**📝 基本设置**")
                        compression_chapter_number = gr.Number(
                            label="🔢 起始章节编号",
                            value=1,
                            minimum=1,
                            step=1,
                            info="从第几章开始生成"
                        )
                        compression_word_count = gr.Slider(
                            label="📏 每章字数",
                            minimum=500,
                            maximum=chapter_settings.max_word_count,
                            value=chapter_settings.default_word_count,
                            step=100
                        )
                        compression_temperature = gr.Slider(
                            label="🎲 温度",
                            minimum=chapter_settings.min_temperature,
                            maximum=chapter_settings.max_temperature,
                            value=chapter_settings.default_temperature,
                            step=0.1,
                            interactive=True
                        )
                    
                    with gr.Group():
                        gr.Markdown("**🗜️ 压缩设置**")
                        compression_threshold = gr.Number(
                            label="⚠️ 压缩阈值",
                            value=compression_settings.default_compression_threshold,
                            minimum=compression_settings.min_compression_threshold,
                            maximum=compression_settings.max_compression_threshold,
                            step=1,
                            info="超过多少章后开始压缩前文"
                        )
                        keep_recent_chapters = gr.Number(
                            label="📌 保留章节数",
                            value=compression_settings.default_keep_recent_chapters,
                            minimum=compression_settings.min_keep_recent_chapters,
                            maximum=compression_settings.max_keep_recent_chapters,
                            step=1,
                            info="保留最近多少章的详细内容"
                        )
                    
                    with gr.Group():
                        gr.Markdown("**⚡ 批量设置**")
                        compression_batch_count = gr.Number(
                            label="📦 批量生成数量",
                            value=compression_settings.default_batch_size,
                            minimum=compression_settings.min_batch_size,
                            maximum=compression_settings.max_batch_size,
                            step=1,
                            info="每次生成多少章"
                        )
                        compression_retry_count = gr.Number(
                            label="🔄 失败重试次数",
                            value=chapter_settings.default_retry_count,
                            minimum=chapter_settings.min_retry_count,
                            maximum=chapter_settings.max_retry_count,
                            step=1,
                            info="生成失败时自动重试的最大次数"
                        )
                        compression_error_handling = gr.Radio(
                            label="🛡️ 错误处理方式",
                            choices=["❌ 停止生成", "⏭️ 跳过错误章节", "💾 保存上一章内容"],
                            value="❌ 停止生成",
                            info="当章节生成失败时的处理方式"
                        )
                    
                    with gr.Row():
                        generate_single_compression_btn = gr.Button(
                            "🚀 生成单章", 
                            variant="primary", 
                            size="lg"
                        )
                        batch_generate_compression_btn = gr.Button(
                            "📦 批量生成", 
                            variant="secondary", 
                            size="lg"
                        )
                
                with gr.Column(scale=2):
                    compression_chapter_content = gr.Textbox(
                        label="📄 章节内容",
                        lines=25,
                        placeholder="生成的章节内容将在这里显示..."
                    )
                    compression_status = gr.Textbox(
                        label="生成状态", 
                        interactive=False
                    )
                    compression_batch_status = gr.Textbox(
                        label="批量生成状态", 
                        interactive=False
                    )
            
            # 章节列表区域
            gr.Markdown("### 📋 章节列表")
            with gr.Row():
                with gr.Column(scale=3):
                    chapter_list_dropdown_compression = gr.Dropdown(
                        label="📖 选择章节",
                        choices=[],
                        interactive=True,
                        info="从下拉列表中选择要管理的章节"
                    )
                with gr.Column(scale=1):
                    refresh_chapters_compression_btn = gr.Button(
                        "🔄 刷新章节列表", 
                        variant="secondary"
                    )
            
            # 章节详情区域
            gr.Markdown("### 📝 章节详情")
            with gr.Row():
                with gr.Column(scale=2):
                    compression_chapter_id = gr.Number(
                        label="🆔 章节 ID", 
                        interactive=False
                    )
                    compression_chapter_num = gr.Number(
                        label="🔢 章节编号", 
                        minimum=1, 
                        step=1
                    )
                    compression_chapter_title = gr.Textbox(
                        label="📚 章节标题"
                    )
                    compression_chapter_text = gr.Textbox(
                        label="📄 章节内容", 
                        lines=10
                    )
                
                with gr.Column(scale=1):
                    load_chapter_compression_btn = gr.Button(
                        "📥 加载章节", 
                        variant="secondary"
                    )
                    update_chapter_compression_btn = gr.Button(
                        "✏️ 更新章节", 
                        variant="primary"
                    )
                    delete_chapter_compression_btn = gr.Button(
                        "🗑️ 删除章节", 
                        variant="stop"
                    )
                    chapter_action_status_compression = gr.Textbox(
                        label="操作状态", 
                        interactive=False
                    )
        
        # ========== 导出小说标签页 ==========
        with gr.Tab("📤 导出小说", id=5):
            gr.Markdown("### 📤 导出小说为多种格式")
            gr.Markdown("""
            **支持的格式**：
            - 📄 TXT - 纯文本格式，适合阅读和打印
            - 📝 Markdown - 支持目录链接，适合网络分享
            - 🌐 HTML - 网页格式，支持样式和响应式设计
            
            **导出选项**：
            - 包含大纲：将小说大纲一起导出
            - 包含线索：将线索列表一起导出
            - 排版样式：选择不同的章节标题样式
            """)
            
            # 选择小说区域
            gr.Markdown("### 📚 选择小说")
            with gr.Row():
                with gr.Column(scale=3):
                    novel_list_dropdown_export = gr.Dropdown(
                        label="📖 选择小说",
                        choices=[],
                        interactive=True,
                        info="从下拉列表中选择要导出的小说"
                    )
                with gr.Column(scale=1):
                    refresh_novels_export_btn = gr.Button("🔄 刷新小说列表", variant="secondary")
            
            selected_novel_id_export = gr.Number(
                label="📌 当前选择的小说 ID", 
                interactive=False
            )
            
            # 导出设置
            gr.Markdown("### ⚙️ 导出设置")
            with gr.Row():
                with gr.Column(scale=1):
                    export_format = gr.Radio(
                        label="📄 导出格式",
                        choices=[
                            ("📄 TXT 文本", "txt"),
                            ("📝 Markdown", "md"),
                            ("🌐 HTML 网页", "html")
                        ],
                        value="txt",
                        info="选择要导出的文件格式"
                    )
                    
                    export_include_outline = gr.Checkbox(
                        label="📋 包含大纲",
                        value=True,
                        info="是否将小说大纲一起导出"
                    )
                    
                    export_include_clues = gr.Checkbox(
                        label="🔍 包含线索",
                        value=False,
                        info="是否将线索列表一起导出"
                    )
                    
                    gr.Markdown("**📖 排版选项**")
                    export_chapter_format = gr.Radio(
                        label="章节标题样式",
                        choices=[
                            ("标准", "standard"),
                            ("简洁", "simple"),
                            ("详细", "detailed")
                        ],
                        value="standard",
                        visible=False,
                        info="仅对 TXT 格式有效"
                    )
                    
                    export_add_page_numbers = gr.Checkbox(
                        label="📄 添加页码",
                        value=False,
                        visible=False,
                        info="仅对 TXT 格式有效"
                    )
                    
                    export_use_css = gr.Checkbox(
                        label="🎨 使用 CSS 样式",
                        value=True,
                        visible=False,
                        info="仅对 HTML 格式有效"
                    )
                    
                    export_responsive = gr.Checkbox(
                        label="📱 响应式设计",
                        value=True,
                        visible=False,
                        info="仅对 HTML 格式有效"
                    )
                    
                    export_add_toc = gr.Checkbox(
                        label="📑 添加目录",
                        value=True,
                        visible=False,
                        info="仅对 Markdown 格式有效"
                    )
                    
                    export_use_headings = gr.Checkbox(
                        label="📝 使用标题样式",
                        value=True,
                        visible=False,
                        info="仅对 Markdown 格式有效"
                    )
                    
                    export_btn = gr.Button("📤 导出小说", variant="primary", size="lg")
                
                with gr.Column(scale=2):
                    export_status = gr.Textbox(
                        label="导出状态",
                        interactive=False,
                        lines=3
                    )
                    
                    export_preview = gr.Textbox(
                        label="📋 导出信息预览",
                        interactive=False,
                        lines=15,
                        placeholder="导出信息将在这里显示..."
                    )
            
            # 格式选择变化时显示对应选项
            def on_export_format_change(format_val):
                return {
                    export_chapter_format: gr.update(visible=(format_val == "txt")),
                    export_add_page_numbers: gr.update(visible=(format_val == "txt")),
                    export_use_css: gr.update(visible=(format_val == "html")),
                    export_responsive: gr.update(visible=(format_val == "html")),
                    export_add_toc: gr.update(visible=(format_val == "md")),
                    export_use_headings: gr.update(visible=(format_val == "md"))
                }
            
            export_format.change(
                fn=on_export_format_change,
                inputs=export_format,
                outputs=[export_chapter_format, export_add_page_numbers, 
                        export_use_css, export_responsive,
                        export_add_toc, export_use_headings]
            )
        
        # ========== 使用统计标签页 ==========
        with gr.Tab("📊 使用统计", id=6):
            gr.Markdown("### 📈 使用情况统计")
            gr.Markdown("查看 Token 使用量、生成次数、小说数量等统计信息")
            
            # 刷新统计按钮
            refresh_stats_btn = gr.Button("🔄 刷新统计数据", variant="primary", size="lg")
            
            # 总体统计卡片
            gr.Markdown("### 📌 总体统计")
            with gr.Row():
                with gr.Column(scale=1):
                    stat_total_novels = gr.Number(
                        label="📚 小说总数",
                        value=0,
                        interactive=False,
                        info="已创建的小说数量"
                    )
                with gr.Column(scale=1):
                    stat_total_chapters = gr.Number(
                        label="📖 章节总数",
                        value=0,
                        interactive=False,
                        info="已生成的章节数量"
                    )
                with gr.Column(scale=1):
                    stat_total_tokens = gr.Number(
                        label="💰 Token 使用量",
                        value=0,
                        interactive=False,
                        info="累计消耗的 Token 数量"
                    )
                with gr.Column(scale=1):
                    stat_total_words = gr.Number(
                        label="✍️ 总字数",
                        value=0,
                        interactive=False,
                        info="已生成的总字数"
                    )
            
            with gr.Row():
                with gr.Column(scale=1):
                    stat_total_generations = gr.Number(
                        label="🚀 生成次数",
                        value=0,
                        interactive=False,
                        info="调用生成 API 的总次数"
                    )
                with gr.Column(scale=1):
                    stat_avg_temperature = gr.Number(
                        label="🎲 平均温度",
                        value=0,
                        interactive=False,
                        info="生成参数的平均温度值",
                        precision=2
                    )
            
            # 按类型统计
            gr.Markdown("### 📊 按类型统计")
            with gr.Row():
                with gr.Column(scale=2):
                    stat_by_type = gr.Dataframe(
                        label="生成类型统计",
                        headers=["类型", "次数", "Token", "字数"],
                        wrap=True
                    )
            
            # 小说排行
            gr.Markdown("### 🏆 小说排行（Top 10）")
            with gr.Row():
                with gr.Column(scale=2):
                    stat_novel_ranking = gr.Dataframe(
                        label="小说使用排行",
                        headers=["小说标题", "生成次数", "Token", "字数"],
                        wrap=True
                    )
            
            # 每日趋势
            gr.Markdown("### 📉 每日趋势（最近 30 天）")
            with gr.Row():
                with gr.Column(scale=2):
                    stat_daily_trend = gr.Dataframe(
                        label="每日使用趋势",
                        headers=["日期", "事件数", "Token", "字数"],
                        wrap=True
                    )
    
    # 绑定生成函数（流式输出）
    def generate_and_store(prompt, chapter_count, chapter_word_count, plot_node_count, temperature):
        # 使用流式生成函数，但收集最终结果用于保存
        full_outline = ""
        for output in generate_outline_streaming(prompt, chapter_count, chapter_word_count, plot_node_count, temperature):
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
        inputs=[prompt_input, chapter_count, chapter_word_count, chapter_interval, temperature],
        outputs=[outline_output, generated_outline_state],
        api_name="generate_outline"
    )
    
    # 绑定保存函数
    def save_novel_to_db(clean_outline, chapter_count_input, chapter_word_count_input):
        if not clean_outline:
            return "大纲不能为空"
        title = extract_title(clean_outline)
        # 确保提示词不为空
        prompt = prompt_input.value if prompt_input.value else f"{title}的小说"
        # 获取章节数和每章字数
        total_chapters_val = int(chapter_count_input) if chapter_count_input else None
        chapter_word_count_val = int(chapter_word_count_input) if chapter_word_count_input else None
        result = add_novel(title, prompt, clean_outline, total_chapters_val, chapter_word_count_val)
        
        # 记录使用统计
        try:
            # 估算 token 数量（中文字符约 1.5 个 token 一个）
            token_count = int(len(clean_outline) * 1.5)
            record_usage(
                event_type="generate_outline",
                token_count=token_count,
                word_count=len(clean_outline),
                temperature=temperature.value
            )
        except Exception as e:
            print(f"记录使用统计失败：{e}")
        

        
        return result
    
    save_btn.click(
        fn=save_novel_to_db,
        inputs=[generated_outline_state, chapter_count, chapter_word_count],
        outputs=save_status
    )
    
    # 绑定刷新小说列表函数
    def refresh_novel_list():
        novels = get_all_novels()
        # 转换为 dropdown 的 choices 格式：[(label, value), ...]
        choices = [(f"{novel[0]} - {novel[1]}", novel[0]) for novel in novels]
        return gr.update(choices=choices)
    
    refresh_btn.click(
        fn=refresh_novel_list,
        outputs=novel_list_dropdown
    )
    
    # 绑定加载小说函数
    def load_novel(novel_id):
        if not novel_id:
            return [0, "", "", "", 5]
        novel = get_novel_by_id(novel_id)
        if novel:
            # novel: (id, title, prompt, outline, total_chapters, chapter_word_count)
            return [novel[0], novel[1], novel[2], novel[3], novel[4] if novel[4] else 5]
        return [0, "", "", "", 5]
    
    novel_list_dropdown.change(
        fn=load_novel,
        inputs=novel_list_dropdown,
        outputs=[novel_id, novel_title, novel_prompt, novel_outline, novel_total_chapters]
    )
    
    # 绑定更新小说函数
    update_btn.click(
        fn=update_novel,
        inputs=[novel_id, novel_title, novel_prompt, novel_outline, novel_total_chapters],
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
        # 转换为 dropdown 的 choices 格式：[(label, value), ...]
        choices = [(f"{novel[0]} - {novel[1]}", novel[0]) for novel in novels]
        return gr.update(choices=choices)
    
    refresh_novels_btn.click(
        fn=refresh_novel_list_chapter,
        outputs=novel_list_dropdown_chapter
    )
    
    # 绑定选择小说函数
    def select_novel_chapter(novel_id):
        print(f"选择的小说 ID: {novel_id}")
        if not novel_id:
            return 0
        return int(novel_id)
    
    novel_list_dropdown_chapter.change(
        fn=select_novel_chapter,
        inputs=novel_list_dropdown_chapter,
        outputs=selected_novel_id
    )
    
    # 当选择小说时，自动填写下一个章节数和每章字数
    def update_chapter_settings(novel_id):
        if not novel_id:
            return 1, chapter_settings.default_word_count
        
        # 获取小说信息
        novel = get_novel_by_id(novel_id)
        if novel and novel[5]:  # novel[5] is chapter_word_count
            # 有存储的每章字数，使用它
            return get_next_chapter_number(novel_id), novel[5]
        else:
            # 没有存储的每章字数，使用默认值
            return get_next_chapter_number(novel_id), chapter_settings.default_word_count
    
    # 绑定小说选择变化事件
    selected_novel_id.change(
        fn=update_chapter_settings,
        inputs=selected_novel_id,
        outputs=[chapter_number, word_count]
    )
    
    # 生成章节（流式输出）
    def generate_chapter_wrapper(novel_id, chapter_num, word_count, temperature, clue_threshold, 
                                use_agent_mode=False, agent_target_audience="普通读者", 
                                agent_content_style="传统叙事", agent_max_tokens=8000, additional_prompt="", retry_count=3, 
                                generate_next_chapter_guidance=False, previous_chapter_count=1):
        """章节生成包装函数，支持普通模式和多 Agent 模式"""
        
        # 多 Agent 模式
        if use_agent_mode:
            try:
                # 获取小说信息（读取总纲）
                novel = get_novel_by_id(int(novel_id))
                if not novel:
                    yield "小说不存在", False
                    return
                
                # novel结构: (id, title, prompt, outline, total_chapters, chapter_word_count)
                novel_title = novel[1]
                novel_outline = novel[3]  # outline在第4个位置（索引3）
                
                # 调试日志
                print(f"\n[调试] 小说标题: {novel_title}")
                print(f"[调试] 小说总纲长度: {len(novel_outline) if novel_outline else 0}字")
                print(f"[调试] 小说总纲预览: {(novel_outline or '空')[:200]}...")
                print(f"[调试] 传入历史章节数: {previous_chapter_count}")
                
                # 获取历史章节内容和指导文字
                previous_chapters = []
                previous_chapter_guidance = None
                if chapter_num > 1:
                    start_chapter = max(1, chapter_num - previous_chapter_count)
                    for ch_num in range(start_chapter, chapter_num):
                        prev_chapter_data = get_chapter_by_number(int(novel_id), ch_num)
                        if prev_chapter_data:
                            # prev_chapter_data: (id, chapter_number, chapter_title, content, next_chapter_guidance)
                            previous_chapters.append({
                                'chapter_number': ch_num,
                                'content': prev_chapter_data[3],  # content在第4个位置
                                'guidance': prev_chapter_data[4]  # next_chapter_guidance在第5个位置
                            })
                            print(f"[调试] 第{ch_num}章内容长度: {len(prev_chapter_data[3])}字")
                            if prev_chapter_data[4]:
                                print(f"[调试] 第{ch_num}章指导文字长度: {len(prev_chapter_data[4])}字")
                    
                    # 使用最后一章的指导文字
                    if previous_chapters and previous_chapters[-1]['guidance']:
                        previous_chapter_guidance = previous_chapters[-1]['guidance']
                    else:
                        print(f"[调试] 未找到任何历史章节")
                

                
                # 获取活跃线索
                all_clues = get_novel_clues(int(novel_id))
                active_clues = []
                for clue in all_clues:
                    # clue: (id, text, type, first_chapter, next_chapter)
                    if clue[4] is None or clue[4] >= int(chapter_num):
                        active_clues.append({
                            'text': clue[1],
                            'type': clue[2],
                            'first_chapter': clue[3],
                            'next_chapter': clue[4]
                        })
                
                # 调用多 Agent 系统
                result = agent_coordinator.generate_chapter(
                    chapter_number=int(chapter_num),
                    chapter_theme=f"第{chapter_num}章",
                    novel_outline=novel_outline,
                    active_clues=active_clues,
                    previous_chapters=previous_chapters,
                    previous_chapter_guidance=previous_chapter_guidance,
                    target_audience=agent_target_audience,
                    content_style=agent_content_style,
                    target_word_count=int(word_count),
                    temperature=float(temperature),
                    generate_next_chapter_guidance=generate_next_chapter_guidance,
                    max_tokens=int(agent_max_tokens)
                )
                
                if result.get('success'):
                    chapter_content = result.get('chapter_content', {})
                    review = result.get('review', {})
                    
                    # 提取章节标题和内容
                    chapter_title = chapter_content.get('chapter_title', f'第{chapter_num}章')
                    full_content = chapter_content.get('polished_content', chapter_content.get('chapter_content', ''))
                    
                    # 获取下一章指导文字
                    next_chapter_guidance = result.get('next_chapter_guidance')
                    
                    # 保存到数据库
                    try:
                        existing_chapters = get_novel_chapters(int(novel_id))
                        for ch in existing_chapters:
                            if ch[1] == chapter_num:
                                delete_chapter(ch[0])
                                break
                        
                        # add_chapter 参数：novel_id, chapter_number, chapter_title, content, next_chapter_guidance
                        add_chapter(int(novel_id), chapter_num, chapter_title, full_content, next_chapter_guidance)
                        
                        # 构建输出
                        output = f"✓ 多 Agent 生成成功并保存\n质量评分：{review.get('quality_score', 0)}/100\n审核：{'通过' if review.get('passed') else '未通过'}\n\n{chapter_title}\n\n{full_content}"
                        
                        # 添加下一章指导文字
                        if next_chapter_guidance:
                            output += f"\n\n=== 第{int(chapter_num) + 1}章指导文字 ===\n{next_chapter_guidance}"
                        
                        yield output, True
                    except Exception as save_error:
                        yield f"⚠ 保存失败：{save_error}\n\n{chapter_title}\n\n{full_content}", True
                        
                else:
                    yield f"生成失败：{result.get('error', '未知错误')}", False
                    
            except Exception as e:
                yield f"系统错误：{str(e)}", False
        else:
            # 普通模式 - 使用原有逻辑
            for output in generate_chapter_streaming(novel_id, chapter_num, word_count, temperature, clue_threshold, additional_prompt, retry_count, generate_next_chapter_guidance, previous_chapter_count):
                if isinstance(output, tuple) and len(output) == 2:
                    yield output[0], True
                else:
                    yield output, False
    
    generate_chapter_btn.click(
        fn=generate_chapter_wrapper,
        inputs=[selected_novel_id, chapter_number, word_count, temperature, clue_threshold, 
                use_agent_mode, agent_target_audience, agent_content_style, agent_max_tokens, additional_prompt, retry_count, 
                generate_next_chapter_guidance, previous_chapter_count],
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
        inputs=[selected_novel_id, chapter_number, batch_chapter_count, word_count, temperature, clue_threshold, auto_add_clue, error_handling, clue_count, additional_prompt, retry_count, use_agent_mode, agent_target_audience, agent_content_style, agent_max_tokens, generate_next_chapter_guidance, previous_chapter_count],
        outputs=[batch_status],
        api_name="batch_generate_chapters"
    )
    
    # 刷新章节列表
    def refresh_chapters(novel_id):
        if not novel_id:
            return gr.update(choices=[])
        
        chapters = get_novel_chapters(novel_id)
        # 转换为 dropdown 的 choices 格式：[(label, value), ...]
        choices = [(f"第{chapter[1]}章 - {chapter[2]}", chapter[0]) for chapter in chapters]
        return gr.update(choices=choices)
    
    refresh_chapters_btn.click(
        fn=refresh_chapters,
        inputs=selected_novel_id,
        outputs=chapter_list_dropdown
    )
    
    # 加载章节
    def load_chapter(chapter_id):
        try:
            if not chapter_id:
                return [0, 1, "", ""]
            # 获取章节内容
            chapter = get_chapter_by_id(chapter_id)
            if chapter:
                return [chapter[0], chapter[1], chapter[2], chapter[3]]
            else:
                return [0, 1, "", ""]
        except Exception as e:
            print(f"Error in load_chapter: {e}")
            return [0, 1, "", ""]
    
    chapter_list_dropdown.change(
        fn=load_chapter,
        inputs=chapter_list_dropdown,
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
    def add_new_clue(novel_id, text, clue_type, chapter, next_chapter=None):
        if not novel_id:
            return "请选择小说"
        # 如果 next_chapter 为 0 或空，转换为 None
        if next_chapter is None or next_chapter == 0:
            next_chapter = None
        return add_clue(novel_id, text, clue_type, chapter, next_chapter)
    
    add_clue_btn.click(
        fn=add_new_clue,
        inputs=[selected_novel_id, clue_text, clue_type, clue_chapter, clue_next_chapter],
        outputs=clue_status
    )
    
    # 刷新线索列表
    def refresh_clues(novel_id):
        if not novel_id:
            return gr.update(choices=[])
        clues = get_novel_clues(novel_id)
        # 转换为 dropdown 的 choices 格式：[(label, value), ...]
        choices = [(f"[{clue[2]}] {clue[1][:30]}...", clue[0]) for clue in clues]
        return gr.update(choices=choices)
    
    refresh_clues_btn.click(
        fn=refresh_clues,
        inputs=selected_novel_id,
        outputs=clue_list_dropdown
    )
    
    # 加载线索
    def load_clue(clue_id, novel_id):
        try:
            if not clue_id:
                return [0, "", "明潮", 1, None]
            # 获取线索内容
            clues = get_novel_clues(novel_id)
            for clue in clues:
                if clue[0] == clue_id:
                    # clue: (id, clue_text, clue_type, first_chapter, next_chapter)
                    return [clue_id, clue[1], clue[2], clue[3], clue[4]]
            return [0, "", "明潮", 1, None]
        except Exception as e:
            print(f"Error in load_clue: {e}")
            return [0, "", "明潮", 1, None]
    
    clue_list_dropdown.change(
        fn=load_clue,
        inputs=[clue_list_dropdown, selected_novel_id],
        outputs=[clue_id, clue_text_edit, clue_type_edit, clue_chapter_edit, clue_next_chapter_edit]
    )
    
    # 绑定更新线索函数
    def update_clue(clue_id, text, clue_type, first_chapter, next_chapter):
        if not clue_id:
            return "请选择线索"
        # 如果 next_chapter 为 0 或空，转换为 None
        if next_chapter is None or next_chapter == 0:
            next_chapter = None
        # 更新完整线索信息
        return update_clue(clue_id, text, clue_type, first_chapter, next_chapter)
    
    update_clue_btn.click(
        fn=update_clue,
        inputs=[clue_id, clue_text_edit, clue_type_edit, clue_chapter_edit, clue_next_chapter_edit],
        outputs=clue_action_status
    )
    
    # 删除线索
    delete_clue_btn.click(
        fn=delete_clue,
        inputs=clue_id,
        outputs=clue_action_status
    )

    # ========== 压缩生成相关绑定 ==========
    # 刷新小说列表（压缩生成页面）
    def refresh_novel_list_compression():
        novels = get_all_novels()
        choices = [(f"{novel[0]} - {novel[1]}", novel[0]) for novel in novels]
        return gr.update(choices=choices)
    
    refresh_novels_compression_btn.click(
        fn=refresh_novel_list_compression,
        outputs=novel_list_dropdown_compression
    )
    
    # 绑定选择小说函数（压缩生成页面）
    def select_novel_compression(novel_id):
        print(f"选择的小说 ID: {novel_id}")
        if not novel_id:
            return 0
        return int(novel_id)
    
    novel_list_dropdown_compression.change(
        fn=select_novel_compression,
        inputs=novel_list_dropdown_compression,
        outputs=selected_novel_id_compression
    )
    
    # 当选择小说时，自动填写下一个章节数和每章字数
    def update_chapter_settings_compression(novel_id):
        if not novel_id:
            return 1, chapter_settings.default_word_count
        
        # 获取小说信息
        novel = get_novel_by_id(novel_id)
        if novel and novel[5]:  # novel[5] is chapter_word_count
            # 有存储的每章字数，使用它
            return get_next_chapter_number(novel_id), novel[5]
        else:
            # 没有存储的每章字数，使用默认值
            return get_next_chapter_number(novel_id), chapter_settings.default_word_count
    
    selected_novel_id_compression.change(
        fn=update_chapter_settings_compression,
        inputs=selected_novel_id_compression,
        outputs=[compression_chapter_number, compression_word_count]
    )
    
    # 生成单章（压缩生成）
    def generate_single_chapter_compression(novel_id, chapter_num, word_count, temperature, 
                                           compression_threshold, keep_recent_chapters):
        result = generate_chapter_with_compression(
            novel_id, chapter_num, word_count, temperature,
            compression_threshold, keep_recent_chapters
        )
        
        if isinstance(result, tuple):
            return result[0], "生成成功"
        else:
            return result, "生成失败"
    
    generate_single_compression_btn.click(
        fn=generate_single_chapter_compression,
        inputs=[
            selected_novel_id_compression, 
            compression_chapter_number, 
            compression_word_count, 
            compression_temperature,
            compression_threshold,
            keep_recent_chapters
        ],
        outputs=[compression_chapter_content, compression_status]
    )
    
    # 批量生成（压缩生成）
    def batch_generate_chapters_compression_wrapper(
        novel_id, start_chapter, batch_count, word_count, temperature,
        compression_threshold, keep_recent_chapters, error_handling
    ):
        result = batch_generate_chapters_with_compression(
            novel_id, start_chapter, batch_count, word_count, temperature,
            compression_threshold, keep_recent_chapters, error_handling
        )
        return result
    
    batch_generate_compression_btn.click(
        fn=batch_generate_chapters_compression_wrapper,
        inputs=[
            selected_novel_id_compression,
            compression_chapter_number,
            compression_batch_count,
            compression_word_count,
            compression_temperature,
            compression_threshold,
            keep_recent_chapters,
            compression_error_handling
        ],
        outputs=compression_batch_status
    )
    
    # 刷新章节列表（压缩生成页面）
    def refresh_chapters_compression(novel_id):
        if not novel_id:
            return gr.update(choices=[])
        
        chapters = get_novel_chapters(novel_id)
        choices = [(f"第{chapter[1]}章 - {chapter[2]}", chapter[0]) for chapter in chapters]
        return gr.update(choices=choices)
    
    refresh_chapters_compression_btn.click(
        fn=refresh_chapters_compression,
        inputs=selected_novel_id_compression,
        outputs=chapter_list_dropdown_compression
    )
    
    # 加载章节（压缩生成页面）
    def load_chapter_compression(chapter_id):
        try:
            if not chapter_id:
                return [0, 1, "", ""]
            chapter = get_chapter_by_id(chapter_id)
            if chapter:
                return [chapter[0], chapter[1], chapter[2], chapter[3]]
            else:
                return [0, 1, "", ""]
        except Exception as e:
            print(f"Error in load_chapter_compression: {e}")
            return [0, 1, "", ""]
    
    chapter_list_dropdown_compression.change(
        fn=load_chapter_compression,
        inputs=chapter_list_dropdown_compression,
        outputs=[
            compression_chapter_id, 
            compression_chapter_num, 
            compression_chapter_title, 
            compression_chapter_text
        ]
    )
    
    # 更新章节（压缩生成页面）
    def update_chapter_compression(chapter_id, chapter_num, chapter_title, chapter_text):
        if not chapter_id:
            return "章节 ID 不能为空"
        return update_chapter(chapter_id, chapter_num, chapter_title, chapter_text)
    
    update_chapter_compression_btn.click(
        fn=update_chapter_compression,
        inputs=[
            compression_chapter_id, 
            compression_chapter_num, 
            compression_chapter_title, 
            compression_chapter_text
        ],
        outputs=chapter_action_status_compression
    )
    
    # 删除章节（压缩生成页面）
    def delete_chapter_compression(chapter_id):
        if not chapter_id:
            return "章节 ID 不能为空"
        return delete_chapter(chapter_id)
    
    delete_chapter_compression_btn.click(
        fn=delete_chapter_compression,
        inputs=compression_chapter_id,
        outputs=chapter_action_status_compression
    )
    
    # ========== 导出功能相关绑定 ==========
    # 刷新小说列表（导出页面）
    def refresh_novel_list_export():
        novels = get_all_novels()
        choices = [(f"{novel[0]} - {novel[1]}", novel[0]) for novel in novels]
        return gr.update(choices=choices)
    
    refresh_novels_export_btn.click(
        fn=refresh_novel_list_export,
        outputs=novel_list_dropdown_export
    )
    
    # 绑定选择小说函数（导出页面）
    def select_novel_export(novel_id):
        print(f"选择的小说 ID: {novel_id}")
        if not novel_id:
            return 0
        return int(novel_id)
    
    novel_list_dropdown_export.change(
        fn=select_novel_export,
        inputs=novel_list_dropdown_export,
        outputs=selected_novel_id_export
    )
    
    # 导出小说功能
    def export_novel_func(novel_id, format_type, include_outline, include_clues,
                         chapter_format="standard", add_page_numbers=False,
                         use_css=True, responsive=True,
                         add_toc=True, use_headings=True):
        """导出小说"""
        if not novel_id:
            return "❌ 请选择要导出的小说", ""
        
        try:
            # 获取小说信息
            novel = get_novel_by_id(novel_id)
            if not novel:
                return "❌ 小说不存在", ""
            
            # 获取章节数量
            chapters = get_novel_chapters(novel_id)
            chapter_count = len(chapters)
            
            if chapter_count == 0:
                return "⚠️ 该小说还没有章节，无法导出", ""
            
            # 预览信息
            preview_lines = [
                f"📚 小说：{novel[1]}",
                f"📝 章节数：{chapter_count}",
                f"📄 导出格式：{format_type.upper()}",
                f"📋 包含大纲：{'是' if include_outline else '否'}",
                f"🔍 包含线索：{'是' if include_clues else '否'}",
                ""
            ]
            
            # 根据格式添加特定选项
            if format_type == "txt":
                preview_lines.append(f"📖 章节样式：{chapter_format}")
                preview_lines.append(f"📄 添加页码：{'是' if add_page_numbers else '否'}")
            elif format_type == "html":
                preview_lines.append(f"🎨 使用 CSS：{'是' if use_css else '否'}")
                preview_lines.append(f"📱 响应式：{'是' if responsive else '否'}")
            elif format_type == "md":
                preview_lines.append(f"📑 添加目录：{'是' if add_toc else '否'}")
                preview_lines.append(f"📝 标题样式：{'是' if use_headings else '否'}")
            
            preview_text = "\n".join(preview_lines)
            
            # 准备导出参数
            export_kwargs = {
                'include_outline': include_outline,
                'include_clues': include_clues,
            }
            
            # 根据格式添加特定参数
            if format_type == "txt":
                export_kwargs['chapter_format'] = chapter_format
                export_kwargs['add_page_numbers'] = add_page_numbers
            elif format_type == "html":
                export_kwargs['use_css_style'] = use_css
                export_kwargs['responsive'] = responsive
            elif format_type == "md":
                export_kwargs['add_table_of_contents'] = add_toc
                export_kwargs['use_heading_style'] = use_headings
            
            # 执行导出
            output_path = export_novel(
                novel_id=novel_id,
                format_type=format_type,
                output_dir="./exports",
                **export_kwargs
            )
            
            # 获取导出文件信息
            import os
            file_size = os.path.getsize(output_path)
            file_size_str = f"{file_size / 1024:.2f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.2f} MB"
            
            status_message = f"✅ 导出成功！\n文件路径：{output_path}\n文件大小：{file_size_str}"
            
            preview_text += f"\n\n✅ 导出成功！\n📁 文件路径：{output_path}\n📊 文件大小：{file_size_str}"
            
            return status_message, preview_text
            
        except Exception as e:
            error_msg = f"❌ 导出失败：{str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return error_msg, ""
    
    export_btn.click(
        fn=export_novel_func,
        inputs=[
            selected_novel_id_export,
            export_format,
            export_include_outline,
            export_include_clues,
            export_chapter_format,
            export_add_page_numbers,
            export_use_css,
            export_responsive,
            export_add_toc,
            export_use_headings
        ],
        outputs=[export_status, export_preview]
    )
    
    # 初始化
    def refresh_statistics():
        """刷新统计数据"""
        import sqlite3
        
        # 获取小说总数
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {db_settings.db_table}")
        total_novels = cursor.fetchone()[0]
        
        # 获取章节总数
        cursor.execute(f"SELECT COUNT(*) FROM {db_settings.chapter_table}")
        total_chapters = cursor.fetchone()[0]
        conn.close()
        
        # 获取统计数据摘要
        stats = get_statistics_summary()
        overall = stats['overall']
        by_type = stats['by_type']
        by_novel = stats['by_novel']
        daily_trend = stats['daily_trend']
        
        # 总体统计
        total_tokens = overall[1] or 0
        total_words = overall[2] or 0
        total_generations = overall[0] or 0
        avg_temp = overall[4] or 0
        
        # 按类型统计
        type_data = []
        for item in by_type:
            type_data.append([
                item[0],  # 事件类型
                item[1],  # 次数
                item[2] or 0,  # Token
                item[3] or 0   # 字数
            ])
        
        # 小说排行
        novel_data = []
        for item in by_novel:
            novel_data.append([
                item[0] or "未命名",  # 小说标题
                item[1],  # 事件数
                item[2] or 0,  # Token
                item[3] or 0   # 字数
            ])
        
        # 每日趋势
        trend_data = []
        for item in daily_trend:
            trend_data.append([
                item[0],  # 日期
                item[1],  # 事件数
                item[2] or 0,  # Token
                item[3] or 0   # 字数
            ])
        
        return [
            total_novels,
            total_chapters,
            total_tokens,
            total_words,
            total_generations,
            avg_temp,
            type_data,
            novel_data,
            trend_data
        ]
    
    refresh_stats_btn.click(
        fn=refresh_statistics,
        outputs=[
            stat_total_novels,
            stat_total_chapters,
            stat_total_tokens,
            stat_total_words,
            stat_total_generations,
            stat_avg_temperature,
            stat_by_type,
            stat_novel_ranking,
            stat_daily_trend
        ]
    )
    
    demo.load(
        fn=refresh_statistics,
        outputs=[
            stat_total_novels,
            stat_total_chapters,
            stat_total_tokens,
            stat_total_words,
            stat_total_generations,
            stat_avg_temperature,
            stat_by_type,
            stat_novel_ranking,
            stat_daily_trend
        ]
    )
    
    demo.load(
        fn=refresh_novel_list_chapter,
        outputs=novel_list_dropdown_chapter
    )
    
    # 加载时刷新导出页面的小说列表
    demo.load(
        fn=refresh_novel_list_export,
        outputs=novel_list_dropdown_export
    )

if __name__ == "__main__":
    demo.launch(theme=gradio_settings.theme)
