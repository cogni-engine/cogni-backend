"""Main FastAPI application with repository pattern"""
import os
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Optional
import datetime

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories import RepositoryFactory
from app.models.task import Task, TaskCreate, TaskUpdate
from app.models.note import Note, NoteCreate, NoteUpdate
from app.models.thread import Thread, ThreadCreate
from app.models.ai_message import AIMessage, AIMessageCreate, MessageRole
from app.models.notification import Notification, NotificationCreate

load_dotenv(dotenv_path=".env")

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)
app = FastAPI(title="Cogni Backend", version="0.1.0")


# Dependency for repository factory
def get_repositories() -> RepositoryFactory:
    """Dependency for repository factory"""
    supabase_client = get_supabase_client()
    return RepositoryFactory(supabase_client)


# ===== Pydantic Models for API =====
class ChatRequest(BaseModel):
    question: str
    thread_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: int


# ===== Root Endpoint =====
@app.get("/")
def read_root():
    return {"message": "Cogni Backend API", "version": "0.1.0"}


# ===== Task Endpoints =====
@app.get("/tasks", response_model=List[Task])
async def get_tasks(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get tasks with optional filters"""
    if user_id and status:
        return await repos.tasks.find_by_status(user_id, status)
    elif user_id:
        return await repos.tasks.find_by_user(user_id)
    else:
        return await repos.tasks.find_all()


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(
    task_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get a specific task by ID"""
    task = await repos.tasks.find_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks", response_model=Task)
async def create_task(
    task: TaskCreate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Create a new task"""
    return await repos.tasks.create(task)


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: int,
    task: TaskUpdate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Update a task"""
    updated_task = await repos.tasks.update(task_id, task)
    if not updated_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated_task


@app.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Delete a task"""
    success = await repos.tasks.delete(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@app.post("/tasks/{task_id}/complete", response_model=Task)
async def complete_task(
    task_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Mark a task as completed"""
    task = await repos.tasks.mark_completed(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks/user/{user_id}/pending", response_model=List[Task])
async def get_pending_tasks(
    user_id: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all pending tasks for a user"""
    return await repos.tasks.find_pending_tasks(user_id)


@app.get("/tasks/user/{user_id}/overdue", response_model=List[Task])
async def get_overdue_tasks(
    user_id: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all overdue tasks for a user"""
    return await repos.tasks.find_overdue_tasks(user_id)


# ===== Note Endpoints =====
@app.get("/notes", response_model=List[Note])
async def get_notes(
    workspace_id: Optional[int] = None,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all notes, optionally filtered by workspace"""
    if workspace_id:
        return await repos.notes.find_by_workspace(workspace_id)
    return await repos.notes.find_all()


@app.get("/notes/{note_id}", response_model=Note)
async def get_note(
    note_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get a specific note"""
    note = await repos.notes.find_by_id(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.post("/notes", response_model=Note)
async def create_note(
    note: NoteCreate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Create a new note"""
    return await repos.notes.create(note)


@app.put("/notes/{note_id}", response_model=Note)
async def update_note(
    note_id: int,
    note: NoteUpdate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Update a note"""
    updated_note = await repos.notes.update(note_id, note)
    if not updated_note:
        raise HTTPException(status_code=404, detail="Note not found")
    return updated_note


@app.delete("/notes/{note_id}")
async def delete_note(
    note_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Delete a note"""
    success = await repos.notes.delete(note_id)
    if not success:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"message": "Note deleted successfully"}


@app.get("/notes/workspace/{workspace_id}/search", response_model=List[Note])
async def search_notes(
    workspace_id: int,
    q: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Search notes by text"""
    return await repos.notes.search_by_text(workspace_id, q)


# ===== Thread & AI Message Endpoints =====
@app.get("/threads", response_model=List[Thread])
async def get_threads(
    workspace_id: Optional[int] = None,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all threads, optionally filtered by workspace"""
    if workspace_id:
        return await repos.threads.find_by_workspace(workspace_id)
    return await repos.threads.find_all()


@app.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(
    thread_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get a specific thread"""
    thread = await repos.threads.find_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.post("/threads", response_model=Thread)
async def create_thread(
    thread: ThreadCreate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Create a new thread"""
    return await repos.threads.create(thread)


@app.get("/threads/{thread_id}/messages", response_model=List[AIMessage])
async def get_thread_messages(
    thread_id: int,
    limit: Optional[int] = 50,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get messages from a thread"""
    return await repos.ai_messages.get_recent_messages(thread_id, limit)


@app.post("/threads/{thread_id}/messages", response_model=AIMessage)
async def create_message(
    thread_id: int,
    content: str,
    role: MessageRole,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Add a message to a thread"""
    message = AIMessageCreate(content=content, thread_id=thread_id, role=role)
    return await repos.ai_messages.create(message)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """
    Chat endpoint with AI - creates or continues a conversation thread
    """
    # Get or create thread
    if request.thread_id:
        thread = await repos.threads.find_by_id(request.thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
    else:
        # Create new thread
        thread = await repos.threads.create(ThreadCreate(title="New Chat"))
    
    # Save user message
    user_message = AIMessageCreate(
        content=request.question,
        thread_id=thread.id,
        role=MessageRole.USER
    )
    await repos.ai_messages.create(user_message)
    
    # Get conversation history
    messages = await repos.ai_messages.find_by_thread(thread.id)
    
    # Convert to OpenAI format
    openai_messages = [
        {"role": msg.role.value, "content": msg.content}
        for msg in messages
    ]
    
    # Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=openai_messages,
    )
    
    answer = response.choices[0].message.content
    
    # Save assistant message
    assistant_message = AIMessageCreate(
        content=answer,
        thread_id=thread.id,
        role=MessageRole.ASSISTANT
    )
    await repos.ai_messages.create(assistant_message)
    
    return ChatResponse(answer=answer, thread_id=thread.id)


# ===== Notification Endpoints =====
@app.get("/notifications/user/{user_id}", response_model=List[Notification])
async def get_user_notifications(
    user_id: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all notifications for a user"""
    return await repos.notifications.find_by_user(user_id)


@app.get("/notifications/user/{user_id}/scheduled", response_model=List[Notification])
async def get_scheduled_notifications(
    user_id: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get scheduled notifications for a user"""
    return await repos.notifications.find_scheduled_notifications(user_id)


@app.post("/notifications", response_model=Notification)
async def create_notification(
    notification: NotificationCreate,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Create a new notification"""
    return await repos.notifications.create(notification)


@app.put("/notifications/{notification_id}/sent", response_model=Notification)
async def mark_notification_sent(
    notification_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Mark a notification as sent"""
    notification = await repos.notifications.mark_sent(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@app.put("/notifications/{notification_id}/cancel", response_model=Notification)
async def cancel_notification(
    notification_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Cancel a notification"""
    notification = await repos.notifications.cancel_notification(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


# ===== Workspace Endpoints =====
@app.get("/workspaces")
async def get_workspaces(
    user_id: Optional[str] = None,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get workspaces, optionally filtered by user"""
    if user_id:
        return await repos.workspaces.find_user_workspaces(user_id)
    return await repos.workspaces.find_all()


@app.get("/workspaces/{workspace_id}/members")
async def get_workspace_members(
    workspace_id: int,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get all members of a workspace"""
    return await repos.workspace_members.find_by_workspace(workspace_id)


# ===== User Profile Endpoints =====
@app.get("/users/{user_id}")
async def get_user_profile(
    user_id: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Get a user profile"""
    user = await repos.users.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/users/search/{username}")
async def search_users(
    username: str,
    repos: RepositoryFactory = Depends(get_repositories)
):
    """Search for users by username"""
    return await repos.users.search_users(username)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

