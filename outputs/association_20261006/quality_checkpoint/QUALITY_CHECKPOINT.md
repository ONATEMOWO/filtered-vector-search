# Incomplete metadata-association campaign: quality-only checkpoint

INCOMPLETE campaign: only the first two of four planned stages completed. There is one physical graph at 100k and one at 250k, not replicated graph evidence at either scale. Both stages' active-power query timing datasets are DISQUALIFIED and quarantined. Host logs report battery operation during both stages despite AC readings at run boundaries; stage 2 also contains host sleep intervals. No query latency or performance comparison is published here. Verified retrieval quality and source-exact density are retained as descriptive checkpoint evidence, not final findings or completion of the planned matched four-stage campaign.

## Scope and verification

Both raw stages and source data are freshly checked by the pinned offline verifier before this projection. Raw artifacts remain unchanged. Producer COMPLETE markers mean their recorded checks passed; they do not override the subsequent host-evidence timing disqualification. This output's COMPLETE marker authenticates only this quality-only checkpoint, not completion of the four-stage research campaign.

Host-evidence record: `/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search-association/outputs/association_20261006/HOST_VALIDITY_REVIEW.json`; SHA-256 `b455301699a6891efa1ee6f7aef5e1cf93f2071146d709317c1371b1786d3001`.

Quality averages retain all five repetitions. Paired differences first average each query's five quality observations and then compare radial minus baseline on the same graph. Conditions and stages are not pooled.

## Verified condition quality

| Stage / scale / build | Metadata | Method | Filter | Canonical Recall@10 | Tie-aware Recall@10 | Returned 10 | Mean returned count | Stable quality queries |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 / 100000 / 1 | legacy | exact | 50% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | exact | 20% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | exact | 10% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | exact | 5% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | exact | 1% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_standard | 50% | 0.9645 | 0.9645 | 99.5% | 9.995 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_standard | 20% | 0.7480 | 0.7480 | 26.0% | 7.560 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_standard | 10% | 0.4110 | 0.4110 | 0.5% | 4.115 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_standard | 5% | 0.2145 | 0.2145 | 0.0% | 2.145 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_standard | 1% | 0.0425 | 0.0425 | 0.0% | 0.425 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_iterative | 50% | 0.9645 | 0.9650 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_iterative | 20% | 0.9515 | 0.9515 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_iterative | 10% | 0.9555 | 0.9555 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_iterative | 5% | 0.9650 | 0.9650 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | legacy | hnsw_iterative | 1% | 0.9835 | 0.9835 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | exact | 50% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | exact | 20% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | exact | 10% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | exact | 5% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | exact | 1% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_standard | 50% | 0.5690 | 0.5690 | 54.5% | 5.850 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_standard | 20% | 0.4065 | 0.4065 | 37.5% | 4.215 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_standard | 10% | 0.2885 | 0.2885 | 23.5% | 3.025 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_standard | 5% | 0.2055 | 0.2055 | 12.0% | 2.130 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_standard | 1% | 0.0530 | 0.0530 | 0.5% | 0.530 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_iterative | 50% | 0.9710 | 0.9710 | 100.0% | 10.000 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_iterative | 20% | 0.5245 | 0.5245 | 55.5% | 5.645 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_iterative | 10% | 0.5130 | 0.5130 | 55.0% | 5.545 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_iterative | 5% | 0.5155 | 0.5155 | 55.0% | 5.520 | 200/200 |
| 1 / 100000 / 1 | radial | hnsw_iterative | 1% | 0.5245 | 0.5245 | 55.0% | 5.500 | 200/200 |
| 2 / 250000 / 1 | legacy | exact | 50% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | exact | 20% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | exact | 10% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | exact | 5% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | exact | 1% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_standard | 50% | 0.9435 | 0.9435 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_standard | 20% | 0.7510 | 0.7510 | 24.0% | 7.720 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_standard | 10% | 0.4095 | 0.4095 | 0.0% | 4.100 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_standard | 5% | 0.2050 | 0.2050 | 0.0% | 2.050 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_standard | 1% | 0.0390 | 0.0390 | 0.0% | 0.390 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_iterative | 50% | 0.9435 | 0.9435 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_iterative | 20% | 0.9225 | 0.9225 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_iterative | 10% | 0.9300 | 0.9300 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_iterative | 5% | 0.9390 | 0.9390 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | legacy | hnsw_iterative | 1% | 0.9730 | 0.9730 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | exact | 50% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | exact | 20% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | exact | 10% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | exact | 5% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | exact | 1% | 1.0000 | 1.0000 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_standard | 50% | 0.5620 | 0.5620 | 55.0% | 5.850 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_standard | 20% | 0.3990 | 0.3990 | 37.5% | 4.200 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_standard | 10% | 0.2690 | 0.2690 | 22.5% | 2.890 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_standard | 5% | 0.1835 | 0.1835 | 12.0% | 1.925 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_standard | 1% | 0.0515 | 0.0515 | 1.0% | 0.520 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_iterative | 50% | 0.9540 | 0.9540 | 100.0% | 10.000 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_iterative | 20% | 0.5170 | 0.5170 | 56.0% | 5.600 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_iterative | 10% | 0.5010 | 0.5010 | 55.0% | 5.540 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_iterative | 5% | 0.5065 | 0.5065 | 55.0% | 5.505 | 200/200 |
| 2 / 250000 / 1 | radial | hnsw_iterative | 1% | 0.5005 | 0.5005 | 53.5% | 5.410 | 200/200 |

