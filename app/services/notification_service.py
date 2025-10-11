import json
import datetime
from typing import List, Dict, Any
from app.config import openai_client
from app.models.notification import NotificationStatus, BulkNotificationUpdate

async def generate_notifications_from_task(task: Dict, user_id: str = "user_123") -> List[Dict]:
    """
    単一のタスクから複数の通知を生成
    
    Args:
        task: タスク情報（dict形式）
        user_id: ユーザーID
    
    Returns:
        生成された通知のリスト（dict形式）
    """
    
    # タスクのdeadlineを安全に変換
    safe_task = {**task}
    if isinstance(safe_task.get("deadline"), datetime.datetime):
        safe_task["deadline"] = safe_task["deadline"].isoformat()
    
    prompt = f"""
以下のタスク情報から、ユーザーに送る通知を生成してください。

タスク情報:
{safe_task}

要件:
1. タスクの重要度・緊急度・締切を考慮して、適切なタイミングで送る通知を1〜2個生成
2. 通知はユーザーにとって有益で、しつこすぎないようにバランスを取る
3. 各通知には具体的な行動提案（suggestions）を3つ含める
4. 通知のタイミングは段階的に（例: 準備段階、実行直前など）

以下のJSON形式で出力してください:
{{
    "notifications": [
        {{
            "title": "通知のタイトル（簡潔に）",
            "content": "通知の本文（具体的で親しみやすく、150文字程度）",
            "due_date": "2024-10-15T10:00:00",
            "suggestions": [
                "具体的な行動提案1",
                "具体的な行動提案2", 
                "具体的な行動提案3"
            ]
        }}
    ]
}}

注意:
- 通知は行動を促すものにする
- タイトルは質問形式や呼びかけ形式で親しみやすく
- due_dateはタスクのdeadlineより前に設定（余裕を持たせる）
- suggestionsは具体的かつ実行可能なアクションにする
- 通知数は1〜2個が適切（多すぎない）
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "あなたはタスク管理の専門家です。ユーザーのタスクを分析し、適切なタイミングで有益な通知を生成してください。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "notification_generation_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "notifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "content": {"type": "string"},
                                    "due_date": {"type": "string"},
                                    "suggestions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 3,
                                        "maxItems": 3
                                    }
                                },
                                "required": ["title", "content", "due_date", "suggestions"]
                            }
                        }
                    },
                    "required": ["notifications"]
                }
            }
        }
    )
    
    result = resp.choices[0].message.content
    data = json.loads(result)
    
    # 生成された通知に追加情報を付与
    notifications = []
    current_time = datetime.datetime.now().isoformat()
    
    for idx, notif in enumerate(data["notifications"]):
        notification = {
            "title": notif["title"],
            "content": notif["content"],
            "user_id": user_id,
            "meta": {},
            "due_date": notif["due_date"],
            "createdAt": current_time,
            "updatedAt": current_time,
            "status": "scheduled",
            "task_id": task["id"],
            "suggestions": notif["suggestions"]
        }
        notifications.append(notification)
    
    return notifications


async def generate_notifications_from_tasks(tasks: List[Dict], user_id: str = "user_123") -> List[Dict]:
    """
    複数のタスクから通知を一括生成
    
    Args:
        tasks: タスクのリスト
        user_id: ユーザーID
    
    Returns:
        生成された通知のリスト（全タスク分）
    """
    all_notifications = []
    notification_id = 1
    
    for task in tasks:
        notifications = await generate_notifications_from_task(task, user_id)
        
        # IDを割り当て
        for notif in notifications:
            notif["id"] = notification_id
            notification_id += 1
            all_notifications.append(notif)
    
    return all_notifications


async def update_notification_status(notification_id: int, status: NotificationStatus, notifications: List[Dict]) -> Dict:
    """
    通知のステータスを更新
    
    Args:
        notification_id: 通知ID
        status: 新しいステータス
        notifications: 通知リスト
    
    Returns:
        更新された通知、または見つからない場合はエラー
    """
    notification = next((n for n in notifications if n["id"] == notification_id), None)
    
    if not notification:
        return {"error": "Notification not found"}
    
    notification["status"] = status.value
    notification["updatedAt"] = datetime.datetime.now().isoformat()
    
    return notification


async def analyze_task_for_notification_updates(task: Dict, current_notifications: List[Dict]) -> List[BulkNotificationUpdate]:
    """
    タスクの内容を分析して通知の変更を検出
    
    Args:
        task: タスクの完全な情報（id, title, deadline, importance, urgency, status, method, reason）
        current_notifications: 既存の通知リスト
    
    Returns:
        必要な通知変更のリスト
    """
    
    # タスクのdeadlineを安全に変換
    safe_task = {**task}
    if isinstance(safe_task.get("deadline"), datetime.datetime):
        safe_task["deadline"] = safe_task["deadline"].isoformat()
    
    prompt = f"""
以下のタスク情報と既存通知を分析し、必要な通知の変更を特定してください。

タスク情報:
{safe_task}

