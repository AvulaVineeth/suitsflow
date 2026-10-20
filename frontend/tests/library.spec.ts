import { expect, test, type Page } from "@playwright/test";

const document = {
  id: "doc-1",
  name: "Live agreement",
  document_type: "contract",
  created_at: "2026-10-20T09:00:00Z",
};
const revision = {
  id: "version-1",
  document_id: "doc-1",
  version_number: 1,
  mime_type: "text/plain",
  file_size: 50,
  checksum: "a".repeat(64),
  created_at: document.created_at,
  content_status: "clean",
};
async function connect(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Connect local API" }).click();
  await page.getByLabel("Local development access token").fill("test-token");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
}
test("sample preview makes no API calls and supports revision text on mobile", async ({
  page,
}) => {
  let requests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requests++;
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Sample preview", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Master services agreement/ }).click();
  await page.getByRole("button", { name: "Read saved text" }).click();
  await expect(page.locator("pre")).toContainText("Sample content");
  await page
    .getByRole("button", { name: /Information security policy/ })
    .click();
  await expect(page.getByText("Text is available only after")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Read saved text" }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(requests).toBe(0);
});
test("reads authenticated API data, treats missing jobs separately, and renders text safely", async ({
  page,
}) => {
  await page.route("**/api/v1/documents**", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer test-token");
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/versions"))
      return route.fulfill({ json: [revision] });
    if (url.pathname.endsWith("-job"))
      return route.fulfill({ status: 404, json: {} });
    if (url.pathname.endsWith("/extraction"))
      return route.fulfill({
        json: {
          text: "<script>window.attacked=true</script>",
          extractor: "plain-text-v1",
          character_count: 38,
          source_checksum: revision.checksum,
        },
      });
    return route.fulfill({ json: [document] });
  });
  await connect(page);
  await page.getByRole("button", { name: /Live agreement/ }).click();
  await expect(page.getByText("No queued job")).toHaveCount(2);
  await page.getByRole("button", { name: "Read saved text" }).click();
  await expect(page.locator("pre")).toContainText("<script>");
  expect(await page.evaluate(() => "attacked" in window)).toBe(false);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByText("Live agreement")).toHaveCount(0);
  await expect(page.getByText("Sample preview", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Sample preview", { exact: true })).toBeVisible();
});
test("authorization failure is visible, with no fallback to sample records", async ({
  page,
}) => {
  await page.route("**/api/v1/documents**", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await connect(page);
  await expect(page.getByRole("alert")).toContainText("not authorized");
  await expect(
    page.getByRole("button", { name: /Master services agreement/ }),
  ).toHaveCount(0);
});
test("service failures do not appear as absent jobs", async ({ page }) => {
  await page.route("**/api/v1/documents**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/versions")) return route.fulfill({ json: [revision] });
    if (path.endsWith("-job")) return route.fulfill({ status: 503, json: {} });
    return route.fulfill({ json: [document] });
  });
  await connect(page);
  await page.getByRole("button", { name: /Live agreement/ }).click();
  await expect(page.getByRole("alert")).toHaveCount(2);
  await expect(page.getByText("No queued job")).toHaveCount(0);
});
test("document pagination sends offsets and clears the inspector", async ({
  page,
}) => {
  await page.route("**/api/v1/documents**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/versions")) return route.fulfill({ json: [] });
    if (url.searchParams.get("offset") === "20")
      return route.fulfill({ json: [] });
    return route.fulfill({
      json: Array.from({ length: 20 }, (_, i) => ({
        ...document,
        id: `doc-${i}`,
        name: `Agreement ${i}`,
      })),
    });
  });
  await connect(page);
  await page
    .getByRole("button", { name: "Agreement 0 contract", exact: false })
    .click();
  const library = page.getByRole("region", { name: "Documents", exact: true });
  await library.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("No documents here yet")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A clear view of every revision" }),
  ).toBeVisible();
  await library.getByRole("button", { name: "Previous" }).click();
  await expect(
    page.getByRole("button", { name: /Agreement 0 contract/ }),
  ).toBeVisible();
});
test("switching documents ignores a late revision response", async ({
  page,
}) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/documents**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/documents/doc-1/versions") {
      await gate;
      return route.fulfill({ json: [revision] }).catch(() => {});
    }
    if (path.endsWith("/versions")) return route.fulfill({ json: [] });
    return route.fulfill({
      json: [document, { ...document, id: "doc-2", name: "Second agreement" }],
    });
  });
  await connect(page);
  await page.getByRole("button", { name: /Live agreement/ }).click();
  await page.getByRole("button", { name: /Second agreement/ }).click();
  release();
  await expect(
    page.getByRole("heading", { name: "Second agreement" }),
  ).toBeVisible();
  await expect(page.getByText("No revisions on this page.")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Revision details" }),
  ).toHaveCount(0);
});

test("disconnect ignores a late API response", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/documents**", async (route) => {
    await gate;
    await route.fulfill({ json: [document] }).catch(() => {});
  });
  await connect(page);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  release();
  await expect(
    page.getByRole("button", { name: /Master services agreement/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Live agreement/ }),
  ).toHaveCount(0);
});
