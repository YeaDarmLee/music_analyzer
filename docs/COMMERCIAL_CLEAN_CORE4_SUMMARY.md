### SDR / SI-SDR / leak by stem and level (mean over timbres; dB)

| Stem | Level | SDR base | SDR core4 | ¥Ä | SI-SDR base | SI-SDR core4 | ¥Ä | Leak base | Leak core4 |
|---|---|---|---|---|---|---|---|---|---|
| piano | 0 dB | 9.64 | 8.54 | -1.10 | 9.15 | 7.88 | -1.27 | -19.50 | -17.69 |
| piano | -6 dB | 6.16 | 4.76 | -1.41 | 4.97 | 2.98 | -1.99 | -20.32 | -15.82 |
| piano | -12 dB | 3.06 | 2.00 | -1.06 | 0.09 | -2.42 | -2.51 | -21.36 | -12.99 |
| piano | -18 dB | 1.11 | 0.30 | -0.81 | -5.48 | -9.82 | -4.34 | -20.87 | -7.95 |
| guitar | 0 dB | 4.05 | 4.16 | 0.11 | 2.10 | 2.22 | 0.12 | -21.03 | -17.71 |
| guitar | -6 dB | 1.82 | 1.67 | -0.15 | -2.74 | -3.17 | -0.43 | -22.24 | -16.28 |
| guitar | -12 dB | 0.16 | 0.17 | 0.02 | -18.53 | -18.86 | -0.32 | -5.96 | 8.15 |
| guitar | -18 dB | 0.00 | -0.12 | -0.12 | -37.35 | -41.02 | -3.67 | 19.92 | 33.54 |
| bass | 0 dB | 12.30 | 11.55 | -0.75 | 12.17 | 11.34 | -0.83 | -27.93 | -25.63 |
| bass | -6 dB | 5.66 | 8.73 | 3.07 | 4.85 | 8.23 | 3.38 | -28.25 | -24.28 |
| bass | -12 dB | 1.21 | 5.50 | 4.29 | -17.10 | 4.25 | 21.35 | -5.39 | -23.26 |
| bass | -18 dB | 0.00 | 1.57 | 1.57 | -35.07 | -3.34 | 31.74 | 22.97 | -19.30 |
| drums | 0 dB | 15.42 | 13.36 | -2.06 | 15.30 | 13.17 | -2.14 | -30.70 | -29.03 |
| drums | -6 dB | 11.87 | 10.34 | -1.53 | 11.59 | 9.94 | -1.65 | -29.40 | -28.06 |
| drums | -12 dB | 8.64 | 6.79 | -1.85 | 8.04 | 5.77 | -2.27 | -28.34 | -26.04 |
| drums | -18 dB | 3.40 | 2.31 | -1.09 | 0.77 | -1.50 | -2.28 | -35.45 | -25.04 |

### Overall per stem (all levels)

| Stem | SDR base | SDR core4 | ¥Ä | energy ratio base | energy ratio core4 |
|---|---|---|---|---|---|
| piano | 4.99 | 3.90 | -1.09 | -3.83 | -3.79 |
| guitar | 1.51 | 1.47 | -0.03 | -25.55 | -12.66 |
| bass | 4.79 | 6.84 | 2.04 | -28.81 | -3.66 |
| drums | 9.83 | 8.20 | -1.63 | -0.97 | -1.47 |

### Silence false positive (target absent; dB relative to mix, lower is better)

| Stem | base | core4 |
|---|---|---|
| piano | -84.2 | -49.1 |
| guitar | -83.5 | -46.8 |
| bass | -92.5 | -50.9 |
| drums | -90.9 | -55.0 |

### Residual (mix minus four stems; dB re full scale) and finiteness

- baseline_6s: mean residual -22.5 dB, all finite: True
- core4: mean residual -22.6 dB, all finite: True

### Runtime

- baseline_6s: 475.3 s for 2400 s audio (RTF 0.20), peak VRAM 1879 MiB
- core4: 453.1 s for 2400 s audio (RTF 0.19), peak VRAM 1646 MiB
