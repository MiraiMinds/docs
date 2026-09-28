> **Customize this file**: Tailor this template to your project by noting specific contribution types you're looking for, adding a Code of Conduct, or adjusting the writing guidelines to match your style.

# Contribute to the documentation

Thank you for your interest in contributing to our documentation! This guide will help you get started.

## How to contribute

### Option 1: Edit directly on GitHub

1. Navigate to the page you want to edit
2. Click the "Edit this file" button (the pencil icon)
3. Make your changes and submit a pull request

### Option 2: Local development

1. Fork and clone this repository
2. Install the Mintlify CLI: `npm i -g mint`
3. Create a branch for your changes
4. Make changes
5. Navigate to the docs directory and run `mint dev`
6. Preview your changes at `http://localhost:3000`
7. Commit your changes and submit a pull request

For more details on local development, see our [development guide](development.mdx).

## Writing guidelines

- **Use active voice**: "Run the command" not "The command should be run"
- **Address the reader directly**: Use "you" instead of "the user"
- **Keep sentences concise**: Aim for one idea per sentence
- **Lead with the goal**: Start instructions with what the user wants to accomplish
- **Use consistent terminology**: Don't alternate between synonyms for the same concept
- **Include examples**: Show, don't just tell

## Write a cookbook

Cookbooks are end-to-end recipes for one use case. They live in `cookbooks/`
and in the **Cookbooks** tab of `docs.json`, grouped by the kind of product
(for example **Browser voice apps**). Add a new group when a recipe does not fit
an existing one, and add a card for the recipe to `cookbooks/overview.mdx`.

Rules:

- **Describe a use case, never a customer.** Do not name the company that asked
  for the recipe, its product or its people.
- **Use only shipped, documented features.** Link to the reference page for
  every field and error code instead of repeating the reference.
- **Make the code complete.** A reader should be able to copy each block and run
  it after replacing clearly marked stand-ins (`db`, `queue`, sign-in helpers).
  Give cURL, Python and Node.js where the step is an API call.
- **Keep secrets on the server.** No example may put an API key in a browser.
- **Include a short test configuration** that shows every behaviour in a few
  minutes, and a troubleshooting table.
- **Cover privacy and compliance** for the use case: what is stored, what users
  must be told, and where a person must stay in the loop.

Every cookbook uses this outline:

```mdx
---
title: <What you build, in plain words>
description: <One sentence: the outcome and the main parts.>
---

<One paragraph: what this recipe builds and which other use cases it fits.>

## What you'll build
<Bullets of the finished behaviour. "You need:" line.>

## How it works
<Sequence diagram and, when time matters, a timeline table.>

## Step 1: <Verb the first thing>
## Step 2: <…>
<One step per moving part. Code tabs: cURL, Python, Node.js.>

## Test it
<Short test values, what to try, and a symptom / cause / fix table.>

## Privacy and compliance
## Production checklist
## Related
<CardGroup linking the reference pages used.>
```

Before opening a pull request, run `mint broken-links --check-anchors` and
check that every example request matches the current API reference.
