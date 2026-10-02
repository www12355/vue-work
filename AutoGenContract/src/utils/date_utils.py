"""日期计算工具模块。

使用 Python datetime 和 python-dateutil 进行日期运算。
"""

from datetime import datetime, date
from dateutil.relativedelta import relativedelta


def today() -> date:
    """返回系统当天日期。"""
    return date.today()


def today_str(fmt: str = "%Y年%m月%d日") -> str:
    """返回系统当天日期的格式化字符串。"""
    return today().strftime(fmt)


def format_date(dt, fmt: str = "%Y年%m月%d日") -> str:
    """将 date/datetime 对象格式化为中文日期字符串。"""
    if isinstance(dt, datetime):
        dt = dt.date()
    return dt.strftime(fmt)


def compute_end_date(
    start_date: date,
    years: int = 0,
    months: int = 0,
    days: int = 0,
) -> date:
    """根据开始日期和服务时长计算结束日期。

    使用 relativedelta 正确处理月份/年份边界。
    例如：1月31日 + 1个月 = 2月28日（非闰年）

    Args:
        start_date: 服务开始日期
        years: 年数
        months: 月数
        days: 日数

    Returns:
        计算后的结束日期
    """
    return start_date + relativedelta(years=years, months=months, days=days)


def format_duration(years: int = 0, months: int = 0, days: int = 0) -> str:
    """格式化服务时长字符串。

    规则：
    - 非零部分拼接，零值部分省略
    - 例如：(0, 12, 0) → "12个月"
    - 例如：(1, 6, 0) → "1年6个月"
    - 例如：(0, 0, 15) → "15日"
    - 全零时返回 "0日"

    Args:
        years: 年数
        months: 月数
        days: 日数

    Returns:
        格式化的时长字符串，如 "1年6个月15日"
    """
    parts = []
    if years > 0:
        parts.append(f"{years}年")
    if months > 0:
        parts.append(f"{months}个月")
    if days > 0:
        parts.append(f"{days}日")

    if not parts:
        return "0日"
    return "".join(parts)


def parse_date_from_str(date_str: str) -> date:
    """从 GUI 输入的中文日期字符串解析为 date 对象。

    支持格式：
    - "2026年07月02日"
    - "2026-07-02"
    - "2026/07/02"
    """
    if not date_str:
        return today()

    # 尝试多种格式
    formats = [
        "%Y年%m月%d日",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    raise ValueError(f"无法解析日期字符串: {date_str}")
