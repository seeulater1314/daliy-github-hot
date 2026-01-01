import requests
import json
import os
import base64
import hashlib
import hmac
import time
from datetime import datetime

# 配置部分 (实际运行时会从环境变量读取)
# 飞书 Webhook 地址
# 从环境变量获取，如果获取不到（比如本地运行），就使用后面的默认值或者 None
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
FEISHU_SECRET = os.getenv("FEISHU_SECRET")
# DeepSeek API (如果你想让AI写点评)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def get_github_trending():
    """
    修正版：获取过去 7 天内创建且最火的项目
    """
    from datetime import datetime, timedelta
    
    LIMIT = 10
    # 【关键修改】把 days=1 改成 days=7 或者 days=10
    # 这样能抓到最近一周发布的好项目，数据不再为空
    search_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 搜索条件：创建时间 > 7天前
    url = f"https://api.github.com/search/repositories?q=created:>{search_date}&sort=stars&order=desc&per_page={LIMIT}"
    
    # GitHub API 要求必须带 User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python/3.9",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        print(f"正在请求 GitHub API: {url}") # 方便调试
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            
            # 简单清洗数据格式，使其匹配之前的逻辑
            cleaned_items = []
            for item in items:
                cleaned_items.append({
                    'author': item['owner']['login'],
                    'name': item['name'],
                    'url': item['html_url'],
                    'description': item['description'],
                    'stars': item['stargazers_count'],
                    'language': item['language']
                })
            print(f"成功获取到 {len(cleaned_items)} 条数据")
            return cleaned_items
        else:
            print(f"接口请求失败，状态码: {resp.status_code}")
            print(resp.text) # 打印错误信息
            return []
            
    except Exception as e:
        print(f"抓取发生异常: {e}")
        return []

def ai_summarize(project_desc):
    """
    (可选) 调用 AI 用一句话犀利点评
    """
    if not DEEPSEEK_API_KEY:
        return project_desc # 如果没 Key，就直接返回原描述

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个毒舌程序员。请用中文一句话犀利点评这个GitHub项目，不要废话。"},
            {"role": "user", "content": f"项目描述: {project_desc}"}
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data)
        return resp.json()['choices'][0]['message']['content']
    except:
        return project_desc

def gen_sign(timestamp, secret):
    """
    飞书签名生成算法
    """
    # 拼接时间戳和密钥
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    # 使用 HMAC-SHA256 进行加密
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), 
        digestmod=hashlib.sha256
    ).digest()
    # 对结果进行 Base64 编码
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return sign


def send_to_feishu(content_list):
    """
    推送到飞书
    """
    if not FEISHU_WEBHOOK:
        print("未配置飞书 Webhook")
        return

    # 1. 获取当前时间戳（整数，单位秒）
    timestamp = str(int(time.time()))
    
    # 2. 生成签名 (如果配置了密钥)
    sign = None
    if FEISHU_SECRET:
        sign = gen_sign(timestamp, FEISHU_SECRET)

    # 构建飞书富文本消息卡片
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    elements = []
    for item in content_list:
        name = item.get('author') + " / " + item.get('name')
        url = item.get('url')
        desc = item.get('description', '暂无描述')
        stars = item.get('stars', 0)
        language = item.get('language', 'Unknown')
        
        # 这一步如果是实战，可以调用 ai_summarize(desc)
        # comment = ai_summarize(desc) 
        
        elements.append(f"⭐ **{stars}** | {language}\n[{name}]({url})\n> {desc}\n")

    card_content = "\n---\n".join(elements)
    
      # 3. 构建最终 payload
    payload = {
        "timestamp": timestamp, # 必填
        "sign": sign,           # 必填
        "msg_type": "interactive",
        "card": {
            # ... (这里面的内容跟之前一样) ...
             "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📅 GitHub 每日精选"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": card_content # 这里引用你之前生成的变量
                }
            ]
        }
    }

    # 发送请求
    resp = requests.post(FEISHU_WEBHOOK, json=payload)
    
    # 加上错误检查，万一签名不对能看到报错
    if resp.json().get("code") != 0:
        print(f"发送失败: {resp.json()}")
    else:
        print("推送成功！")

if __name__ == "__main__":
    projects = get_github_trending()
    if projects:
        send_to_feishu(projects)
    else:
        print("今日无数据")