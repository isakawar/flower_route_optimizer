import type { OptimizationParams, OptimizationResult, RecalculateParams } from "@/types";
import { MOCK_RESULT } from "./mockData";

export class InfeasibleError extends Error {
  readonly minimumCouriersRequired: number;
  readonly reason: string;
  constructor(message: string, minimum: number, reason = "unknown") {
    super(message);
    this.name = "InfeasibleError";
    this.minimumCouriersRequired = minimum;
    this.reason = reason;
  }
}

function parseApiError(body: Record<string, unknown>, status: number): Error {
  // Flat INFEASIBLE response (JSONResponse, no `detail` wrapper)
  if (status === 422 && body.error === "INFEASIBLE") {
    return new InfeasibleError(
      String(body.message ?? "Infeasible schedule"),
      Number(body.minimum_couriers_required ?? 1),
      String(body.reason ?? "unknown")
    );
  }
  // Standard FastAPI error: { detail: string | object }
  const detail = body?.detail;
  return new Error(typeof detail === "string" ? detail : `Server error ${status}`);
}

const POLL_INTERVAL_MS = 1500;
const MAX_WAIT_MS = 5 * 60 * 1000;

export async function* runOptimization(
  params: OptimizationParams,
  onStep: (stepId: string) => void
): AsyncGenerator<OptimizationResult> {
  let backendReachable = false;

  try {
    const formData = new FormData();
    formData.append("file", params.csvFile);

    // Submit job (returns immediately with jobId)
    const res = await fetch("/api/optimize", {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(15_000),
    });

    backendReachable = true;

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw parseApiError(body, res.status);
    }

    const submission = await res.json();

    // Sync fallback (RQ unavailable): backend returned result directly
    if (submission.status === "done" && submission.result) {
      onStep("finalize");
      yield submission.result as OptimizationResult;
      return;
    }

    const { jobId } = submission;
    onStep("upload");

    // Poll until done
    const started = Date.now();
    let lastStep = "upload";

    while (Date.now() - started < MAX_WAIT_MS) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

      const pollRes = await fetch(`/api/jobs/${jobId}`, {
        signal: AbortSignal.timeout(10_000),
      });

      if (!pollRes.ok) {
        const body = await pollRes.json().catch(() => ({}));
        throw parseApiError(body, pollRes.status);
      }

      const job = await pollRes.json();

      if (job.status === "done") {
        onStep("finalize");
        yield job.result as OptimizationResult;
        return;
      }

      if (job.status === "failed") {
        throw new Error(job.error || "Optimization failed");
      }

      // Forward real progress step from backend
      const step: string | undefined = job.progress?.currentStep;
      if (step && step !== lastStep) {
        lastStep = step;
        onStep(step);
      }
    }

    throw new Error("Optimization timed out after 5 minutes");
  } catch (err) {
    if (backendReachable) throw err;
    // Backend not running — fall back to demo data
    console.info("[api] Backend unreachable — using demo data");
  }

  // Demo mode (no backend running)
  const demoSteps = ["upload", "geocode", "matrix", "optimize", "finalize"];
  for (const step of demoSteps) {
    await new Promise((r) => setTimeout(r, 600));
    onStep(step);
  }
  yield MOCK_RESULT;
}

export async function recalculate(params: RecalculateParams): Promise<OptimizationResult> {
  const res = await fetch("/api/recalculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw parseApiError(body, res.status);
  }
  return res.json();
}
