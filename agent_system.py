"""
多 Agent 协作章节生成系统

系统架构：
1. PlanningAgent（内容规划 Agent）- 负责章节内容规划、结构设计
2. WritingAgent（内容撰写 Agent）- 负责根据规划撰写初稿
3. PolishingAgent（内容润色 Agent）- 负责润色、优化文笔
4. ReviewAgent（质量审核 Agent）- 负责质量审核、反馈问题
5. Coordinator（协调器）- 负责任务分配、进度跟踪、冲突解决

协作流程：
1. Coordinator 接收任务参数
2. PlanningAgent 制定章节大纲和结构
3. Coordinator 审核规划并分配任务
4. WritingAgent 根据规划撰写初稿
5. PolishingAgent 润色初稿
6. ReviewAgent 审核质量
7. 如未通过审核，返回相应 Agent 修改
8. 通过后输出最终结果
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import time
import json
from datetime import datetime
from ollama import Client
from settings import OllamaSettings, TokenSettings, DeepSeekSettings

# 加载设置
ollama_settings = OllamaSettings()
token_settings = TokenSettings()
deepseek_settings = DeepSeekSettings()

# 初始化 Ollama 客户端
client = Client(host=ollama_settings.base_url, timeout=ollama_settings.timeout)


def call_ollama(prompt: str, temperature: float = 0.7, num_predict: int = 3000, agent_name: str = "Agent") -> str:
    """统一的 Ollama API 调用函数，内置重试和响应提取逻辑"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = client.chat(
                model=ollama_settings.model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                options={
                    "temperature": temperature,
                    "num_predict": num_predict,
                },
                think=False,
            )
            
            text = ""
            if hasattr(response, 'message') and response.message:
                text = getattr(response.message, 'content', '')
            elif isinstance(response, dict):
                text = response.get('message', {}).get('content', '')
            
            # 过滤掉 Thinking Process 内容
            if text and 'Thinking Process:' in text:
                # 查找第一个空行后的正文内容
                parts = text.split('\n\n', 1)
                if len(parts) > 1:
                    text = parts[1]
            
            done_reason = getattr(response, 'done_reason', None)
            if done_reason == 'length':
                print(f"[{agent_name}] 警告：响应被截断，长度：{len(text)}")
            
            if text and len(text.strip()) > 10:
                print(f"[{agent_name}] 成功获取响应，长度：{len(text)}")
                return text
            
            print(f"[{agent_name}] 响应为空或太短，重试中...")
            
        except Exception as e:
            print(f"[{agent_name}] API调用失败（第 {attempt + 1} 次）：{e}")
        
        time.sleep(2)
    
    raise Exception("AI 响应为空，多次重试失败")


class AgentStatus(Enum):
    """Agent 状态枚举"""
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class TaskMessage:
    """任务消息数据结构"""
    task_id: str
    sender: str
    receiver: str
    task_type: str
    content: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: int = 1  # 1-5，5 为最高优先级
    status: TaskStatus = TaskStatus.PENDING
    feedback: Optional[str] = None


@dataclass
class AgentMetrics:
    """Agent 性能指标"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_response_time: float = 0.0
    quality_score: float = 0.0
    revision_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "avg_response_time": round(self.avg_response_time, 2),
            "quality_score": round(self.quality_score, 2),
            "revision_count": self.revision_count
        }


class BaseAgent(ABC):
    """Agent 基类"""
    
    def __init__(self, agent_id: str, name: str, description: str):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.status = AgentStatus.IDLE
        self.current_task: Optional[TaskMessage] = None
        self.metrics = AgentMetrics()
        self.message_queue: List[TaskMessage] = []
    
    @abstractmethod
    def process_task(self, task: TaskMessage) -> TaskMessage:
        """处理任务，子类必须实现"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """返回 Agent 的能力描述"""
        pass
    
    def receive_message(self, message: TaskMessage):
        """接收消息"""
        self.message_queue.append(message)
        if self.status == AgentStatus.IDLE:
            self.status = AgentStatus.WORKING
    
    def get_next_message(self) -> Optional[TaskMessage]:
        """获取下一条消息"""
        if self.message_queue:
            # 按优先级排序
            self.message_queue.sort(key=lambda x: x.priority, reverse=True)
            return self.message_queue.pop(0)
        return None
    
    def update_metrics(self, success: bool, response_time: float, quality_score: float = 0.0):
        """更新性能指标"""
        if success:
            self.metrics.tasks_completed += 1
        else:
            self.metrics.tasks_failed += 1
        
        # 更新平均响应时间
        total_tasks = self.metrics.tasks_completed + self.metrics.tasks_failed
        self.metrics.avg_response_time = (
            (self.metrics.avg_response_time * (total_tasks - 1) + response_time) / total_tasks
        )
        
        # 更新质量评分
        if quality_score > 0:
            self.metrics.quality_score = (
                (self.metrics.quality_score * (self.metrics.tasks_completed - 1) + quality_score) 
                / self.metrics.tasks_completed
            ) if self.metrics.tasks_completed > 0 else quality_score
    
    def get_status(self) -> Dict:
        """获取 Agent 状态"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "current_task": self.current_task.task_id if self.current_task else None,
            "metrics": self.metrics.to_dict()
        }


