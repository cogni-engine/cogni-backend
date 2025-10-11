import datetime
from typing import Dict
from app.config import openai_client
from app.data.mock_data import chat_history, mock_notifications, message_id_counter

async def generate_notification_message(notification: Dict) -> str:
    """履歴を踏まえて通知内容を自然な会話に変換"""
    
    # チャット履歴の最近10件を取得
    recent_history = chat_history[-10:] if len(chat_history) > 10 else chat_history
    
    prompt = f"""
以下のチャット履歴を踏まえて、通知の内容を自然な会話として表現してください。

チャット履歴:
{recent_history}

通知の元の内容:
{notification['content']}

要求:
- チャット履歴の文脈を考慮して、自然で親しみやすいメッセージに変換
- ユーザーとの会話の流れに合うようなトーンで表現
- 通知の重要な情報は保持しつつ、会話的で親近感のある内容に
- 簡潔にまとめて、150文字以内で表現
"""
    
    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system", 
                "content": "あなたはユーザーとの会話履歴を考慮して、通知を自然な会話メッセージに変換するAIです。親しみやすく、かつ重要な情報は漏らさないようにしてください。"
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]
    )
    
    return resp.choices[0].message.content

async def handle_chat(request, focused_task_id, mock_tasks):
    """チャットリクエストを処理"""
    import app.data.mock_data as data_module
    
    thread_id = "main_thread"
    current_time = datetime.datetime.now().isoformat()
    data_module.message_id_counter += 1
    
    # 通知処理（notification_idがある場合）
    if request.notification_id:
        notification = next((n for n in mock_notifications if n["id"] == request.notification_id), None)
        if notification:
            # 履歴を踏まえた通知メッセージを生成
            notification_message = await generate_notification_message(notification)
            
            # チャット履歴に追加
            chat_history.append({
                "role": "assistant",
                "content": notification_message
            })
            
            # 通知ステータスを更新
            notification["status"] = "delivered"
            notification["updatedAt"] = datetime.datetime.now().isoformat()
            
            # 通知の場合はnotification_messageをそのまま返す
            return {
                "message": {
                    "id": data_module.message_id_counter,
                    "threadId": thread_id,
                    "role": "assistant",
                    "content": notification_message,
                    "meta": {
                        "type": "notification",
                        "notification_id": notification["id"],
                        "task_id": notification["task_id"],
                        "suggestions": notification.get("suggestions", [])
                    },
                    "createdAt": current_time
                }
            }
    
    # 通常のチャット処理（questionがある場合のみ）
    if request.question and request.question.strip():
        chat_history.append({
            "role": "user", 
            "content": request.question
        })
    
    # タスクフォーカス更新
    from app.services.task_service import run_engine
    await run_engine()
    
    task_context = ""
    if focused_task_id is not None:
        task = next((t for t in mock_tasks if t["id"] == focused_task_id), None)
        if task:
            deadline = (
                task["deadline"].isoformat()
                if isinstance(task["deadline"], datetime.datetime)
                else str(task["deadline"])
            )
            task_context = (
                f"現在フォーカスしているタスクは『{task['title']}』です。\n"
                f"- 締切: {deadline}\n"
                f"- 方法: {task['method']}\n"
                f"- 理由: {task['reason']}\n"
            )
    
    messages = []
    if task_context:
        messages.append({
            "role": "system",
            "content": f"ユーザと自然に会話してください。以下のタスク情報は、やらなければならないこととして、マネジメントするような形で必ず考慮に入れて回答してください。特に方法について、ユーザと会話しながらふかぼって実行を助けるようにすると良いかもしれません:\n{task_context}\nただし、一回伝えたことを再度伝えることは、それがマネジメント的に必要でない限り避けてください。最後は、次やらなければならないことを能動的に提示してください"
        })
    messages.extend(chat_history)
    
    print("==== AIに投げるmessages ====")
    for m in messages:
        print(m)
    print("================================")
    
    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
    )
    
    answer = resp.choices[0].message.content
    
    chat_history.append({
        "role": "assistant", 
        "content": answer
    })
    
    # 通常のチャット応答を返す
    return {
        "message": {
            "id": data_module.message_id_counter,
            "threadId": thread_id,
            "role": "assistant",
            "content": answer,
            "meta": {
                "focused_task_id": focused_task_id
            },
            "createdAt": current_time
        }
    }

