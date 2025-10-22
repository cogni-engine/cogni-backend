import json
import asyncio
import logging

# ログ設定（他のimportの前に）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.config import supabase, WEBHOOK_SECRET
from app.models import (
    ChatRequest, ChatResponse, Task, TaskUpdateRequest, TaskUpdateResponse,
    Notification, NotificationCreateRequest, NotificationUpdateStatusRequest, NotificationAnalysisRequest, NotificationAnalysisResponse
)
from app.services import (
    handle_chat, run_engine, analyze_note_for_task_updates, execute_task_updates,
    generate_notifications_from_task, generate_notifications_from_tasks, update_notification_status,
    analyze_task_for_notification_updates, execute_notification_updates
)
from app.services.test.simple_agent import simple_agent_chat, StreamTestRequest
from app.services.note_to_task import generate_tasks_from_note
from app.services.task_to_notification import (
    generate_notifications_from_task as generate_notifications_from_task_ai,
    process_task_queue_for_notifications
)
from app.services.ai_chat.ai_chat_service import ai_chat_stream
from app.services.cogno.cogni_engine.engine_service import make_engine_decision, extract_timer_duration
from app.services.cogno.conversation.conversation_service import conversation_stream
from app.services.cogno.timer.timer_manager import start_timer, get_active_timer
from app.services.cogno.notification.notification_service import handle_notification_click, daily_notification_check
from app.data.mock_data import chat_history, mock_tasks, mock_notifications, focused_task_id
from app.infra.supabase.repositories.workspaces import WorkspaceRepository


# Request/Response models for note-to-task endpoint
class GenerateTasksRequest(BaseModel):
    note_id: int
    user_id: str


class GenerateTasksResponse(BaseModel):
    tasks: List[Task]  # TaskCreate から Task に変更
    count: int


# Request/Response models for task-to-notification endpoint
class GenerateNotificationsRequest(BaseModel):
    task_id: int
    user_id: str


class GenerateNotificationsResponse(BaseModel):
    notifications: List[Notification]
    count: int


# Request model for AI chat streaming endpoint
class AIChatRequest(BaseModel):
    thread_id: int
    message: str


# Request models for Cogno endpoints
class CognoStartTimerRequest(BaseModel):
    thread_id: int
    duration_minutes: int
    message_id: Optional[int] = None


class NotificationTriggerRequest(BaseModel):
    notification_id: int
    thread_id: int


class DailyCheckRequest(BaseModel):
    workspace_id: int


# タスク通知生成キュー
task_notification_queue: Dict[int, int] = {}  # {task_id: source_note_id}
queue_lock = asyncio.Lock()
processing_task: Optional[asyncio.Task] = None
DEBOUNCE_SECONDS = 10


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


