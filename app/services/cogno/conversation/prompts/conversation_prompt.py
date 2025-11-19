"""System prompt for conversation AI"""
from typing import Optional, List, Dict
import json
from app.models.task import Task
from app.models.notification import AINotification
from app.utils.datetime_helper import get_current_datetime_ja, format_datetime_ja


CONVERSATION_BASE_PROMPT = """あなたはCognoという名前の、親切で知的なAIアシスタントです。"""


TIMER_REQUEST_ADDITION = """

【タイマー設定について】
ユーザーがこれから長時間かかる作業や外出をする予定のようです。
作業が終わったら、その状況を確認したいので、ユーザーに「何分で終わりますか？」「どれくらい時間がかかりそうですか？」と自然に質問してください。
やることが明確でないなら簡単に質問して確認してください。

例：
- 「何分くらいかかりそうですか？タイマーを設定しておきますね」
- 「どれくらいで戻られますか？」
- 「所要時間を教えていただければ、時間になったら声をかけます」

ユーザーが時間を答えたら、それを確認して会話を続けてください。
"""


TIMER_STARTED_ADDITION = """

【タイマー設定完了】
{duration_display}のタイマーを設定しました。
ユーザーの作業を応援し、時間になったら声をかける旨を簡潔に伝えてください。
また、進める上で何か困っていることがあったらすぐに伝えるように言ってください。
やることを簡潔にまとめたり、難しいポイントを提示して、その解決策を提示することや、別のやり方を提示することも有効です
ユーザが進める上で障壁になり得るものなどがあれば、それらを軽減する方法や工夫も一言添えてみてください。
現在ユーザがやろうとしている作業については触れるようにしましょう
そもそもやることを十分に把握できていない場合には、きちんとユーザーに確認してください。やることを明確化する必要性もあります。
"""


TIMER_COMPLETED_ADDITION = """

【タイマー完了 - チェックイン】
タイマーが完了しました。今こそユーザーの状況を確認し、なるべく簡潔に、適切にサポートしてください。

【あなたがすべきこと】
1. 進捗を簡単に確認
   - 例:「時間になりました！いかがですか？」
2. 状況に合わせた提案
   - 完了なら称賛と次の一歩、途中なら残りや時間延長、詰まりがあればサポート
   - 予定外なら優先度や今後の行動の相談
3. 必要に応じてフィードバックも提案。そもそも何をやっていたのか明確でない場合には、きちんとユーザーに確認してください。

【ポイント】
- 親しみやすく建設的、一緒に進める雰囲気で
- 具体的な次のアクションを提案

ユーザーが前向きに次に進めるようサポートしてください。
"""


NOTIFICATION_TRIGGERED_ADDITION = """

【通知トリガー】
直前の会話内容（存在すれば）から話題が変わることを伝えつつ、通知内容を簡潔に会話形式で伝えてください。

【指示】
- 最初に通知内容・取り組むことを一言で要約して伝える　題名のような感じで、大文字で通知のタイトルから始める
- 状況の確認や着手・進捗・質問も必要であれば
- 優先度や締切、次のアクションがあれば簡潔に促す
- 上記の内容を、通知として捉えられるような短文にまとめる

【例】
- 通知のタイトル: 締切が近いやること
- 「締切が近いやること:○○があります。今、対応できますか？」
- 「進捗はいかがですか？困っていることがあれば教えてください。」

【ゴール】
出力はダイレクトで短く、"通知"としてすぐ理解・行動できる形にしてください。出力は5行に収まる程度にしてください。
"""


SUGGEST_IMPORTANT_TASKS_ADDITION = """

【重要なことの提案】
今取り組んでいることはありませんが、以下のやることがあります：

{task_list_str}

現在時刻: {current_time}

あなたの役割：
- 期限が近いもの、重要度が高そうなものを2-3個ピックアップ
- 「タスク」という言葉は避け、自然な会話で提案
- 過ぎているものも含め、期限を適宜伝えながら緊急性を伝える
- ユーザーのモチベーションを上げる言い回しで
- 具体的な行動を促す
- どれくらい進んでいるか、終わらせたかの確認をする

例：
- 「今日中に○○を片付けておくと安心ですね」
- 「△△の期限が迫っているので、今取り組みませんか？」
- 「□□から始めるのはどうでしょう？」

【注意】
- やること、予定、といった自然な言葉で表現
- 押し付けがましくなく、前向きに
"""


