# Third-Party Data Notice

Models and datasets produced with the Data Factory use the following third-party material. Obligations are recorded per asset in `artifacts/assets/<asset_id>.json` and checked by the production gate (`engine.data.manifest`, usage `PRODUCTION_TRAINING`): an asset with `attribution_required=true` is rejected unless `attribution_text` is present.

## Attribution required

**VocalSet: A Singing Voice Dataset** — Wilkins, Julia; Prem Seetharaman; Alison Wahl; Bryan Pardo (creators as listed by the Zenodo record). Version 1.1, Zenodo, 2018. DOI 10.5281/zenodo.1203819. Licensed under Creative Commons Attribution 4.0 International (https://creativecommons.org/licenses/by/4.0/). The recordings were cropped, mixed with other material and processed (EQ, compression, reverb, delay, chorus, gain) for model training. Only the `scales`, `arpeggios` and `long_tones` categories are used; `excerpts` are excluded by project policy. The exact citation wording requested by the publisher is not confirmed (NEEDS_RESEARCH).

## No attribution required (CC0 1.0 Universal), listed for provenance

| asset | source | pinned version |
|---|---|---|
| Versilian Community Sample Library (VCSL) | https://github.com/sgossner/VCSL | commit c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e |
| VCSL Keys | https://versilian-studios.com/vcsl-keys/ | VCSL_Keys.zip sha256 2e91c9aa7b16d936f035963149df1fe4cbd65911116fb3e3ea6daca52e92024b |
| Karoryfer Big Little Bass | https://github.com/sfzinstruments/karoryfer.big-little-bass | commit 4e92bdf54dcd2d6cfad968cc90542d5461c9b9fc |
| Karoryfer Sneakybass | https://github.com/sfzinstruments/karoryfer.sneakybass | commit cc1a67e5c913678b85eaad1a3b5cb180d3be3e2d |
| Stargate Sample Pack | https://github.com/stargatedaw/stargate-sample-pack | commit dbfd6ec52d4ed53b60bdbea5fc6adf295127c027 |

License snapshots (verbatim legal text with retrieval evidence): `artifacts/licenses/<asset_id>/LICENSE.txt`.
