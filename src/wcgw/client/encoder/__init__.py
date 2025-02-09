import threading
from typing import Callable, Protocol, TypeVar, cast

import tokenizers  # type: ignore[import-untyped]

T = TypeVar("T")


class EncoderDecoder(Protocol[T]):
    def encoder(self, text: str) -> list[T]: ...

    def decoder(self, tokens: list[T]) -> str: ...


class LazyEncoder:
    def __init__(self) -> None:
        self._tokenizer: tokenizers.Tokenizer | None = None
        self._init_lock = threading.Lock()
        self._init_thread = threading.Thread(target=self._initialize, daemon=True)
        self._init_thread.start()

    def _initialize(self) -> None:
        with self._init_lock:
            if self._tokenizer is None:
                self._tokenizer = tokenizers.Tokenizer.from_pretrained(
                    "Xenova/claude-tokenizer"
                )

    def _ensure_initialized(self) -> None:
        if self._tokenizer is None:
            with self._init_lock:
                if self._tokenizer is None:
                    self._init_thread.join()

    def encoder(self, text: str) -> list[int]:
        self._ensure_initialized()
        assert self._tokenizer is not None, "Couldn't initialize tokenizer"
        return cast(list[int], self._tokenizer.encode(text).ids)

    def decoder(self, tokens: list[int]) -> str:
        self._ensure_initialized()
        assert self._tokenizer is not None, "Couldn't initialize tokenizer"
        return cast(str, self._tokenizer.decode(tokens))


def get_default_encoder() -> EncoderDecoder[int]:
    return LazyEncoder()
