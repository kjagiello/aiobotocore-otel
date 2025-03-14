import nox

nox.options.default_venv_backend = "uv"


def uv_run(session: nox.Session, *args: str) -> None:
    assert isinstance(session.python, str)
    session.run("uv", "run", "--python", session.python, "--active", *args)


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13"])
@nox.parametrize("aiobotocore", ["2.21.0", "2.21.1"])
def test(session: nox.Session, aiobotocore: str) -> None:
    uv_run(
        session,
        "--with",
        f"aiobotocore=={aiobotocore}",
        "--",
        "pytest",
        "--cov",
        "--cov-report=term",
        *session.posargs,
    )


@nox.session(python="3.13")
@nox.session
def lint(session: nox.Session) -> None:
    uv_run(session, "--", "ruff", "check")
    uv_run(session, "--", "ruff", "format", "--check")