@app.post("/api/ai-chat/stream")
async def ai_chat_stream_endpoint(request: AIChatRequest):
    """
    Thread IDベースでAIチャットのストリーミングレスポンスを返すエンドポイント
    
    - thread_idから履歴を取得
    - ユーザーメッセージを保存
    - AIレスポンスをストリームで返す
    - 完全なレスポンスをデータベースに保存
    """
    return StreamingResponse(
        ai_chat_stream(request.thread_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/ai-chat/messages/{thread_id}")
async def get_ai_messages(thread_id: int):
    """指定されたThreadのメッセージ一覧を取得"""
    from app.infra.supabase.repositories.ai_messages import AIMessageRepository
    
    ai_message_repo = AIMessageRepository(supabase)
    messages = await ai_message_repo.find_by_thread(thread_id)
    
    return {"messages": messages}


# ============================================
# Cogno Endpoints (新しいアーキテクチャ)
# ============================================

@app.post("/api/cogno/chat/stream")
async def cogno_chat_stream_endpoint(request: AIChatRequest):
    """
    Cogno chat stream endpoint with engine decision.
    
    Flow:
    1. Engine makes decision (focused_task_id, should_start_timer)
    2. If should_start_timer=true, extract timer duration and start timer
    3. Conversation AI responds with appropriate context
    """
    # Make engine decision with current user message
    decision = await make_engine_decision(request.thread_id, request.message)
    logging.info(f"Engine decision: focused_task_id={decision.focused_task_id}, should_start_timer={decision.should_start_timer}")
    
    # If engine decided to start timer, extract duration and start timer
    timer_started = False
    if decision.should_start_timer:
        timer_duration = extract_timer_duration(request.message)
        logging.info(f"Timer duration extraction result: {timer_duration} minutes" if timer_duration else "No duration found in message")
        if timer_duration:
            # Start timer automatically
            await start_timer(request.thread_id, timer_duration)
            logging.info(f"✓ Timer started automatically: {timer_duration} minutes for thread {request.thread_id}")
            timer_started = True
    
    # Ask for timer duration only if engine wants timer but we couldn't extract duration
    should_ask_timer = decision.should_start_timer and not timer_started
    logging.info(f"Conversation context: should_ask_timer={should_ask_timer}, timer_started={timer_started}")
    
    # Stream conversation response with engine decision context
    return StreamingResponse(
        conversation_stream(
            thread_id=request.thread_id,
            user_message=request.message,
            focused_task_id=decision.focused_task_id,
            should_ask_timer=should_ask_timer
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/cogno/timers/poll")
async def cogno_timer_poll(thread_id: int):
    """
    Poll for active timer status.
    Returns timer info with remaining time or timer_ended flag.
    """
    timer_info = await get_active_timer(thread_id)
    
    if not timer_info:
        return {"timer": None, "timer_ended": False}
    
    return timer_info


@app.post("/api/cogno/timers/start")
async def cogno_start_timer_endpoint(request: CognoStartTimerRequest):
    """
    Start a new timer for a thread.
    Called when user provides duration (e.g., "30分").
    """
    timer_state = await start_timer(
        request.thread_id,
        request.duration_minutes,
        request.message_id
    )
    
    return {
        "success": True,
        "timer": timer_state.dict()
    }


@app.get("/api/cogno/messages/{thread_id}")
async def get_cogno_messages(thread_id: int):
    """指定されたThreadのメッセージ一覧を取得（Cogno用）"""
    from app.infra.supabase.repositories.ai_messages import AIMessageRepository
    
    ai_message_repo = AIMessageRepository(supabase)
    messages = await ai_message_repo.find_by_thread(thread_id)
    
    return {"messages": messages}


# ============================================
# Notification Endpoints (Cogno統合)
# ============================================

@app.post("/api/cogno/notification/trigger")
async def cogno_notification_trigger(request: NotificationTriggerRequest):
    """
    Handle notification click event.
    Generates AI conversation response and marks notification as resolved.
    
    Flow:
    1. Get notification details
    2. Generate AI response using conversation_stream
    3. Mark notification as resolved
    """
    try:
        await handle_notification_click(
            notification_id=request.notification_id,
            thread_id=request.thread_id
        )
        return {"success": True, "message": "Notification processed"}
    except Exception as e:
        logging.error(f"Error in notification trigger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cogno/notification/daily-check")
async def cogno_daily_notification_check(request: DailyCheckRequest):
    """
    Daily notification check endpoint.
    Called at 10:00 AM JST by external scheduler.
    
    Flow:
    1. Check latest message in workspace's latest thread
    2. If not notification-triggered, summarize pending notifications
    3. Generate AI message with summary
    """
    try:
        await daily_notification_check(workspace_id=request.workspace_id)
        return {"success": True, "message": "Daily check completed"}
    except Exception as e:
        logging.error(f"Error in daily notification check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
# Note to Task AI エンドポイント
# ============================================

@app.post("/api/notes/generate-tasks", response_model=GenerateTasksResponse)
async def generate_tasks_endpoint(request: GenerateTasksRequest):
    """指定されたnoteからAIでタスクを生成"""
    from app.infra.supabase.repositories.notes import NoteRepository
    
    # noteを取得
    note_repo = NoteRepository(supabase)
    note = await note_repo.find_by_id(request.note_id)
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    tasks = await generate_tasks_from_note(request.note_id, note.text, request.user_id)
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }


# ============================================
# Task to Notification AI エンドポイント
# ============================================

@app.post("/api/tasks/generate-notifications", response_model=GenerateNotificationsResponse)
async def generate_notifications_endpoint(request: GenerateNotificationsRequest):
    """特定のタスクからAIで通知を生成してデータベースに保存"""
    from app.infra.supabase.repositories.tasks import TaskRepository
    
    # タスクを取得
    task_repo = TaskRepository(supabase)
    task = await task_repo.find_by_id(request.task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    notifications = await generate_notifications_from_task_ai(task)
    
    return {
        "notifications": notifications,
        "count": len(notifications)
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



async def process_task_notification_queue():
    """10秒待機後、キューをサービス層に渡して処理"""
    global task_notification_queue
    
    await asyncio.sleep(DEBOUNCE_SECONDS)
    
    async with queue_lock:
        if not task_notification_queue:
            return
        queue_copy = task_notification_queue.copy()
        task_notification_queue.clear()
    
    await process_task_queue_for_notifications(queue_copy)


@app.post("/webhooks/notes")
async def notes_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """Supabase Webhookから呼ばれ、noteの内容を受け取ってAIタスクを生成（personalワークスペースのみ）"""
    
    # セキュリティチェック
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized webhook call")
    
    # Supabaseから送られたpayloadを受け取る
    body = await request.json()
    print("✅ Webhook received:", json.dumps(body, indent=2))
    
    # payloadから必要な情報を取得
    record = body.get("record") or {}
    note_id = record.get("id")
    note_text = record.get("text", "")
    workspace_id = record.get("workspace_id")

    if not note_id:
        raise HTTPException(status_code=400, detail="Missing note_id in payload")
    
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Missing workspace_id in payload")
    
    # WorkspaceRepositoryを使ってworkspaceを取得
    workspace_repo = WorkspaceRepository(supabase)
    workspace = await workspace_repo.find_by_id(workspace_id)
    
    if not workspace:
        print(f"❌ Workspace {workspace_id} not found")
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    # personalワークスペース以外はスキップ
    if workspace.type != "personal":
        print(f"🚫 Skipped webhook for workspace_id={workspace_id}, type={workspace.type}")
        return {"status": "ignored", "reason": "Not personal workspace"}
    
    if not note_text:
        print(f"⚠️ Note {note_id} has no text, skipping task generation")
        return {"status": "skipped", "reason": "empty_note"}
    
    # TODO: 将来的にworkspace_idからuser_idを取得する処理を追加
    user_id = "58e744e7-ec0f-45e1-a63a-bc6ed71e10de"  # 仮
    
    try:
        # AIでタスクを生成（note_textを直接渡す）
        tasks = await generate_tasks_from_note(note_id, note_text, user_id)
        print(f"🧠 Generated {len(tasks)} tasks from note {note_id}")
        return {"status": "ok", "generated_count": len(tasks)}
    except Exception as e:
        print(f"❌ Error generating tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Task generation failed: {str(e)}")


@app.post("/webhooks/tasks")
async def tasks_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """Supabase Webhookから呼ばれ、taskをキューに追加"""
    global processing_task
    
    # セキュリティチェック
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized webhook call")
    
    body = await request.json()
    record = body.get("record") or {}
    
    task_id = record.get("id")
    source_note_id = record.get("source_note_id")
    
    if not task_id or not source_note_id:
        print(f"⚠️ Invalid webhook payload: task_id={task_id}, source_note_id={source_note_id}")
        return {"status": "ignored", "reason": "missing_required_fields"}
    
    # キューに追加
    async with queue_lock:
        task_notification_queue[task_id] = source_note_id
        
        # 既存の処理タスクをキャンセル
        if processing_task and not processing_task.done():
            processing_task.cancel()
        
        # 新しい処理タスクを起動
        processing_task = asyncio.create_task(process_task_notification_queue())
    
    print(f"📝 Task {task_id} added to queue (total: {len(task_notification_queue)})")
    return {"status": "queued", "task_id": task_id}