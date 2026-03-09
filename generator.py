from ollama import Client
import sqlite3
from settings import OllamaSettings, ChapterSettings, OutlineSettings, DatabaseSettings, TokenSettings, OutlineGenerationSettings
from database import add_chapter, get_novel_clues, update_clue_next_chapter, get_novel_by_id

# 加载数据库设置
db_settings = DatabaseSettings()

# 加载设置
ollama_settings = OllamaSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
token_settings = TokenSettings()
outline_gen_settings = OutlineGenerationSettings()

# 初始化Ollama客户端
client = Client(host=ollama_settings.base_url)

# 生成小说大纲的函数
def generate_outline(prompt, chapter_count, chapter_word_count, chapter_interval, recursion_depth=None):
    # 使用默认递归深度如果未指定
    if recursion_depth is None:
        recursion_depth = outline_gen_settings.default_recursion_depth
    
    # 确保递归深度在有效范围内
    recursion_depth = max(outline_gen_settings.min_recursion_depth, min(recursion_depth, outline_gen_settings.max_recursion_depth))
    
    # 第一步：生成基础骨架
    print(f"开始生成大纲，递归深度：{recursion_depth}")
    
    # 生成小说基础信息和骨架
    system_prompt_base = f"你是一位专业的小说编辑，擅长根据提示词生成小说骨架。请根据用户提供的提示词，生成一个结构完整的小说骨架。\n\n要求：\n1. 第一行为小说标题\n2. 第二行为故事梗概（1-2句话）\n3. 接下来为主要角色列表（每个角色一行，格式：角色名：角色简介）\n4. 最后为{outline_gen_settings.skeleton_chapter_count}个主要情节节点（每个节点一行，格式：节点X：节点内容）\n5. 禁用所有的markdown格式\n6. 禁止其他所有的输出，只输出骨架内容"
    
    response_base = client.generate(
        model=ollama_settings.model,
        prompt=f"{system_prompt_base}\n\n提示词：{prompt}",
        options={"temperature": 0.7, "max_tokens": token_settings.max_tokens_outline}
    )
    
    base_skeleton = response_base["response"]
    print("基础骨架生成完成")
    
    # 解析骨架内容
    title, summary, characters, plot_nodes = parse_skeleton(base_skeleton)
    
    if recursion_depth == 1:
        # 递归深度为1，直接基于骨架生成完整大纲
        return generate_final_outline(title, summary, characters, plot_nodes, chapter_count, chapter_word_count, chapter_interval)
    else:
        # 递归深度大于1，逐步细化
        current_depth = 1
        current_outline = base_skeleton
        
        while current_depth < recursion_depth:
            print(f"开始第{current_depth+1}层递归细化")
            # 基于当前大纲生成更详细的内容
            system_prompt_refine = f"你是一位专业的小说编辑，擅长细化小说大纲。请根据以下大纲，生成更详细的版本。\n\n要求：\n1. 保留原有的小说标题、故事梗概和主要角色\n2. 扩展情节节点，增加更多细节和连贯性\n3. 为每个情节节点添加更多具体内容和发展线索\n4. 保持结构清晰，逻辑连贯\n5. 禁用所有的markdown格式\n6. 禁止其他所有的输出，只输出细化后的大纲"
            
            response_refine = client.generate(
                model=ollama_settings.model,
                prompt=f"{system_prompt_refine}\n\n当前大纲：{current_outline}",
                options={"temperature": 0.7, "max_tokens": token_settings.max_tokens_outline * 2}
            )
            
            current_outline = response_refine["response"]
            current_depth += 1
            print(f"第{current_depth}层递归细化完成")
        
        # 最后生成完整的章节大纲
        print("生成最终章节大纲")
        return generate_final_outline(title, summary, characters, plot_nodes, chapter_count, chapter_word_count, chapter_interval, current_outline)

