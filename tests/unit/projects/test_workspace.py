import pytest

from openviking.core.namespace import (
    canonical_session_uri,
    canonical_user_root,
    context_type_for_uri,
    is_accessible,
    is_session_uri,
    owner_fields_for_uri,
    resolve_uri,
)
from openviking.core.workspace import WorkspaceTarget
from openviking.server.identity import RequestContext, Role
from openviking_cli.session.user_id import UserIdentifier


def context(target=None, projects=()):
    return RequestContext(
        user=UserIdentifier("acme", "alice"),
        role=Role.USER,
        workspace_target=target,
        project_ids=projects,
    )


@pytest.mark.parametrize(
    "kind,owner,peer",
    [
        ("project", "../x", None),
        ("project", "", None),
        ("project", "a/b", None),
        ("project", "a", "b"),
        ("peer", "alice", None),
        ("peer", "alice", "../b"),
        ("other", "a", None),
    ],
)
def test_unsafe_targets_rejected(kind, owner, peer):
    with pytest.raises(ValueError):
        WorkspaceTarget(kind, owner, peer)


def test_scope_does_not_change_actor_or_home():
    ctx = context(WorkspaceTarget("project", "orders"), ("orders",))
    assert canonical_session_uri(ctx, "s1") == "viking://project/orders/sessions/s1"
    assert canonical_user_root(ctx) == "viking://user/alice"
    assert ctx.user.user_id == "alice"
    assert is_accessible("viking://project/orders/resources/api", ctx)
    assert not is_accessible("viking://project/payments/resources/api", ctx)
    assert not is_accessible("viking://project/orders", context())


def test_peer_and_legacy_session_paths():
    peer = context(WorkspaceTarget("peer", "alice", "repo"))
    assert canonical_session_uri(peer, "s") == "viking://user/alice/peers/repo/sessions/s"
    assert canonical_session_uri(context(), "s") == "viking://user/alice/sessions/s"
    assert is_session_uri(canonical_session_uri(peer, "s"))


def test_project_classification_and_ownership():
    uri = "viking://project/orders/memories/architecture/api.md"
    assert context_type_for_uri(uri) == "memory"
    assert owner_fields_for_uri(uri) == {
        "uri": uri,
        "owner_user_id": None,
        "owner_project_id": "orders",
    }
    assert resolve_uri(uri).owner_project_id == "orders"
    assert is_session_uri("viking://project/orders/sessions/s1")


def test_header_conflicts_and_serialization():
    with pytest.raises(ValueError):
        WorkspaceTarget.from_headers("alice", "orders", "repo")
    target = WorkspaceTarget.from_headers("alice", None, "repo")
    assert WorkspaceTarget.from_dict(target.to_dict()) == target
