# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Queue consumer for restart-safe Session Phase 2 work."""

import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from openviking.core.workspace import task_owner_key
from openviking.observability.context import (
    bind_root_observability_context,
    reset_root_observability_context,
)
from openviking.server.identity import RequestContext, Role
from openviking.service.task_tracker import get_task_tracker
from openviking.service.task_work_index import bind_task_context
from openviking.storage.queuefs.named_queue import DequeueHandlerBase
from openviking.storage.queuefs.process_result import ProcessResult
from openviking.storage.queuefs.session_commit_msg import SessionCommitMsg
from openviking.telemetry.span_models import create_root_span_attributes
from openviking_cli.session.user_id import UserIdentifier

if TYPE_CHECKING:
    from openviking.service.session_service import SessionService


class SessionCommitProcessor(DequeueHandlerBase):
    def __init__(
        self,
        session_service: "SessionService",
    ) -> None:
        self._session_service = session_service

    @staticmethod
    def _parse_message(data: Dict[str, Any]) -> tuple[SessionCommitMsg, RequestContext]:
        payload = data.get("data", data)
        if isinstance(payload, str):
            payload = json.loads(payload)
        msg = SessionCommitMsg.from_dict(payload)
        ctx = RequestContext(
            user=UserIdentifier.from_dict(msg.user),
            role=Role.USER,
        )
        if msg.workspace_target:
            from openviking.core.namespace import canonical_session_uri
            from openviking.core.workspace import WorkspaceTarget

            ctx.workspace_target = WorkspaceTarget.from_dict(msg.workspace_target)
            if (
                ctx.workspace_target.kind != "project"
                and ctx.workspace_target.owner_id != ctx.user.user_id
            ):
                raise ValueError("Workspace owner does not match queue identity")
            if canonical_session_uri(ctx, msg.session_id) != msg.session_uri:
                raise ValueError("Workspace does not match queue session URI")
            if not msg.archive_uri.startswith(msg.session_uri + "/history/") or any(
                p in {".", ".."} for p in msg.archive_uri.split("/")
            ):
                raise ValueError("Archive does not belong to session")
            ctx.workspace_session_uri = msg.session_uri
            ctx.workspace_worker = True
            if ctx.workspace_target.kind == "project":
                ctx.project_ids = (ctx.workspace_target.owner_id,)
        elif msg.session_uri.startswith("viking://project/") or "/peers/" in msg.session_uri:
            raise ValueError("Workspace session requires explicit queue ownership")
        return msg, ctx

    async def _process(self, msg: SessionCommitMsg, ctx: RequestContext) -> bool:
        # Bind a root observability context so Phase-2 extraction VLM/embedding
        # token events are attributed to the committing account/user rather than
        # "__unknown__" (mirrors SemanticProcessor.on_dequeue). Restore the
        # worker's previous context when processing finishes.
        root_attrs = create_root_span_attributes(
            http_method="QUEUE",
            http_route="/queuefs/session_commit",
            request_id=msg.task_id,
            url_path=msg.session_uri,
        )
        root_attrs.account_id = ctx.account_id
        root_attrs.user_id = ctx.user.user_id
        root_context_token = bind_root_observability_context(root_attrs)
        try:
            session = self._session_service.session(
                ctx,
                msg.session_id,
                session_uri=msg.session_uri,
            )
            if not await session.exists():
                error = f"Session '{msg.session_id}' no longer exists"
                tracker = get_task_tracker()
                await tracker.create(
                    "session_commit",
                    resource_id=msg.session_id,
                    account_id=ctx.account_id,
                    user_id=task_owner_key(ctx),
                    task_id=msg.task_id,
                )
                await tracker.fail(
                    msg.task_id,
                    error,
                    account_id=ctx.account_id,
                    user_id=task_owner_key(ctx),
                )
                return True
            await session.load()
            with bind_task_context(msg.task_id, ctx.account_id, task_owner_key(ctx)):
                processed = await session.resume_queued_commit(msg)
            if not processed:
                from openviking.storage.queuefs import QueueManager, get_queue_manager

                await get_queue_manager().enqueue(
                    QueueManager.SESSION_COMMIT,
                    msg.to_dict(),
                )
            return processed
        finally:
            reset_root_observability_context(root_context_token)

    async def _finalize_cancelled(self, msg: SessionCommitMsg, ctx: RequestContext) -> None:
        session = self._session_service.session(
            ctx,
            msg.session_id,
            session_uri=msg.session_uri,
        )
        if await session.exists():
            await session.finalize_cancelled_commit(msg.archive_uri)

    async def on_cancelled(self, data: Optional[Dict[str, Any]]) -> ProcessResult:
        if not data:
            return ProcessResult.cancelled()

        try:
            msg, ctx = self._parse_message(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return ProcessResult.failed(str(exc))

        await self._finalize_cancelled(msg, ctx)
        return ProcessResult.cancelled()

    async def on_dequeue(self, data: Optional[Dict[str, Any]]) -> ProcessResult:
        if not data:
            return ProcessResult.success()

        try:
            msg, ctx = self._parse_message(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return ProcessResult.failed(str(exc))
        processed = await self._process(msg, ctx)
        return ProcessResult.success() if processed else ProcessResult.requeued()
