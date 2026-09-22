"""Request-local schemas with server-bound roots; shared registries remain immutable."""

from copy import deepcopy

from openviking.core.workspace import memory_root
from openviking.prompts.manager import PromptManager
from openviking.session.memory.memory_type_registry import MemoryTypeRegistry, get_default_registry

PROJECT_MEMORY_TYPES = frozenset({"architecture", "conventions", "decisions", "experiences"})


def workspace_registry(ctx, base=None):
    target = getattr(ctx, "workspace_target", None)
    if target is None:
        return base or get_default_registry()
    if target.kind == "project":
        source = MemoryTypeRegistry(load_schemas=False)
        loaded = source.load_from_directory(
            str(PromptManager._get_bundled_templates_dir() / "memory" / "project")
        )
        if loaded != len(PROJECT_MEMORY_TYPES):
            raise RuntimeError("Project memory schemas are incomplete")
    else:
        source = base or get_default_registry()
    result = MemoryTypeRegistry(load_schemas=False)
    for schema in source.list_all(include_disabled=True):
        bound = deepcopy(schema)
        # Bind the trusted directory before handing schemas to extraction/merge.
        # Model-provided fields can only affect escaped filename segments.
        if target.kind == "project":
            bound.directory = f"{memory_root(ctx)}/{schema.memory_type}"
        else:
            prefix = "viking://user/{{ user_space }}/memories"
            if not bound.directory.startswith(prefix):
                continue
            bound.directory = memory_root(ctx) + bound.directory[len(prefix) :]
        bound.peer_enabled = False
        result.register(bound)
    return result
