from ollama import Client
import sqlite3
import json
from settings import OllamaSettings, ChapterSettings, OutlineSettings, DatabaseSettings, TokenSettings, OutlineGenerationSettings, DeepSeekSettings
from database import add_chapter, get_novel_clues, update_clue_next_chapter, get_novel_by_id

# 加载数据库设置
db_settings = DatabaseSettings()

# 加载设置
ollama_settings = OllamaSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
token_settings = TokenSettings()
outline_gen_settings = OutlineGenerationSettings()
deepseek_settings = DeepSeekSettings()

# 初始化Ollama客户端
client = Client(host=ollama_settings.base_url)

# 生成小说大纲的函数（普通版本）
def generate_outline(prompt, chapter_count, chapter_word_count, chapter_interval, split_count=None, temperature=0.7):
    # 输入验证
    if not prompt or not isinstance(prompt, str):
        return "提示词不能为空"
    
    try:
        chapter_count = int(chapter_count)
        chapter_word_count = int(chapter_word_count)
        chapter_interval = int(chapter_interval)
        temperature = float(temperature)
    except (ValueError, TypeError):
        return "章节数、每章字数、章节间隔和温度必须是数字"
    
    # 确保温度在有效范围内
    temperature = max(0.1, min(temperature, 1.0))
    
    # 使用默认拆分次数如果未指定
    if split_count is None:
        split_count = outline_gen_settings.default_split_count
    
    # 确保拆分次数在有效范围内
    split_count = max(outline_gen_settings.min_split_count, min(split_count, outline_gen_settings.max_split_count))
    
    # 第一步：生成基础骨架
    print("开始生成大纲...")
    print(f"拆分次数设置为：{split_count}")
    
    # 生成小说基础信息和骨架
    # 不使用 JSON 格式，直接使用文本格式以避免解析问题
    system_prompt_base = f"你是一位专业的小说编辑，擅长根据提示词生成小说骨架。请根据用户提供的提示词，生成一个结构完整的小说骨架。\n\n要求：\n1. 第一行为小说标题\n2. 第二行为故事梗概（1-2 句话）\n3. 接下来为主要角色列表（每个角色一行，格式：角色名：角色简介）\n4. 最后为{outline_gen_settings.skeleton_chapter_count}个主要情节节点（每个节点一行，格式：节点 X：节点内容）\n5. 禁用所有的 markdown 格式\n6. 禁止其他所有的输出，只输出骨架内容"
    
    print("正在生成小说基础骨架...")
    try:
        response_base = client.generate(
            model=ollama_settings.model,
            prompt=f"{system_prompt_base}\n\n提示词：{prompt}",
            options={"temperature": temperature, "max_tokens": token_settings.max_tokens_outline, "thinking": deepseek_settings.enable_thinking}
        )
        
        base_skeleton = response_base["response"]
        if not base_skeleton:
            return "生成骨架失败，请重试"
        
        print("基础骨架生成完成")
        
        # 解析骨架内容
        print("正在解析骨架内容...")
        title, summary, characters, plot_nodes = parse_skeleton(base_skeleton)
        
        if not title:
            return "无法从骨架中提取标题"
        
        print(f"小说标题：{title}")
        print(f"故事梗概：{summary}")
        
        # 基于拆分次数进行分段生成
        print(f"开始分段生成大纲，共拆分为{split_count}段...")
        
        # 计算每段的章节数
        chapters_per_segment = chapter_count // split_count
        remainder_chapters = chapter_count % split_count
        
        full_outline = ""
        previous_segment_content = ""
        
        for segment_index in range(split_count):
            print(f"正在生成第 {segment_index + 1}/{split_count} 段大纲...")
            
            # 计算当前段的章节范围
            start_chapter = segment_index * chapters_per_segment + min(segment_index, remainder_chapters) + 1
            end_chapter = (segment_index + 1) * chapters_per_segment + min(segment_index + 1, remainder_chapters)
            current_segment_chapters = end_chapter - start_chapter + 1
            
            # 构建总纲信息（包含骨架和已生成的部分）
            total_outline_context = base_skeleton
            if full_outline:
                total_outline_context += f"\n\n已生成的前序大纲：\n{full_outline}"
            
            # 生成当前段的大纲
            segment_outline = generate_segment_outline(
                title, summary, characters, plot_nodes,
                start_chapter, current_segment_chapters, chapter_word_count, chapter_interval,
                total_outline_context, previous_segment_content,
                segment_index + 1, split_count, temperature=temperature
            )
            
            # 更新已生成的大纲和上一段内容
            if full_outline:
                full_outline += "\n\n" + segment_outline
            else:
                full_outline = segment_outline
            previous_segment_content = segment_outline
            
            print(f"第 {segment_index + 1}/{split_count} 段大纲生成完成")
        
        print("大纲生成完成！")
        return full_outline
    except Exception as e:
        print(f"生成大纲时出错：{str(e)}")
        return f"生成大纲失败：{str(e)}"

