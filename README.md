# Airport Chaos (CP3)

CSC310 Algorithms and Data Structures, final project.

This is a command-line simulator for airport runway scheduling. It loads the flight CSV, keeps every flight in our own hash table, keeps one BST per runway, checks for conflicts, and handles the three crisis scenarios (runway closure, emergency insert, mass cancel). It also has the sorting, divide and conquer, matrix multiplication and perfect hashing parts from the handout.

We used Python. You only need Python 3.10 or newer to run it. matplotlib is only used to draw the benchmark charts, the program and the tests work without it.

## How to run

Run everything from the main folder of the repo.

```
python main.py
```
opens the numbered menu.

```
python main.py --batch scenarios/scenario_a_runway_closure.txt
```
runs a file of commands, one command per line.

```
python main.py --cmd "LOAD airport_flights.csv" --cmd STATS
```
runs commands straight from the terminal.

Other scripts:

```
python run_tests.py                     all automated tests
python scenarios/run_scenarios.py       scenarios A, B and C, each one from a fresh LOAD
python benchmarks/run_benchmarks.py     benchmarks (add --full for bigger sizes)
python tools/generate_dataset.py --flights 10000 --runways 8 --order shuffled --out data/big.csv
```

The scenario files expect `airport_flights.csv` in the main folder. On some machines you have to type `python3` instead of `python`.

## Folders

```
main.py                  starts the program
airport_flights.csv      official data file (not modified)
airport_chaos/           the source code
    hashtable.py         flight registry (universal hashing + linear probing)
    bst.py               runway BST
    engine.py            all the operations and the crisis scenarios
    sorting.py           counting sort, radix sort, merge sort
    dnc.py               maximum subarray
    matrix.py            classical and Strassen
    perfect_hash.py      FKS perfect hashing
    cli.py               menu, batch mode, command parsing
    timeutil.py, flight.py, tracing.py, benchmarks.py, datagen.py
tests/                   unit tests
scenarios/               command files for the scenarios
benchmarks/              benchmark script
tools/                   script to make extra test datasets
data/                    synthetic datasets we made for scale tests
```

## Commands

Times are written as `YYYY-MM-DD HH:MM`. You can put them in quotes or not, both work. Command names can be upper or lower case, but flight IDs are case sensitive.

```
LOAD <file>
STATS
LIST_RUNWAY <runway> [<from> <to>]
FIND <flight_id>
ADD <flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>
CANCEL <flight_id>
RESCHEDULE <flight_id> <new_start> [<runway>]
CHECK_CONFLICT <runway> <start> <end>
RUNWAY_CLOSURE <runway> <start> <end>
EMERGENCY_INSERT [<flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>] [ACCEPT|REJECT]
MASS_CANCEL <start> <end>
SORT_PRIORITY [<limit>]
SORT_ID [EXACT|NUMERIC] [<limit>]
STABILITY_DEMO
ANALYZE [ALL|DISRUPTION|ROUTES] [<strassen_cutoff>]
PERFECT_HASH [<rule_id> ...]
BENCHMARK [ALL|HASH|BST|SORT|MATRIX] [QUICK|FULL]
VALIDATE
TRACE [ON|OFF]
HELP
EXIT
```

What they do:

- `LOAD` clears everything and loads a CSV. Bad rows (wrong timestamp, duplicate ID, bad priority, overlapping flight) are skipped and listed with their line number.
- `STATS` shows how many flights are scheduled, delayed or cancelled, the size and height of each runway tree, and the hash table numbers (p, a, b, m, load factor, collisions, probes).
- `LIST_RUNWAY` prints a runway in time order. If you give a from/to time it only shows flights that start in that range.
- `FIND` looks up a flight in the hash table, shows how many probes it took, and shows the flight before and after it on the same runway.
- `ADD` only inserts the flight if the slot is free. If not, it shows which flights are in the way and the next free slot.
- `CANCEL` sets the flight to CANCELLED and takes it out of the runway tree. It stays in the registry.
- `RESCHEDULE` moves a flight to a new start time (and runway if you give one), keeping the same duration, but only if the new slot is free.
- `CHECK_CONFLICT` tells you if a time slot is free on a runway.
- `RUNWAY_CLOSURE`, `EMERGENCY_INSERT` and `MASS_CANCEL` are scenarios A, B and C (see below).
- `EMERGENCY_INSERT` with no flight details uses the official EM90001 flight (EM, JFK to BOS, R1, 09:00 to 09:05, priority 1). If there is a conflict, `ACCEPT` puts it in the suggested slot and `REJECT` doesn't. In the menu it asks you.
- `SORT_PRIORITY` and `SORT_ID` run our sorts and check the result.
- `ANALYZE` runs the disruption analysis and the route matrix.
- `VALIDATE` checks that the hash table and the runway trees agree and that no flights overlap.
- `TRACE ON` prints hash probes, BST search paths and neighbours, and sorting passes. We use it to show how things work step by step.

