"""Prompt template for completion notification generation after AI task execution"""
from langchain_core.prompts import ChatPromptTemplate


completion_notification_prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        "あなたはAIタスクの実行完了をユーザーに通知する専門家です。"
        "タスクが完了したことを親しみやすく、簡潔に伝える通知を生成してください。"
        "すべての内容は必ず日本語で記述してください。"
    ),
    (
        "user",
        """以下のAIタスクが実行されました。完了通知を1つ生成してください。

タスクタイトル: {task_title}

実行結果の概要: {result_title}

実行結果の詳細:
{result_text}

要求:
- 通知は必ず日本語で記述してください
- 通知は1つだけ生成してください
- タイトルは「○○を終わらせました」のような完了を伝える形式にしてください
- 本文（body）は100-150文字程度で、完了した内容の概要や次のアクションを簡潔に記述してください
- ai_contextには、通知生成の判断根拠やタスクの詳細分析を記述してください（ユーザーには表示されません）
- 親しみやすく、達成感を感じられる内容にしてください"""
    )
])