既存通知:
{current_notifications}

分析の基本方針:
**既存通知の更新を最優先**し、完全に新しい内容の場合のみ新規作成してください。

分析の観点:
1. 既存通知との関連性チェック（最優先）
   - タスク情報（特にtask_id）を見て、既存通知と同じタスクに関連する場合は必ず既存通知を更新（update）
   - 関連例: 同じtask_id、締切の変更、ステータス変更、内容の詳細化、suggestions の更新
   - 更新対象: title, content, due_date, suggestions, status など
   - 例1: タスクのdeadlineが変更 → 既存通知の due_date を更新
   - 例2: タスクのstatusが "completed" → 既存通知を archived に更新
   - 例3: タスクのmethodが変更 → 既存通知の content と suggestions を更新

2. 完全に新規の内容の場合のみ新規作成（create）
   - 既存通知と全く異なるタスク（task_idが異なる）に関する通知が必要な場合のみ新規作成
   - 判断基準: 該当するtask_idの通知が既存通知に存在しない
   - 例: 新しいタスクが追加され、それに対する通知が必要な場合
   
3. 不要通知の削除（delete）
   - タスクのstatusが "completed" の場合の通知
   - タスクが削除された場合の通知
   - 期限切れで不要になった通知

優先順位: update（既存更新） > create（新規作成） > delete（削除）
**重要: 既存通知を活用できる場合は必ず更新を選び、通知数を無駄に増やさない**

以下のJSON形式で変更内容を出力してください:
{{
    "updates": [
        {{
            "action": "create|update|delete",
            "notification_id": 既存通知のID（update/deleteの場合のみ必須）,
            "notification_data": {{
                "title": "通知タイトル",
                "content": "通知本文（150文字程度）",
                "user_id": "user_123",
                "due_date": "2024-10-15T10:00:00",
                "status": "scheduled|delivered|read|archived",
                "task_id": タスクID（整数）,
                "suggestions": ["提案1", "提案2", "提案3"]
            }}
        }}
    ]
}}

注意事項:
- 変更が不要な場合は空の配列を返す
- actionでupdateを選ぶ場合は必ずnotification_idを指定
- due_dateはISO形式（YYYY-MM-DDTHH:MM:SS）で出力
- suggestionsは必ず3つ含める
- 既存通知との関連性を慎重に判断し、統合できるものは統合する
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "あなたは通知管理の専門家です。タスク内容を分析して、効率的で実用的な通知変更を提案してください。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "notification_updates_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {"type": "string", "enum": ["create", "update", "delete"]},
                                    "notification_id": {"type": "integer"},
                                    "notification_data": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "content": {"type": "string"},
                                            "user_id": {"type": "string"},
                                            "due_date": {"type": "string"},
                                            "status": {"type": "string"},
                                            "task_id": {"type": "integer"},
                                            "suggestions": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "minItems": 3,
                                                "maxItems": 3
                                            }
                                        },
                                        "required": ["title", "content", "user_id", "due_date", "status", "task_id", "suggestions"]
                                    }
                                },
                                "required": ["action"]
                            }
                        }
                    },
                    "required": ["updates"]
                }
            }
        }
    )
    
    result = resp.choices[0].message.content
    data = json.loads(result)
    
    return [BulkNotificationUpdate(**update) for update in data["updates"]]


async def execute_notification_updates(updates: List[BulkNotificationUpdate], notifications: List[Dict]) -> Dict[str, Any]:
    """
    通知更新を実行
    
    Args:
        updates: 通知変更のリスト
        notifications: 既存の通知リスト（変更対象）
    
    Returns:
        実行結果（created, updated, deleted, errors）
    """
    
    results = {
        "created": [],
        "updated": [],
        "deleted": [],
        "errors": []
    }
    
    current_time = datetime.datetime.now().isoformat()
    
    for update in updates:
        try:
            if update.action == "create":
                # 新規通知作成
                new_notification = update.notification_data.copy()
                new_notification["id"] = max([n["id"] for n in notifications]) + 1 if notifications else 1
                new_notification["createdAt"] = current_time
                new_notification["updatedAt"] = current_time
                new_notification["meta"] = {}
                notifications.append(new_notification)
                results["created"].append(new_notification)
                
            elif update.action == "update" and update.notification_id:
                # 既存通知更新
                notification = next((n for n in notifications if n["id"] == update.notification_id), None)
                if notification and update.notification_data:
                    notification.update(update.notification_data)
                    notification["updatedAt"] = current_time
                    results["updated"].append(notification)
                else:
                    results["errors"].append(f"Notification {update.notification_id} not found")
                    
            elif update.action == "delete" and update.notification_id:
                # 通知削除
                notification = next((n for n in notifications if n["id"] == update.notification_id), None)
                if notification:
                    notifications.remove(notification)
                    results["deleted"].append(notification)
                else:
                    results["errors"].append(f"Notification {update.notification_id} not found")
                    
        except Exception as e:
            results["errors"].append(f"Error processing update {update}: {str(e)}")
    
    return results

