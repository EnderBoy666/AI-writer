import requests
import os
import datetime
import re,json

from settings import OpenaiSettings,WebSettings
web_settings=WebSettings()
openai_settings=OpenaiSettings()

def filter_think_tags(text: str) -> str:
    """
    过滤 <think>...</think> 标签及其内部的所有内容
    支持：单行、多行、大小写不敏感、标签带属性（如 <think class="x">）
    """
    # 正则表达式：匹配 <think ...> 到 </think> 之间所有内容
    if(web_settings.debug==True):
        print(f"[{datetime.datetime.now()}]AI 响应内容:\n{text}")
    pattern = re.compile(r'<think.*?>.*?</think>', re.DOTALL | re.IGNORECASE)
    return pattern.sub('', text)

def generate(prompts, user, max_token, tool, thinking_budget=None, max_thinking_tokens=None):
    ai_json={
            "model": openai_settings.model,
            "messages": [{"role": user, "content": prompts}],
            "max_completion_tokens":max_token,
            "frequency_penalty":openai_settings.frequency_penalty
        }
    
    # 添加思考参数（如果启用）
    if openai_settings.enable_thinking:
        thinking_params = {}
        if thinking_budget is not None:
            thinking_params["thinking_budget"] = thinking_budget
        else:
            thinking_params["thinking_budget"] = openai_settings.thinking_budget
        
        if max_thinking_tokens is not None:
            thinking_params["max_thinking_tokens"] = max_thinking_tokens
        else:
            thinking_params["max_thinking_tokens"] = openai_settings.max_thinking_tokens
        
        # 将思考参数添加到请求中（根据 API 格式调整）
        ai_json["thinking"] = thinking_params
    
    if(len(tool)!=0):
        ai_json["tools"]=tool
        ai_json["tool_choices"]="auto"
    x = requests.post(
        url=f"{openai_settings.url}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_settings.api_key}"
        },
        json=ai_json,
        timeout=openai_settings.timeout
    )
    if(x.json()["choices"][0]["message"]["content"]==""):
        print(f"[{datetime.datetime.now}]警告：AI 返回值为空，即将重试。最大 token:{max_token}")
        for i in range(openai_settings.retry):
            ai_json["max_completion_tokens"]+=openai_settings.add_token
            x = requests.post(
                url=f"{openai_settings.url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_settings.api_key}"
                },
                json=ai_json,
                timeout=openai_settings.timeout
            )
            if(x.json()["choices"][0]["message"]["content"]==""):
                print(f"[{datetime.datetime.now()}]警告：AI 返回值为空，已重试{i+1}/{openai_settings.retry}。最大 token:{max_token}")
            else:
                break
    if x.status_code == 200:
        if(len(tool)!=0):
            #处理工具调用
            choice = x.json()["choices"][0]
            if choice.get("finish_reason") == "tool_calls":
                tool_calls = choice["message"]["tool_calls"]
                # 添加工具调用结果到消息历史
                ai_json["messages"].append({
                    "role": "assistant",
                    "tool_calls": tool_calls
                })
                for tool_call in tool_calls:
                    function_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                    tool_call_id = tool_call["id"]
                    # 执行真实函数
                    if function_name == "get_chapter":
                        result = get_chapter(novel_name=arguments.get("novel_name"),chapter_id=arguments.get("chapter_id"))
                    elif function_name == "get_chapter_outline":
                        result = get_chapter_outline(novel_name=arguments.get("novel_name"),chapter_outline_id=arguments.get("chapter_outline_id"))
                    else:
                        result = f"错误：未知的函数名 {function_name}"
                    print(f"[{datetime.datetime.now()}]:调用工具： {function_name} 参数：{arguments} 返回：{result}")
                    # 将工具调用结果添加回消息
                    ai_json["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                    })
                # 重新调用 AI 获取最终响应
                x = requests.post(
                    url=f"{openai_settings.url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {openai_settings.api_key}"
                    },
                    json=ai_json,
                    timeout=openai_settings.timeout
                )
        x.json()["choices"][0]["message"]["content"]=filter_think_tags(x.json()["choices"][0]["message"]["content"])
    return x

def check_file(path):
    if os.path.exists(path):
        return True
    else:
        return False
    
#工具类
def get_chapter(novel_name,chapter_id):
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    return novel_info["chapters"][chapter_id]

