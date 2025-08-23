import hashlib
from pathlib import Path
import pandas as pd

CACHE_ROOT = Path(__file__).resolve().parents[1] / "data_cache"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

def _hash_key(key_parts: dict) -> str:
    s = "|".join(f"{k}={v}" for k, v in sorted(key_parts.items()))
    return hashlib.sha256(s.encode()).hexdigest()[:16]

def cache_path(prefix: str, key_parts: dict) -> Path:
    return CACHE_ROOT / f"{prefix}-{_hash_key(key_parts)}.parquet"

def get_cached_df(prefix: str, key_parts: dict) -> pd.DataFrame | None:
    p = cache_path(prefix, key_parts)
    if p.exists():
        return pd.read_parquet(p)
    return None

def set_cached_df(prefix: str, key_parts: dict, df: pd.DataFrame) -> Path:
    p = cache_path(prefix, key_parts)
    df.to_parquet(p, index=True)
    return p

def export_dir() -> Path:
    d = CACHE_ROOT / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d
