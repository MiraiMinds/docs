# Voice Agents Documentation Project

## About this project

- This is the official documentation for Voice Agents platform
- Built on [Mintlify](https://mintlify.com)
- Pages are MDX files with YAML frontmatter
- Configuration lives in `docs.json`
- Run `mint dev` to preview locally
- Run `mint broken-links` to check links

## Terminology

- Use "voice agent" not "voice bot" or "AI assistant"
- Use "workspace" not "account"
- Use "campaign" for outbound call operations
- Use "assistant" for voice agent configurations
- Use "integration" not "connection" or "plugin"

## Style preferences

- Use active voice and second person ("you")
- Keep sentences concise — one idea per sentence
- Use sentence case for headings
- Bold for UI elements: Click **Settings**
- Code formatting for file names, commands, paths, and code references
- Use `<Note>`, `<Tip>`, `<Warning>` components for callouts
- Include code examples in multiple languages when applicable (cURL, Node.js, Python)

## Content boundaries

- Document public-facing features only
- Don't document internal admin tools
- Include security best practices
- Always mention compliance considerations where relevant (HIPAA, GDPR, TCPA)
- Focus on practical implementation guidance

## API Documentation Standards

- Include complete request/response examples
- Document all required and optional parameters
- Show common error scenarios
- Provide working code examples
- Include authentication details

## API reference tab (generated)

- The **API reference** tab and `api-reference/openapi.json` are generated.
  Never edit them by hand.
- The hosted docs serve only images, audio, video and fonts as files: `.json`,
  `.zip`, `.pdf` and `.csv` answer 404. Link downloads to where they live (the
  Postman files: `https://console.voice.miraiminds.co/static/postman/`).
- Rebuild after every API release that changes an endpoint:
  `python3 scripts/build_api_reference.py` (reads the live Postman collection and
  `GET /v2/schema`); `--check` exits 1 when the committed files are stale.
- Fix wording at the source: the Postman spec in `MiraiMinds/mirai-voice`
  (`scripts/postman/spec/`). Hand-written pages are `api-reference/introduction.mdx`,
  `api-reference/postman.mdx` and `api-reference/calls/start-a-browser-call.mdx`.
- There is no v1 documentation. Old v1 URLs redirect to their v2 pages in `docs.json`.