# 生成小说大纲的函数（流式输出版本）
def generate_outline_streaming(prompt, chapter_count, chapter_word_count, chapter_interval, split_count=None, temperature=0.7):
    # 输入验证
    if not prompt or not isinstance(prompt, str):
        yield "提示词不能为空"
        return
    
    try:
        chapter_count = int(chapter_count)
        chapter_word_count = int(chapter_word_count)
        chapter_interval = int(chapter_interval)
        temperature = float(temperature)
    except (ValueError, TypeError):
        yield "章节数、每章字数、章节间隔和温度必须是数字"
        return
    
    # 确保温度在有效范围内
    temperature = max(0.1, min(temperature, 1.0))
    
    # 使用默认拆分次数如果未指定
    if split_count is None:
        split_count = outline_gen_settings.default_split_count
    
    # 确保拆分次数在有效范围内
    split_count = max(outline_gen_settings.min_split_count, min(split_count, outline_gen_settings.max_split_count))
    
    # 第一步：生成基础骨架
    progress_text = "开始生成大纲...\n"
    progress_text += f"拆分次数设置为：{split_count}\n\n"
    yield progress_text
    
    # 生成小说基础信息和骨架
    system_prompt_base = f"你是一位专业的小说编辑，擅长根据提示词生成小说骨架。请根据用户提供的提示词，生成一个结构完整的小说骨架。\n\n要求：\n1. 第一行为小说标题\n2. 第二行为故事梗概（1-2 句话）\n3. 接下来为主要角色列表（每个角色一行，格式：角色名：角色简介）\n4. 最后为{outline_gen_settings.skeleton_chapter_count}个主要情节节点（每个节点一行，格式：节点 X：节点内容）\n5. 禁用所有的 markdown 格式\n6. 禁止其他所有的输出，只输出骨架内容"
    
    progress_text += "正在生成小说基础骨架...\n"
    yield progress_text
    
    try:
        response_base = client.generate(
            model=ollama_settings.model,
            prompt=f"{system_prompt_base}\n\n提示词：{prompt}",
            options={"temperature": temperature, "max_tokens": token_settings.max_tokens_outline, "thinking": deepseek_settings.enable_thinking}
        )
        
        base_skeleton = response_base["response"]
        if not base_skeleton:
            yield "生成骨架失败，请重试\n"
            return
        
        progress_text += "基础骨架生成完成\n\n"
        progress_text += "=== 基础骨架 ===\n"
        progress_text += base_skeleton + "\n\n"
        yield progress_text
        
        # 解析骨架内容
        progress_text += "正在解析骨架内容...\n"
        yield progress_text
        
        title, summary, characters, plot_nodes = parse_skeleton(base_skeleton)
        
        if not title:
            yield "无法从骨架中提取标题\n"
            return
        
        progress_text += f"小说标题：{title}\n"
        progress_text += f"故事梗概：{summary}\n\n"
        yield progress_text
        
        # 基于拆分次数进行分段生成
        progress_text += f"开始分段生成大纲，共拆分为{split_count}段...\n\n"
        yield progress_text
        
        # 计算每段的章节数
        chapters_per_segment = chapter_count // split_count
        remainder_chapters = chapter_count % split_count
        
        full_outline = ""
        previous_segment_content = ""
        
        for segment_index in range(split_count):
            progress_text += f"正在生成第 {segment_index + 1}/{split_count} 段大纲...\n"
            yield progress_text
            
            # 计算当前段的章节范围
            start_chapter = segment_index * chapters_per_segment + min(segment_index, remainder_chapters) + 1
            end_chapter = (segment_index + 1) * chapters_per_segment + min(segment_index + 1, remainder_chapters)
            current_segment_chapters = end_chapter - start_chapter + 1
            
            # 构建总纲信息（包含骨架和已生成的部分）
            total_outline_context = base_skeleton
            if full_outline:
                total_outline_context += f"\n\n已生成的前序大纲：\n{full_outline}"
            
            # 生成当前段的大纲
            segment_outline = generate_segment_outline(
                title, summary, characters, plot_nodes,
                start_chapter, current_segment_chapters, chapter_word_count, chapter_interval,
                total_outline_context, previous_segment_content,
                segment_index + 1, split_count, temperature=temperature
            )
            
            # 更新已生成的大纲和上一段内容
            if full_outline:
                full_outline += "\n\n" + segment_outline
            else:
                full_outline = segment_outline
            previous_segment_content = segment_outline
            
            progress_text += f"第 {segment_index + 1}/{split_count} 段大纲生成完成\n"
            progress_text += f"--- 第 {start_chapter}-{end_chapter} 章大纲 ---\n"
            progress_text += segment_outline + "\n\n"
            yield progress_text
        
        progress_text += "大纲生成完成！\n"
        progress_text += "\n=== 完整大纲 ===\n"
        progress_text += full_outline
        yield progress_text
        
    except Exception as e:
        error_text = f"生成大纲时出错：{str(e)}\n"
        yield error_text

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
        if line and (line.startswith("节点") or line.startswith("第")):
            plot_nodes.append(line)
        i += 1
    
    return title, summary, characters, plot_nodes

