import json
import datetime
from typing import List, Dict, Optional, Any
from app.config import openai_client
from app.data.mock_data import chat_history, mock_tasks
from app.models.task import BulkTaskUpdate

async def run_engine() -> Optional[int]:
    """タスクフォーカスエンジンを実行"""
    import app.data.mock_data as data_module
    
    # datetime を文字列に変換してから渡す
    safe_tasks = []
    for t in mock_tasks:
        safe_t = {**t}
        if isinstance(safe_t["deadline"], datetime.datetime):
            safe_t["deadline"] = safe_t["deadline"].isoformat()
        safe_tasks.append(safe_t)

    prompt = """
    以下はユーザーとのチャット履歴とタスク一覧です。
    会話からユーザーが今一番フォーカスすべきタスクを1つ選び、
    JSON形式で { "focused_task_id": <id> } の形で答えてください。
    優先順位としては、
    直近のユーザー発話との意図一致度を最優先にするため、ユーザのチャット履歴に含まれる
    発話と関係の最もありそうなタスクを選んでください。
    ただし、ユーザの最新の発言に最も関係のあるものを選んでください。そのために過去の話を無視しても良いです
    分割されているタスクについては、フォーカスしているものが終わったと判断できる場合に、次のタスクにフォーカスしてください。
    """

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Chat history: {chat_history}\nTasks: {safe_tasks}"}
    ]

    print("==== AIに投げるmessages ====")
    for m in messages:
        print(m)
    print("================================")

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "focused_task_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "focused_task_id": {"type": "integer"}
                    },
                    "required": ["focused_task_id"],
                    "additionalProperties": False
                }
            }
        }
    )

    result = resp.choices[0].message
    print("==== AIからのレスポンス ====")
    print(result)

    # content を JSON として扱う
    data = json.loads(result.content)
    data_module.focused_task_id = data.get("focused_task_id")

    return data_module.focused_task_id

async def analyze_note_for_task_updates(note_content: str, current_tasks: List[Dict]) -> List[BulkTaskUpdate]:
    """Noteの内容を分析してタスクの変更を検出"""
    
    # 現在のタスクを安全な形式に変換
    safe_tasks = []
    for task in current_tasks:
        safe_task = {**task}
        if isinstance(safe_task.get("deadline"), datetime.datetime):
            safe_task["deadline"] = safe_task["deadline"].isoformat()
        safe_tasks.append(safe_task)
    
    prompt = f"""
以下のNote内容と既存タスクを分析し、必要なタスク変更を特定してください。

Note内容:
{note_content}

既存タスク:
{safe_tasks}

分析の観点:
1. 既存タスクとの関連性を優先的に検討
   - Note内容が既存タスクに関連する場合は、既存タスクを更新（update）する
   -その際、既存のタスク内容は完了していることが明示されていないならそのままにする（統合する）
   - 既存タスクの補足・詳細化・期限変更などで対応できる内容は統合する
2. 完全に新しい内容のみ新規作成（create）
   - 既存タスクと全く異なるテーマ・目的の場合のみ新規タスクを作成
3. 既存タスクの削除（delete）
   - Note内で完了が明示されているタスク
   - Note内で不要になったと判断できるタスク

以下のJSON形式で変更内容を出力してください:
{{
    "updates": [
        {{
            "action": "create|update|delete",
            "task_id": 既存タスクのID（update/deleteの場合のみ）,
            "task_data": {{
                "title": "タスクタイトル",
                "deadline": "2024-10-15T00:00:00",
                "importance": 1-5,
                "urgency": 1-5,
                "status": "pending|in_progress|completed",
                "method": "実行方法",
                "reason": "理由"
            }}
        }}
    ]
}}

注意:
- 変更がない場合は空の配列を返す
- 既存タスクは可能な限り更新し、不要な新規作成は避ける
- deadlineはISO形式で出力
- actionは必ず小文字で指定
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system", 
                "content": "あなたはタスク管理の専門家です。Noteの内容を分析して、効率的で実用的なタスク変更を提案してください。"
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "task_updates_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {"type": "string", "enum": ["create", "update", "delete"]},
                                    "task_id": {"type": "integer"},
                                    "task_data": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "deadline": {"type": "string"},
                                            "importance": {"type": "integer"},
                                            "urgency": {"type": "integer"},
                                            "status": {"type": "string"},
                                            "method": {"type": "string"},
                                            "reason": {"type": "string"}
                                        },
                                        "required": ["title", "deadline", "importance", "urgency", "status", "method", "reason"]
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
    
    return [BulkTaskUpdate(**update) for update in data["updates"]]

async def execute_task_updates(updates: List[BulkTaskUpdate]) -> Dict[str, Any]:
    """タスク更新を実行"""
    
    results = {
        "created": [],
        "updated": [],
        "deleted": [],
        "errors": []
    }
    
    for update in updates:
        try:
            if update.action == "create":
                # 新規タスク作成
                new_task = update.task_data.copy()
                new_task["id"] = max([t["id"] for t in mock_tasks]) + 1 if mock_tasks else 1
                new_task["deadline"] = datetime.datetime.fromisoformat(new_task["deadline"])
                mock_tasks.append(new_task)
                results["created"].append(new_task)
                
            elif update.action == "update" and update.task_id:
                # 既存タスク更新
                task = next((t for t in mock_tasks if t["id"] == update.task_id), None)
                if task and update.task_data:
                    task.update(update.task_data)
                    if "deadline" in update.task_data:
                        task["deadline"] = datetime.datetime.fromisoformat(update.task_data["deadline"])
                    results["updated"].append(task)
                else:
                    results["errors"].append(f"Task {update.task_id} not found")
                    
            elif update.action == "delete" and update.task_id:
                # タスク削除
                task = next((t for t in mock_tasks if t["id"] == update.task_id), None)
                if task:
                    mock_tasks.remove(task)
                    results["deleted"].append(task)
                else:
                    results["errors"].append(f"Task {update.task_id} not found")
                    
        except Exception as e:
            results["errors"].append(f"Error processing update {update}: {str(e)}")
    
    return results

