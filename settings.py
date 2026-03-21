# Ollama模型设置
class OllamaSettings:
    def __init__(self):
        # 使用的Ollama模型名称
        self.model = "qwen3:8b"
        # Ollama服务的基础URL
        self.base_url = "http://localhost:11434"

# Gradio界面设置
class GradioSettings:
    def __init__(self):
        # 界面标题
        self.title = "长篇小说生成器"
        # 界面描述
        self.description = "输入提示词，生成小说"
        # 界面主题
        self.theme = "default"
        # 是否允许用户标记内容
        self.allow_flagging = "never"

# 数据库设置
class DatabaseSettings:
    def __init__(self):
        # 小说数据库路径
        self.db_path = r'./novel.db'
        # 小说表名
        self.db_table = 'novels'
        # 章节表名
        self.chapter_table = 'chapters'

# 章节生成设置
class ChapterSettings:
    def __init__(self):
        # 默认章节字数
        self.default_word_count = 1000
        # 默认生成温度
        self.default_temperature = 0.7
        # 最大章节字数
        self.max_word_count = 10000
        # 最小生成温度
        self.min_temperature = 0.1
        # 最大生成温度
        self.max_temperature = 1.0

# 大纲生成设置
class OutlineSettings:
    def __init__(self):
        # 默认章节数
        self.default_chapter_count = 5
        # 默认每章字数
        self.default_chapter_word_count = 1000
        # 默认章节间隔（每隔多少章拆分成小事件）
        self.default_chapter_interval = 5
        # 最小章节数
        self.min_chapter_count = 3
        # 最大章节数
        self.max_chapter_count = 3000
        # 最小每章字数
        self.min_chapter_word_count = 500
        # 最大每章字数
        self.max_chapter_word_count = 10000
        # 最小章节间隔
        self.min_chapter_interval = 1
        # 最大章节间隔
        self.max_chapter_interval = 500

# 线索管理设置
class ClueSettings:
    def __init__(self):
        # 默认线索阈值（当章节数接近总章节数的阈值）
        self.default_clue_threshold = 3
        # 最小线索阈值
        self.min_clue_threshold = 1
        # 最大线索阈值
        self.max_clue_threshold = 100
        # 默认线索频率（线索平均出现频率，章节间隔）
        self.default_clue_frequency = 2

# Token限制设置
class TokenSettings:
    def __init__(self):
        # 大纲生成的最大token数
        self.max_tokens_outline = 3000
        # 章节生成的token系数（每字对应的token数）
        self.token_coefficient_chapter = 2
        # 线索提取的最大token数
        self.max_tokens_clue_extraction = 1500

# DeepSeek模型设置
class DeepSeekSettings:
    def __init__(self):
        # 是否启用思考模式
        self.enable_thinking = True
        # 思考模式的温度值
        self.thinking_temperature = 0.7
        # 思考模式的最大token数
        self.max_tokens_thinking = 2000

# 大纲生成设置
class OutlineGenerationSettings:
    def __init__(self):
        # 默认拆分次数（将大纲拆分成几段进行输出）
        self.default_split_count = 3
        # 最小拆分次数
        self.min_split_count = 1
        # 最大拆分次数
        self.max_split_count = 10
        # 骨架章节数（用于初始大纲生成）
        self.skeleton_chapter_count = 5
