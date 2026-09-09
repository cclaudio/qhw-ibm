"""Command-line entry points for IBM Quantum raw JSON normalization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from qhw_data.serialize import to_json

from .normalize import normalize_calibration, normalize_coupling
from .normalize import normalize_device, normalize_result


Normalizer = Callable[..., dict[str, Any]]


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="raw IBM Quantum JSON input file")
    parser.add_argument("-o", "--output", help="normalized JSON output file")
    parser.add_argument(
        "--device-id",
        help="site-level logical device id to use in normalized output",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="embed the raw IBM JSON payload in the normalized record",
    )


def _run(argv: list[str] | None, normalizer: Normalizer) -> int:
    parser = argparse.ArgumentParser()
    _add_common_args(parser)
    args = parser.parse_args(argv)

    with Path(args.input).open(encoding="utf-8") as stream:
        raw = json.load(stream)

    normalized = normalizer(
        raw,
        device_id=args.device_id,
        include_raw=args.include_raw,
    )
    output = to_json(normalized, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        sys.stdout.write(output + "\n")
    return 0


def device_main(argv: list[str] | None = None) -> int:
    """Normalize an IBM backend configuration JSON as a device record.

    Args:
        argv: Optional argument list. When omitted, argparse reads
            ``sys.argv``.

    Returns:
        Process return code. Zero means the output was written successfully.
    """
    return _run(argv, normalize_device)


def coupling_main(argv: list[str] | None = None) -> int:
    """Normalize an IBM backend configuration JSON as a coupling record.

    Args:
        argv: Optional argument list. When omitted, argparse reads
            ``sys.argv``.

    Returns:
        Process return code. Zero means the output was written successfully.
    """
    return _run(argv, normalize_coupling)


def calibration_main(argv: list[str] | None = None) -> int:
    """Normalize an IBM backend properties JSON as a calibration record.

    Args:
        argv: Optional argument list. When omitted, argparse reads
            ``sys.argv``.

    Returns:
        Process return code. Zero means the output was written successfully.
    """
    return _run(argv, normalize_calibration)


def result_main(argv: list[str] | None = None) -> int:
    """Normalize an IBM Qiskit result JSON.

    Args:
        argv: Optional argument list. When omitted, argparse reads
            ``sys.argv``.

    Returns:
        Process return code. Zero means the output was written successfully.
    """
    return _run(argv, normalize_result)