# 生成最终大纲的函数（用于单次生成完整大纲）
def generate_final_outline(title, summary, characters, plot_nodes, chapter_count, chapter_word_count, chapter_interval, previous_outline=None, temperature=0.7):
    # 构建系统提示
    system_prompt = f"你是一位专业的小说编辑，擅长根据骨架生成详细的章节大纲。请根据以下信息，生成一个完整的小说大纲。\n\n要求：\n1. 第一行为小说标题：{title}\n2. 第二行为故事梗概：{summary}\n3. 接下来为主要角色列表\n"
    
    for character in characters:
        system_prompt += f"{character}\n"
    
    system_prompt += f"\n4. 章节大纲共{chapter_count}章，每章约{chapter_word_count}字，每隔{chapter_interval}章为一个事件进行输出\n"
    system_prompt += "5. 详细描述每章的主要内容、情节发展和角色互动\n"
    system_prompt += "6. 确保章节之间逻辑连贯，情节紧凑\n"
    system_prompt += "7. 禁用所有的 markdown 格式\n"
    system_prompt += "8. 禁止其他所有的输出，只输出详细大纲内容"
    
    # 如果有之前的大纲，加入作为参考
    prompt = system_prompt
    if previous_outline:
        prompt += f"\n\n参考大纲：{previous_outline}"
    else:
        prompt += f"\n\n情节节点：\n"
        for node in plot_nodes:
            prompt += f"{node}\n"
    
    try:
        response = client.generate(
            model=ollama_settings.model,
            prompt=prompt,
            options={"temperature": temperature, "max_tokens": token_settings.max_tokens_outline * 3, "thinking": deepseek_settings.enable_thinking}
        )
        
        outline = response["response"]
        if not outline:
            return "生成大纲失败，请重试"
        
        return outline
    except Exception as e:
        print(f"生成最终大纲时出错：{str(e)}")
        return f"生成大纲失败：{str(e)}"

