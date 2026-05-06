import gradio as gr
import generate
import json

#设置
from settings import OpenaiSettings,WebSettings,NovelSettings
openai_settings=OpenaiSettings()
web_settings=WebSettings()
novel_settings=NovelSettings()

#生成大纲
def create_outline(prompts,total_chapters,slite_num,node_num,max_token,better_outline):
    status="正在生成简介...\n"
    yield status
    outline={
        "name":"",
        "introduction":"",
        "total_outline":"",
        "total_chapters":total_chapters,
        "chapter_outline":[],
        "enities":[]
    }
    x=generate.generate(f"""请根据一下这段提示词生成一个小说的简介，要求包含以下内容:
                        1.输出格式为：第一行为文章标题，随后为文章的简介,简介大约300字
                        2.禁用一切markdown格式，禁用其他所有输出
                        提示词为:{prompts}"""
        ,"user",max_token)
    if x.status_code == 200:
        outline["name"] = x.json()["choices"][0]["message"]["content"].split("\n")[0]
        outline["introduction"] = x.json()["choices"][0]["message"]["content"]
        status+=x.json()["choices"][0]["message"]["content"]
        yield status

    else:
        return f"{x.status_code}:{x.text}"

    status+="\n开始生成总纲...\n"
    x=generate.generate(f"""请跟据以下要求和提示词生成一份小说大纲
                        1.分为{node_num}各节点，总共预计为{total_chapters}章
                        2.输出格式为：节点x（第a章-第b章）：内容。
                        3.每一个节点应包含情节，人物变化等信息
                        4.禁用markdown和其他多余输出。关键实体必须给出名称，大纲不能过于笼统，尽量具体详细，遵循提示词
                        5.在生成完节点后，在生成一段世界设定与人物设定
                        6.用户提示词：{prompts}
                        7.小说简介：{outline['introduction']}
                        ""","user",max_token)
    if x.status_code == 200:
        outline["total_outline"] = x.json()["choices"][0]["message"]["content"]
        status+=x.json()["choices"][0]["message"]["content"]
        yield status

    else:
        return f"{x.status_code}:{x.text}"
    
    if(better_outline==True):
        status+="\n正在提取实体名单\n"
        yield status
        prompts=f"请从大纲中提取出关键实体名单，要求：每一行一个实体名，重复的实体（如别名，代号等）只用输出一个，禁用任何markdown和其他多于输出.大纲如下{outline['total_outline']}"
        x=generate.generate(prompts,user="user",max_token=max_token)
        if x.status_code == 200:
            enities=x.json()["choices"][0]["message"]["content"].split("\n")
            status+=x.json()["choices"][0]["message"]["content"]
            yield status
        else:
            return f"{x.status_code}:{x.text}"
        for i in range(len(enities)):
            status+=f"\n正在提取实体{enities[i]}的信息({i+1}/{len(enities)})\n"
            yield status
            prompts=f"请在以下大纲中寻找和实体有关的信息,可以适当扩写但不能偏离大纲，实体名{enities[i]}。输出格式：实体每一个变化占一行，第一行为初始状态。格式为‘第x章’-‘第y章’：内容。禁用一切markdown格式和其他多余输出。大纲如下:{outline["total_outline"]}"
            x=generate.generate(prompts=prompts,user="user",max_token=max_token)
            if x.status_code == 200:
                outline["enities"].append(x.json()["choices"][0]["message"]["content"])
                status+=x.json()["choices"][0]["message"]["content"]
                yield status
            else:
                return f"{x.status_code}:{x.text}"
        status+="\n开始生成章节大纲...\n"
    yield status

    for i in range(slite_num):
        status+=f"\n当前拆分{i+1}/{slite_num}:\n"
        yield status
        prompts=f"""请跟据以下要求和提示词生成一份的章节大纲
                        1.整本小说总共预计为{total_chapters}章.
                        2.注意：你生成的不是某一本小说，而是其中的一部分。你只需要生成按照拆分次数分配后的一小部分。节点为情节节点数，与拆分次数无关
                        3.输出格式为：第一行为章节名：章节标题，随后转行输出内容。最后对后面的章节进行一小段指导文字。如果是最后一次拆分就不用编写指导文字
                        4.每一个章节应包含情节，人物，地点等信息
                        5.禁用markdown和其他多余输出,生成章节大纲而不是一整章的内容
                        6.用户提示词：{prompts}
                        7.小说简介：{outline['introduction']}
                        8.小说总纲：{outline["total_outline"]}
                        9.当前位于第{i+1}次拆分，共拆分{slite_num}次
                        """
        if(i!=0):
            prompts+=f"\n10.上一段章节大纲：{outline['chapter_outline'][i-1]}"
        if(i!=slite_num-1):
            prompts+=f"\n11.你需要生成的章节大纲范围为{int(total_chapters/slite_num*i)+1}-{int(total_chapters/slite_num*(i+1))}\n"
        else:
            prompts+=f"\n11.你需要生成的章节大纲范围为{int(total_chapters/slite_num*i)+1}-{total_chapters}\n"
        if(i==slite_num-1):
            prompts+=f"\n注意：小说已到结尾结尾部分，此为最后一次拆分"
        #print(prompts)
        x=generate.generate(prompts,"user",max_token)
        if x.status_code == 200:
            outline["chapter_outline"].append(x.json()["choices"][0]["message"]["content"])
            status+=x.json()["choices"][0]["message"]["content"]
            yield status

        else:
            return f"{x.status_code}:{x.text}"
        
        #print(outline["chapter_outline"])
        if(better_outline==True):
            status+="\n正在查找有关实体...\n"
            yield status
            prompts=f"请从以下下章节大纲中找出是否有和以下实体有关的信息。章节大纲如下{x.json()["choices"][0]["message"]["content"]},输出格式：返回对应的实体的数字id（例如给出的实体为'1.青云宗'就返回1),每一行有且仅有一个数字id\n禁用一切markdown格式和多余输出"
            for j in range(len(enities)):
                prompts+=f"{j}.{enities[j]}\n"
            x=generate.generate(prompts=prompts,user="user",max_token=max_token)
            if x.status_code == 200:
                chapter_enities=x.json()["choices"][0]["message"]["content"].split("\n")
                status+=x.json()["choices"][0]["message"]["content"]
                status+="\n正在优化大纲\n"
                yield status
            else:
                return f"{x.status_code}:{x.text}"
            
            if(chapter_enities[0].isdigit()==False):
                x=generate.generate(prompts=f"请以每行一个数字id的格式输出，原输出为{chapter_enities},实体列表为{enities}",user="user",max_token=max_token)
                if x.status_code == 200:
                    chapter_enities=x.json()["choices"][0]["message"]["content"].split("\n")
                    status+=x.json()["choices"][0]["message"]["content"]
                    status+="\n正在优化大纲\n"
                    yield status
                else:
                    return f"{x.status_code}:{x.text}"
            prompts=f"请根据以下实体的信息，优化这一段章节大纲，要求：\n1.遵循总纲和章节大纲，对章节大纲中与总纲和实体信息不合理的地方进行矫正即可\n2.禁用markdown格式和其余多余输出\n3.输出格式：与给出的章节大纲相同\n总昂如下:{outline['total_outline']}\n章节大纲如下{outline['chapter_outline'][i]}"
            for j in range(len(chapter_enities)):
                prompts+=f"\n{outline["enities"][int(chapter_enities[j])]}"
            print(prompts)
            x=generate.generate(prompts,"user",max_token)
            if x.status_code == 200:
                outline["chapter_outline"][i]=x.json()["choices"][0]["message"]["content"]
                status+=x.json()["choices"][0]["message"]["content"]
                yield status
            else:
                return f"{x.status_code}:{x.text}"

    status+="\n正在保存..."
    yield status
    with open("data/novel.json","r",encoding="utf-8") as file:
        novel=json.load(file)

    with open(f"data/novels/{outline['name']}.json","w",encoding="utf-8") as f:
        novel_t={"outline":outline,"chapters":[]}
        novel_json = json.dumps(novel_t, ensure_ascii=False, indent=4)
        f.write(novel_json)
    
    with open("data/novel.json","w",encoding="utf-8") as file:
        novel["novel_count"]+=1
        novel["novels"].append(outline["name"])
        novel_new=json.dumps(novel,ensure_ascii=False,indent=4)
        file.write(novel_new)
    status+="\n保存成功！\n"
    yield status