## Paired quality contrasts

| Stage | Method | Filter | Canonical recall delta | Tie-aware recall delta | Returned-10 rate delta | Mean returned-count delta |
|---:|---|---:|---:|---:|---:|---:|
| 1 | exact | 50% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 1 | exact | 20% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 1 | exact | 10% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 1 | exact | 5% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 1 | exact | 1% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 1 | hnsw_standard | 50% | -0.3955 | -0.3955 | -0.4500 | -4.145 |
| 1 | hnsw_standard | 20% | -0.3415 | -0.3415 | +0.1150 | -3.345 |
| 1 | hnsw_standard | 10% | -0.1225 | -0.1225 | +0.2300 | -1.090 |
| 1 | hnsw_standard | 5% | -0.0090 | -0.0090 | +0.1200 | -0.015 |
| 1 | hnsw_standard | 1% | +0.0105 | +0.0105 | +0.0050 | +0.105 |
| 1 | hnsw_iterative | 50% | +0.0065 | +0.0060 | +0.0000 | +0.000 |
| 1 | hnsw_iterative | 20% | -0.4270 | -0.4270 | -0.4450 | -4.355 |
| 1 | hnsw_iterative | 10% | -0.4425 | -0.4425 | -0.4500 | -4.455 |
| 1 | hnsw_iterative | 5% | -0.4495 | -0.4495 | -0.4500 | -4.480 |
| 1 | hnsw_iterative | 1% | -0.4590 | -0.4590 | -0.4500 | -4.500 |
| 2 | exact | 50% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 2 | exact | 20% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 2 | exact | 10% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 2 | exact | 5% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 2 | exact | 1% | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| 2 | hnsw_standard | 50% | -0.3815 | -0.3815 | -0.4500 | -4.150 |
| 2 | hnsw_standard | 20% | -0.3520 | -0.3520 | +0.1350 | -3.520 |
| 2 | hnsw_standard | 10% | -0.1405 | -0.1405 | +0.2250 | -1.210 |
| 2 | hnsw_standard | 5% | -0.0215 | -0.0215 | +0.1200 | -0.125 |
| 2 | hnsw_standard | 1% | +0.0125 | +0.0125 | +0.0100 | +0.130 |
| 2 | hnsw_iterative | 50% | +0.0105 | +0.0105 | +0.0000 | +0.000 |
| 2 | hnsw_iterative | 20% | -0.4055 | -0.4055 | -0.4400 | -4.400 |
| 2 | hnsw_iterative | 10% | -0.4290 | -0.4290 | -0.4500 | -4.460 |
| 2 | hnsw_iterative | 5% | -0.4325 | -0.4325 | -0.4500 | -4.495 |
| 2 | hnsw_iterative | 1% | -0.4725 | -0.4725 | -0.4650 | -4.590 |

## Source-exact local association

At L=100, D is the mean squared difference between query-local and global qualifying fractions. The prespecified manipulation gate applies to 50% and 5%. The permutation p95 is an engineering reference, not a population significance test. All filters are retained.

| Stage | Filter | Baseline D | Radial D | Permutation p95 D | Condition passes |
|---:|---:|---:|---:|---:|---|
| 1 | 50% | 0.002277 | 0.226298 | 0.00289955 | True |
| 1 | 20% | 0.001436 | 0.133353 | 0.0018773 | True |
| 1 | 10% | 0.0008395 | 0.066549 | 0.0010497 | True |
| 1 | 5% | 0.000531 | 0.0278255 | 0.0005428 | True |
| 1 | 1% | 0.0001105 | 0.0022425 | 0.0001188 | True |
| 2 | 50% | 0.0024415 | 0.226533 | 0.00285865 | True |
| 2 | 20% | 0.001648 | 0.132865 | 0.0018608 | True |
| 2 | 10% | 0.0008875 | 0.0660965 | 0.00105775 | True |
| 2 | 5% | 0.00051 | 0.027085 | 0.000562 | True |
| 2 | 1% | 0.0001105 | 0.001499 | 0.0001246 | True |

JSON retains measured and disjoint-warmup density summaries, 60 quality conditions, 30 paired quality contrasts, per-query quality-only contrasts, top-40 density groups (0, 1–9, 10+), rank associations with quality only, query-anchor distances and exact filtered kth distances. No query timing values or timing comparisons are included.

## Limitations and next checkpoint

- Same fixed 200 queries and all five technical repetitions retained; 60000 calls are not independent samples.
- Synthetic fixed-anchor block-balanced metadata, one inherited assignment; not semantic labels.
- Modes share a graph within each stage; scale contrasts have different graphs and chronological confounding.
- No repeat graph at either scale; no completed counterbalanced four-stage campaign.
- Top-40 exact-neighbor counts proxy local density; they are not HNSW candidate sets or visit counts.
- Descriptive rank associations use average ranks and null for constant vectors; no significance tests.
- Quality and source-distance verification do not validate the disqualified active-power timing regime.

Do not resume database experiments until host power and sleep handling are confirmed. Any timing replacement or campaign continuation must preserve these quarantined originals and explicitly document its relationship to the frozen protocol. No 500k/1M execution or final research conclusion is authorized here.
