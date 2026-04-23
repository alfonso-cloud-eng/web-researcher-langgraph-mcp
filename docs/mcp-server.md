# MCP Browser Server

## Overview

The browser server is a TypeScript process (`mcp_browser_server/`) that controls a Chromium instance via Playwright and exposes browser actions as MCP tools over STDIO. The Python agent starts it as a subprocess and communicates with it using the Model Context Protocol.

**Source files:**
- `mcp_browser_server/src/browser.ts` — Playwright logic, one exported function per tool
- `mcp_browser_server/src/index.ts` — MCP server bootstrap, tool registration, request dispatch

**Build output:** `mcp_browser_server/dist/` (compiled JS, run with `node dist/index.js`)

### How the connection works

```
Python process
  └─ MultiServerMCPClient (langchain-mcp-adapters)
       └─ client.session("browser")          ← persistent STDIO session
            └─ spawns: node dist/index.js    ← this server
                 └─ Playwright → Chromium (headless)
```

A single Playwright `Browser` and `Page` instance are reused for the entire agent run. The browser is launched headless with a 1280×800 viewport and `Accept-Language: en-US`.

---

## Browser tools

### `goto`

Navigate to a URL and wait for `domcontentloaded`.

| Parameter | Type | Description |
|---|---|---|
| `url` | `string` | Full URL to navigate to |

Returns: `"Navigated to {url}"`

Timeout: 30 s.

---

### `get_page_context`

Read the current page. Injects numeric IDs into every interactive element (`a[href]`, `button`, `input`, `select`, `textarea`, `[role=button]`, `[role=link]`), converts the page body to Markdown via Turndown, and returns both.

No parameters.

Returns a JSON object:
```json
{
  "markdown": "...",
  "elements": {
    "1": {"type": "link", "text": "Home", "selector": "[data-mcp-id='1']"},
    "2": {"type": "button", "text": "Submit", "selector": "[data-mcp-id='2']"}
  }
}
```

- `markdown` is capped at 20 000 characters. Tags `script`, `style`, `noscript`, and `iframe` are stripped before conversion.
- Each interactive element appears in the Markdown as `[visible text [ID:N]](href)`.
- IDs are reassigned from 1 on every call. Old IDs are invalidated after any navigation.
- The injected `data-mcp-id` attributes are removed from the live DOM after the snapshot is taken.

---

### `click_element`

Click an element by its numeric ID from the most recent `get_page_context` call.

| Parameter | Type | Description |
|---|---|---|
| `id` | `number` | Numeric element ID |

Returns: `"Clicked element {id}. Current URL: {url}"`

Waits for `domcontentloaded` after the click (up to 15 s, soft — does not fail on timeout). Throws if the ID is not in the current element map.

---

### `type_text`

Fill an input or textarea identified by its numeric ID.

| Parameter | Type | Description |
|---|---|---|
| `id` | `number` | Numeric element ID |
| `text` | `string` | Text to type |

Returns: `"Typed "{text}" into element {id}"`

Uses Playwright `fill()` which clears the field first.

---

### `press_key`

Press a keyboard key using Playwright's key notation.

| Parameter | Type | Description |
|---|---|---|
| `key` | `string` | Key name, e.g. `"Enter"`, `"Tab"`, `"Escape"`, `"ArrowDown"` |

Returns: `"Pressed key: {key}"`

Waits for `domcontentloaded` after the keypress (up to 10 s, soft).

---

### `scroll_down`

Scroll the current viewport down by 600 px.

No parameters. Returns: `"Scrolled down 600px"`

---

### `scroll_up`

Scroll the current viewport up by 600 px.

No parameters. Returns: `"Scrolled up 600px"`

---

### `take_screenshot`

Capture the current viewport as a PNG.

No parameters. Returns: Base64-encoded PNG string.

---

### `go_back`

Navigate back in the browser history and wait for `domcontentloaded`.

No parameters. Returns: `"Went back. Current URL: {url}"`

Timeout: 15 s.

---

### `get_current_url`

Return the URL of the page currently loaded in the browser.

No parameters. Returns: the current URL as a plain string.

---

## Build & run

```bash
cd mcp_browser_server
npm install
npm run build          # compiles TypeScript → dist/
npx playwright install chromium   # download browser binary (first time only)
```

The Python agent starts the server automatically via `mcp_client.py`. You do not need to run it manually.
