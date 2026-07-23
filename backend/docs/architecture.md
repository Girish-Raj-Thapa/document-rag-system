# System Architecture — Technical Specification

> **Version**: 0.1.0  
> **Last Updated**: 2026-07-23  
> **System**: Document RAG System — Backend API

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Directory Structure](#3-directory-structure)
4. [Architectural Patterns & Design Decisions](#4-architectural-patterns--design-decisions)
5. [Application Lifecycle](#5-application-lifecycle)
6. [The Request Pipeline](#6-the-request-pipeline)
7. [Dependency Injection System](#7-dependency-injection-system)
8. [Database Architecture](#8-database-architecture)
9. [Global Exception Handling](#9-global-exception-handling)
10. [Configuration Management](#10-configuration-management)
11. [API Versioning & Routing](#11-api-versioning--routing)

---

## 1. System Overview

The backend is a **Modular Monolith** — a single deployable unit whose internals are cleanly separated into domain modules. Each module owns its models, schemas, service logic, and data access layer independently. This gives us the development speed of a monolith with the clean boundaries that make future extraction into microservices trivial.

```mermaid
graph LR
    subgraph "External"
        Client[Web Client<br>Next.js / React]
    end
    
    subgraph "Backend Container"
        direction TB
        Uvicorn[Uvicorn ASGI Server]
        FastAPI[FastAPI Application]
        Modules[Domain Modules]
    end
    
    subgraph "Data Stores"
        PG[(PostgreSQL<br>Primary Database)]
        Redis[(Redis<br>Rate Limiting & Cache)]
    end
    
    Client -->|HTTP/HTTPS| Uvicorn
    Uvicorn --> FastAPI
    FastAPI --> Modules
    Modules --> PG
    FastAPI --> Redis
```

---

## 2. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.11 | Async-first, type-hinted |
| **Framework** | FastAPI | 0.115+ | ASGI web framework with automatic OpenAPI |
| **ORM** | SQLAlchemy | 2.0 (Async) | Declarative models with async session support |
| **Database** | PostgreSQL | 16 | Primary relational data store |
| **Cache / Rate Limit** | Redis | 7+ | Fixed-window rate limiting, future task queues |
| **Migrations** | Alembic | 1.14+ | Versioned database schema management |
| **Auth** | python-jose + passlib | — | JWT encoding/decoding + bcrypt password hashing |
| **Validation** | Pydantic | v2 | Request/response schema validation |
| **Config** | pydantic-settings | — | Type-safe env variable loading |
| **Containerization** | Docker + Compose | — | Reproducible dev/prod environments |

---

## 3. Directory Structure

```
backend/
├── app/
│   ├── main.py                        # Entrypoint (thin — delegates to setup.py)
│   ├── core/                          # Cross-cutting concerns
│   │   ├── config.py                  # Settings loaded from .env
│   │   ├── setup.py                   # Application Factory (create_app)
│   │   ├── security.py                # Password hashing, JWT creation/decoding
│   │   ├── schemas.py                 # Shared Pydantic schemas (TokenPayload)
│   │   ├── responses.py               # ApiResponse generic wrapper
│   │   ├── exceptions.py              # Domain exceptions + global handlers
│   │   ├── rate_limit.py              # Redis-backed rate limiter
│   │   └── logging.py                 # Structured logging configuration
│   ├── db/                            # Database infrastructure
│   │   ├── base.py                    # DeclarativeBase with naming conventions
│   │   ├── mixins.py                  # UUIDPrimaryKeyMixin, TimestampMixin
│   │   └── session.py                 # Async engine, session factory, get_db dependency
│   ├── api/
│   │   └── v1/
│   │       └── router.py             # Version prefix aggregator (/api/v1)
│   └── modules/
│       ├── accounts/                  # Identity & Authentication domain
│       │   ├── models.py              # User model
│       │   ├── schemas.py             # RegisterRequest, LoginRequest, UserRead
│       │   ├── repository.py          # UserRepository (DB queries)
│       │   ├── service.py             # AccountService (business logic)
│       │   ├── router.py              # HTTP endpoints
│       │   └── dependencies.py        # get_current_user auth dependency
│       └── workspaces/                # Multi-Tenancy domain
│           ├── models.py              # Workspace, WorkspaceMember, WorkspaceRole
│           ├── schemas.py             # WorkspaceCreate, InviteMemberRequest, etc.
│           ├── repository.py          # WorkspaceRepository
│           ├── service.py             # WorkspaceService
│           ├── router.py              # HTTP endpoints
│           └── dependencies.py        # RBAC dependency (require_workspace_roles)
├── migrations/                        # Alembic migration versions
├── tests/                             # Mirrors app/modules/ structure
├── docker/                            # Dockerfiles
└── pyproject.toml                     # Dependencies, pytest config
```

---

## 4. Architectural Patterns & Design Decisions

### 4.1 Pattern: Layered Architecture (Router → Service → Repository)

Every domain module is internally structured into three strictly separated layers. Each layer has a single responsibility and communicates only with its immediate neighbor.

```mermaid
graph TD
    subgraph "Router Layer"
        R["router.py<br><i>HTTP parsing, validation, response formatting</i>"]
    end
    
    subgraph "Service Layer"
        S["service.py<br><i>Business rules, orchestration, domain exceptions</i>"]
    end
    
    subgraph "Repository Layer"
        Repo["repository.py<br><i>SQLAlchemy queries, data access</i>"]
    end
    
    subgraph "Database"
        DB[(PostgreSQL)]
    end
    
    R -->|"Pydantic schema"| S
    S -->|"Model objects"| Repo
    Repo -->|"SQL via ORM"| DB
    
    style R fill:#e8eaf6,stroke:#3f51b5
    style S fill:#e8f5e9,stroke:#43a047
    style Repo fill:#fff3e0,stroke:#ef6c00
```

**Why this pattern?**
- The Router never touches SQLAlchemy. If we swap FastAPI for another framework, only routers change.
- The Service never knows about HTTP status codes. It raises semantic exceptions like `ConflictError`, not `HTTPException(409)`.
- The Repository never validates business rules. It simply executes queries and returns model instances.

### 4.2 Pattern: Application Factory

The `create_app()` function in `app/core/setup.py` constructs the entire FastAPI application. This pattern (borrowed from Flask) keeps `main.py` to a single line and makes the app fully configurable for testing.

```mermaid
flowchart LR
    main["main.py"] -->|"calls"| factory["create_app()"]
    factory --> logging["Setup Logging"]
    factory --> cors["Add CORS Middleware"]
    factory --> exc["Register Exception Handlers"]
    factory --> routes["Include API Routers"]
    factory --> health["Add /health Endpoint"]
    factory --> lifespan["Attach Lifespan<br>(Redis connect/disconnect)"]
    factory -->|"returns"| app["FastAPI Instance"]
```

### 4.3 Pattern: Generic Response Envelope

Every API response is wrapped in `ApiResponse[T]`, a generic Pydantic model:

```python
class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str | None = None
    data: T | None = None
```

This guarantees the frontend always receives a predictable JSON shape:
```json
// Success
{ "success": true, "message": "Login successful", "data": { ... } }

// Error
{ "success": false, "message": "Invalid email or password" }
```

### 4.4 Pattern: Mixin-Based Model Composition

Instead of repeating `id`, `created_at`, and `updated_at` columns across every model, we use Python's multiple inheritance to compose models from reusable mixins.

```mermaid
classDiagram
    class UUIDPrimaryKeyMixin {
        +UUID id (PK, default=uuid4)
    }
    class TimestampMixin {
        +DateTime created_at (server_default=NOW)
        +DateTime updated_at (onupdate=NOW)
    }
    class Base {
        +MetaData metadata (naming conventions)
    }
    class User {
        +String email (unique)
        +String full_name
        +String password
        +Boolean is_active
        +UUID current_refresh_jti
    }
    class Workspace {
        +String name
    }
    class WorkspaceMember {
        +UUID workspace_id (FK)
        +UUID user_id (FK)
        +Enum role
    }
    
    UUIDPrimaryKeyMixin <|-- User
    TimestampMixin <|-- User
    Base <|-- User
    UUIDPrimaryKeyMixin <|-- Workspace
    TimestampMixin <|-- Workspace
    Base <|-- Workspace
    UUIDPrimaryKeyMixin <|-- WorkspaceMember
    TimestampMixin <|-- WorkspaceMember
    Base <|-- WorkspaceMember
```

**Why server-side timestamps?** The `TimestampMixin` uses `server_default=func.now()` (PostgreSQL's `NOW()`) rather than Python's `datetime.utcnow()`. This ensures all timestamps come from the database clock, not the application server clock, which matters when running multiple app replicas.

### 4.5 Pattern: Flush vs Commit (Unit of Work)

A critical architectural decision in the Repository layer:

- **`flush()`** — Sends the SQL to PostgreSQL and assigns IDs, but does NOT finalize the transaction. The data can still be rolled back.
- **`commit()`** — Permanently writes data to disk. Called only by the Service layer after all operations succeed.

```mermaid
sequenceDiagram
    participant Service as AccountService
    participant UserRepo as UserRepository
    participant WsRepo as WorkspaceRepository
    participant DB as PostgreSQL
    
    Service->>UserRepo: create(email, name, pw)
    UserRepo->>DB: INSERT INTO users ... (flush)
    DB-->>UserRepo: user.id = abc-123
    UserRepo-->>Service: User(id=abc-123)
    
    Service->>WsRepo: create_workspace(name)
    WsRepo->>DB: INSERT INTO workspaces ... (flush)
    DB-->>WsRepo: workspace.id = xyz-789
    
    Service->>WsRepo: add_member(workspace_id, user_id)
    WsRepo->>DB: INSERT INTO workspace_members ... (flush)
    
    Service->>DB: COMMIT
    Note over DB: All 3 INSERTs are<br>committed atomically
```

If any step fails (e.g., a duplicate email), the entire transaction rolls back — no orphaned workspaces or members are left behind.

### 4.6 Pattern: Database Naming Conventions

The `Base` class in `app/db/base.py` enforces PostgreSQL naming conventions for all auto-generated constraints:

| Constraint Type | Pattern | Example |
|----------------|---------|---------|
| Primary Key | `pk_%(table_name)s` | `pk_users` |
| Foreign Key | `fk_%(table_name)s_%(column)s_%(referred)s` | `fk_workspace_members_user_id_users` |
| Unique | `uq_%(table_name)s_%(column)s` | `uq_users_email` |
| Index | `ix_%(table_name)s_%(column)s` | `ix_workspace_members_user_id` |

This ensures Alembic migrations produce deterministic, readable constraint names across all environments.

---

## 5. Application Lifecycle

The FastAPI application follows a strict startup/shutdown lifecycle managed by an async context manager.

```mermaid
stateDiagram-v2
    [*] --> Booting
    
    state Booting {
        [*] --> SetupLogging
        SetupLogging --> LoadSettings : Read .env
        LoadSettings --> CreateApp : Application Factory
        CreateApp --> RegisterMiddleware
        RegisterMiddleware --> RegisterExceptionHandlers
        RegisterExceptionHandlers --> IncludeRouters
        IncludeRouters --> [*]
    }
    
    Booting --> Running
    
    state Running {
        [*] --> ConnectRedis : Lifespan startup
        ConnectRedis --> PingRedis : Verify connectivity
        PingRedis --> ServingTraffic
    }
    
    Running --> ShuttingDown
    
    state ShuttingDown {
        [*] --> CloseRedis
        CloseRedis --> [*] : Graceful exit
    }
    
    ShuttingDown --> [*]
```

---

## 6. The Request Pipeline

Every incoming HTTP request traverses a well-defined pipeline before reaching application code and returning a response.

```mermaid
sequenceDiagram
    participant Client
    participant CORS as CORS Middleware
    participant DI as Dependency Injection
    participant Auth as get_current_user
    participant RL as RateLimiter
    participant Router as Router Layer
    participant Service as Service Layer
    participant Repo as Repository Layer
    participant DB as PostgreSQL
    participant EH as Exception Handler
    
    Client->>CORS: HTTP Request
    CORS->>DI: Pass-through (check Origin)
    
    par Authentication
        DI->>Auth: Extract access_token cookie
        Auth->>DB: Fetch User by token.sub
        DB-->>Auth: User object
    and Rate Limiting
        DI->>RL: Check Redis counter
        RL->>RL: Increment counter
    end
    
    DI->>Router: Inject User, DB session
    Router->>Service: Call business method
    Service->>Repo: Execute query
    Repo->>DB: SQL
    DB-->>Repo: Result
    Repo-->>Service: Model instance
    Service-->>Router: Domain object
    Router-->>Client: ApiResponse JSON
    
    Note over EH: If any step raises an exception,<br>the global handler intercepts it<br>and returns a formatted ApiResponse
```

---

## 7. Dependency Injection System

FastAPI's `Depends()` mechanism is used extensively to build a composable dependency graph. Dependencies are resolved per-request and can be nested.

```mermaid
graph TD
    subgraph "Database Dependencies"
        get_db["get_db()<br><i>Yields AsyncSession</i>"]
    end
    
    subgraph "Auth Dependencies"
        get_current["get_current_user()<br><i>Reads cookie, decodes JWT,<br>fetches User from DB</i>"]
        get_db --> get_current
    end
    
    subgraph "Workspace RBAC Dependencies"
        req_member["require_workspace_membership()<br><i>Verifies user belongs to workspace</i>"]
        req_roles["require_workspace_roles(OWNER, ADMIN)<br><i>Verifies user has specific role</i>"]
        
        get_current --> req_member
        get_db --> req_member
        req_member --> req_roles
    end
    
    subgraph "Rate Limiting"
        rate["RateLimiter(max=10, window=60)<br><i>Checks Redis counter</i>"]
    end
    
    subgraph "Router Endpoints"
        login["/login"]
        register["/register"]
        me["/me"]
        create_ws["POST /workspaces"]
        invite["POST /workspaces/{id}/members"]
    end
    
    rate --> login
    rate --> register
    get_current --> me
    get_current --> create_ws
    req_roles --> invite
```

The `require_workspace_roles()` function is a **dependency factory** — a function that returns a dependency. This pattern allows passing configuration (which roles are allowed) while still participating in FastAPI's DI graph:

```python
# Usage: Only OWNER and ADMIN can invite members
member: WorkspaceMember = Depends(
    require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
)
```

---

## 8. Database Architecture

### 8.1 Full Entity-Relationship Diagram

```mermaid
erDiagram
    users {
        uuid id PK "default: uuid4"
        varchar email UK "NOT NULL"
        varchar full_name "NOT NULL"
        varchar password "NOT NULL (bcrypt hash)"
        boolean is_active "default: true"
        uuid current_refresh_jti "NULLABLE"
        timestamptz created_at "server_default: NOW()"
        timestamptz updated_at "onupdate: NOW()"
    }
    
    workspaces {
        uuid id PK "default: uuid4"
        varchar name "NOT NULL"
        timestamptz created_at "server_default: NOW()"
        timestamptz updated_at "onupdate: NOW()"
    }
    
    workspace_members {
        uuid id PK "default: uuid4"
        uuid workspace_id FK "NOT NULL, indexed"
        uuid user_id FK "NOT NULL, indexed"
        workspace_role_enum role "NOT NULL, default: member"
        timestamptz created_at "server_default: NOW()"
        timestamptz updated_at "onupdate: NOW()"
    }
    
    users ||--o{ workspace_members : "has memberships"
    workspaces ||--o{ workspace_members : "contains members"
```

### 8.2 Connection Pool Configuration

The async engine is configured for production-grade connection management:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `pool_size` | 10 | Maximum persistent connections in the pool |
| `max_overflow` | 20 | Extra connections allowed during traffic spikes (total: 30) |
| `pool_recycle` | 3600s | Recreate connections after 1 hour to prevent stale TCP sessions |
| `expire_on_commit` | False | Objects remain usable after `commit()` without re-querying |

### 8.3 Session Lifecycle

```mermaid
flowchart TD
    Request[Incoming HTTP Request] --> DI["get_db() dependency called"]
    DI --> Create["AsyncSessionLocal() creates session"]
    Create --> Yield["Session yielded to handler"]
    Yield --> Handler["Route handler executes queries"]
    Handler --> Finally["finally: session.close()"]
    Finally --> Pool["Connection returned to pool"]
    
    Handler -->|"If exception"| Finally
```

The `get_db()` generator dependency uses `try/finally` to guarantee session cleanup regardless of whether the request succeeds or raises an exception.

---

## 9. Global Exception Handling

### 9.1 Exception Class Hierarchy

```mermaid
classDiagram
    class AppError {
        +str message
        +Any details
    }
    class ValidationError {
        HTTP 422
    }
    class AuthenticationError {
        HTTP 401
    }
    class PermissionDeniedError {
        HTTP 403
    }
    class NotFoundError {
        HTTP 404
    }
    class ConflictError {
        HTTP 409
    }
    
    AppError <|-- ValidationError
    AppError <|-- AuthenticationError
    AppError <|-- PermissionDeniedError
    AppError <|-- NotFoundError
    AppError <|-- ConflictError
```

### 9.2 Handler Resolution Order

Four exception handlers are registered on the FastAPI app, checked in this priority:

1. **`AppError`** — All domain exceptions. Maps exception type to HTTP status code.
2. **`RequestValidationError`** — Pydantic schema validation failures. Returns field-level error details.
3. **`StarletteHTTPException`** — Standard HTTP errors (e.g., 404 for unknown routes).
4. **`Exception`** — Catch-all safety net. Logs the full traceback server-side but returns only `"Internal server error"` to the client to prevent information leakage.

```mermaid
sequenceDiagram
    participant Route
    participant Service
    participant Repository
    participant Handler as Global Exception Handler
    participant Client
    
    Route->>Service: register_user(payload)
    Service->>Repository: create(email, name, pw)
    Repository->>Repository: db.flush() raises IntegrityError
    
    Note over Repository: Catches DB IntegrityError,<br>re-raises as ConflictError
    Repository-->>Service: ConflictError("Email already exists")
    Service-->>Route: Exception bubbles up
    Route-->>Handler: ConflictError intercepted
    
    Handler->>Handler: isinstance check -> 409
    Handler->>Handler: Log warning
    Handler-->>Client: HTTP 409
    
    Note right of Client: {"success": false,<br>"message": "A user with this<br>email already exists."}
```

---

## 10. Configuration Management

### 10.1 Design: pydantic-settings

All configuration is centralized in `app/core/config.py` using `pydantic-settings`. This provides:
- **Type safety**: `ACCESS_TOKEN_EXPIRE_MINUTES: int = 30` — if someone sets it to `"abc"` in `.env`, the app crashes at startup with a clear error.
- **Validation**: `extra="forbid"` causes the app to fail loudly if there is a typo in an env variable name.
- **Defaults**: Every setting has a safe development default, so the app boots without manual configuration.

### 10.2 Configuration Categories

| Category | Variables | Purpose |
|----------|----------|---------|
| **Database** | `DATABASE_URL` | PostgreSQL connection string (sync format for Alembic compatibility) |
| **Redis** | `REDIS_URL` | Rate limiting and future caching |
| **JWT Auth** | `SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Dual-token authentication |
| **Cookies** | `ACCESS_COOKIE_NAME`, `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_SECURE`, `REFRESH_COOKIE_SAMESITE` | HttpOnly cookie behavior |
| **Storage** | `STORAGE_PATH` | File upload directory |
| **Celery** | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Background task processing (future) |
| **AI/ML** | `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `DEFAULT_LLM_PROVIDER`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL` | RAG pipeline configuration (future) |

### 10.3 Factory Pattern for Testability

```python
def get_settings() -> Settings:
    return Settings()
```

Settings are accessed through a factory function, not a global singleton. This allows tests to monkeypatch `get_settings` to inject test-specific configurations (like a separate test database URL).

---

## 11. API Versioning & Routing

### 11.1 Version Prefix Architecture

```mermaid
graph LR
    subgraph "app/api/v1/router.py"
        V1["/api/v1"]
    end
    
    subgraph "app/modules/accounts/router.py"
        Acc["/accounts"]
    end
    
    subgraph "app/modules/workspaces/router.py"
        Ws["/workspaces"]
    end
    
    V1 --> Acc
    V1 --> Ws
    
    Acc --> R1["POST /api/v1/accounts/register"]
    Acc --> R2["POST /api/v1/accounts/login"]
    Acc --> R3["POST /api/v1/accounts/refresh"]
    Acc --> R4["POST /api/v1/accounts/logout"]
    Acc --> R5["GET  /api/v1/accounts/me"]
    
    Ws --> R6["POST   /api/v1/workspaces"]
    Ws --> R7["GET    /api/v1/workspaces"]
    Ws --> R8["GET    /api/v1/workspaces/{id}"]
    Ws --> R9["GET    /api/v1/workspaces/{id}/members"]
    Ws --> R10["POST   /api/v1/workspaces/{id}/members"]
    Ws --> R11["PATCH  /api/v1/workspaces/{id}/members/{mid}"]
    Ws --> R12["DELETE /api/v1/workspaces/{id}/members/{mid}"]
```

The version prefix (`/api/v1`) is applied at the aggregator level in `api/v1/router.py`. Each module defines its own prefix (`/accounts`, `/workspaces`). When API v2 is needed, a new `api/v2/router.py` can be created without touching existing module code.

### 11.2 Health Check

A standalone `/health` endpoint is registered directly on the app (outside of versioned routing) to provide infrastructure-level monitoring:

```json
// GET /health
{
  "status": "ok",        // or "degraded"
  "service": "docrag-api",
  "redis": "connected",
  "database": "connected"
}
```

Docker Compose and load balancers use this endpoint to determine container readiness.
