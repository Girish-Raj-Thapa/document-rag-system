# Accounts Module — Technical Specification

> **Module Path**: `app/modules/accounts/`  
> **API Prefix**: `/api/v1/accounts`  
> **Responsibilities**: User identity, registration, authentication, session management

---

## Table of Contents

1. [Module Overview](#1-module-overview)
2. [Data Model](#2-data-model)
3. [Authentication Architecture](#3-authentication-architecture)
4. [Rate Limiting](#4-rate-limiting)
5. [API Reference](#5-api-reference)
6. [Cross-Module Orchestration](#6-cross-module-orchestration)
7. [Error Catalogue](#7-error-catalogue)

---

## 1. Module Overview

The accounts module is the identity provider for the entire system. It manages user registration, credential verification, JWT token issuance and rotation, and session lifecycle.

### Module Structure

```
app/modules/accounts/
├── models.py          # User SQLAlchemy model
├── schemas.py         # Pydantic request/response schemas
├── repository.py      # UserRepository (database queries)
├── service.py         # AccountService (business logic)
├── router.py          # HTTP endpoint definitions
└── dependencies.py    # get_current_user auth dependency
```

### Internal Data Flow

```mermaid
flowchart LR
    subgraph Router
        EP[HTTP Endpoint]
    end
    subgraph Service
        AS[AccountService]
    end
    subgraph Repository
        UR[UserRepository]
    end
    
    EP -->|"Pydantic schema"| AS
    AS -->|"raw params"| UR
    UR -->|"User model"| AS
    AS -->|"User model"| EP
    EP -->|"ApiResponse[UserRead]"| Client[Client]
```

---

## 2. Data Model

### 2.1 Entity-Relationship Diagram

```mermaid
erDiagram
    users {
        uuid id PK "default: uuid4"
        varchar email UK "NOT NULL, unique"
        varchar full_name "NOT NULL"
        varchar password "NOT NULL (bcrypt hash)"
        boolean is_active "default: true"
        uuid current_refresh_jti "NULLABLE"
        timestamptz created_at "server_default: NOW()"
        timestamptz updated_at "onupdate: NOW()"
    }
```

### 2.2 Column Specification

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | PK, default `uuid4` | Globally unique user identifier |
| `email` | `VARCHAR` | UNIQUE, NOT NULL | Normalized to lowercase on registration |
| `full_name` | `VARCHAR` | NOT NULL | Display name |
| `password` | `VARCHAR` | NOT NULL | bcrypt hash (never stored in plaintext) |
| `is_active` | `BOOLEAN` | default `true` | Soft-delete / account suspension flag |
| `current_refresh_jti` | `UUID` | NULLABLE | JTI of the currently valid refresh token. Used for rotation detection |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | Set by PostgreSQL `NOW()` on insert |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | Auto-updated by PostgreSQL on every change |

### 2.3 Relationships

| Relationship | Type | Target | Cascade |
|-------------|------|--------|---------|
| `workspace_memberships` | One-to-Many | `WorkspaceMember` | `all, delete-orphan` |

When a User is deleted, all their workspace memberships are automatically removed.

---

## 3. Authentication Architecture

### 3.1 Dual-Token JWT Strategy

The system uses two separate JWT tokens to balance security and usability:

```mermaid
graph TD
    subgraph "Access Token"
        AT_Life["Lifespan: 30 minutes"]
        AT_Secret["Signed with: SECRET_KEY"]
        AT_Store["Stored in: HttpOnly Cookie"]
        AT_Use["Used for: Every authenticated request"]
    end
    
    subgraph "Refresh Token"
        RT_Life["Lifespan: 7 days"]
        RT_Secret["Signed with: JWT_REFRESH_SECRET_KEY"]
        RT_Store["Stored in: HttpOnly Cookie"]
        RT_Use["Used for: /refresh endpoint only"]
    end
    
    style AT_Secret fill:#e8f5e9,stroke:#2e7d32
    style RT_Secret fill:#fce4ec,stroke:#c62828
```

**Why separate secrets?** If an attacker compromises the access token secret (e.g., leaked in a log), they can forge access tokens that expire in 30 minutes. But they CANNOT forge refresh tokens (which use a completely different secret), limiting the blast radius.

### 3.2 Token Payload Structure

Both tokens share the same Pydantic schema (`TokenPayload`):

| Claim | Type | Description |
|-------|------|-------------|
| `sub` | `uuid.UUID` | User ID (subject) |
| `exp` | `int` | Expiration timestamp (Unix epoch) |
| `jti` | `uuid.UUID` | Unique token identifier |
| `type` | `"access" \| "refresh"` | Discriminator to prevent cross-use |
| `iat` | `datetime` | Issued-at timestamp |

### 3.3 Complete Authentication Lifecycle

```mermaid
sequenceDiagram
    actor User
    participant Client as Browser
    participant API as FastAPI
    participant Redis
    participant DB as PostgreSQL
    
    Note over User,DB: === REGISTRATION ===
    User->>Client: Fill out registration form
    Client->>API: POST /register {email, full_name, password}
    API->>Redis: RateLimiter check (5 req/min)
    API->>API: Validate RegisterRequest schema
    API->>API: hash_password(payload.password)
    API->>DB: INSERT INTO users (email, name, hash)
    DB-->>API: User(id=abc)
    API->>DB: INSERT INTO workspaces (auto-provision)
    API->>DB: INSERT INTO workspace_members (role=owner)
    API->>DB: COMMIT (atomic)
    API->>API: Generate access_jti, refresh_jti
    API->>DB: UPDATE users SET current_refresh_jti = refresh_jti
    API->>Client: 201 + Set-Cookie: access_token, refresh_token
    
    Note over User,DB: === AUTHENTICATED REQUEST ===
    Client->>API: GET /me (Cookie: access_token=eyJ...)
    API->>API: Decode JWT with SECRET_KEY
    API->>API: Check payload.type == "access"
    API->>DB: SELECT * FROM users WHERE id = payload.sub
    DB-->>API: User object
    API->>API: Check user.is_active == true
    API-->>Client: 200 {success: true, data: UserRead}
    
    Note over User,DB: === TOKEN REFRESH ===
    Client->>API: POST /refresh (Cookie: refresh_token=eyJ...)
    API->>Redis: RateLimiter check (5 req/min)
    API->>API: Decode JWT with JWT_REFRESH_SECRET_KEY
    API->>DB: SELECT current_refresh_jti FROM users WHERE id = sub
    
    alt JTI matches (legitimate refresh)
        API->>API: Generate NEW access_jti, refresh_jti
        API->>DB: UPDATE users SET current_refresh_jti = NEW_jti
        API->>DB: COMMIT
        API-->>Client: 200 + Set-Cookie: NEW access_token, NEW refresh_token
    else JTI mismatch (stolen token detected)
        API->>DB: UPDATE users SET current_refresh_jti = NULL
        API->>DB: COMMIT (revoke all sessions)
        API-->>Client: 401 "Refresh token reuse detected"
    end
    
    Note over User,DB: === LOGOUT ===
    Client->>API: POST /logout
    API->>Client: Clear access_token cookie (max-age=0)
    API->>Client: Clear refresh_token cookie (max-age=0)
```

### 3.4 Token Rotation & Reuse Detection (State Machine)

```mermaid
stateDiagram-v2
    [*] --> Active : Token issued at login/register
    
    Active --> Rotated : User calls /refresh
    Note right of Rotated : Old token invalidated,<br>new token issued.<br>DB stores new JTI.
    
    Rotated --> Active : New token is now active
    
    Active --> ReuseDetected : Old token used again
    Note right of ReuseDetected : JTI mismatch detected.<br>Attacker likely stole old token.
    
    ReuseDetected --> Revoked : current_refresh_jti = NULL
    Note right of Revoked : ALL sessions destroyed.<br>User must log in again.
    
    Active --> Expired : Time > 7 days
    Expired --> [*] : User must log in again
    
    Revoked --> [*]
```

### 3.5 HttpOnly Cookie Security

| Cookie Attribute | Value | Purpose |
|-----------------|-------|---------|
| `httponly` | `True` | JavaScript cannot read the cookie (XSS protection) |
| `secure` | `False` (dev) / `True` (prod) | Only sent over HTTPS in production |
| `samesite` | `lax` | Prevents CSRF on cross-origin requests |
| `max-age` | 1800s (access) / 604800s (refresh) | Browser auto-deletes expired cookies |

### 3.6 Password Hashing

Passwords are hashed using **bcrypt** via the `passlib` library:

```mermaid
flowchart LR
    Plain["plaintext password"] --> Hash["bcrypt.hash()"]
    Hash --> Stored["$2b$12$LJ3m4..."]
    
    Login["login attempt"] --> Verify["bcrypt.verify()"]
    Stored --> Verify
    Verify -->|Match| Allow["Allow Login"]
    Verify -->|No Match| Deny["Raise AuthenticationError"]
```

bcrypt is intentionally slow (configurable work factor, currently `$2b$12$`) to make offline brute-force attacks computationally prohibitive.

---

## 4. Rate Limiting

### 4.1 Fixed-Window Counter Algorithm

The rate limiter uses Redis to track request counts per IP per endpoint within a fixed time window.

```mermaid
sequenceDiagram
    participant Client
    participant RL as RateLimiter
    participant Redis
    
    Client->>RL: Request to /login
    RL->>RL: Build key = "rate_limit:/api/v1/accounts/login:192.168.1.1"
    RL->>Redis: INCR key
    Redis-->>RL: current_count = 3
    
    alt count == 1 (first request in window)
        RL->>Redis: EXPIRE key 60
    end
    
    alt count <= max_requests
        RL-->>Client: Allow (proceed to handler)
    else count > max_requests
        RL-->>Client: HTTP 429 "Rate limit exceeded"
    end
```

### 4.2 Rate Limits Per Endpoint

| Endpoint | Max Requests | Window | Rationale |
|----------|-------------|--------|-----------|
| `POST /register` | 5 | 60s | Prevent mass account creation |
| `POST /login` | 10 | 60s | Prevent credential stuffing / brute force |
| `POST /refresh` | 5 | 60s | Prevent refresh token abuse |

---

## 5. API Reference

### `POST /api/v1/accounts/register`

Creates a new user account and auto-provisions a default personal workspace.

**Request**

| Field | Type | Constraints | Required |
|-------|------|-------------|----------|
| `email` | `EmailStr` | Valid email format | Yes |
| `full_name` | `str` | min: 2, max: 100 chars | Yes |
| `password` | `str` | min: 8 chars | Yes |

```json
{
  "email": "john@example.com",
  "full_name": "John Doe",
  "password": "securepassword123"
}
```

**Response** — `201 Created`

```json
{
  "success": true,
  "message": "Registration successful",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "john@example.com",
    "full_name": "John Doe",
    "is_active": true,
    "created_at": "2026-07-23T15:00:00+00:00"
  }
}
```

**Side Effects:**
- Sets `access_token` and `refresh_token` HttpOnly cookies
- Creates a default workspace named `"John Doe's Workspace"`
- Assigns the user as `owner` of that workspace

**Error Responses:**

| Status | Condition | Message |
|--------|-----------|---------|
| 409 | Email already registered | `"A user with this email already exists."` |
| 422 | Invalid payload (e.g., password too short) | `"Request validation failed"` |
| 429 | Rate limit exceeded | `"Rate limit exceeded. Try again in 60 seconds."` |

---

### `POST /api/v1/accounts/login`

Authenticates a user with email and password, issues new tokens.

**Request**

| Field | Type | Constraints | Required |
|-------|------|-------------|----------|
| `email` | `EmailStr` | Valid email format | Yes |
| `password` | `str` | Any length | Yes |

```json
{
  "email": "john@example.com",
  "password": "securepassword123"
}
```

**Response** — `200 OK`

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "john@example.com",
    "full_name": "John Doe",
    "is_active": true,
    "created_at": "2026-07-23T15:00:00+00:00"
  }
}
```

**Side Effects:**
- Sets `access_token` and `refresh_token` HttpOnly cookies
- Updates `current_refresh_jti` in the database

**Error Responses:**

| Status | Condition | Message |
|--------|-----------|---------|
| 401 | Wrong email or password | `"Invalid email or password."` |
| 401 | Account disabled | `"User account is disabled."` |
| 429 | Rate limit exceeded | `"Rate limit exceeded. Try again in 60 seconds."` |

---

### `POST /api/v1/accounts/refresh`

Issues new access and refresh tokens using the refresh token cookie. Implements token rotation.

**Request**

No JSON body. Reads `refresh_token` from HttpOnly cookie.

**Response** — `200 OK`

```json
{
  "success": true,
  "message": "Token refreshed successfully",
  "data": null
}
```

**Side Effects:**
- Invalidates the old refresh token
- Sets new `access_token` and `refresh_token` HttpOnly cookies
- Updates `current_refresh_jti` in the database

**Error Responses:**

| Status | Condition | Message |
|--------|-----------|---------|
| 401 | No refresh cookie present | `"Missing refresh token cookie."` |
| 401 | Token expired or malformed | `"Invalid or expired refresh token."` |
| 401 | Token reuse detected | `"Refresh token reuse detected. Please log in again."` |

---

### `POST /api/v1/accounts/logout`

Clears authentication cookies. No server-side session invalidation.

**Request**

No JSON body required. No authentication required.

**Response** — `200 OK`

```json
{
  "success": true,
  "message": "Logged out successfully",
  "data": null
}
```

**Side Effects:**
- Sets `access_token` cookie to empty with `max-age=0`
- Sets `refresh_token` cookie to empty with `max-age=0`

---

### `GET /api/v1/accounts/me`

Returns the profile of the currently authenticated user.

**Request**

No JSON body. Requires valid `access_token` cookie.

**Response** — `200 OK`

```json
{
  "success": true,
  "message": "User profile retrieved",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "john@example.com",
    "full_name": "John Doe",
    "is_active": true,
    "created_at": "2026-07-23T15:00:00+00:00"
  }
}
```

**Error Responses:**

| Status | Condition | Message |
|--------|-----------|---------|
| 401 | No access cookie | `"Not authenticated."` |
| 401 | Token expired or invalid | `"Invalid or expired access token."` |
| 401 | User deleted after token was issued | `"User no longer exists."` |
| 401 | Account suspended | `"User account is disabled."` |

---

## 6. Cross-Module Orchestration

The `AccountService.register_user` method demonstrates how modules communicate while maintaining transactional integrity:

```mermaid
sequenceDiagram
    participant AS as AccountService
    participant UR as UserRepository
    participant WS as WorkspaceService
    participant WR as WorkspaceRepository
    participant DB as PostgreSQL
    
    AS->>UR: create(email, name, hash)
    UR->>DB: INSERT users ... flush()
    Note over DB: user.id assigned,<br>transaction still OPEN
    
    AS->>WS: create_workspace(user, payload)
    WS->>WR: create_workspace(name)
    WR->>DB: INSERT workspaces ... flush()
    
    WS->>WR: add_member(ws_id, user_id, OWNER)
    WR->>DB: INSERT workspace_members ... flush()
    
    WS->>DB: COMMIT
    Note over DB: All 3 INSERTs committed<br>in a single transaction
    
    AS-->>AS: return user
```

If any step fails (e.g., a duplicate email on the user insert), the entire transaction rolls back. No orphaned workspaces or workspace members are created.

---

## 7. Error Catalogue

| Error Class | HTTP Status | When Raised | Example Message |
|------------|-------------|-------------|-----------------|
| `AuthenticationError` | 401 | Invalid credentials, expired tokens, disabled accounts | `"Invalid email or password."` |
| `ConflictError` | 409 | Duplicate email on registration | `"A user with this email already exists."` |
| `ValidationError` | 422 | Pydantic schema validation failure | `"Request validation failed"` |
