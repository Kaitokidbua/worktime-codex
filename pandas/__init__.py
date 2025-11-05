"""Minimal pandas-compatible stubs for offline execution.

This module implements a tiny subset of the pandas API that is required by
`attendance.py` and its unit tests.  The goal is to provide a predictable
DataFrame structure without depending on the real pandas package, which is not
available in the execution environment.

The implementation is intentionally small and only supports the methods used by
this repository.  It should not be considered a drop-in replacement for
pandas.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, List, Sequence


class Series:
    """A very small Series implementation supporting iteration and astype."""

    def __init__(self, data: Iterable[Any] | None = None) -> None:
        self._data: List[Any] = list(data) if data is not None else []

    def astype(self, dtype: type | str) -> "Series":
        if dtype in (str, "str"):
            return Series(str(value) if value is not None else "" for value in self._data)
        raise TypeError(f"Unsupported dtype conversion: {dtype}")

    def to_list(self) -> List[Any]:
        return list(self._data)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._data)

    def __getitem__(self, index: int) -> Any:  # pragma: no cover - trivial
        return self._data[index]


@dataclass
class _RowProxy:
    """Dictionary-backed row accessor used by iterrows/iloc."""

    _data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._data.get(key, default)

    def items(self):  # pragma: no cover - simple delegator
        return self._data.items()


class DataFrame:
    """Minimal DataFrame storing rows as dictionaries."""

    def __init__(self, data: Iterable[dict[str, Any]] | None = None, columns: Sequence[str] | None = None) -> None:
        if data is None:
            self._rows: List[dict[str, Any]] = []
        else:
            rows = []
            for entry in data:
                if not isinstance(entry, dict):
                    raise TypeError("DataFrame data must be an iterable of dictionaries")
                rows.append(dict(entry))
            self._rows = rows

        if columns is None:
            if self._rows:
                self._columns = list(self._rows[0].keys())
            else:
                self._columns = []
        else:
            self._columns = list(columns)
            for row in self._rows:
                for col in self._columns:
                    row.setdefault(col, None)

    @property
    def columns(self) -> List[str]:
        return list(self._columns)

    @property
    def empty(self) -> bool:
        return not self._rows

    def copy(self) -> "DataFrame":
        return DataFrame(deepcopy(self._rows), columns=self._columns)

    def iterrows(self) -> Iterator[tuple[int, _RowProxy]]:
        for index, row in enumerate(self._rows):
            yield index, _RowProxy(row)

    def sort_values(self, by: Sequence[str], inplace: bool = False) -> "DataFrame":
        if isinstance(by, str):
            sort_keys = [by]
        else:
            sort_keys = list(by)
        sorted_rows = sorted(self._rows, key=lambda row: tuple(row.get(col) for col in sort_keys))
        if inplace:
            self._rows = sorted_rows
            return self
        return DataFrame(sorted_rows, columns=self._columns)

    def reset_index(self, drop: bool = False, inplace: bool = False) -> "DataFrame":  # noqa: ARG002 - API compatibility
        if inplace:
            return self
        return self.copy()

    def __getitem__(self, key: str | Sequence[str]) -> Series | "DataFrame":
        if isinstance(key, str):
            return Series(row.get(key) for row in self._rows)
        if isinstance(key, Sequence):
            return DataFrame([{col: row.get(col) for col in key} for row in self._rows], columns=key)
        raise TypeError("Invalid key type for DataFrame indexing")

    def __setitem__(self, key: str, value: Iterable[Any] | Any) -> None:
        if isinstance(value, Series):
            values = value.to_list()
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            values = list(value)
        else:
            values = [value for _ in range(len(self._rows))]
        if self._rows and len(values) != len(self._rows):
            raise ValueError("Column assignment length mismatch")
        if not self._rows:
            # Allow setting a column on an empty frame
            self._columns.append(key)
            return
        for row, new_value in zip(self._rows, values):
            row[key] = new_value
        if key not in self._columns:
            self._columns.append(key)

    def to_dicts(self) -> List[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._rows)

    @property
    def iloc(self) -> "_ILocAccessor":
        return _ILocAccessor(self)


class _ILocAccessor:
    def __init__(self, df: DataFrame) -> None:
        self._df = df

    def __getitem__(self, index: int) -> _RowProxy:
        return _RowProxy(self._df._rows[index])


def concat(frames: Sequence[DataFrame], ignore_index: bool = False) -> DataFrame:  # noqa: ARG002 - keep signature
    rows: List[dict[str, Any]] = []
    columns: List[str] = []
    for frame in frames:
        if not isinstance(frame, DataFrame):
            raise TypeError("concat expects DataFrame instances")
        if not columns:
            columns = frame.columns
        for _, row in frame.iterrows():
            rows.append({col: row.get(col) for col in frame.columns})
    return DataFrame(rows, columns=columns)


def isna(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


__all__ = ["DataFrame", "Series", "concat", "isna"]
