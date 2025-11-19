"""Prompts for notification summarization"""
from typing import List
from app.models.notification import AINotification
from app.utils.datetime_helper import get_current_datetime_ja


def build_daily_summary_prompt(notifications: List[AINotification]) -> str:
    """
    Build prompt for LLM to summarize AI notifications into important items to tell user.
    
    Args:
        notifications: List of AI notifications with status sent/scheduled
        
    Returns:
        Prompt string for LLM
    """
    current_time = get_current_datetime_ja()
    
    notification_list = []
    for notif in notifications:
        notification_list.append({
            "title": notif.title,
            "content": notif.content,
            "due_date": notif.due_date.isoformat(),
            "status": notif.status
        })
    
    import json
    notifications_json = json.dumps(notification_list, ensure_ascii=False, indent=2)
    
    prompt = f"""あなたは親切で知的なAIアシスタントです。

現在時刻: {current_time}

以下のnotificationリストを分析し、ユーザーに今伝えるべき重要な事項を2-3個に絞って、自然な日本語でまとめてください。

【優先順位の基準】
1. 期限切れまたは期限が近いもの（最優先）
2. ステータスがscheduledの新しい通知
3. タスクの重要度や緊急度

【Notificationリスト】
{notifications_json}

【出力形式】
- 簡潔で自然な日本語で
- 2-3個の重要事項に絞る
- 期限を明示する
- ユーザーが行動しやすいように具体的に

重要事項のまとめ:"""
    
    return prompt