class PlanningAgent(BaseAgent):
    """内容规划 Agent - 负责章节内容规划和结构设计"""
    
    def __init__(self):
        super().__init__(
            agent_id="planning_001",
            name="内容规划 Agent",
            description="负责分析章节主题，制定内容结构，规划情节发展"
        )
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "specialty": "内容规划与结构设计",
            "input_format": {
                "chapter_theme": "章节主题",
                "novel_outline": "小说大纲",
                "previous_chapter": "上一章内容（可选）",
                "target_audience": "目标读者",
                "content_style": "内容风格"
            },
            "output_format": {
                "chapter_structure": "章节结构（起承转合）",
                "key_plot_points": "关键情节点",
                "character_arcs": "角色发展线",
                "scene_breakdown": "场景分解",
                "word_count_distribution": "字数分配"
            }
        }
    
    def process_task(self, task: TaskMessage) -> TaskMessage:
        """处理章节规划任务"""
        start_time = time.time()
        self.status = AgentStatus.WORKING
        self.current_task = task
        
        try:
            content = task.content
            
            # 根据任务类型选择不同的处理方法
            if task.task_type == "next_chapter_guidance":
                prompt = self._build_next_chapter_guidance_prompt(content)
                ai_response = call_ollama(prompt, temperature=0.7, num_predict=5000, agent_name="规划Agent")
                result = ai_response  # 直接返回指导文字
                task_type = "next_chapter_guidance_result"
            else:
                # 常规规划任务
                prompt = self._build_planning_prompt(content)
                ai_response = call_ollama(prompt, temperature=0.7, num_predict=8000, agent_name="规划Agent")
                result = self._parse_plan(ai_response)
                task_type = "planning_result"
            
            response_time = time.time() - start_time
            
            # 创建响应消息
            response_task = TaskMessage(
                task_id=f"{task.task_id}_result",
                sender=self.agent_id,
                receiver="coordinator",
                task_type=task_type,
                content=result,
                priority=task.priority,
                status=TaskStatus.COMPLETED
            )
            
            self.update_metrics(True, response_time, 0.85)
            self.status = AgentStatus.IDLE
            return response_task
            
        except Exception as e:
            response_time = time.time() - start_time
            self.update_metrics(False, response_time)
            self.status = AgentStatus.ERROR
            
            error_task = TaskMessage(
                task_id=f"{task.task_id}_error",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="error",
                content={"error": str(e)},
                priority=5,
                status=TaskStatus.FAILED
            )
            return error_task
    
    def _build_planning_prompt(self, content: Dict) -> str:
        """构建规划提示词"""
        chapter_num = content.get('chapter_number', 1)
        novel_outline = content.get('novel_outline', '')
        active_clues = content.get('active_clues', [])
        
        # 从总纲中提取对应章节的信息
        chapter_context = self._extract_chapter_from_outline(novel_outline, chapter_num)
        
        # 构建线索信息
        clues_text = ""
        if active_clues:
            clues_parts = []
            for clue in active_clues:
                next_info = f"（预计在第{clue['next_chapter']}章再次出现）" if clue.get('next_chapter') else "（待收束）"
                clues_parts.append(f"- [{clue['type']}] {clue['text']} {next_info}")
            clues_text = '\n'.join(clues_parts)
        else:
            clues_text = "暂无活跃线索"
        
        prompt = f"""你是一位专业的小说内容规划师。请根据以下信息为章节制定详细的内容规划。

【基本信息】
- 章节编号：第{chapter_num}章
- 章节主题：{content.get('chapter_theme', '未知')}
- 目标读者：{content.get('target_audience', '普通读者')}
- 内容风格：{content.get('content_style', '传统叙事')}

【小说总纲（节选）】
{novel_outline[:3000] if novel_outline else '暂无总纲'}

【历史章节内容】
{content.get('previous_chapters_text', '这是第一章，无历史章节内容')}

【活跃线索】
{clues_text}

【规划要求】
请制定一个结构完整的章节规划，包括：
1. 章节结构（起承转合四部分）
2. 关键情节点（3-5 个）
3. 角色发展线
4. 场景分解（每个场景的主要内容）
5. 字数分配建议
6. 注意线索的自然铺设和推进
7. 规划必须与历史章节内容自然衔接，符合小说总纲的设定

请结合小说总纲、历史章节内容和本章大纲，以清晰的格式输出规划内容。"""
        return prompt
    
    def _extract_chapter_from_outline(self, outline: str, chapter_num: int) -> str:
        """从总纲中提取指定章节的相关信息"""
        if not outline:
            return "无总纲信息"
        
        lines = outline.split('\n')
        relevant_content = []
        in_chapter = False
        found_chapter = False
        
        # 尝试匹配章节
        chapter_patterns = [
            f"第{chapter_num}章",
            f"第{chapter_num}回",
            f"Chapter {chapter_num}",
            f"{chapter_num}."
        ]
        
        for i, line in enumerate(lines):
            # 检查是否找到目标章节
            for pattern in chapter_patterns:
                if pattern in line:
                    in_chapter = True
                    found_chapter = True
                    relevant_content.append(f"[第{chapter_num}章相关]")
                    continue
            
            # 如果在本章内，收集内容
            if in_chapter:
                # 检查是否进入下一章
                next_chapter_patterns = [
                    f"第{chapter_num + 1}章",
                    f"第{chapter_num + 1}回",
                    f"Chapter {chapter_num + 1}"
                ]
                
                if any(pattern in line for pattern in next_chapter_patterns):
                    break
                
                relevant_content.append(line)
        
        # 如果没有找到具体章节，尝试从总纲中提取相关上下文
        if not found_chapter:
            # 返回总纲的前后部分作为上下文
            outline_lines = outline.split('\n')
            if len(outline_lines) <= 10:
                return outline
            else:
                # 返回总纲的概览部分
                return '\n'.join(outline_lines[:10]) + "\n...(总纲内容过长，仅显示概览)..."
        
        return '\n'.join(relevant_content).strip()
    
    def _parse_plan(self, response: str) -> Dict:
        """解析规划结果"""
        # 简单的文本解析，实际可以使用更复杂的 NLP 方法
        return {
            "plan_text": response,
            "structure": self._extract_section(response, "章节结构"),
            "plot_points": self._extract_section(response, "关键情节点"),
            "scenes": self._extract_section(response, "场景分解")
        }
    
    def _build_next_chapter_guidance_prompt(self, content: Dict) -> str:
        """构建下一章指导文字的提示词"""
        current_chapter_num = content.get('current_chapter_number', 1)
        next_chapter_num = current_chapter_num + 1
        current_content = content.get('current_chapter_content', '')
        novel_outline = content.get('novel_outline', '')
        active_clues = content.get('active_clues', [])
        
        # 构建线索信息
        clues_text = ""
        if active_clues:
            clues_parts = []
            for clue in active_clues:
                next_info = f"（预计在第{clue['next_chapter']}章再次出现）" if clue.get('next_chapter') else "（待收束）"
                clues_parts.append(f"- [{clue['type']}] {clue['text']} {next_info}")
            clues_text = '\n'.join(clues_parts)
        else:
            clues_text = "暂无活跃线索"
        
        prompt = f"""你是一位专业的小说编辑和指导者。请基于以下信息为第{next_chapter_num}章生成一段指导文字。

【当前章节信息】
- 当前章节：第{current_chapter_num}章
- 当前章节内容（节选）：
{current_content[:1000] if current_content else '暂无内容'}

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
        return prompt
    
    def _extract_section(self, text: str, section_name: str) -> str:
        """提取指定章节内容"""
        lines = text.split('\n')
        in_section = False
        result = []
        
        for line in lines:
            if section_name in line:
                in_section = True
                continue
            if in_section:
                if line.strip() and not line.startswith(' '):
                    break
                result.append(line)
        
        return '\n'.join(result).strip()


class WritingAgent(BaseAgent):
    """内容撰写 Agent - 负责根据规划撰写初稿"""
    
    def __init__(self):
        super().__init__(
            agent_id="writing_001",
            name="内容撰写 Agent",
            description="负责根据内容规划撰写章节初稿"
        )
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "specialty": "内容撰写与初稿创作",
            "input_format": {
                "chapter_plan": "章节规划",
                "chapter_number": "章节编号",
                "target_word_count": "目标字数",
                "style_guide": "风格指南"
            },
            "output_format": {
                "chapter_title": "章节标题",
                "chapter_content": "章节正文",
                "word_count": "实际字数",
                "writing_notes": "撰写说明"
            }
        }
    
    def process_task(self, task: TaskMessage) -> TaskMessage:
        """处理章节撰写任务"""
        start_time = time.time()
        self.status = AgentStatus.WORKING
        self.current_task = task
        
        try:
            content = task.content
            prompt = self._build_writing_prompt(content)
            target_word_count = content.get('target_word_count', 2000)
            
            ai_response = call_ollama(prompt, temperature=0.8, num_predict=target_word_count * 2, agent_name="写作Agent")
            chapter_result = self._parse_chapter(ai_response)
            response_time = time.time() - start_time
            
            response_task = TaskMessage(
                task_id=f"{task.task_id}_write",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="writing_result",
                content=chapter_result,
                priority=task.priority,
                status=TaskStatus.COMPLETED
            )
            
            self.update_metrics(True, response_time, 0.80)
            self.status = AgentStatus.IDLE
            return response_task
            
        except Exception as e:
            response_time = time.time() - start_time
            self.update_metrics(False, response_time)
            self.status = AgentStatus.ERROR
            
            error_task = TaskMessage(
                task_id=f"{task.task_id}_error",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="error",
                content={"error": str(e)},
                priority=5,
                status=TaskStatus.FAILED
            )
            return error_task
    
    def _build_writing_prompt(self, content: Dict) -> str:
        """构建撰写提示词"""
        plan = content.get('chapter_plan', {})
        active_clues = content.get('active_clues', [])
        previous_chapters_text = content.get('previous_chapters_text', '')
        novel_outline = content.get('novel_outline', '')
        
        # 构建线索信息
        clues_text = ""
        if active_clues:
            clues_parts = []
            for clue in active_clues:
                next_info = f"（预计在第{clue['next_chapter']}章再次出现）" if clue.get('next_chapter') else "（待收束）"
                clues_parts.append(f"- [{clue['type']}] {clue['text']} {next_info}")
            clues_text = '\n'.join(clues_parts)
        
        # 构建规划摘要
        plan_structure = plan.get('structure', '')
        plan_plot_points = plan.get('plot_points', '')
        plan_scenes = plan.get('scenes', '')
        
        prompt = f"""你是一位专业的小说作家。请根据以下信息撰写第{content.get('chapter_number', 1)}章内容。

