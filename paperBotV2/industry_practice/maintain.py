import re
import ast
import os
import random
import json
import argparse
import requests
import generate_industry_html
import datetime
import sys
import re

# 添加当前目录到系统路径，以便导入自定义模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 直接定义配置项
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录（向上两层）
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
# 仓库根加入 sys.path，复用包级飞书通知模块（paperBotV2/notify.py）
sys.path.insert(0, PROJECT_ROOT)
from paperBotV2 import notify

# 直接定义配置项
DATA_DIR = os.path.join(BASE_DIR, "data")
ARTICLE_CSV_FILE = os.path.join(DATA_DIR, "article.csv")
ARTICLE_JSON_FILE = os.path.join(DATA_DIR, "article.json")
# 正确指向根目录的README.md
README_FILE = os.path.join(PROJECT_ROOT, "README.md")

# 支持多个飞书URL，使用逗号分隔
FEISHU_URLS = notify.parse_urls(os.environ.get("FEISHU_URL", ""))

def set_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", "-i", type=str, help="input issue JSON string", required=False)
    parser.add_argument("--file", "-f", type=str, help="input issue JSON file", required=False)
    args = parser.parse_args()
    
    # 确保至少提供了一个参数
    if not args.issue and not args.file:
        parser.error("Either --issue or --file must be provided")
        
    # 如果提供了文件参数，读取文件内容
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                args.issue = f.read()
        except Exception as e:
            parser.error(f"Failed to read file {args.file}: {e}")
            
    return args


def parse_issue(issue):
    try:
        issue = issue.replace("\\n", "").replace("\\r", "")
        info = ast.literal_eval(issue)
        print(info)
        assert isinstance(info, list)
        assert len(info) > 0 and info[0].get("公司") and info[0].get("内容") and info[0].get("标签") and info[0].get("时间") and info[0].get("链接")
    except Exception as exc:
        raise ValueError(f"issue 数据格式错误（需含 公司/内容/标签/时间/链接 字段）: {exc}") from exc
    return info

def update_json_and_csv(args):
    """更新JSON和CSV文件中的文章数据
    
    读取现有的JSON和CSV文件，添加新的文章数据，并保存更新后的文件
    """
    print("[+] 开始更新JSON和CSV文件...")
    
    try:
        # 解析新的文章数据
        new_items = parse_issue(args.issue)
        print(f"[+] 解析到 {len(new_items)} 条新文章数据")
        
        # 读取现有的JSON数据
        existing_json_data = []
        if os.path.exists(ARTICLE_JSON_FILE):
            with open(ARTICLE_JSON_FILE, 'r', encoding='utf-8') as f:
                existing_json_data = json.load(f)
        
        # 读取现有的CSV数据
        existing_csv_data = []
        if os.path.exists(ARTICLE_CSV_FILE):
            with open(ARTICLE_CSV_FILE, 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                existing_csv_data = list(reader)
        
        # 处理并添加新的数据
        for item in new_items:
            # 检查是否已经存在相同的文章
            is_duplicate = False
            for existing_item in existing_json_data:
                if existing_item.get('link') == item.get('链接') or existing_item.get('title') == item.get('内容'):
                    is_duplicate = True
                    print(f"[-] 跳过重复文章: {item.get('内容')}")
                    break
            
            if not is_duplicate:
                # 格式化JSON数据
                json_item = {
                    "company": item.get('公司'),
                    "link": item.get('链接'),
                    "title": item.get('内容'),
                    "tags": [tag.strip() for tag in item.get('标签').split(',')],
                    "date": item.get('时间')
                }
                existing_json_data.append(json_item)
                
                # 格式化CSV数据
                csv_item = {
                    "公司": item.get('公司'),
                    "链接": item.get('链接'),
                    "标题": item.get('内容'),
                    "标签": item.get('标签'),
                    "日期": item.get('时间')
                }
                existing_csv_data.append(csv_item)
                
                print(f"[+] 添加新文章: {item.get('内容')}")
        
        # 按时间排序数据（最新的在前）
        existing_json_data.sort(key=lambda x: generate_industry_html.get_sortable_date(x.get("date", x.get("时间", ""))), reverse=True)
        existing_csv_data.sort(key=lambda x: generate_industry_html.get_sortable_date(x["日期"]), reverse=True)
        
        # 保存更新后的JSON文件
        with open(ARTICLE_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_json_data, f, ensure_ascii=False, indent=2)
        print(f"[+] JSON文件更新成功: {ARTICLE_JSON_FILE}")
        
        # 保存更新后的CSV文件
        with open(ARTICLE_CSV_FILE, 'w', encoding='utf-8', newline='') as f:
            fieldnames = ['公司', '链接', '标题', '标签', '日期']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_csv_data)
        print(f"[+] CSV文件更新成功: {ARTICLE_CSV_FILE}")
        
        return True
    except Exception as e:
        print(f"[-] 更新JSON和CSV文件失败: {e}")
        import traceback
        print(f"[-] 错误详情: {traceback.format_exc()}")
        return False