TASK_COMPLETION_CONFIRMATION_ADDITION = """

【完了の最終確認】
ユーザーが「{task_title}」の完了を示唆しました。

あなたの役割：
- 説明に書かれている内容を元に、残っているやるべきことを特定する
- 残っていることがあれば、それを実行するように提案する
- 残っていることがなければ、完了かどうか、隅々まで終わっているか、内容とともに確認して次のステップに進む
- 完了を急がせず、丁寧に対応すること

情報：
- タイトル: {task_title}
- 説明: {task_description}
- 期限: {task_deadline}

【アプローチ】
1. 説明の内容を詳しく見て、やるべきことのリストを確認する
2. 残っていることがあれば、「○○はまだ残っていますね。一緒にやりましょう」という形で提案する
3. 残っていることがなければ、完了かどうかを確認して次のステップに進む

"""


FOCUSED_TASK_ADDITION = """
【今取り組んでいること】
『{task_title}』
締切: {deadline_str}
{description_section}{status_section}

【あなたの役割と行動指針】
あなたの最優先目標は、ユーザーと協働して取り組みを実際に完遂することです。

【実行アプローチ】
1. やることの分割と実行
   - 大きなことは小さなステップに分割して、一つずつ進める
   - ただし、原則的には【方法・手順】を、一つ一つ順番にやっていく（一回の会話で一つのステップを完了させる）
   - 今すぐ実行できる具体的なアクションを提案する
   - 各ステップを完了させてから次に進む

2. 情報収集と意思決定支援
   - 実行に必要な情報が不足している場合は、具体的に質問する
   - 選択肢を提示して、ユーザーの意思決定をサポートする
   - 調べるべきことや確認すべきポイントを明確にする

3. 実際の実行
   - 雛形やテンプレート、具体例を作成して提示する
   - リサーチが必要なら情報を調べて提供する
   - コードやドキュメントなど、成果物を実際に作成する
   - 「やりましょうか？」と提案し、実行する

4. 進捗管理と時間見積もり
   - ユーザーがやることが必要な場合は、どれくらい時間がかかるか確認する
   - 待ち時間が発生する場合は、その間にできることを提案する
   - 締切を意識して、優先順位を調整する

5. 協働的な姿勢
   - 「一緒に考えましょう」「一緒にやりましょう」という姿勢で臨む
   - ユーザーの意見や状況を尊重しつつ、前進を促す
   - 詰まったら、別のアプローチを提案する

【コミュニケーションスタイル】
- 親しみやすく、でも的確で具体的に
- 抽象的な助言ではなく、実行可能なアクションを示す
- 必要に応じて断定的に（例：「まずこれをやりましょう」「次はこれです」）
- 同じことを繰り返さず、常に会話を前進させる
- 完了したステップは明確に確認し、次に進む

【ゴール】
やることを「話す」だけでなく、「実際に終わらせる」こと。
ユーザーと二人三脚で、確実に完遂まで導いてください。
"""


RELATED_TASKS_ADDITION = """

【このノートから生成されたやること】
ノートタグ: {note_mention_line}

{formatted_tasks_list}

これらは同じノート「{source_note_title}」から生成されたものです。
ノートに言及する場合は、上記のタグをそのまま出力に埋め込んでください。属性名・順序・引用符を変更したり省略したりしてはいけません。

関連性を意識しながら、今取り組んでいることの完遂をサポートしてください。
目標は、ユーザがノートのすべてのやることを終わらせることです。そのために、今取り組んでいることを完璧に終わらせ、他のやることも順番に終わらせていきましょう。

【注意】
次のやることに進む場合には、先ほど取り組んでいたことがきちんと終わっているかどうか確実に確認してから進めてください。
"""


WORKSPACE_ADDITION = """

【ワークスペースとメンバー情報】
- ワークスペースタグ: {workspace_line}
- タイプ: {workspace_type}

メンバータグ一覧（タグをそのまま使用すること）:
{members_list}

タグは一意のID（例: workspace-5, member-52）を含みます。必ず提示されたタグをそのまま会話で使用し、書式を変更しないでください。
"""


