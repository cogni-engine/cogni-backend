# Cogni Backend

Billing・ユーザー管理・Push通知を担当する軽量APIサーバー。

> **Note**: AI関連機能（チャット、ノートAI編集、オンボーディング、メモリ、タスク実行等）は全て [cogno-core](../cogno-core/) に移行済みです。

## Features

- ✅ Billing & Subscription management (Stripe)
- ✅ Organization management
- ✅ User management
- ✅ Push notification support via Expo
- ✅ RLS-friendly architecture

## Project Structure

```
cogni-backend/
├── app/
│   ├── api/                       # FastAPI route handlers
│   │   ├── health.py              # Health check
│   │   ├── users.py               # User endpoints
│   │   ├── organizations.py       # Organization endpoints
│   │   └── push_notifications.py  # Push notification endpoints
│   ├── features/
│   │   └── billing/               # Billing feature (Stripe integration)
│   │       ├── api.py
│   │       ├── service.py
│   │       ├── webhook_service.py
│   │       ├── domain.py
│   │       ├── schemas.py
│   │       ├── models/
│   │       ├── repositories/
│   │       └── services/
│   ├── services/
│   │   └── push_notification_service.py
│   ├── db/models/                 # Database models
│   ├── config.py                  # Configuration (Supabase, Stripe)
│   └── main.py                    # FastAPI application
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.prod
├── render.yaml
├── pyproject.toml
└── README.md
```

## Setup

### Prerequisites

- Python 3.13+
- Poetry
- Supabase account with configured database

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
```

```
# Supabase
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Frontend URL (for CORS and Stripe redirects)
CLIENT_URL=http://localhost:3000

# Stripe
STRIPE_SECRET_KEY=sk_test_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
STRIPE_PRICE_ID_PRO=price_xxxxx
STRIPE_PRICE_ID_BUSINESS=price_xxxxx
```

### Running the Application

```bash
# Docker Compose
docker-compose up

# Or without Docker
poetry run uvicorn app.main:app --reload
```

The API will be available at:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

## API Endpoints

### Billing & Subscriptions
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/billing/purchase` | Universal plan purchase (Pro/Business) | JWT |
| POST | `/api/billing/portal-session` | Create Stripe Customer Portal session | JWT |
| POST | `/api/billing/pro/purchase` | Create Pro plan checkout session (legacy) | - |
| POST | `/api/billing/upgrade-to-business` | Upgrade from Pro to Business plan | - |
| POST | `/api/billing/sync-seats` | Sync subscription seats with member count | - |
| POST | `/api/billing/update-seats` | Manually update subscription seats | - |
| POST | `/api/stripe/webhook` | Handle Stripe webhook events | - |

### Push Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/push-notifications/health` | Health check |
| POST | `/api/push-notifications/send` | Send push notification (Supabase webhook) |

### Users / Organizations
| Method | Endpoint | Description |
|--------|----------|-------------|
| - | `/api/users/*` | User management |
| - | `/api/organizations/*` | Organization management |

## Tech Stack

- **Framework**: FastAPI
- **Language**: Python 3.13+
- **Package Manager**: Poetry
- **Database**: Supabase (PostgreSQL)
- **Payment**: Stripe
- **Type Safety**: Pydantic v2
- **Deployment**: Docker, Render