Example:

```
LOAD airport_flights.csv
STATS
RUNWAY_CLOSURE R1 "2026-11-27 09:00" "2026-11-27 11:00"
STATS
```

To run a different scenario, LOAD the file again first so you start from the original data.

## How it works

### Times
We turn every timestamp into the number of minutes since 2000-01-01 00:00 so we can compare and subtract them as integers. A flight occupies `[start, end)`, so a flight ending at 09:20 and one starting at 09:20 don't conflict. Durations are always end minus start from the file, we never assume 5 minutes.

### Flight registry (hash table)
The flight IDs are strings, so first we turn them into a number:

```
k = (c0*257^(L-1) + c1*257^(L-2) + ... + c(L-1)) mod p
```

where c is the character code. We compute it with Horner's rule.

Then the hash is `h(k) = ((a*k + b) mod p) mod m` with:

- p = 2^61 - 1 = 2305843009213693951 (prime, and bigger than any encoded key)
- a picked randomly from 1 to p-1, b from 0 to p-1, using a fixed seed (310) so results are the same every run
- m starts at 16 and doubles when needed

Collisions are handled with linear probing. Since two different IDs can end up with the same number, every lookup compares the real ID string, not just the number. Deleting leaves a tombstone so the probe chain doesn't break. When (size + tombstones) / m goes above 0.5 we rehash into a bigger table with new a and b, and the tombstones get removed.

### Runway BSTs
Each runway has its own unbalanced BST. The key is (start_time, flight_id) and each node also stores the end time, the flight and a parent pointer. It supports insert, search, delete (including the two-children case, where we use the in-order successor), in-order listing, predecessor, successor and range search.

The rule we keep is that flights on the same runway never overlap. Because of that, to check a new slot [s, e) we only need:

1. the predecessor (the last flight starting before s): it conflicts only if it ends after s
2. the successor and the ones after it: each one that starts before e is a conflict

Finding them costs O(h), where h is the tree height. If flights are inserted in random order h is about log n, but if they come in sorted order (like a CSV sorted by time) the tree becomes a line and h = n, so it's O(n) in the worst case.

The hash table and the trees are always updated together, and `VALIDATE` checks they agree.

### Crisis scenarios
For a runway closure, the affected flights are taken off the runway and sorted by priority, then original start time, then flight ID. We build that order with our own sorts (radix sort on ID, then radix sort on start time, then counting sort on priority, all stable).

Each flight then tries the closure end time, then +5 minutes, +10 and so on, on the same runway. It takes the first free slot as long as the delay from its original start is at most 120 minutes. If nothing fits, it gets cancelled. Flights that weren't affected are never moved.

- Scenario A closes R1 from 09:00 to 11:00. Any R1 flight that overlaps that window is affected.
- Scenario B tries to add EM90001 on R1 at 09:00. It shows the conflicts, then looks for the earliest free slot after that in 5-minute steps without moving anyone. It only inserts into a free slot.
- Scenario C cancels every active flight that starts between 14:00 and 15:00, on all runways. They stay in the registry as CANCELLED.

Every report shows the flight IDs, old and new times, status, the flights blocking the first slot tried, and totals (affected, delayed, cancelled, total delay minutes).

### Sorting
- Counting sort on priority (1 to 3). It is stable because we fill the output from left to right using the running counts. O(n + k).
- LSD radix sort on integers, base 256, one counting pass per byte. O(d(n + b)).
- For flight IDs in real alphabetical order we do a radix sort on the characters. Shorter IDs are padded with a value smaller than any character so "AA" comes before "AA1".
- `SORT_ID NUMERIC` sorts by the encoded number instead. That is not alphabetical order. If two IDs have the same number, the real ID decides.

Any sort that only compares elements can be drawn as a decision tree with at least n! leaves, so it needs at least log2(n!) = Ω(n log n) comparisons. Counting sort and radix sort never compare two elements, they use the key values as array indexes, so that bound doesn't apply to them.

