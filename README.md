# qhw-ibm

Provider-specific IBM Quantum Platform normalizers for `qhw-data`.

This package does not talk to the IBM Quantum API. It accepts raw JSON payloads
already collected from IBM-facing tools and converts them into the
provider-neutral schemas defined by `qhw-data`.

The package is intentionally a data adapter, not an IBM client wrapper. It does
not submit jobs, authenticate to IBM, or fetch calibration data. Other tools
collect raw IBM JSON first, then call this package to normalize it.

## API

`qhw-ibm` maps IBM Quantum Platform native payloads into four generic
`qhw-data` schemas.

The normalizers accept an optional logical `device_id`. This lets a site use a stable name such as `ornl-ibm-eagle` while still preserving IBM's backend name as `provider_device_id`.

The details of accepted payload shapes and parameter meanings are documented in
`src/qhw_ibm/normalize.py`.

| API | Accpeted payload (parameter raw) | Output / Normalized schema | Notes |
| --- | --- | --- | --- |
| `normalize_device(raw, device_id=None, include_raw=False)` | Backend configuration JSON<br> (`/v1/backends/{backend_name}/configuration` or `qrmi.target()["configuration"]`) | `qhw-device-v1` | Uses `backend_name` as `provider_device_id`, derives qubit IDs from `n_qubits`, preserves `basis_gates`, `open_pulse`, and `simulator` flags in metadata. |
| `normalize_coupling(raw, device_id=None, include_raw=False)` | Backend configuration JSON<br> (`/v1/backends/{backend_name}/configuration` or `qrmi.target()["configuration"]`) | `qhw-coupling-v1` | Reads `coupling_map` (directed [control, target] pairs) for the connectivity graph; maps `basis_gates` into the operations list with best-effort arity. |
| `normalize_calibration(raw, device_id=None, include_raw=False)` | Backend properties JSON <br> (`/v1/backends/{backend_name}/properties` or `qrmi.target()["properties"]`) | `qhw-calibration-v1` | Stores timestamp, qubit count, and gate-locus count in the core record; full IBM `qubits`, `gates`, and `general` arrays are preserved under `extensions["ibm.v1"]`. |
| `normalize_result(raw, device_id=None, include_raw=False)` | Custom JSON <br> <pre>{<br>  "device": { <br>     "raw_configuration": CONFIG_JSON<br>  },<br>  "job": <LAST_JOB_JSON>,<br>  "raw_results": RESULT_JSON<br>}</pre> Where:<br>- **CONFIG_JSON** = Backend configuration JSON (`/v1/backends/{backend_name}/configuration` or `qrmi.target()["configuration"]`)<br>- **LAST_JOB_JSON** = QFw qrmi_driver.last_job <br>- **RESULT_JSON** = JSON returned by `qrmi.task_result()` | `qhw-result-v1` | Maps counts (hex → binary bitstring), shots, job id, and success flag; full Qiskit `results` array is preserved under `extensions["ibm.qiskit.v1"]`. |

## Example

```python
import json
from pathlib import Path

from qhw_ibm import normalize_result

raw = json.loads(Path("result.raw.json").read_text())
normalized = normalize_result(raw, device_id="ornl-ibm-eagle")
```

## Command-Line Tools

```bash
qhw-ibm-device   backend_config.raw.json    --output device.json
qhw-ibm-coupling backend_config.raw.json    --output coupling.json
qhw-ibm-calibration backend_props.raw.json  --output calibration.json
qhw-ibm-result   result.raw.json            --output result.json
```

Use `--device-id` when the site has a stable logical device name that is
different from IBM's backend name.

Use `--include-raw` only when the normalized file should embed the raw IBM
payload. Otherwise keep the raw file as a sibling artifact.

The commands write normalized JSON to stdout unless `--output` is supplied.
