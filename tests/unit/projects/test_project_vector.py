from dataclasses import replace

import pytest

from openviking.server.identity import Role
from openviking.storage.expr import And, Eq, In, Or, PathScope, RawDSL
from openviking.storage.viking_vector_index_backend import VikingVectorIndexBackend
from tests.unit.projects.test_workspace_pipeline import ctx


def matches(expr, row):
    if isinstance(expr, And):
        return all(matches(c, row) for c in expr.conds)
    if isinstance(expr, Or):
        return any(matches(c, row) for c in expr.conds)
    if isinstance(expr, Eq):
        return row.get(expr.field) == expr.value
    if isinstance(expr, In):
        return row.get(expr.field) in expr.values
    if isinstance(expr, PathScope):
        return row.get(expr.field, "").startswith(expr.path + "/")
    if isinstance(expr, RawDSL) and expr.payload["op"] == "must_not":
        return row.get(expr.payload["field"]) not in expr.payload["conds"]
    raise AssertionError(expr)


@pytest.mark.parametrize("acl", [True, False])
@pytest.mark.parametrize("role", [Role.USER, Role.ADMIN, Role.ROOT])
@pytest.mark.parametrize("worker", [True, False])
def test_project_filter_never_admits_personal_or_other_project_data(acl, role, worker):
    context = replace(ctx(), role=role, bypass_acl=worker)
    backend = object.__new__(VikingVectorIndexBackend)
    expression = backend._tenant_filter(context, acl_enabled=acl)
    own = {"account_id": "acme", "uri": "viking://project/orders/resources/api"}
    assert matches(expression, own)
    assert not matches(expression, {**own, "account_id": "other"})
    assert not matches(expression, {**own, "uri": "viking://project/payments/resources/api"})
    assert not matches(expression, {**own, "uri": "viking://user/alice/resources/private"})
