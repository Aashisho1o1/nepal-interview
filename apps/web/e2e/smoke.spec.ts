import { expect, test, type Page } from "@playwright/test";

test("home page loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /Why this course/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recorded Demos" })).toBeVisible();
  const legal = page.locator(".legal-links");
  await expect(legal.getByRole("link", { name: "Privacy" })).toBeVisible();
  await expect(legal.getByRole("link", { name: "Terms" })).toBeVisible();
  await expect(page.getByText("needs a newer browser")).toHaveCount(0);
});

// One student, new each run, so the free plan starts full. The steps share one page.
test.describe("a new student", () => {
  test.describe.configure({ mode: "serial" });
  const name = "Asha Gurung";
  const email = `e2e-${Date.now()}@example.com`;
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    // The microphone is blocked: no permission is granted, and it fails as a blocked one does.
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("blocked", "NotAllowedError"));
    });
  });
  test.afterAll(() => page.close());

  test("signs up and lands on practice", async () => {
    await page.goto("/");
    await page.getByLabel("Your name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("e2e-password");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL("/interview");
    await expect(page.getByText("Hi, Asha")).toBeVisible();
  });

  test("has 3 free voice sessions", async () => {
    await expect(page.locator("label.tier", { hasText: "Voice only" })).toContainText("3 sessions left");
  });

  test("a blocked microphone starts no session", async () => {
    const starts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && new URL(r.url()).pathname === "/api/sessions") starts.push(r.url());
    });
    await page.getByRole("button", { name: "Start practice" }).click();
    await expect(page.getByText("Your microphone is blocked")).toBeVisible();
    expect(starts).toEqual([]);
  });

  // Covers Back to a page that reloads; Playwright's Chromium never restores pages from
  // the back/forward cache, so Shell's pageshow reload isn't exercised here.
  test("signs out, and Back sends a signed-out student home", async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    await expect(page.getByText("Hi, Asha")).toHaveCount(0);
  });
});

test("an old browser is told to update", async ({ page }) => {
  // What the page's check sees on Safari before 16.4: class static blocks don't parse.
  await page.addInitScript(() => {
    window.Function = function () {
      throw new SyntaxError("old browser");
    } as unknown as FunctionConstructor;
  });
  // The app's code would not run there either.
  await page.route("**/_next/static/chunks/**", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByText("update your iPhone to iOS 16.4")).toBeVisible();
});