【小说总纲】
{novel_outline[:2000] if novel_outline else '暂无总纲'}

【历史章节内容】
{previous_chapters_text if previous_chapters_text else '这是第一章，无历史章节内容'}

【章节规划】
结构：{plan_structure if plan_structure else '无'}
情节点：{plan_plot_points if plan_plot_points else '无'}
场景：{plan_scenes if plan_scenes else '无'}

【活跃线索】
{clues_text if clues_text else '暂无'}

【撰写要求】
1. 严格按照规划的结构、情节点和场景进行创作
2. 必须与历史章节内容自然衔接，不要重复前面的开头情节
3. 保持文风一致，情节连贯，符合小说总纲设定
4. 注重角色塑造和对话自然
5. 避免使用 markdown 格式
6. 第一行为章节标题
7. 注重章节上下文衔接流畅，避免重复内容，忌同一意思反复说
8. 注意活跃线索的自然铺设和推进
9. 直接开始写本章内容，不要复述或总结前面内容
10. 字数目标：{content.get('target_word_count', 2000)}字

请开始撰写第{content.get('chapter_number', 1)}章的正文内容。"""
        return prompt
    
    def _parse_chapter(self, response: str) -> Dict:
        """解析章节内容"""
        print(f"[写作Agent] AI 原始响应长度：{len(response) if response else 0}字")
        print(f"[写作Agent] AI 响应预览：{response[:200] if response else '空'}...")
        
        if not response or not response.strip():
            print(f"[写作Agent] 错误：AI 响应为空")
            return {
                "chapter_title": "",
                "chapter_content": "",
                "word_count": 0,
                "writing_notes": "AI 响应为空"
            }
        
        lines = response.strip().split('\n')
        title = lines[0].strip() if lines else "无标题"
        content = '\n'.join(lines[1:]).strip()
        
        print(f"[写作Agent] 解析结果：")
        print(f"  - 标题：{title}")
        print(f"  - 内容长度：{len(content)}字")
        
        return {
            "chapter_title": title,
            "chapter_content": content,
            "word_count": len(content),
            "writing_notes": "初稿完成"
        }


class PolishingAgent(BaseAgent):
    """内容润色 Agent - 负责润色和优化文笔"""
    
    def __init__(self):
        super().__init__(
            agent_id="polishing_001",
            name="内容润色 Agent",
            description="负责润色章节内容，优化文笔和表达"
        )
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "specialty": "内容润色与文笔优化",
            "input_format": {
                "chapter_content": "章节内容",
                "style_requirements": "风格要求",
                "focus_areas": "重点关注领域"
            },
            "output_format": {
                "polished_content": "润色后内容",
                "changes_made": "修改说明",
                "quality_improvements": "质量提升点"
            }
        }
    
    def process_task(self, task: TaskMessage) -> TaskMessage:
        """处理润色任务"""
        start_time = time.time()
        self.status = AgentStatus.WORKING
        self.current_task = task
        
        try:
            content = task.content
            chapter_content = content.get('chapter_content', '')
            
            # 如果内容为空，直接返回
            if not chapter_content:
                print(f"[润色Agent] 警告：接收到空内容，跳过润色")
                return TaskMessage(
                    task_id=f"{task.task_id}_polish",
                    sender=self.agent_id,
                    receiver="coordinator",
                    task_type="polishing_result",
                    content={
                        "polished_content": "",
                        "changes_made": "无内容，跳过润色",
                        "quality_improvements": "无"
                    },
                    priority=task.priority,
                    status=TaskStatus.COMPLETED
                )
            
            prompt = self._build_polishing_prompt(content)
            max_tokens = content.get('max_tokens', 8000)
            ai_response = call_ollama(prompt, temperature=0.6, num_predict=max_tokens, agent_name="润色Agent")
            polished_result = self._parse_polished(ai_response)
            response_time = time.time() - start_time
            
            response_task = TaskMessage(
                task_id=f"{task.task_id}_polish",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="polishing_result",
                content=polished_result,
                priority=task.priority,
                status=TaskStatus.COMPLETED
            )
            
            self.update_metrics(True, response_time, 0.88)
            self.status = AgentStatus.IDLE
            return response_task
            
        except Exception as e:
            response_time = time.time() - start_time
            self.update_metrics(False, response_time)
            self.status = AgentStatus.ERROR
            
            error_task = TaskMessage(
                task_id=f"{task.task_id}_error",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="error",
                content={"error": str(e)},
                priority=5,
                status=TaskStatus.FAILED
            )
            return error_task
    
    def _build_polishing_prompt(self, content: Dict) -> str:
        """构建润色提示词"""
        chapter_content = content.get('chapter_content', '')
        active_clues = content.get('active_clues', [])
        
        # 构建线索信息
        clues_text = ""
        if active_clues:
            clues_parts = []
            for clue in active_clues:
                next_info = f"（预计在第{clue['next_chapter']}章再次出现）" if clue.get('next_chapter') else "（待收束）"
                clues_parts.append(f"- [{clue['type']}] {clue['text']} {next_info}")
            clues_text = '\n'.join(clues_parts)
        
        prompt = f"""你是一位专业的文字编辑和润色专家。请对以下章节内容进行润色和优化。

