import nox

nox.options.default_venv_backend = "uv"


def uv_run(session: nox.Session, *args: str) -> None:
    assert isinstance(session.python, str)
    session.run("uv", "run", "--python", session.python, "--active", *args)


@nox.session(python=["3.10", "3.11", "3.12", "3.13", "3.14"])
@nox.parametrize(
    "aiobotocore",
    [
        "2.24.2",
        "2.25",
        "3.1.0",
        "3.2.0",
        "3.3.0",
        "3.4.0",
        "3.5.0",
        "3.6.0",
        "3.7.0",
        "3.8.0",
        "3.9.0",
    ],
)
def test(session: nox.Session, aiobotocore: str) -> None:
    uv_run(
        session,
        "--with",
        f"aiobotocore=={aiobotocore}",
        "--",
        "pytest",
        "--cov=src",
        "--cov=test",
        "--cov-report=term",
        *session.posargs,
    )


# Minimum supported OpenTelemetry API minor version; contrib packages
# (instrumentation, semconv, test-utils) are versioned as 0.(minor + 21)b0.
OTEL_MIN_MINOR = 28


@nox.session(python=["3.10", "3.14"])
@nox.parametrize("otel", ["min", "latest"])
def test_otel(session: nox.Session, otel: str) -> None:
    # Install into the session venv rather than using `uv run --with`: the
    # `opentelemetry` namespace package would otherwise mix modules from the
    # locked versions with the overlay (e.g. a removed module stays importable).
    session.run_install(
        "uv", "sync", "--active", "--frozen", "--python", session.python
    )
    if otel == "min":
        api, contrib = f"==1.{OTEL_MIN_MINOR}.0", f"==0.{OTEL_MIN_MINOR + 21}b0"
    else:
        api = contrib = ""
    packages = {
        "opentelemetry-api": api,
        "opentelemetry-sdk": api,
        "opentelemetry-instrumentation": contrib,
        "opentelemetry-semantic-conventions": contrib,
        "opentelemetry-test-utils": contrib,
    }
    # Only upgrade the OpenTelemetry packages; other packages keep their locked
    # versions unless the requested versions require otherwise.
    upgrade = [arg for name in packages for arg in ("--upgrade-package", name)]
    session.run_install(
        "uv",
        "pip",
        "install",
        *upgrade,
        *(f"{name}{spec}" for name, spec in packages.items()),
    )
    session.run("uv", "pip", "list")
    session.run(
        "uv",
        "run",
        "--active",
        "--no-sync",
        "--python",
        session.python,
        "--",
        "pytest",
        "--cov=src",
        "--cov=test",
        "--cov-report=term",
        *session.posargs,
    )


@nox.session(python="3.13")
@nox.session
def lint(session: nox.Session) -> None:
    uv_run(session, "--", "ruff", "check")
    uv_run(session, "--", "ruff", "format", "--check")
