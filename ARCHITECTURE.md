# System Architecture

## 1. Overview

Orbit acts as a hybrid real-time system. It uses a **REST-first write model** where all state changes (creating notes, moving items) happen via standard HTTP API calls. Real-time updates are handled via a **Signal-Driven Broadcast** system, ensuring that one source of truth (the Database) drives both the API and the WebSockets.

---

## 2. Ghost Identity System

### 2.1 The Problem: Zero-Friction Anonymous Participation

Traditional auth systems require email/password, creating friction that kills spontaneous feedback. Orbit solves this with **Ghost Identity**: a cryptographically-backed anonymous identity that persists across sessions without any login.

### 2.2 Architecture Flow

#### Client-Side (Frontend)

1.  **Generation**: On first visit, `useGhostIdentity.ts` checks IndexedDB for an existing Ghost ID.
2.  **If Not Found**: The client calls `POST /api/v1/identity/ghost/generate/` which returns a fresh UUID (v4).
3.  **Storage**: The Ghost ID is saved to **IndexedDB** (not localStorage, for better privacy isolation).
4.  **Transmission**: Every API request includes `X-Ghost-ID: <uuid>` header.

#### Server-Side (Backend)

1.  **Middleware Interception**: `GhostIdentityMiddleware` extracts the `X-Ghost-ID` header.
2.  **Database Lookup**: `AnonymousProfile.objects.get_or_create(ghost_id=<uuid>)` ensures a DB record exists.
3.  **Request Injection**: The profile is attached as `request.ghost`, making it available to all views and permissions.

### 2.3 Upgrade Path: Claiming Identity

1.  **User Signs Up**: When a user provides an email and verifies it, their `User` record is created.
2.  **Linking**: The `AnonymousProfile.user` field is populated, linking the Ghost ID to the authenticated account.
3.  **Persistence**: The user **_keeps_** their Ghost ID. All their previously created boards/notes remain under their control.
4.  **Dual Auth**: Post-signup, the user can authenticate via **either**:
    - `X-Ghost-ID` header (anonymous mode)
    - `Authorization: Bearer <JWT>` (authenticated mode)

### 2.4 Security Model

- **No Hashing on Ghost ID**: The Ghost ID itself is stored raw in the DB. This is intentional—it's a persistent identifier, not a password.
- **30-Day Expiry**: Unclaimed Ghost IDs are soft-deleted after 30 days of creation (not activity—this prevents indefinite free-tier abuse).
- **Hard Delete**: After 7 more days (37 total), records are permanently purged by a Celery Beat task.

---

## 3. Board Access Control Architecture

### 3.1 Public vs Private Boards

Each `Board` has an `is_public` boolean:

- **Public** (`is_public=True`): Anyone with the URL can view and add notes.
- **Private** (`is_public=False`): Only users with the admin token OR users explicitly invited can participate.

### 3.2 The Admin Token ("Master Link")

Every board has a `secret_admin_token` (UUID) generated on creation. This token grants **Board Owner** privileges:

- **Creation**: When a board is created, the backend returns both the board `id` and the `secret_admin_token`.
- **Frontend Storage**: The token is stored in LocalStorage under `board_admin_tokens` (keyed by board ID).
- **Transmission**: Sent via `X-Admin-Token` header on every request to that board.

### 3.3 Permission Hierarchy (`IsOwnerOrAdminToken`)

The permission class enforces a strict hierarchy:

1.  **Safe Methods (GET)**: Always allowed (public boards are readable).
2.  **Author Rights (Notes Only)**:
    - If the requester's Ghost ID matches `note.creator_ghost`, they have full control (edit, delete, move).
    - This check happens _before_ admin checks, ensuring authors always own their content.
3.  **Board Admin Rights**:
    - **Token Match**: If `X-Admin-Token` matches `board.secret_admin_token`.
    - **Claimed Ownership**: If the requester is authenticated and their `User` matches `board.creator_ghost.user`.
