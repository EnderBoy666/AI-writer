import requests
import os
import datetime
import re

from settings import OpenaiSettings
openai_settings=OpenaiSettings()

def filter_think_tags(text: str) -> str:
    """
    过滤 <think>...</think> 标签及其内部的所有内容
    支持：单行、多行、大小写不敏感、标签带属性（如 <think class="x">）
    """
    # 正则表达式：匹配 <think ...> 到 </think> 之间所有内容
    pattern = re.compile(r'<think.*?>.*?</think>', re.DOTALL | re.IGNORECASE)
    return pattern.sub('', text)

def generate(prompts, user,max_token):
    x = requests.post(
        url=f"{openai_settings.url}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_settings.api_key}"
        },
        json={
            "model": openai_settings.model,
            "messages": [{"role": user, "content": prompts}],
            "max_completion_tokens":max_token
        },
        timeout=openai_settings.timeout
    )
    if(x.json()["choices"][0]["message"]["content"]==""):
        print(f"[{datetime.datetime.now}]警告：AI返回值为空，即将重试。最大token:{max_token}")
        for i in range(openai_settings.retry):
            max_token+=openai_settings.add_token
            x = requests.post(
                url=f"{openai_settings.url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_settings.api_key}"
                },
                json={
                    "model": openai_settings.model,
                    "messages": [{"role": user, "content": prompts}],
                    "max_completion_tokens":max_token
                },
                timeout=openai_settings.timeout
            )
            if(x.json()["choices"][0]["message"]["content"]==""):
                print(f"[{datetime.datetime.now()}]警告：AI返回值为空，已重试{i+1}/{openai_settings.retry}。最大token:{max_token}")
            else:
                break
    if x.status_code == 200:
        x.json()["choices"][0]["message"]["content"]=filter_think_tags(x.json()["choices"][0]["message"]["content"])
    return x

def check_file(path):
    if os.path.exists(path):
        return True
    else:
        return False
    