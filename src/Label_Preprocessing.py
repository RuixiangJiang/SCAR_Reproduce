leaky_module = {
    "train": [
        ("subbytes", "s_box"),
        ("invsubbytes", "is_box"),
        ("subword", "s_box"),
        ("MixColumn",),
    ],
    "AES_PPRM1": [
        ("SBOX",),
        ("Mixcolumn",),
        ("MX",),
        ("sb",)
    ],
    "AES_PPRM3": [
        ("Sbox",),
        ("Mixcolumn",),
        ("MX",),
    ],
    "AES_TBL": [
        ("SBOX",),
        ("Mixcolumn",),
        ("MX",),
        ("EC", "sb",),
        ("EC", "di",),
        ("EC", "ki"),
        ("EC", "so"),
    ],
    "RSA": [
        ("MODEXP_SEQ",),
        ("MULT_BLK",),
    ],
    "SABER": [
        ("sa",),
        (":",),
    ],
    "PRESENT": [
        ("SBOX",),
    ]
}

def label(Feature, design):
    def contains_any(value, keyword_tuples):
        return int(
            any(all(kw.lower() in str(value).lower() for kw in kws) for kws in keyword_tuples)
        )

    for node in Feature.keys():
        Feature[node]["label"] = contains_any(
            Feature[node]["Node"],
            leaky_module.get(design, [])
        )