# 解析骨架内容的函数
def parse_skeleton(skeleton):
    lines = skeleton.strip().split('\n')
    title = ""
    summary = ""
    characters = []
    plot_nodes = []
    
    if lines:
        title = lines[0].strip()
    
    if len(lines) > 1:
        summary = lines[1].strip()
    
    i = 2
    # 解析角色
    while i < len(lines):
        line = lines[i].strip()
        if line and "：" in line and not line.startswith("节点"):
            characters.append(line)
            i += 1
        else:
            break
    
    # 解析情节节点
    while i < len(lines):
        line = lines[i].strip()
        if line and line.startswith("节点"):
            plot_nodes.append(line)
        i += 1
    
    return title, summary, characters, plot_nodes

# 生成最终大纲的函数
def generate_final_outline(title, summary, characters, plot_nodes, chapter_count, chapter_word_count, chapter_interval, previous_outline=None):
    # 构建系统提示
    system_prompt = f"你是一位专业的小说编辑，擅长根据骨架生成详细的章节大纲。请根据以下信息，生成一个完整的小说大纲。\n\n要求：\n1. 第一行为小说标题：{title}\n2. 第二行为故事梗概：{summary}\n3. 接下来为主要角色列表\n"
    
    for character in characters:
        system_prompt += f"{character}\n"
    
    system_prompt += f"\n4. 章节大纲共{chapter_count}章，每章约{chapter_word_count}字，每隔{chapter_interval}章为一个事件进行输出\n"
    system_prompt += "5. 详细描述每章的主要内容、情节发展和角色互动\n"
    system_prompt += "6. 确保章节之间逻辑连贯，情节紧凑\n"
    system_prompt += "7. 禁用所有的markdown格式\n"
    system_prompt += "8. 禁止其他所有的输出，只输出详细大纲内容"
    
    # 如果有之前的大纲，加入作为参考
    prompt = system_prompt
    if previous_outline:
        prompt += f"\n\n参考大纲：{previous_outline}"
    else:
        prompt += f"\n\n情节节点：\n"
        for node in plot_nodes:
            prompt += f"{node}\n"
    
    response = client.generate(
        model=ollama_settings.model,
        prompt=prompt,
        options={"temperature": 0.7, "max_tokens": token_settings.max_tokens_outline * 3}
    )
    
    return response["response"]

# 从大纲中提取标题
def extract_title(outline):
    lines = outline.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            return line
    return "未知标题"

