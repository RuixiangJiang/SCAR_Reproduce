import hashlib
import pandas as pd

def df_md5(df: pd.DataFrame) -> str:
    cols = sorted(df.columns)
    csv_str = df[cols].sort_index().to_csv(
        index=False,
        na_rep="<NA>",
        float_format="%.12g",
        lineterminator="\n",
    )
    return hashlib.md5(csv_str.encode("utf-8")).hexdigest()

import hashlib
import numpy as np

def md5_ndarray_strict(a: np.ndarray, normalize_endian=True) -> str:
    x = a
    if normalize_endian and x.dtype.byteorder in (">", "<"):
        x = x.astype(x.dtype.newbyteorder("<"), copy=False)

    x = np.ascontiguousarray(x)
    h = hashlib.md5()
    h.update(str(x.dtype.str).encode("utf-8"))
    h.update(str(x.shape).encode("utf-8"))
    h.update(x.tobytes())
    return h.hexdigest()
