"""通用工具函数"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# 划线颜色映射
COLOR_MAP = {
    0: ("白色", "⚪"),
    1: ("黄色", "🟡"),
    2: ("绿色", "🟢"),
    3: ("蓝色", "🔵"),
    4: ("紫色", "🟣"),
}


def timestamp_to_str(ts: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Unix 时间戳转格式化字符串（上海时间）"""
    if not ts:
        return ""
    from datetime import timedelta
    dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))
    return dt.strftime(fmt)


def timestamp_to_utc_str(ts: int) -> str:
    """Unix 时间戳转 UTC ISO 格式字符串"""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds_to_reading_time(seconds: int) -> str:
    """秒数转阅读时长字符串，如 '12小时30分钟'"""
    if not seconds or seconds <= 0:
        return "0分钟"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0 and minutes > 0:
        return f"{hours}小时{minutes}分钟"
    elif hours > 0:
        return f"{hours}小时"
    else:
        return f"{minutes}分钟"


def extract_category(category: str) -> str:
    """从 category 字段提取一级分类

    以 ·、-、/ 切分，取第一部分，去除首尾空白
    """
    if not category:
        return "未分类"
    # 尝试多种分隔符
    for sep in ["·", "-", "/"]:
        if sep in category:
            first = category.split(sep)[0].strip()
            if first:
                return first
    return category.strip() or "未分类"


def sanitize_filename(name: str) -> str:
    """清理文件名，移除不合法字符"""
    # 移除 Windows/Linux 不允许的字符
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip()
    # 限制长度
    if len(name) > 100:
        name = name[:100]
    return name or "unnamed"


def get_folder_name(title: str, book_id: str) -> str:
    """生成文件夹名：书名_bookId后4位"""
    clean_title = sanitize_filename(title)
    suffix = str(book_id)[-4:] if book_id else "0000"
    return f"{clean_title}_{suffix}"


def get_color_label(color_style: int) -> str:
    """获取划线颜色标签"""
    label, _ = COLOR_MAP.get(color_style, ("未知", "⚪"))
    return label


def get_color_emoji(color_style: int) -> str:
    """获取划线颜色 emoji"""
    _, emoji = COLOR_MAP.get(color_style, ("未知", "⚪"))
    return emoji


def atomic_write_json(filepath: Path, data: dict):
    """原子写入 JSON 文件

    先写临时文件，验证后重命名覆盖
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 写入临时文件
    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 验证写入完整性
        with open(tmp_path, "r", encoding="utf-8") as f:
            json.load(f)  # 验证 JSON 合法性

        # 原子重命名
        tmp_path.replace(filepath)
    except Exception:
        # 清理临时文件
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def atomic_write_text(filepath: Path, content: str):
    """原子写入文本文件"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 验证写入
        with open(tmp_path, "r", encoding="utf-8") as f:
            f.read()

        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def load_json(filepath: Path) -> dict | None:
    """加载 JSON 文件，不存在返回 None"""
    filepath = Path(filepath)
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """直接保存 JSON（非原子，用于 index.json 等频繁更新场景）"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_range(range_str: str) -> tuple[int, int]:
    """解析划线范围字符串 '393-401' -> (393, 401)"""
    if not range_str or "-" not in range_str:
        return (0, 0)
    parts = range_str.split("-")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def star_to_emoji(star: int) -> str:
    """评分转 emoji 星级（最多5星）"""
    if star == -1 or star is None:
        return ""
    # 微信读书评分可能是百分制，转换为5星制
    if star > 5:
        star = min(5, max(1, star // 20))
    return "⭐" * star
