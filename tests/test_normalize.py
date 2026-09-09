"""Tests for qhw_ibm normalizers.

All tests use synthetic payloads that reproduce the shapes IBM Quantum
Platform actually returns, so no IBM credentials or network access are needed.
Schema validation runs inside every builder.build() call, so a passing test
confirms the output matches the qhw-data schemas.
"""

from __future__ import annotations

import pytest

from qhw_ibm import (
    normalize_calibration,
    normalize_coupling,
    normalize_device,
    normalize_result,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

BACKEND_NAME = "ibm_eagle"
DEVICE_ID = "test-ibm-eagle"

# Minimal IBM backend configuration (config API / IBMBackend.configuration())
CONFIG = {
    "backend_name": BACKEND_NAME,
    "backend_version": "1.0.0",
    "n_qubits": 5,
    "basis_gates": ["id", "rz", "sx", "x", "cx", "reset", "measure"],
    "coupling_map": [[0, 1], [1, 0], [1, 2], [2, 1], [2, 3], [3, 2], [3, 4], [4, 3]],
    "open_pulse": False,
    "local": False,
    "simulator": False,
}

# Minimal IBM backend properties (properties API / IBMBackend.properties())
# Each qubit is a list of property dicts; gates carry per-locus parameters.
PROPERTIES = {
    "backend_name": BACKEND_NAME,
    "backend_version": "1.0.0",
    "last_update_date": "2024-01-15T12:00:00Z",
    "qubits": [
        [
            {"name": "T1", "date": "2024-01-15T10:00:00Z", "unit": "µs", "value": 120.5},
            {"name": "T2", "date": "2024-01-15T10:00:00Z", "unit": "µs", "value": 80.3},
            {"name": "frequency", "date": "2024-01-15T10:00:00Z", "unit": "GHz", "value": 5.1},
            {"name": "readout_error", "date": "2024-01-15T10:00:00Z", "unit": "", "value": 0.02},
        ],
        [
            {"name": "T1", "date": "2024-01-15T10:00:00Z", "unit": "µs", "value": 110.0},
            {"name": "T2", "date": "2024-01-15T10:00:00Z", "unit": "µs", "value": 75.0},
            {"name": "readout_error", "date": "2024-01-15T10:00:00Z", "unit": "", "value": 0.03},
        ],
    ],
    "gates": [
        {
            "gate": "cx",
            "qubits": [0, 1],
            "parameters": [
                {"name": "gate_error", "date": "2024-01-15T10:00:00Z", "unit": "", "value": 0.005},
                {"name": "gate_length", "date": "2024-01-15T10:00:00Z", "unit": "ns", "value": 320.0},
            ],
            "name": "cx0_1",
        },
        {
            "gate": "cx",
            "qubits": [1, 0],
            "parameters": [
                {"name": "gate_error", "date": "2024-01-15T10:00:00Z", "unit": "", "value": 0.006},
                {"name": "gate_length", "date": "2024-01-15T10:00:00Z", "unit": "ns", "value": 320.0},
            ],
            "name": "cx1_0",
        },
        {
            "gate": "sx",
            "qubits": [0],
            "parameters": [
                {"name": "gate_error", "date": "2024-01-15T10:00:00Z", "unit": "", "value": 0.001},
                {"name": "gate_length", "date": "2024-01-15T10:00:00Z", "unit": "ns", "value": 35.0},
            ],
            "name": "sx0",
        },
    ],
    "general": [
        {"name": "rep_time", "date": "2024-01-15T10:00:00Z", "unit": "µs", "value": 2000.0},
    ],
}

# ---------------------------------------------------------------------------
# normalize_result fixtures
#
# normalize_result expects the envelope:
#   {"device": {"raw_configuration": <config>}, "job": <job>, "raw_results": <results>}
#
# raw_results["results"][0]["data"] holds per-register SamplerV2 blocks:
#   {"<reg>": {"samples": [...], "num_bits": <n>}}
# ---------------------------------------------------------------------------

def _make_result_raw(data, *, job_status="completed", job_id="job-xyz-456",
                     backend_name=BACKEND_NAME):
    """Build a normalize_result envelope from a data block."""
    return {
        "device": {
            "raw_configuration": {
                "backend_name": backend_name,
                "backend_version": "1.0.0",
                "n_qubits": 5,
            }
        },
        "job": {"id": job_id, "status": job_status},
        "raw_results": {
            "results": [{"data": data}],
        },
    }


# Single register "meas" — Bell-state-like: 512× |00⟩, 512× |11⟩
_BELL_DATA = {
    "meas": {"samples": [0] * 512 + [3] * 512, "num_bits": 2},
}
QISKIT_RESULT = _make_result_raw(_BELL_DATA)


# ---------------------------------------------------------------------------
# normalize_device
# ---------------------------------------------------------------------------

class TestNormalizeDevice:
    def test_schema_tag(self):
        rec = normalize_device(CONFIG)
        assert rec["schema"] == "qhw-device-v1"

    def test_provider(self):
        rec = normalize_device(CONFIG)
        assert rec["provider"] == "ibm"

    def test_device_id_from_backend_name(self):
        rec = normalize_device(CONFIG)
        assert rec["device"]["id"] == BACKEND_NAME

    def test_device_id_override(self):
        rec = normalize_device(CONFIG, device_id=DEVICE_ID)
        assert rec["device"]["id"] == DEVICE_ID

    def test_provider_device_id_preserved(self):
        rec = normalize_device(CONFIG, device_id=DEVICE_ID)
        assert rec["device"]["provider_device_id"] == BACKEND_NAME

    def test_num_qubits(self):
        rec = normalize_device(CONFIG)
        assert rec["device"]["num_qubits"] == 5

    def test_qubit_count(self):
        rec = normalize_device(CONFIG)
        assert len(rec["qubits"]) == 5

    def test_qubit_ids_are_strings(self):
        rec = normalize_device(CONFIG)
        ids = [q["id"] for q in rec["qubits"]]
        assert ids == ["0", "1", "2", "3", "4"]

    def test_technology(self):
        rec = normalize_device(CONFIG)
        assert rec["device"]["technology"] == "superconducting"

    def test_version(self):
        rec = normalize_device(CONFIG)
        assert rec["device"]["version"] == "1.0.0"

    def test_basis_gates_in_metadata(self):
        rec = normalize_device(CONFIG)
        assert "cx" in rec["metadata"]["basis_gates"]

    def test_include_raw(self):
        rec = normalize_device(CONFIG, include_raw=True)
        assert rec["raw"]["included"] is True

    def test_no_raw_by_default(self):
        rec = normalize_device(CONFIG)
        assert rec["raw"]["included"] is False

    def test_name_field_alias(self):
        raw = {**CONFIG, "name": "ibm_falcon"}
        raw.pop("backend_name", None)
        rec = normalize_device(raw)
        assert rec["device"]["id"] == "ibm_falcon"

    def test_empty_config(self):
        # Should produce a minimal but schema-valid record.
        rec = normalize_device({})
        assert rec["schema"] == "qhw-device-v1"
        assert rec["provider"] == "ibm"


# ---------------------------------------------------------------------------
# normalize_coupling
# ---------------------------------------------------------------------------

class TestNormalizeCoupling:
    def test_schema_tag(self):
        rec = normalize_coupling(CONFIG)
        assert rec["schema"] == "qhw-coupling-v1"

    def test_provider(self):
        rec = normalize_coupling(CONFIG)
        assert rec["provider"] == "ibm"

    def test_directed_graph(self):
        rec = normalize_coupling(CONFIG)
        assert rec["coupling"]["directed"] is True

    def test_nodes(self):
        rec = normalize_coupling(CONFIG)
        assert rec["coupling"]["nodes"] == ["0", "1", "2", "3", "4"]

    def test_edges_count(self):
        # 8 directed pairs in CONFIG.coupling_map, all unique.
        rec = normalize_coupling(CONFIG)
        assert len(rec["coupling"]["edges"]) == 8

    def test_edge_format(self):
        rec = normalize_coupling(CONFIG)
        for edge in rec["coupling"]["edges"]:
            assert len(edge) == 2
            assert all(isinstance(x, str) for x in edge)

    def test_coupling_source(self):
        rec = normalize_coupling(CONFIG)
        assert "coupling_map" in rec["coupling"]["source"]

    def test_cx_operation_present(self):
        rec = normalize_coupling(CONFIG)
        names = [op["name"] for op in rec["operations"]]
        assert "cx" in names

    def test_cx_arity_2(self):
        rec = normalize_coupling(CONFIG)
        cx = next(op for op in rec["operations"] if op["name"] == "cx")
        assert cx["arity"] == 2

    def test_sx_arity_1(self):
        rec = normalize_coupling(CONFIG)
        sx = next(op for op in rec["operations"] if op["name"] == "sx")
        assert sx["arity"] == 1

    def test_device_id_override(self):
        rec = normalize_coupling(CONFIG, device_id=DEVICE_ID)
        assert rec["device"]["id"] == DEVICE_ID

    def test_no_coupling_map(self):
        raw = {**CONFIG, "coupling_map": []}
        rec = normalize_coupling(raw)
        assert rec["coupling"]["edges"] == []


# ---------------------------------------------------------------------------
# normalize_calibration
# ---------------------------------------------------------------------------

class TestNormalizeCalibration:
    def test_schema_tag(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["schema"] == "qhw-calibration-v1"

    def test_provider(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["provider"] == "ibm"

    def test_device_id_from_backend_name(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["device"]["id"] == BACKEND_NAME

    def test_timestamp(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["calibration"]["timestamp"] == "2024-01-15T12:00:00Z"

    def test_observation_count_equals_qubit_count(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["calibration"]["observation_count"] == 2

    def test_quality_metric_count_equals_gate_entries(self):
        rec = normalize_calibration(PROPERTIES)
        assert rec["calibration"]["quality_metric_count"] == 3

    def test_ibm_extension_present(self):
        rec = normalize_calibration(PROPERTIES)
        assert "ibm.v1" in rec["extensions"]

    def test_extension_qubits_preserved(self):
        rec = normalize_calibration(PROPERTIES)
        assert len(rec["extensions"]["ibm.v1"]["qubits"]) == 2

    def test_extension_gates_preserved(self):
        rec = normalize_calibration(PROPERTIES)
        assert len(rec["extensions"]["ibm.v1"]["gates"]) == 3

    def test_extension_general_preserved(self):
        rec = normalize_calibration(PROPERTIES)
        assert len(rec["extensions"]["ibm.v1"]["general"]) == 1

    def test_gate_names_in_summaries(self):
        rec = normalize_calibration(PROPERTIES)
        assert "cx" in rec["calibration"]["summaries"]["gate_names_present"]
        assert "sx" in rec["calibration"]["summaries"]["gate_names_present"]

    def test_qubit_metrics_in_summaries(self):
        rec = normalize_calibration(PROPERTIES)
        assert "T1" in rec["calibration"]["summaries"]["qubit_metrics_present"]
        assert "T2" in rec["calibration"]["summaries"]["qubit_metrics_present"]

    def test_device_id_override(self):
        rec = normalize_calibration(PROPERTIES, device_id=DEVICE_ID)
        assert rec["device"]["id"] == DEVICE_ID

    def test_empty_properties(self):
        rec = normalize_calibration({})
        assert rec["schema"] == "qhw-calibration-v1"


# ---------------------------------------------------------------------------
# normalize_result
# ---------------------------------------------------------------------------

class TestNormalizeResult:
    def test_schema_tag(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["schema"] == "qhw-result-v1"

    def test_provider(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["provider"] == "ibm"

    def test_device_id_from_backend_name(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["device"]["id"] == BACKEND_NAME

    def test_device_id_override(self):
        rec = normalize_result(QISKIT_RESULT, device_id=DEVICE_ID)
        assert rec["device"]["id"] == DEVICE_ID

    def test_job_id(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["job"]["id"] == "job-xyz-456"

    def test_job_status_completed(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["job"]["status"] == "completed"

    def test_job_status_failed(self):
        raw = _make_result_raw(_BELL_DATA, job_status="failed")
        rec = normalize_result(raw)
        assert rec["job"]["status"] == "failed"

    def test_shots(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["result"]["shots"] == 1024

    def test_num_circuits(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["result"]["num_circuits"] == 1

    def test_success_flag(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["result"]["success"] is True

    def test_single_register_counts(self):
        rec = normalize_result(QISKIT_RESULT)
        counts = rec["result"]["counts"]
        assert set(counts.keys()) == {"00", "11"}
        assert counts["00"] == 512
        assert counts["11"] == 512

    def test_counts_sum_equals_shots(self):
        rec = normalize_result(QISKIT_RESULT)
        counts = rec["result"]["counts"]
        assert sum(counts.values()) == 1024

    def test_include_raw(self):
        rec = normalize_result(QISKIT_RESULT, include_raw=True)
        assert rec["raw"]["included"] is True

    def test_no_raw_by_default(self):
        rec = normalize_result(QISKIT_RESULT)
        assert rec["raw"]["included"] is False

    def test_empty_result(self):
        rec = normalize_result(_make_result_raw({}))
        assert rec["schema"] == "qhw-result-v1"

    # -----------------------------------------------------------------------
    # Multi-register join tests (the bug being fixed)
    # -----------------------------------------------------------------------

    def test_bug1_unused_register_not_selected(self):
        # QuantumCircuit(3, 3) + measure_all produces two registers:
        # 'c' (the pre-existing 3-bit classical reg, never written → all zeros)
        # 'meas' (added by measure_all, qubit 0 flipped → value 1 every shot).
        # The old code returned {'000': 1000} from 'c' (first register).
        # The fixed code joins both: '001' (meas) + '000' (c) = '001 000'.
        data = {
            "c":    {"samples": [0] * 1000, "num_bits": 3},
            "meas": {"samples": [1] * 1000, "num_bits": 3},
        }
        rec = normalize_result(_make_result_raw(data))
        counts = rec["result"]["counts"]
        # Joined in reverse declaration order: meas (MSB) then c (LSB)
        assert counts == {"001 000": 1000}

    def test_bug2_multi_register_join(self):
        # Registers a (2 bits, declared first) and b (1 bit, declared second).
        # Qubit 2 → b[0] is flipped; a stays 0.
        # Old code: {'00': 1000} (only 'a').  Fixed: {'1 00': 1000}.
        data = {
            "a": {"samples": [0] * 1000, "num_bits": 2},
            "b": {"samples": [1] * 1000, "num_bits": 1},
        }
        rec = normalize_result(_make_result_raw(data))
        counts = rec["result"]["counts"]
        assert counts == {"1 00": 1000}

    def test_multi_register_shots_inferred_correctly(self):
        data = {
            "a": {"samples": [0] * 1000, "num_bits": 2},
            "b": {"samples": [1] * 1000, "num_bits": 1},
        }
        rec = normalize_result(_make_result_raw(data))
        assert rec["result"]["shots"] == 1000

    def test_single_register_passthrough_unchanged(self):
        # A circuit with one register must not get a space-separated key.
        data = {"meas": {"samples": [0] * 500 + [3] * 500, "num_bits": 2}}
        rec = normalize_result(_make_result_raw(data))
        counts = rec["result"]["counts"]
        assert " " not in next(iter(counts))
        assert set(counts) == {"00", "11"}

    def test_real_hardware_payload_three_registers(self):
        # Samples taken verbatim from ibm-run-circuit-qrmi-result.json
        # (10-shot run, 3 registers × 3 bits, hex-encoded samples).
        # Expected keys computed by zipping every shot across registers in
        # reverse declaration order (c2=MSB, c0=LSB), space-separated —
        # the same rule as Qiskit V1 Result.get_counts() for multi-register
        # circuits.  Cross-checked shot-by-shot against Qiskit BitArray (get_counts)
        data = {
            "c0": {
                "samples": ["0x6","0x0","0x0","0x5","0x5","0x4","0x5","0x1","0x7","0x5"],
                "num_bits": 3,
            },
            "c1": {
                "samples": ["0x2","0x1","0x5","0x7","0x4","0x3","0x2","0x4","0x0","0x7"],
                "num_bits": 3,
            },
            "c2": {
                "samples": ["0x2","0x1","0x2","0x6","0x3","0x6","0x2","0x5","0x0","0x0"],
                "num_bits": 3,
            },
        }
        expected = {
            "010 010 110": 1,   # shot 0:  c0=0x6=110  c1=0x2=010  c2=0x2=010
            "001 001 000": 1,   # shot 1:  c0=0x0=000  c1=0x1=001  c2=0x1=001
            "010 101 000": 1,   # shot 2:  c0=0x0=000  c1=0x5=101  c2=0x2=010
            "110 111 101": 1,   # shot 3:  c0=0x5=101  c1=0x7=111  c2=0x6=110
            "011 100 101": 1,   # shot 4:  c0=0x5=101  c1=0x4=100  c2=0x3=011
            "110 011 100": 1,   # shot 5:  c0=0x4=100  c1=0x3=011  c2=0x6=110
            "010 010 101": 1,   # shot 6:  c0=0x5=101  c1=0x2=010  c2=0x2=010
            "101 100 001": 1,   # shot 7:  c0=0x1=001  c1=0x4=100  c2=0x5=101
            "000 000 111": 1,   # shot 8:  c0=0x7=111  c1=0x0=000  c2=0x0=000
            "000 111 101": 1,   # shot 9:  c0=0x5=101  c1=0x7=111  c2=0x0=000
        }
        rec = normalize_result(_make_result_raw(data))
        assert rec["result"]["counts"] == expected
        assert rec["result"]["shots"] == 10