【本章原文内容】
{chapter_content}

【活跃线索】
{clues_text if clues_text else '暂无'}

【润色要求】
1. 优化语句流畅度和可读性
2. 改进词汇选择，使表达更精准
3. 调整句式结构，增加变化
4. 保持原文风格和情节不变
5. 修正可能的语法错误
6. 增强描写的生动性
7. 确保线索描写自然流畅，不突兀
8. 不要改变原文的核心情节和意思

请提供润色后的完整内容，并列出主要修改点。"""
        return prompt
    
    def _parse_polished(self, response: str) -> Dict:
        """解析润色结果"""
        # 简单分割，实际可以更智能
        if "主要修改点" in response:
            parts = response.split("主要修改点")
            content = parts[0].strip()
            changes = parts[1].strip() if len(parts) > 1 else ""
        else:
            content = response
            changes = ""
        
        return {
            "polished_content": content,
            "changes_made": changes,
            "quality_improvements": "流畅度提升、词汇优化、句式丰富"
        }


class ReviewAgent(BaseAgent):
    """质量审核 Agent - 负责审核内容质量"""
    
    def __init__(self):
        super().__init__(
            agent_id="review_001",
            name="质量审核 Agent",
            description="负责审核章节质量，提供反馈和改进建议"
        )
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "specialty": "质量审核与反馈",
            "input_format": {
                "chapter_content": "章节内容",
                "original_plan": "原始规划",
                "quality_criteria": "质量标准"
            },
            "output_format": {
                "quality_score": "质量评分（0-100）",
                "passed": "是否通过",
                "feedback": "详细反馈",
                "suggestions": "改进建议"
            }
        }
    
    def process_task(self, task: TaskMessage) -> TaskMessage:
        """处理审核任务"""
        start_time = time.time()
        self.status = AgentStatus.WORKING
        self.current_task = task
        
        try:
            content = task.content
            prompt = self._build_review_prompt(content)
            max_tokens = content.get('max_tokens', 2000)
            ai_response = call_ollama(prompt, temperature=0.5, num_predict=max_tokens, agent_name="审核Agent")
            review_result = self._parse_review(ai_response)
            response_time = time.time() - start_time
            
            response_task = TaskMessage(
                task_id=f"{task.task_id}_review",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="review_result",
                content=review_result,
                priority=task.priority,
                status=TaskStatus.COMPLETED
            )
            
            self.update_metrics(True, response_time, 0.90)
            self.status = AgentStatus.IDLE
            return response_task
            
        except Exception as e:
            response_time = time.time() - start_time
            self.update_metrics(False, response_time)
            self.status = AgentStatus.ERROR
            
            error_task = TaskMessage(
                task_id=f"{task.task_id}_error",
                sender=self.agent_id,
                receiver="coordinator",
                task_type="error",
                content={"error": str(e)},
                priority=5,
                status=TaskStatus.FAILED
            )
            return error_task
    
    def _build_review_prompt(self, content: Dict) -> str:
        """构建审核提示词"""
        chapter_content = content.get('chapter_content', '')
        active_clues = content.get('active_clues', [])
        original_plan = content.get('original_plan', {})
        
        # 构建线索信息
        clues_text = ""
        if active_clues:
            clues_parts = []
            for clue in active_clues:
                next_info = f"（预计在第{clue['next_chapter']}章再次出现）" if clue.get('next_chapter') else "（待收束）"
                clues_parts.append(f"- [{clue['type']}] {clue['text']} {next_info}")
            clues_text = '\n'.join(clues_parts)
        
        prompt = f"""你是一位严格的小说质量审核编辑。请对以下章节内容进行质量审核。

