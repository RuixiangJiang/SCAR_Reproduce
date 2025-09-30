from vcdvcd import VCDVCD

def parse_vcd(filename):
    vcd = VCDVCD(filename)
    with open("../out/train_vcd_signals.txt", "w") as f:
        for sig_key in vcd.signals:
            f.write(f"{sig_key}\n")
            sig = vcd[sig_key]
            for t, v in sig.tv:
                f.write(f" {t} {v}\n")


if __name__ == "__main__":
    parse_vcd("../data/aes128_table_ecb/aes128_table_ecb.vcd")