def update_readme(args, info=None):
    print("[+] Add new items into readme...")
    if info is None:
        info = parse_issue(args.issue)
    with open(README_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 查找表格位置
    table_title = "## 大厂实践文章"
    table_index = None
    for i, line in enumerate(lines):
        if table_title in line.strip():
            table_index = i
            break

    # 如果找到表格位置，则更新表格
    if table_index is not None:
        j = table_index + 2
        while j < len(lines) and not re.search(r"\|(\s-+\s\|)+", lines[j]):
            j += 1
        index = j + 1
        newlines = []
        for item in info:
            newline = "".join("| {} | [{}]({}) | {} | {} |\n".format(
                item["公司"], item["内容"], item["链接"], item["标签"], item["时间"]))
            newlines.append(newline)
        lines = lines[:index] + newlines + lines[index:]
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Add items Done!")
        return True
    else:
        print("[-] README 表格未找到，跳过 README 更新")
        return False

def update_message(args):
    "更新消息通知"
    print("[+] 开始更新消息通知...")
    
    try:
        # 如果没有设置FEISHU_URLS，跳过发送消息
        if not FEISHU_URLS:
            print("[-] FEISHU_URL未设置或为空，跳过发送消息")
            return
        
        # 解析issue数据
        infos = parse_issue(args.issue)
        print(f"[+] 解析到 {len(infos)} 条新文章数据")
        
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        title = f"🌸大厂实践文章自动更新@{today}"
        content = []
        for info in infos:
            emoji = random.choice("🌱🌿🍀🪴🎋🍃🪷🌸✨")
            meta_info = f"🥹 {info['公司']}  📆 {info['时间']}  🍉 {info['标签']}"
            info_title = f"✅ {info['内容']}"
            line_len = max(len(meta_info), len(info_title))
            sepline = emoji * line_len
            content.append(
                [{
                    "tag": "text",
                    "text": ""
                }]
            )
            # content.append(
            #     [{
            #         "tag": "text",
            #         "text": sepline
            #     }]
            # )
            # content.append(
            #     [{
            #         "tag": "text",
            #         "text": ""
            #     }]
            # )
            content.append(
                [{
                    "tag": "text",
                    "text": meta_info
                }]
            )
            content.append(
                [{
                    "tag": "text",
                    "text": ""
                }]
            )
            content.append(
                [{
                    "tag": "a",
                    "text": info_title,
                    "href": f"{info['链接']}"
                }]
            )
            content.append(
                [{
                    "tag": "text",
                    "text": ""
                }]
            )
        content.append(
            [{
                "tag": "text",
                "text": "-----",
            }]
        )
        content.append(
            [{
                "tag": "a",
                "text": "➡️ 点击查看完整大厂实践文章列表",
                "href": "https://github.com/Doragd/Algorithm-Practice-in-Industry?tab=readme-ov-file#%E5%A4%A7%E5%8E%82%E5%AE%9E%E8%B7%B5%E6%96%87%E7%AB%A0newest%E7%BD%91%E9%A1%B5%E7%89%88%E6%9C%AC%E7%82%B9%E5%87%BB%E6%9F%A5%E7%9C%8B"
            }]
        )
        send_feishu_message(title, content)
        print("[+] 消息通知发送成功！")
    except Exception as e:
        print(f"[-] 更新消息通知失败: {e}")
        import traceback
        print(f"[-] 错误详情: {traceback.format_exc()}")

def send_feishu_message(title, content, urls=None):
    # 如果没有指定URL列表，使用默认的FEISHU_URLS
    if urls is None:
        urls = FEISHU_URLS

    # 如果没有有效的飞书URL，直接返回
    if not urls:
        print("⚠️ 没有有效的飞书URL，跳过发送消息")
        return

    # notify.send 失败（任一URL）会上抛，由调用方 update_message 捕获打印
    notify.send(urls, notify.text_post(title, content))



def update_industry_practice_page():
    """更新大厂实践文章页面（同模块直调 generate_industry_html，替代 subprocess）"""
    print("[+] 开始更新大厂实践文章页面...")
    try:
        generate_industry_html.generate_industry_html()
        print("[+] 更新大厂实践文章页面成功!")
        return True
    except Exception as e:
        print(f"[-] 更新大厂实践文章页面失败: {e}")
        import traceback
        print(f"[-] 错误详情: {traceback.format_exc()}")
        return False


def main():
    args = set_args()
    failed = False
    # 数据与页面阶段失败必须显式（退出码 1）；消息通知为 best-effort，不改变退出码
    if not update_json_and_csv(args):
        failed = True
    if not update_readme(args):
        failed = True
    update_message(args)
    if not update_industry_practice_page():
        failed = True
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