We also wrote a merge sort to compare against in the benchmarks.

### Disruption analysis (divide and conquer)
We split the day into 5-minute buckets (288 for one day, more if the data covers more days). Each bucket counts the flights whose original start falls in it and whose status is now DELAYED or CANCELLED.

Then we find the run of buckets with the biggest total using divide and conquer: best in the left half, best in the right half, or best crossing the middle. That gives T(n) = 2T(n/2) + O(n), which is O(n log n). An O(n²) version checks the answer.

If there is a tie we pick the shorter range, then the earlier one, and both versions follow the same rule so they always give the same indexes. If everything is zero (nothing delayed or cancelled yet), the answer is 0 at bucket 0 and the program says there is no disruption.

### Route matrix (classical and Strassen)
We list the airports in alphabetical order and build A, where A[i][j] is the number of flights from airport i to airport j. A×A then counts two-leg routes i → k → j. This is only a rough count of possible routes, not passengers or real connections.

- Classical multiplication is the triple loop, O(N³).
- Strassen pads the matrix with zeros up to the next power of 2, does 7 recursive multiplications instead of 8, then cuts the result back to the original size. Under the cutoff size (32 by default, you can change it in ANALYZE) it switches to classical. T(n) = 7T(n/2) + O(n²), about O(n^2.81).

Strassen is usually slower for small matrices. It needs a lot of extra additions and new sub-matrices at each level, and padding can make the matrix almost twice as big (10 airports become 16). It only starts to pay off for big N with a good cutoff.

### Perfect hashing
For the 20 fixed rule IDs we use two-level (FKS) hashing with p = 10007:

- Level 1 has 20 buckets with `h(k) = ((a*k + b) mod p) mod 20`. We keep picking new a and b until the sum of (bucket size)² is at most 80.
- Each bucket with s keys gets its own table of size s² and its own a and b, picked again until there are no collisions.

A lookup is two hash calculations and one comparison, so O(1) even in the worst case. Storage is the 20 level-1 cells plus the sum of s² level-2 slots, plus 2 numbers per non-empty bucket.

## Complexity

| Operation | Time |
|---|---|
| Hash insert / lookup / delete | O(1) expected, O(m) worst case |
| Rehash | O(m), O(1) amortized per insert |
| BST insert / search / delete / predecessor / successor | O(h): O(log n) on average, O(n) worst case |
| Conflict check | O(h + number of conflicts) |
| Range search | O(h + number of results) |
| Runway closure | O(a · (h + w)), a = affected flights, w = slots tried (at most 25 each) |
| Counting sort | O(n + k) |
| Radix sort | O(d(n + b)) |
| Max subarray | O(n log n), brute force O(n²) |
| Classical / Strassen | O(N³) / O(N^2.81) |
| Perfect hash lookup | O(1) worst case |

## Tests

`python run_tests.py` runs 47 tests covering:

- CSV parsing, duplicate IDs, bad timestamps and other bad fields
- hash collisions (forced by making every ID hash to the same number), tombstones and resizing
- BST root deletion (leaf, one child, two children), predecessor/successor, range search
- touching flights not counting as a conflict, different runways not conflicting, a conflicting insert being refused
- scenarios A, B and C compared against a simple brute-force version, plus a fresh LOAD test for each one
- sorting stability, string radix sort vs normal alphabetical order
- max subarray vs the O(n²) version and the all-zero case
- Strassen vs classical on odd and even sizes
- perfect hashing, batch mode
- hash table and trees still matching after 300 random changes

Most tests use generated data with the same columns as the official file but different sizes and numbers of runways. If `airport_flights.csv` is in the main folder, the scenario tests run on it too.

## Benchmarks

`python benchmarks/run_benchmarks.py` saves CSV files, charts and the machine details to `benchmarks/results/`. It measures:

- hash lookups at load factors from 0.1 to 0.95, compared with the expected number of probes for linear probing
- BST insert and search with sorted keys vs shuffled keys
- counting sort and radix sort vs merge sort
- classical vs Strassen for different sizes and cutoffs

Each test is repeated (3 times in quick mode, 5 in full mode) and we keep the best time. The official CSV is what we use to check correctness. The synthetic files in `data/` are only for testing bigger inputs.

## Interview version

The version for the interview is tagged `interview-2026-11-28`.
