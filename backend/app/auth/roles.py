"""
Account modes, corporate roles, and the rules governing who may hold them.

Kept in one place because the previous implementation accepted `mode` and `role`
straight from the client with no validation at all. Any authenticated user could
call:

    POST /users/register?mode=corporate&role=hr_admin

and receive HR administrator access. That is privilege escalation, and it is the
defect this module exists to close.

Policy
------
Self-registration may only produce an UNPRIVILEGED account:
  - learner
  - corporate / employee

`hr_admin` is privileged: it grants access to compliance dashboards and other
employees' completion records, so it must never be obtainable by asking for it.
It can be granted two ways:

  1. Bootstrap — the email appears in HR_ADMIN_EMAILS in backend/.env. This
     solves the chicken-and-egg problem of creating the first HR account.
  2. Promotion — an existing hr_admin promotes another user via
     POST /users/{uid}/corporate-role.
"""

import os

MODE_LEARNER = "learner"
MODE_CORPORATE = "corporate"

ROLE_EMPLOYEE = "employee"
ROLE_HR_ADMIN = "hr_admin"

VALID_MODES = {MODE_LEARNER, MODE_CORPORATE}
VALID_CORPORATE_ROLES = {ROLE_EMPLOYEE, ROLE_HR_ADMIN}

# Roles a user may give themselves during registration.
SELF_ASSIGNABLE_CORPORATE_ROLES = {ROLE_EMPLOYEE}

# Roles that must be granted, never requested.
PRIVILEGED_CORPORATE_ROLES = VALID_CORPORATE_ROLES - SELF_ASSIGNABLE_CORPORATE_ROLES


def hr_admin_bootstrap_emails() -> set:
    """
    Emails permitted to self-register as hr_admin, from HR_ADMIN_EMAILS in the
    environment (comma-separated). Empty by default, so the escalation path is
    closed unless someone deliberately opens it for a named address.
    """
    raw = os.getenv("HR_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def resolve_registration_role(mode: str, role, email):
    """
    Validate a registration request and return the (mode, corporate_role) that
    should actually be stored.

    Raises ValueError with a message safe to return to the client.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")

    if mode == MODE_LEARNER:
        # A learner never carries a corporate role. Any role sent alongside
        # mode=learner is ignored rather than stored, so it cannot be read back
        # later by code that checks the role without also checking the mode.
        return MODE_LEARNER, None

    if role not in VALID_CORPORATE_ROLES:
        raise ValueError(
            f"role must be one of: {', '.join(sorted(VALID_CORPORATE_ROLES))} when mode is corporate"
        )

    if role in PRIVILEGED_CORPORATE_ROLES:
        allowed = hr_admin_bootstrap_emails()
        if not email or email.lower() not in allowed:
            raise PermissionError(
                "This role cannot be self-assigned. An existing HR administrator "
                "must grant it."
            )

    return MODE_CORPORATE, role
