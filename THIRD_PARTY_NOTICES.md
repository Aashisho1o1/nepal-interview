# Third-party notices

Inspected 1 November 2026 (shallow clones; exact commits below).

| Source | Commit | License | What we use |
|---|---|---|---|
| simliai/create-simli-app-livekit-agents | `e85f8ea6c6e11f4175e318ff4e849e82dc9f3749` (2026-10-26) | MIT, © 2026 Simli | `Trinity2Config` (adapted in `services/agent/interview_agent/adapters.py`); agent start/join/fallback order; Next.js scaffold (`next.config`, `tsconfig`, eslint config) |
| livekit-examples/agent-starter-python | `469650c20ad1e808f65d667c10f05b22423fe2af` (2026-10-22) | MIT, © 2025 LiveKit, Inc. | Reference only: AgentSession/cascade configuration, AGENTS.md testing guidance. Cascade model ids in `CascadeVoice` defaults come from it |
| livekit-examples/agent-starter-react | `9e1fc2f40fd7ceaccbe4a872b21765b49eefea80` (2026-10-19) | MIT, © 2025 LiveKit, Inc. | Reference only (not copied); far heavier dependency tree than this milestone needs |

Not copied: the Simli starter's `ABCRepro*` font files and Simli logo/media. They ship in an MIT repository but are Simli's brand assets; an MIT code license is not evidence of a font or trademark license.

Runtime dependencies are pinned in `pyproject.toml` (livekit-agents / plugins 1.8.9, the versions the Simli starter pins) and `apps/web/package-lock.json` (next 16.4.3, react 19.3.0, livekit-client 2.23.0). Transitive licenses have not yet been audited.

Hosted services (LiveKit Cloud, Simli, OpenAI) are paid services under their own terms. The MIT license on integration code grants no rights to those services, their stock faces, or voices. Confirm commercial rights to the face set in `SIMLI_FACE_ID` before any paid use.

MIT License text (applies to the adapted Simli code):

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
