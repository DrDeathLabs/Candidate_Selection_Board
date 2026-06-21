import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";
import axios from "axios";

const UI_BASE = process.env.E2E_UI_BASE_URL ?? "http://127.0.0.1:8610";
const API_BASE = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8612/api/v1";
const OUTPUT_ROOT = path.resolve(process.cwd(), "test-results", "batch");

const args = parseArgs(process.argv.slice(2));
const runCount = args.runs ?? 3;
const minResumes = args["min-resumes"] ?? 10;
const maxResumes = args["max-resumes"] ?? 15;
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(OUTPUT_ROOT, stamp);

const firstNames = ["Alex", "Jordan", "Morgan", "Taylor", "Riley", "Avery", "Quinn", "Reese", "Parker", "Casey"];
const lastNames = ["Bennett", "Coleman", "Hayes", "Reed", "Taylor", "Brooks", "Rivera", "Morgan", "Lee", "Santos"];

await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ baseURL: UI_BASE, viewport: { width: 1440, height: 1024 } });
const summary = [];

try {
  for (let runIndex = 0; runIndex < runCount; runIndex += 1) {
    const title = `Batch Hiring Event ${runIndex + 1} ${Date.now()}`;
    const resumeCount = pickResumeCount(runIndex, runCount, minResumes, maxResumes);
    const startedAt = Date.now();
    let caseId = null;

    try {
      console.log(`[batch ${runIndex + 1}/${runCount}] creating engagement with ${resumeCount} resumes`);
      const created = await apiFetch("/cases/", {
        method: "POST",
        json: {
          title,
          series: "2210",
          grade: "15",
          organization: "Selection Platform",
          hiring_action_type: "Merit Promotion",
          certificate_number: "",
          selecting_official: `Official ${runIndex + 1}`,
          panel_members: [],
          data_sensitivity: "moderate",
          retention_settings: { policy: "default" },
          model_provider_settings: { provider: "ollama" },
          outside_enrichment_allowed: false,
        },
      });
      caseId = created.id;

      console.log(`[batch ${runIndex + 1}/${runCount}] uploading materials`);
      await uploadTextDocument(caseId, "position_description", `pd-${runIndex + 1}.txt`, buildPositionDescription(runIndex));
      await uploadTextDocument(caseId, "resume_bundle", `resumes-${runIndex + 1}.txt`, buildResumeBundle(runIndex, resumeCount));
      await uploadTextDocument(caseId, "other", `support-${runIndex + 1}.txt`, `Supporting note for batch run ${runIndex + 1}.`);

      console.log(`[batch ${runIndex + 1}/${runCount}] waiting for intake readiness`);
      await waitFor(`documents ready (${title})`, async () => {
        const prep = await apiFetch(`/cases/${caseId}/prep-workspace`);
        return Number(prep.document_summary?.ready_documents ?? 0) >= 2 ? prep : null;
      });

      console.log(`[batch ${runIndex + 1}/${runCount}] running matching and PD analysis`);
      await apiFetch(`/cases/${caseId}/candidates/reconcile`, { method: "POST" });
      await apiFetch(`/cases/${caseId}/analysis/position/run`, { method: "POST" });

      await waitFor(`pd analysis (${title})`, async () => {
        try {
          const analysis = await apiFetch(`/cases/${caseId}/analysis/position`);
          return Array.isArray(analysis.recommended_dimensions) && analysis.recommended_dimensions.length > 0 ? analysis : null;
        } catch {
          return null;
        }
      });

      console.log(`[batch ${runIndex + 1}/${runCount}] generating rubric and resume review`);
      await apiFetch(`/cases/${caseId}/rubrics/from-analysis`, { method: "POST" });

      const prepWorkspace = await apiFetch(`/cases/${caseId}/prep-workspace`);
      const resumeStage = prepWorkspace.stages.find((stage) => stage.template_key === "resume_review");
      if (!resumeStage) {
        throw new Error("Resume review stage was not configured.");
      }

      await apiFetch(`/cases/${caseId}/workflow-plan/stages/${resumeStage.id}/run`, {
        method: "POST",
        json: { force: false },
      });

      console.log(`[batch ${runIndex + 1}/${runCount}] waiting for review workspace`);
      const reviewWorkspace = await waitFor(`review workspace (${title})`, async () => {
        const review = await apiFetch(`/cases/${caseId}/review-workspace`);
        return Array.isArray(review.candidate_rows) && review.candidate_rows.length > 0 ? review : null;
      });

      console.log(`[batch ${runIndex + 1}/${runCount}] running final stage and generating recommendation`);
      const decisionWarmup = await apiFetch(`/cases/${caseId}/decision-workspace`);
      if (decisionWarmup.final_stage_id) {
        await apiFetch(`/cases/${caseId}/workflow-plan/stages/${decisionWarmup.final_stage_id}/run`, {
          method: "POST",
          json: { force: true },
        });
      }

      await apiFetch(`/cases/${caseId}/selection/recommendation/generate`, { method: "POST" });

      console.log(`[batch ${runIndex + 1}/${runCount}] waiting for decision workspace and screenshots`);
      const decisionWorkspace = await waitFor(`decision workspace (${title})`, async () => {
        const decision = await apiFetch(`/cases/${caseId}/decision-workspace`);
        return decision.recommendation ? decision : null;
      });

      await page.goto(`${UI_BASE}/engagements/${caseId}/prep`);
      await page.getByRole("heading", { name: title }).waitFor();
      await page.getByText("Open selecting official workspace").waitFor({ timeout: 30000 });
      await page.screenshot({ path: path.join(outputDir, `run-${runIndex + 1}-prep.png`), fullPage: true });

      const reviewStageId = reviewWorkspace.active_stage_id ?? reviewWorkspace.stage_navigation?.find((entry) => entry.candidate_count > 0)?.id;
      const reviewCandidateId = reviewWorkspace.candidate_rows[0]?.candidate_id;
      const reviewTarget = new URL(`${UI_BASE}/engagements/${caseId}/review`);
      if (reviewStageId) {
        reviewTarget.searchParams.set("stage", reviewStageId);
      }
      if (reviewCandidateId) {
        reviewTarget.searchParams.set("candidate", reviewCandidateId);
      }
      await page.goto(reviewTarget.toString());
      await page.getByText(reviewWorkspace.candidate_rows[0]?.candidate_name ?? "Candidate review").waitFor({ timeout: 30000 });
      await page.locator(".candidate-matrix tbody tr").first().waitFor({ timeout: 30000 });
      await page.screenshot({ path: path.join(outputDir, `run-${runIndex + 1}-review.png`), fullPage: true });

      const decisionCandidateId = decisionWorkspace.recommendation.rankings[0]?.candidate_id;
      const decisionTarget = new URL(`${UI_BASE}/engagements/${caseId}/decision`);
      if (decisionCandidateId) {
        decisionTarget.searchParams.set("candidate", decisionCandidateId);
      }
      await page.goto(decisionTarget.toString());
      await page.getByText(decisionWorkspace.recommendation.rankings[0]?.candidate_name ?? selecteeName(decisionWorkspace)).waitFor({ timeout: 30000 });
      await page.locator(".decision-matrix-table tbody tr").first().waitFor({ timeout: 30000 });
      await page.screenshot({ path: path.join(outputDir, `run-${runIndex + 1}-decision.png`), fullPage: true });

      summary.push({
        title,
        caseId,
        resumeCount,
        candidateCount: reviewWorkspace.candidate_rows.length,
        rankedCount: decisionWorkspace.recommendation.rankings.length,
        durationMs: Date.now() - startedAt,
        status: "passed",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      summary.push({
        title,
        caseId,
        resumeCount,
        durationMs: Date.now() - startedAt,
        status: "failed",
        error: message,
      });
      if (caseId) {
        await page.goto(`${UI_BASE}/engagements/${caseId}/prep`).catch(() => {});
        await page.screenshot({ path: path.join(outputDir, `run-${runIndex + 1}-failure.png`), fullPage: true }).catch(() => {});
      }
    } finally {
      if (caseId) {
        await apiFetch(`/cases/${caseId}`, { method: "DELETE", acceptEmpty: true }).catch(() => {});
      }
    }
  }
} finally {
  await browser.close();
}

await fs.writeFile(path.join(outputDir, "summary.json"), JSON.stringify(summary, null, 2));
console.log(JSON.stringify({ outputDir, runCount, failures: summary.filter((entry) => entry.status === "failed").length }, null, 2));

if (summary.some((entry) => entry.status === "failed")) {
  process.exitCode = 1;
}

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const value = argv[index + 1];
    parsed[key] = value ? Number(value) : true;
    index += 1;
  }
  return parsed;
}

