"""Markdown 转 Notion Block

将 Markdown 内容转换为 Notion API 的 Block 格式。
"""

import re
from typing import Optional


def md_to_blocks(md_content: str) -> list[dict]:
    """将 Markdown 内容转换为 Notion Blocks

    Args:
        md_content: Markdown 字符串

    Returns:
        Notion Block 列表
    """
    blocks: list[dict] = []

    # 跳过 YAML Front Matter
    lines = md_content.split("\n")
    if lines and lines[0].strip() == "---":
        end_idx = 1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i + 1
                break
        lines = lines[end_idx:]

    # 重新组合为文本
    text = "\n".join(lines)

    # 按行处理
    current_lines: list[str] = []
    in_quote = False

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            if current_lines:
                block = _lines_to_block(current_lines, in_quote)
                if block:
                    blocks.append(block)
                current_lines = []
                in_quote = False
            continue

        # 分隔线
        if stripped == "---":
            if current_lines:
                block = _lines_to_block(current_lines, in_quote)
                if block:
                    blocks.append(block)
                current_lines = []
                in_quote = False
            blocks.append(_divider_block())
            continue

        # 标题
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            if current_lines:
                block = _lines_to_block(current_lines, in_quote)
                if block:
                    blocks.append(block)
                current_lines = []
                in_quote = False

            level = len(heading_match.group(1))
            title_text = heading_match.group(2)
            blocks.append(_heading_block(title_text, level))
            continue

        # 引用
        if stripped.startswith(">"):
            quote_text = re.sub(r"^>\s?", "", stripped)
            if in_quote and current_lines:
                current_lines.append(quote_text)
            else:
                if current_lines:
                    block = _lines_to_block(current_lines, in_quote)
                    if block:
                        blocks.append(block)
                current_lines = [quote_text]
                in_quote = True
            continue

        # 普通文本
        if in_quote:
            block = _lines_to_block(current_lines, True)
            if block:
                blocks.append(block)
            current_lines = [stripped]
            in_quote = False
        else:
            current_lines.append(stripped)

    # 处理剩余行
    if current_lines:
        block = _lines_to_block(current_lines, in_quote)
        if block:
            blocks.append(block)

    return blocks


def _lines_to_block(lines: list[str], is_quote: bool) -> dict | None:
    """将行列表转换为单个 Block"""
    if not lines:
        return None

    # 过滤掉 "在 App 中打开" 行（Notion 页面内容中不需要）
    filtered_lines = [line for line in lines if "在 App 中打开" not in line]
    if not filtered_lines:
        return None

    text = "\n".join(filtered_lines)
    if not text.strip():
        return None

    if is_quote:
        return _quote_block(text)

    # 检查是否以特殊标记开头
    if text.startswith("💭"):
        content = text[1:].strip()
        return _paragraph_block(content)
    elif text.startswith("⏱"):
        return _paragraph_block(text, color="gray")
    elif text.startswith("（") and text.endswith("）"):
        return _paragraph_block(text, color="gray")

    return _paragraph_block(text)


def _rich_text(text: str) -> list[dict]:
    """将纯文本转换为 Notion rich_text 格式

    Notion 单个 rich_text part 的 content 上限为 2000 字符，
    超过时自动分割为多个 part。
    """
    if not text:
        return []

    NOTION_TEXT_LIMIT = 2000

    # 处理链接格式 [text](url)
    parts = []
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    last_end = 0
    for match in link_pattern.finditer(text):
        # 链接前的普通文本
        if match.start() > last_end:
            normal_text = text[last_end:match.start()]
            if normal_text:
                parts.append({"type": "text", "text": {"content": normal_text}})

        # 链接文本
        link_text = match.group(1)
        link_url = match.group(2)
        
        # 只保留有效的 URL 链接（http/https），其他当作纯文本
        if link_url.startswith(("http://", "https://")):
            parts.append({
                "type": "text",
                "text": {"content": link_text, "link": {"url": link_url}},
            })
        else:
            # weread:// 协议或无效 URL，只保留文本
            parts.append({"type": "text", "text": {"content": link_text}})
        last_end = match.end()

    # 剩余文本
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            parts.append({"type": "text", "text": {"content": remaining}})

    if not parts:
        parts.append({"type": "text", "text": {"content": text}})

    # 分割超过 2000 字符限制的 part
    final_parts = []
    for part in parts:
        content = part["text"]["content"]
        if len(content) <= NOTION_TEXT_LIMIT:
            final_parts.append(part)
        else:
            # 按字符限制分割
            for i in range(0, len(content), NOTION_TEXT_LIMIT):
                chunk = content[i:i + NOTION_TEXT_LIMIT]
                chunk_part = {"type": "text", "text": {"content": chunk}}
                # 保留链接（仅附加到第一个 chunk）
                if "link" in part.get("text", {}) and i == 0:
                    chunk_part["text"]["link"] = part["text"]["link"]
                final_parts.append(chunk_part)

    return final_parts


def _heading_block(text: str, level: int = 1) -> dict:
    """创建标题 Block"""
    heading_type = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {"rich_text": _rich_text(text)},
    }


def _paragraph_block(text: str, color: str = "default") -> dict:
    """创建段落 Block"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": _rich_text(text),
            "color": color,
        },
    }


def _quote_block(text: str) -> dict:
    """创建引用 Block"""
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _rich_text(text)},
    }


def _divider_block() -> dict:
    """创建分隔线 Block"""
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }


def _image_block(url: str, caption: str = "") -> dict:
    """创建图片 Block"""
    block: dict = {
        "object": "block",
        "type": "image",
        "image": {
            "type": "external",
            "external": {"url": url},
        },
    }
    if caption:
        block["image"]["caption"] = _rich_text(caption)
    return block
