leaky_module = {
    "train": [" s_box", "subbytes", "sb", "MixColumn"],
    "AES_PPRM1": ["SBOX", "Mixcolumns", "MX"],
    "AES_PPRM3": ["Sbox", "Mixcolumns", "MX"],
    "AES_TBL": ["SBOX", "Mixcolumns", "MX"],
    "RSA": ["MODEXP_SEQ", "MULT_BLK"],
    "SABER": ["PMULTs"]
}

def label(Feature, design):
    def contains_any(value, keywords):
        return int(any(kw in str(value) for kw in keywords))
    for node in Feature.keys():
        Feature[node]["label"] = contains_any(Feature[node]["Node"], leaky_module.get(design, []))