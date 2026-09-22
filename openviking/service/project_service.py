"""Project management and membership authorization."""

from datetime import datetime, timezone

from openviking.server.identity import Role
from openviking_cli.exceptions import FailedPreconditionError, NotFoundError, PermissionDeniedError


class ProjectService:
    def __init__(self, store, manager):
        self.store = store
        self.manager = manager

    @staticmethod
    def require_admin(ctx):
        if ctx.role not in {Role.ADMIN, Role.ROOT}:
            raise PermissionDeniedError("Project management requires an account administrator")

    async def get(self, ctx, project_id):
        project = await self.store.get(ctx.account_id, project_id)
        if not project.get("initialized"):
            raise NotFoundError(project_id, "project")
        if ctx.role not in {Role.ADMIN, Role.ROOT}:
            try:
                members = await self.store.members(ctx.account_id, project["group_id"])
            except NotFoundError:
                members = []
            if ctx.user.user_id not in members:
                raise NotFoundError(project_id, "project")
        return project

    async def list(self, ctx):
        visible = []
        for project in await self.store.list(ctx.account_id):
            try:
                visible.append(await self.get(ctx, project["project_id"]))
            except NotFoundError:
                pass
        return visible

    async def create(self, ctx, data):
        self.require_admin(ctx)
        async with self.store.lock(ctx.account_id):
            await self.store.members(ctx.account_id, data["group_id"])
            return await self.store.create(ctx.account_id, ctx.user.user_id, data)

    async def update(self, ctx, project_id, changes):
        self.require_admin(ctx)
        async with self.store.lock(ctx.account_id):
            project = await self.get(ctx, project_id)
            project.update(changes, updated_at=datetime.now(timezone.utc).isoformat())
            await self.store.save(ctx.account_id, project)
            root = f"/local/{ctx.account_id}/project/{project_id}/memories"
            await self.store.agfs.write(
                f"{root}/overview.md", f"# {project['name']}\n\n{project['description']}\n".encode()
            )
            return project

    async def change_member(self, ctx, project_id, user_id, *, remove=False):
        self.require_admin(ctx)
        project = await self.get(ctx, project_id)
        if self.manager is None:
            raise FailedPreconditionError("User management is unavailable")
        action = self.manager.remove_group_member if remove else self.manager.add_group_member
        return await action(ctx.account_id, project["group_id"], user_id)

    async def ensure_group_unreferenced(self, account_id, group_id):
        for project in await self.store.list(account_id):
            if project["group_id"] == group_id:
                raise FailedPreconditionError("Group is referenced by a project")
