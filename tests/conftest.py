"""Unit tests configuration module."""

import asyncio
import json
import os
from typing import Awaitable
from unittest import mock

import aiobotocore.awsrequest
import aiobotocore.endpoint
import pytest
import yaml

from opentelemetry.instrumentation.aiobotocore import AioBotocoreInstrumentor
from opentelemetry.instrumentation.aiobotocore.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import (
    MeterProvider,
)
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogExporter()
    yield exporter


@pytest.fixture(scope="function", name="metric_reader")
def fixture_metric_reader():
    reader = InMemoryMetricReader()
    yield reader


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function", name="event_logger_provider")
def fixture_event_logger_provider(log_exporter):
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    event_logger_provider = EventLoggerProvider(provider)

    return event_logger_provider


@pytest.fixture(scope="function", name="meter_provider")
def fixture_meter_provider(metric_reader):
    meter_provider = MeterProvider(
        metric_readers=[metric_reader],
    )

    return meter_provider


@pytest.fixture(autouse=True)
def environment():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        os.environ["AWS_ACCESS_KEY_ID"] = "test_aws_access_key_id"
    if not os.getenv("AWS_SECRET_ACCESS_KEY"):
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test_aws_secret_key"
    if not os.getenv("AWS_DEFAULT_REGION"):
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def instrument_no_content(tracer_provider, event_logger_provider, meter_provider):
    os.environ.update({OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "False"})

    instrumentor = AioBotocoreInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        event_logger_provider=event_logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider, event_logger_provider, meter_provider):
    os.environ.update({OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"})
    instrumentor = AioBotocoreInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        event_logger_provider=event_logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    response["headers"]["Set-Cookie"] = "test_set_cookie"
    # SDK validates response length which we modify by pretty-printing JSON.
    # Content length does not affect our instrumentation so just drop it.
    response["headers"].pop("Content-Length", None)
    return response


class LiteralBlockScalar(str):
    """Formats the string as a literal block scalar, preserving whitespace and
    without interpreting escape characters"""


def literal_block_scalar_presenter(dumper, data):
    """Represents a scalar string as a literal block, via '|' syntax"""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlockScalar, literal_block_scalar_presenter)


def process_string_value(string_value):
    """Pretty-prints JSON or returns long strings as a LiteralBlockScalar"""
    if isinstance(string_value, bytes):
        return string_value
    try:
        json_data = json.loads(string_value)
        return LiteralBlockScalar(json.dumps(json_data, indent=2))
    except (ValueError, TypeError):
        if len(string_value) > 80:
            return LiteralBlockScalar(string_value)
    return string_value


def convert_body_to_literal(data):
    """Searches the data for body strings, attempting to pretty-print JSON"""
    if isinstance(data, dict):
        for key, value in data.items():
            # Handle response body case (e.g., response.body.string)
            if key == "body" and isinstance(value, dict) and "string" in value:
                value["string"] = process_string_value(value["string"])

            # Handle request body case (e.g., request.body)
            elif key == "body" and isinstance(value, str):
                data[key] = process_string_value(value)

            else:
                convert_body_to_literal(value)

    elif isinstance(data, list):
        for idx, choice in enumerate(data):
            data[idx] = convert_body_to_literal(choice)

    # botocore uses bytes types for string values in headers, making recordings
    # of them unreadable. It is fine to convert to strings where possible as vcr
    # will still match them correctly.
    elif isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            pass

    return data


@pytest.fixture
def mock_aws_response():
    async def patch_read(self, _amt=None):
        self.__wrapped__.seek(0)
        return self.__wrapped__.read()

    def patch_response(original):
        async def _inner(http_response, operation_model):
            if not isinstance(http_response._content, Awaitable):
                fut = asyncio.Future()
                fut.set_result(http_response.content)
                http_response._content = fut
            return await original(http_response, operation_model)

        return _inner

    with (
        mock.patch(
            "aiobotocore.endpoint.convert_to_response_dict",
            patch_response(aiobotocore.endpoint.convert_to_response_dict),
        ),
        mock.patch.object(aiobotocore.response.StreamingBody, "read", patch_read),
        mock.patch.object(aiobotocore.httpchecksum.AioAwsChunkedWrapper, "_make_chunk"),
        mock.patch.object(aiobotocore.httpchecksum.AioAwsChunkedWrapper, "read"),
    ):
        del aiobotocore.httpchecksum.AioAwsChunkedWrapper._make_chunk
        del aiobotocore.httpchecksum.AioAwsChunkedWrapper.read

        yield
