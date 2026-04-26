from ollama import Client
import sqlite3
import json
import time
from settings import OllamaSettings, ChapterSettings, OutlineSettings, DatabaseSettings, TokenSettings, OutlineGenerationSettings, DeepSeekSettings, CompressionGenerationSettings
from database import add_chapter, get_novel_clues, update_clue_next_chapter, get_novel_by_id, record_usage

# 加载数据库设置
db_settings = DatabaseSettings()

# 加载设置
ollama_settings = OllamaSettings()
chapter_settings = ChapterSettings()
outline_settings = OutlineSettings()
token_settings = TokenSettings()
outline_gen_settings = OutlineGenerationSettings()
deepseek_settings = DeepSeekSettings()
compression_settings = CompressionGenerationSettings()

# 初始化 Ollama 客户端
client = Client(host=ollama_settings.base_url, timeout=ollama_settings.timeout)

# 生成小说大纲的函数（流式输出版本）
def generate_outline_streaming(prompt, chapter_count, chapter_word_count, plot_node_count, temperature=0.7):
    # 输入验证
    if not prompt or not isinstance(prompt, str):
        yield "提示词不能为空"
        return
    
    try:
        chapter_count = int(chapter_count)
        chapter_word_count = int(chapter_word_count)
        plot_node_count = int(plot_node_count)
        temperature = float(temperature)
    except (ValueError, TypeError):
        yield "章节数、每章字数、情节节点数和温度必须是数字"
        return
    
    # 确保温度在有效范围内
    temperature = max(0.1, min(temperature, 1.0))
    
    # 第一步：生成基础骨架
    progress_text = "开始生成大纲...\n"
    progress_text += f"情节节点数：{plot_node_count}个\n\n"
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
        
        # 构建系统提示
        system_prompt_full = f"""你是一位专业的小说编辑，擅长根据骨架生成大纲。请根据以下信息，将{plot_node_count}个情节节点分配到第 1 章至第{chapter_count}章。

【基本信息】
- 小说标题：{title}
- 故事梗概：{summary}
- 总章节数：{chapter_count}章
- 每章字数：约{chapter_word_count}字
- 情节节点数：{plot_node_count}个

【主要角色】
"""
        for character in characters:
            system_prompt_full += f"{character}\n"
        
        system_prompt_full += f"""
【情节节点】（共{plot_node_count}个）
"""
        for node in plot_nodes:
            system_prompt_full += f"{node}\n"
        
        system_prompt_full += f"""
【生成要求】
1. 将{plot_node_count}个情节节点合理分配到{chapter_count}章中
2. 说明每个情节节点覆盖的章节范围（例如：第 1-5 章）
3. 每个情节节点需要包含以下要素：
   - 核心冲突：该节点的主要矛盾和冲突点
   - 角色成长：角色在该节点的心理变化或能力提升
   - 世界观展开：逐步揭示的世界观设定（如适用）
   - 伏笔暗线：埋下的伏笔或暗线发展
   - 情感节奏：该节点的情感基调变化（如：平静→紧张→爆发）
4. 保持情节连贯，节奏合理
5. 禁用所有的 markdown 格式
6. 禁止其他所有的输出，只输出大纲内容

【输出格式】
节点 1（第 1-X 章）：节点标题
核心冲突：...
角色成长：...
世界观展开：...
伏笔暗线：...
情感节奏：...
情节走向：...

节点 2（第 X-Y 章）：节点标题
核心冲突：...
角色成长：...
世界观展开：...
伏笔暗线：...
情感节奏：...
情节走向：...

...（依此类推）
"""
        
        progress_text += "正在生成完整大纲...\n"
        yield progress_text
        
        response_full = client.generate(
            model=ollama_settings.model,
            prompt=system_prompt_full,
            options={"temperature": temperature, "max_tokens": token_settings.max_tokens_outline * 3, "thinking": deepseek_settings.enable_thinking}
        )
        
        full_outline = response_full["response"]
        if not full_outline:
            yield "生成大纲失败，请重试"
            return
        
        progress_text += "完整大纲生成完成！\n"
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

# 从大纲中提取标题
def extract_title(outline):
    lines = outline.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            return line
    return "未知标题"

