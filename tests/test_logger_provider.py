import asyncio
from unittest import mock

import aiobotocore.session
import pytest
from moto import mock_aws

from opentelemetry.instrumentation.aiobotocore import AioBotocoreInstrumentor
from opentelemetry.sdk._logs import LoggerProvider


@pytest.fixture(name="instrumentor")
def fixture_instrumentor():
    instrumentor = AioBotocoreInstrumentor()
    yield instrumentor
    instrumentor.uninstrument()


@pytest.mark.usefixtures("mock_aws_response")
def test_logger_provider(instrumentor):
    logger_provider = mock.Mock(wraps=LoggerProvider())
    instrumentor.instrument(logger_provider=logger_provider)

    async def list_queues():
        session = aiobotocore.session.get_session()
        session.set_credentials(access_key="access-key", secret_key="secret-key")
        async with session.create_client("sqs", region_name="us-west-2") as client:
            await client.list_queues()

    with mock_aws():
        asyncio.run(list_queues())

    logger_provider.get_logger.assert_called_once()


def test_event_logger_provider_is_deprecated(instrumentor):
    with pytest.warns(
        DeprecationWarning, match="Use logger_provider instead"
    ) as record:
        instrumentor.instrument(event_logger_provider=mock.Mock())

    # The warning points at the caller of instrument()
    assert record[0].filename == __file__
