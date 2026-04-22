import { chromium, Browser, Page } from "playwright";
import TurndownService from "turndown";

const turndown = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced" });

// Remove non-content tags before converting
turndown.remove(["script", "style", "noscript", "iframe"]);

let browser: Browser | null = null;
let page: Page | null = null;

// Map of assigned numeric IDs to CSS selectors for interactive elements
let elementMap: Record<number, string> = {};

async function ensureBrowser(): Promise<Page> {
  if (!browser) {
    browser = await chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });
  }
  if (!page || page.isClosed()) {
    page = await browser.newPage();
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.setExtraHTTPHeaders({
      "Accept-Language": "en-US,en;q=0.9",
    });
  }
  return page;
}

export async function goto(url: string): Promise<string> {
  const p = await ensureBrowser();
  await p.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  return `Navigated to ${url}`;
}

export async function getPageContext(): Promise<{ markdown: string; elements: Record<number, { type: string; text: string; selector: string }> }> {
  const p = await ensureBrowser();

  // Inject IDs into all interactive elements
  const elements = await p.evaluate(() => {
    const selectors = ["a[href]", "button", "input", "select", "textarea", "[role='button']", "[role='link']"];
    const all = document.querySelectorAll(selectors.join(","));
    const result: Array<{ id: number; type: string; text: string; selector: string }> = [];
    let counter = 1;

    all.forEach((el) => {
      const htmlEl = el as HTMLElement;
      const id = counter++;
      htmlEl.setAttribute("data-mcp-id", String(id));

      const tag = el.tagName.toLowerCase();
      const type = tag === "a" ? "link" : tag === "input" ? (el.getAttribute("type") || "input") : tag;
      const text = (htmlEl.innerText || el.getAttribute("value") || el.getAttribute("placeholder") || el.getAttribute("aria-label") || "").trim().slice(0, 80);

      // Build a reliable selector using the assigned attribute
      result.push({ id, type, text, selector: `[data-mcp-id="${id}"]` });
    });

    return result;
  });

  // Build element map for later clicks
  elementMap = {};
  const elementsDict: Record<number, { type: string; text: string; selector: string }> = {};
  for (const el of elements) {
    elementMap[el.id] = el.selector;
    elementsDict[el.id] = { type: el.type, text: el.text, selector: el.selector };
  }

  // Get the page HTML and convert to Markdown, replacing links with ID annotations
  const bodyHtml = await p.evaluate(() => {
    // Annotate links with their MCP ID in the text so Turndown preserves them
    document.querySelectorAll("[data-mcp-id]").forEach((el) => {
      const id = el.getAttribute("data-mcp-id");
      const span = document.createElement("span");
      span.textContent = ` [ID:${id}]`;
      el.appendChild(span);
    });
    return document.body?.innerHTML || "";
  });

  const markdown = turndown.turndown(bodyHtml);

  // Remove the injected spans from the live DOM to keep it clean
  await p.evaluate(() => {
    document.querySelectorAll("[data-mcp-id]").forEach((el) => {
      const span = el.querySelector("span:last-child");
      if (span && span.textContent?.startsWith(" [ID:")) span.remove();
    });
  });

  return { markdown: markdown.slice(0, 20000), elements: elementsDict };
}

export async function clickElement(id: number): Promise<string> {
  const p = await ensureBrowser();
  const selector = elementMap[id];
  if (!selector) throw new Error(`Element ID ${id} not found. Call get_page_context first.`);

  await p.click(selector, { timeout: 10000 });
  await p.waitForLoadState("domcontentloaded", { timeout: 15000 }).catch(() => {});
  return `Clicked element ${id}. Current URL: ${p.url()}`;
}

export async function typeText(id: number, text: string): Promise<string> {
  const p = await ensureBrowser();
  const selector = elementMap[id];
  if (!selector) throw new Error(`Element ID ${id} not found. Call get_page_context first.`);

  await p.fill(selector, text, { timeout: 10000 });
  return `Typed "${text}" into element ${id}`;
}

export async function pressKey(key: string): Promise<string> {
  const p = await ensureBrowser();
  await p.keyboard.press(key);
  await p.waitForLoadState("domcontentloaded", { timeout: 10000 }).catch(() => {});
  return `Pressed key: ${key}`;
}

export async function scrollDown(): Promise<string> {
  const p = await ensureBrowser();
  await p.evaluate(() => window.scrollBy(0, 600));
  return "Scrolled down 600px";
}

export async function scrollUp(): Promise<string> {
  const p = await ensureBrowser();
  await p.evaluate(() => window.scrollBy(0, -600));
  return "Scrolled up 600px";
}

export async function takeScreenshot(): Promise<string> {
  const p = await ensureBrowser();
  const buffer = await p.screenshot({ type: "png" });
  return buffer.toString("base64");
}

export async function goBack(): Promise<string> {
  const p = await ensureBrowser();
  await p.goBack({ waitUntil: "domcontentloaded", timeout: 15000 });
  return `Went back. Current URL: ${p.url()}`;
}

export async function getCurrentUrl(): Promise<string> {
  const p = await ensureBrowser();
  return p.url();
}

export async function closeBrowser(): Promise<void> {
  if (browser) {
    await browser.close();
    browser = null;
    page = null;
  }
}
