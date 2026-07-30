/**
 * Frontière HTTP commune du frontend.
 * Ce module construit les requêtes JSON et normalise les erreurs FastAPI.
 */
export type ApiValidationIssue = {
  loc: Array<string | number>
  msg: string
  type: string
}

/** Erreur HTTP normalisée, avec les détails de validation FastAPI éventuels. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly issues: ApiValidationIssue[] = [],
    readonly code: string | null = null,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

/**
 * Exécute une requête JSON vers l'API configurée et normalise les réponses d'erreur.
 * Le générique décrit le contrat attendu mais ne valide pas le JSON à l'exécution.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  })

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const issues = readIssues(payload)
    const detail = readDetail(payload)
    throw new ApiError(
      detail ?? `Erreur HTTP ${response.status}`,
      response.status,
      issues,
      readCode(payload),
    )
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function readIssues(payload: unknown): ApiValidationIssue[] {
  // La frontière réseau reste unknown jusqu'à validation structurelle minimale.
  if (!payload || typeof payload !== "object" || !("detail" in payload) || !Array.isArray(payload.detail)) return []
  return payload.detail.filter((item): item is ApiValidationIssue => {
    if (!item || typeof item !== "object") return false
    return "loc" in item && Array.isArray(item.loc) && "msg" in item && typeof item.msg === "string" && "type" in item && typeof item.type === "string"
  })
}

function readDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return null
  if (typeof payload.detail === "string") return payload.detail
  if (
    payload.detail
    && typeof payload.detail === "object"
    && "message" in payload.detail
    && typeof payload.detail.message === "string"
  ) return payload.detail.message
  const issues = readIssues(payload)
  return issues.length ? issues.map((issue) => `${issue.loc.join(".")}: ${issue.msg}`).join(" · ") : null
}

function readCode(payload: unknown): string | null {
  if (
    !payload
    || typeof payload !== "object"
    || !("detail" in payload)
    || !payload.detail
    || typeof payload.detail !== "object"
    || !("code" in payload.detail)
    || typeof payload.detail.code !== "string"
  ) return null
  return payload.detail.code
}
