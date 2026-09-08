from typing import Any

from ._backends import (
    DEFAULT_BACKEND,
    BackendConfig,
    ModelNotAvailableError,
    resolve,
)


def load(
    backend: Any = DEFAULT_BACKEND,
    model: str | None = None,
    local_only: bool = False,
    num_threads: int | None = None,
    **options: Any,
) -> None:
    config = BackendConfig(
        model=model,
        local_only=local_only,
        num_threads=num_threads,
        options=tuple(sorted(options.items())),
    )
    resolve(backend, config).load()


def find_person_spans(
    texts: list[str],
    backend: Any = DEFAULT_BACKEND,
    config: BackendConfig | None = None,
) -> list[list[tuple[int, int]]]:
    if not texts:
        return []
    return resolve(backend, config or BackendConfig()).person_spans(texts)


__all__ = ["load", "find_person_spans", "ModelNotAvailableError"]
