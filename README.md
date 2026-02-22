# Orbit Server 🪐

The backend API and websocket server for **Orbit**, an anonymous feedback board system.

## ✨ Features

- **Ghost Identity System**: Zero-login authentication using persistent, hashed "Ghost IDs".
- **Real-Time WebSockets**: Powered by Django Channels and Redis for live board updates.
- **Board Management**: Secure creation, claiming, and administration of feedback boards.
- **Permissions System**: Granular permission logic for Authors, Admins, and Guests.
- **Stripe Integration**: Secure payment processing and webhook handling for Orbit Pro.
- **Freemium Lifecycle**: Server-side enforcement of board limits and automated data retention/purging policies.
- **Background Tasks**: Celery workers for housekeeping and async processing.

## � System Architecture

Orbit uses a **Real-Time Event Bus** architecture:

1.  **API Layer**: Django REST Framework handles board configuration and persistent storage (PostgreSQL).
2.  **Websocket Layer**: Django Channels manages long-lived connections.
3.  **State Broker**: Redis acts as the Channel Layer, broadcasting note movements and edits to all connected peers in a "Board Group".
4.  **Worker Layer**: Celery handles asynchronous tasks like data purging and payment reconciliation.

## �🛠 Tech Stack

- **Framework**: [Django 5](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/)
- **Real-Time**: [Django Channels](https://channels.readthedocs.io/) + [Redis](https://redis.io/)
- **Asynchronous**: [Celery](https://docs.celeryq.dev/) + [Celery Beat](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
- **Database**: PostgreSQL
- **Testing**: [Pytest](https://pytest.org/), [Factory Boy](https://factoryboy.readthedocs.io/), [k6](https://k6.io/) (Load Testing)
- **Security**: SimpleJWT, CORS Headers

## � Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

### �🔐 Environment Variables

Create a `.env` file in the root directory:

```env
DEBUG=True
SECRET_KEY=your_django_secret_key
DATABASE_URL=postgres://user:pass@localhost:5432/orbit
REDIS_URL=redis://localhost:6379/1
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

### Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/GreyyDaze/orbit-server.git
    cd orbit-server
    ```

2.  Create and activate virtual environment:

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

4.  **Start Infrastructure (Postgres & Redis)**:

    ```bash
    docker-compose up -d
    ```

    This spins up the database and redis containers in the background.

5.  Run Migrations:

    ```bash
    python3 manage.py migrate
    ```

6.  Start the Server:

    ```bash
    # Run the Django Dev Server (WebSockets + API)
    python3 manage.py runserver
    ```

7.  Start Celery (for background tasks):

    ```bash
    # Worker
    celery -A config worker -l info

    # Beat (Scheduler)
    celery -A config beat -l info
    ```

## 🗺 Project Structure

```text
├── workspace/          # Core Board & Note logic (API ViewSets)
├── identity/           # Ghost ID system, AnonymousProfile & Auth logic
├── payments/           # Stripe Checkout & Webhook handlers
├── config/             # Django Settings, URLs, and WSGI/ASGI entry points
├── scripts/            # Benchmarking and utility scripts
└── requirements.txt    # Project dependencies
```

## 🧪 Testing & Verification

The backend uses **Pytest** with **Risk-Based Integration Testing** to ensure the integrity of the freemium model and security rules.

### Running Tests

```bash
# Run the complete test suite
pytest

# Run tests with verbose output
pytest -v
```

### Strategic Reflection: Integration over Isolation

In the `orbit-server` repo, we intentionally prioritize **Integration Tests** over isolated Unit tests.

- **Why?** In a Django-based system, the most critical failures happen at the intersection of Permissions, Database Queries, and API Responses.
- **The Goal**: By testing the real endpoints against a real (test) database, we verify that the "freemium guardrails" (like the 2-board limit for Guests) are strictly enforced. We avoid "mocking" the database here because we want to test the **actual state** of the data, not a simulated version of it.

## 📈 Performance Testing

The project includes a [k6](https://k6.io/) script to benchmark WebSocket performance.

1.  **Install k6**: `brew install k6`
2.  **Run Test**:
    ```bash
    # Replace with a valid board ID from your local DB
    BOARD_ID="your-uuid-here" k6 run scripts/load_test.js
    ```
