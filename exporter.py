import os
import re
from datetime import datetime
from database import get_novel_by_id, get_novel_chapters, get_chapter_by_id, get_novel_clues


class NovelExporter:
    """小说导出器，支持多种格式和排版选项"""
    
    def __init__(self, novel_id):
        """
        初始化导出器
        
        Args:
            novel_id: 小说 ID
        """
        self.novel_id = novel_id
        self.novel = get_novel_by_id(novel_id)
        if not self.novel:
            raise ValueError(f"小说不存在：{novel_id}")
        
        self.title = self.novel[1]
        self.prompt = self.novel[2]
        self.outline = self.novel[3]
        self.total_chapters = self.novel[4]
        self.chapter_word_count = self.novel[5]
        
        # 获取所有章节
        self.chapters = self._load_all_chapters()
        
        # 获取线索
        self.clues = get_novel_clues(novel_id)
    
    def _load_all_chapters(self):
        """加载所有章节内容"""
        chapter_list = get_novel_chapters(self.novel_id)
        chapters = []
        for chapter in chapter_list:
            chapter_data = get_chapter_by_id(chapter[0])
            if chapter_data:
                chapters.append({
                    'id': chapter_data[0],
                    'number': chapter_data[1],
                    'title': chapter_data[2],
                    'content': chapter_data[3]
                })
        # 按章节编号排序
        chapters.sort(key=lambda x: x['number'])
        return chapters
    
    def export_to_txt(self, output_path, include_outline=False, include_clues=False, 
                     chapter_format="standard", add_page_numbers=False):
        """
        导出为 TXT 格式
        
        Args:
            output_path: 输出文件路径
            include_outline: 是否包含大纲
            include_clues: 是否包含线索
            chapter_format: 章节格式 ("standard", "simple", "detailed")
            add_page_numbers: 是否添加页码
        """
        lines = []
        
        # 标题
        lines.append("=" * 50)
        lines.append(self.title)
        lines.append("=" * 50)
        lines.append("")
        
        # 基本信息
        lines.append(f"作者：AI 创作")
        lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.total_chapters:
            lines.append(f"总章节数：{self.total_chapters}")
        if self.chapter_word_count:
            lines.append(f"每章字数：{self.chapter_word_count}")
        lines.append("")
        
        # 大纲
        if include_outline:
            lines.append("-" * 50)
            lines.append("📋 小说大纲")
            lines.append("-" * 50)
            lines.append(self.outline)
            lines.append("")
            lines.append("")
        
        # 章节
        lines.append("-" * 50)
        lines.append("📖 正文章节")
        lines.append("-" * 50)
        lines.append("")
        
        page_number = 1
        for chapter in self.chapters:
            # 章节标题格式
            if chapter_format == "simple":
                lines.append(f"第{chapter['number']}章 {chapter['title']}")
            elif chapter_format == "detailed":
                lines.append("")
                lines.append("=" * 30)
                lines.append(f"第{chapter['number']}章 {chapter['title']}")
                lines.append("=" * 30)
            else:  # standard
                lines.append("")
                lines.append(f"第{chapter['number']}章 {chapter['title']}")
                lines.append("")
            
            # 章节内容
            lines.append(chapter['content'])
            lines.append("")
            lines.append("")
            
            # 添加页码
            if add_page_numbers:
                lines.append(f"--- 第 {page_number} 页 ---")
                lines.append("")
                page_number += 1
        
        # 线索
        if include_clues and self.clues:
            lines.append("")
            lines.append("-" * 50)
            lines.append("🔍 线索列表")
            lines.append("-" * 50)
            for clue in self.clues:
                clue_type = clue[2]
                clue_text = clue[1]
                first_chapter = clue[3]
                next_chapter = clue[4] if clue[4] else "未收束"
                lines.append(f"[{clue_type}] {clue_text}")
                lines.append(f"  首次出现：第{first_chapter}章")
                lines.append(f"  下次出现：第{next_chapter}章")
                lines.append("")
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path
    
    def export_to_markdown(self, output_path, include_outline=False, include_clues=False,
                          add_table_of_contents=True, use_heading_style=True):
        """
        导出为 Markdown 格式
        
        Args:
            output_path: 输出文件路径
            include_outline: 是否包含大纲
            include_clues: 是否包含线索
            add_table_of_contents: 是否添加目录
            use_heading_style: 是否使用标题样式
        """
        lines = []
        
        # 标题
        if use_heading_style:
            lines.append(f"# {self.title}")
        else:
            lines.append(self.title)
            lines.append("=" * len(self.title))
        lines.append("")
        
        # 基本信息
        lines.append("**作者**: AI 创作")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.total_chapters:
            lines.append(f"**总章节数**: {self.total_chapters}")
        if self.chapter_word_count:
            lines.append(f"**每章字数**: {self.chapter_word_count}")
        lines.append("")
        
        # 目录
        if add_table_of_contents:
            lines.append("## 📑 目录")
            lines.append("")
            for chapter in self.chapters:
                # Markdown 锚点链接
                anchor = f"第{chapter['number']}章-{self._slugify(chapter['title'])}"
                lines.append(f"- [第{chapter['number']}章 {chapter['title']}](#{anchor})")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # 大纲
        if include_outline:
            lines.append("## 📋 小说大纲")
            lines.append("")
            lines.append(self.outline)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # 章节
        lines.append("## 📖 正文章节")
        lines.append("")
        
        for chapter in self.chapters:
            if use_heading_style:
                lines.append(f"### 第{chapter['number']}章 {chapter['title']}")
            else:
                lines.append(f"第{chapter['number']}章 {chapter['title']}")
                lines.append("-" * 30)
            
            lines.append("")
            # 处理内容中的段落
            content = chapter['content']
            # 确保段落之间有适当的空行
            paragraphs = content.split('\n')
            for para in paragraphs:
                if para.strip():
                    lines.append(para)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # 线索
        if include_clues and self.clues:
            lines.append("## 🔍 线索列表")
            lines.append("")
            for clue in self.clues:
                clue_type = clue[2]
                clue_text = clue[1]
                first_chapter = clue[3]
                next_chapter = clue[4] if clue[4] else "未收束"
                lines.append(f"**[{clue_type}]** {clue_text}")
                lines.append(f"- 首次出现：第{first_chapter}章")
                lines.append(f"- 下次出现：第{next_chapter}章")
                lines.append("")
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path
    
    def _slugify(self, text):
        """将文本转换为适合 URL 的格式"""
        # 移除特殊字符，保留中文
        text = re.sub(r'[^\w\u4e00-\u9fff-]', '', text)
        return text.lower()
    
    def export_to_html(self, output_path, include_outline=False, include_clues=False,
                      use_css_style=True, responsive=True):
        """
        导出为 HTML 格式
        
        Args:
            output_path: 输出文件路径
            include_outline: 是否包含大纲
            include_clues: 是否包含线索
            use_css_style: 是否使用 CSS 样式
            responsive: 是否使用响应式设计
        """
        html_parts = []
        
        # HTML 头部
        html_parts.append('<!DOCTYPE html>')
        html_parts.append('<html lang="zh-CN">')
        html_parts.append('<head>')
        html_parts.append('    <meta charset="UTF-8">')
        if responsive:
            html_parts.append('    <meta name="viewport" content="width=device-width, initial-scale=1.0">')
        html_parts.append(f'    <title>{self.title}</title>')
        
        if use_css_style:
            html_parts.append('    <style>')
            html_parts.append('        body { font-family: "Microsoft YaHei", Arial, sans-serif; line-height: 1.8; max-width: 800px; margin: 0 auto; padding: 20px; }')
            html_parts.append('        .title { text-align: center; font-size: 2em; margin-bottom: 20px; }')
            html_parts.append('        .meta { color: #666; margin-bottom: 30px; }')
            html_parts.append('        .toc { background: #f5f5f5; padding: 20px; margin-bottom: 30px; border-radius: 5px; }')
            html_parts.append('        .toc a { text-decoration: none; color: #333; }')
            html_parts.append('        .toc a:hover { text-decoration: underline; }')
            html_parts.append('        .outline { background: #fff9e6; padding: 20px; margin-bottom: 30px; border-left: 4px solid #f0ad4e; }')
            html_parts.append('        .chapter { margin-bottom: 40px; }')
            html_parts.append('        .chapter-title { font-size: 1.5em; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }')
            html_parts.append('        .chapter-content { text-indent: 2em; text-align: justify; }')
            html_parts.append('        .clues { background: #e6f3ff; padding: 20px; margin-top: 30px; border-left: 4px solid #428bca; }')
            html_parts.append('        .clue-item { margin-bottom: 15px; }')
            html_parts.append('        .clue-type { font-weight: bold; color: #428bca; }')
            html_parts.append('        hr { border: none; border-top: 1px solid #ddd; margin: 30px 0; }')
            if responsive:
                html_parts.append('        @media (max-width: 600px) { body { padding: 10px; } .title { font-size: 1.5em; } }')
            html_parts.append('    </style>')
        
        html_parts.append('</head>')
        html_parts.append('<body>')
        
        # 标题
        html_parts.append(f'    <h1 class="title">{self.title}</h1>')
        
        # 基本信息
        html_parts.append('    <div class="meta">')
        html_parts.append('        <p><strong>作者:</strong> AI 创作</p>')
        html_parts.append(f'        <p><strong>生成时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>')
        if self.total_chapters:
            html_parts.append(f'        <p><strong>总章节数:</strong> {self.total_chapters}</p>')
        if self.chapter_word_count:
            html_parts.append(f'        <p><strong>每章字数:</strong> {self.chapter_word_count}</p>')
        html_parts.append('    </div>')
        
        # 目录
        html_parts.append('    <div class="toc">')
        html_parts.append('        <h2>📑 目录</h2>')
        html_parts.append('        <ul>')
        for chapter in self.chapters:
            html_parts.append(f'            <li><a href="#chapter{chapter["number"]}">第{chapter["number"]}章 {chapter["title"]}</a></li>')
        html_parts.append('        </ul>')
        html_parts.append('    </div>')
        
        # 大纲
        if include_outline:
            html_parts.append('    <div class="outline">')
            html_parts.append('        <h2>📋 小说大纲</h2>')
            html_parts.append(f'        <p>{self.outline.replace(chr(10), "<br>")}</p>')
            html_parts.append('    </div>')
            html_parts.append('    <hr>')
        
        # 章节
        html_parts.append('    <h2>📖 正文章节</h2>')
        
        for chapter in self.chapters:
            html_parts.append(f'    <div class="chapter" id="chapter{chapter["number"]}">')
            html_parts.append(f'        <h3 class="chapter-title">第{chapter["number"]}章 {chapter["title"]}</h3>')
            html_parts.append(f'        <div class="chapter-content">')
            
            # 处理内容段落
            paragraphs = chapter['content'].split('\n')
            for para in paragraphs:
                if para.strip():
                    html_parts.append(f'            <p>{para}</p>')
            
            html_parts.append('        </div>')
            html_parts.append('    </div>')
            html_parts.append('    <hr>')
        
        # 线索
        if include_clues and self.clues:
            html_parts.append('    <div class="clues">')
            html_parts.append('        <h2>🔍 线索列表</h2>')
            for clue in self.clues:
                clue_type = clue[2]
                clue_text = clue[1]
                first_chapter = clue[3]
                next_chapter = clue[4] if clue[4] else "未收束"
                html_parts.append(f'        <div class="clue-item">')
                html_parts.append(f'            <p><span class="clue-type">[{clue_type}]</span> {clue_text}</p>')
                html_parts.append(f'            <p>首次出现：第{first_chapter}章 | 下次出现：第{next_chapter}章</p>')
                html_parts.append(f'        </div>')
            html_parts.append('    </div>')
        
        html_parts.append('</body>')
        html_parts.append('</html>')
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_parts))
        
        return output_path
    
    def get_chapter_count(self):
        """获取章节数量"""
        return len(self.chapters)
    
    def get_total_word_count(self):
        """获取总字数"""
        total = 0
        for chapter in self.chapters:
            total += len(chapter['content'])
        return total


def export_novel(novel_id, format_type, output_dir="./exports", **kwargs):
    """
    导出小说的便捷函数
    
    Args:
        novel_id: 小说 ID
        format_type: 导出格式 ("txt", "md", "html")
        output_dir: 输出目录
        **kwargs: 传递给对应导出函数的其他参数
    
    Returns:
        导出文件路径
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建导出器
    exporter = NovelExporter(novel_id)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^\w\u4e00-\u9fff]', '', exporter.title)
    
    if format_type == "txt":
        filename = f"{safe_title}_{timestamp}.txt"
        filepath = os.path.join(output_dir, filename)
        return exporter.export_to_txt(filepath, **kwargs)
    
    elif format_type == "md":
        filename = f"{safe_title}_{timestamp}.md"
        filepath = os.path.join(output_dir, filename)
        return exporter.export_to_markdown(filepath, **kwargs)
    
    elif format_type == "html":
        filename = f"{safe_title}_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)
        return exporter.export_to_html(filepath, **kwargs)
    
    else:
        raise ValueError(f"不支持的导出格式：{format_type}")
