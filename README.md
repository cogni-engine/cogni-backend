# Cogni Backend

A FastAPI-based backend for the Cogni application with a clean repository pattern for Supabase database operations.

## Features

- ✅ Clean repository pattern abstracting Supabase
- ✅ Type-safe domain models with Pydantic
- ✅ FastAPI endpoints for all entities
- ✅ OpenAI integration for AI-powered conversations and task execution
- ✅ Comprehensive CRUD operations for tasks, notes, threads, and notifications
- ✅ Recurring task management with flexible recurrence patterns
- ✅ AI-powered task generation from notes
- ✅ AI-powered notification generation from tasks
- ✅ Push notification support via Expo
- ✅ Webhook endpoints for scheduled tasks and background processing
- ✅ RLS-friendly architecture

## Project Structure

```
cogni-backend/
├── app/
│   ├── api/                    # FastAPI route handlers
│   │   ├── cogno.py            # Cogno AI conversation endpoints
│   │   ├── notes.py            # Note-related endpoints
│   │   ├── tasks.py            # Task CRUD and AI endpoints
│   │   ├── webhooks.py         # Webhook endpoints for CRON jobs
│   │   └── push_notifications.py # Push notification endpoints
│   ├── models/                 # Domain models (Pydantic)
│   │   ├── task.py
│   │   ├── task_result.py
│   │   ├── note.py
│   │   ├── thread.py
│   │   ├── ai_message.py
│   │   ├── notification.py
│   │   ├── push_notification.py
│   │   ├── workspace.py
│   │   ├── user.py
│   │   ├── chat.py
│   │   └── recurrence.py
│   ├── infra/
│   │   └── supabase/
│   │       ├── client.py       # Supabase client singleton
│   │       └── repositories/   # Repository implementations
│   │           ├── base.py
│   │           ├── tasks.py
│   │           ├── task_results.py
│   │           ├── notes.py
│   │           ├── threads.py
│   │           ├── ai_messages.py
│   │           ├── notifications.py
│   │           └── workspaces.py
│   ├── services/               # Business logic services
│   │   ├── cogno/              # Cogno AI engine and conversation
│   │   ├── ai_task_executor/  # AI task execution service
│   │   ├── note_to_task/      # Generate tasks from notes
│   │   ├── task_to_notification/ # Generate notifications from tasks
│   │   ├── task/              # Recurring task service
│   │   ├── llm/               # LLM utilities
│   │   ├── file_processor/    # File processing
│   │   └── push_notification_service.py
│   ├── utils/                 # Utility functions
│   │   ├── datetime_helper.py
│   │   └── recurrence_calculator.py
│   ├── data/                  # Mock data for development
│   ├── config.py              # Configuration and clients
│   └── main.py                # FastAPI application
├── docker-compose.yml         # Docker Compose configuration
├── Dockerfile                 # Development Dockerfile
├── Dockerfile.prod            # Production Dockerfile
├── render.yaml                # Render deployment config
├── pyproject.toml             # Poetry dependencies
└── README.md
```

## Setup

### Prerequisites

- Python 3.13+
- Poetry
- Supabase account with configured database
- OpenAI API key

### Installation

1. Clone the repository
```bash
cd cogni-backend
```

2. Install dependencies
```bash
poetry install
```

3. Configure environment variables

Copy the example environment file and fill in your values:
```bash
cp .env.example .env
# Supabase
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Frontend URL (for CORS and Stripe redirects)
CLIENT_URL=http://localhost:3000

# Stripe
STRIPE_SECRET_KEY=sk_test_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
STRIPE_PRICE_ID_PRO=price_xxxxx
STRIPE_PRICE_ID_BUSINESS=price_xxxxx
```