#创建章节
def create_chapter(novel_id,latest_chapter,create_chapter_num,extra_prompts,max_token,word_count,better_chapter):
    with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    status="开始创建章节...\n"
    yield status
    for i in range(create_chapter_num):
        chapter_prompts=f"""你是一名专业的小说家。请根据以下要求，生成一章小说.本章大约有{word_count}字
                          1.小说共有{novel_info["outline"]["total_chapters"]}章，当编写的是{latest_chapter+1}章
                          2.请勿输出重复内容，避免叙事平铺直叙，确保上下文连贯，同时一切遵循大纲，不要过度偏离
                          3.输出格式为：第一行为'第 x 章'：章节标题
                          4.禁用一切 markdown 格式，直接输出文本，以流畅的中文输出
                          5.小说总纲:{novel_info["outline"]["total_outline"]}
                          6.当前章节大纲:{novel_info["outline"]["chapter_outline"][int((latest_chapter+1)/len(novel_info["outline"]["chapter_outline"]))]}
                          7.用户附加提示词:{extra_prompts}"""
        if(latest_chapter!=0):
            chapter_prompts+=f"\n8.上一章内容:{novel_info["chapters"][latest_chapter-1]}"
        x=generate.generate(chapter_prompts,user="user",max_token=max_token)
        #print(chapter_prompts)
        if x.status_code == 200:
            novel_info["chapters"].append({"title":x.json()["choices"][0]["message"]["content"].split("\n")[0],"content":x.json()["choices"][0]["message"]["content"]})
            status+=x.json()["choices"][0]["message"]["content"]
            yield status
        else:
            return f"{x.status_code}:{x.text}"
        status+=f"\n已生成了第{latest_chapter}章，内容如下:\n{x.json()["choices"][0]["message"]["content"]}\n"
        if(better_chapter==True):
            prompts="请根据总纲和章节内容是否大纲检查本章内容"
        latest_chapter+=1
        with open(f"data/novels/{novel_id}.json","w",encoding="utf-8") as file:
            novel_new=json.dumps(novel_info,ensure_ascii=False,indent=4)
            file.write(novel_new)
        status+="\n保存成功！\n"
        yield status

