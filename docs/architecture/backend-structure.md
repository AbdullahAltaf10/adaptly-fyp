# Backend structure — where things go

Written so nobody has to guess where a file belongs, and so future issues can be
written against what actually exists.

## The rule

**Code lives with the module that owns it. `api/` and `core/` are for things no
single module owns.**

```
backend/app/
├── api/          shared API plumbing — NOT endpoints
├── core/         shared infrastructure — NOT business logic
├── auth/         Module 1: identity, roles, authorization
├── users/        Module 1: profiles
├── content/      Module 2: ingestion and processing
└── engagement/   Module 3: webcam pipeline and detection
```

## What goes in `api/`

Cross-cutting API concerns only:

- **router registration** (`api/router.py`) — collects each module's router into one
- shared exception handlers
- shared response helpers and common middleware

**Endpoints do NOT go here.** Route files live with their module:

| Route prefix | File | Module |
|---|---|---|
| `/users/*` | `app/users/routes.py` | 1 |
| `/content/*` | `app/content/routes.py` | 2 |
| `/engagement/*` | `app/engagement/routes.py` | 3 |

The reason is practical. If routes were collected in `api/`, changing one module
would mean editing two folders, and two people working on different modules
would keep colliding in the same file. Keeping routes beside their module also
means "show me Module 3" is one folder rather than four.

`app/main.py` stays thin: create the app, add middleware, include `api_router`,
expose `/health`.

## What goes in `core/`

Shared infrastructure with no business logic — currently the database
connection. Anything specific to one module belongs in that module's folder.

## Module 1 — as migrated

| File | Responsibility |
|---|---|
| `auth/firebase.py` | Verifies the Firebase ID token. Lazy init. |
| `auth/dependencies.py` | `get_current_user` — proves *who* is calling |
| `auth/roles.py` | Valid modes and roles, and the self-assignment policy |
| `auth/authorization.py` | `require_hr_admin` etc — proves *what they may do* |
| `users/models.py` | The stored profile shape |
| `users/contracts.py` | Converts stored shape → shared contract |
| `users/routes.py` | The `/users/*` endpoints |

## Internal names vs contract names

The team agreed that `shared/contracts/*.schema.json` define **what modules send
each other**, not how each module stores data internally.

So this module stores `uid` and converts to `user_id` at the boundary, in
`users/contracts.py`. That is the only place the contract shape appears.

**If you add a field:** change `users/models.py`, then map it in
`users/contracts.py`. Do not rename internal fields to match the contract — that
was the point of the agreement.

## Two behaviours worth knowing

**Nothing connects at import time.** The database and Firebase both initialise
lazily. The prototype connected on import, which meant importing the app
required live credentials and made the tests depend on a real database. Missing
configuration now produces a clear message naming the variable and pointing at
`backend/.env.example`, rather than a `TypeError` from inside pymongo or a bare
`FileNotFoundError`.

**Roles cannot be self-assigned.** Registration only produces `learner` or
`corporate/employee`. `hr_admin` is granted — either by listing an address in
`HR_ADMIN_EMAILS`, or by an existing admin calling
`PUT /users/{uid}/corporate-role`. Authorization dependencies read the role from
the database, never from the request.