async function apiFetch(route, options = {}) {
  const response = await axios({
    url: `${API_BASE}${route}`,
    method: options.method ?? "GET",
    headers: options.headers,
    data: options.formData ?? options.json,
    timeout: 0,
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
    validateStatus: () => true,
  });

  if (response.status < 200 || response.status >= 300) {
    const detail = typeof response.data === "string" ? response.data : JSON.stringify(response.data);
    throw new Error(`${options.method ?? "GET"} ${route} failed with ${response.status}: ${detail}`);
  }

  if (options.acceptEmpty && response.status === 204) {
    return null;
  }

  return response.data ?? null;
}

async function uploadTextDocument(caseId, documentType, fileName, content) {
  const form = new FormData();
  form.set("file", new File([content], fileName, { type: "text/plain" }));
  form.set("document_type", documentType);
  form.set("metadata_source", "batch-regression");
  return apiFetch(`/cases/${caseId}/documents/upload`, {
    method: "POST",
    formData: form,
  });
}

async function waitFor(label, callback, timeoutMs = 180000, intervalMs = 2000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const result = await callback();
    if (result) {
      return result;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out while waiting for ${label}.`);
}

function pickResumeCount(index, totalRuns, min, max) {
  if (totalRuns <= 1) {
    return max;
  }
  const ratio = index / (totalRuns - 1);
  return Math.round(min + (max - min) * ratio);
}

function buildPositionDescription(runIndex) {
  return [
    `Position: Batch Director ${runIndex + 1}`,
    "Leads enterprise platform delivery, service modernization, cloud operations, procurement coordination, and budget execution.",
    "Supervises a cross-functional team, manages contractor performance, and oversees mission delivery metrics.",
    "Builds a defensible review model tied to technical execution, leadership, fiscal stewardship, and communication.",
  ].join("\n");
}

function buildResumeBundle(runIndex, count) {
  const entries = [];
  for (let index = 0; index < count; index += 1) {
    const firstName = firstNames[(runIndex + index) % firstNames.length];
    const lastName = lastNames[(runIndex * 3 + index) % lastNames.length];
    const identifier = `${runIndex + 1}-${index + 1}`;
    entries.push(
      [
        `Name: ${firstName} ${lastName}`,
        `Email: ${firstName.toLowerCase()}.${lastName.toLowerCase()}.${identifier}@example.gov`,
        `Led mission systems operations for a ${10 + (index % 25)}-person team with budget oversight and modernization responsibilities.`,
        `Delivered enterprise platform upgrades, vendor coordination, cloud migration planning, and service reliability improvements for portfolio ${identifier}.`,
      ].join("\n"),
    );
  }
  return entries.join("\n\n");
}

function selecteeName(decisionWorkspace) {
  return decisionWorkspace.recommendation?.selectee_candidate_name ?? "Decision workspace";
}
