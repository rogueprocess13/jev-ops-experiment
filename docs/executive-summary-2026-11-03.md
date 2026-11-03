# Executive summary: can an AI tool help run IT systems? (2026-11-03)

## The question

Jev is an AI tool from TypeSafe. We wanted to know if it can watch a computer system, notice when something breaks, and say how to fix it. We tested it from 30 September to 2 November 2026. We compared it with Claude Opus, an AI model from Anthropic.

## How we tested it

We broke parts of a demo online shop on purpose, in ten different ways. Each time, the AI read the shop's data and answered four questions:

1. Is something wrong?
2. Which part broke?
3. What kind of problem is it?
4. What should we do about it?

We wrote the right answers ourselves before the tests, and the AI never saw them. In the last round, the computer carried out the AI's advice once, and we checked if the shop recovered.

## What we found

Jev is good at noticing problems. It caught all 18 problems in the last round.

Jev is weak at finding the part that broke. It often blamed the part that showed the error, not the part that caused it. For example, it blamed the shop's front page when the shopping cart service had stopped. Jev named the right part in 9 of 18 tests. Claude Opus named it in 18 of 18.

This decides whether the fix works, because the fix goes to the part that the AI names. Jev's advice fixed 3 of 18 problems. Claude Opus's advice fixed 11 of 18. Both AIs chose a sensible kind of fix every time. The difference was where they aimed it.

Jev raised fewer false alarms. In the 22 tests where nothing was wrong, Jev reported a problem 4 times and Claude Opus 7 times.

Jev is fast and cheap. It answers in about 0.4 seconds, and Claude Opus takes about 2.2 seconds. One batch of 40 tests cost about 5 cents with Jev and about 6.21 dollars with Claude Opus.

We tried to improve Jev with clearer question wording, a different alarm cut-off and a clearer layout of the data. None of these fixed its weak spots.

## The numbers people ask for

| | Jev | Claude Opus | What it means |
|---|---|---|---|
| F1 score | 0.90 | 0.84 | How good the alarm is, from 0 to 1. It counts missed problems and false alarms. It does not check the diagnosis. |
| Time to detect (MTTD) | 16.6 seconds | 18.7 seconds | From the break until the AI says that something is wrong. We checked every 15 seconds, so most of this is the wait for the first check. |
| Time to recover (MTTR) | 106.2 seconds, from 3 fixes | 122.7 seconds, from 11 fixes | From the break until the shop worked again. Read the number of fixes first. |

All timings are middle values from the last round.

## What this means

Jev is a good, fast and cheap alarm. It is not yet good enough to decide on its own what to fix.

## Our recommendation

Use Jev to watch the system and raise the alarm. When it raises one, hand the case to a stronger AI or to a person, who finds the broken part and fixes it. Test this split as the next step, before anyone uses it on real systems.

## Limits

- The tests are small. We tested each problem 3 times, so a difference of 2 or 3 tests can be chance.
- We used one demo app and carried out each piece of advice only once, with no second try.
- We wrote the right answers ourselves. On a few unclear cases, a person can reasonably agree with Jev.

Full details are in the [one-page summary](results-2026-11-02-summary.md). Every number on this page comes from it or from the [Tier 4 results page](results-2026-11-02-tier4-jev-vs-opus-api.md).
