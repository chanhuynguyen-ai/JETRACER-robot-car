from typing import Any, Dict


def _coerce_value(key: str, value: str) -> Any:
    key = key.upper()

    if key in {"ESTOP", "PCA"}:
        return value == "1"

    try:
        return int(value)
    except ValueError:
        return value.upper()


def _parse_kv_payload(payload: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    for token in payload.split():
        if "=" not in token:
            continue

        k, v = token.split("=", 1)
        result[k.lower()] = _coerce_value(k, v)

    return result


def parse_line(line: str) -> Dict[str, Any]:
    line = line.strip()

    if not line:
        return {"type": "empty"}

    if line.startswith("STATUS "):
        return {"type": "status", **_parse_kv_payload(line[7:])}

    if line.startswith("TEL "):
        return {"type": "telemetry", **_parse_kv_payload(line[4:])}

    if line.startswith("ACK "):
        return {"type": "ack", "message": line[4:]}

    if line.startswith("ERR "):
        return {"type": "error", "message": line[4:]}

    if line.startswith("BOOT "):
        return {"type": "boot", "message": line[5:]}

    if line == "PONG":
        return {"type": "pong"}

    return {"type": "raw", "message": line}