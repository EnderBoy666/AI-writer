class DeepSeekSettings:
    def __init__(self):
        self.ds_path=r"./models/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

class CreateExamSettings:
    def __init__(self):
        self.db_path=r'./exam.db'

class QrSettings:
    def __init__(self):
        self.qr_path=r"./exam_data/qr"

class OllamaSettings:
    def __init__(self):
        self.model = "qwen3:8b"
        self.base_url = "http://localhost:11434"

class GradioSettings:
    def __init__(self):
        self.title = "小说大纲生成器"
        self.description = "输入提示词，生成小说大纲"
        self.theme = "default"
        self.allow_flagging = "never"

class DatabaseSettings:
    def __init__(self):
        self.db_path = r'./novel.db'
        self.db_table = 'novels'
        self.chapter_table = 'chapters'

class ChapterSettings:
    def __init__(self):
        self.default_word_count = 1000
        self.default_temperature = 0.7
        self.max_word_count = 5000
        self.min_temperature = 0.1
        self.max_temperature = 1.0

class OutlineSettings:
    def __init__(self):
        self.default_chapter_count = 5
        self.default_chapter_word_count = 1000
        self.min_chapter_count = 3
        self.max_chapter_count = 1000
        self.min_chapter_word_count = 200
        self.max_chapter_word_count = 5000

class ClueSettings:
    def __init__(self):
        self.default_clue_threshold = 3  # 当章节数接近总章节数的阈值
        self.min_clue_threshold = 1
        self.max_clue_threshold = 10
        self.default_clue_frequency = 2  # 线索平均出现频率（章节间隔）
