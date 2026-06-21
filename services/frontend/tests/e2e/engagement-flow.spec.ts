import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixture = (name: string) => path.resolve(__dirname, "fixtures", name);

test.describe("Engagement workflow — intake to decision", () => {
  let createdCaseId: string | null = null;

  test.afterEach(async ({ request }) => {
    if (!createdCaseId) {
      return;
    }
    await request.delete(`/api/v1/cases/${createdCaseId}`);
    createdCaseId = null;
  });

  test("creates a fresh engagement and walks the rebuilt UI from intake to decision", async ({ page }) => {
    const title = `E2E Hiring Event ${Date.now()}`;

    await page.goto("/engagements");

    await page.getByLabel("Title").fill(title);
    await page.getByLabel("Organization").fill("Selection Platform");
    await page.getByLabel("Hiring action type").fill("Merit Promotion");
    await page.getByLabel("Selecting official").fill("Jordan Rivera");
    await page.getByRole("button", { name: "Create engagement" }).click();

    await expect(page).toHaveURL(/\/engagements\/.+\/prep/);
    createdCaseId = page.url().match(/engagements\/([^/]+)\//)?.[1] ?? null;
    expect(createdCaseId).not.toBeNull();

    await page.getByLabel("Position description file").setInputFiles(fixture("position-description.txt"));
    await page.getByRole("button", { name: "Upload PD" }).click();

    await page.getByLabel("Resume package file").setInputFiles(fixture("resume-bundle.txt"));
    await page.getByRole("button", { name: "Upload resumes" }).click();

    await page.getByLabel("Supporting document file").setInputFiles(fixture("supporting-notes.txt"));
    await page.getByRole("button", { name: "Upload", exact: true }).click();

    await page.waitForTimeout(7000);

    await page.getByRole("button", { name: "Run candidate matching" }).click();
    await expect(page.getByText("Matched candidates")).toBeVisible();

    await page.getByRole("button", { name: "Run PD analysis" }).click();
    await page.waitForTimeout(3000);

    await page.getByRole("button", { name: /Generate rubric|Refresh rubric from PD/ }).click();
    await page.waitForTimeout(1500);

    await page.getByRole("button", { name: "Add dimension" }).click();
    await page.locator(".dimension-row").last().locator("input").first().fill("Human-centered judgment");
    await page.locator(".dimension-row").last().locator("textarea").fill("Optional human review dimension added during intake.");
    await page.getByRole("button", { name: "Save model" }).click();

    await page.locator("#prep-launch").getByRole("button", { name: "Run resume review" }).click();
    await page.waitForTimeout(3000);

    await page.getByRole("link", { name: "Review" }).last().click();
    await expect(page).toHaveURL(/\/engagements\/.+\/review/);

    const hasMatrixRow = (await page.locator(".candidate-matrix tbody tr").count()) > 0;
    if (hasMatrixRow) {
      await page.locator(".candidate-matrix tbody tr").first().click();
      await page.getByRole("button", { name: "Overrides" }).click();
      await page.getByLabel("Final tier").selectOption("Tier A");
      await page.getByLabel("Final disposition").selectOption("alternate");
      await page.getByLabel("Advancement decision").selectOption("advance");
      await page.getByLabel("Stage score").fill("91");
      await page.getByLabel("Decision rationale").fill("E2E override applied through the rebuilt review workspace.");
      await page.getByRole("button", { name: "Save decision" }).click();
    }

    await page.getByRole("link", { name: "Decision" }).last().click();
    await expect(page).toHaveURL(/\/engagements\/.+\/decision/);

    if (await page.getByRole("button", { name: /Run final stage|Generate package|Generate recommendation|Build package/ }).count()) {
      await page.getByRole("button", { name: /Run final stage|Generate package|Generate recommendation|Build package/ }).first().click();
      await page.waitForTimeout(4000);
    }

    const rankedSlate = page.getByRole("heading", { name: "Final ranking and disposition" });
    await expect(rankedSlate).toBeVisible();

    if ((await page.locator(".candidate-matrix tbody tr").count()) > 0) {
      await page.locator(".candidate-matrix tbody tr").first().click();
      await page.getByLabel("Decision rationale").fill("E2E final review rationale.");
      const finalizeButton = page.getByRole("button", { name: /Finalize selectee|Make selectee/ });
      if (await finalizeButton.count()) {
        await finalizeButton.first().click();
      }
    }

    await expect(page.getByText("Decision Package", { exact: true }).first()).toBeVisible();
  });
});