# 生成章节的函数
def generate_chapter(novel_id, chapter_number, word_count, temperature, clue_threshold=3, additional_prompt="", generate_next_chapter_guidance=False, previous_chapter_count=1):
    start_time = time.time()
    
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    print(f"传入历史章节数：{previous_chapter_count}")
    
    if not novel_id:
        return "无效的小说 ID"
    
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
    
    # 获取历史章节内容（根据传入数量）
    previous_chapters = []
    previous_chapter_guidance = None
    
    if chapter_number > 1:
        print(f"正在获取前{min(previous_chapter_count, chapter_number - 1)}章内容...")
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        
        # 获取最近的 previous_chapter_count 章
        start_chapter = max(1, chapter_number - previous_chapter_count)
        for ch_num in range(start_chapter, chapter_number):
            cursor.execute(f"""
            SELECT content, next_chapter_guidance FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
            """, (novel_id, ch_num))
            chapter_data = cursor.fetchone()
            if chapter_data:
                previous_chapters.append({
                    'chapter_number': ch_num,
                    'content': chapter_data[0],
                    'guidance': chapter_data[1]
                })
                print(f"已获取第{ch_num}章内容（长度：{len(chapter_data[0])}字）")
                if chapter_data[1]:
                    print(f"第{ch_num}章指导文字长度：{len(chapter_data[1])}字")
        
        conn.close()
        
        # 使用最后一章的指导文字
        if previous_chapters and previous_chapters[-1]['guidance']:
            previous_chapter_guidance = previous_chapters[-1]['guidance']
            print(f"已获取最新章指导文字")
        
        if not previous_chapters:
            print(f"警告：未找到第 {start_chapter}-{chapter_number - 1} 章的记录")
    
    # 获取小说的线索
    print("正在获取小说线索...")
    clues = get_novel_clues(novel_id)
    active_clues = []
    urgent_clues = []  # 紧急线索（必须在本章出现）
    
    for clue in clues:
        clue_id, clue_text, clue_type, first_chapter, next_chapter = clue
        
        # 计算线索的紧急程度
        chapters_since_first = chapter_number - first_chapter
        
        # 紧急线索：超过预计出现章节 2 章以上，或者首次出现后已经过了很多章
        if next_chapter is not None and chapter_number >= next_chapter:
            urgent_clues.append((clue_id, clue_text, clue_type, first_chapter, next_chapter))
        # 普通激活：首次出现且还未安排下次出现，且已经过了至少 1 章
        elif next_chapter is None and chapters_since_first >= 1:
            active_clues.append((clue_id, clue_text, clue_type, first_chapter, None))
    
    # 合并紧急线索和普通线索
    all_active_clues = urgent_clues + active_clues
    
    if urgent_clues:
        print(f"找到 {len(urgent_clues)} 个紧急线索（需要优先处理）")
    if active_clues:
        print(f"找到 {len(active_clues)} 个活跃线索")
    if not all_active_clues:
        print("当前没有需要激活的线索")
    
    # 构建系统提示
    system_prompt = f"""你是一位专业的小说作家，擅长根据大纲和历史章节生成新的章节。

【当前任务】
请生成第{chapter_number}章的内容

【基本信息】
- 小说标题：{novel_title}
- 小说总章节数：{total_chapters}章
- 当前章节：第{chapter_number}章（进度：{chapter_number}/{total_chapters}，约{int(chapter_number/total_chapters*100) if total_chapters else 0}%）

【小说总纲】
{outline}

"""
    
    # 添加历史章节内容
    if previous_chapters:
        system_prompt += "【历史章节内容】\n"
        for ch_data in previous_chapters:
            ch_num = ch_data['chapter_number']
            ch_content = ch_data['content']
            system_prompt += f"第{ch_num}章:\n{ch_content}\n\n"
        system_prompt += f"【最新章指导文字】\n{previous_chapter_guidance if previous_chapter_guidance else '无指导文字'}\n"
    else:
        system_prompt += f"""【上一章内容】
这是第一章，无上一章内容

【上一章指导文字】
无指导文字
"""
    
    # 添加线索信息（仅在有线索时提供，让 AI 自主决定是否使用）
    if all_active_clues:
        # 区分紧急线索和普通线索
        if urgent_clues:
            system_prompt += f"""
【紧急线索】（这些线索已经过期，请务必在本章中自然融入）
"""
            for _, clue_text, clue_type, first_chapter, next_chapter in urgent_clues:
                delay_info = f"（原计划第{next_chapter}章出现，已延迟{chapter_number - next_chapter}章）" if next_chapter else ""
                system_prompt += f"- 【{clue_type}】{clue_text}（首次出现于第{first_chapter}章{delay_info}）\n"
        
        if active_clues:
            system_prompt += f"""
【可选线索】（这些线索可供参考，请根据情节需要选择使用）
"""
            for _, clue_text, clue_type, first_chapter, _ in active_clues:
                system_prompt += f"- 【{clue_type}】{clue_text}（首次出现于第{first_chapter}章）\n"
        
        system_prompt += f"""
【线索使用说明】
1. **紧急线索必须使用**：如果情节允许，请巧妙地将紧急线索融入本章内容
2. **可选线索灵活使用**：根据情节发展需要，可以选择使用部分或全部可选线索，也可以不使用
3. **自然融入**：线索应该是情节的自然组成部分，不要生硬插入
4. **使用标记**：
   - 如果使用了任何紧急线索，请在章节内容的第二行输出数字 1
   - 如果只使用了可选线索，请在章节内容的第二行输出数字 2
   - 如果没有使用任何线索，请在章节内容的第二行输出数字 0
"""
    else:
        system_prompt += """
【线索信息】
当前无需特别关注的线索，请按照大纲和情节自然发展
"""
    
    system_prompt += f"""
【撰写要求】
1. 第一行为章节标题（格式：第{chapter_number}章 XXX）
2. 第二行为线索使用标记：1（使用了线索）或 0（未使用线索）
3. 第三行开始为正文内容，约{word_count}字
4. 保持与上一章内容的情节连贯
5. 符合小说总纲的设定
6. 如有本章详细大纲，请严格按照大纲撰写
7. 禁用所有的 markdown 格式
8. 禁止其他所有的输出，只输出章节内容
9. **重要：不要在章节末尾重复前面的内容，每段内容都应该是新的情节发展**
10. **重要：当达到目标字数后，自然结束章节，不要为了凑字数而重复**
"""
    
    # 添加用户的附加提示词
    if additional_prompt:
        system_prompt += f"\n【用户附加要求】\n{additional_prompt}\n"
    
    # 检查是否接近结尾
    if total_chapters and total_chapters - chapter_number <= clue_threshold:
        system_prompt += f"\n注意：已接近小说结尾（剩余{total_chapters - chapter_number}章），请适当收束线索。\n"
    
    # 生成章节
    print(f"正在生成第{chapter_number}章...")
    response = client.generate(
        model=ollama_settings.model,
        prompt=system_prompt,
        options={"temperature": temperature, "max_tokens": word_count * token_settings.token_coefficient_chapter, "thinking": deepseek_settings.enable_thinking}  # 使用配置的token系数
    )
    
    # 处理响应内容
    chapter_content = response["response"]
    
    # 提取章节标题和线索标记
    chapter_title = f"第{chapter_number}章"
    lines = chapter_content.split('\n')
    clue_used = False  # 线索使用标记
    
    # 查找章节标题行
    title_line_idx = 0
    for i, line in enumerate(lines):
        if line.startswith(f"第{chapter_number}章"):
            chapter_title = line.strip()
            title_line_idx = i
            break
    
    # 检查第二行是否为线索标记（1 或 0）
    clue_marker_line = title_line_idx + 1
    if clue_marker_line < len(lines):
        marker = lines[clue_marker_line].strip()
        if marker == "1":
            clue_used = True
            print("检测到线索使用标记：1（使用了线索）")
        elif marker == "0":
            clue_used = False
            print("检测到线索使用标记：0（未使用线索）")
    
    # 规范输出格式，确保章节内容第一行为章节名，第二行为线索标记
    formatted_content = f"{chapter_title}\n"
    formatted_content += f"{'1' if clue_used else '0'}\n"
    
    # 跳过标题行和线索标记行
    skip_lines = title_line_idx + 1
    # 如果第二行是线索标记，也跳过
    if skip_lines < len(lines) and lines[skip_lines].strip() in ["0", "1"]:
        skip_lines += 1
    
    # 添加章节内容（从第三行开始）
    formatted_content += '\n'.join(lines[skip_lines:])
    chapter_content = formatted_content
    
    # 验证生成内容的有效性
    content_text = '\n'.join(lines[skip_lines:]).strip()
    if not content_text or len(content_text) < 50:  # 内容太短，可能是生成失败
        return f"第{chapter_number}章生成失败：内容过短或为空，请重试"
    
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
    
    # 生成下一章指导文字（如果需要）
    next_chapter_guidance = None
    if generate_next_chapter_guidance:
        print("正在生成下一章指导文字...")
        try:
            next_chapter_guidance = _generate_guidance_for_next_chapter(
                novel_title=novel_title,
                novel_outline=outline,
                current_chapter_number=chapter_number,
                current_chapter_content=chapter_content,
                active_clues=all_active_clues,
                total_chapters=total_chapters,
                temperature=temperature
            )
            if next_chapter_guidance:
                print("下一章指导文字生成成功")
            else:
                print("下一章指导文字生成失败，将保存空值")
        except Exception as e:
            print(f"生成下一章指导文字时出错：{str(e)}")
    
    # 保存章节
    print("正在保存章节...")
    add_chapter(novel_id, chapter_number, chapter_title, chapter_content, next_chapter_guidance)
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
    
    # 记录使用统计
    try:
        duration = time.time() - start_time
        token_count = int(len(chapter_content) * 1.5)  # 估算 token 数量
        record_usage(
            event_type="generate_chapter",
            novel_id=novel_id,
            chapter_number=chapter_number,
            token_count=token_count,
            word_count=len(chapter_content),
            temperature=temperature,
            duration_seconds=duration
        )
        print(f"使用统计已记录：Token={token_count}, 字数={len(chapter_content)}, 耗时={duration:.2f}秒")
    except Exception as e:
        print(f"记录使用统计失败：{e}")
    
    return chapter_content, True

