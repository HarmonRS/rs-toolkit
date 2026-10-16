from __future__ import annotations

import re
from pathlib import Path

from gf3_l1a2l2.errors import RpcError


RPC_KEY_MAP = {
    "errBias": "ERR_BIAS",
    "errRand": "ERR_RAND",
    "lineOffset": "LINE_OFF",
    "sampOffset": "SAMP_OFF",
    "latOffset": "LAT_OFF",
    "longOffset": "LONG_OFF",
    "heightOffset": "HEIGHT_OFF",
    "lineScale": "LINE_SCALE",
    "sampScale": "SAMP_SCALE",
    "latScale": "LAT_SCALE",
    "longScale": "LONG_SCALE",
    "heightScale": "HEIGHT_SCALE",
    "lineNumCoef": "LINE_NUM_COEFF",
    "lineDenCoef": "LINE_DEN_COEFF",
    "sampNumCoef": "SAMP_NUM_COEFF",
    "sampDenCoef": "SAMP_DEN_COEFF",
}

COEFFICIENT_KEYS = {
    "lineNumCoef",
    "lineDenCoef",
    "sampNumCoef",
    "sampDenCoef",
}


def read_rpc_metadata(rpc_path: Path | str) -> dict[str, str]:
    path = Path(rpc_path)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise RpcError(f"Cannot read RPC file: {path}") from exc

    metadata: dict[str, str] = {}
    missing: list[str] = []
    for source_key, target_key in RPC_KEY_MAP.items():
        value = _find_rpc_value(text, source_key)
        if value is None:
            missing.append(source_key)
            continue
        metadata[target_key] = _normalize_rpc_value(source_key, value)

    if missing:
        raise RpcError(f"RPC file {path} is missing fields: {', '.join(missing)}")

    return metadata


def _find_rpc_value(text: str, key: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(key)}\b\s*[:=]?\s*(.*?);", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)


def _normalize_rpc_value(key: str, raw_value: str) -> str:
    value = raw_value.strip().strip("=")
    if key in COEFFICIENT_KEYS:
        value = value.replace("(", " ").replace(")", " ").replace(",", " ")
    return " ".join(value.split())
