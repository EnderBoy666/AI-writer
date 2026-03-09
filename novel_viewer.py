import gradio as gr
import sqlite3
from settings import DatabaseSettings

# 加载数据库设置
db_settings = DatabaseSettings()

# 数据库操作函数
def get_all_novels():
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, title, prompt, created_at FROM {db_settings.db_table} ORDER BY created_at DESC
    """)
    novels = cursor.fetchall()
    conn.close()
    return novels

def get_novel_by_id(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT title, outline, total_chapters FROM {db_settings.db_table} WHERE id = ?
    """, (novel_id,))
    novel = cursor.fetchone()
    conn.close()
    return novel

def get_novel_chapters(novel_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT id, chapter_number, chapter_title, created_at FROM {db_settings.chapter_table} WHERE novel_id = ? ORDER BY chapter_number ASC
    """, (novel_id,))
    chapters = cursor.fetchall()
    conn.close()
    return [list(chapter) for chapter in chapters]

def get_chapter_content(chapter_id):
    conn = sqlite3.connect(db_settings.db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT content FROM {db_settings.chapter_table} WHERE id = ?
    """, (chapter_id,))
    chapter = cursor.fetchone()
    conn.close()
    return chapter[0] if chapter else ""

# 创建Gradio界面
with gr.Blocks(title="小说查看器") as demo:
    gr.Markdown("# 小说查看器")
    
    # 小说列表
    novel_list = gr.Dataframe(
        label="小说列表",
        headers=["ID", "标题", "提示词", "创建时间"],
        datatype=["number", "str", "str", "str"],
        interactive=False
    )
    
    # 刷新按钮
    refresh_btn = gr.Button("刷新小说列表")
    
    # 小说详情
    with gr.Row():
        with gr.Column(scale=1):
            novel_selector = gr.Dropdown(
                label="选择小说",
                choices=[],
                interactive=True,
                allow_custom_value=True
            )
            chapter_list = gr.Dataframe(
                label="章节列表",
                headers=["ID", "章节编号", "章节标题", "创建时间"],
                datatype=["number", "number", "str", "str"],
                interactive=False
            )
        
        with gr.Column(scale=2):
            chapter_content = gr.Textbox(
                label="章节内容",
                lines=30,
                interactive=False
            )
    
    # 绑定函数
    def refresh_novel_list():
        novels = get_all_novels()
        return novels
    
    def update_novel_selector():
        novels = get_all_novels()
        return [(str(novel[0]), novel[1]) for novel in novels]
    
    def update_chapter_list(novel_id_str):
        try:
            # 调试信息
            print(f"update_chapter_list called with: {novel_id_str}")
            print(f"Type: {type(novel_id_str)}")
            
            if not novel_id_str:
                return []
            # 处理嵌套列表类型的输入，如 [['1', '《九霄劫》']]
            if isinstance(novel_id_str, list):
                # 处理多层嵌套列表
                while isinstance(novel_id_str, list) and len(novel_id_str) > 0:
                    print(f"Processing nested list: {novel_id_str}")
                    novel_id_str = novel_id_str[0]
            # 现在novel_id_str应该是字符串 '1' 或 ['1', '《九霄劫》']
            if isinstance(novel_id_str, list) and len(novel_id_str) > 0:
                # 格式为 ['1', '《九霄劫》']
                print(f"Processing inner list: {novel_id_str}")
                novel_id_str = novel_id_str[0]
            # 转换为整数
            try:
                novel_id = int(novel_id_str)
                print(f"Processing novel_id: {novel_id}")
                chapters = get_novel_chapters(novel_id)
                print(f"Found chapters: {chapters}")
                return chapters
            except (ValueError, TypeError) as e:
                print(f"Error converting to int: {e}")
                return []
        except Exception as e:
            print(f"Error in update_chapter_list: {e}")
            return []
    
    def load_chapter_content(chapter_row, evt: gr.SelectData):
        try:
            # 调试信息，查看chapter_row的格式
            print(f"chapter_row type: {type(chapter_row)}")
            print(f"chapter_row value: {chapter_row}")
            print(f"evt: {evt}")
            
            # 获取选中行的索引
            idx = evt.index[0]
            
            # 尝试不同的方式获取chapter_id
            if hasattr(chapter_row, 'iloc'):
                # 如果是pandas DataFrame
                chapter_id = int(chapter_row.iloc[idx, 0])
            elif isinstance(chapter_row, list):
                # 如果是列表
                if len(chapter_row) > 0:
                    if isinstance(chapter_row[0], list):
                        # 嵌套列表格式
                        chapter_id = int(chapter_row[idx][0])
                    else:
                        # 单层列表格式
                        chapter_id = int(chapter_row[0])
            else:
                # 其他格式
                return "无法获取章节内容：格式错误"
            
            content = get_chapter_content(chapter_id)
            print(f"Content length: {len(content)}")
            return content
        except Exception as e:
            print(f"Error in load_chapter_content: {e}")
            return f"加载章节内容失败：{str(e)}"
    
    # 绑定事件
    refresh_btn.click(
        fn=refresh_novel_list,
        outputs=novel_list
    )
    
    refresh_btn.click(
        fn=update_novel_selector,
        outputs=novel_selector
    )
    
    novel_selector.change(
        fn=update_chapter_list,
        inputs=novel_selector,
        outputs=chapter_list
    )
    
    chapter_list.select(
        fn=load_chapter_content,
        inputs=chapter_list,
        outputs=chapter_content
    )
    
    # 初始化
    demo.load(
        fn=refresh_novel_list,
        outputs=novel_list
    )
    
    demo.load(
        fn=update_novel_selector,
        outputs=novel_selector
    )

if __name__ == "__main__":
    demo.launch(server_port=7863, share=True)