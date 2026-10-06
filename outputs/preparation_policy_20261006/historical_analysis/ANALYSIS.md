# Historical repetition reanalysis

Descriptive measurement-qualification evidence, not final research findings. All five repetitions are retained. The same 200 queries are reused; repeated executions, conditions, and the two graph builds are not pooled as independent samples. No inferential test, cache-causality claim, or proof of steady state is made. Historical and pilot campaigns are context, not a matched comparison.

Primary latency: median across 200 per-query medians of all five repetitions. Query-median p95 is not request p95; each pass also reports its raw-request p95 separately. Ratios are paired within query. The 20% flag checks each pass median divided by the median across per-query medians of repetitions 2–5, outside [0.8, 1.2]. It is an engineering flag, not a statistical test.

## All conditions

| Build/arm | Method | Filter | Pass medians 1–5 ms | Pass request p95s ms | Primary median / query-median p95 ms | Paired first/later | Median absolute log2 | Later max/min | 20% flag | Recall canonical / tie | Complete |
|---|---|---:|---|---|---|---:|---:|---:|---|---|---:|
| 1/historical | exact | 1% | 2.059, 1.942, 2.197, 2.082, 2.126 | 4.455, 3.521, 3.601, 3.704, 3.391 | 2.088 / 2.837 | 0.991 | 0.300 | 1.131 | False | 1.0000 / 1.0000 | 100.0% |
| 1/historical | exact | 5% | 5.725, 5.602, 5.423, 4.556, 4.344 | 10.964, 9.968, 11.379, 7.645, 7.095 | 4.912 / 6.986 | 1.117 | 0.410 | 1.289 | False | 1.0000 / 1.0000 | 100.0% |
| 1/historical | exact | 10% | 7.117, 7.239, 7.827, 7.960, 7.904 | 11.725, 11.177, 13.993, 12.270, 12.180 | 7.618 / 9.925 | 0.963 | 0.302 | 1.099 | False | 1.0000 / 1.0000 | 100.0% |
| 1/historical | exact | 20% | 13.216, 15.196, 14.047, 12.807, 14.077 | 18.731, 22.094, 18.913, 18.305, 20.451 | 13.921 / 17.271 | 0.943 | 0.232 | 1.187 | False | 1.0000 / 1.0000 | 100.0% |
| 1/historical | exact | 50% | 27.022, 24.909, 26.123, 27.708, 27.353 | 39.337, 29.427, 31.169, 37.151, 35.948 | 26.524 / 29.486 | 1.037 | 0.161 | 1.112 | False | 1.0000 / 1.0000 | 100.0% |
| 1/historical | hnsw_standard | 1% | 8.552, 1.337, 1.175, 1.011, 1.285 | 48.062, 3.334, 2.773, 2.503, 2.651 | 1.395 / 2.367 | 6.787 | 2.763 | 1.321 | True | 0.0420 / 0.0420 | 0.0% |
| 1/historical | hnsw_standard | 5% | 1.713, 1.756, 1.818, 1.711, 1.606 | 2.942, 4.439, 6.048, 2.852, 4.716 | 1.754 / 2.319 | 0.976 | 0.192 | 1.132 | False | 0.2140 / 0.2140 | 0.0% |
| 1/historical | hnsw_standard | 10% | 1.378, 1.426, 1.366, 1.276, 1.375 | 3.426, 3.573, 2.894, 2.526, 2.655 | 1.380 / 1.986 | 1.026 | 0.392 | 1.117 | False | 0.4130 / 0.4130 | 0.5% |
| 1/historical | hnsw_standard | 20% | 1.430, 1.357, 1.392, 1.594, 1.711 | 2.858, 2.483, 2.492, 6.912, 8.526 | 1.465 / 2.401 | 0.937 | 0.365 | 1.261 | False | 0.7480 / 0.7480 | 26.0% |
| 1/historical | hnsw_standard | 50% | 17.902, 1.966, 1.621, 1.617, 1.572 | 56.753, 7.711, 3.365, 4.458, 3.277 | 1.901 / 3.404 | 10.877 | 3.443 | 1.250 | True | 0.9635 / 0.9635 | 99.5% |
| 1/historical | hnsw_iterative | 1% | 14.008, 13.559, 14.618, 18.057, 19.771 | 24.034, 23.089, 24.431, 45.694, 45.476 | 15.852 / 24.718 | 0.839 | 0.289 | 1.458 | False | 0.9835 / 0.9835 | 100.0% |
| 1/historical | hnsw_iterative | 5% | 5.098, 4.808, 4.291, 4.554, 4.514 | 10.980, 9.994, 8.373, 10.244, 8.472 | 4.567 / 8.002 | 1.172 | 0.342 | 1.120 | False | 0.9660 / 0.9660 | 100.0% |
| 1/historical | hnsw_iterative | 10% | 8.580, 4.017, 3.762, 3.132, 2.712 | 26.290, 8.868, 9.022, 7.066, 6.305 | 3.639 / 6.883 | 2.679 | 1.421 | 1.481 | True | 0.9565 / 0.9565 | 100.0% |
| 1/historical | hnsw_iterative | 20% | 2.149, 2.167, 2.030, 2.205, 2.034 | 4.784, 5.825, 3.500, 5.211, 3.536 | 2.124 / 3.285 | 1.015 | 0.319 | 1.086 | False | 0.9515 / 0.9515 | 100.0% |
| 1/historical | hnsw_iterative | 50% | 1.670, 1.653, 1.704, 1.633, 1.843 | 5.066, 3.857, 4.053, 3.633, 5.651 | 1.721 / 2.600 | 0.964 | 0.449 | 1.129 | False | 0.9635 / 0.9640 | 100.0% |
| 2/historical | exact | 1% | 2.487, 2.401, 2.462, 2.384, 2.214 | 4.742, 5.214, 4.736, 4.498, 5.208 | 2.440 / 3.286 | 1.056 | 0.350 | 1.112 | False | 1.0000 / 1.0000 | 100.0% |
| 2/historical | exact | 5% | 5.537, 4.879, 5.853, 6.854, 5.688 | 10.626, 11.330, 12.434, 15.889, 7.037 | 5.716 / 7.454 | 0.953 | 0.399 | 1.405 | False | 1.0000 / 1.0000 | 100.0% |
| 2/historical | exact | 10% | 9.571, 8.345, 8.141, 8.400, 8.376 | 17.121, 11.858, 12.873, 14.696, 12.895 | 8.555 / 10.978 | 1.115 | 0.296 | 1.032 | False | 1.0000 / 1.0000 | 100.0% |
| 2/historical | exact | 20% | 13.694, 14.768, 15.283, 12.634, 16.104 | 20.511, 35.667, 30.012, 17.490, 24.498 | 14.578 / 18.267 | 0.954 | 0.262 | 1.275 | False | 1.0000 / 1.0000 | 100.0% |
| 2/historical | exact | 50% | 25.397, 24.683, 32.144, 34.134, 28.153 | 32.277, 31.835, 106.673, 103.092, 36.865 | 27.623 / 33.455 | 0.849 | 0.261 | 1.383 | False | 1.0000 / 1.0000 | 100.0% |
| 2/historical | hnsw_standard | 1% | 10.135, 1.815, 1.770, 1.567, 1.479 | 39.328, 4.668, 5.717, 3.594, 3.244 | 1.854 / 3.732 | 5.929 | 2.568 | 1.227 | True | 0.0420 / 0.0420 | 0.0% |
| 2/historical | hnsw_standard | 5% | 1.391, 1.358, 1.342, 1.392, 1.324 | 2.430, 2.401, 2.553, 2.416, 2.530 | 1.370 / 1.857 | 0.993 | 0.322 | 1.051 | False | 0.2135 / 0.2135 | 0.0% |
| 2/historical | hnsw_standard | 10% | 1.428, 1.350, 1.361, 1.383, 1.258 | 2.503, 2.461, 2.597, 2.301, 2.786 | 1.352 / 1.834 | 1.037 | 0.299 | 1.099 | False | 0.4120 / 0.4120 | 0.5% |
| 2/historical | hnsw_standard | 20% | 1.648, 1.817, 1.747, 1.749, 1.769 | 2.838, 3.938, 3.111, 2.757, 3.090 | 1.777 / 2.356 | 0.970 | 0.240 | 1.040 | False | 0.7490 / 0.7490 | 26.0% |
| 2/historical | hnsw_standard | 50% | 2.444, 1.343, 1.252, 1.230, 1.204 | 7.560, 3.991, 5.632, 3.470, 3.417 | 1.406 / 2.664 | 1.869 | 0.941 | 1.115 | True | 0.9635 / 0.9635 | 99.5% |
| 2/historical | hnsw_iterative | 1% | 16.007, 15.003, 17.901, 15.364, 15.588 | 28.879, 24.766, 32.624, 26.149, 29.315 | 15.581 / 25.784 | 1.030 | 0.244 | 1.193 | False | 0.9835 / 0.9835 | 100.0% |
| 2/historical | hnsw_iterative | 5% | 4.389, 4.523, 4.604, 4.817, 4.380 | 8.365, 8.260, 8.842, 10.406, 9.434 | 4.416 / 7.449 | 0.934 | 0.260 | 1.100 | False | 0.9645 / 0.9645 | 100.0% |
| 2/historical | hnsw_iterative | 10% | 3.831, 3.309, 3.280, 3.076, 2.713 | 8.715, 6.496, 6.452, 6.135, 5.556 | 3.219 / 4.912 | 1.240 | 0.424 | 1.220 | True | 0.9565 / 0.9565 | 100.0% |
| 2/historical | hnsw_iterative | 20% | 1.988, 2.003, 2.023, 2.012, 2.189 | 3.441, 3.754, 3.521, 3.801, 3.764 | 2.063 / 2.884 | 0.941 | 0.248 | 1.093 | False | 0.9520 / 0.9520 | 100.0% |
| 2/historical | hnsw_iterative | 50% | 1.418, 1.410, 1.380, 1.216, 1.362 | 2.699, 2.450, 2.891, 2.706, 2.787 | 1.351 / 2.005 | 1.034 | 0.349 | 1.159 | False | 0.9635 / 0.9640 | 100.0% |

