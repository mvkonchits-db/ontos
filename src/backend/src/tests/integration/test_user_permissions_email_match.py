"""Integration tests for /api/user/permissions email-based assignment (issue #197).

These tests exercise the full FastAPI dependency chain — TestClient -> route ->
PermissionChecker / get_user_effective_permissions -> SettingsManager — to catch
wiring bugs that pure unit tests would miss.

The CANARY test (`test_canary_unrelated_user_no_groups_still_denied`) is the
load-bearing security check for A2: relaxing the no-groups guard must not let
a user with no groups and an unrelated email gain any permissions.
"""
import json
import uuid

from src.common.features import FeatureAccessLevel
from src.db_models.settings import AppRoleDb


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _create_role_with_assigned_users(db_session, name, assigned_users, feature_permissions):
    """Insert a role row directly into the test DB.

    We bypass the public API here because POST /api/settings/roles depends on
    the audit manager which isn't wired in the test client. Direct insertion
    is closer to what we actually want to test: the auth resolution path.
    """
    role = AppRoleDb(
        id=str(uuid.uuid4()),
        name=name,
        description=f"{name} (created by test)",
        assigned_groups=json.dumps([]),
        assigned_users=json.dumps(assigned_users),
        feature_permissions=json.dumps(feature_permissions),
        home_sections=json.dumps([]),
        approval_privileges=json.dumps({}),
    )
    db_session.add(role)
    db_session.commit()
    return role


# ----------------------------------------------------------------------
# /api/user/permissions — email-based grant
# ----------------------------------------------------------------------

class TestUserPermissionsEmailMatch:
    """End-to-end: a user with no Databricks groups but an email assignment
    must receive the role's permissions."""

    def test_email_only_user_gets_role_permissions(self, client, db_session, mock_test_user):
        # Arrange — seed a role with alice as a direct user assignment
        _create_role_with_assigned_users(
            db_session,
            name="EmailOnlyRole",
            assigned_users=["alice@example.com"],
            feature_permissions={"data-products": "Read-only"},
        )

        # Act — switch identity to alice with NO groups, then ask for permissions
        mock_test_user.email = "alice@example.com"
        mock_test_user.groups = []

        resp = client.get("/api/user/permissions")

        # Assert
        assert resp.status_code == 200
        perms = resp.json()
        # data-products should be at least READ_ONLY for alice
        assert perms.get("data-products") == FeatureAccessLevel.READ_ONLY.value, (
            f"Email-assigned user did not receive expected permissions: {perms}"
        )

    def test_email_match_is_case_insensitive(self, client, db_session, mock_test_user):
        _create_role_with_assigned_users(
            db_session,
            name="CaseInsensitiveRole",
            assigned_users=["alice@example.com"],
            feature_permissions={"data-products": "Read-only"},
        )

        mock_test_user.email = "ALICE@Example.COM"
        mock_test_user.groups = []

        resp = client.get("/api/user/permissions")
        assert resp.status_code == 200
        assert resp.json().get("data-products") == FeatureAccessLevel.READ_ONLY.value


# ----------------------------------------------------------------------
# CANARY — must keep failing closed for unrelated users
# ----------------------------------------------------------------------

class TestNoGroupsGuardCanary:
    """SECURITY: relaxing the no-groups guard must not open a hole for users
    without legitimate role assignments."""

    def test_canary_unrelated_user_no_groups_still_denied(self, client, db_session, mock_test_user):
        # Arrange — role exists for alice only
        _create_role_with_assigned_users(
            db_session,
            name="AliceOnlyRole",
            assigned_users=["alice@example.com"],
            feature_permissions={"data-products": "Read-only"},
        )

        # Act — mallory (different email, no groups) hits a permission-gated endpoint
        mock_test_user.email = "mallory@example.com"
        mock_test_user.groups = []

        # Listing data domains requires READ_ONLY on data-domains.
        # We use this endpoint specifically because it's the canonical existing
        # PermissionChecker integration test target (test_data_domains_routes.py).
        resp = client.get("/api/data-domains")

        # Assert — the relaxed no-groups guard must NOT open a hole
        assert resp.status_code == 403, (
            f"SECURITY: unrelated user with no groups gained access to /api/data-domains "
            f"(got {resp.status_code}: {resp.text[:200]})"
        )

    def test_user_with_no_groups_and_no_email_match_gets_empty_permissions(
        self, client, mock_test_user
    ):
        """Per /api/user/permissions: an unprivileged user receives a permissions
        object with NONE / missing entries — not a 500, not a 200-with-everything."""
        mock_test_user.email = "nobody@example.com"
        mock_test_user.groups = []

        resp = client.get("/api/user/permissions")

        assert resp.status_code == 200
        perms = resp.json()
        # Every present feature must be NONE; no feature should be elevated
        elevated = {
            k: v for k, v in perms.items()
            if v not in (FeatureAccessLevel.NONE.value, None)
        }
        assert not elevated, (
            f"SECURITY: unrelated user gained non-NONE permissions: {elevated}"
        )
