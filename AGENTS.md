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