## Exploratory prevalence

```json
{
  "condition_count": 30,
  "paired_first_over_later_above_1_2": 6,
  "paired_first_over_later_above_2": 4,
  "later_pass_max_over_min_above_1_2": 11,
  "engineering_20pct_flags": 6,
  "threshold_interpretation": "Historical thresholds are exploratory descriptions, not retroactive acceptance tests."
}
```

## Warmup versus measured query descriptors

```json
{
  "interpretation": "Descriptive only; supplied full-1M unfiltered distances are query features, not filtered 100k ground truth.",
  "groups": {
    "measured": {
      "query_count": 200,
      "features": {
        "vector_l2_norm": {
          "min_q25_median_q75_max": [
            507.10649769057386,
            508.2632192076013,
            508.62559903263093,
            509.0643376946129,
            510.64958631139615
          ],
          "mean": 508.6690736352037
        },
        "zero_dimension_count": {
          "min_q25_median_q75_max": [
            1.0,
            18.0,
            28.5,
            36.25,
            73.0
          ],
          "mean": 29.61
        },
        "full1m_nearest_distance": {
          "min_q25_median_q75_max": [
            53.879493713378906,
            153.5244255065918,
            189.82624053955078,
            223.32780838012695,
            290.41351318359375
          ],
          "mean": 184.80680309295656
        },
        "full1m_10th_distance": {
          "min_q25_median_q75_max": [
            75.8617172241211,
            188.9927215576172,
            229.18223571777344,
            251.21152114868164,
            313.78973388671875
          ],
          "mean": 219.06983825683594
        },
        "full1m_100th_distance": {
          "min_q25_median_q75_max": [
            91.0933609008789,
            216.25809478759766,
            253.79222869873047,
            275.9628448486328,
            350.3755187988281
          ],
          "mean": 244.93462268829344
        },
        "full1m_d1_over_d10": {
          "min_q25_median_q75_max": [
            0.316465429366696,
            0.8388014435849245,
            0.8879583293620658,
            0.9214130296616532,
            0.9732154857195905
          ],
          "mean": 0.8412449718108208
        }
      }
    },
    "warmup": {
      "query_count": 20,
      "features": {
        "vector_l2_norm": {
          "min_q25_median_q75_max": [
            507.585460784684,
            508.2007333299608,
            508.5346586426299,
            508.9086361896569,
            509.6459555416878
          ],
          "mean": 508.53838812625446
        },
        "zero_dimension_count": {
          "min_q25_median_q75_max": [
            2.0,
            13.25,
            25.5,
            32.25,
            52.0
          ],
          "mean": 23.65
        },
        "full1m_nearest_distance": {
          "min_q25_median_q75_max": [
            85.73213958740234,
            168.93943405151367,
            196.87332153320312,
            227.63719177246094,
            262.31658935546875
          ],
          "mean": 191.69665870666503
        },
        "full1m_10th_distance": {
          "min_q25_median_q75_max": [
            156.52476501464844,
            212.46151733398438,
            237.2277069091797,
            271.2584228515625,
            286.0384521484375
          ],
          "mean": 236.84332275390625
        },
        "full1m_100th_distance": {
          "min_q25_median_q75_max": [
            183.283935546875,
            236.5968132019043,
            263.14849853515625,
            298.51758575439453,
            317.6838073730469
          ],
          "mean": 262.6850440979004
        },
        "full1m_d1_over_d10": {
          "min_q25_median_q75_max": [
            0.3024141442978198,
            0.8261714379484089,
            0.8827153902130411,
            0.9103419329781371,
            0.9597117108540784
          ],
          "mean": 0.8170656779364048
        }
      }
    }
  }
}
```

## Provenance and scope

Generator SHA-256: `8a0d4ee8a448d0eed828e23b59db2d5da40047ce57197edbd641c4796063f0ad`.

Full artifact snapshots, source hashes where supplied, and code/worktree identity are in analysis.json. Input manifests are checked before and after analysis. This supplement does not replace source/ground-truth/query-plan verification.
