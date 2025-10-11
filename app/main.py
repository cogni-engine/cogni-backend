from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.config import supabase
from app.models import (
    ChatRequest, ChatResponse, Task, TaskUpdateRequest, TaskUpdateResponse,
    NotificationCreateRequest, NotificationUpdateStatusRequest, NotificationAnalysisRequest, NotificationAnalysisResponse
)
from app.services import (
    handle_chat, run_engine, analyze_note_for_task_updates, execute_task_updates,
    generate_notifications_from_task, generate_notifications_from_tasks, update_notification_status,
    analyze_task_for_notification_updates, execute_notification_updates
)
from app.services.test.simple_agent import simple_agent_chat, StreamTestRequest
from app.data.mock_data import chat_history, mock_tasks, mock_notifications, focused_task_id

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - specify your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods including OPTIONS
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

@app.post("/test/stream")
async def test_stream(request: StreamTestRequest):
    """Test endpoint to showcase streaming LLM responses with LangGraph"""
    
    return StreamingResponse(
        simple_agent_chat(request.system_message, request.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/engine")
async def engine():
    fid = await run_engine()
    return {"focused_task_id": fid}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await handle_chat(request, focused_task_id, mock_tasks)

# チャット履歴を取得するエンドポイント
@app.get("/chat/history")
async def get_chat_history():
    return chat_history

# チャット履歴をクリアするエンドポイント
@app.delete("/chat/history")
async def clear_chat_history():
    chat_history.clear()
    return {"message": "Chat history cleared"}

# タスク一覧を取得するエンドポイント
@app.get("/tasks")
async def get_tasks():
    return {"tasks": mock_tasks}

# 特定のタスクを取得するエンドポイント
@app.get("/tasks/{task_id}")
async def get_task(task_id: int):
    task = next((task for task in mock_tasks if task["id"] == task_id), None)
    if task is None:
        return {"error": "Task not found"}
    return {"task": task}

# タスクのステータスを更新するエンドポイント
@app.put("/tasks/{task_id}/status")
async def update_task_status(task_id: int, status: str):
    task = next((task for task in mock_tasks if task["id"] == task_id), None)
    if task is None:
        return {"error": "Task not found"}
    
    task["status"] = status
    return {"task": task}

# 新しいタスクを作成するエンドポイント
@app.post("/tasks")
async def create_task(task: Task):
    new_task = task.dict()
    new_task["id"] = max([t["id"] for t in mock_tasks]) + 1 if mock_tasks else 1
    mock_tasks.append(new_task)
    return {"task": new_task}

# Noteの内容からタスクを更新
@app.post("/tasks/update-from-note", response_model=TaskUpdateResponse)
async def update_tasks_from_note(request: TaskUpdateRequest):
    """Noteの内容からタスクを更新"""
    
    # AIで変更を分析
    updates = await analyze_note_for_task_updates(
        request.note_content, 
        request.current_tasks
    )
    
    if not updates:
        return {
            "updates": [],
            "summary": "変更は必要ありません"
        }
    
    # タスク更新を実行
    results = await execute_task_updates(updates)
    
    # サマリー生成
    summary_parts = []
    if results["created"]:
        summary_parts.append(f"新規タスク {len(results['created'])}件作成")
    if results["updated"]:
        summary_parts.append(f"既存タスク {len(results['updated'])}件更新")
    if results["deleted"]:
        summary_parts.append(f"タスク {len(results['deleted'])}件削除")
    if results["errors"]:
        summary_parts.append(f"エラー {len(results['errors'])}件")
    
    summary = ", ".join(summary_parts) if summary_parts else "変更なし"
    
    return {
        "updates": [update.dict() for update in updates],
        "summary": summary
    }



# ============================================
# 通知（Notification）関連エンドポイント
# ============================================

# 通知一覧を取得
@app.get("/notifications")
async def get_notifications():
    """すべての通知を取得"""
    return {"notifications": mock_notifications}

# 特定の通知を取得
@app.get("/notifications/{notification_id}")
async def get_notification(notification_id: int):
    """特定の通知を取得"""
    notification = next((n for n in mock_notifications if n["id"] == notification_id), None)
    if notification is None:
        return {"error": "Notification not found"}
    return {"notification": notification}

# 特定のタスクから通知を生成
@app.post("/notifications/generate-from-task")
async def generate_notifications_from_task_endpoint(request: NotificationCreateRequest):
    """特定のタスクから通知を生成"""
    task = next((t for t in mock_tasks if t["id"] == request.task_id), None)
    if task is None:
        return {"error": "Task not found"}
    
    notifications = await generate_notifications_from_task(task)
    
    # 生成された通知をモックデータに追加
    for notification in notifications:
        # IDを割り当て
        notification["id"] = max([n["id"] for n in mock_notifications]) + 1 if mock_notifications else 1
        mock_notifications.append(notification)
    
    return {
        "notifications": notifications,
        "count": len(notifications),
        "message": f"{len(notifications)}件の通知を生成しました"
    }

# すべてのタスクから通知を一括生成
@app.post("/notifications/generate-from-all-tasks")
async def generate_notifications_from_all_tasks_endpoint():
    """すべてのタスクから通知を一括生成"""
    notifications = await generate_notifications_from_tasks(mock_tasks)
    
    # 既存の通知をクリアして新しい通知を追加
    mock_notifications.clear()
    mock_notifications.extend(notifications)
    
    return {
        "notifications": notifications,
        "count": len(notifications),
        "message": f"全{len(mock_tasks)}タスクから{len(notifications)}件の通知を生成しました"
    }

# 通知のステータスを更新
@app.put("/notifications/{notification_id}/status")
async def update_notification_status_endpoint(notification_id: int, request: NotificationUpdateStatusRequest):
    """通知のステータスを更新"""
    result = await update_notification_status(notification_id, request.status, mock_notifications)
    
    if "error" in result:
        return result
    
    return {
        "notification": result,
        "message": f"通知 #{notification_id} のステータスを {request.status} に更新しました"
    }

# タスク情報から通知を差分検出して更新
@app.post("/notifications/analyze-and-update", response_model=NotificationAnalysisResponse)
async def analyze_and_update_notifications(request: NotificationAnalysisRequest):
    """タスク情報から通知の差分を検出して更新"""
    
    # AIで変更を分析
    updates = await analyze_task_for_notification_updates(
        request.task,
        request.current_notifications
    )
    
    if not updates:
        return {
            "updates": [],
            "summary": "変更は必要ありません"
        }
    
    # 通知更新を実行
    results = await execute_notification_updates(updates, mock_notifications)
    
    # サマリー生成
    summary_parts = []
    if results["created"]:
        summary_parts.append(f"新規通知 {len(results['created'])}件作成")
    if results["updated"]:
        summary_parts.append(f"既存通知 {len(results['updated'])}件更新")
    if results["deleted"]:
        summary_parts.append(f"通知 {len(results['deleted'])}件削除")
    if results["errors"]:
        summary_parts.append(f"エラー {len(results['errors'])}件")
    
    summary = ", ".join(summary_parts) if summary_parts else "変更なし"
    
    return {
        "updates": [update.dict() for update in updates],
        "summary": summary
    }
