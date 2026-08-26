#!/usr/bin/env python3
"""Faza 13: pobor mocy na biegu jalowym. Tylko czytanie sysfs, zero zapisow.

Dwa niezalezne kanaly: GPU (hwmon power1_average, calka trapezami) i pakiet CPU
(licznik energii RAPL, roznica koncow - odporna na czestotliwosc probkowania).
Kanal CPU jest tu wazny, bo ASPM performance dotyczy calego kompleksu PCIe,
nie samej karty, a root complex siedzi w IO die procesora.
"""
import argparse, json, statistics as st, time

H = "/sys/class/drm/card1/device/hwmon/hwmon1"
D = "/sys/class/drm/card1/device"
RAPL = "/sys/class/powercap/intel-rapl:0"
DPMS = "/sys/class/drm/card1-DP-1/dpms"
LNK = "/sys/bus/pci/devices/0000:08:00.0/link"


def rd(p, cast=int, dflt=0):
    try:
        return cast(open(p).read().strip())
    except Exception:
        return dflt


def txt(p):
    return rd(p, str, "?")


def pkg_w(e0, t0, e1, t1, wrap):
    """Moc pakietu z licznika energii. Licznik moze sie przewinac przy wrap."""
    d = e1 - e0
    if d < 0:
        d += wrap
    dt = t1 - t0
    return round(d / 1e6 / dt, 2) if dt > 0 else None


def trapz(rows, i):
    """Srednia moc jako calka trapezami po realnych znacznikach czasu / czas."""
    if len(rows) < 2:
        return None
    j = sum((a[i] + b[i]) / 2.0 * (b[0] - a[0]) for a, b in zip(rows, rows[1:]))
    return round(j / (rows[-1][0] - rows[0][0]), 2)


def demo():
    assert pkg_w(0, 0.0, 2_000_000, 2.0, 1 << 40) == 1.0
    assert pkg_w((1 << 40) - 1_000_000, 0.0, 1_000_000, 2.0, 1 << 40) == 1.0, "wrap"
    r = [(0.0, 10.0), (1.0, 20.0), (2.0, 20.0)]  # 15 J + 20 J / 2 s
    assert trapz(r, 1) == 17.5, trapz(r, 1)
    print("demo ok")


def main(a):
    wrap = rd(f"{RAPL}/max_energy_range_uj", int, 1 << 40)
    dpms0, rows = txt(DPMS), []
    e0, t0 = rd(f"{RAPL}/energy_uj"), time.time()
    end = t0 + a.sec
    while time.time() < end:
        rows.append((time.time(),
                     rd(f"{H}/power1_average") / 1e6,
                     rd(f"{H}/in0_input"),
                     rd(f"{H}/freq1_input") / 1e6,
                     rd(f"{H}/freq2_input") / 1e6,
                     rd(f"{H}/temp2_input") / 1000.0,
                     rd(f"{H}/fan1_input"),
                     rd(f"{D}/gpu_busy_percent"),
                     rd(f"{D}/mem_busy_percent")))
        time.sleep(1.0 / a.hz)
    e1, t1 = rd(f"{RAPL}/energy_uj"), time.time()
    w = [r[1] for r in rows]
    o = {"tag": a.tag, "n": len(rows), "span_s": round(t1 - t0, 1),
         "gpu_w_trapz": trapz(rows, 1), "gpu_w_med": round(st.median(w), 2),
         "gpu_w_min": round(min(w), 2), "gpu_w_max": round(max(w), 2),
         "gpu_w_sd": round(st.stdev(w), 3) if len(w) > 1 else None,
         "mv_med": round(st.median(r[2] for r in rows), 1),
         "sclk_med": round(st.median(r[3] for r in rows), 1),
         "mclk_med": round(st.median(r[4] for r in rows), 1),
         "jt_med": round(st.median(r[5] for r in rows), 1),
         "fan_max": max(r[6] for r in rows),
         "busy_avg": round(st.mean(r[7] for r in rows), 2),
         "busy_max": max(r[7] for r in rows),
         "membusy_avg": round(st.mean(r[8] for r in rows), 2),
         "cpu_pkg_w": pkg_w(e0, t0, e1, t1, wrap),
         "dpms": dpms0, "dpms_stable": dpms0 == txt(DPMS),
         "pcie_dpm": txt(f"{D}/pp_dpm_pcie").replace("\n", "|"),
         "l1_aspm": txt(f"{LNK}/l1_aspm"), "clkpm": txt(f"{LNK}/clkpm"),
         "perf": txt(f"{D}/power_dpm_force_performance_level"),
         "cap_w": rd(f"{H}/power1_cap") // 1000000}
    print(json.dumps(o, ensure_ascii=False))
    if a.out:
        open(a.out, "a").write(json.dumps(o, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sec", type=float, default=120.0)
    ap.add_argument("--hz", type=float, default=4.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    demo() if a.demo else main(a)
