# Preparation-policy pilot analysis

Descriptive measurement-qualification evidence, not final research findings. All five repetitions are retained. The same 200 queries are reused; repeated executions, conditions, and the two graph builds are not pooled as independent samples. No inferential test, cache-causality claim, or proof of steady state is made. Historical and pilot campaigns are context, not a matched comparison.

Arm A: 20 disjoint warmup queries per method/filter block. Arm B: the same 20 warmups plus one exposure to all 200 measured queries before the five retained repetitions. Build 1 runs A then B; build 2 runs B then A. Arms within a build share the graph, with verified shared-buffer eviction before each arm; OS cache is not flushed. This is an operational preparation-policy comparison, not a cold-cache test.

Primary latency: median across 200 per-query medians of all five repetitions. Query-median p95 is not request p95; each pass also reports its raw-request p95 separately. Ratios are paired within query. The 20% flag checks each pass median divided by the median across per-query medians of repetitions 2–5, outside [0.8, 1.2]. It is an engineering flag, not a statistical test.

## All conditions

| Build/arm | Method | Filter | Pass medians 1–5 ms | Pass request p95s ms | Primary median / query-median p95 ms | Paired first/later | Median absolute log2 | Later max/min | 20% flag | Recall canonical / tie | Complete |
|---|---|---:|---|---|---|---:|---:|---:|---|---|---:|
| 1/A | exact | 1% | 1.395, 1.402, 1.327, 1.311, 1.301 | 2.708, 2.826, 2.483, 2.388, 2.467 | 1.343 / 1.853 | 1.031 | 0.386 | 1.078 | False | 1.0000 / 1.0000 | 100.0% |
| 1/A | exact | 5% | 3.806, 3.929, 4.306, 3.898, 3.645 | 5.513, 6.490, 7.074, 6.788, 4.758 | 3.900 / 4.965 | 0.957 | 0.180 | 1.181 | False | 1.0000 / 1.0000 | 100.0% |
| 1/A | exact | 10% | 6.050, 5.966, 6.267, 6.142, 6.039 | 7.426, 7.192, 10.185, 8.176, 8.149 | 6.065 / 6.924 | 0.997 | 0.114 | 1.050 | False | 1.0000 / 1.0000 | 100.0% |
| 1/A | exact | 20% | 11.138, 11.067, 11.631, 10.953, 10.966 | 14.128, 17.747, 17.271, 14.192, 14.161 | 11.124 / 12.655 | 0.997 | 0.119 | 1.062 | False | 1.0000 / 1.0000 | 100.0% |
| 1/A | exact | 50% | 21.198, 21.543, 20.702, 21.582, 20.977 | 29.882, 29.953, 28.281, 30.498, 28.926 | 21.148 / 23.478 | 0.989 | 0.084 | 1.042 | False | 1.0000 / 1.0000 | 100.0% |
| 1/A | hnsw_iterative | 1% | 13.468, 11.149, 12.834, 11.091, 10.173 | 27.028, 17.639, 21.977, 18.950, 16.802 | 11.160 / 17.302 | 1.223 | 0.385 | 1.262 | True | 0.9830 / 0.9830 | 100.0% |
| 1/A | hnsw_iterative | 5% | 3.549, 3.304, 3.740, 3.429, 3.402 | 5.980, 6.220, 7.270, 6.647, 5.867 | 3.415 / 5.625 | 0.990 | 0.195 | 1.132 | False | 0.9655 / 0.9655 | 100.0% |
| 1/A | hnsw_iterative | 10% | 5.193, 2.275, 2.359, 2.698, 2.302 | 10.349, 4.589, 4.175, 5.599, 4.332 | 2.544 / 4.462 | 2.214 | 1.147 | 1.186 | True | 0.9575 / 0.9575 | 100.0% |
| 1/A | hnsw_iterative | 20% | 1.568, 1.461, 1.482, 1.595, 1.644 | 3.049, 2.799, 2.720, 2.845, 3.509 | 1.511 / 2.424 | 1.012 | 0.262 | 1.125 | False | 0.9525 / 0.9525 | 100.0% |
| 1/A | hnsw_iterative | 50% | 1.216, 1.045, 1.202, 1.020, 1.061 | 2.125, 1.725, 1.939, 1.751, 1.888 | 1.105 / 1.475 | 1.110 | 0.283 | 1.178 | False | 0.9650 / 0.9655 | 100.0% |
| 1/A | hnsw_standard | 1% | 1.120, 1.113, 1.086, 1.037, 1.017 | 2.205, 2.257, 2.381, 2.163, 2.100 | 1.072 / 1.516 | 1.030 | 0.271 | 1.095 | False | 0.0420 / 0.0420 | 0.0% |
| 1/A | hnsw_standard | 5% | 1.109, 1.063, 1.063, 1.082, 1.130 | 2.156, 1.816, 1.884, 2.261, 2.248 | 1.090 / 1.504 | 0.992 | 0.284 | 1.063 | False | 0.2140 / 0.2140 | 0.0% |
| 1/A | hnsw_standard | 10% | 5.924, 1.204, 1.171, 1.170, 1.157 | 16.908, 1.919, 2.182, 1.972, 1.922 | 1.239 / 1.775 | 5.025 | 2.329 | 1.041 | True | 0.4120 / 0.4120 | 0.5% |
| 1/A | hnsw_standard | 20% | 1.274, 1.198, 1.060, 1.005, 0.986 | 2.318, 2.485, 2.398, 1.642, 1.648 | 1.093 / 1.530 | 1.201 | 0.400 | 1.215 | False | 0.7490 / 0.7490 | 26.5% |
| 1/A | hnsw_standard | 50% | 1.016, 0.996, 0.936, 0.938, 0.990 | 1.768, 1.884, 1.705, 1.771, 1.636 | 0.971 / 1.373 | 1.055 | 0.247 | 1.064 | False | 0.9650 / 0.9650 | 99.5% |
| 1/B | exact | 1% | 1.435, 1.517, 1.628, 1.284, 1.190 | 2.534, 3.093, 3.078, 2.191, 2.111 | 1.389 / 2.025 | 1.010 | 0.377 | 1.368 | False | 1.0000 / 1.0000 | 100.0% |
| 1/B | exact | 5% | 3.413, 3.457, 3.569, 4.128, 3.608 | 4.553, 4.509, 4.667, 9.429, 6.140 | 3.561 / 4.353 | 0.935 | 0.174 | 1.194 | False | 1.0000 / 1.0000 | 100.0% |
| 1/B | exact | 10% | 6.022, 6.229, 6.434, 6.619, 6.638 | 7.551, 8.540, 8.422, 10.409, 8.436 | 6.370 / 7.286 | 0.927 | 0.140 | 1.066 | False | 1.0000 / 1.0000 | 100.0% |
| 1/B | exact | 20% | 11.156, 11.108, 10.967, 11.292, 11.085 | 17.485, 15.283, 12.592, 14.636, 12.320 | 11.101 / 11.870 | 1.022 | 0.100 | 1.030 | False | 1.0000 / 1.0000 | 100.0% |
| 1/B | exact | 50% | 25.228, 24.418, 25.991, 25.504, 21.823 | 31.743, 28.279, 31.000, 30.707, 26.098 | 24.576 / 27.136 | 1.045 | 0.146 | 1.191 | False | 1.0000 / 1.0000 | 100.0% |
| 1/B | hnsw_iterative | 1% | 12.637, 13.412, 11.552, 16.637, 12.478 | 23.182, 22.839, 18.879, 40.610, 19.516 | 12.890 / 20.039 | 0.993 | 0.192 | 1.440 | True | 0.9830 / 0.9830 | 100.0% |
| 1/B | hnsw_iterative | 5% | 3.836, 3.877, 4.089, 4.203, 4.191 | 6.877, 7.623, 7.422, 7.702, 8.485 | 4.027 / 6.962 | 0.951 | 0.204 | 1.084 | False | 0.9655 / 0.9655 | 100.0% |
| 1/B | hnsw_iterative | 10% | 2.191, 2.230, 2.202, 2.446, 3.654 | 4.171, 3.961, 3.829, 4.596, 15.601 | 2.329 / 4.051 | 0.928 | 0.318 | 1.660 | True | 0.9575 / 0.9575 | 100.0% |
| 1/B | hnsw_iterative | 20% | 1.878, 1.879, 1.854, 1.961, 1.992 | 3.616, 3.758, 3.229, 3.975, 3.778 | 1.935 / 3.120 | 0.952 | 0.333 | 1.074 | False | 0.9525 / 0.9525 | 100.0% |
| 1/B | hnsw_iterative | 50% | 1.319, 1.458, 1.380, 1.294, 1.902 | 2.326, 2.399, 2.580, 2.669, 3.631 | 1.423 / 2.071 | 0.868 | 0.356 | 1.470 | True | 0.9650 / 0.9655 | 100.0% |
| 1/B | hnsw_standard | 1% | 1.133, 1.069, 1.027, 1.024, 1.051 | 2.308, 2.236, 2.152, 1.923, 1.953 | 1.030 / 1.578 | 1.047 | 0.342 | 1.043 | False | 0.0420 / 0.0420 | 0.0% |
| 1/B | hnsw_standard | 5% | 1.019, 1.064, 1.024, 1.036, 1.000 | 1.863, 2.074, 2.187, 1.777, 1.991 | 1.028 / 1.455 | 0.955 | 0.282 | 1.064 | False | 0.2140 / 0.2140 | 0.0% |
| 1/B | hnsw_standard | 10% | 1.171, 1.124, 1.083, 1.131, 1.018 | 2.188, 2.266, 2.038, 2.149, 1.889 | 1.112 / 1.639 | 1.026 | 0.302 | 1.112 | False | 0.4120 / 0.4120 | 0.5% |
| 1/B | hnsw_standard | 20% | 1.536, 1.921, 1.676, 1.335, 1.232 | 7.016, 6.879, 7.508, 2.038, 1.939 | 1.507 / 2.154 | 1.014 | 0.297 | 1.559 | True | 0.7490 / 0.7490 | 26.5% |
| 1/B | hnsw_standard | 50% | 1.247, 1.209, 1.156, 1.107, 1.156 | 1.998, 1.831, 1.702, 1.986, 1.810 | 1.179 / 1.605 | 1.066 | 0.254 | 1.092 | False | 0.9650 / 0.9650 | 99.5% |
| 2/A | exact | 1% | 1.738, 1.680, 1.631, 1.790, 1.615 | 3.135, 2.286, 2.050, 3.163, 2.083 | 1.689 / 2.024 | 1.060 | 0.333 | 1.109 | False | 1.0000 / 1.0000 | 100.0% |
| 2/A | exact | 5% | 3.879, 3.898, 3.711, 3.742, 3.735 | 5.462, 4.966, 4.240, 4.355, 4.566 | 3.764 / 4.153 | 1.025 | 0.116 | 1.050 | False | 1.0000 / 1.0000 | 100.0% |
| 2/A | exact | 10% | 5.953, 5.965, 5.877, 6.115, 5.937 | 8.207, 8.528, 7.408, 8.090, 8.292 | 5.968 / 6.583 | 0.994 | 0.086 | 1.041 | False | 1.0000 / 1.0000 | 100.0% |
| 2/A | exact | 20% | 10.861, 10.802, 10.911, 10.891, 12.785 | 12.324, 14.272, 12.654, 16.299, 19.468 | 10.967 / 11.701 | 0.982 | 0.073 | 1.184 | False | 1.0000 / 1.0000 | 100.0% |
| 2/A | exact | 50% | 25.042, 22.666, 21.515, 23.058, 22.328 | 28.865, 28.399, 27.670, 27.588, 27.137 | 22.800 / 25.822 | 1.096 | 0.176 | 1.072 | False | 1.0000 / 1.0000 | 100.0% |
| 2/A | hnsw_iterative | 1% | 9.785, 10.162, 10.232, 10.390, 10.463 | 16.103, 15.597, 16.762, 17.089, 16.340 | 10.194 / 15.608 | 0.957 | 0.108 | 1.030 | False | 0.9830 / 0.9830 | 100.0% |
| 2/A | hnsw_iterative | 5% | 3.399, 3.834, 3.942, 4.672, 5.199 | 5.810, 6.220, 7.289, 7.539, 8.896 | 3.971 / 6.664 | 0.797 | 0.331 | 1.356 | True | 0.9650 / 0.9650 | 100.0% |
| 2/A | hnsw_iterative | 10% | 2.277, 2.196, 2.353, 2.541, 2.306 | 3.366, 3.662, 3.783, 4.516, 4.357 | 2.302 / 3.610 | 0.984 | 0.120 | 1.157 | False | 0.9560 / 0.9560 | 100.0% |
| 2/A | hnsw_iterative | 20% | 1.615, 1.684, 1.418, 1.650, 1.472 | 2.368, 2.458, 2.314, 2.497, 2.348 | 1.603 / 2.300 | 1.041 | 0.173 | 1.188 | False | 0.9505 / 0.9505 | 100.0% |
| 2/A | hnsw_iterative | 50% | 1.655, 1.513, 1.285, 1.301, 1.303 | 2.512, 2.296, 1.823, 1.774, 1.828 | 1.375 / 1.743 | 1.259 | 0.380 | 1.177 | True | 0.9640 / 0.9645 | 100.0% |
| 2/A | hnsw_standard | 1% | 1.222, 1.163, 1.169, 1.198, 1.107 | 1.726, 1.807, 1.869, 1.881, 1.484 | 1.160 / 1.514 | 1.059 | 0.195 | 1.083 | False | 0.0420 / 0.0420 | 0.0% |
| 2/A | hnsw_standard | 5% | 0.955, 1.213, 1.155, 0.905, 1.145 | 1.379, 2.130, 1.575, 1.527, 1.515 | 1.116 / 1.387 | 0.837 | 0.290 | 1.340 | True | 0.2145 / 0.2145 | 0.0% |
| 2/A | hnsw_standard | 10% | 1.157, 1.015, 1.149, 1.211, 1.121 | 1.537, 1.555, 1.503, 1.753, 1.486 | 1.144 / 1.410 | 0.997 | 0.157 | 1.193 | False | 0.4130 / 0.4130 | 0.5% |
| 2/A | hnsw_standard | 20% | 1.257, 1.112, 1.134, 0.915, 1.158 | 2.098, 1.556, 1.467, 1.427, 1.562 | 1.131 / 1.415 | 1.141 | 0.283 | 1.265 | False | 0.7480 / 0.7480 | 27.0% |
| 2/A | hnsw_standard | 50% | 1.618, 1.029, 1.156, 0.950, 1.241 | 8.630, 1.486, 1.486, 1.386, 1.904 | 1.182 / 1.423 | 1.425 | 0.514 | 1.306 | True | 0.9640 / 0.9640 | 99.5% |
| 2/B | exact | 1% | 1.584, 1.640, 1.607, 1.534, 1.677 | 2.295, 2.713, 2.479, 2.229, 2.735 | 1.598 / 2.022 | 0.971 | 0.241 | 1.093 | False | 1.0000 / 1.0000 | 100.0% |
| 2/B | exact | 5% | 3.825, 3.747, 3.789, 3.890, 3.790 | 4.897, 4.290, 4.359, 5.209, 4.846 | 3.788 / 4.178 | 1.009 | 0.102 | 1.038 | False | 1.0000 / 1.0000 | 100.0% |
| 2/B | exact | 10% | 5.528, 6.123, 6.465, 6.262, 6.149 | 7.068, 7.322, 8.614, 9.804, 7.254 | 6.142 / 6.829 | 0.897 | 0.191 | 1.056 | False | 1.0000 / 1.0000 | 100.0% |
| 2/B | exact | 20% | 10.794, 10.791, 10.847, 11.020, 11.139 | 12.663, 12.741, 13.861, 14.458, 14.530 | 10.915 / 11.667 | 0.981 | 0.066 | 1.032 | False | 1.0000 / 1.0000 | 100.0% |
| 2/B | exact | 50% | 24.916, 24.986, 29.930, 25.246, 22.509 | 30.774, 30.556, 54.623, 36.148, 28.061 | 24.964 / 28.612 | 0.972 | 0.170 | 1.330 | False | 1.0000 / 1.0000 | 100.0% |
| 2/B | hnsw_iterative | 1% | 10.776, 11.279, 10.479, 10.379, 10.454 | 18.038, 17.198, 17.190, 15.947, 16.148 | 10.608 / 15.957 | 1.023 | 0.098 | 1.087 | False | 0.9830 / 0.9830 | 100.0% |
| 2/B | hnsw_iterative | 5% | 4.120, 4.026, 3.789, 3.986, 3.663 | 6.649, 6.831, 7.080, 7.160, 6.763 | 3.791 / 6.010 | 1.023 | 0.241 | 1.099 | False | 0.9650 / 0.9650 | 100.0% |
| 2/B | hnsw_iterative | 10% | 2.330, 2.215, 2.339, 2.139, 2.244 | 3.503, 3.592, 4.238, 3.462, 3.542 | 2.206 / 3.257 | 1.038 | 0.116 | 1.093 | False | 0.9560 / 0.9560 | 100.0% |
| 2/B | hnsw_iterative | 20% | 1.708, 1.598, 1.620, 1.724, 1.659 | 2.666, 2.383, 2.505, 2.625, 2.384 | 1.686 / 2.250 | 1.007 | 0.178 | 1.079 | False | 0.9505 / 0.9505 | 100.0% |
| 2/B | hnsw_iterative | 50% | 1.130, 1.166, 1.193, 1.258, 1.298 | 2.008, 2.059, 1.953, 2.182, 2.334 | 1.222 / 1.623 | 0.920 | 0.325 | 1.114 | False | 0.9640 / 0.9645 | 100.0% |
| 2/B | hnsw_standard | 1% | 1.121, 1.144, 1.130, 1.112, 1.107 | 1.533, 1.525, 1.520, 1.611, 1.501 | 1.111 / 1.387 | 0.977 | 0.202 | 1.033 | False | 0.0420 / 0.0420 | 0.0% |
| 2/B | hnsw_standard | 5% | 1.150, 1.218, 1.186, 1.173, 1.223 | 1.509, 2.043, 1.999, 2.045, 2.023 | 1.205 / 1.489 | 0.970 | 0.205 | 1.042 | False | 0.2145 / 0.2145 | 0.0% |
| 2/B | hnsw_standard | 10% | 1.156, 1.136, 1.096, 1.259, 1.230 | 1.704, 1.542, 1.474, 1.914, 2.020 | 1.195 / 1.470 | 0.974 | 0.239 | 1.149 | False | 0.4130 / 0.4130 | 0.5% |
| 2/B | hnsw_standard | 20% | 1.428, 1.643, 1.461, 1.286, 1.201 | 2.451, 2.869, 2.164, 2.109, 2.158 | 1.423 / 1.855 | 1.022 | 0.245 | 1.368 | False | 0.7480 / 0.7480 | 27.0% |
| 2/B | hnsw_standard | 50% | 1.271, 1.378, 1.156, 1.129, 1.222 | 2.265, 2.013, 2.052, 1.992, 2.165 | 1.243 / 1.706 | 1.014 | 0.325 | 1.221 | False | 0.9640 / 0.9640 | 99.5% |

