# Contributing to Uoink

Uoink is the local corpus and agent layer for AI-native creators and the developers building alongside them. Glad you're here.

## Getting started

1. **Good first issues**: the issue tracker's `good first issue` label marks scoped tasks sized for a first PR.
2. **Discussions**: got a feature idea? Raise it in GitHub Discussions before you write code, so the work lands on the roadmap instead of beside it.
3. **Local setup**: clone the repo, run `npm install` for the UI, and set up your Python environment for the backend. The README has the full instructions.

## Pull requests

1. **One PR, one thing.** Fixing a bug and adding a feature? That's 2 PRs.
2. **Tests**: run `pytest tests/` before submitting. All tests must pass, and a new feature needs a test of its own.
3. **Linting**: linting is strict here. Run the CI workflow's static checks locally and catch issues before the bot does.

## Voice DNA (read this before writing any copy)

Any feature that generates text (prompts, UI copy, or agent outputs) must follow Uoink's Voice DNA. We write like sharp humans, not language models.

- **Contractions**: use them naturally (don't, can't, won't).
- **Formatting**: short paragraphs. 1-3 sentences max.
- **Punctuation**: NO em dashes ever. Use commas, periods, colons, or parentheses.
- **Tone**: get to the point. No throat-clearing. Use physical verbs for abstract processes ("sanded down" not "improved").
- **Banned AI language**: never use "delve," "harness," "landscape," "supercharge," or "game-changer." Never use "This isn't X. This is Y."

Check your copy against these rules before submitting.

Thanks for building with us.
