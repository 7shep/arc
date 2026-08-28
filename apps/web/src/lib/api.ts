import type {
  BulkApproveResult,
  CandidateDetail,
  CandidateNode,
  CandidateQueue,
  CandidateRelationship,
  Course,
  CourseDocument,
  CourseGraph,
} from "@arc/shared";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    let message = "Arc could not complete that request.";
    try { message = (await response.json()).detail ?? message; } catch {}
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export type CandidateKind = "node" | "relationship";

const reviewPath = (courseId: string) => `/courses/${courseId}/graph/review`;
const segment = (kind: CandidateKind) => (kind === "node" ? "nodes" : "relationships");

function send<T>(path: string, method: "POST" | "PATCH", body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export const api = {
  courses: () => request<Course[]>("/courses"),
  course: (id: string) => request<Course>(`/courses/${id}`),
  documents: (id: string) => request<CourseDocument[]>(`/courses/${id}/documents`),
  graph: (id: string) => request<CourseGraph>(`/courses/${id}/graph`),
  createCourse: (data: { name: string; code: string; description?: string }) => request<Course>("/courses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  uploadDocument: (id: string, form: FormData) => request<CourseDocument>(`/courses/${id}/documents`, { method: "POST", body: form }),
  candidates: (id: string) => request<CandidateQueue>(`${reviewPath(id)}/candidates`),
  nodeCandidate: (id: string, nodeId: string) => request<CandidateDetail<CandidateNode>>(`${reviewPath(id)}/candidates/nodes/${nodeId}`),
  relationshipCandidate: (id: string, relationshipId: string) => request<CandidateDetail<CandidateRelationship>>(`${reviewPath(id)}/candidates/relationships/${relationshipId}`),
  approveCandidate: (id: string, kind: CandidateKind, candidateId: string) => send<CandidateNode | CandidateRelationship>(`${reviewPath(id)}/candidates/${segment(kind)}/${candidateId}/approve`, "POST"),
  rejectCandidate: (id: string, kind: CandidateKind, candidateId: string, note?: string) => send<CandidateNode | CandidateRelationship>(`${reviewPath(id)}/candidates/${segment(kind)}/${candidateId}/reject`, "POST", { note: note ?? null }),
  editCandidate: (id: string, kind: CandidateKind, candidateId: string, data: Record<string, unknown>) => send<CandidateNode | CandidateRelationship>(`${reviewPath(id)}/candidates/${segment(kind)}/${candidateId}`, "PATCH", data),
  mergeCandidate: (id: string, kind: CandidateKind, candidateId: string, targetId: string) => send<unknown>(`${reviewPath(id)}/candidates/${segment(kind)}/${candidateId}/merge`, "POST", { targetId }),
  approveCandidates: (id: string, selection: { nodeIds: string[]; relationshipIds: string[] }) => send<BulkApproveResult>(`${reviewPath(id)}/candidates/approve`, "POST", selection),
};

