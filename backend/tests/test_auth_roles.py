"""
Tests for role validation and authorization.

These exist because the registration endpoint previously accepted `mode` and
`role` straight from the client, so any authenticated user could register as
`hr_admin` and gain access to other employees' records. The tests below are the
regression guard for that defect.

Run from backend/:   python -m pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app.auth import roles  # noqa: E402


# --------------------------------------------------------------------------
# Registration: what a user may give themselves
# --------------------------------------------------------------------------

def test_learner_registration_is_allowed():
    mode, role = roles.resolve_registration_role("learner", None, "a@b.com")
    assert (mode, role) == ("learner", None)


def test_learner_cannot_smuggle_a_corporate_role():
    """mode=learner with role=hr_admin must not store the role."""
    mode, role = roles.resolve_registration_role("learner", "hr_admin", "a@b.com")
    assert mode == "learner"
    assert role is None


def test_corporate_employee_registration_is_allowed():
    mode, role = roles.resolve_registration_role("corporate", "employee", "a@b.com")
    assert (mode, role) == ("corporate", "employee")


def test_hr_admin_cannot_be_self_assigned():
    """The original privilege-escalation defect. Must raise."""
    with pytest.raises(PermissionError):
        roles.resolve_registration_role("corporate", "hr_admin", "attacker@example.com")


def test_hr_admin_allowed_only_for_bootstrap_emails(monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    mode, role = roles.resolve_registration_role("corporate", "hr_admin", "boss@company.com")
    assert (mode, role) == ("corporate", "hr_admin")


def test_bootstrap_list_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "Boss@Company.com")
    mode, role = roles.resolve_registration_role("corporate", "hr_admin", "BOSS@company.COM")
    assert role == "hr_admin"


def test_bootstrap_does_not_admit_other_emails(monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    with pytest.raises(PermissionError):
        roles.resolve_registration_role("corporate", "hr_admin", "someone@else.com")


def test_no_bootstrap_configured_blocks_everyone(monkeypatch):
    monkeypatch.delenv("HR_ADMIN_EMAILS", raising=False)
    with pytest.raises(PermissionError):
        roles.resolve_registration_role("corporate", "hr_admin", "anyone@any.com")


def test_missing_email_cannot_match_bootstrap(monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    with pytest.raises(PermissionError):
        roles.resolve_registration_role("corporate", "hr_admin", None)


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_mode", ["admin", "", "LEARNER", "superuser", None])
def test_invalid_mode_is_rejected(bad_mode):
    with pytest.raises(ValueError):
        roles.resolve_registration_role(bad_mode, None, "a@b.com")


@pytest.mark.parametrize("bad_role", ["admin", "", "HR_ADMIN", "root", None])
def test_invalid_corporate_role_is_rejected(bad_role):
    with pytest.raises(ValueError):
        roles.resolve_registration_role("corporate", bad_role, "a@b.com")


# --------------------------------------------------------------------------
# Policy constants — guard against someone widening these by accident
# --------------------------------------------------------------------------

def test_hr_admin_is_not_in_the_self_assignable_set():
    assert "hr_admin" not in roles.SELF_ASSIGNABLE_CORPORATE_ROLES


def test_hr_admin_is_marked_privileged():
    assert "hr_admin" in roles.PRIVILEGED_CORPORATE_ROLES


def test_valid_modes_are_exactly_two():
    assert roles.VALID_MODES == {"learner", "corporate"}
