# Chronological milestone and commit history

This is the actual local Git history through the last benchmark-artifact commit.
The final documentation/checksum packaging is the commit containing this file;
its full identity is obtained with `git log -1 --format='%H %s'` at this checkpoint.
No benchmark was run during final packaging.

| Date | Commit | Recorded change |
|---|---|---|
| 2026-09-15 | `cd199a2` | Complete Milestone 1 pgvector smoke pipeline |
| 2026-09-15 | `61519cd` | Implement Milestone 2 qualification harness |
| 2026-09-15 | `8682a76` | Record and fix qualification version gate |
| 2026-09-15 | `8f537a4` | Tighten ground truth and query-level summaries |
| 2026-09-15 | `0f5fe34` | Record corrected 10k SIFT preflight |
| 2026-09-29 | `97eb5b0` | Correct and harden Milestone 2 qualification harness |
| 2026-09-29 | `6708bfa` | Handle nanosecond percentile roundoff in independent verification |
| 2026-09-29 | `8f62bb3` | Record independently verified corrected 10k SIFT preflight |
| 2026-09-29 | `5549ad1` | Preserve permission-blocked 100k qualification attempt |
| 2026-09-29 | `1b68328` | Record verified physical 100k SIFT qualification |
| 2026-09-29 | `5d6a16f` | Enable restart-verified standalone 100k rounds with strict scope gates |
| 2026-09-29 | `3692827` | Add checksum-linked qualification figures and measurement table |
| 2026-09-29 | `e7952e5` | Record verified full 100k round 1 and academic progress evidence |
| 2026-09-29 | `f671005` | Record verified full 100k round 2 and independent campaign proof |
| 2026-09-29 | `fa5a03f` | Complete academic evidence and larger-scale review checkpoint |

`0f5fe34` was the starting HEAD for the resumed work. The ten subsequent
commits above were created during this resume, followed by the containing
final evidence-packaging commit. Original uncommitted changes were preserved
before the first of those commits. No prior run was rewritten.

## Full commit identities

```text
cd199a2b523b875ab06a8de00953e17672a2800a  Complete Milestone 1 pgvector smoke pipeline
61519cd73247b9ed976de3ac7f2245c75d1a5670  Implement Milestone 2 qualification harness
8682a76e61cbe14095d71880fcaf6169ef47ec40  Record and fix qualification version gate
8f537a4d02c405ae9235859ed41c88276b53ce99  Tighten ground truth and query-level summaries
0f5fe348813934e9f93ccb483be2979feac59d8c  Record corrected 10k SIFT preflight
97eb5b0ce324c76284c863dd9aeb0fe4471ac876  Correct and harden Milestone 2 qualification harness
6708bfaa6c41636aa1327a089b7f89916efbb84d  Handle nanosecond percentile roundoff in independent verification
8f62bb3f93ddafa6d8f30a224f6e4b5b6055793f  Record independently verified corrected 10k SIFT preflight
5549ad1675ba11c3bef7b936fccb553d62264e6f  Preserve permission-blocked 100k qualification attempt
1b683288f839b8054e788e11eda05818f33b429e  Record verified physical 100k SIFT qualification
5d6a16fdde9ba0c7e7dc3e0b8ea01c8e3c365dfc  Enable restart-verified standalone 100k rounds with strict scope gates
3692827fda9989f8af2e598d170a16d0c34a5a77  Add checksum-linked qualification figures and measurement table
e7952e5c1d8b22f5565945a24ef9259411d8f796  Record verified full 100k round 1 and academic progress evidence
f67100500bbfcc09bf7ccd3b1e42dd8e344fc801  Record verified full 100k round 2 and independent campaign proof
fa5a03f6babf533f6ed4f5a977c22373f55228a1  Complete academic evidence and larger-scale review checkpoint
```

## Execution chronology

1. Preserve starting work and history; reproduce and repair strict-profile failures.
2. Verify corrected single-vector/prepared-plan harness; commit it.
3. Run and independently verify corrected 10k preflight; preserve its immutable artifacts.
4. Preserve the permission-blocked 100k attempt; grant loopback access and execute the full bounded 100k qualification.
5. Verify qualification; add strictly scoped standalone-100k/restart support and descriptive qualification figures.
6. Physically rebuild 100k round 1, validate truth, obtain a real restart, execute and independently verify 15,000 timings; commit.
7. Physically rebuild 100k round 2, validate truth, obtain the second real restart, execute 15,000 timings; independently verify both as a pair and commit.
8. Package the final academic evidence and stop before 250k+ for review.
