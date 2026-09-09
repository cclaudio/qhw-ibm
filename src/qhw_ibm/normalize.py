"""Normalize raw IBM Quantum Platform JSON payloads into qhw-data schemas.

This module is a data adapter. It does not call IBM Quantum APIs, submit jobs,
or fetch calibration data. Callers pass dictionaries already collected from
IBM-facing tools (qiskit-ibm-runtime, or the IBM Quantum REST API directly),
and the functions return provider-neutral ``qhw-data`` dictionaries.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from qhw_data import new_calibration, new_coupling, new_device, new_result

PROVIDER = "ibm"
DEFAULT_TECHNOLOGY = "superconducting"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_device(raw: dict[str, Any], *, device_id: str | None = None,
                     include_raw: bool = False) -> dict[str, Any]:
    """Normalize an IBM backend configuration dict into ``qhw-device-v1``.

    Args:
        raw: IBM backend configuration dictionary. Accepted shape is the
             ``/v1/backends/{backend_name}/configuration`` REST response,
             which is the same as qrmi.target()["configuration"].
        device_id: Optional site-level logical device ID. When omitted, the
                   raw["backend_name"] field is used.
        include_raw: Embed the full raw input under ``raw.payload``.

    Returns:
        A validated ``qhw-device-v1`` dictionary.
    """
    provider_device_id = _backend_name(raw)
    normalized_id = device_id or provider_device_id or "ibm-device"
    name = provider_device_id or normalized_id

    qubits = _qubit_ids(raw)
    num_qubits = len(qubits) or _n_qubits(raw)
    version = _backend_version(raw)

    builder = (
        new_device(PROVIDER, normalized_id, num_qubits=num_qubits)
        .device(
            normalized_id,
            name=name,
            version=version,
            num_qubits=num_qubits,
            technology=DEFAULT_TECHNOLOGY,
            provider_device_id=provider_device_id,
        )
        .qubits(qubits)
        .metadata({
            "processor_type": raw.get("processor_type") or {},
            "basis_gates": raw.get("basis_gates") or [],
            "simulator": raw.get("simulator"),
        })
        .extension("ibm.v1", {
            "open_pulse": raw.get("open_pulse"),
            "local": raw.get("local"),
            "supported_features": raw.get("supported_features") or [],
            "supported_instructions": raw.get("supported_instructions") or [],
        })
    )
    if include_raw:
        builder.raw_payload(raw, format="ibm-backend-config-json")
    return builder.build()


def normalize_coupling(raw: dict[str, Any], *, device_id: str | None = None,
                       include_raw: bool = False) -> dict[str, Any]:
    """Normalize an IBM backend configuration dict into ``qhw-coupling-v1``.

    Args:
        raw: IBM backend configuration dictionary. Accepted shape is the
             ``/v1/backends/{backend_name}/configuration`` REST response,
             which is the same as qrmi.target()["configuration"].
             The normalizer reads ``coupling_map`` (list of [control, target]
             index pairs) and ``basis_gates`` for the operations list.
        device_id: Optional site-level logical device ID.
        include_raw: Embed the full raw input under ``raw.payload``.

    Returns:
        A validated ``qhw-coupling-v1`` dictionary.
    """
    provider_device_id = _backend_name(raw)
    normalized_id = device_id or provider_device_id or "ibm-device"
    name = provider_device_id or normalized_id

    qubits = _qubit_ids(raw)
    num_qubits = len(qubits) or _n_qubits(raw)
    edges, sources = _coupling_edges(raw, num_qubits)

    builder = (
        new_coupling(
            PROVIDER,
            normalized_id,
            device_name=name,
            num_qubits=num_qubits,
            directed=True,
        )
        .nodes(qubits)
        .coupling(edges, directed=True, nodes=qubits, source=sources)
        .metadata({
            "processor_type": raw.get("processor_type") or {},
            "basis_gates": raw.get("basis_gates") or [],
        })
    )

    for gate_name in sorted(raw.get("basis_gates") or []):
        # IBM coupling_map lists 2-qubit edges; single-qubit gates apply to
        # every qubit. Gate loci cannot be determined from config alone (that
        # data lives in properties), so we record the gate with no loci —
        # call normalize_coupling with a properties payload to get loci.
        arity = _gate_arity_hint(gate_name)
        if arity == 2:
            loci = [[str(a), str(b)] for a, b in _raw_edges(raw)]
        elif arity == 1:
            loci = [[q] for q in qubits]
        else:
            loci = []
        builder.operation(gate_name, arity, supported_loci=loci or None)

    if include_raw:
        builder.raw_payload(raw, format="ibm-backend-config-json")
    return builder.build()


def normalize_calibration(raw: dict[str, Any], *,
                          device_id: str | None = None,
                          include_raw: bool = False) -> dict[str, Any]:
    """Normalize an IBM backend properties dict into ``qhw-calibration-v1``.

    Args:
        raw: IBM backend properties dictionary. Accepted shape is the
            ``/v1/backends/{backend_name}/properties`` REST response,
            which is the same as qrmi.target()["properties"].
        device_id: Optional site-level logical device ID.
        include_raw: Embed the full raw input under ``raw.payload``.

    Returns:
        A validated ``qhw-calibration-v1`` dictionary.

    Notes:
        Core schema fields carry identity and counts. Full IBM qubit and gate
        calibration data are preserved under ``extensions["ibm.v1"]`` so a
        consumer that understands the IBM shape can access every value while a
        generic consumer sees the standardised record.
    """
    provider_device_id = _backend_name(raw)
    normalized_id = device_id or provider_device_id or "ibm-device"
    name = provider_device_id or normalized_id

    timestamp = raw.get("last_update_date")
    qubits_data = raw.get("qubits") or []
    gates_data = raw.get("gates") or []

    qubit_count = len(qubits_data) or _n_qubits(raw)
    gate_locus_count = len(gates_data)

    # Summaries: which scalar qubit metrics are present and the gate names.
    qubit_metrics_present = sorted({
        prop.get("name")
        for qubit in qubits_data
        for prop in (qubit if isinstance(qubit, list) else [])
        if isinstance(prop, dict) and prop.get("name")
    })
    gate_names_present = sorted({
        g.get("gate") for g in gates_data
        if isinstance(g, dict) and g.get("gate")
    })

    builder = (
        new_calibration(
            PROVIDER,
            normalized_id,
            device_name=name,
            num_qubits=qubit_count,
        )
        .calibration(
            timestamp=timestamp,
            observation_count=qubit_count,
            quality_metric_count=gate_locus_count,
        )
        .summaries({
            "qubit_metrics_present": qubit_metrics_present,
            "gate_names_present": gate_names_present,
            "qubit_count": qubit_count,
            "gate_locus_count": gate_locus_count,
        })
        .extension("ibm.v1", {
            "qubits": qubits_data,
            "gates": gates_data,
            "general": raw.get("general") or [],
            "last_update_date": timestamp,
        })
    )
    if include_raw:
        builder.raw_payload(raw, format="ibm-backend-properties-json")
    return builder.build()


def normalize_result(raw: dict[str, Any], *, device_id: str | None = None,
                     include_raw: bool = False) -> dict[str, Any]:
    """Normalize an IBM Qiskit result dict into ``qhw-result-v1``.

    Args:
        raw: Custom JSON
            {
               "device": {
                   "raw_configuration": <config_json>
                },
                "job": self.last_job,
                "raw_results": <result_json>
            }
            Where:
              - <config_json> = Backend configuration JSON
                               (`/v1/backends/{backend_name}/configuration` or
                                `qrmi.target()["configuration"]`)
              - job = same format as defined in the QFw qrmi_driver.last_job
              - <result_json> = JSON returned by `qrmi.task_result()
        device_id: Optional site-level logical device ID. When omitted the
                   ``backend_name`` field is used.
        include_raw: Embed the full raw input under ``raw.payload``.

    Returns:
        A validated ``qhw-result-v1`` dictionary.
    """
    raw_device_config = raw.get("device", {}).get("raw_configuration", {})
    provider_device_id = _backend_name(raw_device_config)
    version = raw_device_config.get("backend_version")
    num_qubits = _n_qubits(raw_device_config)
    normalized_id = device_id or provider_device_id or "ibm-device"

    raw_job = raw.get("job") or {}
    job_id = raw_job.get("id")
    job_status = raw_job.get("status")
    success = True if job_status == "completed" else False

    raw_results = raw.get("raw_results") or {}
    execution_spans = raw_results.get("metadata", {}).get("execution", {}).get("execution_spans") or []
    timestamps = execution_spans[0] if execution_spans else []
    qpu_start = timestamps[0].get("date") if len(timestamps) > 0 else None
    qpu_stop = timestamps[1].get("date") if len(timestamps) > 1 else None

    results = raw_results.get("results") or []
    data = results[0].get("data") if results else {}
    counts = _get_counts(data)
    shots = _infer_shots(counts)
    num_circuits = len(results)

    builder = (
        new_result(PROVIDER, normalized_id, job_status=job_status)
        .device(
            normalized_id,
            name=provider_device_id,
            provider=PROVIDER,
            num_qubits=num_qubits,
            version=version,
        )
        .job(
            id=job_id,
            status=job_status,
            provider_status=job_status,
        )
        .result(
            shots=shots,
            num_circuits=num_circuits,
            counts=counts,
            success=success,
        )
    )

    if qpu_start and qpu_stop:
        builder.timestamp("execution_started_at", qpu_start)
        builder.timestamp("execution_ended_at", qpu_stop)

    if include_raw:
        builder.raw_payload(raw_results, format="ibm-qiskit-result-json")

    return builder.build()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sample_to_int(s: Any) -> int:
    """Convert a raw sample value to int, accepting hex strings like ``"0x2"``."""
    if isinstance(s, int):
        return s
    k = str(s).strip()
    if k.startswith(("0x", "0X")):
        return int(k, 16)
    if k.startswith(("0b", "0B")):
        return int(k, 2)
    return int(k)


def _get_counts(data: dict[str, Any] | None) -> dict[str, int] | None:
    """Return combined shot counts from a SamplerV2 result data block.

    Each register entry in *data* has the shape::

        {"samples": [...], "num_bits": <int>}

    where ``samples`` is a list of raw integer shot values and ``num_bits`` is
    the classical register width.

    When *data* contains a single register the counts are returned directly,
    with each sample formatted as ``bin(val)[2:].zfill(num_bits)``.

    When *data* contains multiple registers they are joined per-shot in
    **reverse declaration order** (last-declared register = most-significant
    bits), space-separated — matching the behaviour of Qiskit V1
    ``Result.get_counts()`` for circuits with multiple classical registers.
    For example, registers ``a`` (2 bits, declared first) and ``b`` (1 bit,
    declared second) are joined as ``"<b_bits> <a_bits>"``.

    Args:
        data: The ``data`` dict from a single result entry, e.g.
              ``raw_results["results"][0]["data"]``.  Keys are register names
              in declaration order; values are dicts with ``samples`` and
              ``num_bits``.

    Returns:
        A ``{"<bitstring>": <count>, ...}`` dict, or ``None`` when *data* is
        absent or contains no registers with samples.
    """
    from collections import Counter

    if not isinstance(data, dict):
        return None

    # Collect (samples_as_ints, num_bits) in declaration order, skipping
    # registers that carry no samples.
    regs: list[tuple[list[int], int]] = []
    for reg_data in data.values():
        if not isinstance(reg_data, dict):
            continue
        samples = reg_data.get("samples")
        if not samples:
            continue
        num_bits: int = int(reg_data.get("num_bits") or 1)
        regs.append(([_sample_to_int(s) for s in samples], num_bits))

    if not regs:
        return None

    if len(regs) == 1:
        samples, num_bits = regs[0]
        return dict(Counter(bin(v)[2:].zfill(num_bits) for v in samples))

    # Multi-register: zip per-shot, reverse for MSB-first, space-separated.
    combined: Counter[str] = Counter()
    for shot_vals in zip(*(s for s, _ in regs)):
        parts = [
            bin(v)[2:].zfill(nb)
            for v, nb in zip(reversed(shot_vals), (nb for _, nb in reversed(regs)))
        ]
        combined[" ".join(parts)] += 1
    return dict(combined)

def _backend_name(raw: dict[str, Any]) -> str | None:
    return raw.get("backend_name") or raw.get("name")


def _backend_version(raw: dict[str, Any]) -> str | None:
    return raw.get("backend_version") or raw.get("version")


def _n_qubits(raw: dict[str, Any]) -> int | None:
    v = raw.get("n_qubits") or raw.get("num_qubits")
    return int(v) if v is not None else None


def _qubit_ids(raw: dict[str, Any]) -> list[str]:
    # IBM qubits are referenced by integer index (0, 1, 2, ...).
    # Build canonical string IDs from n_qubits when explicit qubit data is
    # absent (config payloads), or from the length of the qubits array
    # (properties payloads).
    qubits_data = raw.get("qubits")
    if qubits_data:
        return [str(i) for i in range(len(qubits_data))]
    n = _n_qubits(raw)
    if n:
        return [str(i) for i in range(n)]
    return []


def _raw_edges(raw: dict[str, Any]) -> list[list[int]]:
    cmap = raw.get("coupling_map")
    if not cmap:
        return []
    return [[int(a), int(b)] for a, b in cmap if len(list(a for a in [a, b])) == 2]


def _coupling_edges(
        raw: dict[str, Any],
        num_qubits: int | None,
) -> tuple[list[list[str]], list[str]]:
    raw_edges = _raw_edges(raw)
    if not raw_edges:
        return [], []
    edges = _unique_edges([[str(a), str(b)] for a, b in raw_edges])
    return edges, ["coupling_map"]


def _gate_arity_hint(gate_name: str) -> int:
    # Best-effort arity from the IBM standard basis gate set; anything
    # unrecognised defaults to 1.
    _TWO_QUBIT = {"cx", "cz", "ecr", "rzz", "rxx", "ryy", "swap",
                  "iswap", "dcx", "ch", "crx", "cry", "crz", "cp",
                  "cu", "cu1", "cu3", "csx"}
    _THREE_QUBIT = {"ccx", "cswap"}
    name = gate_name.lower()
    if name in _THREE_QUBIT:
        return 3
    if name in _TWO_QUBIT:
        return 2
    return 1


def _unique_edges(edges: Iterable[Iterable[str]]) -> list[list[str]]:
    # IBM coupling_map is directed; preserve direction but deduplicate.
    # Sort edges in natural numerical order (e.g. [0, 1], [0, 2], [0, 10]) rather than
    # lexical order (e.g. [0, 1], [0, 10], [0, 2]), that also allow reproducible
    # serialization
    seen: set[tuple[str, str]] = set()
    unique: list[list[str]] = []
    for edge in edges:
        pair = [str(item) for item in edge]
        if len(pair) != 2:
            continue
        key = (pair[0], pair[1])
        if key not in seen:
            seen.add(key)
            unique.append(pair)
    return sorted(unique, key=lambda e: (_int_key(e[0]), _int_key(e[1])))


def _infer_shots(counts: dict[str, int] | None) -> int | None:
    if isinstance(counts, dict) and counts:
        return sum(counts.values())
    return None


def _int_key(value: str) -> tuple[int, str]:
    # Natural sort for qubit-index strings ("0", "1", "10" ...).
    try:
        return (int(value), "")
    except ValueError:
        return (0, value)