【章节内容】
{chapter_content}

【活跃线索】
{clues_text if clues_text else '暂无'}

【原始规划】
{original_plan.get('plan_text', '无规划')}

【审核标准】
1. 内容是否符合规划（30 分）
2. 情节是否连贯合理（25 分）
3. 文笔是否流畅优美（20 分）
4. 角色塑造是否立体（15 分）
5. 对话是否自然真实（10 分）

【输出格式要求】
**第一行必须是一个数字（0-100），表示总分**
第二行开始输出一份较为完整的报告

【输出示例】
85
详细评审：
- 内容符合度：25/30
- 情节连贯性：23/25
...（详细分析）

改进建议：..."""
        return prompt
    
    def _parse_review(self, response: str) -> Dict:
        """解析审核结果"""
        import re
        
        # 提取第一行的数字作为评分
        lines = response.strip().split('\n')
        score = 0
        
        if lines:
            first_line = lines[0].strip()
            # 尝试从第一行提取数字
            score_match = re.match(r'^(\d+)', first_line)
            if score_match:
                score = int(score_match.group(1))
                # 确保分数在 0-100 范围内
                score = max(0, min(100, score))
        
        # 提取详细评审内容（从第二行开始）
        feedback_lines = lines[1:] if len(lines) > 1 else []
        feedback = '\n'.join(feedback_lines).strip()
        
        # 判断是否通过（60 分及以上）
        passed = score >= 60
        
        # 提取改进建议
        suggestions_match = re.search(r'改进建议\s*[:：]?\s*(.*)', feedback, re.DOTALL)
        suggestions = suggestions_match.group(1).strip() if suggestions_match else ""
        
        return {
            "quality_score": score,
            "passed": passed,
            "feedback": feedback,
            "suggestions": suggestions
        }


class Coordinator:
    """协调器 - 负责任务分配、进度跟踪、冲突解决"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.task_queue: List[TaskMessage] = []
        self.completed_tasks: List[TaskMessage] = []
        self.task_history: List[Dict] = []
        self.current_chapter_task: Optional[Dict] = None
        self.system_metrics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "avg_collaboration_time": 0.0
        }
        
        # 注册默认 Agent
        self.register_agent(PlanningAgent())
        self.register_agent(WritingAgent())
        self.register_agent(PolishingAgent())
        self.register_agent(ReviewAgent())
    
    def register_agent(self, agent: BaseAgent):
        """注册 Agent"""
        self.agents[agent.agent_id] = agent
        print(f"[协调器] 已注册 Agent: {agent.name} ({agent.agent_id})")
    
    def generate_chapter(self, 
                        chapter_number: int,
                        chapter_theme: str,
                        novel_outline: str,
                        active_clues: Optional[List[Dict]] = None,
                        previous_chapters: Optional[List[Dict]] = None,
                        previous_chapter_guidance: Optional[str] = None,
                        target_audience: str = "普通读者",
                        content_style: str = "传统叙事",
                        target_word_count: int = 2000,
                        temperature: float = 0.7,
                        generate_next_chapter_guidance: bool = False,
                        max_tokens: int = 8000) -> Dict:
        """生成章节的主流程"""
        
        task_id = f"chapter_{chapter_number}_{int(time.time())}"
        start_time = time.time()
        
        print(f"\n{'='*60}")
        print(f"[协调器] 开始生成第{chapter_number}章")
        print(f"任务 ID: {task_id}")
        print(f"传入历史章节数：{len(previous_chapters) if previous_chapters else 0}")
        print(f"{'='*60}\n")
        
        self.current_chapter_task = {
            "task_id": task_id,
            "chapter_number": chapter_number,
            "status": "in_progress",
            "start_time": start_time,
            "steps": []
        }
        
        try:
            # 调试日志
            print(f"\n[协调器调试] 接收到的参数：")
            print(f"  - chapter_number: {chapter_number}")
            print(f"  - novel_outline长度: {len(novel_outline) if novel_outline else 0}字")
            print(f"  - active_clues数量: {len(active_clues) if active_clues else 0}")
            print(f"  - previous_chapters数量: {len(previous_chapters) if previous_chapters else 0}")
            print(f"  - generate_next_chapter_guidance: {generate_next_chapter_guidance}")
            
            # Step 1: 内容规划
            plan_result = self._step_planning(
                task_id=task_id,
                chapter_number=chapter_number,
                chapter_theme=chapter_theme,
                novel_outline=novel_outline,
                active_clues=active_clues,
                previous_chapters=previous_chapters,
                previous_chapter_guidance=previous_chapter_guidance,
                target_audience=target_audience,
                content_style=content_style
            )
            
            if not plan_result:
                raise Exception("内容规划失败")
            
            # Step 2: 内容撰写
            writing_result = self._step_writing(
                task_id=task_id,
                chapter_number=chapter_number,
                plan=plan_result,
                active_clues=active_clues or [],
                previous_chapters=previous_chapters,
                novel_outline=novel_outline,
                target_word_count=target_word_count,
                style_guide=content_style
            )
            
            if not writing_result:
                raise Exception("内容撰写失败")
            
            # Step 3: 内容润色
            # writing_result 是一个字典，包含 chapter_content 字段
            if isinstance(writing_result, dict):
                chapter_text = writing_result.get('chapter_content', '')
                print(f"[协调器] 从写作结果中提取章节内容，长度：{len(chapter_text)}字")
            else:
                chapter_text = writing_result
                print(f"[协调器] 写作结果为字符串，长度：{len(chapter_text) if chapter_text else 0}字")
            
            if not chapter_text:
                print(f"[协调器] 警告：章节内容为空！写作结果：{writing_result}")
            
            polishing_result = self._step_polishing(
                task_id=task_id,
                chapter_content=chapter_text,
                active_clues=active_clues or [],
                style_requirements=content_style,
                max_tokens=max_tokens
            )
            
            if not polishing_result:
                raise Exception("内容润色失败")
            
            # Step 4: 质量审核
            # polishing_result 是一个字典，包含 polished_content 字段
            if isinstance(polishing_result, dict):
                final_content = polishing_result.get('polished_content', '')
            else:
                final_content = polishing_result
            
            review_result = self._step_review(
                task_id=task_id,
                chapter_content=final_content,
                active_clues=active_clues or [],
                original_plan=plan_result,
                max_tokens=max_tokens
            )
            
            # Step 5: 根据审核结果决定下一步
            if review_result.get('passed', False):
                # 审核通过，完成任务
                total_time = time.time() - start_time
                
                # 生成下一章指导文字（如果需要）
                next_chapter_guidance = None
                if generate_next_chapter_guidance:
                    next_chapter_guidance = self._step_next_chapter_guidance(
                        task_id=task_id,
                        chapter_number=chapter_number,
                        chapter_content=final_content,
                        novel_outline=novel_outline,
                        active_clues=active_clues or [],
                        previous_chapters=previous_chapters,
                        target_audience=target_audience,
                        content_style=content_style
                    )
                
                self._complete_task(task_id, final_content, review_result, total_time)
                
                result = {
                    "success": True,
                    "chapter_content": {
                        "chapter_title": writing_result.get('chapter_title', f'第{chapter_number}章') if isinstance(writing_result, dict) else f'第{chapter_number}章',
                        "polished_content": final_content
                    },
                    "review": review_result,
                    "metrics": self._get_task_metrics(task_id)
                }
                
                # 添加下一章指导文字
                if next_chapter_guidance:
                    result["next_chapter_guidance"] = next_chapter_guidance
                
                return result
            else:
                # 审核未通过，需要修改
                revision_result = self._handle_revision(
                    task_id=task_id,
                    chapter_content=polishing_result,
                    review_result=review_result,
                    revision_type="writing" if review_result.get('quality_score', 0) < 50 else "polishing"
                )
                
                total_time = time.time() - start_time
                
                # 生成下一章指导文字（如果需要），即使审核未通过也应该生成
                next_chapter_guidance = None
                if generate_next_chapter_guidance:
                    # 提取润色后的内容用于生成指导文字
                    if isinstance(polishing_result, dict):
                        guidance_content = polishing_result.get('polished_content', '')
                    else:
                        guidance_content = polishing_result
                    
                    next_chapter_guidance = self._step_next_chapter_guidance(
                        task_id=task_id,
                        chapter_number=chapter_number,
                        chapter_content=guidance_content,
                        novel_outline=novel_outline,
                        active_clues=active_clues or [],
                        previous_chapters=previous_chapters,
                        target_audience=target_audience,
                        content_style=content_style
                    )
                
                self._complete_task(task_id, revision_result, review_result, total_time)
                
                result = {
                    "success": True,
                    "chapter_content": revision_result,
                    "review": review_result,
                    "revised": True,
                    "metrics": self._get_task_metrics(task_id)
                }
                
                # 添加下一章指导文字
                if next_chapter_guidance:
                    result["next_chapter_guidance"] = next_chapter_guidance
                
                return result
                
        except Exception as e:
            print(f"[协调器] 任务失败：{e}")
            self.current_chapter_task["status"] = "failed"
            self.system_metrics["failed_tasks"] += 1
            
            return {
            "success": False,
            "error": str(e),
            "metrics": self._get_task_metrics(task_id)
        }
    
    def _step_next_chapter_guidance(self, **kwargs) -> Optional[str]:
        """Step 5: 生成下一章指导文字"""
        print("\n[协调器] Step 5: 生成下一章指导文字")
        
        task = TaskMessage(
            task_id=f"{kwargs['task_id']}_guidance",
            sender="coordinator",
            receiver="planning_001",  # 使用规划Agent来生成指导
            task_type="next_chapter_guidance",
            content={
                "current_chapter_number": kwargs.get('chapter_number'),
                "current_chapter_content": kwargs.get('chapter_content'),
                "novel_outline": kwargs.get('novel_outline'),
                "active_clues": kwargs.get('active_clues', []),
                "previous_chapters": kwargs.get('previous_chapters'),
                "target_audience": kwargs.get('target_audience'),
                "content_style": kwargs.get('content_style')
            },
            priority=3
        )
        
        planning_agent = self.agents.get("planning_001")
        if not planning_agent:
            print("[协调器] 错误：未找到内容规划 Agent")
            return None
        
        result_task = planning_agent.process_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            print("[协调器] ✓ 下一章指导文字生成完成")
            self.current_chapter_task["steps"].append({
                "step": "next_chapter_guidance",
                "status": "completed",
                "agent": "planning_001"
            })
            # 直接返回内容
            return result_task.content if isinstance(result_task.content, str) else str(result_task.content)
        else:
            print(f"[协调器] ✗ 下一章指导文字生成失败：{result_task.content.get('error')}")
            self.current_chapter_task["steps"].append({
                "step": "next_chapter_guidance",
                "status": "failed",
                "agent": "planning_001"
            })
            return None
    
    def _step_planning(self, **kwargs) -> Optional[Dict]:
        """Step 1: 内容规划"""
        print("\n[协调器] Step 1: 内容规划")
        
        # 构建历史章节内容字符串
        previous_chapters = kwargs.get('previous_chapters', [])
        previous_chapter_guidance = kwargs.get('previous_chapter_guidance')
        
        previous_chapters_text = ""
        if previous_chapters:
            for ch_data in previous_chapters:
                ch_num = ch_data.get('chapter_number', '')
                ch_content = ch_data.get('content', '')
                previous_chapters_text += f"第{ch_num}章:\n{ch_content}\n\n"
            if previous_chapter_guidance:
                previous_chapters_text += f"最新章指导文字:\n{previous_chapter_guidance}\n"
        else:
            previous_chapters_text = "这是第一章，无历史章节内容"
        
        task = TaskMessage(
            task_id=f"{kwargs['task_id']}_plan",
            sender="coordinator",
            receiver="planning_001",
            task_type="planning",
            content={
                "chapter_theme": kwargs.get('chapter_theme'),
                "chapter_number": kwargs.get('chapter_number'),
                "novel_outline": kwargs.get('novel_outline'),
                "chapter_outline": kwargs.get('chapter_outline'),
                "active_clues": kwargs.get('active_clues', []),
                "previous_chapters_text": previous_chapters_text,
                "target_audience": kwargs.get('target_audience'),
                "content_style": kwargs.get('content_style')
            },
            priority=4
        )
        
        planning_agent = self.agents.get("planning_001")
        if not planning_agent:
            print("[协调器] 错误：未找到内容规划 Agent")
            return None
        
        result_task = planning_agent.process_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            print(f"[协调器] ✓ 内容规划完成")
            self.current_chapter_task["steps"].append({
                "step": "planning",
                "status": "completed",
                "agent": "planning_001"
            })
            return result_task.content
        else:
            print(f"[协调器] ✗ 内容规划失败：{result_task.content.get('error')}")
            self.current_chapter_task["steps"].append({
                "step": "planning",
                "status": "failed",
                "agent": "planning_001"
            })
            return None
    
    def _step_writing(self, **kwargs) -> Optional[Dict]:
        """Step 2: 内容撰写"""
        print("\n[协调器] Step 2: 内容撰写")
        
        # 构建历史章节内容字符串
        previous_chapters = kwargs.get('previous_chapters', [])
        
        previous_chapters_text = ""
        if previous_chapters:
            for ch_data in previous_chapters:
                ch_num = ch_data.get('chapter_number', '')
                ch_content = ch_data.get('content', '')
                previous_chapters_text += f"第{ch_num}章:\n{ch_content}\n\n"
        else:
            previous_chapters_text = "这是第一章，无历史章节内容"
        
        task = TaskMessage(
            task_id=f"{kwargs['task_id']}_write",
            sender="coordinator",
            receiver="writing_001",
            task_type="writing",
            content={
                "chapter_number": kwargs.get('chapter_number'),
                "chapter_plan": kwargs.get('plan'),
                "chapter_outline": kwargs.get('chapter_outline'),
                "active_clues": kwargs.get('active_clues', []),
                "previous_chapters_text": previous_chapters_text,
                "novel_outline": kwargs.get('novel_outline'),
                "target_word_count": kwargs.get('target_word_count'),
                "style_guide": kwargs.get('style_guide')
            },
            priority=4
        )
        
        writing_agent = self.agents.get("writing_001")
        if not writing_agent:
            print("[协调器] 错误：未找到内容撰写 Agent")
            return None
        
        result_task = writing_agent.process_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            print(f"[协调器] ✓ 内容撰写完成")
            self.current_chapter_task["steps"].append({
                "step": "writing",
                "status": "completed",
                "agent": "writing_001"
            })
            return result_task.content
        else:
            print(f"[协调器] ✗ 内容撰写失败：{result_task.content.get('error')}")
            self.current_chapter_task["steps"].append({
                "step": "writing",
                "status": "failed",
                "agent": "writing_001"
            })
            return None
    
    def _step_polishing(self, **kwargs) -> Optional[Dict]:
        """Step 3: 内容润色"""
        print("\n[协调器] Step 3: 内容润色")
        
        task = TaskMessage(
            task_id=f"{kwargs['task_id']}_polish",
            sender="coordinator",
            receiver="polishing_001",
            task_type="polishing",
            content={
                "chapter_content": kwargs.get('chapter_content'),
                "chapter_outline": kwargs.get('chapter_outline'),
                "active_clues": kwargs.get('active_clues', []),
                "style_requirements": kwargs.get('style_requirements'),
                "max_tokens": kwargs.get('max_tokens', 8000)
            },
            priority=3
        )
        
        polishing_agent = self.agents.get("polishing_001")
        if not polishing_agent:
            print("[协调器] 错误：未找到内容润色 Agent")
            return None
        
        result_task = polishing_agent.process_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            print(f"[协调器] ✓ 内容润色完成")
            self.current_chapter_task["steps"].append({
                "step": "polishing",
                "status": "completed",
                "agent": "polishing_001"
            })
            return result_task.content
        else:
            print(f"[协调器] ✗ 内容润色失败：{result_task.content.get('error')}")
            self.current_chapter_task["steps"].append({
                "step": "polishing",
                "status": "failed",
                "agent": "polishing_001"
            })
            return None
    
    def _step_review(self, **kwargs) -> Dict:
        """Step 4: 质量审核"""
        print("\n[协调器] Step 4: 质量审核")
        
        task = TaskMessage(
            task_id=f"{kwargs['task_id']}_review",
            sender="coordinator",
            receiver="review_001",
            task_type="review",
            content={
                "chapter_content": kwargs.get('chapter_content'),
                "chapter_outline": kwargs.get('chapter_outline'),
                "active_clues": kwargs.get('active_clues', []),
                "original_plan": kwargs.get('original_plan'),
                "max_tokens": kwargs.get('max_tokens', 8000)
            },
            priority=5
        )
        
        review_agent = self.agents.get("review_001")
        if not review_agent:
            print("[协调器] 错误：未找到质量审核 Agent")
            return {"passed": False, "quality_score": 0, "feedback": "审核 Agent 缺失"}
        
        result_task = review_agent.process_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            review_data = result_task.content
            passed = review_data.get('passed', False)
            score = review_data.get('quality_score', 0)
            
            if passed:
                print(f"[协调器] ✓ 质量审核通过（评分：{score}）")
            else:
                print(f"[协调器] ✗ 质量审核未通过（评分：{score}）")
            
            self.current_chapter_task["steps"].append({
                "step": "review",
                "status": "completed",
                "agent": "review_001",
                "score": score,
                "passed": passed
            })
            return review_data
        else:
            print(f"[协调器] ✗ 质量审核失败：{result_task.content.get('error')}")
            self.current_chapter_task["steps"].append({
                "step": "review",
                "status": "failed",
                "agent": "review_001"
            })
            return {"passed": False, "quality_score": 0, "feedback": "审核失败"}
    
    def _handle_revision(self, **kwargs) -> Dict:
        """处理修改请求"""
        print("\n[协调器] 处理修改请求")
        
        revision_type = kwargs.get('revision_type', 'writing')
        review_result = kwargs.get('review_result', {})
        suggestions = review_result.get('suggestions', '')
        
        if revision_type == 'writing':
            print("[协调器] 返回内容撰写 Agent 重新撰写")
            # 重新撰写逻辑（简化版本，实际应该循环）
            return kwargs.get('chapter_content')
        else:
            print("[协调器] 返回内容润色 Agent 重新润色")
            # 重新润色逻辑
            return kwargs.get('chapter_content')
    
    def _complete_task(self, task_id: str, content: Dict, review: Dict, total_time: float):
        """完成任务"""
        self.system_metrics["completed_tasks"] += 1
        self.system_metrics["total_tasks"] += 1
        
        # 更新平均协作时间
        n = self.system_metrics["completed_tasks"]
        avg_time = self.system_metrics["avg_collaboration_time"]
        self.system_metrics["avg_collaboration_time"] = (avg_time * (n - 1) + total_time) / n
        
        self.current_chapter_task["status"] = "completed"
        self.current_chapter_task["end_time"] = time.time()
        self.current_chapter_task["total_time"] = total_time
        
        self.task_history.append(self.current_chapter_task)
        
        print(f"\n[协调器] ✓ 任务完成，总耗时：{total_time:.2f}秒")
    
    def _get_task_metrics(self, task_id: str) -> Dict:
        """获取任务指标"""
        return {
            "task_id": task_id,
            "system_metrics": self.system_metrics.copy(),
            "agent_metrics": {
                agent_id: agent.metrics.to_dict()
                for agent_id, agent in self.agents.items()
            }
        }
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            "system_metrics": self.system_metrics,
            "agents_status": {
                agent_id: agent.get_status()
                for agent_id, agent in self.agents.items()
            },
            "pending_tasks": len(self.task_queue),
            "completed_tasks": len(self.completed_tasks)
        }


# 导出主要类
__all__ = [
    'Coordinator',
    'PlanningAgent',
    'WritingAgent',
    'PolishingAgent',
    'ReviewAgent',
    'BaseAgent',
    'TaskMessage',
    'AgentStatus',
    'TaskStatus'
]