# 生成下一章指导文字的函数
def _generate_guidance_for_next_chapter(novel_title, novel_outline, current_chapter_number, current_chapter_content, active_clues, total_chapters, temperature):
    """
    生成下一章的指导文字
    
    Args:
        novel_title: 小说标题
        novel_outline: 小说大纲
        current_chapter_number: 当前章节编号
        current_chapter_content: 当前章节内容
        active_clues: 活跃线索列表
        total_chapters: 小说总章节数
        temperature: 生成温度
    """
    next_chapter_num = current_chapter_number + 1
    
    # 构建线索信息
    clues_text = ""
    if active_clues:
        clues_parts = []
        for clue in active_clues:
            if len(clue) >= 3:
                clue_text = clue[1]
                clue_type = clue[2]
                next_info = f"（预计在第{clue[4]}章再次出现）" if len(clue) > 4 and clue[4] else "（待收束）"
                clues_parts.append(f"- [{clue_type}] {clue_text} {next_info}")
        clues_text = '\n'.join(clues_parts)
    else:
        clues_text = "暂无活跃线索"
    
    prompt = f"""你是一位专业的小说编辑和指导者。请基于以下信息为第{next_chapter_num}章生成一段指导文字。

【小说信息】
- 小说标题：{novel_title}
- 当前章节：第{current_chapter_number}章
- 小说总章节数：{total_chapters}章

【当前章节内容（节选）】
{current_chapter_content[:1000] if current_chapter_content else '暂无内容'}

【小说总纲】
{novel_outline[:1000] if novel_outline else '暂无总纲'}

【活跃线索】
{clues_text}

【指导文字要求】
1. 分析当前章节的结局和遗留问题
2. 为下一章提供明确的方向和建议
3. 提示需要收束或发展的线索
4. 建议可能的情节发展方向
5. 保持与小说总纲的一致性
6. 语言简洁明了，重点突出
7. 不超过800字

请为第{next_chapter_num}章生成一段专业、实用的指导文字。"""
    
    try:
        response = client.generate(
            model=ollama_settings.model,
            prompt=prompt,
            options={"temperature": temperature, "max_tokens": 1500, "thinking": deepseek_settings.enable_thinking}
        )
        guidance = response.get("response", "").strip()
        return guidance if guidance else None
    except Exception as e:
        print(f"生成指导文字失败：{str(e)}")
        return None

