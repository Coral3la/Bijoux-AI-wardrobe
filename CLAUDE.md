# Bijoux — agent instructions

AI wardrobe: photograph your clothes, get them tagged automatically, receive
outfit recommendations from your own wardrobe, and generate a weather-aware
packing list for a trip.

Stack: Angular 22 + FastAPI + PostgreSQL + Cloudinary + OpenAI.

## Read these before doing anything

1. `docs/README.md` — documentation map and how the docs relate
2. `docs/CONVENTIONS.md` — coding standards and definition of done
3. `docs/PROGRESS.md` — which stage is currently active
4. The active stage file in `docs/stages/`

The documents are the source of truth. If code and docs disagree, one of them
is wrong — say so and ask which, do not silently pick a side.

## Git — the developer commits, never the agent

**Never run a git command that writes to the repository.**
Forbidden: `commit`, `push`, `add`, `branch`, `checkout`, `switch`, `merge`,
`rebase`, `reset`, `revert`, `tag`, `stash`, `cherry-pick`.

Allowed and encouraged: `status`, `diff`, `log`, `show`.

At the end of every task, print a suggested commit message in a fenced code
block, then stop. Do not stage. Do not commit.

## How we work

The developer is building this project in order to learn it, and will have to
defend every file in it. You may write code — but nothing moves forward until
she has understood it and said so.

### Before each task

Orientation first, no code:

- what this task produces, in two or three sentences
- which files it creates or changes
- where each one sits in the architecture, and what will import it later
- which earlier file it depends on

Then stop and wait.

### Delivering a file

Default: **print it, do not write it.** Output the full contents in a fenced
code block whose first line is a comment with the target path. She creates the
file and pastes it in herself. This is deliberate — it is how she reads the
structure on the way past, so do not optimise it away.

Before the block, explain:

- what the file is responsible for
- what it imports, and what will import it
- the two or three decisions inside it that could have gone another way

Files longer than roughly 60 lines: deliver in labelled sections, with the
explanation for each section immediately before that section. Never dump a
long file as one uninterrupted wall of code.

After the block, stop. Wait for "approved" or "next". Answer any questions
before moving on.

If she says "write it yourself", use your file tools for that one file —
still explain first. If she says she wants to write a file herself from your
instructions, switch to describing it step by step and do not print it whole.

### Commands

**Never run a command that changes anything.** No installs, no scaffolding
generators, no migrations, no dev servers, no builds, no test runs.

Print it instead:

- the command, in a copyable block
- what it will do
- what she should see if it worked, and the likeliest way it fails

She runs it and reports back.

Read-only inspection needs no permission: `ls`, `cat`, `git status`,
`git diff`, `git log`. If you need something else run, ask for it.

### After each task

- two lines on what now exists and what it connects to
- one question she should be able to answer about what was just built
- the suggested commit message

## One task at a time

Stage files contain numbered tasks. Do **one** task, then stop and wait.
Do not continue to the next task unprompted, and do not build anything listed
under "Out of scope for this stage" — not even a disabled placeholder.

## Ask instead of assuming

When a requirement is ambiguous, missing from the docs, or contradicts them,
stop and ask. A wrong assumption carried forward costs more than a question.

## Secrets

Never write real credentials to any file. `.env` is created by the developer
and is git-ignored. You may create and edit `.env.example` with placeholder
values only.

## Code style

No comments unless the *why* is genuinely non-obvious from the code — see the
examples in `docs/CONVENTIONS.md`. No dead code, no speculative abstraction,
no "future-proofing" for features not in the current stage.
