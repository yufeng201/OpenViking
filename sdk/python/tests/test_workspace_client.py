from unittest.mock import patch

import httpx
import pytest
from openviking_sdk import AsyncHTTPClient, SyncHTTPClient, use_actor_peer


@pytest.mark.asyncio
async def test_scoped_client_probes_and_pins_headers():
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "result": {"capabilities": {"protocol_version": 2, "target_kinds": ["project"]}},
            },
        )

    client = AsyncHTTPClient(
        url="http://test",
        api_key="test",
        project_id="orders",
        extra_headers={"X-OpenViking-Actor-Peer": "old"},
    )
    real = httpx.AsyncClient
    with patch(
        "openviking_sdk.client.httpx.AsyncClient",
        side_effect=lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs),
    ):
        await client.initialize()
    with use_actor_peer("injected"):
        await client._request("GET", "/test", headers={"x-openviking-project": "wrong"})
    assert seen[0].url.path == "/api/v1/workspace"
    assert all(r.headers["X-OpenViking-Project"] == "orders" for r in seen)
    assert all("X-OpenViking-Actor-Peer" not in r.headers for r in seen)
    await client.close()


@pytest.mark.asyncio
async def test_old_server_rejected_before_capture():
    client = AsyncHTTPClient(url="http://test", project_id="orders")
    real = httpx.AsyncClient
    with patch(
        "openviking_sdk.client.httpx.AsyncClient",
        side_effect=lambda **kwargs: real(
            transport=httpx.MockTransport(lambda request: httpx.Response(404, json={})), **kwargs
        ),
    ):
        with pytest.raises(ValueError):
            await client.initialize()
    assert client._http is None


def test_sync_constructor_and_conflicting_targets():
    assert SyncHTTPClient(
        url="http://test", workspace_peer_id="repo"
    )._async_client._workspace_headers == {"X-OpenViking-Workspace-Peer": "repo"}
    with pytest.raises(ValueError):
        AsyncHTTPClient(project_id="orders", workspace_peer_id="repo")