MENTION_RULES_ADDITION = """

【メンション出力ルール（厳守）】
- ノート／ワークスペース／ワークスペースメンバーに言及する際は、ここで提示されたタグをそのまま本文に挿入する。
- タグの属性名・順序・引用符・IDを変更・省略・補完してはならない。
- 新しい形式を作らず、提供されたタグをコピー＆ペーストする感覚で利用する。
以下が今回利用できるタグ一覧:
{mention_examples}
"""


def build_conversation_prompt(
    focused_task: Optional[Task] = None,
    related_tasks_info: Optional[List[Dict[str, str]]] = None,
    source_note_title: Optional[str] = None,
    source_note_id: Optional[int] = None,
    note_mention: Optional[str] = None,
    should_ask_timer: bool = False,
    timer_started: bool = False,
    timer_duration: Optional[int] = None,  # 秒単位に統一
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[AINotification] = None,
    daily_summary_context: Optional[str] = None,
    task_list_for_suggestion: Optional[List[Dict]] = None,  # Focused Task=Noneの場合のタスクリスト
    task_to_complete: Optional[Task] = None,  # 完了確認対象タスク
    task_completion_confirmed: bool = False,  # 完了確定フラグ
    file_context: Optional[str] = None,  # NEW: File attachments context
    workspace_info: Optional[Dict] = None,  # Workspace information
    workspace_members_info: Optional[List[Dict]] = None,  # Workspace members with profiles
    workspace_mention: Optional[str] = None,
    workspace_member_mentions: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Build conversation AI system prompt.
    
    Args:
        focused_task: Task to focus on, or None
        related_tasks_info: List of task info dictionaries with 'title' and 'status'
        source_note_title: Title extracted from the source note
        note_mention: Preformatted mention tag for the source note
        source_note_id: Numeric ID of the source note
        should_ask_timer: Whether to ask user about timer duration
        timer_started: Whether timer was just started
        timer_duration: Duration of started timer in seconds
        timer_completed: Whether timer has just completed (triggers management check-in)
        notification_triggered: Whether notification was triggered
        notification_context: Single notification context (for click)
        daily_summary_context: Daily summary of multiple notifications
        task_list_for_suggestion: Task list when no focused task exists
        task_to_complete: Task currently pending completion confirmation
        task_completion_confirmed: Whether completion is confirmed
        file_context: Additional context generated from attached files
        workspace_info: Workspace metadata dictionary
        workspace_members_info: Workspace member info dictionaries
        workspace_mention: Preformatted workspace mention tag
        workspace_member_mentions: List of dicts containing member mention tags and roles
        
    Returns:
        Complete system prompt string
    """
    base_prompt = CONVERSATION_BASE_PROMPT
    
    # Add current time
    current_time = get_current_datetime_ja()
    base_prompt += f"\n\n現在時刻: {current_time}"
    
    # Add file context if available
    if file_context:
        base_prompt += "\n\n" + file_context
    
    # Add mention rules if we have predefined tags
    mention_example_lines: List[str] = []
    if note_mention:
        mention_example_lines.append(f"- ノート: {note_mention}")
    if workspace_mention:
        mention_example_lines.append(f"- ワークスペース: {workspace_mention}")
    if workspace_member_mentions:
        for member in workspace_member_mentions:
            label = member.get("label", "メンバー")
            mention_text = member.get("mention")
            if mention_text:
                mention_example_lines.append(f"- メンバー（{label}）: {mention_text}")
    if mention_example_lines:
        mention_examples_text = "\n".join(mention_example_lines)
        base_prompt += MENTION_RULES_ADDITION.format(mention_examples=mention_examples_text)
    
    # Add task context if available
    if focused_task:
        deadline_str = format_datetime_ja(focused_task.deadline) if focused_task.deadline else "未設定"
        
        description_section = f"説明: {focused_task.description}\n" if focused_task.description else ""
        status_section = f"ステータス: {focused_task.status}\n" if focused_task.status else ""
        
        task_context = FOCUSED_TASK_ADDITION.format(
            task_title=focused_task.title,
            deadline_str=deadline_str,
            description_section=description_section,
            status_section=status_section
        )
        
        base_prompt += "\n\n" + task_context
        
        # Add workspace context if available
        if workspace_info:
            workspace_title = workspace_info.get('title', '無題')
            workspace_id = workspace_info.get('id')
            workspace_type = workspace_info.get('type', 'personal')
            
            workspace_line = workspace_mention or f"ワークスペース「{workspace_title}」(ID: {workspace_id})"
            
            # Format members list using prepared mention tags
            members_lines = []
            if workspace_member_mentions:
                for member in workspace_member_mentions:
                    mention_text = member.get("mention")
                    role = member.get("role", "member")
                    if mention_text:
                        members_lines.append(f"- {mention_text}（役割: {role}）")
            if not members_lines:
                members_lines.append("- （メンバータグがありません）")
            
            members_list = "\n".join(members_lines)
            
            base_prompt += "\n\n" + WORKSPACE_ADDITION.format(
                workspace_line=workspace_line,
                workspace_type=workspace_type,
                members_list=members_list
            )
        
        # Add related tasks from source note if available
        if related_tasks_info and source_note_title:
            # ステータスを含めて整形
            formatted_tasks = []
            for task_info in related_tasks_info:
                status = task_info.get("status", "pending")
                if status == "completed":
                    checkbox = "☑"
                else:
                    checkbox = "☐"
                formatted_tasks.append(f"{checkbox} {task_info['title']}")
            
            formatted_tasks_list = "\n".join(formatted_tasks)
            note_mention_line = note_mention or f"ノート「{source_note_title}」(ID: {source_note_id})"
            base_prompt += RELATED_TASKS_ADDITION.format(
                source_note_title=source_note_title,
                note_mention_line=note_mention_line,
                formatted_tasks_list=formatted_tasks_list
            )
    
    # Add timer request if needed
    if should_ask_timer:
        base_prompt += TIMER_REQUEST_ADDITION
    
    # Add timer started confirmation if needed
    if timer_started and timer_duration:
        # 時間・分・秒の表示用文字列を生成
        def format_duration(seconds: int) -> str:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            remaining_seconds = seconds % 60
            
            parts = []
            if hours > 0:
                parts.append(f"{hours}時間")
            if minutes > 0:
                parts.append(f"{minutes}分")
            if remaining_seconds > 0:
                parts.append(f"{remaining_seconds}秒")
            
            return "".join(parts) if parts else "0秒"
        
        duration_display = format_duration(timer_duration)
        base_prompt += TIMER_STARTED_ADDITION.format(duration_display=duration_display)
    
    # Add timer completion management instructions if needed
    if timer_completed:
        base_prompt += TIMER_COMPLETED_ADDITION
    
    # Add notification-triggered instructions if needed
    if notification_triggered:
        base_prompt += NOTIFICATION_TRIGGERED_ADDITION
        
        # Add specific notification context if single notification click
        if notification_context:
            deadline_str = format_datetime_ja(notification_context.due_date)
            notification_detail = "\n\n【通知の詳細】\n"
            notification_detail += f"タイトル: {notification_context.title}\n"
            notification_detail += f"期限: {deadline_str}\n"
            base_prompt += notification_detail
        
        # Add daily summary if provided
        if daily_summary_context:
            daily_context = f"\n\n【本日の重要事項】\n{daily_summary_context}\n"
            daily_context += "\nこれらの事項について、ユーザーと会話しながら対応を進めてください。"
            base_prompt += daily_context
    
    # Add task suggestion prompt if no focused task but tasks exist
    if task_list_for_suggestion and not focused_task:
        current_time = get_current_datetime_ja()
        task_list_str = json.dumps(task_list_for_suggestion, ensure_ascii=False, indent=2)
        base_prompt += SUGGEST_IMPORTANT_TASKS_ADDITION.format(
            task_list_str=task_list_str,
            current_time=current_time
        )
    
    # Add task completion confirmation prompt if needed
    if task_to_complete and not task_completion_confirmed:
        task_deadline_str = format_datetime_ja(task_to_complete.deadline) if task_to_complete.deadline else "未設定"
        task_description_str = task_to_complete.description or "説明なし"
        base_prompt += TASK_COMPLETION_CONFIRMATION_ADDITION.format(
            task_title=task_to_complete.title,
            task_description=task_description_str,
            task_deadline=task_deadline_str
        )
    
    return base_prompt

