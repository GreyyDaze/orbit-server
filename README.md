# Orbit Server 🪐

The backend API and websocket server for **Orbit**, an anonymous feedback board system.

## ✨ Features

- **Ghost Identity System**: Zero-login authentication using persistent, hashed "Ghost IDs".
- **Real-Time WebSockets**: Powered by Django Channels and Redis for live board updates.
- **Board Management**: Secure creation, claiming, and administration of feedback boards.
- **Permissions System**: Granular permission logic for Authors, Admins, and Guests.
- **Background Tasks**: Celery workers for housekeeping and async processing.

## 🛠 Tech Stack

- **Framework**: [Django 5](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/)
- **Real-Time**: [Django Channels](https://channels.readthedocs.io/) + [Redis](https://redis.io/)
- **Asynchronous**: [Celery](https://docs.celeryq.dev/) + [Celery Beat](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
- **Database**: PostgreSQL
- **Security**: SimpleJWT, CORS Headers

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

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

4.  Configure environment:
    Ensure `.env` exists (or export variables) for `DATABASE_URL`, `REDIS_URL`, etc.

5.  **Start Infrastructure (Postgres & Redis)**:

    ```bash
    docker-compose up -d
    ```

    This spins up the database and redis containers in the background.

6.  Run Migrations:

    ```bash
    python3 manage.py migrate
    ```

7.  Start the Server:

    ```bash
    # Run the Django Dev Server (WebSockets + API)
    python3 manage.py runserver
    ```

8.  Start Celery (for background tasks):

    ```bash
    # Worker
    celery -A config worker -l info

    # Beat (Scheduler)
    celery -A config beat -l info
    ```

## 🔗 Connection

Connects to `orbit-client`. Ensure CORS settings allow requests from your frontend domain.
