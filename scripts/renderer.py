"""Markdown 渲染器 — 从 JSON 数据生成派生视图

Markdown 由 JSON 重新渲染生成，禁止手动编辑。
"""

import logging
import os
from typing import Optional

from utils import (
    get_weread_web_url,
    parse_range,
    star_to_emoji,
    timestamp_to_str,
)

logger = logging.getLogger(__name__)


def _resolve_cover_url(meta: dict) -> str:
    """解析封面图片 URL（优先本地 raw GitHub，fallback 远程 WeRead CDN）"""
    cover = meta.get("cover", "")
    local_cover_name = meta.get("localCover", "")
    if local_cover_name:
        repo_url = os.environ.get("GITHUB_REPOSITORY", "")
        if repo_url:
            if "/" in local_cover_name:
                return f"https://raw.githubusercontent.com/{repo_url}/main/{local_cover_name}"
            else:
                return f"https://raw.githubusercontent.com/{repo_url}/main/covers/{local_cover_name}"
    return cover


def render_markdown(book_data: dict) -> str:
    """从书籍 JSON 数据渲染完整的 Markdown 文件

    Args:
        book_data: 完整的书籍 JSON 数据（含 meta, chapters, content, bookReviews 等）

    Returns:
        Markdown 字符串
    """
    meta = book_data.get("meta", {})
    chapters = book_data.get("chapters", [])
    content = book_data.get("content", [])
    book_reviews = book_data.get("bookReviews", [])

    lines: list[str] = []

    # ── YAML Front Matter ──────────────────────────────────
    lines.append("---")
    lines.append("doc_type: weread-highlights-reviews")
    lines.append(f'bookId: "{meta.get("bookId", "")}"')
    lines.append(f'title: "{meta.get("title", "")}"')
    lines.append(f'author: "{meta.get("author", "")}"')
    lines.append(f'category: "{meta.get("category", "")}"')
    lines.append(f'publisher: "{meta.get("publisher", "")}"')
    lines.append(f'publishTime: "{meta.get("publishTime", "")}"')
    lines.append(f'isbn: "{meta.get("isbn", "")}"')
    lines.append(f'localCover: "{meta.get("localCover", "")}"')
    lines.append(f'cover: "{meta.get("cover", "")}"')
    lines.append(f'wordCount: {meta.get("wordCount", 0)}')
    lines.append(f'newRating: {meta.get("newRating", 0)}')
    lines.append(f'newRatingCount: {meta.get("newRatingCount", 0)}')
    lines.append(f'lastSync: "{meta.get("lastSync", "")}"')
    lines.append(f'readingProgress: "{meta.get("readingProgress", "")}"')
    lines.append(f'readingTime: "{meta.get("readingTime", "")}"')
    lines.append(f'finishedDate: "{meta.get("finishedDate", "")}"')
    lines.append(f'noteCount: {meta.get("noteCount", 0)}')
    lines.append(f'reviewCount: {meta.get("reviewCount", 0)}')
    lines.append(f'bookmarkCount: {meta.get("bookmarkCount", 0)}')
    lines.append(f'appLink: "{meta.get("appLink", "")}"')
    lines.append(f'webLink: "{meta.get("webLink", "")}"')
    lines.append("---")
    lines.append("")

    # ── 元数据区块 ──────────────────────────────────────────
    title = meta.get("title", "")
    cover = meta.get("cover", "")
    author = meta.get("author", "")
    intro = meta.get("intro", "")
    publish_time = meta.get("publishTime", "")
    isbn = meta.get("isbn", "")
    category = meta.get("category", "")
    publisher = meta.get("publisher", "")
    app_link = meta.get("appLink", "")

    # 封面图片（使用本地封面，优先 raw.githubusercontent.com）
    cover = _resolve_cover_url(meta)
    if cover:
        lines.append(f"![{title}]({cover})")
        lines.append("")
        
    lines.append("# 元数据")
    lines.append("")
    
    # 元信息表格
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")

    # 书名带网页链接
    web_link = meta.get("webLink", "")
    if web_link:
        lines.append(f"| 书名 | [{title}]({web_link}) |")
    else:
        lines.append(f"| 书名 | {title} |")

    if author:
        lines.append(f"| 作者 | {author} |")
    if publish_time:
        lines.append(f"| 出版时间 | {publish_time} |")
    if isbn:
        lines.append(f"| ISBN | {isbn} |")
    if category:
        lines.append(f"| 分类 | {category} |")
    if publisher:
        lines.append(f"| 出版社 | {publisher} |")
    lines.append("")

    # 书籍简介（独立区块，放在表格下方、笔记上方）
    if intro:
        lines.append("## 简介")
        lines.append("")
        lines.append(intro)
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 按章节渲染笔记内容 ──────────────────────────────────
    # 构建章节标题映射（按 chapterIdx 排序）
    chapter_map: dict[int, str] = {}
    chapter_idx_map: dict[int, int] = {}  # uid -> chapterIdx
    for ch in chapters:
        uid = ch.get("chapterUid", 0)
        ch_title = ch.get("title", "")
        ch_idx = ch.get("chapterIdx", 0)
        if uid and ch_title:
            chapter_map[uid] = ch_title
            chapter_idx_map[uid] = ch_idx

    book_id = meta.get("bookId", "")

    # 按 chapterIdx 排序章节内容
    content.sort(key=lambda x: chapter_idx_map.get(x.get("chapterUid", 0), 999999))

    for chapter_content in content:
        chapter_uid = chapter_content.get("chapterUid", 0)
        chapter_title = chapter_content.get("chapterTitle", "") or chapter_map.get(
            chapter_uid, f"章节 {chapter_uid}"
        )
        items = chapter_content.get("items", [])

        if not items:
            continue

        # 章节标题
        lines.append(f"# {chapter_title}")
        lines.append("")

        # 章节内排序：按 range 起始位置，划线在前，想法在后
        items.sort(key=lambda x: _get_sort_key(x))

        # 将划线和对应想法配对
        highlights = [it for it in items if it.get("type") == "highlight"]
        reviews = [it for it in items if it.get("type") == "review"]

        # 建立 range -> reviews 的映射
        range_reviews: dict[str, list[dict]] = {}
        standalone_reviews: list[dict] = []

        for rv in reviews:
            rv_range = rv.get("range", "")
            if rv_range:
                range_reviews.setdefault(rv_range, []).append(rv)
            else:
                standalone_reviews.append(rv)

        # 建立 highlight range -> markText 的映射（用于查找原文）
        highlight_map: dict[str, str] = {h.get("range", ""): h.get("markText", "") for h in highlights}
        highlight_time_map: dict[str, str] = {h.get("range", ""): h.get("createTimeFormatted", "") for h in highlights}

        for hl in highlights:
            hl_range = hl.get("range", "")
            mark_text = hl.get("markText", "")
            create_time = hl.get("createTimeFormatted", "")

            # 渲染划线（使用引用块）
            lines.append(f"> 📌 {mark_text}")
            if create_time:
                lines.append(f"> ⏱ {create_time}")
            lines.append("")

            # 渲染对应想法（想法前必须贴原文）
            matched = range_reviews.pop(hl_range, [])
            for rv in matched:
                # 想法前引用原文
                lines.append(f"> 📌 {mark_text}")
                if create_time:
                    lines.append(f"> ⏱ {create_time}")
                lines.append("")
                # 想法内容
                lines.append(_render_review(rv))
                lines.append("")

            # 如果没有对应想法，不显示任何内容

        # 章节末尾：无对应划线的想法（纯想法/章节点评）
        # 处理 range_reviews 中剩余的想法（有 range 但无对应划线）
        for rv_range, rv_list in range_reviews.items():
            for rv in rv_list:
                abstract = rv.get("abstract", "")  # API 返回的原文摘要
                create_time = rv.get("createTimeFormatted", "")

                if rv_range in highlight_map:
                    # 找到对应的划线，使用划线的原文
                    mark_text = highlight_map[rv_range]
                    hl_create_time = highlight_time_map.get(rv_range, create_time)
                    lines.append(f"> 📌 {mark_text}")
                    if hl_create_time:
                        lines.append(f"> ⏱ {hl_create_time}")
                    lines.append("")
                elif abstract:
                    # 纯想法：使用 abstract 作为原文
                    lines.append(f"> 📌 {abstract}")
                    if create_time:
                        lines.append(f"> ⏱ {create_time}")
                    lines.append("")

                lines.append(_render_review(rv))
                lines.append("")

        # 处理 standalone_reviews（无 range 的想法）
        for rv in standalone_reviews:
            abstract = rv.get("abstract", "")  # API 返回的原文摘要
            create_time = rv.get("createTimeFormatted", "")

            if abstract:
                # 纯想法：使用 abstract 作为原文
                lines.append(f"> 📌 {abstract}")
                if create_time:
                    lines.append(f"> ⏱ {create_time}")
                lines.append("")

            lines.append(_render_review(rv))
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── 本书评论（固定放在文件最末尾）──────────────────────────
    if book_reviews:
        lines.append("# 本书评论")
        lines.append("")
        for rv in book_reviews:
            lines.append(_render_book_review(rv))
            lines.append("")

    return "\n".join(lines)


