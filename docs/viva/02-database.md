# 2. Database Explanation

## Database Engine

- **Engine**: SQLite with WAL (Write-Ahead Logging) journal mode
- **File**: `data/banking.db`
- **Connection**: SQLAlchemy 2.x with `pool_pre_ping=True`
- **Pragmas set on connect** (`src/database.py`):
  - `PRAGMA journal_mode=WAL` — concurrent reads during writes
  - `PRAGMA foreign_keys=ON` — enforce referential integrity
- **Fallback**: If `DATABASE_URL` environment variable is set, uses PostgreSQL (production path). Otherwise defaults to SQLite.

## ORM Configuration

- Declarative base: `src/database.py:Base(DeclarativeBase)`
- Session factory: `SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)`
- Context manager: `get_db()` yields a session, commits on success, rolls back on exception
- All amounts use `Numeric(15, 2)` for exact decimal arithmetic

## Tables (7 total)

### 1. `users`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `username` | String(80) | UNIQUE, NOT NULL, indexed |
| `email` | String(254) | UNIQUE, NOT NULL, indexed |
| `password_hash` | String(128) | NOT NULL (bcrypt) |
| `is_active` | Boolean | NOT NULL, default True |
| `created_at` | DateTime | server_default=now() |

**Relationships**: `accounts` → FinancialAccount (cascade delete), `imports` → ImportRecord (cascade delete)

### 2. `financial_accounts`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `user_id` | Integer | FK → users.id (CASCADE), indexed |
| `name` | String(120) | NOT NULL |
| `account_type` | String(40) | NOT NULL, default "checking" |
| `currency` | String(3) | NOT NULL, default "INR" |
| `created_at` | DateTime | server_default=now() |

**Key design**: Currency is set per account (not per user or globally). This enables multi-currency support — e.g., GBP for `moneydata_demo`, INR for other users.

**Relationships**: `user` → User, `transactions` → Transaction (cascade delete)

### 3. `transactions`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `external_id` | String(64) | NOT NULL, default=uuid4().hex |
| `account_id` | Integer | FK → financial_accounts.id (CASCADE) |
| `import_id` | Integer | FK → import_records.id (SET NULL), nullable |
| `date` | Date | NOT NULL |
| `description` | Text | NOT NULL, default "Transaction" |
| `merchant` | String(200) | NOT NULL |
| `category` | String(80) | NOT NULL |
| `txn_type` | String(10) | NOT NULL ("Debit" or "Credit") |
| `amount` | Numeric(15,2) | NOT NULL |
| `currency` | String(3) | NOT NULL, default "INR" |
| `original_description` | Text | nullable |
| `original_category` | String(80) | nullable |
| `original_txn_code` | String(20) | nullable |
| `balance` | Numeric(15,2) | nullable |
| `location_city` | String(100) | nullable |
| `location_country` | String(100) | nullable |
| `created_at` | DateTime | server_default=now() |

**Indexes**: `(account_id, date)` composite, `(external_id)` unique lookup

**Original data columns**: `original_description`, `original_category`, `original_txn_code`, `balance`, `location_city`, `location_country` preserve raw import data before normalization.

### 4. `import_records`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `user_id` | Integer | FK → users.id (CASCADE), indexed |
| `filename` | String(255) | NOT NULL |
| `file_type` | String(10) | NOT NULL ("csv" or "xlsx") |
| `rows_total` | Integer | NOT NULL, default 0 |
| `rows_imported` | Integer | NOT NULL, default 0 |
| `rows_skipped` | Integer | NOT NULL, default 0 |
| `rows_duplicate` | Integer | NOT NULL, default 0 |
| `status` | String(20) | NOT NULL, default "pending" |
| `error_message` | Text | nullable |
| `created_at` | DateTime | server_default=now() |

