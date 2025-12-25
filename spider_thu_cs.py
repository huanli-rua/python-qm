# -*- coding: utf-8 -*-
"""
爬虫：清华计算机系在职教师名录 -> 教师个人页 -> 抽取研究领域/研究方向/研究概况文本 -> 写入 data/姓名.txt

运行：
  python spider_thu_cs.py
"""

import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www.cs.tsinghua.edu.cn/"
LIST_URL = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"


def _safe_filename(name: str) -> str:
    """把姓名变成安全文件名（Windows 不允许的字符去掉）"""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name


def _clean_lines(text: str) -> list[str]:
    """把页面文本做成干净的行列表（去空行/多空格）"""
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    return [x for x in lines if x]


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    """抓取网页 HTML，带基本重试"""
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError("unreachable")


def parse_teacher_links(list_html: str) -> list[tuple[str, str]]:
    """
    从名录页提取教师(姓名, 个人页URL)
    名录页里链接一般是 /info/xxxx/yyyy.htm
    """
    soup = BeautifulSoup(list_html, "lxml")
    pairs: list[tuple[str, str]] = []

    # 找所有 <a>，过滤出文本是姓名、href 指向 info 页的
    for a in soup.find_all("a"):
        name = a.get_text(strip=True)
        href = a.get("href", "").strip()

        if not name:
            continue
        if not href:
            continue
        if "/info/" not in href:
            continue

        # 姓名一般是纯中文 2~4 个字（也可能更长，但这里先放宽一点）
        if not re.fullmatch(r"[\u4e00-\u9fff·]{2,10}", name):
            continue

        full_url = urljoin(BASE, href)
        pairs.append((name, full_url))

    # 去重（同名同链接）
    seen = set()
    uniq = []
    for name, url in pairs:
        key = (name, url)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((name, url))
    return uniq


def extract_research_text(profile_html: str) -> str:
    """
    从教师个人页抽取研究相关文本：
    - 研究领域
    - 研究方向
    - 研究概况
    做法：把页面转纯文本后，按“标题行”截取后续内容直到遇到下一个栏目标题。
    """
    soup = BeautifulSoup(profile_html, "lxml")

    # 整页转文本（不要太聪明：很多站点结构不固定，硬找 div class 反而脆）
    raw_text = soup.get_text("\n", strip=True)
    lines = _clean_lines(raw_text)

    # 可能出现的栏目标题（停止条件）
    stop_titles = {
        "教育背景", "工作经历", "社会兼职", "学术兼职", "奖励与荣誉", "荣誉奖励",
        "学术成果", "科研项目", "代表性论文", "代表论文", "出版物", "专利",
        "招生信息", "教学", "课程", "联系方式", "邮箱", "电话", "上一篇", "下一篇", "关闭"
    }

    target_titles = ["研究领域", "研究方向", "研究概况"]

    # 建一个“标题 -> 抽取内容”的字典
    sections: dict[str, list[str]] = {t: [] for t in target_titles}

    i = 0
    while i < len(lines):
        line = lines[i]

        # 有时标题带冒号，比如“研究领域：”
        normalized = re.sub(r"[：:]\s*$", "", line)

        if normalized in sections:
            title = normalized
            i += 1
            buf = []
            while i < len(lines):
                nxt = lines[i]
                nxt_norm = re.sub(r"[：:]\s*$", "", nxt)

                # 碰到另一个栏目标题就停
                if (nxt_norm in stop_titles) or (nxt_norm in target_titles):
                    break

                # 一些噪声行过滤（可按需加规则）
                if nxt_norm.startswith("首页") or "清华大学计算机科学与技术系" in nxt_norm:
                    i += 1
                    continue

                buf.append(nxt)
                i += 1

            # 合并去重（同一段落可能被页面重复输出）
            for x in buf:
                if x not in sections[title]:
                    sections[title].append(x)
            continue

        i += 1

    # 组装输出：只要命中任何一个栏目就输出
    out_parts = []
    for t in target_titles:
        content = sections[t]
        if content:
            out_parts.append(t)
            out_parts.extend(content)
            out_parts.append("")  # 空行分隔

    result = "\n".join(out_parts).strip()

    # 再做一层“弱清洗”：如果太短基本就是没抓到
    if len(result) < 10:
        return ""

    return result


def crawl_to_data(output_dir: str = "data", sleep_sec: float = 0.2) -> None:
    os.makedirs(output_dir, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36"
    })

    print(f"【开始】抓取教师名录：{LIST_URL}")
    list_html = fetch_html(session, LIST_URL)
    teachers = parse_teacher_links(list_html)
    print(f"【名录】解析到教师个人页链接数：{len(teachers)}")

    saved = 0
    skipped = 0

    for idx, (name, url) in enumerate(teachers, 1):
        try:
            html = fetch_html(session, url)
            research_text = extract_research_text(html)

            if not research_text:
                skipped += 1
                print(f"[{idx}/{len(teachers)}] {name}：未提取到研究相关文本，跳过")
                time.sleep(sleep_sec)
                continue

            fn = _safe_filename(name) + ".txt"
            path = os.path.join(output_dir, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(research_text)

            saved += 1
            print(f"[{idx}/{len(teachers)}] {name}：已保存 -> {path}")

        except Exception as e:
            skipped += 1
            print(f"[{idx}/{len(teachers)}] {name}：抓取失败，原因：{e}")

        time.sleep(sleep_sec)

    print(f"【完成】成功保存：{saved}，跳过/失败：{skipped}，输出目录：{output_dir}")


if __name__ == "__main__":
    crawl_to_data(output_dir="data", sleep_sec=0.25)
