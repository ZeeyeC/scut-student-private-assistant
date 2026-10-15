let csrf = "";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!csrf)
    csrf = (
      await (await fetch("/api/csrf", { credentials: "same-origin" })).json()
    ).csrf_token;
  const headers = new Headers(options.headers);
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !(options.body instanceof URLSearchParams)
  )
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") {
    headers.set("X-CSRF-Token", csrf);
    if (!headers.has("Idempotency-Key"))
      headers.set("Idempotency-Key", crypto.randomUUID());
  }
  const r = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: "服务不可用" }));
    throw new ApiError(
      r.status,
      typeof e.detail === "string"
        ? e.detail
        : r.status === 409
          ? "数据已在另一端更新，请刷新后重新校对"
          : JSON.stringify(e.detail),
    );
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