### 5. `subscriptions`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `user_id` | Integer | FK → users.id (CASCADE), indexed |
| `plan` | String(20) | NOT NULL, default "free" |
| `status` | String(20) | NOT NULL, default "active" |
| `payment_id` | String(255) | nullable |
| `payment_provider` | String(50) | nullable |
| `started_at` | DateTime | nullable |
| `expires_at` | DateTime | nullable |
| `created_at` | DateTime | server_default=now() |

**Plans**: "free" (Standard Mode only) or "pro" (AI Mode enabled).
**Providers**: "razorpay" (real payment — unconfigured), "demo" (activation key or DEMO_USERNAMES list).

### 6. `conversations`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `user_id` | Integer | FK → users.id (CASCADE), indexed |
| `title` | String(200) | NOT NULL, default "New conversation" |
| `created_at` | DateTime | server_default=now() |
| `updated_at` | DateTime | server_default=now(), onupdate=now() |

### 7. `conversation_messages`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `conversation_id` | Integer | FK → conversations.id (CASCADE), indexed |
| `role` | String(20) | NOT NULL ("user" or "assistant") |
| `content` | Text | NOT NULL |
| `intent` | String(40) | nullable |
| `date_range` | String(40) | nullable |
| `category` | String(80) | nullable |
| `created_at` | DateTime | server_default=now() |

## Entity Relationship Diagram

```
┌──────────┐       ┌───────────────────┐       ┌──────────────┐
│  users   │──1:N──│ financial_accounts │──1:N──│ transactions │
│          │       │                   │       │              │
│ id (PK)  │       │ id (PK)           │       │ id (PK)      │
│ username │       │ user_id (FK)      │       │ account_id   │
│ email    │       │ name              │       │ import_id    │
│ pass_hash│       │ account_type      │       │ date         │
│ is_active│       │ currency          │       │ amount       │
└──────┬───┘       └───────────────────┘       │ txn_type     │
       │                                       │ merchant     │
       │                                       │ category     │
       │       ┌────────────────┐              └──────────────┘
       ├──1:N──│ import_records │──1:N──────────────────┘
       │       │                │        (import_id FK)
       │       │ id (PK)       │
       │       │ user_id (FK)  │
       │       │ filename      │
       │       │ status        │
       │       └────────────────┘
       │
       ├──1:N──┌────────────────┐
       │       │ subscriptions  │
       │       │ user_id (FK)   │
       │       │ plan, status   │
       │       └────────────────┘
       │
       └──1:N──┌────────────────┐       ┌──────────────────────┐
               │ conversations  │──1:N──│ conversation_messages │
               │ user_id (FK)   │       │ conversation_id (FK)  │
               │ title          │       │ role, content         │
               └────────────────┘       │ intent, date_range   │
                                        └──────────────────────┘
```

## User Data Isolation

Transactions are never queried directly by `user_id`. The isolation path is:

```
User → FinancialAccount (user_id) → Transaction (account_id)
```

In `DBTransactionRepository.load()`:
```python
stmt = (
    select(Transaction)
    .join(FinancialAccount)
    .where(FinancialAccount.user_id == self.user_id)
)
```

This ensures User A can never see User B's transactions, even if they share the same SQLite file.

## Multi-Currency Support

- `FinancialAccount.currency` stores the ISO 4217 code ("INR", "GBP", "USD", "EUR")
- Default: "INR" (set in the model)
- The `moneydata_demo` account uses "GBP" (set during import)
- Currency flows through the pipeline: `Orchestrator._resolve_currency()` → specialist agents → `format_inr()` → UI display
- `format_inr()` applies Indian digit grouping (1,25,000) for INR, Western grouping (125,000) for others

## Alembic Migrations

Three migrations exist in `alembic/versions/`:

| # | Revision | Description |
|---|----------|-------------|
| 1 | `d1b0c82c90a1` | Initial schema: users, accounts, transactions, import_records, conversations, messages |
| 2 | `a2f3e7b9c401` | Add subscriptions table |
| 3 | `f46c3ae40d7d` | Add original data preservation columns (original_category, original_txn_code, balance, location_city, location_country) |