Then edit `.env` and fill in your actual values:
- `SUPABASE_URL` - Your Supabase project URL (from Supabase project settings)
- `SUPABASE_SERVICE_ROLE_KEY` - Your Supabase service role key (from Supabase project settings)
- `OPENAI_API_KEY` - Your OpenAI API key (from https://platform.openai.com/api-keys)
- `WEBHOOK_SECRET` - Optional, for webhook verification
- `CLIENT_URL` - Optional, for CORS configuration (default: http://localhost:3000)

### Running the Application

The easiest way to run the application is using Docker Compose:

```bash
docker-compose up
```

This will:
- Build the Docker image
- Start the FastAPI server on port 8000
- Enable auto-reload on code changes
- Load environment variables from `.env` file

The API will be available at:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**Alternative: Running without Docker**

If you prefer to run without Docker:

```bash
# Development mode with auto-reload
poetry run uvicorn app.main:app --reload

# Production mode
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Quick Start

### Using the Repository Pattern

```python
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.tasks import TaskRepository
from app.models.task import TaskCreate
from datetime import datetime, timedelta

# Get Supabase client and repository
client = get_supabase_client()
task_repo = TaskRepository(client)

# Create a task
task_data = TaskCreate(
    title="Complete MVP",
    description="Build the product",
    user_id="user-uuid",
    deadline=datetime.now() + timedelta(days=7)
)
task = await task_repo.create(task_data)

# Find task by ID
task = await task_repo.find_by_id(task.id)

# Mark task as completed
completed = await task_repo.mark_completed(task.id)
```

## API Endpoints

### Billing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/billing/pro/purchase` | Create Pro plan checkout session |

### Stripe Webhooks
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/stripe/webhook` | Handle Stripe webhook events |

### Tasks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks` | List all tasks |
| GET | `/tasks/{task_id}` | Get task by ID |
| POST | `/tasks` | Create new task |
| PUT | `/tasks/{task_id}` | Update task |
| DELETE | `/tasks/{task_id}` | Delete task |
| POST | `/tasks/{task_id}/complete` | Mark task complete |
| GET | `/tasks/user/{user_id}/pending` | Get pending tasks |
| GET | `/tasks/user/{user_id}/overdue` | Get overdue tasks |

### Cogno AI (`/api/cogno`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cogno/conversations/stream` | Stream conversation with Cogno AI (handles engine decisions, timers, task completion) |
| GET | `/api/cogno/threads/{thread_id}/messages` | Get messages for a thread (optionally since a message ID) |

### Tasks (`/api/tasks`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks?user_id={user_id}` | List all recurring tasks for a user |
| GET | `/api/tasks/{task_id}` | Get task by ID |
| POST | `/api/tasks` | Create new recurring task |
| PUT | `/api/tasks/{task_id}` | Update task |
| DELETE | `/api/tasks/{task_id}` | Delete task |
| POST | `/api/tasks/{task_id}/notifications` | Generate AI notifications for a task |

### Notes (`/api/notes`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/notes/{note_id}/tasks` | Generate AI tasks from a note |

### Webhooks (`/api/webhooks`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/sync-memories` | Sync memories (production CRON - processes notes updated in last 60 minutes, excludes dev users) |
| POST | `/api/webhooks/sync-memories-local` | Sync memories (local development - processes notes updated in last 5 minutes, dev users only) |
| POST | `/api/webhooks/process-recurring-tasks` | Process recurring tasks (generate next instances) |
| POST | `/api/webhooks/execute-ai-tasks` | Execute AI tasks (production CRON - executes tasks due in next 10 minutes, excludes dev users) |
| POST | `/api/webhooks/execute-ai-tasks-local` | Execute AI tasks (local development - executes tasks due in next 1 minute, dev users only) |

### Push Notifications (`/api/push-notifications`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/push-notifications/health` | Health check for push notification service |
| POST | `/api/push-notifications/send` | Send push notification (called by Supabase webhook) |

## Example Usage

### Creating a Recurring Task via API

```bash
curl -X POST "http://localhost:8000/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Weekly team meeting",
    "description": "Review progress and plan next week",
    "user_id": "user-123",
    "deadline": "2024-12-31T23:59:59Z",
    "status": "pending",
    "recurrence_pattern": {
      "frequency": "weekly",
      "interval": 1,
      "day_of_week": [1]
    },
    "next_run_time": "2024-12-16T10:00:00Z",
    "is_ai_task": false,
    "is_recurring_task_active": true
  }'
```

### Stream Conversation with Cogno AI

```bash
curl -X POST "http://localhost:8000/api/cogno/conversations/stream" \
  -H "Content-Type: application/json" \
  -H "Cookie: current_user_id=user-123" \
  -d '{
    "thread_id": 1,
    "messages": [
      {
        "role": "user",
        "content": "What should I focus on today?",
        "meta": null,
        "file_ids": null
      }
    ]
  }'
```

### Generate Tasks from a Note

```bash
curl -X POST "http://localhost:8000/api/notes/123/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123"
  }'
```

### Get Thread Messages

```bash
curl "http://localhost:8000/api/cogno/threads/1/messages?since=100"
```

## Database Schema

The application uses the following Supabase tables:

- `tasks` - Task management (supports recurring tasks)
- `task_results` - Results from AI task execution
- `notes` - Note-taking
- `thread` - Conversation threads
- `ai_messages` - Chat messages (linked to threads)
- `notifications` - AI-generated user notifications
- `push_notifications` - Push notification records
- `workspace` - Workspace management
- `workspace_member` - Workspace memberships
- `user_profile` - User profiles

See your Supabase schema for complete details.

## Repository Pattern

This project uses a clean repository pattern to abstract database operations. Benefits include:

- **Abstraction**: Business logic is decoupled from Supabase
- **Type Safety**: Pydantic models ensure type correctness
- **Testability**: Easy to mock repositories in tests
- **Maintainability**: Database logic is centralized
- **Reusability**: Common CRUD operations in base repository

All repositories are located in `app/infra/supabase/repositories/` and extend the base repository class for common operations.

## Tech Stack

- **Framework**: FastAPI
- **Language**: Python 3.13+
- **Package Manager**: Poetry
- **Database**: Supabase (PostgreSQL)
- **AI Integration**: OpenAI API, LangChain
- **Type Safety**: Pydantic v2
- **Async**: asyncio, httpx
- **Deployment**: Docker, Render

## Dependencies

Key dependencies (see `pyproject.toml` for complete list):

- `fastapi` - FastAPI web framework
- `uvicorn` - ASGI server
- `supabase` - Supabase Python client
- `openai` - OpenAI API client
- `langchain` / `langchain-core` / `langchain-openai` - LangChain for AI workflows
- `pydantic` ^2.0 - Data validation and serialization
- `httpx` - Async HTTP client
- `croniter` - Cron expression parsing for recurring tasks
- `python-dotenv` - Environment variable management

## Architecture Decisions

### Why Repository Pattern?

1. **Separation of Concerns**: Database logic is separate from business logic
2. **Easy Testing**: Repositories can be easily mocked
3. **Database Agnostic**: Can switch from Supabase to another DB without changing business logic
4. **RLS Friendly**: Works naturally with Supabase Row Level Security

### Why Pydantic Models?

1. **Validation**: Automatic data validation
2. **Type Safety**: Strong typing throughout the application
3. **Documentation**: Auto-generated API docs
4. **Serialization**: Easy JSON serialization/deserialization

### Service Layer Architecture

Business logic is organized into service modules:
- **Cogno Services**: AI engine decisions and conversation handling
- **Task Services**: Recurring task management and AI task execution
- **Note Services**: AI-powered task generation from notes
- **Notification Services**: AI-powered notification generation from tasks
- **Push Notification Service**: Expo push notification handling

## Contributing

1. Create a feature branch
2. Make your changes
3. Ensure tests pass
4. Submit a pull request

## License

MIT

## Support

For issues or questions, please open an issue on GitHub.

