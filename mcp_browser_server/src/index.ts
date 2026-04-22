import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  goto,
  getPageContext,
  clickElement,
  typeText,
  pressKey,
  scrollDown,
  scrollUp,
  takeScreenshot,
  goBack,
  getCurrentUrl,
} from "./browser.js";

const server = new Server(
  { name: "mcp-browser-server", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// ── Tool definitions ──────────────────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "goto",
      description: "Navigate the browser to a URL.",
      inputSchema: {
        type: "object",
        properties: { url: { type: "string", description: "Full URL to navigate to" } },
        required: ["url"],
      },
    },
    {
      name: "get_page_context",
      description:
        "Read the current page. Returns the page content as Markdown (with interactive elements annotated as [ID:N]) and a map of element IDs to their type, visible text, and CSS selector.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "click_element",
      description: "Click an interactive element by its numeric ID from get_page_context.",
      inputSchema: {
        type: "object",
        properties: { id: { type: "number", description: "Numeric element ID from get_page_context" } },
        required: ["id"],
      },
    },
    {
      name: "type_text",
      description: "Type text into an input or textarea by its numeric ID.",
      inputSchema: {
        type: "object",
        properties: {
          id: { type: "number", description: "Numeric element ID" },
          text: { type: "string", description: "Text to type" },
        },
        required: ["id", "text"],
      },
    },
    {
      name: "press_key",
      description: "Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape').",
      inputSchema: {
        type: "object",
        properties: { key: { type: "string", description: "Key name (Playwright format)" } },
        required: ["key"],
      },
    },
    {
      name: "scroll_down",
      description: "Scroll the page down by 600px.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "scroll_up",
      description: "Scroll the page up by 600px.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "take_screenshot",
      description: "Take a screenshot of the current page. Returns a Base64-encoded PNG.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "go_back",
      description: "Navigate back to the previous page.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "get_current_url",
      description: "Return the URL of the current page.",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

// ── Tool dispatch ─────────────────────────────────────────────────────────────

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result: unknown;

    switch (name) {
      case "goto":
        result = await goto((args as { url: string }).url);
        break;
      case "get_page_context":
        result = await getPageContext();
        break;
      case "click_element":
        result = await clickElement((args as { id: number }).id);
        break;
      case "type_text":
        result = await typeText((args as { id: number; text: string }).id, (args as { id: number; text: string }).text);
        break;
      case "press_key":
        result = await pressKey((args as { key: string }).key);
        break;
      case "scroll_down":
        result = await scrollDown();
        break;
      case "scroll_up":
        result = await scrollUp();
        break;
      case "take_screenshot":
        result = await takeScreenshot();
        break;
      case "go_back":
        result = await goBack();
        break;
      case "get_current_url":
        result = await getCurrentUrl();
        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [{ type: "text", text: typeof result === "string" ? result : JSON.stringify(result, null, 2) }],
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      content: [{ type: "text", text: `ERROR: ${message}` }],
      isError: true,
    };
  }
});

// ── Start ─────────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stderr so it doesn't pollute the STDIO MCP channel
  process.stderr.write("MCP Browser Server running on stdio\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal error: ${err}\n`);
  process.exit(1);
});
