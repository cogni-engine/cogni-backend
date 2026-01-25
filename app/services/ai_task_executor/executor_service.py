"""AI Task Executor service with LangChain"""
import logging
from typing import Tuple, List, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.models.task import Task
from app.utils.datetime_helper import get_current_datetime_ja
from .models.executor_response import FormattedExecutionResponse

logger = logging.getLogger(__name__)


# Prompt template for structured execution with web search
_executor_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an AI assistant that executes tasks and produces well-formatted deliverables.

Prioritize clarity and conciseness. Shorter, high-value content is better than lengthy filler.

Your output must be structured with:
1. result_title: A concise title (max 30 chars) summarizing what you accomplished
2. result_text: The deliverable formatted as clean, readable Markdown

Formatting guidelines for result_text:
- Use ## and ### headings to structure content logically
- Use bullet points (-) and numbered lists (1.) where appropriate
- Use **bold** for key points and emphasis
- Use `code` for technical terms, commands, or code snippets
- Use tables (| col1 | col2 |) for comparative data
- Keep paragraphs concise and scannable
- If you used web sources, add a "## References" section at the end with: - [Title](URL)

Do NOT include meta-commentary like "Here is the result" - output the deliverable directly."""
    ),
    (
        "user",
        """Execute the following task and produce a well-formatted deliverable:

Task: {task_title}

Details:
{task_description}

Current datetime: {current_datetime}

Produce the deliverable with a title and formatted Markdown content."""
    )
])


def _extract_text_and_citations(content: Any) -> Tuple[str, List[dict]]:
    """
    Extract text and citations from LLM response content.
    Handles both simple string responses and structured responses with annotations.
    """
    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return str(content), []

    texts = []
    citations = []

    for item in content:
        # Handle ContentBlock objects (from OpenAI Responses API)
        if hasattr(item, 'text'):
            texts.append(item.text)
            if hasattr(item, 'annotations'):
                for ann in item.annotations:
                    if hasattr(ann, 'url'):
                        citations.append({
                            'url': ann.url,
                            'title': getattr(ann, 'title', ann.url)
                        })
        # Handle dict format
        elif isinstance(item, dict):
            if 'text' in item:
                texts.append(item['text'])
            if 'annotations' in item:
                for ann in item['annotations']:
                    if 'url' in ann:
                        citations.append({
                            'url': ann['url'],
                            'title': ann.get('title', ann['url'])
                        })
        else:
            texts.append(str(item))

    return "\n".join(texts), citations


def _append_citations_to_markdown(text: str, citations: List[dict]) -> str:
    """Append citations as a References section if not already present."""
    if not citations:
        return text

    # Check if references section already exists
    if "## References" in text or "## 参考" in text:
        return text

    # Build references section
    refs = "\n\n## References\n"
    seen_urls = set()
    for cite in citations:
        if cite['url'] not in seen_urls:
            refs += f"- [{cite['title']}]({cite['url']})\n"
            seen_urls.add(cite['url'])

    return text + refs


async def execute_ai_task(task: Task) -> Tuple[str, str]:
    """
    Execute an AI task and return structured results with title and formatted content.

    Args:
        task: The task to execute

    Returns:
        Tuple[str, str]: (result_title, result_text)
        - result_title: Short title summarizing the deliverable
        - result_text: Well-formatted Markdown content with citations if applicable
    """
    current_datetime = get_current_datetime_ja()
    task_deadline = task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "Not specified"

    # Initialize LLM with web search (minimal context) and structured output
    llm = ChatOpenAI(model="gpt-5.1", use_responses_api=True)
    web_search_tool = {"type": "web_search_preview", "search_context_size": "low"}
    llm_with_tools = llm.bind_tools([web_search_tool])
    structured_llm = llm_with_tools.with_structured_output(FormattedExecutionResponse)

    chain = _executor_prompt | structured_llm

    try:
        result: FormattedExecutionResponse = await chain.ainvoke({
            "task_title": task.title,
            "task_description": task.description or "No details provided",
            "current_datetime": current_datetime
        })

        logger.info(f"AI task executed successfully: task_id={task.id}, title={task.title}")
        return (result.result_title, result.result_text)

    except Exception as e:
        logger.error(f"Failed to execute AI task: task_id={task.id}, error={e}")

        # Fallback: try without structured output
        try:
            fallback_llm = ChatOpenAI(model="gpt-5.1", use_responses_api=True)
            fallback_with_tools = fallback_llm.bind_tools([web_search_tool])
            fallback_chain = _executor_prompt | fallback_with_tools

            fallback_result = await fallback_chain.ainvoke({
                "task_title": task.title,
                "task_description": task.description or "No details provided",
                "current_datetime": current_datetime
            })

            text, citations = _extract_text_and_citations(fallback_result.content)
            formatted_text = _append_citations_to_markdown(text, citations)

            # Generate simple title from task title
            title = task.title[:30] if len(task.title) <= 30 else task.title[:27] + "..."

            logger.info(f"AI task executed with fallback: task_id={task.id}")
            return (title, formatted_text)

        except Exception as fallback_error:
            logger.error(f"Fallback also failed: task_id={task.id}, error={fallback_error}")
            error_text = f"## Error\n\nTask execution failed: {str(e)}"
            return ("Execution Error", error_text)

