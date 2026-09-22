"""Immutable asset ownership, separate from the authenticated contributor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from openviking.core.identifiers import validate_identifier_part


@dataclass(frozen=True)
class WorkspaceTarget:
    kind: Literal["user", "peer", "project"]
    owner_id: str
    peer_id: str | None = None

    def __post_init__(self):
        if self.kind not in {"user", "peer", "project"}:
            raise ValueError("Unsupported workspace kind")
        for name, value in (("owner_id", self.owner_id), ("peer_id", self.peer_id)):
            if name == "peer_id" and self.kind != "peer":
                if value is not None:
                    raise ValueError("Only peer workspaces accept peer_id")
                continue
            error = validate_identifier_part(value, name)
            if error or len(value) > 128:
                raise ValueError(error or f"{name} exceeds 128 characters")

    @property
    def root(self) -> str:
        if self.kind == "project":
            return f"viking://project/{self.owner_id}"
        root = f"viking://user/{self.owner_id}"
        return f"{root}/peers/{self.peer_id}" if self.kind == "peer" else root

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> WorkspaceTarget:
        if not isinstance(value, dict) or set(value) - {"kind", "owner_id", "peer_id"}:
            raise ValueError("Invalid workspace target")
        return cls(**value)

    @classmethod
    def from_headers(cls, user_id: str, project: str | None, peer: str | None):
        if project is not None and peer is not None:
            raise ValueError("Project and workspace peer are mutually exclusive")
        if project is not None:
            return cls("project", project)
        if peer is not None:
            return cls("peer", user_id, peer)
        return None


def workspace_root(ctx) -> str:
    target = ctx.workspace_target
    return target.root if target else f"viking://user/{ctx.user.user_id}"


def memory_root(ctx) -> str:
    return f"{workspace_root(ctx)}/memories"


def workspace_key(ctx) -> tuple:
    target = ctx.workspace_target or WorkspaceTarget("user", ctx.user.user_id)
    return (ctx.account_id, target.kind, target.owner_id, target.peer_id)


def task_owner_key(ctx) -> str:
    """Encode asset task ownership in the legacy task-store owner column.

    Tilde is forbidden in account user IDs, so project/peer buckets cannot
    collide with actual users. The authenticated identity remains unchanged.
    """
    target = ctx.workspace_target
    if target and target.kind == "project":
        return f"~project~{target.owner_id}"
    if target and target.kind == "peer":
        return f"~peer~{target.owner_id}~{target.peer_id}"
    return ctx.user.user_id


def context_for_owned_uri(ctx, uri: str):
    """Restore immutable ownership from a server-generated queue target URI."""
    from dataclasses import replace

    parts = uri.removeprefix("viking://").strip("/").split("/")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Invalid queued workspace URI")
    target = None
    if len(parts) >= 2 and parts[0] == "project":
        target = WorkspaceTarget("project", parts[1])
    elif len(parts) >= 4 and parts[0] == "user" and parts[2] == "peers":
        target = WorkspaceTarget("peer", parts[1], parts[3])
        if target.owner_id != ctx.user.user_id:
            raise ValueError("Queued peer owner does not match contributor")
    if target is None:
        return ctx
    return replace(
        ctx,
        workspace_target=target,
        workspace_worker=True,
        project_ids=(target.owner_id,) if target.kind == "project" else (),
        actor_peer_id=None,
    )


def resource_task_owner(msg) -> str:
    from openviking.server.identity import RequestContext, Role
    from openviking_cli.session.user_id import UserIdentifier

    return task_owner_key(
        context_for_owned_uri(
            RequestContext(UserIdentifier(msg.account_id, msg.user_id), Role.USER), msg.root_uri
        )
    )