## Matched arm comparison (each build kept separate)

B must strictly reduce median absolute log2(first/later) AND later-pass max/min in BOTH builds. Quality equality is reported separately and gates supported_without_quality_change. This is an engineering directional criterion, not significance.

| Build | Method | Filter | Median paired B/A query latency | Quality-identical queries |
|---:|---|---:|---:|---:|
| 1 | exact | 1% | 1.034 | 200/200 |
| 1 | exact | 5% | 0.917 | 200/200 |
| 1 | exact | 10% | 1.055 | 200/200 |
| 1 | exact | 20% | 0.997 | 200/200 |
| 1 | exact | 50% | 1.164 | 200/200 |
| 1 | hnsw_standard | 1% | 0.966 | 200/200 |
| 1 | hnsw_standard | 5% | 0.947 | 200/200 |
| 1 | hnsw_standard | 10% | 0.869 | 200/200 |
| 1 | hnsw_standard | 20% | 1.404 | 200/200 |
| 1 | hnsw_standard | 50% | 1.212 | 200/200 |
| 1 | hnsw_iterative | 1% | 1.157 | 200/200 |
| 1 | hnsw_iterative | 5% | 1.223 | 200/200 |
| 1 | hnsw_iterative | 10% | 0.933 | 200/200 |
| 1 | hnsw_iterative | 20% | 1.256 | 200/200 |
| 1 | hnsw_iterative | 50% | 1.272 | 200/200 |
| 2 | exact | 1% | 0.949 | 200/200 |
| 2 | exact | 5% | 1.014 | 200/200 |
| 2 | exact | 10% | 1.029 | 200/200 |
| 2 | exact | 20% | 0.996 | 200/200 |
| 2 | exact | 50% | 1.091 | 200/200 |
| 2 | hnsw_standard | 1% | 0.963 | 200/200 |
| 2 | hnsw_standard | 5% | 1.081 | 200/200 |
| 2 | hnsw_standard | 10% | 1.039 | 200/200 |
| 2 | hnsw_standard | 20% | 1.275 | 200/200 |
| 2 | hnsw_standard | 50% | 1.101 | 200/200 |
| 2 | hnsw_iterative | 1% | 1.016 | 200/200 |
| 2 | hnsw_iterative | 5% | 0.944 | 200/200 |
| 2 | hnsw_iterative | 10% | 0.943 | 200/200 |
| 2 | hnsw_iterative | 20% | 1.043 | 200/200 |
| 2 | hnsw_iterative | 50% | 0.889 | 200/200 |