#获取小说信息
def get_novels(dropdown):
    with open(f"data/novel.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    dropdown=gr.Dropdown(choices=novel_info["novels"])
    return dropdown

def get_novel_introduction(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        return novel_info["outline"]["introduction"]

def get_novel_chapter_outline(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        chapter_outline=[]
        for i in range(len(novel_info["outline"]["chapter_outline"])):
            chapter_outline.append([i,novel_info["outline"]["chapter_outline"][i]])
        return chapter_outline
    
def get_novel_total_outline(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        return novel_info["outline"]["total_outline"]
    
def get_novel_json(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        return novel_info

def get_lastest_chapter(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        return len(novel_info["chapters"])
    
def get_chapter_list(novel_id):
    if(generate.check_file(f"data/novels/{novel_id}.json")):
        with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
            novel_info=json.load(file)
        chapter_title=[]
        for i in range(len(novel_info["chapters"])):
            chapter_title.append(novel_info["chapters"][i]["title"])
        return chapter_title

def choose_chapter(novel_id,table,evt:gr.SelectData):
    col_index = evt.index[0]
    with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    #print(col_index)
    return novel_info["chapters"][col_index]["content"]

def choose_del_chapter(novel_id,table,evt:gr.SelectData):
    col_index = evt.index[0]
    with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    #print(col_index)
    return [col_index,novel_info["chapters"][col_index]["title"]]

#删除
def del_novel(novel_id):
    with open(f"data/novel.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    novel_info["novels"].remove(novel_id)
    with open(f"data/novel.json","w",encoding="utf-8") as file:
        novel_new=json.dumps(novel_info,ensure_ascii=False,indent=4)
        file.write(novel_new)
    return f"已成功删除小说{novel_id}"

def del_chapter(novel_id,chapter_id):
    with open(f"data/novels/{novel_id}.json","r",encoding="utf-8") as file:
        novel_info=json.load(file)
    novel_info["chapters"].pop(chapter_id[0][0])
    with open(f"data/novels/{novel_id}.json","w",encoding="utf-8") as file:
        novel_new=json.dumps(novel_info,ensure_ascii=False,indent=4)
        file.write(novel_new)
    return f"已成功删除章节{chapter_id[1][0]}"

#页面
with gr.Blocks() as app:
    with gr.Tab(label="生成大纲"):
        with gr.Row():
            with gr.Column():
                prompts=gr.Textbox(label="输入提示词")
                total_chapters=gr.Slider(label="总章节数",minimum=novel_settings.min_total_chapters,maximum=novel_settings.max_total_chapters,value=25)
                node_num=gr.Slider(label="情节节点数",minimum=novel_settings.min_slite_num,maximum=novel_settings.max_slite_num,value=5)
                slite_num=gr.Slider(label="拆分次数",minimum=novel_settings.min_slite_num,maximum=novel_settings.max_slite_num,value=1)
                better_outline=gr.Checkbox(label="是否开启更好的大纲生成（可能非常耗token)")
                max_token=gr.Slider(label="最大token",minimum=100000,maximum=2500000,value=130000)
                create_outline_btn=gr.Button(value="生成大纲")
            with gr.Column():
                outline_out_status=gr.Textbox(label="生成状态")
                create_outline_btn.click(fn=create_outline,inputs=[prompts,total_chapters,slite_num,node_num,max_token,better_outline],outputs=outline_out_status)
    with gr.Tab(label="小说管理",):        
        with gr.Row():
            novel_id=gr.Dropdown(label="请选择小说",type="value")
            refresh_novel_list=gr.Button(value="点击刷新小说列表")
            refresh_novel_list.click(fn=get_novels,inputs=[novel_id],outputs=novel_id)
        with gr.Accordion(label="小说详情"):
            with gr.Row():
                with gr.Column():            
                    gr.Textbox(value=get_novel_introduction,inputs=[novel_id],every=0.5,label="简介")
                    gr.Textbox(value=get_novel_total_outline,inputs=[novel_id],every=0.5,label="总纲")
                    gr.List(value=get_novel_chapter_outline,inputs=[novel_id],every=0.5,label="章节大纲",headers=["ID","内容"]) 
                with gr.Column():
                    novel_json=gr.JSON(label="小说json文件",max_height=800)
                    novel_id.change(fn=get_novel_json,inputs=[novel_id],outputs=novel_json)
        with gr.Accordion(label="章节生成"):
            with gr.Row():
                with gr.Column():
                    latest_chapter=gr.Number(value=get_lastest_chapter,inputs=[novel_id],every=0.5,label="最新章节")
                    chapter_prompts=gr.Textbox(label="附加提示词")
                    chapter_max_toekn=gr.Slider(label="最大token",minimum=100000,maximum=4500000,value=400000)
                    chapter_count=gr.Slider(label="批量创建章节数",minimum=1,maximum=1500,value=1)
                    word_count=gr.Slider(label="章节字数",minimum=150,maximum=10000,value=2000)
                    better_chapter=gr.Checkbox(label="是否开启更好的章节生成(可能非常耗token)")
                    create_chapter_btn=gr.Button(value="创建章节")
                with gr.Column():
                    chapter_create_status=gr.Textbox(label="创建章节状态")
                    create_chapter_btn.click(fn=create_chapter,inputs=[novel_id,latest_chapter,chapter_count,chapter_prompts,chapter_max_toekn,word_count,better_chapter],outputs=chapter_create_status)
        with gr.Accordion("查看章节"):
            with gr.Accordion("章节列表"):
                with gr.Row():
                    with gr.Column():
                        chapter_list=gr.DataFrame(value=get_chapter_list,inputs=[novel_id],every=0.5,label="章节列表",headers=["title"])
                    with gr.Column():
                        chapter_content=gr.Textbox(label="章节内容")
                        chapter_list.select(fn=choose_chapter,inputs=[novel_id,chapter_list],outputs=chapter_content)
        with gr.Accordion("危险区域",open=False):
            del_status=gr.Textbox(label="删除状态")
            del_novel_btn=gr.Button(value="删除小说")
            with gr.Row():
                choose_chapter_id=gr.Dataframe(label="所选章节",type="array")
                del_chapter_btn=gr.Button(value="删除章节")
                chapter_list.select(fn=choose_del_chapter,inputs=[novel_id,chapter_list],outputs=[choose_chapter_id])
            del_novel_btn.click(fn=del_novel,inputs=[novel_id],outputs=del_status)
            del_chapter_btn.click(fn=del_chapter,inputs=[novel_id,choose_chapter_id],outputs=del_status)

app.launch(share=web_settings.share,server_port=web_settings.port,server_name=web_settings.server_name)