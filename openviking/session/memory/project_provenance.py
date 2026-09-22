"""Persist trusted archive provenance, never model-supplied ownership."""


def add_project_source(metadata, operation, ctx):
    references = operation.project_sources or ([operation.source] if operation.source else [])
    if not references:
        raise ValueError("Project memory requires archive provenance")
    sources = list(metadata.get("sources") or [])
    for source in references:
        if not source.archive_uri or not source.archive_uri.startswith(
            ctx.workspace_target.root + "/sessions/"
        ):
            raise ValueError("Project memory source is outside the workspace")
        reference = {
            "archive_uri": source.archive_uri,
            "repository": source.repository,
            "session_id": source.session_id,
            "contributor_id": source.contributor_id,
            "message_ids": source.source_message_ids,
            "extracted_at": source.extracted_at,
        }
        key = (reference["archive_uri"], tuple(reference["message_ids"]))
        if not any(
            (item.get("archive_uri"), tuple(item.get("message_ids", []))) == key for item in sources
        ):
            sources.append(reference)
    metadata["sources"] = sources
    metadata["owner_project_id"] = ctx.workspace_target.owner_id