# 生成段落大纲的函数（用于分段生成）
def generate_segment_outline(title, summary, characters, plot_nodes, start_chapter, chapter_count, chapter_word_count, chapter_interval, total_outline_context, previous_segment_content, segment_index, total_segments, temperature=0.7):
    """
    生成指定章节范围的大纲段落
    
    参数：
    - title: 小说标题
    - summary: 故事梗概
    - characters: 角色列表
    - plot_nodes: 情节节点列表
    - start_chapter: 起始章节编号
    - chapter_count: 当前段包含的章节数
    - chapter_word_count: 每章字数
    - chapter_interval: 章节间隔
    - total_outline_context: 总纲信息（包含骨架和已生成的前序大纲）
    - previous_segment_content: 上一段生成的大纲内容（用于保持连贯性）
    - segment_index: 当前段序号（从 1 开始）
    - total_segments: 总段数
    - temperature: 生成温度
    """
    # 计算当前段在整体中的位置比例
    progress_percentage = (segment_index / total_segments) * 100
    
    # 构建系统提示
    system_prompt = f"你是一位专业的小说编辑，擅长根据骨架和已有大纲生成详细的章节大纲段落。请根据以下信息，生成第{start_chapter}章至第{start_chapter + chapter_count - 1}章的详细大纲。\n\n"
    
    system_prompt += f"小说标题：{title}\n"
    system_prompt += f"故事梗概：{summary}\n\n"
    
    system_prompt += "主要角色：\n"
    for character in characters:
        system_prompt += f"{character}\n"
    
    system_prompt += f"\n情节节点：\n"
    for node in plot_nodes:
        system_prompt += f"{node}\n"
    
    system_prompt += f"\n总纲信息（包含基础骨架和已生成的前序大纲）：\n{total_outline_context}\n"
    
    if previous_segment_content:
        system_prompt += f"\n上一段大纲内容（用于保持连贯性）：\n{previous_segment_content}\n"
    
    system_prompt += f"\n当前生成进度：第 {segment_index}/{total_segments} 段（{progress_percentage:.0f}%）\n"
    system_prompt += f"当前章节范围：第{start_chapter}章 至 第{start_chapter + chapter_count - 1}章（共{chapter_count}章）\n"
    
    system_prompt += f"\n要求：\n"
    system_prompt += f"1. 生成第{start_chapter}章至第{start_chapter + chapter_count - 1}章的详细大纲，共{chapter_count}章\n"
    system_prompt += f"2. 每章约{chapter_word_count}字，每隔{chapter_interval}章为一个事件\n"
    system_prompt += "3. 详细描述每章的主要内容、情节发展和角色互动\n"
    system_prompt += "4. 确保与总纲信息保持一致，与上一段大纲内容逻辑连贯\n"
    system_prompt += "5. 保持章节之间逻辑连贯，情节紧凑\n"
    system_prompt += "6. 根据当前进度合理安排情节发展节奏\n"
    system_prompt += "   - 如果是开头部分（前 30%），注重铺垫和角色介绍\n"
    system_prompt += "   - 如果是中间部分（30%-70%），注重情节发展和冲突升级\n"
    system_prompt += "   - 如果是后半部分（70%-90%），注重高潮铺垫\n"
    system_prompt += "   - 如果是结尾部分（90%-100%），注重收束线索和结局\n"
    system_prompt += "7. 禁用所有的 markdown 格式\n"
    system_prompt += "8. 禁止其他所有的输出，只输出详细大纲内容"
    
    try:
        response = client.generate(
            model=ollama_settings.model,
            prompt=system_prompt,
            options={"temperature": temperature, "max_tokens": token_settings.max_tokens_outline * 3, "thinking": deepseek_settings.enable_thinking}
        )
        
        outline = response["response"]
        if not outline:
            return "生成段落大纲失败，请重试"
        
        return outline
    except Exception as e:
        print(f"生成段落大纲时出错：{str(e)}")
        return f"生成段落大纲失败：{str(e)}"

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
    print(f"处理小说选择值: {novel_id}")
    
    if not novel_id:
        return "无效的小说ID"
    
    # 获取小说信息
    print("正在获取小说信息...")
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
    print(f"小说标题：{novel_title}")
    print(f"总章节数：{total_chapters}")
    
    # 获取上一章节内容
    previous_chapter = None
    if chapter_number > 1:
        print("正在获取上一章节内容...")
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT content FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, chapter_number - 1))
        previous = cursor.fetchone()
        conn.close()
        if previous:
            previous_chapter = previous[0]
            print("已获取上一章节内容")
    
    # 获取小说的线索
    print("正在获取小说线索...")
    clues = get_novel_clues(novel_id)
    active_clues = []
    for clue in clues:
        clue_id, clue_text, clue_type, first_chapter, next_chapter = clue
        # 如果线索应该在本章或之前出现，且尚未在本章之后安排出现
        if (next_chapter is None or next_chapter <= chapter_number):
            active_clues.append((clue_id, clue_text, clue_type, first_chapter))
    
    if active_clues:
        print(f"找到 {len(active_clues)} 个活跃线索")
    
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
    print(f"正在生成第{chapter_number}章...")
    response = client.generate(
        model=ollama_settings.model,
        prompt=system_prompt,
        options={"temperature": temperature, "max_tokens": word_count * token_settings.token_coefficient_chapter, "thinking": deepseek_settings.enable_thinking}  # 使用配置的token系数
    )
    
    # 处理响应内容
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
    print("正在检查章节编号...")
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
    print("正在保存章节...")
    add_chapter(novel_id, chapter_number, chapter_title, chapter_content)
    print("章节保存成功")
    
    # 更新线索的下次出现时间
    if total_chapters and active_clues:
        print("正在更新线索信息...")
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
        print("线索信息更新完成")
    
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
    print("章节生成完成！")
    return chapter_content, True

