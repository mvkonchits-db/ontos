"""
Unit tests for AuthorizationManager

Tests authorization and permission management including:
- Effective permission calculation
- Permission merging from multiple roles
- Team role overrides
- Access level checking
"""
import pytest
import uuid
from unittest.mock import Mock

from src.controller.authorization_manager import AuthorizationManager
from src.models.settings import AppRole
from src.common.features import FeatureAccessLevel


class TestAuthorizationManager:
    """Test suite for AuthorizationManager"""

    @pytest.fixture
    def mock_settings_manager(self):
        """Create a mock SettingsManager."""
        return Mock()

    @pytest.fixture
    def manager(self, mock_settings_manager):
        """Create AuthorizationManager instance for testing."""
        return AuthorizationManager(settings_manager=mock_settings_manager)

    @pytest.fixture
    def developer_role(self):
        """Create a developer role with basic permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Developer",
            description="Developer role",
            assigned_groups=["developers"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,
                "data-contracts": FeatureAccessLevel.READ_WRITE,
                "teams": FeatureAccessLevel.READ_ONLY,
            },
            home_sections=[],
            approval_privileges={},
        )

    @pytest.fixture
    def admin_role(self):
        """Create an admin role with full permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Admin",
            description="Admin role",
            assigned_groups=["admins"],
            feature_permissions={
                "data-products": FeatureAccessLevel.ADMIN,
                "data-contracts": FeatureAccessLevel.ADMIN,
                "teams": FeatureAccessLevel.ADMIN,
                "settings": FeatureAccessLevel.ADMIN,
            },
            home_sections=[],
            approval_privileges={},
        )

    @pytest.fixture
    def viewer_role(self):
        """Create a viewer role with read-only permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Viewer",
            description="Viewer role",
            assigned_groups=["viewers"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_ONLY,
                "data-contracts": FeatureAccessLevel.READ_ONLY,
            },
            home_sections=[],
            approval_privileges={},
        )

    # Effective permission calculation tests
    def test_get_effective_permissions_no_groups(self, manager, mock_settings_manager):
        """Test calculating permissions with no user groups."""
        mock_settings_manager.list_app_roles.return_value = []
        
        result = manager.get_user_effective_permissions([])
        
        # Should return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_single_role(self, manager, mock_settings_manager, developer_role):
        """Test calculating permissions from a single matching role."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["developers"])
        
        # Should have permissions from developer role
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE
        assert result["data-contracts"] == FeatureAccessLevel.READ_WRITE
        assert result["teams"] == FeatureAccessLevel.READ_ONLY

    def test_get_effective_permissions_no_matching_roles(self, manager, mock_settings_manager, developer_role):
        """Test calculating permissions when no roles match user groups."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["unknown-group"])
        
        # Should return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_multiple_roles(self, manager, mock_settings_manager, developer_role, viewer_role):
        """Test merging permissions from multiple matching roles."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, viewer_role]
        
        result = manager.get_user_effective_permissions(["developers", "viewers"])
        
        # Should take the highest permission level for each feature
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE  # Higher of READ_WRITE and READ_ONLY
        assert result["data-contracts"] == FeatureAccessLevel.READ_WRITE

    def test_get_effective_permissions_highest_wins(self, manager, mock_settings_manager, developer_role, admin_role):
        """Test that highest permission level wins when merging."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, admin_role]
        
        result = manager.get_user_effective_permissions(["developers", "admins"])
        
        # Admin permissions should win
        assert result["data-products"] == FeatureAccessLevel.ADMIN
        assert result["data-contracts"] == FeatureAccessLevel.ADMIN
        assert result["teams"] == FeatureAccessLevel.ADMIN
        assert result["settings"] == FeatureAccessLevel.ADMIN

    def test_get_effective_permissions_partial_group_match(self, manager, mock_settings_manager, developer_role):
        """Test permissions when user has some matching and some non-matching groups."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["developers", "other-group"])
        
        # Should still get developer permissions
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE

    # Team role override tests
    def test_get_effective_permissions_with_team_override(self, manager, mock_settings_manager, developer_role, admin_role):
        """Test that team role override takes precedence."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, admin_role]
        
        result = manager.get_user_effective_permissions(
            user_groups=["developers"],
            team_role_override="Admin"
        )
        
        # Should use admin permissions despite only having developer group
        assert result["data-products"] == FeatureAccessLevel.ADMIN
        assert result["settings"] == FeatureAccessLevel.ADMIN

    def test_get_effective_permissions_invalid_team_override(self, manager, mock_settings_manager, developer_role):
        """Test fallback when team role override doesn't exist."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(
            user_groups=["developers"],
            team_role_override="NonExistentRole"
        )
        
        # Should fall back to group-based permissions
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE

    # has_permission tests
    def test_has_permission_sufficient(self, manager):
        """Test permission check when user has sufficient access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
            "data-contracts": FeatureAccessLevel.READ_ONLY,
        }
        
        # User has READ_WRITE, requires READ_ONLY
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_ONLY
        ) is True

    def test_has_permission_exact_match(self, manager):
        """Test permission check with exact level match."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
        }
        
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_WRITE
        ) is True

    def test_has_permission_insufficient(self, manager):
        """Test permission check when user lacks sufficient access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_ONLY,
        }
        
        # User has READ_ONLY, requires READ_WRITE
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_WRITE
        ) is False

    def test_has_permission_none_level(self, manager):
        """Test permission check when user has no access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.NONE,
        }
        
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_ONLY
        ) is False

    def test_has_permission_missing_feature(self, manager):
        """Test permission check for feature not in permissions."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
        }
        
        # Feature not in permissions should default to NONE
        assert manager.has_permission(
            effective_permissions,
            "unknown-feature",
            FeatureAccessLevel.READ_ONLY
        ) is False

    def test_has_permission_admin_level(self, manager):
        """Test permission check with admin level."""
        effective_permissions = {
            "settings": FeatureAccessLevel.ADMIN,
        }
        
        # Admin should have all lower levels
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.READ_ONLY
        ) is True
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.READ_WRITE
        ) is True
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.ADMIN
        ) is True

    # Edge cases
    def test_get_effective_permissions_none_groups(self, manager, mock_settings_manager):
        """Test handling None as user groups."""
        mock_settings_manager.list_app_roles.return_value = []
        
        result = manager.get_user_effective_permissions(None)
        
        # Should handle None gracefully and return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_role_with_unknown_feature(self, manager, mock_settings_manager):
        """Test handling role with permission for unknown feature."""
        role_with_unknown = AppRole(
            id=uuid.uuid4(),
            name="TestRole",
            description="Test",
            assigned_groups=["test"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,
                "unknown-feature-xyz": FeatureAccessLevel.ADMIN,  # Unknown feature
            },
            home_sections=[],
            approval_privileges={},
        )
        mock_settings_manager.list_app_roles.return_value = [role_with_unknown]
        
        result = manager.get_user_effective_permissions(["test"])

        # Should process valid features and skip unknown ones
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE
        assert "unknown-feature-xyz" not in result or result.get("unknown-feature-xyz") == FeatureAccessLevel.NONE


class TestAuthorizationByEmail:
    """Email-based role matching via assigned_users (issue #197).

    Roles match the user when EITHER groups intersect assigned_groups OR
    user email is in assigned_users. Group-only matching must keep working
    unchanged; email-only matching is the new path.
    """

    @pytest.fixture
    def mock_settings_manager(self):
        return Mock()

    @pytest.fixture
    def manager(self, mock_settings_manager):
        return AuthorizationManager(settings_manager=mock_settings_manager)

    @pytest.fixture
    def role_factory(self):
        def make(name="TestRole", assigned_groups=None, assigned_users=None,
                 feature_permissions=None):
            return AppRole(
                id=uuid.uuid4(),
                name=name,
                description=f"{name} (test)",
                assigned_groups=list(assigned_groups or []),
                assigned_users=list(assigned_users or []),
                feature_permissions=feature_permissions or {
                    "data-products": FeatureAccessLevel.READ_ONLY,
                },
                home_sections=[],
                approval_privileges={},
            )
        return make

    # ------------------------------------------------------------------
    # The full match-or-deny matrix
    # ------------------------------------------------------------------

    def test_email_only_match_grants_access(self, manager, mock_settings_manager, role_factory):
        """User with no groups but email in assigned_users gets the role's permissions."""
        role = role_factory(assigned_users=["alice@example.com"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="alice@example.com",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_ONLY

    def test_group_only_match_still_works(self, manager, mock_settings_manager, role_factory):
        """Existing group-based assignment must remain unchanged when assigned_users is empty."""
        role = role_factory(assigned_groups=["data-team"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=["data-team"],
            user_email="alice@example.com",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_ONLY

    def test_both_match_idempotent(self, manager, mock_settings_manager, role_factory):
        """When both groups and email match the same role, permissions are not double-counted."""
        role = role_factory(
            assigned_groups=["data-team"],
            assigned_users=["alice@example.com"],
            feature_permissions={"data-products": FeatureAccessLevel.READ_WRITE},
        )
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=["data-team"],
            user_email="alice@example.com",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_WRITE

    def test_email_match_is_case_insensitive(self, manager, mock_settings_manager, role_factory):
        """Email matching tolerates casing differences between input and stored value."""
        role = role_factory(assigned_users=["alice@example.com"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="ALICE@Example.COM",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_ONLY

    def test_email_match_strips_whitespace(self, manager, mock_settings_manager, role_factory):
        """Stray whitespace in input email does not block a legitimate match."""
        role = role_factory(assigned_users=["alice@example.com"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="  alice@example.com  ",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_ONLY

    # ------------------------------------------------------------------
    # The CANARY — must not regress
    # ------------------------------------------------------------------

    def test_unrelated_user_no_groups_no_email_match_denied(
        self, manager, mock_settings_manager, role_factory
    ):
        """SECURITY CANARY: a user with no groups and an email that matches no role
        must NOT receive any permissions. The no-groups guard relaxation must not
        open a hole."""
        role = role_factory(assigned_users=["alice@example.com"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="mallory@example.com",
        )

        assert all(level == FeatureAccessLevel.NONE for level in result.values()), (
            "SECURITY: unrelated user with no groups gained permissions"
        )

    def test_no_groups_no_email_returns_none_for_all(
        self, manager, mock_settings_manager, role_factory
    ):
        """A user with neither groups nor email gets NONE for every feature."""
        role = role_factory(assigned_groups=["data-team"], assigned_users=["alice@example.com"])
        mock_settings_manager.list_app_roles.return_value = [role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email=None,
        )

        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_email_in_one_role_groups_in_another_unions_permissions(
        self, manager, mock_settings_manager, role_factory
    ):
        """Two distinct roles matched via different paths union to the highest level per feature."""
        role_via_email = role_factory(
            name="Reader",
            assigned_users=["alice@example.com"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_ONLY,
                "data-contracts": FeatureAccessLevel.READ_ONLY,
            },
        )
        role_via_group = role_factory(
            name="Writer",
            assigned_groups=["data-writers"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,  # higher — should win
                "teams": FeatureAccessLevel.READ_ONLY,
            },
        )
        mock_settings_manager.list_app_roles.return_value = [role_via_email, role_via_group]

        result = manager.get_user_effective_permissions(
            user_groups=["data-writers"],
            user_email="alice@example.com",
        )

        assert result["data-products"] == FeatureAccessLevel.READ_WRITE   # from group role
        assert result["data-contracts"] == FeatureAccessLevel.READ_ONLY    # only from email role
        assert result["teams"] == FeatureAccessLevel.READ_ONLY             # only from group role

    # ------------------------------------------------------------------
    # Team-role override + email assignment precedence (#197 follow-up)
    # ------------------------------------------------------------------

    def test_team_role_override_wins_over_email_assignment(
        self, manager, mock_settings_manager, role_factory
    ):
        """Team role override is unconditional — even if the user has a higher-priv
        role via email assignment, the override takes full precedence.

        Locks in the documented behavior: team-role-override branch returns early
        BEFORE the OR-matching loop runs, so email-based matching never gets a
        chance to elevate the user."""
        # Email-assigned role grants WRITE
        email_role = role_factory(
            name="EmailAssignedWriter",
            assigned_users=["alice@example.com"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,
            },
        )
        # Team override role grants only READ_ONLY (lower than email-assigned!)
        override_role = role_factory(
            name="ReadOnlyOverride",
            assigned_groups=[],
            assigned_users=[],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_ONLY,
            },
        )
        mock_settings_manager.list_app_roles.return_value = [email_role, override_role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="alice@example.com",
            team_role_override="ReadOnlyOverride",
        )

        # Override wins: the email-based WRITE permission must NOT leak through.
        assert result["data-products"] == FeatureAccessLevel.READ_ONLY, (
            f"team_role_override must take precedence over email assignment; "
            f"got data-products={result['data-products']}"
        )

    def test_team_role_override_missing_falls_back_to_email_match(
        self, manager, mock_settings_manager, role_factory
    ):
        """If the named override role doesn't exist, fall back to normal matching
        (groups + email). This is the documented fallback behavior — the override
        is best-effort, not a hard requirement."""
        email_role = role_factory(
            name="DataConsumer",
            assigned_users=["alice@example.com"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_ONLY,
            },
        )
        mock_settings_manager.list_app_roles.return_value = [email_role]

        result = manager.get_user_effective_permissions(
            user_groups=[],
            user_email="alice@example.com",
            team_role_override="NonexistentRole",  # not in list_app_roles
        )

        # Override is missing — falls back to email match → DataConsumer perms apply
        assert result["data-products"] == FeatureAccessLevel.READ_ONLY


class TestApprovalCheckerEmailMatch:
    """ApprovalChecker.__call__ direct unit tests (issue #197 follow-up).

    Hits the OR-matching code path inside ApprovalChecker that we previously
    only covered indirectly via AuthorizationManager. Constructed deliberately
    to bypass FastAPI dep resolution (audit_manager etc. are not relevant here)
    and exercise the exact branch added in A2.
    """

    @pytest.fixture
    def mock_settings_manager(self):
        m = Mock()
        # Default: no role override applied
        m.get_applied_role_override_for_user.return_value = None
        return m

    @pytest.fixture
    def approval_role_factory(self):
        from src.models.settings import ApprovalEntity

        def make(name, assigned_groups=None, assigned_users=None, can_approve_contracts=False,
                 can_approve_products=False):
            return AppRole(
                id=uuid.uuid4(),
                name=name,
                description=f"{name} (approval test)",
                assigned_groups=list(assigned_groups or []),
                assigned_users=list(assigned_users or []),
                feature_permissions={},
                home_sections=[],
                approval_privileges={
                    ApprovalEntity.CONTRACTS: can_approve_contracts,
                    ApprovalEntity.PRODUCTS: can_approve_products,
                },
            )
        return make

    def test_approval_granted_via_email_assignment(
        self, mock_settings_manager, approval_role_factory
    ):
        """Email-only user with approval privilege via assigned_users gets through."""
        import asyncio
        from src.common.authorization import ApprovalChecker
        from src.models.users import UserInfo
        from src.models.settings import ApprovalEntity
        from unittest.mock import Mock as _Mock

        approver_role = approval_role_factory(
            name="ContractApprover",
            assigned_users=["alice@example.com"],
            can_approve_contracts=True,
        )
        mock_settings_manager.list_app_roles.return_value = [approver_role]

        checker = ApprovalChecker(ApprovalEntity.CONTRACTS)
        alice = UserInfo(
            email="alice@example.com",
            username="alice",
            user="Alice",
            ip="127.0.0.1",
            groups=[],  # no groups
        )

        # Should not raise — approval granted
        asyncio.run(
            checker(request=_Mock(), user_details=alice, settings_manager=mock_settings_manager)
        )

    def test_approval_denied_for_unrelated_user_canary(
        self, mock_settings_manager, approval_role_factory
    ):
        """SECURITY CANARY: ApprovalChecker — unrelated user with no groups must
        NOT receive approval privilege via the OR-matching path."""
        import asyncio
        from src.common.authorization import ApprovalChecker
        from src.models.users import UserInfo
        from src.models.settings import ApprovalEntity
        from fastapi import HTTPException
        from unittest.mock import Mock as _Mock

        approver_role = approval_role_factory(
            name="ContractApprover",
            assigned_users=["alice@example.com"],
            can_approve_contracts=True,
        )
        mock_settings_manager.list_app_roles.return_value = [approver_role]

        checker = ApprovalChecker(ApprovalEntity.CONTRACTS)
        mallory = UserInfo(
            email="mallory@example.com",  # not in assigned_users
            username="mallory",
            user="Mallory",
            ip="127.0.0.1",
            groups=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                checker(
                    request=_Mock(),
                    user_details=mallory,
                    settings_manager=mock_settings_manager,
                )
            )
        assert exc_info.value.status_code == 403, (
            f"SECURITY: ApprovalChecker did not deny unrelated user "
            f"(got status {exc_info.value.status_code})"
        )

    def test_approval_via_email_case_insensitive(
        self, mock_settings_manager, approval_role_factory
    ):
        """Email match for approval is case-insensitive on both sides."""
        import asyncio
        from src.common.authorization import ApprovalChecker
        from src.models.users import UserInfo
        from src.models.settings import ApprovalEntity
        from unittest.mock import Mock as _Mock

        approver_role = approval_role_factory(
            name="ContractApprover",
            assigned_users=["alice@example.com"],
            can_approve_contracts=True,
        )
        mock_settings_manager.list_app_roles.return_value = [approver_role]

        checker = ApprovalChecker(ApprovalEntity.CONTRACTS)
        alice_upper = UserInfo(
            email="ALICE@Example.COM",
            username="alice",
            user="Alice (mixed case email)",
            ip="127.0.0.1",
            groups=[],
        )

        # Must not raise — case-insensitive match grants approval
        asyncio.run(
            checker(
                request=_Mock(), user_details=alice_upper, settings_manager=mock_settings_manager
            )
        )

    def test_approval_granted_via_group_when_assigned_users_empty(
        self, mock_settings_manager, approval_role_factory
    ):
        """Existing group-based approval path must keep working unchanged
        when assigned_users is empty (regression guard for #197)."""
        import asyncio
        from src.common.authorization import ApprovalChecker
        from src.models.users import UserInfo
        from src.models.settings import ApprovalEntity
        from unittest.mock import Mock as _Mock

        approver_role = approval_role_factory(
            name="ContractApprover",
            assigned_groups=["governance-team"],
            assigned_users=[],
            can_approve_contracts=True,
        )
        mock_settings_manager.list_app_roles.return_value = [approver_role]

        checker = ApprovalChecker(ApprovalEntity.CONTRACTS)
        bob = UserInfo(
            email="bob@example.com",
            username="bob",
            user="Bob",
            ip="127.0.0.1",
            groups=["governance-team"],
        )

        # Group match must still grant approval — ensures A2's OR didn't break the AND-path
        asyncio.run(
            checker(request=_Mock(), user_details=bob, settings_manager=mock_settings_manager)
        )

