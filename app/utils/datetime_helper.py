"""日時フォーマットのヘルパー関数"""
from datetime import datetime, timezone, timedelta


def get_current_datetime_ja() -> str:
    """
    現在の日本時間を日本語フォーマットで取得
    
    Returns:
        str: "2025年10月14日（火曜日） 午前10時30分" 形式の文字列
    """
    # 日本時間 (UTC+9)
    jst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc).astimezone(jst)
    
    return format_datetime_ja(now)


def format_datetime_ja(dt: datetime) -> str:
    """
    datetimeオブジェクトを日本語フォーマットに変換
    
    Args:
        dt: 変換するdatetimeオブジェクト（タイムゾーン情報がない場合はJSTとみなす）
    
    Returns:
        str: "2025年10月14日（火曜日） 午前10時30分" 形式の文字列
    """
    # タイムゾーン情報がない場合はJSTを付与
    if dt.tzinfo is None:
        jst = timezone(timedelta(hours=9))
        dt = dt.replace(tzinfo=jst)
    
    # 曜日の日本語マッピング
    weekday_ja = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]
    
    # 午前/午後の判定
    hour = dt.hour
    if hour < 12:
        period = "午前"
        display_hour = hour if hour != 0 else 12
    else:
        period = "午後"
        display_hour = hour - 12 if hour != 12 else 12
    
    # フォーマット
    formatted = (
        f"{dt.year}年{dt.month}月{dt.day}日"
        f"（{weekday_ja[dt.weekday()]}） "
        f"{period}{display_hour}時{dt.minute:02d}分"
    )
    
    return formatted


def convert_jst_to_utc(dt: datetime) -> datetime:
    """
    入力のタイムゾーンに関わらず、9時間分ずらしてUTCに変換する
    
    Args:
        dt: datetime（タイムゾーン情報に関わらず、JSTとして解釈して9時間引く）
    
    Returns:
        UTCのdatetime（timezone.utc）
    """
    # タイムゾーン情報を削除してnaive datetimeにする
    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    
    # JST（UTC+9）として解釈
    jst = timezone(timedelta(hours=9))
    dt_jst = dt_naive.replace(tzinfo=jst)
    
    # JSTからUTCに変換（9時間引く）
    utc_dt = dt_jst.astimezone(timezone.utc)
    
    return utc_dt

