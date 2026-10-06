/** A non-2xx answer from the backend API, carrying the backend's own explanation. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`The API answered ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** FastAPI sends `detail` as a string, or as a list of validation issues for a 422. */
async function errorDetail(response: Response): Promise<string> {
  if (response.headers.get("Content-Type")?.includes("application/json")) {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      if (typeof body.detail === "string") {
        return body.detail;
      }
      if (Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((issue: unknown) =>
          typeof issue === "object" &&
          issue !== null &&
          "msg" in issue &&
          typeof issue.msg === "string"
            ? [issue.msg]
            : [],
        );
        if (messages.length > 0) {
          return messages.join("; ");
        }
      }
    }
  }
  return response.statusText || "no detail was supplied";
}

/** Reads one answer of the backend read API ; the caller owns the check of `T`. */
export async function readJson<T>(url: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { signal, cache: "no-store" });
  } catch (error: unknown) {
    if (signal.aborted) {
      throw error;
    }
    throw new Error(`The API could not be reached at ${url}.`, { cause: error });
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  const data: T = await response.json();
  return data;
}
