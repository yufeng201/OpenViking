"""Keep unsupported or conflicting project proposals out of searchable memory."""

import hashlib
import json

from openviking.server.error_mapping import is_not_found_error


async def retain_project_candidates(operations, *, archive_uri, messages, ctx, fs):
    accepted, candidates = [], []
    for op in operations.upsert_operations:
        if op.memory_fields.get("evidence_status") == "confirmed":
            accepted.append(op)
        else:
            candidates.append(
                {
                    "category": op.memory_type,
                    "fields": op.memory_fields,
                    "reason": op.memory_fields.get("evidence_status", "missing_evidence"),
                }
            )
    for deleted in operations.delete_file_contents:
        candidates.append(
            {"uri": deleted.uri, "reason": "automatic_project_delete_requires_review"}
        )
    if candidates:
        uri = f"{archive_uri}/memory-candidates.jsonl"
        path = fs._uri_to_path(uri, ctx=ctx)
        lease = await fs._async_agfs.pathlock_acquire_exact(path, timeout_secs=10.0)
        try:
            try:
                raw = await fs.read_file(uri, ctx=ctx)
            except Exception as exc:
                if not is_not_found_error(exc):
                    raise
                raw = ""
            existing = [json.loads(line) for line in raw.splitlines() if line.strip()]
            ids = {item["candidate_id"] for item in existing}
            for candidate in candidates:
                identity = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
                candidate_id = hashlib.sha256((archive_uri + identity).encode()).hexdigest()
                if candidate_id in ids:
                    continue
                existing.append(
                    dict(
                        candidate,
                        candidate_id=candidate_id,
                        archive_uri=archive_uri,
                        contributor_id=ctx.user.user_id,
                        message_ids=[message.id for message in messages],
                    )
                )
                ids.add(candidate_id)
            await fs.write_file(
                uri,
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in existing),
                ctx=ctx,
                lease_ref=lease,
            )
        finally:
            await fs._async_agfs.pathlock_release(lease)
    operations.upsert_operations = accepted
    operations.delete_file_contents = []
    operations.delete_replacements = {}
    allowed = {uri for op in accepted for uri in op.uris}
    operations.resolved_links = [
        link
        for link in operations.resolved_links
        if link.from_uri in allowed and link.to_uri in allowed
    ]
