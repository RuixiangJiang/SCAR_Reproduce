from vcdvcd import VCDVCD

def parse_vcd(filename):
    vcd = VCDVCD(filename)

    signals = list(vcd.signals)

    for sig_key in vcd.signals:
        if "key_in" in sig_key or "text_in" in sig_key or "text_out" in sig_key:
            print(sig_key)
            sig = vcd[sig_key]
            for t, v in sig.tv:
                print(" ", t, v)


if __name__ == "__main__":
    parse_vcd("../data/aes128_table_ecb/aes128_table_ecb.vcd")
