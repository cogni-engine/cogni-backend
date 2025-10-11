# Cogni Backend

A FastAPI-based backend for the Cogni application with a clean repository pattern for Supabase database operations.

## Features

- ✅ Clean repository pattern abstracting Supabase
- ✅ Type-safe domain models with Pydantic
- ✅ FastAPI endpoints for all entities
- ✅ OpenAI integration for chat functionality
- ✅ Comprehensive CRUD operations
- ✅ RLS-friendly architecture

## Project Structure

```
cogni-backend/
├── app/
│   ├── models/                 # Domain models
│   │   ├── task.py
│   │   ├── note.py
│   │   ├── thread.py
│   │   ├── ai_message.py
│   │   ├── notification.py
│   │   ├── workspace.py
│   │   └── user.py
│   ├── infra/
│   │   └── supabase/
│   │       ├── client.py       # Supabase singleton
│   │       └── repositories/   # Repository implementations
│   │           ├── base.py
│   │           ├── tasks.py
│   │           ├── notes.py
│   │           ├── threads.py
│   │           ├── ai_messages.py
│   │           ├── notifications.py
│   │           ├── workspaces.py
│   │           └── users.py
│   └── main.py                 # FastAPI application
├── tests/
│   ├── conftest.py             # Test fixtures
│   ├── integration/            # Integration tests (87 tests)
│   │   ├── test_tasks.py
│   │   ├── test_notes.py
│   │   ├── test_threads_and_messages.py
│   │   ├── test_notifications.py
│   │   ├── test_workspaces.py
│   │   ├── test_users.py
│   │   └── test_relationships.py
│   └── README.md
├── REPOSITORY_PATTERN.md       # Detailed documentation
├── pytest.ini
├── run_tests.sh                # Test runner script
├── pyproject.toml
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

Create a `.env` file in the root directory:
```bash
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
OPENAI_API_KEY=your-openai-api-key
```

### Running the Application

```bash
# Development mode with auto-reload
poetry run uvicorn app.main:app --reload

# Production mode
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Quick Start

### Using the Repository Pattern

```python
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories import RepositoryFactory
from app.models.task import TaskCreate
from datetime import datetime, timedelta

# Get repository factory
client = get_supabase_client()
repos = RepositoryFactory(client)

# Create a task
task_data = TaskCreate(
    title="Complete MVP",
    description="Build the product",
    user_id="user-uuid",
    deadline=datetime.now() + timedelta(days=7)
)
task = await repos.tasks.create(task_data)

# Find user's tasks
tasks = await repos.tasks.find_by_user("user-uuid")

# Mark task as completed
completed = await repos.tasks.mark_completed(task.id)
```

## API Endpoints

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

### Notes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notes` | List all notes |
| GET | `/notes/{note_id}` | Get note by ID |
| POST | `/notes` | Create new note |
| PUT | `/notes/{note_id}` | Update note |
| DELETE | `/notes/{note_id}` | Delete note |
| GET | `/notes/workspace/{workspace_id}/search?q=term` | Search notes |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Chat with AI (creates/continues thread) |
| GET | `/threads` | List threads |
| GET | `/threads/{thread_id}` | Get thread by ID |
| GET | `/threads/{thread_id}/messages` | Get thread messages |
| POST | `/threads/{thread_id}/messages` | Add message to thread |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications/user/{user_id}` | Get user notifications |
| GET | `/notifications/user/{user_id}/scheduled` | Get scheduled notifications |
| POST | `/notifications` | Create notification |
| PUT | `/notifications/{notification_id}/sent` | Mark as sent |
| PUT | `/notifications/{notification_id}/cancel` | Cancel notification |

### Workspaces & Users
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/workspaces` | List workspaces |
| GET | `/workspaces/{workspace_id}/members` | Get workspace members |
| GET | `/users/{user_id}` | Get user profile |
| GET | `/users/search/{username}` | Search users |

## Example Usage

### Creating a Task via API

```bash
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Buy groceries",
    "description": "Milk, eggs, bread",
    "user_id": "user-123",
    "deadline": "2024-12-31T23:59:59Z",
    "status": "pending"
  }'
```

### Chat with AI

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What should I focus on today?"
  }'
```

### Search Notes

```bash
curl "http://localhost:8000/notes/workspace/1/search?q=meeting"
```

## Database Schema

The application uses the following Supabase tables:

- `tasks` - Task management
- `notes` - Note-taking
- `thread` - Conversation threads
- `ai_messages` - Chat messages (linked to threads)
- `notifications` - User notifications
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

For detailed documentation, see [REPOSITORY_PATTERN.md](./REPOSITORY_PATTERN.md)

## Development

### Running with Docker

```bash
docker-compose up
```

### Running Tests

The project includes **87 comprehensive integration tests** that connect to real Supabase database:

```bash
# Run all tests
./run_tests.sh all

# Run specific test suite
./run_tests.sh tasks
./run_tests.sh notes
./run_tests.sh threads
./run_tests.sh relationships

# Run with coverage
./run_tests.sh coverage

# Or use pytest directly
poetry run pytest tests/integration/ -v
```

**Test Coverage:**
- ✅ Task repository (13 tests)
- ✅ Note repository (9 tests)
- ✅ Thread & AI messages (15 tests)
- ✅ Notifications (11 tests)
- ✅ Workspaces & members (16 tests)
- ✅ User profiles (14 tests)
- ✅ Cross-entity relationships (9 tests)

See [tests/README.md](tests/README.md) for detailed testing documentation

### Code Quality

```bash
# Format code
poetry run black app/

# Lint
poetry run ruff check app/

# Type check
poetry run mypy app/
```

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

## Contributing

1. Create a feature branch
2. Make your changes
3. Ensure tests pass
4. Submit a pull request

## License

MIT

## Support

For issues or questions, please open an issue on GitHub.

