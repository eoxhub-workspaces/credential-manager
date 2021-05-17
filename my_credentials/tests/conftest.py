import base64
from my_credentials.views import MY_SECRETS_LABEL_KEY, MY_SECRETS_LABEL_VALUE
from unittest import mock

from async_asgi_testclient import TestClient
from kubernetes import client as k8s_client
import pytest

from my_credentials import app


USER = "foo-123"


@pytest.fixture
def client():
    # we only use this as a workaround for a starlette bug
    # https://github.com/tiangolo/fastapi/issues/806#issuecomment-567913676
    # https://github.com/encode/starlette/issues/472
    return TestClient(
        app,
        headers={"X-Auth-Request-User": USER},
    )


@pytest.fixture(autouse=True)
def mock_k8s_base():
    with mock.patch("my_credentials.views.k8s_config"), mock.patch(
        "my_credentials.views.current_namespace",
        return_value=USER,
    ):
        yield


@pytest.fixture()
def secret() -> k8s_client.V1Secret:
    data = {
        "username": "testington",
        "password": "123",
        "existing-key": "foo",
    }
    return k8s_client.V1Secret(
        metadata=k8s_client.V1ObjectMeta(
            name="credentials-a",
            labels={
                MY_SECRETS_LABEL_KEY: MY_SECRETS_LABEL_VALUE,
            },
        ),
        data={k: base64.b64encode(v.encode()) for k, v in data.items()},
    )