# 生成章节的函数（流式输出版本）
def generate_chapter_streaming(novel_id, chapter_number, word_count, temperature, clue_threshold=3):
    """
    流式输出版本的章节生成函数
    实时显示生成进度和章节内容
    """
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    
    if not novel_id:
        yield "无效的小说 ID"
        return
    
    # 获取小说信息
    progress_text = "正在获取小说信息...\n"
    yield progress_text
    
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT title, outline, total_chapters FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    novel = cursor.fetchone()
    conn.close()
    
    if not novel:
        yield "小说不存在"
        return
    
    novel_title, outline, total_chapters = novel
    progress_text += f"小说标题：{novel_title}\n"
    progress_text += f"总章节数：{total_chapters}\n"
    yield progress_text
    
    # 获取上一章节内容
    previous_chapter = None
    if chapter_number > 1:
        progress_text += "正在获取上一章节内容...\n"
        yield progress_text
        
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT content FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, chapter_number - 1))
        previous = cursor.fetchone()
        conn.close()
        if previous:
            previous_chapter = previous[0]
            progress_text += "已获取上一章节内容\n"
            yield progress_text
    
    # 获取小说的线索
    progress_text += "正在获取小说线索...\n"
    yield progress_text
    
    clues = get_novel_clues(novel_id)
    active_clues = []
    for clue in clues:
        clue_id, clue_text, clue_type, first_chapter, next_chapter = clue
        # 如果线索应该在本章或之前出现，且尚未在本章之后安排出现
        if (next_chapter is None or next_chapter <= chapter_number):
            active_clues.append((clue_id, clue_text, clue_type, first_chapter))
    
    if active_clues:
        progress_text += f"找到 {len(active_clues)} 个活跃线索\n"
        yield progress_text
    
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
    system_prompt += f"5. 禁用所有的 markdown 格式\n"
    system_prompt += f"6. 禁止其他所有的输出，只输出章节内容"
    
    # 生成章节（流式输出）
    progress_text += f"正在生成第{chapter_number}章...\n"
    progress_text += "=== 生成开始 ===\n"
    yield progress_text
    
    try:
        response = client.generate(
            model=ollama_settings.model,
            prompt=system_prompt,
            options={"temperature": temperature, "max_tokens": word_count * token_settings.token_coefficient_chapter, "thinking": deepseek_settings.enable_thinking}
        )
        
        # 处理响应内容
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
        
        # 显示生成的章节内容
        progress_text += chapter_content + "\n"
        progress_text += "\n=== 生成完成 ===\n"
        yield progress_text
        
        # 检查章节编号是否已存在
        print("正在检查章节编号...")
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT id FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, chapter_number))
        existing_chapter = cursor.fetchone()
        conn.close()
        
        if existing_chapter:
            yield f"\n错误：章节 {chapter_number} 已经存在，请修改章节编号"
            return
        
        # 保存章节
        print("正在保存章节...")
        add_chapter(novel_id, chapter_number, chapter_title, chapter_content)
        progress_text += "\n章节已保存到数据库\n"
        yield progress_text
        
        # 更新线索的下次出现时间
        if total_chapters and active_clues:
            progress_text += "正在更新线索信息...\n"
            yield progress_text
            
            for clue_id, _, _, first_chapter in active_clues:
                # 预估下次线索出现的章节
                chapters_passed = chapter_number - first_chapter
                if chapters_passed > 0:
                    # 简单算法：平均间隔章节数
                    avg_interval = max(1, (total_chapters - first_chapter) // 3)  # 假设线索出现 3 次
                    next_chapter_estimate = chapter_number + avg_interval
                    # 确保不超过总章节数
                    next_chapter_estimate = min(next_chapter_estimate, total_chapters)
                    update_clue_next_chapter(clue_id, next_chapter_estimate)
            progress_text += "线索信息更新完成\n"
            yield progress_text
        
        # 添加线索分析结果
        if active_clues and total_chapters:
            progress_text += "\n=== 线索分析 ===\n"
            progress_text += f"当前章节：第{chapter_number}章\n"
            progress_text += f"小说总章节数：{total_chapters}章\n"
            if total_chapters - chapter_number <= clue_threshold:
                progress_text += f"提示：已接近小说结尾，剩余{total_chapters - chapter_number}章\n"
            progress_text += "\n活跃线索及预估下次出现章节：\n"
            for clue_id, clue_text, clue_type, first_chapter in active_clues:
                # 获取更新后的下次出现章节
                conn = sqlite3.connect(db_settings.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT next_chapter FROM clues WHERE id = ?", (clue_id,))
                next_chapter = cursor.fetchone()[0]
                conn.close()
                progress_text += f"- {clue_type}：{clue_text} → 预计下次出现于第{next_chapter}章\n"
            yield progress_text
        
        # 返回章节内容和一个标志，表示生成成功
        progress_text += "\n章节生成完成！\n"
        yield progress_text, True
        
    except Exception as e:
        error_text = f"生成章节时出错：{str(e)}\n"
        yield error_text

# 从章节内容中提取线索的函数
def extract_clues_from_chapter(chapter_content, chapter_number, novel_outline, total_chapters, clue_count=2):
    """
    使用AI从章节内容中提取线索，并根据大纲推测预计出现章节数
    """
    try:
        # 输入验证
        if not chapter_content or not isinstance(chapter_content, str):
            return []
        
        # 构建系统提示，使用文本格式而非JSON
        system_prompt = f"你是一位专业的小说编辑，擅长从小说章节中识别和提取线索。请从以下章节内容中提取{clue_count}个重要的线索，包括明潮和暗涌两种类型。\n\n要求：\n1. 分析章节内容，识别出{clue_count}个重要的线索\n2. 为每条线索指定类型（明潮或暗涌）\n3. 基于小说大纲，推测每条线索的预计下次出现章节数\n4. 输出格式为：每条线索两行，第一行为「类型：线索内容」，第二行为「预计出现章节：X」\n5. 确保线索格式规范，内容简洁明了\n6. 只输出线索，不输出其他内容"
        
        # 调用AI生成线索
        response = client.generate(
            model=ollama_settings.model,
            prompt=f"{system_prompt}\n\n章节内容：{chapter_content}\n\n小说大纲：{novel_outline}",
            options={"temperature": 0.5, "max_tokens": token_settings.max_tokens_clue_extraction, "thinking": deepseek_settings.enable_thinking}
        )
        
        # 处理响应
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
    except Exception as e:
        print(f"提取线索时出错：{str(e)}")
        return []