4.  **Admin Restrictions on Notes**:
    - Admins can **only** update `position_x` and `position_y` on notes they don't own.
    - They **cannot** edit content, change colors, or delete other users' notes.
    - This prevents board admins from impersonating contributors or censoring feedback.

### 3.4 Private Board Invitations

- **Model**: `BoardInvite` stores email-based invitations.
- **Flow**:
  1.  Admin sends an invite (email is stored, no notification sent in MVP).
  2.  Invited user signs up/logs in with that email.
  3.  Backend checks if their email exists in `BoardInvite` for that board.
  4.  If yes, they gain read/write access to the private board.

---

## 4. Server Architecture (`orbit-server`)

### 4.1 The "Signal-Driven" Event Loop

Orbit does **not** use WebSockets for writing data. Clients do not send JSON payloads to the socket to move notes.

**The Flow:**

1.  **Frontend Action**: User drags a note. Client sends `PATCH /api/notes/{id}/` with new coordinates.
2.  **API Layer**: Django Rest Framework validates the request and saves the `Note` model to PostgreSQL.
3.  **Signal Layer (`signals.py`)**:
    - A `post_save` signal triggers for the `Note`.
    - The signal serializes the updated note.
    - It pushes a message to the Redis Channel Group: `board_{board_uuid}`.
4.  **Broadcast Layer (`consumers.py`)**:
    - The `BoardConsumer` listening to that group receives the message.
    - It forwards the JSON payload to all connected WebSockets.
5.  **Client Update**: React Query receives the socket event and updates its cache.

**Why this approach?**

- **Data Integrity**: All writes go through DRF Serializers, ensuring validation rules (permissions, types) are strictly enforced in one place.
- **Simplicity**: The WebSocket consumer is "dumb"—it only broadcasts. It doesn't need to handle business logic.

### 4.2 The "Gravity" Logic

Orbit features a unique physics-based interaction model hardcoded into the backend:

- **Trigger**: When an `Upvote` is created (`signals.py`).
- **Action**: The system proactively pulls the associated `Note` 5% closer to the canvas origin `(0,0)`.
- **Result**: Popular ideas naturally cluster in the center of the board, while unpopular ones drift at the edges.

---

## 5. Frontend Architecture (`orbit-client`)

### 5.1 Canvas Rendering (`BoardCanvas.tsx`)

- **Library**: Framer Motion.
- **Concept**: An "Infinite" canvas where $(0,0)$ is the center of the screen.
- **Movement**: Panning updates a `MotionValue` translation. Note coordinates are relative to this origin.

### 5.2 Optimistic Updates

To enable a "tactile" feel despite the REST-write loop:

1.  **User Move**: The note snaps to the new position _instantly_ via React Query's `onMutate`.
2.  **Network Request**: The `PATCH` request fires in the background.
3.  **Reconciliation**:
    - If the request fails, the note snaps back.
    - If a WebSocket event arrives for the _same_ move (echo), it is ignored or merged seamlessly.

---

## 6. Key Files & Responsibilities

| File                      | Purpose                                                                                              |
| ------------------------- | ---------------------------------------------------------------------------------------------------- |
| `identity/middleware.py`  | Intercepts `X-Ghost-ID`, creates/retrieves `AnonymousProfile`, injects into `request.ghost`.         |
| `identity/permissions.py` | Enforces Author > Admin hierarchy. Validates admin tokens. Restricts admin actions on others' notes. |
| `workspace/models.py`     | Defines `Board.secret_admin_token`, `Board.is_public`, and the note ownership graph.                 |
| `workspace/consumers.py`  | "Dumb" pipes. Connects clients to Redis groups. Broadcasts messages.                                 |
| `workspace/signals.py`    | The "Brain". Listens for DB changes, applies Gravity physics, triggers broadcasts.                   |
| `useGhostIdentity.ts`     | Client-side Ghost ID lifecycle manager. Generates, stores, and transmits IDs.                        |
| `useBoardSocket.ts`       | Frontend listener. Injects socket payloads directly into the React Query cache.                      |
