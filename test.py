from openai import OpenAI
client = OpenAI(api_key="ollama",base_url="http://127.0.0.1:11434/v1")

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"]
        }
    }
}]

response = client.chat.completions.create(
    model="qwen3.5:9b",
    messages=[{"role": "user", "content": "上海天气怎么样？"}],
    tools=tools,
    tool_choice="auto"
)

if response.choices[0].finish_reason == "tool_calls":
    tool_call = response.choices[0].message.tool_calls[0]
    # 直接拿到函数名和参数
    print(tool_call.function.name)       # "get_weather"
    print(tool_call.function.arguments)  # '{"city": "Shanghai"}'

def get_weather(city: str) -> str:
    """模拟一个天气查询接口，根据城市名返回天气"""
    # 实际开发中，这里应该是调用真实的天气API
    mock_data = {
        "Beijing": "晴，24°C，微风",
        "Shanghai": "多云，28°C，东南风3级",
        "Guangzhou": "雷阵雨，32°C，南风2级"
    }
    return mock_data.get(city, "抱歉，暂无该城市天气数据")