# 生成章节的函数
def generate_chapter(novel_id, chapter_number, word_count, temperature, clue_threshold=3):
    # 确保novel_id是整数
    print(f"novel_id type: {type(novel_id)}, value: {novel_id}")  # 调试信息
    if isinstance(novel_id, list):
        # 处理嵌套列表，如 [['2', '九霄天命']]
        while isinstance(novel_id, list) and len(novel_id) > 0:
            novel_id = novel_id[0]
        # 现在novel_id应该是字符串 '2' 或 ['2', '九霄天命']
        if isinstance(novel_id, list) and len(novel_id) > 0:
            # 格式为 ['2', '九霄天命']
            novel_id = novel_id[0]
        if isinstance(novel_id, str):
            # 尝试提取ID部分
            try:
                novel_id = int(novel_id)
            except ValueError:
                return "无效的小说ID"
        else:
            return "无效的小说ID"
    elif isinstance(novel_id, str):
        # 尝试从字符串中提取ID
        try:
            if ':' in novel_id:
                novel_id = int(novel_id.split(':')[0].strip())
            else:
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
    system_prompt = f"你是一位专业的小说作家，擅长根据大纲和上一章节生成新的章节。请根据以下信息生成第{chapter_number}章。\n"
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
    
    system_prompt += f"\n要求：\n"
    system_prompt += f"1. 第一行为章节标题\n"
    system_prompt += f"2. 接下来为正文内容\n"
    system_prompt += f"3. 字数约{word_count}字\n"
    system_prompt += f"4. 风格保持一致，情节连贯\n"
    system_prompt += f"5. 禁用所有的markdown格式\n"
    system_prompt += f"6. 禁止其他所有的输出，只输出章节内容"
    
    # 生成章节
    response = client.generate(
        model=ollama_settings.model,
        prompt=system_prompt,
        options={"temperature": temperature, "max_tokens": word_count * token_settings.token_coefficient_chapter}  # 使用配置的token系数
    )
    
    chapter_content = response["response"]
    
    # 提取章节标题
    chapter_title = f"第{chapter_number}章"
    lines = chapter_content.split('\n')
    for line in lines:
        if line.startswith(f"第{chapter_number}章"):
            chapter_title = line.strip()
            break
    
    # 规范输出格式，确保章节内容第一行为章节名
    formatted_content = f"{chapter_title}\n\n"
    # 跳过已经存在的标题行
    skip_lines = 0
    for line in lines:
        if line.startswith(f"第{chapter_number}章") or line.strip() == novel_title:
            skip_lines += 1
        else:
            break
    # 添加章节内容
    formatted_content += '\n'.join(lines[skip_lines:])
    chapter_content = formatted_content
    
    # 检查章节编号是否已存在
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
    """, (novel_id, chapter_number))
    existing_chapter = cursor.fetchone()
    conn.close()
    
    if existing_chapter:
        return f"章节 {chapter_number} 已经存在，请修改章节编号"
    
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
    
    # 返回章节内容和一个标志，表示生成成功
    return chapter_content, True

# 从章节内容中提取线索的函数
def extract_clues_from_chapter(chapter_content, chapter_number, novel_outline, total_chapters, clue_count=2):
    """
    使用AI从章节内容中提取线索，并根据大纲推测预计出现章节数
    """
    system_prompt = f"你是一位专业的小说编辑，擅长从小说章节中识别和提取线索。请从以下章节内容中提取{clue_count}个重要的线索，包括明潮和暗涌两种类型。\n\n要求：\n1. 分析章节内容，识别出{clue_count}个重要的线索\n2. 为每条线索指定类型（明潮或暗涌）\n3. 基于小说大纲，推测每条线索的预计下次出现章节数\n4. 输出格式为：每条线索两行，第一行为「类型：线索内容」，第二行为「预计出现章节：X」\n5. 确保线索格式规范，内容简洁明了\n6. 只输出线索，不输出其他内容"
    
    response = client.generate(
        model=ollama_settings.model,
        prompt=f"{system_prompt}\n\n章节内容：{chapter_content}\n\n小说大纲：{novel_outline}",
        options={"temperature": 0.5, "max_tokens": token_settings.max_tokens_clue_extraction}
    )
    
    clues = []
    lines = response["response"].split('\n')
    i = 0
    while i < len(lines) and len(clues) < clue_count:
        line = lines[i].strip()
        if line and '：' in line:
            parts = line.split('：', 1)
            if len(parts) == 2:
                clue_type = parts[0].strip()
                clue_text = parts[1].strip()
                if clue_type in ["明潮", "暗涌"]:
                    # 规范线索格式，确保内容简洁
                    clue_text = clue_text.strip().rstrip('。')
                    if clue_text:
                        # 尝试获取预计出现章节数
                        next_chapter = None
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line.startswith("预计出现章节："):
                                try:
                                    next_chapter_str = next_line.split("：")[1].strip()
                                    next_chapter = int(next_chapter_str)
                                    # 确保章节数在合理范围内
                                    if next_chapter < chapter_number:
                                        next_chapter = chapter_number + 1
                                    if total_chapters and next_chapter > total_chapters:
                                        next_chapter = total_chapters
                                except (ValueError, IndexError):
                                    # 如果解析失败，使用默认值
                                    pass
                        clues.append((clue_text, clue_type, chapter_number, next_chapter))
                        i += 2  # 跳过下一行
                        continue
        i += 1
    
    return clues
