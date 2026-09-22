"""Account-owned project metadata, persisted independently of contributors."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from openviking.core.identifiers import validate_account_id
from openviking.core.workspace import WorkspaceTarget
from openviking.server.error_mapping import is_not_found_error
from openviking_cli.exceptions import AlreadyExistsError, InvalidArgumentError, NotFoundError


class ProjectStore:
    def __init__(self, agfs):
        self.agfs = agfs

    def root(self, account_id: str) -> str:
        error = validate_account_id(account_id)
        if error:
            raise InvalidArgumentError(error)
        return f"/local/{account_id}/_system/projects"

    def path(self, account_id: str, project_id: str) -> str:
        try:
            WorkspaceTarget("project", project_id)
        except ValueError as exc:
            raise InvalidArgumentError(str(exc)) from exc
        return f"{self.root(account_id)}/{project_id}.json"

    async def read_json(self, path: str):
        try:
            raw = await self.agfs.read(path)
        except Exception as exc:
            if is_not_found_error(exc):
                return None
            raise
        if not isinstance(raw, (str, bytes)):
            raw = raw.content
        return json.loads(raw)

    async def get(self, account_id: str, project_id: str) -> dict:
        record = await self.read_json(self.path(account_id, project_id))
        if record is None:
            raise NotFoundError(project_id, "project")
        return record

    async def list(self, account_id: str) -> list[dict]:
        try:
            entries = await self.agfs.ls(self.root(account_id))
        except Exception as exc:
            if is_not_found_error(exc):
                return []
            raise
        return [
            await self.get(account_id, e["name"][:-5])
            for e in entries
            if not e.get("isDir") and e.get("name", "").endswith(".json")
        ]

    @asynccontextmanager
    async def lock(self, account_id: str):
        # Serializes project creation/update and group-reference checks.
        path = f"{self.root(account_id)}/.registry"
        await self.agfs.ensure_parent_dirs(path)
        lease = await self.agfs.pathlock_acquire_exact(path, timeout_secs=10.0)
        try:
            yield
        finally:
            await self.agfs.pathlock_release(lease)

    async def save(self, account_id: str, record: dict):
        path = self.path(account_id, record["project_id"])
        await self.agfs.ensure_parent_dirs(path)
        await self.agfs.write(path, json.dumps(record, ensure_ascii=False).encode())

    async def create(self, account_id: str, actor: str, data: dict) -> dict:
        path = self.path(account_id, data["project_id"])
        existing = await self.read_json(path)
        if existing and existing.get("initialized"):
            raise AlreadyExistsError(data["project_id"], "project")
        if existing and (
            existing["created_by"] != actor or existing["group_id"] != data["group_id"]
        ):
            raise AlreadyExistsError(data["project_id"], "project")
        now = datetime.now(timezone.utc).isoformat()
        record = existing or dict(
            data,
            account_id=account_id,
            schema_version=1,
            status="active",
            initialized=False,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        await self.save(account_id, record)
        root = f"/local/{account_id}/project/{data['project_id']}"
        for directory in ("resources", "sessions", "memories"):
            await self.agfs.ensure_parent_dirs(f"{root}/{directory}/.placeholder")
        overview = f"# {record['name']}\n\n{record['description']}\n"
        await self.agfs.write(f"{root}/memories/overview.md", overview.encode())
        record["initialized"] = True
        await self.save(account_id, record)
        return record

    async def members(self, account_id: str, group_id: str) -> list[str]:
        # Read authoritative group storage, not a possibly stale worker cache.
        data = await self.read_json(f"/local/{account_id}/_system/groups.json") or {}
        group = data.get("groups", {}).get(group_id)
        if group is None:
            raise NotFoundError(group_id, "group")
        return sorted(set(group.get("members", [])))