def get_chapter_outline(novel_name,chapter_outline_id):
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    return novel_info["outline"]["chapter_outline"][chapter_outline_id]["content"]

def search_chapters(novel_name,start_chapter,end_chapter,keyword=""):
    """搜索并压缩指定范围的章节内容"""
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    
    chapters = novel_info["chapters"]
    result = []
    
    for i in range(start_chapter, min(end_chapter + 1, len(chapters))):
        chapter = chapters[i]
        chapter_summary = {
            "chapter_id": i,
            "title": chapter.get("title", ""),
            "content_preview": chapter.get("content", "")[:500]  # 只返回前 500 字
        }
        if keyword == "" or keyword in chapter.get("content", ""):
            result.append(chapter_summary)
    
    return {
        "total_chapters": len(result),
        "chapters": result
    }

def get_entity_info(novel_name,entity_name):
    """获取实体的详细信息"""
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    
    entities = novel_info["outline"].get("enities", [])
    chapter_outlines = novel_info["outline"].get("chapter_outline", [])
    
    result = {
        "entity_name": entity_name,
        "description": "",
        "related_chapters": []
    }
    
    # 查找实体简介
    for i, entity in enumerate(entities):
        if entity_name in entity:
            result["description"] = entity
            # 查找相关章节
            for j, outline in enumerate(chapter_outlines):
                if isinstance(outline, dict):
                    if entity_name in str(outline.get("enities", [])):
                        result["related_chapters"].append(j)
                elif entity_name in str(outline):
                    result["related_chapters"].append(j)
    
    return result

def get_character_relations(novel_name,character_name):
    """获取特定角色的人物关系"""
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    
    total_outline = novel_info["outline"].get("total_outline", "")
    entities = novel_info["outline"].get("enities", [])
    
    result = {
        "character": character_name,
        "relations": [],
        "background": ""
    }
    
    # 从总纲和实体列表中提取关系信息
    for entity in entities:
        if character_name in entity and ":" in entity:
            result["background"] = entity
            break
    
    # 简化总纲中包含角色名的部分
    if character_name in total_outline:
        lines = total_outline.split("\n")
        for line in lines:
            if character_name in line and len(line) < 200:
                result["relations"].append(line)
    
    return result