def _get_sort_key(item: dict) -> tuple:
    """获取排序键：按 range 起始位置，划线在前，想法在后"""
    range_str = item.get("range", "")
    range_start, _ = parse_range(range_str)
    # 如果 range 为空，给一个很大的值排到最后
    if range_start == 0:
        range_start = 999999
    item_type = item.get("type", "")
    # 划线在前(0)，想法在后(1)
    type_order = 0 if item_type == "highlight" else 1
    return (range_start, type_order)


def _render_review(rv: dict) -> str:
    """渲染单条想法/点评"""
    content = rv.get("content", "")
    create_time = rv.get("createTimeFormatted", "")

    lines: list[str] = []
    lines.append(f"💭 {content}")
    if create_time:
        lines.append(f"⏱ {create_time}")

    return "\n".join(lines)


def _render_book_review(rv: dict) -> str:
    """渲染书评"""
    content = rv.get("content", "")
    star = rv.get("star", -1)
    create_time = rv.get("createTimeFormatted", "")
    is_finish = rv.get("isFinish", False)

    lines: list[str] = []
    lines.append("## 书评")
    meta_parts = []
    if create_time:
        meta_parts.append(f"⏱ {create_time}")
    star_str = star_to_emoji(star)
    if star_str:
        meta_parts.append(star_str)
    if is_finish:
        meta_parts.append("已读完")

    if meta_parts:
        lines.append(" · ".join(meta_parts))
    lines.append("")
    lines.append(content)

    return "\n".join(lines)
