# The post corpus

Every post the experiments have paid to read, in one append-only file with
one schema. Posts cost $0.005 each and only the paid full-archive endpoint
reaches back in time, so a post read and discarded is money spent twice —
and, worse, a gate change that cannot be evaluated.

## Files

| file | rows | what it is |
|---|---|---|
| `posts.jsonl` | 496 | the corpus. One row per post, deduped on X's post id |
| `labelled_cases.jsonl` | 17 | hand-transcribed gate examples. Kept separate because they have no timestamps and would otherwise read as "not actionable" |
| `labels.json` | — | human adjudication, declarative so labels are reviewable in a diff |

## Provenance

| source | rows | post ids | followers | notes |
|---|---|---|---|---|
| `blind2/keyword_rules` | 288 | ✓ | ✓ | re-fetched after `blind2.py` discarded them |
| `blind1/who_broke_it` | 98 | ✗ | ✓ | harness dropped the ids; these dedupe on a content hash |
| `gate_calibration` | 110 | ✗ | ✗ | cannot be scored against a follower floor |

## Labels

`breaker` — this post broke the story.
`chatter` — on-topic but not an announcement.
`unlabelled` — read, never adjudicated.

The gap between `chatter` and `unlabelled` is load-bearing. A market that
repriced with every post dropped is either a market where nothing was
posted or a false negative, and only a human reading the posts can say
which. Defaulting to `chatter` would quietly assert the flattering answer.

A market-level label is only applied where a human has read **every** post
in the window and established the breaker is not among them.

## Current state

125 labelled (5 breaker, 120 chatter), 371 unlabelled of which 309 are
actionable — the review queue, reachable via `corpus.needs_label()`.

## Scoring

`corpus.score()` builds a confusion matrix from stored gate answers against
the labels, counting only rows that are labelled, actionable (published
*before* the repricing) and above the follower floor:

| floor | scored | TP | FP | TN | FN | precision | recall |
|---|---|---|---|---|---|---|---|
| 0 | 125 | 4 | 1 | 119 | 1 | 80% | 80% |
| 10,000 | 23 | 3 | 0 | 20 | 0 | 100% | 100% |
| 50,000 | 8 | 2 | 0 | 6 | 0 | 100% | 100% |
| 250,000 | 2 | 1 | 0 | 1 | 0 | 100% | 100% |

Reproduced from stored data with no API calls. The 10k row is 23 posts and
3 breakers — real, but small; treat it as consistent with the blind test
rather than as an independent confirmation of it.

The two disagreements at floor 0:

- **False alarm** — @Jeffery_xbt (106f) on Arcium, the one measured false
  positive of blind test 2. Removed by the 10k floor.
- **Miss** — @Mario19940 (757f) retweeting @SprinterPress on Burnham. The
  gate fired on the original and dropped the retweet. The market was still
  caught, so this is a post-level miss, not a market-level one.

## Adding to it

Any harness that reads posts should write `corpus.Post` rows and call
`corpus.add()`. Rows merge on post id, so a re-fetch with richer fields
upgrades the existing row rather than duplicating it, and a row's label
survives the upgrade.

Full gate answers are stored, not just fire/drop — so changing one question
means re-reading the other five from disk and re-calling only the rows
whose verdict turns on the change.