def get_world_setting(novel_name,setting_type=""):
    """获取世界观设定信息"""
    with open(f"data/novels/{novel_name}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    
    total_outline = novel_info["outline"].get("total_outline", "")
    
    result = {
        "setting_type": setting_type if setting_type else "general",
        "content": ""
    }
    
    # 从总纲中提取世界观相关内容
    if setting_type == "":
        result["content"] = total_outline[:2000]  # 返回总纲的前 2000 字
    else:
        lines = total_outline.split("\n")
        matched_lines = []
        for line in lines:
            if setting_type in line:
                matched_lines.append(line)
        result["content"] = "\n".join(matched_lines)
    
    return result

# 多 Agent 协作相关函数
def plot_planner_agent(novel_info, chapter_num, word_count, extra_prompts, thinking_budget=None, max_thinking_tokens=None):
    """
    剧情规划师 Agent
    职责：规划本章剧情走向、关键情节点、人物出场等
    """
    chapter_outline_index = int((chapter_num - 1) / len(novel_info["outline"]["chapter_outline"]))
    current_outline = novel_info["outline"]["chapter_outline"][chapter_outline_index]
    if isinstance(current_outline, dict):
        current_outline = current_outline.get("content", "")
    
    # 提取总纲和实体信息
    total_outline = novel_info["outline"].get("total_outline", "")
    entities = novel_info["outline"].get("enities", [])
    entities_str = "\n".join(entities) if entities else "无"
    
    # 获取上一章内容（如果存在）
    if chapter_num > 1 and len(novel_info["chapters"]) >= chapter_num - 1:
        prev_chapter = novel_info["chapters"][chapter_num - 2]["content"][:1500]
        prev_chapter_title = novel_info["chapters"][chapter_num - 2]["title"]
    else:
        prev_chapter = "这是第一章，无上一章内容"
        prev_chapter_title = "无"
    
    prompts = f"""你是一名专业的剧情规划师。请为第{chapter_num}章规划详细的剧情大纲。

【重要背景信息】
总章节数：{novel_info["outline"]["total_chapters"]}
当前章节：第{chapter_num}章
字数要求：约{word_count}字

【小说总纲】（必须严格遵循）
{total_outline}

【实体列表】（出场人物、组织等）
{entities_str}

【当前章节大纲】
{current_outline}

【上一章内容摘要】
标题：{prev_chapter_title}
内容前 1500 字：{prev_chapter}

【用户附加提示词】
{extra_prompts}

【规划要求】
1. 必须严格遵循总纲设定，不能与总纲矛盾
2. 确保与上一章内容连贯，情节自然过渡
3. 规划 3-5 个关键情节点
4. 列出需要出场的人物及其作用（必须从实体列表中选择或合理新增）
5. 设计情节起伏和冲突点
6. 为后续章节埋下伏笔
7. 保持人物性格和行为的一致性

请以 JSON 格式输出规划结果，包含以下字段：
- plot_points: 关键情节点列表（每个情节点包含：标题、描述、涉及人物）
- characters: 出场人物列表（包含：姓名、作用、本章表现）
- conflicts: 冲突点列表（包含：冲突类型、参与方、解决方式）
- transition: 与上一章的衔接方式（如何承接上一章结尾）
- foreshadowing: 为后续章节埋下的伏笔
- consistency_check: 自我一致性检查（说明如何遵循总纲和保持连贯性）"""

    x = generate(prompts, "user", 12000, tool=[], thinking_budget=thinking_budget, max_thinking_tokens=max_thinking_tokens)
    if x.status_code == 200:
        return x.json()["choices"][0]["message"]["content"]
    else:
        return None

def content_creator_agent(novel_info, chapter_num, word_count, plot_plan, extra_prompts, max_token, thinking_budget=None, max_thinking_tokens=None):
    """
    内容创作者 Agent
    职责：根据剧情规划创作具体内容
    """
    chapter_outline_index = int((chapter_num - 1) / len(novel_info["outline"]["chapter_outline"]))
    current_outline = novel_info["outline"]["chapter_outline"][chapter_outline_index]
    if isinstance(current_outline, dict):
        current_outline = current_outline.get("content", "")
    
    # 提取总纲和实体信息
    total_outline = novel_info["outline"].get("total_outline", "")
    entities = novel_info["outline"].get("enities", [])
    entities_str = "\n".join(entities) if entities else "无"
    
    # 获取上一章内容（如果存在）
    if chapter_num > 1 and len(novel_info["chapters"]) >= chapter_num - 1:
        prev_chapter = novel_info["chapters"][chapter_num - 2]["content"][:2000]
        prev_chapter_title = novel_info["chapters"][chapter_num - 2]["title"]
    else:
        prev_chapter = "这是第一章，无上一章内容"
        prev_chapter_title = "无"
    
    prompts = f"""你是一名专业的小说家。请根据剧情规划创作第{chapter_num}章的内容。

【重要背景信息】
总章节数：{novel_info["outline"]["total_chapters"]}
当前章节：第{chapter_num}章
字数要求：约{word_count}字

【小说总纲】（创作的核心指导，必须严格遵循）
{total_outline}

【实体列表】（人物、组织等设定）
{entities_str}

【当前章节大纲】
{current_outline}

【上一章内容】
标题：{prev_chapter_title}
内容：{prev_chapter}

【剧情规划】（必须按照此规划进行创作）
{plot_plan}

【用户附加提示词】
{extra_prompts}

【创作要求】
1. 严格遵循剧情规划进行创作，不能偏离规划的核心情节点
2. 必须遵循总纲设定，人物性格、世界观、剧情走向都要与总纲一致
3. 确保与上一章内容自然衔接，情节连贯
4. 字数控制在{word_count}字左右
5. 输出格式：第一行为'第 x 章'：章节标题，随后是正文
6. 禁用 markdown 格式，直接输出流畅的文本
7. 注重细节描写和情感渲染
8. 保持叙事节奏和张弛有度
9. 人物对话要符合其性格和身份
10. 场景描写要符合世界观设定

【一致性保证】
- 人物行为必须符合其性格设定
- 剧情发展必须符合总纲走向
- 世界观设定必须前后一致
- 不能出现与之前章节矛盾的内容

请开始创作："""

    x = generate(prompts, "user", max_token, tool=[], thinking_budget=thinking_budget, max_thinking_tokens=max_thinking_tokens)
    if x.status_code == 200:
        return x.json()["choices"][0]["message"]["content"]
    else:
        return None

def consistency_checker_agent(novel_info, chapter_num, chapter_content, plot_plan, thinking_budget=None, max_thinking_tokens=None):
    """
    一致性检查 Agent
    职责：专门检查章节内容与总纲、前文的一致性
    """
    total_outline = novel_info["outline"].get("total_outline", "")
    entities = novel_info["outline"].get("enities", [])
    entities_str = "\n".join(entities) if entities else "无"
    
    # 获取前几章内容用于检查
    prev_chapters = []
    for i in range(max(0, chapter_num - 3), chapter_num - 1):
        if i < len(novel_info["chapters"]):
            prev_chapters.append(f"第{i+1}章：{novel_info['chapters'][i]['title']}\n内容摘要：{novel_info['chapters'][i]['content'][:800]}")
    
    prev_chapters_str = "\n\n".join(prev_chapters) if prev_chapters else "无前章内容"
    
    prompts = f"""你是一名专业的文学编辑和一致性检查员。请严格检查以下章节内容的一致性。

【检查对象】
第{chapter_num}章内容：
{chapter_content}

【参考依据】
1. 小说总纲（必须严格遵循）：
{total_outline}

2. 实体设定：
{entities_str}

3. 剧情规划：
{plot_plan}

4. 前几章内容（检查连贯性）：
{prev_chapters_str}

【检查要点】
1. 总纲一致性：检查本章内容是否与总纲设定矛盾（包括世界观、人物设定、剧情走向）
2. 前文一致性：检查是否与之前章节的内容矛盾（包括人物状态、情节发展、时间线等）
3. 人物一致性：检查人物性格、行为、对话是否符合其设定
4. 逻辑一致性：检查情节发展是否合理，有无逻辑漏洞
5. 设定一致性：检查世界观、规则、背景设定是否前后一致
6. 剧情规划遵循度：检查是否按照剧情规划进行创作

请以 JSON 格式输出检查结果：
{{
    "passed": true/false,
    "total_outline_consistency": "总纲一致性评分（1-10 分）及说明",
    "previous_consistency": "前文一致性评分（1-10 分）及说明",
    "character_consistency": "人物一致性评分（1-10 分）及说明",
    "logic_consistency": "逻辑一致性评分（1-10 分）及说明",
    "setting_consistency": "设定一致性评分（1-10 分）及说明",
    "plan_followed": "剧情规划遵循度评分（1-10 分）及说明",
    "issues": ["发现的问题列表，每个问题包含：类型、描述、严重性（高/中/低）"],
    "suggestions": ["具体的修改建议列表"],
    "overall_score": "综合评分（1-10 分）
}}"""

    x = generate(prompts, "user", 12000, tool=[], thinking_budget=thinking_budget, max_thinking_tokens=max_thinking_tokens)
    if x.status_code == 200:
        return x.json()["choices"][0]["message"]["content"]
    else:
        return None

def revision_agent(novel_info, chapter_num, chapter_content, consistency_report, extra_prompts, max_token, thinking_budget=None, max_thinking_tokens=None):
    """
    修改优化 Agent
    职责：根据一致性检查报告修改优化章节内容
    """
    total_outline = novel_info["outline"].get("total_outline", "")
    
    prompts = f"""你是一名专业的小说编辑和修订专家。请根据一致性检查报告修改优化以下章节。

【待修改章节】
第{chapter_num}章：
{chapter_content}

【一致性检查报告】（必须按照报告中的建议进行修改）
{consistency_report}

【小说总纲】（修改的核心指导）
{total_outline}

【用户附加提示词】
{extra_prompts}

【修改要求】
1. 严格按照一致性检查报告中的建议进行修改
2. 优先修复严重性为"高"的问题
3. 保持原文的风格和优点
4. 确保修改后的内容与总纲一致
5. 确保修改后的内容与前文连贯
6. 保持人物性格的一致性
7. 保持世界观设定的一致性
8. 字数保持在合理范围内（±10% 波动）

请输出修改后的完整章节内容："""

    x = generate(prompts, "user", max_token, tool=[], thinking_budget=thinking_budget, max_thinking_tokens=max_thinking_tokens)
    if x.status_code == 200:
        return x.json()["choices"][0]["message"]["content"]
    else:
        return None

def multi_agent_collaboration(novel_info, chapter_num, word_count, extra_prompts, max_token, thinking_budget=None, max_thinking_tokens=None):
    """
    多 Agent 协作主控函数
    协调各 agent 完成高质量章节创作
    """
    import datetime
    
    result = {
        "status": "",
        "plot_plan": "",
        "chapter_content": "",
        "consistency_report": "",
        "final_content": ""
    }
    
    # Step 1: 剧情规划师工作
    result["status"] = "【剧情规划师】正在分析总纲和规划本章剧情...\n"
    print(f"[{datetime.datetime.now()}] {result['status']}")
    yield result
    plot_plan = plot_planner_agent(novel_info, chapter_num, word_count, extra_prompts, thinking_budget, max_thinking_tokens)
    if plot_plan:
        result["plot_plan"] = plot_plan
        result["status"] += "✓ 剧情规划完成！\n"
    else:
        result["status"] += "✗ 剧情规划失败，使用简化模式\n"
    
    # Step 2: 内容创作者工作
    result["status"] += "\n【内容创作者】正在创作本章内容...\n"
    print(f"[{datetime.datetime.now()}] {result['status']}")
    yield result
    if plot_plan:
        chapter_content = content_creator_agent(novel_info, chapter_num, word_count, plot_plan, extra_prompts, max_token, thinking_budget, max_thinking_tokens)
    else:
        # 如果没有规划，直接创作
        chapter_content = content_creator_agent(novel_info, chapter_num, word_count, "", extra_prompts, max_token, thinking_budget, max_thinking_tokens)
    
    if chapter_content:
        result["chapter_content"] = chapter_content
        result["status"] += "✓ 本章内容创作完成！\n"
    else:
        result["status"] += "✗ 内容创作失败\n"
        yield result
        return result
    
    # Step 3: 一致性检查（核心步骤）
    result["status"] += "\n【一致性检查员】正在严格检查章节一致性...\n"
    print(f"[{datetime.datetime.now()}] {result['status']}")
    yield result
    consistency_report = consistency_checker_agent(novel_info, chapter_num, chapter_content, plot_plan, thinking_budget, max_thinking_tokens)
    if consistency_report:
        result["consistency_report"] = consistency_report
        result["status"] += "✓ 一致性检查完成！\n"
    else:
        result["status"] += "✗ 一致性检查失败\n"
    
    # Step 4: 根据一致性检查结果决定是否修改
    result["status"] += "\n【审核决策】正在分析检查结果...\n"
    print(f"[{datetime.datetime.now()}] {result['status']}")
    yield result
    
    # 检查是否需要修改（如果评分低于 7 分或发现严重问题）
    need_revision = False
    if consistency_report:
        # 简单判断：如果包含"false"或评分较低或有问题
        if "false" in consistency_report.lower() or "问题" in consistency_report or "建议" in consistency_report:
            # 尝试解析 JSON 获取评分
            try:
                import json as json_lib
                # 尝试提取 JSON 部分
                json_start = consistency_report.find("{")
                json_end = consistency_report.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    report_json = json_lib.loads(consistency_report[json_start:json_end])
                    overall_score = report_json.get("overall_score", 5)
                    if overall_score < 7 or report_json.get("passed") == False:
                        need_revision = True
                        result["status"] += f"⚠ 检测到一致性问题（综合评分：{overall_score}/10），正在优化...\n"
                    else:
                        result["status"] += f"✓ 一致性良好（综合评分：{overall_score}/10）\n"
                else:
                    need_revision = True
            except:
                # 如果无法解析，默认需要修改
                need_revision = True
                result["status"] += "⚠ 检测到需要改进的问题，正在优化...\n"
    
    if need_revision:
        result["status"] += "\n【修订专家】正在根据检查报告修改优化...\n"
        print(f"[{datetime.datetime.now()}] {result['status']}")
        yield result
        revised_content = revision_agent(novel_info, chapter_num, chapter_content, consistency_report, extra_prompts, max_token, thinking_budget, max_thinking_tokens)
        if revised_content:
            result["final_content"] = revised_content
            result["status"] += "✓ 修订完成！\n"
        else:
            result["status"] += "✗ 修订失败，使用原内容\n"
            result["final_content"] = chapter_content
    else:
        result["final_content"] = chapter_content
    
    result["status"] += "\n✓ 多 agent 协作完成！\n"
    print(f"[{datetime.datetime.now()}] {result['status']}")
    yield result
    return result
