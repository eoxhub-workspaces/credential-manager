import base64
from unittest import mock

from async_asgi_testclient import TestClient
from kubernetes import client as k8s_client
import pytest

from my_credentials import app


@pytest.fixture
def client():
    # we only use this as a workaround for a starlette bug
    # https://github.com/tiangolo/fastapi/issues/806#issuecomment-567913676
    # https://github.com/encode/starlette/issues/472
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_k8s_base():
    with mock.patch("my_credentials.views.k8s_config"), mock.patch(
        "my_credentials.views.current_namespace"
    ):
        yield


@pytest.fixture()
def secret() -> k8s_client.V1Secret:
    data = {
        "username": "testington",
        "password": "123",
    }
    return k8s_client.V1Secret(
        metadata=k8s_client.V1ObjectMeta(name="credentials-a"),
        data={k: base64.b64encode(v.encode()) for k, v in data.items()},
    )