# 生成章节的函数（流式输出版本）
def generate_chapter_streaming(novel_id, chapter_number, word_count, temperature, clue_threshold=3, additional_prompt="", retry_count=3, generate_next_chapter_guidance=False, previous_chapter_count=1):
    """
    流式输出版本的章节生成函数
    实时显示生成进度和章节内容
    
    Args:
        retry_count: 生成失败时的重试次数
        generate_next_chapter_guidance: 是否生成下一章指导文字
        previous_chapter_count: 传入历史章节数
    """
    start_time = time.time()
    
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    print(f"重试次数设置：{retry_count}")
    print(f"传入历史章节数：{previous_chapter_count}")
    
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
    
    # 获取历史章节内容和指导文字
    previous_chapters = []
    previous_chapter_guidance = None
    if chapter_number > 1:
        progress_text += f"正在获取历史章节内容...\n"
        yield progress_text
        
        conn = sqlite3.connect(db_settings.db_path)
        cursor = conn.cursor()
        
        start_chapter = max(1, chapter_number - previous_chapter_count)
        for ch_num in range(start_chapter, chapter_number):
            cursor.execute(f"""
            SELECT content, next_chapter_guidance FROM {db_settings.chapter_table} WHERE novel_id = ? AND chapter_number = ?
            """, (novel_id, ch_num))
            chapter_data = cursor.fetchone()
            if chapter_data:
                previous_chapters.append({
                    'chapter_number': ch_num,
                    'content': chapter_data[0],
                    'guidance': chapter_data[1]
                })
                progress_text += f"已获取第{ch_num}章内容（长度：{len(chapter_data[0])}字）\n"
                if chapter_data[1]:
                    progress_text += f"第{ch_num}章指导文字长度：{len(chapter_data[1])}字\n"
        
        conn.close()
        
        if previous_chapters and previous_chapters[-1]['guidance']:
            previous_chapter_guidance = previous_chapters[-1]['guidance']
            progress_text += f"已获取最新章指导文字\n"
        
        if not previous_chapters:
            progress_text += f"警告：未找到第 {start_chapter}-{chapter_number - 1} 章的记录\n"
            yield progress_text
    
    # 获取小说的线索
    progress_text += "正在获取小说线索...\n"
    yield progress_text
    
    clues = get_novel_clues(novel_id)
    active_clues = []
    for clue in clues:
        clue_id, clue_text, clue_type, first_chapter, next_chapter = clue
        # 只激活应该在当前章节出现的线索（next_chapter == chapter_number）
        # 或者首次出现且还未安排下次出现的线索
        if next_chapter == chapter_number or (next_chapter is None and first_chapter <= chapter_number):
            active_clues.append((clue_id, clue_text, clue_type, first_chapter))
    
    if active_clues:
        progress_text += f"找到 {len(active_clues)} 个活跃线索\n"
        yield progress_text
    else:
        progress_text += "当前没有需要激活的线索\n"
        yield progress_text
    
    # 构建系统提示
    system_prompt = f"你是一位专业的小说作家，擅长根据大纲和历史章节生成新的章节。请根据以下信息生成第{chapter_number}章。\n"
    system_prompt += f"小说标题：{novel_title}\n"
    system_prompt += f"小说大纲：{outline}\n"
    
    if previous_chapters:
        system_prompt += "\n【历史章节内容】\n"
        for ch_data in previous_chapters:
            ch_num = ch_data['chapter_number']
            ch_content = ch_data['content']
            system_prompt += f"第{ch_num}章:\n{ch_content}\n\n"
        if previous_chapter_guidance:
            system_prompt += f"【最新章指导文字】\n{previous_chapter_guidance}\n"
            progress_text += f"[调试] 系统提示中已包含最新章指导文字\n"
        else:
            progress_text += f"[调试] 系统提示中将不包含指导文字\n"
    else:
        system_prompt += f"【上一章内容】\n这是第一章，无上一章内容\n"
        progress_text += f"[调试] 系统提示中将不包含历史章节内容（这是第一章）\n"
    
    yield progress_text
    
    # 添加线索信息（仅在有线索时提供，让 AI 自主决定是否使用）
    if active_clues:
        system_prompt += "\n【可选择的线索】（注意：这些线索仅供参考，请根据情节需要自然融入，不必强制使用所有线索）\n"
        for _, clue_text, clue_type, first_chapter in active_clues:
            system_prompt += f"- {clue_type}：{clue_text}（首次出现于第{first_chapter}章）\n"
        system_prompt += """
【线索使用说明】
- 请根据当前章节的情节发展，自然选择是否需要使用这些线索
- 如果情节需要，可以巧妙地将线索融入章节内容中
- 如果不需要使用线索，也完全没问题，请按照正常情节发展撰写
- 如果使用了某个线索，请在章节内容的第二行单独输出数字 1
- 如果没有使用任何线索，请在章节内容的第二行单独输出数字 0
"""
    
    # 添加章节数和阈值信息
    if total_chapters:
        system_prompt += f"\n小说总章节数：{total_chapters}章\n"
        system_prompt += f"当前是第{chapter_number}章\n"
        # 检查是否接近结尾
        if total_chapters - chapter_number <= clue_threshold:
            system_prompt += f"注意：已接近小说结尾（剩余{total_chapters - chapter_number}章），请适当收束线索。\n"
    
    system_prompt += f"\n要求：\n"
    system_prompt += f"1. 第一行为章节标题（格式：第{chapter_number}章 XXX）\n"
    system_prompt += f"2. 第二行为线索使用标记：1（使用了线索）或 0（未使用线索）\n"
    system_prompt += f"3. 第三行开始为正文内容\n"
    system_prompt += f"4. 字数约{word_count}字\n"
    system_prompt += f"5. 风格保持一致，情节连贯\n"
    system_prompt += f"6. 禁用所有的 markdown 格式\n"
    system_prompt += f"7. 禁止其他所有的输出，只输出章节内容\n"
    system_prompt += f"8. **重要：不要在章节末尾重复前面的内容，每段内容都应该是新的情节发展**\n"
    system_prompt += f"9. **重要：当达到目标字数后，自然结束章节，不要为了凑字数而重复**"
    
    # 添加用户的附加提示词
    if additional_prompt:
        system_prompt += f"\n\n【用户附加要求】\n{additional_prompt}"
    
    # 生成章节（带重试逻辑）
    progress_text += f"正在生成第{chapter_number}章...\n"
    progress_text += f"最大重试次数：{retry_count}\n"
    progress_text += "=== 生成开始 ===\n"
    yield progress_text
    
    chapter_content = None
    last_error = None
    success = False
    
    for attempt in range(retry_count):
        if attempt > 0:
            progress_text += f"\n第{attempt}次重试生成...\n"
            yield progress_text
        
        try:
            response = client.generate(
                model=ollama_settings.model,
                prompt=system_prompt,
                options={"temperature": temperature, "max_tokens": word_count * token_settings.token_coefficient_chapter, "thinking": deepseek_settings.enable_thinking}
            )
            
            # 处理响应内容
            chapter_content = response["response"]
            
            # 检测并删除末尾重复内容
            chapter_content = remove_duplicate_content(chapter_content)
            
            # 验证生成内容的有效性
            lines = chapter_content.split('\n')
            content_text = '\n'.join(lines[2:]).strip() if len(lines) > 2 else ""
            
            if content_text and len(content_text) >= 50:
                success = True
                progress_text += f"\n第{attempt + 1}次尝试生成成功\n"
                yield progress_text
                break
            else:
                last_error = f"生成内容过短（{len(content_text)}字），可能是生成失败"
                progress_text += f"\n生成内容无效（长度：{len(content_text)}），准备重试...\n"
                yield progress_text
                
        except Exception as e:
            last_error = str(e)
            progress_text += f"\n生成出错：{last_error}\n"
            yield progress_text
    
    if not success:
        error_text = f"生成章节失败：经过{retry_count}次尝试后仍然失败\n"
        if last_error:
            error_text += f"最后错误：{last_error}\n"
        yield error_text
        return
    
    # 继续处理成功的响应
    # 提取章节标题和线索标记
    chapter_title = f"第{chapter_number}章"
    lines = chapter_content.split('\n')
    clue_marker = 0  # 线索使用标记：0=未使用，1=使用了紧急线索，2=使用了可选线索
    
    # 查找章节标题行
    title_line_idx = 0
    for i, line in enumerate(lines):
        if line.startswith(f"第{chapter_number}章"):
            chapter_title = line.strip()
            title_line_idx = i
            break
    
    # 检查第二行是否为线索标记（1、2 或 0）
    clue_marker_line = title_line_idx + 1
    if clue_marker_line < len(lines):
        marker = lines[clue_marker_line].strip()
        if marker in ['1', '2', '0']:
            clue_marker = int(marker)
            marker_descriptions = {1: "使用了紧急线索", 2: "使用了可选线索", 0: "未使用线索"}
            progress_text += f"\n检测到线索使用标记：{marker}（{marker_descriptions[clue_marker]}）\n"
            yield progress_text
    
    # 规范输出格式，确保章节内容第一行为章节名，第二行为线索标记
    formatted_content = f"{chapter_title}\n"
    formatted_content += f"{clue_marker}\n"
    
    # 跳过标题行和线索标记行
    skip_lines = title_line_idx + 1
    if skip_lines < len(lines) and lines[skip_lines].strip() in ['0', '1', '2']:
        skip_lines += 1
    
    # 添加章节内容（从第三行开始）
    formatted_content += '\n'.join(lines[skip_lines:])
    chapter_content = formatted_content
    
    # 验证生成内容的有效性
    content_text = '\n'.join(lines[skip_lines:]).strip()
    if not content_text or len(content_text) < 50:  # 内容太短，可能是生成失败
        progress_text += f"\n错误：第{chapter_number}章生成失败：内容过短或为空，请重试\n"
        yield progress_text
        return
    
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
    
    # 生成下一章指导文字（如果需要）
    next_chapter_guidance = None
    if generate_next_chapter_guidance:
        progress_text += "\n正在生成下一章指导文字...\n"
        yield progress_text
        try:
            next_chapter_guidance = _generate_guidance_for_next_chapter(
                novel_title=novel_title,
                novel_outline=outline,
                current_chapter_number=chapter_number,
                current_chapter_content=chapter_content,
                active_clues=active_clues,
                total_chapters=total_chapters,
                temperature=temperature
            )
            if next_chapter_guidance:
                progress_text += "下一章指导文字生成成功\n"
            else:
                progress_text += "下一章指导文字生成失败，将保存空值\n"
        except Exception as e:
            progress_text += f"生成下一章指导文字时出错：{str(e)}\n"
        yield progress_text
    
    # 保存章节
    print("正在保存章节...")
    add_chapter(novel_id, chapter_number, chapter_title, chapter_content, next_chapter_guidance)
    progress_text += "\n章节已保存到数据库\n"
    yield progress_text
    
    # 根据线索使用标记处理线索
    if clue_marker == 1:
        # 使用了紧急线索，删除所有紧急线索
        progress_text += "\n检测到紧急线索被使用，正在删除已使用的紧急线索...\n"
        yield progress_text
        for clue_id, clue_text, clue_type, first_chapter, next_chapter in urgent_clues:
            # 删除已使用的线索
            from database import delete_clue
            delete_clue(clue_id)
            progress_text += f"已删除紧急线索：{clue_text[:20]}...\n"
            yield progress_text
        
        # 可选线索未被使用，更新下次出现时间
        if active_clues:
            progress_text += "\n可选线索未被使用，正在更新线索信息...\n"
            yield progress_text
            for clue_id, _, _, first_chapter, _ in active_clues:
                chapters_passed = chapter_number - first_chapter
                if chapters_passed > 0:
                    avg_interval = max(1, (total_chapters - first_chapter) // 3)
                    next_chapter_estimate = chapter_number + avg_interval
                    next_chapter_estimate = min(next_chapter_estimate, total_chapters)
                    update_clue_next_chapter(clue_id, next_chapter_estimate)
            progress_text += "线索信息更新完成\n"
            yield progress_text
            
    elif clue_marker == 2:
        # 只使用了可选线索，删除被使用的可选线索（这里简化处理，删除所有可选线索）
        progress_text += "\n检测到可选线索被使用，正在删除已使用的可选线索...\n"
        yield progress_text
        for clue_id, clue_text, clue_type, first_chapter, _ in active_clues:
            from database import delete_clue
            delete_clue(clue_id)
            progress_text += f"已删除可选线索：{clue_text[:20]}...\n"
            yield progress_text
        
        # 紧急线索需要重新安排
        if urgent_clues:
            progress_text += "\n紧急线索未被使用，将重新安排出现时间...\n"
            yield progress_text
            for clue_id, _, _, first_chapter, _ in urgent_clues:
                chapters_passed = chapter_number - first_chapter
                if chapters_passed > 0:
                    avg_interval = max(1, (total_chapters - first_chapter) // 3)
                    next_chapter_estimate = chapter_number + avg_interval
                    next_chapter_estimate = min(next_chapter_estimate, total_chapters)
                    update_clue_next_chapter(clue_id, next_chapter_estimate)
            progress_text += "线索信息更新完成\n"
            yield progress_text
            
    else:
        # 未使用任何线索，更新所有线索的下次出现时间
        if all_active_clues:
            progress_text += "\n线索未被使用，正在更新线索信息...\n"
            yield progress_text
            for clue_id, _, _, first_chapter, _ in all_active_clues:
                chapters_passed = chapter_number - first_chapter
                if chapters_passed > 0:
                    avg_interval = max(1, (total_chapters - first_chapter) // 3)
                    next_chapter_estimate = chapter_number + avg_interval
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
    
    # 添加下一章指导文字（如果有）
    if next_chapter_guidance:
        progress_text += f"\n=== 第{chapter_number + 1}章指导文字 ===\n{next_chapter_guidance}\n"
    
    # 记录使用统计
    try:
        duration = time.time() - start_time
        token_count = int(len(chapter_content) * 1.5)  # 估算 token 数量
        record_usage(
            event_type="generate_chapter",
            novel_id=novel_id,
            chapter_number=chapter_number,
            token_count=token_count,
            word_count=len(chapter_content),
            temperature=temperature,
            duration_seconds=duration
        )
        print(f"使用统计已记录：Token={token_count}, 字数={len(chapter_content)}, 耗时={duration:.2f}秒")
    except Exception as e:
        print(f"记录使用统计失败：{e}")
    
    yield progress_text, True

# 检测并删除重复内容的函数
def remove_duplicate_content(content, min_repeat_sentences=3):
    """
    检测并删除章节末尾的重复句子
    
    Args:
        content: 章节内容
        min_repeat_sentences: 最小重复次数（同一句子重复多少次才认为是重复）
    
    Returns:
        删除重复后的内容
    """
    if not content:
        return content
    
    lines = content.split('\n')
    
    # 跳过标题行和线索标记行
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith(f"第") and "章" in line:
            start_idx = i + 1
            # 检查下一行是否为线索标记
            if i + 1 < len(lines) and lines[i + 1].strip() in ['0', '1']:
                start_idx = i + 2
            break
    
    # 只处理正文内容
    body_lines = lines[start_idx:]
    
    if len(body_lines) < 3:  # 内容太短，不需要处理
        return content
    
    # 将正文合并后按句子分割（中文句号、问号、感叹号）
    full_text = '\n'.join(body_lines)
    
    # 按句子分隔符分割
    import re
    sentences = re.split(r'([。！？!?])', full_text)
    
    # 重组句子（将分隔符加回）
    reconstructed_sentences = []
    for i in range(0, len(sentences), 2):
        sentence = sentences[i].strip()
        if sentence:
            if i + 1 < len(sentences):
                reconstructed_sentences.append(sentence + sentences[i])
            else:
                reconstructed_sentences.append(sentence)
    
    if len(reconstructed_sentences) < 5:  # 句子太少，不需要处理
        return content
    
    # 检查最后几个句子是否重复
    last_sentence = reconstructed_sentences[-1]
    repeat_count = 1
    
    # 从后往前数，看有多少个相同的句子
    for i in range(len(reconstructed_sentences) - 2, -1, -1):
        if reconstructed_sentences[i].strip() == last_sentence.strip():
            repeat_count += 1
        else:
            break
    
    # 如果最后一句重复超过阈值，删除重复部分
    if repeat_count >= min_repeat_sentences:
        # 保留非重复的句子
        non_repeat_sentences = reconstructed_sentences[:-repeat_count]
        
        # 重建内容
        result_text = ''.join(non_repeat_sentences)
        
        print(f"检测到末尾句子重复 {repeat_count} 次，已删除重复部分")
        print(f"重复的句子：{last_sentence[:50]}...")
        
        # 重新格式化为多行
        result_lines = lines[:start_idx] + [result_text]
        return '\n'.join(result_lines)
    
    return content


# 从章节内容中提取线索的函数
def extract_clues_from_chapter(chapter_content, chapter_number, novel_outline, total_chapters, clue_count=2):
    """
    使用 AI 从章节内容中逐条提取线索，并根据大纲推测预计出现章节数
    每次生成时传入已生成的线索，避免重复
    """
    try:
        # 输入验证
        if not chapter_content or not isinstance(chapter_content, str):
            print("[线索提取] 章节内容为空或类型不正确")
            return []
        
        print(f"[线索提取] 开始提取线索，目标数量：{clue_count}")
        print(f"[线索提取] 章节内容长度：{len(chapter_content)}字")
        print(f"[线索提取] 大纲长度：{len(novel_outline) if novel_outline else 0}字")
        
        clues = []
        
        for clue_index in range(clue_count):
            print(f"\n[线索提取] 开始生成第 {clue_index + 1} 条线索...")
            
            # 构建已生成线索的描述
            existing_clues_text = ""
            if clues:
                existing_clues_text = "\n【本章已生成的线索】（请避免重复）\n"
                for i, (clue_text, clue_type, first_chapter, next_chapter) in enumerate(clues):
                    existing_clues_text += f"{i + 1}. 类型：{clue_type}\n"
                    existing_clues_text += f"   内容：{clue_text}\n"
                    if next_chapter:
                        existing_clues_text += f"   预计回收章节：第{next_chapter}章\n"
                existing_clues_text += "\n"
            
            # 构建系统提示，要求逐条生成
            system_prompt = (
                f"你是一位专业的小说编辑，擅长从小说章节中识别和提取线索，以供后面的生成使用。不是续写，也不是总结，只是提取线索。\n"
                f"请根据提供的章节内容、小说大纲和总章节数，提取 1 条重要的线索。回收章节为预计何时续上这个线索的章节号。\n\n"
                f"【输出格式要求】\n"
                f"必须严格按照以下三行格式输出，不要有任何其他内容：\n"
                f"类型：明潮（或暗涌）\n"
                f"回收章节：X（X为预计下次出现的章节数字）\n"
                f"内容：线索的简要描述（30-100个汉字）\n"
                f"【注意事项】\n"
                f"1. 类型只能是「明潮」或「暗涌」二选一，不要用英文或其他词汇。\n"
                f"2. 「回收章节」必须是阿拉伯数字，表示预计这条线索下次会出现的章节号。\n"
                f"   - 回收章节必须大于当前章节，不能是本章或之前的章节。\n"
                f"   - 回收章节不能超过小说总章节数。\n"
                f"   - 请根据小说大纲和情节发展，合理推测线索的回收时机。\n"
                f"3. 线索内容必须简洁明确，30-100个汉字。\n"
                f"4. 只输出这三行，禁止输出任何其他内容、标题、解释或英文单词。\n"
            )
            
            # 用户提示，包含章节内容、大纲和总章节数
            user_prompt = (
                f"【当前章节内容】\n{chapter_content[:3000]}\n\n"
                f"【小说大纲】\n{novel_outline[:2000]}\n\n"
                f"【当前章节号】{chapter_number}\n"
                f"【小说总章节数】{total_chapters if total_chapters else '未知'}"
            )
            if existing_clues_text:
                user_prompt += f"\n{existing_clues_text}"
            
            # 调用 AI 生成单条线索
            print("[线索提取] 调用 AI 生成线索...")
            try:
                response = client.chat(
                    model=ollama_settings.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    stream=False,
                    think=False,  # 禁用思考模式
                    options={
                        "temperature": 0.6,
                        "num_predict": 500,
                    }
                )
                
                # 获取响应内容
                if hasattr(response, 'message') and response.message:
                    ai_response = response.message.content
                elif isinstance(response, dict):
                    ai_response = response.get('message', {}).get('content', '')
                else:
                    print(f"[线索提取] 未知响应格式：{type(response)}")
                    ai_response = ''
                
                # 过滤掉思考过程
                if ai_response:
                    # 方法1：过滤 <think> 标签内容
                    import re
                    think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)
                    ai_response = think_pattern.sub('', ai_response).strip()
                    
                    # 方法2：过滤 "思考过程" 等关键词开头的内容
                    if 'Thinking Process:' in ai_response or '思考过程' in ai_response:
                        parts = ai_response.split('\n\n', 1)
                        if len(parts) > 1:
                            ai_response = parts[1].strip()
                
                print(f"[线索提取] AI 响应长度：{len(ai_response)}字")
                print(f"[线索提取] AI 响应预览：\n{ai_response[:200]}")
            except Exception as api_error:
                print(f"[线索提取] API 调用异常：{str(api_error)}")
                import traceback
                traceback.print_exc()
                break  # 如果 API 出错，停止生成后续线索
            
            # 解析响应
            import re
            clue_type = None
            next_chapter = None
            clue_text = None
            
            lines = ai_response.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 匹配类型行
                if line.startswith('类型：') or line.startswith('类型:'):
                    clue_type_raw = line.split('：' if '：' in line else ':', 1)[1].strip()
                    if '明潮' in clue_type_raw:
                        clue_type = '明潮'
                    elif '暗涌' in clue_type_raw:
                        clue_type = '暗涌'
                    else:
                        clue_type = '明潮'  # 默认
                
                # 匹配回收章节行
                elif line.startswith('回收章节：') or line.startswith('回收章节:'):
                    try:
                        next_chapter_str = line.split('：' if '：' in line else ':', 1)[1].strip()
                        # 提取数字
                        num_match = re.search(r'(\d+)', next_chapter_str)
                        if num_match:
                            next_chapter = int(num_match.group(1))
                            # 验证章节号合理性
                            if next_chapter <= chapter_number:
                                next_chapter = chapter_number + 1
                            if total_chapters and next_chapter > total_chapters:
                                next_chapter = total_chapters
                    except (ValueError, IndexError):
                        pass
                
                # 匹配内容行
                elif line.startswith('内容：') or line.startswith('内容:'):
                    clue_text = line.split('：' if '：' in line else ':', 1)[1].strip()
                    clue_text = clue_text.rstrip('。').strip()
            
            # 验证并保存线索
            if clue_type and clue_text and len(clue_text) >= 5:
                clues.append((clue_text, clue_type, chapter_number, next_chapter))
                print(f"[线索提取] 成功提取第 {clue_index + 1} 条线索：")
                print(f"  - 类型：{clue_type}")
                print(f"  - 回收章节：{'第' + str(next_chapter) + '章' if next_chapter else '未指定'}")
                print(f"  - 内容：{clue_text}")
            else:
                print(f"[线索提取] 第 {clue_index + 1} 条线索解析失败，跳过...")
                print(f"  - clue_type: {clue_type}")
                print(f"  - clue_text: {clue_text}")
        
        print(f"\n[线索提取] 提取完成，共 {len(clues)} 条线索")
        return clues
    except Exception as e:
        print(f"提取线索时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return []

# 压缩生成章节的函数（基于前文压缩）
def generate_chapter_with_compression(novel_id, chapter_number, word_count, temperature, 
                                      compression_threshold=None, keep_recent_chapters=None):
    """
    基于上下文压缩的章节生成方法
    当章节数超过阈值时，对前文进行压缩后输入到后文生成
    
    参数：
    - novel_id: 小说 ID
    - chapter_number: 当前章节编号
    - word_count: 目标字数
    - temperature: 生成温度
    - compression_threshold: 压缩阈值（超过多少章后开始压缩）
    - keep_recent_chapters: 保留最近多少章的详细内容
    - chapter_outline: 章节大纲（可选）
    """
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    
    if not novel_id:
        return "无效的小说 ID"
    
    # 使用默认设置如果未指定
    if compression_threshold is None:
        compression_threshold = compression_settings.default_compression_threshold
    if keep_recent_chapters is None:
        keep_recent_chapters = compression_settings.default_keep_recent_chapters
    
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
    
    # 如果没有提供章节大纲，尝试从数据库获取
    if chapter_outline is None:
        from database import get_chapter_outline
        outline_data = get_chapter_outline(novel_id, chapter_number)
        if outline_data:
            chapter_outline = outline_data[1]
            print(f"已加载第{chapter_number}章大纲")
    
    # 获取所有已有章节
    print("正在获取已有章节...")
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT chapter_number, content, next_chapter_guidance FROM {db_settings.chapter_table} 
    WHERE novel_id = ? 
    ORDER BY chapter_number
    """, (novel_id,))
    all_chapters = cursor.fetchall()
    conn.close()
    
    # 构建上下文
    context = ""
    needs_compression = len(all_chapters) >= compression_threshold
    
    if needs_compression:
        print(f"章节数已达到{len(all_chapters)}，超过阈值{compression_threshold}，开始压缩前文...")
        
        # 分离保留章节和需要压缩的章节
        recent_chapters = all_chapters[-keep_recent_chapters:]
        old_chapters = all_chapters[:-keep_recent_chapters]
        
        # 压缩旧章节
        compressed_summary = compress_previous_chapters(
            novel_id, old_chapters, recent_chapters, 
            chapter_number, outline, temperature
        )
        
        context += "=== 前文摘要 ===\n"
        context += compressed_summary + "\n\n"
        
        # 添加保留的近期章节
        if recent_chapters:
            context += "=== 近期章节（详细内容） ===\n"
            for ch_num, ch_content, ch_guidance in recent_chapters:
                context += f"第{ch_num}章:\n{ch_content}\n"
                if ch_guidance:
                    context += f"指导文字：{ch_guidance}\n\n"
                else:
                    context += "\n"
    else:
        # 章节数较少，直接使用所有章节
        if all_chapters:
            context += "=== 前文章节 ===\n"
            for ch_num, ch_content, ch_guidance in all_chapters:
                context += f"第{ch_num}章:\n{ch_content}\n"
                if ch_guidance:
                    context += f"指导文字：{ch_guidance}\n\n"
                else:
                    context += "\n"
    
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
    system_prompt = f"你是一位专业的小说作家，擅长根据大纲和前文内容生成新的章节。请根据以下信息生成第{chapter_number}章。\n"
    system_prompt += f"小说标题：{novel_title}\n"
    system_prompt += f"小说大纲：{outline}\n"
    
    # 添加上下文（压缩后的或直接的前文）
    if context:
        system_prompt += f"\n前文内容：\n{context}\n"
    
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
        if total_chapters - chapter_number <= 3:
            system_prompt += f"注意：已接近小说结尾（剩余{total_chapters - chapter_number}章），请适当收束线索。\n"
    
    system_prompt += f"\n要求：\n"
    system_prompt += f"1. 第一行为章节标题\n"
    system_prompt += f"2. 接下来为正文内容\n"
    system_prompt += f"3. 字数约{word_count}字\n"
    system_prompt += f"4. 风格保持一致，情节连贯\n"
    system_prompt += f"5. 禁用所有的 markdown 格式\n"
    system_prompt += f"6. 禁止其他所有的输出，只输出章节内容"
    
    # 生成章节
    print(f"正在生成第{chapter_number}章...")
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
    
    # 验证生成内容的有效性
    content_text = '\n'.join(lines[skip_lines:]).strip()
    if not content_text or len(content_text) < 50:  # 内容太短，可能是生成失败
        return f"第{chapter_number}章生成失败：内容过短或为空，请重试"
    
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
    
    # 根据线索使用标记处理线索
    if clue_used and active_clues:
        print("检测到线索被使用，正在删除已使用的线索...")
        for clue_id, clue_text, clue_type, first_chapter in active_clues:
            # 删除已使用的线索
            from database import delete_clue
            delete_clue(clue_id)
            print(f"已删除线索：{clue_text[:20]}...")
    elif active_clues:
        # 线索未被使用，更新下次出现时间
        print("线索未被使用，正在更新线索信息...")
        for clue_id, _, _, first_chapter in active_clues:
            # 预估下次线索出现的章节
            # 基于线索首次出现的章节和总章节数
            chapters_passed = chapter_number - first_chapter
            if chapters_passed > 0:
                # 简单算法：平均间隔章节数
                avg_interval = max(1, (total_chapters - first_chapter) // 3)  # 假设线索出现 3 次
                next_chapter_estimate = chapter_number + avg_interval
                # 确保不超过总章节数
                next_chapter_estimate = min(next_chapter_estimate, total_chapters)
                update_clue_next_chapter(clue_id, next_chapter_estimate)
        print("线索信息更新完成")
    
    # 返回章节内容和一个标志，表示生成成功
    print("章节生成完成！")
    return chapter_content, True

# 压缩前文章节的函数
def compress_previous_chapters(novel_id, old_chapters, recent_chapters, 
                               current_chapter_number, novel_outline, temperature):
    """
    使用 AI 对旧章节进行压缩摘要
    
    参数：
    - novel_id: 小说 ID
    - old_chapters: 需要压缩的旧章节列表 [(chapter_number, content), ...]
    - recent_chapters: 保留的近期章节列表
    - current_chapter_number: 当前章节编号
    - novel_outline: 小说大纲
    - temperature: 生成温度
    """
    if not old_chapters:
        return "无需要压缩的前文"
    
    # 构建压缩请求
    old_chapters_text = ""
    for ch_num, ch_content, ch_guidance in old_chapters:
        old_chapters_text += f"第{ch_num}章:\n{ch_content}\n"
        if ch_guidance:
            old_chapters_text += f"指导文字：{ch_guidance}\n\n"
        else:
            old_chapters_text += "\n"
    
    system_prompt = f"""你是一位专业的小说编辑，擅长对小说章节进行压缩摘要。请对以下旧章节内容进行压缩，提取关键情节、角色发展和重要线索。

要求：
1. 保留主要情节发展和转折点
2. 保留重要角色的关键行为和成长
3. 保留所有重要线索和伏笔
4. 按章节顺序组织摘要
5. 语言简洁，但保持故事连贯性
6. 禁用 markdown 格式
7. 只输出摘要内容，不输出其他说明

旧章节内容：
{old_chapters_text}

请生成一个连贯的摘要，能够让人理解故事的前因后果。"""

    try:
        response = client.generate(
            model=ollama_settings.model,
            prompt=system_prompt,
            options={"temperature": temperature, "max_tokens": 2000, "thinking": deepseek_settings.enable_thinking}
        )
        
        summary = response["response"]
        if not summary:
            # 如果压缩失败，返回简化版本
            summary = "前文章节摘要：\n"
            for ch_num, ch_content, _ in old_chapters:
                # 简单提取每章的前 200 字
                first_part = ch_content[:200].strip()
                summary += f"第{ch_num}章：{first_part}...\n"
        
        return summary
    except Exception as e:
        print(f"压缩前文时出错：{str(e)}")
        # 返回简化版本
        summary = "前文章节摘要：\n"
        for ch_num, ch_content, _ in old_chapters:
            first_part = ch_content[:200].strip()
            summary += f"第{ch_num}章：{first_part}...\n"
        return summary

# 批量压缩生成章节的函数
def batch_generate_chapters_with_compression(novel_id, start_chapter, batch_count, word_count, 
                                              temperature, compression_threshold, keep_recent_chapters,
                                              error_handling="❌ 停止生成"):
    """
    批量生成章节，使用压缩方法
    
    参数：
    - novel_id: 小说 ID
    - start_chapter: 起始章节编号
    - batch_count: 批量生成数量
    - word_count: 每章字数
    - temperature: 生成温度
    - compression_threshold: 压缩阈值
    - keep_recent_chapters: 保留最近章节数
    - error_handling: 错误处理方式
    """
    # 确保 novel_id 是整数
    print(f"处理小说选择值：{novel_id}")
    print(f"错误处理方式：{error_handling}")
    print(f"批量生成参数：起始章节={start_chapter}, 数量={batch_count}")
    
    if not novel_id:
        return "无效的小说 ID"
    
    # 获取小说信息（大纲和总章节数）
    print("正在获取小说信息...")
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
    
    # 获取章节大纲
    print("正在获取章节大纲...")
    chapter_outlines_map = {}
    for i in range(start_chapter, start_chapter + batch_count):
        outline_data = get_chapter_outline(novel_id, i)
        if outline_data:
            chapter_outlines_map[i] = {
                'title': outline_data[0],
                'outline': outline_data[1]
            }
            print(f"第{i}章大纲已加载：{outline_data[0]}")
    
    # 批量生成章节
    generated_chapters = []
    failed_chapters = []
    skipped_chapters = []
    retry_attempts = 3  # 重试次数
    
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
            result = generate_chapter_with_compression(
                novel_id, current_chapter, word_count, temperature,
                compression_threshold, keep_recent_chapters,
                chapter_outlines_map.get(current_chapter, {}).get('outline')
            )
            
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
            # 保存章节到数据库
            try:
                conn = sqlite3.connect(db_settings.db_path)
                cursor = conn.cursor()
                cursor.execute(f"""
                INSERT INTO {db_settings.chapter_table} (novel_id, chapter_number, content, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """, (novel_id, current_chapter, chapter_content))
                conn.commit()
                conn.close()
                
                generated_chapters.append(current_chapter)
                print(f"第{current_chapter}章生成并保存成功")
                
            except Exception as e:
                print(f"保存第{current_chapter}章到数据库失败：{e}")
                if error_handling == "⏭️ 跳过错误章节":
                    skipped_chapters.append(current_chapter)
                elif error_handling == "❌ 停止生成":
                    return f"保存第{current_chapter}章失败：{e}"
                
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
                            cursor.execute(f"""
                            INSERT INTO {db_settings.chapter_table} (novel_id, chapter_number, content, created_at)
                            VALUES (?, ?, ?, datetime('now'))
                            """, (novel_id, current_chapter, previous_content[0]))
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
