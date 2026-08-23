"""
Shared API plumbing.

WHAT BELONGS IN `app/api/`
-------------------------
Cross-cutting API concerns only — things that are not owned by any single
module:

  - router registration (this file)
  - shared exception handlers
  - shared response helpers and common middleware

WHAT DOES NOT BELONG HERE
-------------------------
Endpoint definitions. Routes live with the module that owns them, so that
everything for one module sits in one folder:

    app/users/routes.py        -> /users/*        (Module 1)
    app/auth/                  -> token verification, roles, authorization
    app/content/routes.py      -> /content/*      (Module 2)
    app/engagement/routes.py   -> /engagement/*   (Module 3)

The reason is practical: with routes split out into a shared `api/` folder,
changing one module means editing two places, and two people working on
different modules keep colliding in the same file. Keeping routes beside their
module also means "show me Module 3" is one folder rather than four.
"""

from fastapi import APIRouter

from app.users.routes import router as users_router

api_router = APIRouter()

# Module 1 — User Profile and Access Management
api_router.include_router(users_router)

# Module 2 (content) and Module 3 (engagement) routers are registered here as
# they are migrated, under issues #10 and #11.