## Prespecified directional criterion

| Method | Filter | Both-build timing criterion | Quality preserved | Supported without quality change |
|---|---:|---|---|---|
| exact | 1% | False | True | False |
| exact | 5% | False | True | False |
| exact | 10% | False | True | False |
| exact | 20% | True | True | True |
| exact | 50% | False | True | False |
| hnsw_standard | 1% | False | True | False |
| hnsw_standard | 5% | False | True | False |
| hnsw_standard | 10% | False | True | False |
| hnsw_standard | 20% | False | True | False |
| hnsw_standard | 50% | False | True | False |
| hnsw_iterative | 1% | False | True | False |
| hnsw_iterative | 5% | False | True | False |
| hnsw_iterative | 10% | False | True | False |
| hnsw_iterative | 20% | False | True | False |
| hnsw_iterative | 50% | False | True | False |

## Preparation costs (not part of primary measured latency)

| Build | Arm | Phase | Executions | Total query seconds |
|---:|---|---|---:|---:|
| 1 | A | disjoint_warmup | 300 | 3.225 |
| 1 | B | disjoint_warmup | 300 | 2.061 |
| 1 | B | measured_exposure | 3000 | 17.729 |
| 2 | A | disjoint_warmup | 300 | 2.497 |
| 2 | B | disjoint_warmup | 300 | 4.821 |
| 2 | B | measured_exposure | 3000 | 19.758 |

Per-condition preparation costs and normalized pass values are retained in analysis.json. Query-call totals exclude validation, journaling, pauses, and other workflow overhead.

## Provenance and scope

Generator SHA-256: `8a0d4ee8a448d0eed828e23b59db2d5da40047ce57197edbd641c4796063f0ad`.

Full artifact snapshots, source hashes where supplied, and code/worktree identity are in analysis.json. Input manifests are checked before and after analysis. This supplement does not replace source/ground-truth/query-plan verification.
