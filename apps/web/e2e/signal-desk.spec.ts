import { expect, test } from "@playwright/test";

test("desktop desk completes the live demo production workflow", async (
  { page },
  testInfo,
) => {
  test.skip(testInfo.project.name !== "desktop-edge");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Good evening. The desk is live." }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Mira, the Giani AI news anchor" }),
  ).toBeVisible();
  await expect(page.getByText("3/3 locked")).toBeVisible();

  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Find the signal." }),
  ).toBeVisible();
  await expect(page.getByText("Demo dataset:")).toBeVisible();
  await expect(page.locator("article.research-card")).toHaveCount(3);

  await page.goto("/studio");
  const angle = page.getByRole("textbox", { name: "One-sentence angle" });
  await angle.fill(
    "Reliable AI operations matter more than isolated model announcements.",
  );
  await page.getByRole("button", {
    name: "Generate structured draft",
  }).click();
  await expect(page.getByText("Structured script generated.")).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByRole("heading", { name: "Structured script" }),
  ).toBeVisible();
  await expect(page.locator(".runtime-display")).toContainText("210");

  const gates = page.locator('.gate-list input[type="checkbox"]');
  const gateLabels = page.locator(".gate-list label");
  await expect(gates).toHaveCount(11);
  await expect(gateLabels).toHaveCount(11);
  for (let index = 0; index < 11; index += 1) {
    if (await gates.nth(index).isChecked()) continue;
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        response.url().includes("/compliance/"),
    );
    await gateLabels.nth(index).click();
    const response = await responsePromise;
    expect(response.ok()).toBe(true);
    await expect(gates.nth(index)).toBeChecked();
  }
  await expect(page.getByText("11 / 11 passed")).toBeVisible();

  await page.getByRole("button", { name: /Approve editorial/ }).click();
  await expect(page.getByText("Episode approved for production.")).toBeVisible();

  await page.getByRole("button", { name: /Generate voice/ }).click();
  await expect(
    page.getByText(
      "Demo voice artifact created. Configure ElevenLabs for audio.",
    ),
  ).toBeVisible();

  await page.getByRole("button", { name: /Start render/ }).click();
  await expect(page.getByText(/Render 100%/)).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: /Build publish package/ }).click();
  await expect(
    page.getByText(
      "Publish package is ready with metadata and disclosures.",
    ),
  ).toBeVisible();
  await expect(page.getByText("Packaged", { exact: true })).toBeVisible();
});

test("mobile navigation and primary pages fit the viewport", async (
  { page },
  testInfo,
) => {
  test.skip(testInfo.project.name !== "mobile-edge");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Good evening. The desk is live." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  const primary = page.getByRole("navigation", {
    name: "Primary",
    exact: true,
  });
  await expect(primary).toBeVisible();
  await primary.getByRole("link", { name: "Library" }).click();
  await expect(
    page.getByRole("heading", {
      name: "One identity. Fifteen visual beats.",
    }),
  ).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
