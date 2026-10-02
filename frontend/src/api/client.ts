export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    const text = await res.text();
    try {
      const j = JSON.parse(text);
      if (typeof j?.detail === "string") return j.detail;
      if (Array.isArray(j?.detail)) {
        return `입력값을 확인하세요: ${j.detail.map((d: { msg?: string }) => d.msg ?? "").join(", ")}`;
      }
    } catch {
      /* JSON 아님 → 원문 */
    }
    return text || res.statusText;
  } catch {
    return res.statusText || "unknown error";
  }
}

export async function http<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { credentials: "same-origin" });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "네트워크 연결에 실패했습니다. 잠시 후 다시 시도하세요.",
    );
  }

  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  }

  if (res.status === 403) {
    throw new ApiError(403, "forbidden", "이 기능에 접근할 권한이 없습니다.");
  }

  if (res.status === 404) {
    throw new ApiError(404, "not_found", "요청한 데이터가 없습니다.");
  }

  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      res.status,
      "server_error",
      body || "서버 오류가 발생했습니다.",
    );
  }

  return res.json() as Promise<T>;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "네트워크 연결에 실패했습니다. 잠시 후 다시 시도하세요.",
    );
  }

  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  }

  if (res.status === 403) {
    throw new ApiError(403, "forbidden", "이 기능에 접근할 권한이 없습니다.");
  }

  if (res.status === 404) {
    throw new ApiError(404, "not_found", "요청한 데이터가 없습니다.");
  }

  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(
      res.status,
      "server_error",
      body || "요청 처리 중 오류가 발생했습니다.",
    );
  }

  return res.json() as Promise<T>;
}

export async function del<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method: "DELETE", credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network_error", "네트워크 연결에 실패했습니다. 잠시 후 다시 시도하세요.");
  }

  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  }
  if (res.status === 403) {
    throw new ApiError(403, "forbidden", "이 기능에 접근할 권한이 없습니다.");
  }
  if (res.status === 404) {
    throw new ApiError(404, "not_found", "요청한 데이터가 없습니다.");
  }
  if (!res.ok) {
    const body = await readErrorBody(res);
    throw new ApiError(res.status, "server_error", body || "요청 처리 중 오류가 발생했습니다.");
  }
  return res.json() as Promise<T>;
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "네트워크 연결에 실패했습니다. 잠시 후 다시 시도하세요.");
  }
  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  }
  if (res.status === 403) throw new ApiError(403, "forbidden", "이 기능에 접근할 권한이 없습니다.");
  if (!res.ok) {
    const b = await readErrorBody(res);
    throw new ApiError(res.status, "server_error", b || "요청 처리 중 오류가 발생했습니다.");
  }
  return res.json() as Promise<T>;
}
