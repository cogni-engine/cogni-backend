"""Recurrence pattern calculator for recurring tasks"""
from datetime import datetime, timedelta
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# 曜日名から曜日番号へのマッピング（0=月曜日, 6=日曜日）
WEEKDAY_MAP: Dict[str, int] = {
    "EVERY_MONDAY": 0,
    "EVERY_TUESDAY": 1,
    "EVERY_WEDNESDAY": 2,
    "EVERY_THURSDAY": 3,
    "EVERY_FRIDAY": 4,
    "EVERY_SATURDAY": 5,
    "EVERY_SUNDAY": 6,
}


def calculate_next_run_time(current_time: datetime, recurrence_pattern: str) -> datetime:
    """
    recurrence_patternに基づいて次回実行時刻を計算する
    
    Args:
        current_time: 現在の実行時刻
        recurrence_pattern: 定期実行パターン
            - "EVERY_DAY": 24時間後
            - "EVERY_WEEK": 7日後
            - "EVERY_MONTH": 1ヶ月後
            - "EVERY_YEAR": 1年後
            - "EVERY_MONDAY" 等の単一曜日: 7日後（同じ曜日の次週）
            - "EVERY_MONDAY, EVERY_FRIDAY" 等の複数曜日: 次の該当曜日
    
    Returns:
        次回実行時刻
    
    Raises:
        ValueError: 不正なrecurrence_patternの場合
    """
    if not recurrence_pattern:
        raise ValueError("recurrence_pattern is required")
    
    # パターンをカンマで分割してトリム
    patterns = [p.strip() for p in recurrence_pattern.split(",")]
    
    # EVERY_DAYの場合
    if "EVERY_DAY" in patterns:
        return current_time + timedelta(days=1)
    
    # EVERY_WEEKの場合
    if "EVERY_WEEK" in patterns:
        return current_time + timedelta(weeks=1)
    
    # EVERY_MONTHの場合
    if "EVERY_MONTH" in patterns:
        # 月を1つ進める
        year = current_time.year
        month = current_time.month + 1
        if month > 12:
            month = 1
            year += 1
        
        # 日付が存在しない場合（例：1/31 -> 2/31）は月末に調整
        day = current_time.day
        while True:
            try:
                return current_time.replace(year=year, month=month, day=day)
            except ValueError:
                day -= 1
                if day < 1:
                    raise ValueError(f"Failed to calculate next month for {current_time}")
    
    # EVERY_YEARの場合
    if "EVERY_YEAR" in patterns:
        year = current_time.year + 1
        # 2/29の場合は調整
        day = current_time.day
        month = current_time.month
        if month == 2 and day == 29:
            # 次の年が閏年でない場合は2/28にする
            try:
                return current_time.replace(year=year)
            except ValueError:
                return current_time.replace(year=year, day=28)
        return current_time.replace(year=year)
    
    # 曜日指定の場合
    weekday_patterns = [p for p in patterns if p in WEEKDAY_MAP]
    
    if weekday_patterns:
        # 現在の曜日を取得（0=月曜日, 6=日曜日）
        current_weekday = current_time.weekday()
        
        # 指定された曜日番号のリストを取得
        target_weekdays = sorted([WEEKDAY_MAP[p] for p in weekday_patterns])
        
        # 現在の曜日より後の最初の該当曜日を探す
        next_weekday = None
        for weekday in target_weekdays:
            if weekday > current_weekday:
                next_weekday = weekday
                break
        
        # 見つからない場合は、最小の曜日＋7日
        if next_weekday is None:
            next_weekday = target_weekdays[0]
            days_ahead = (next_weekday - current_weekday + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
        else:
            days_ahead = next_weekday - current_weekday
        
        return current_time + timedelta(days=days_ahead)
    
    # どのパターンにも該当しない場合
    raise ValueError(f"Invalid recurrence_pattern: {recurrence_pattern}")