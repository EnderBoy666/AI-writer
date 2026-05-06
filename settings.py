class OpenaiSettings():
    def __init__(self):
        self.url="http://127.0.0.1:11434/v1"
        self.api_key="ollama"
        self.model="qwen3.5:9b"
        self.timeout=1800
        self.add_token=50000
        self.retry=3

class WebSettings():
    def __init__(self):
        self.share=False
        self.port=7860
        self.server_name="0.0.0.0"

class NovelSettings():
    def __init__(self):
        self.max_total_chapters=1000
        self.min_total_chapters=0

        self.min_words=150
        self.max_words=30000

        self.min_slite_num=1
        self.max_slite_num=500