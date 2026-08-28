import type { Course, CourseDocument, CourseGraph } from "@arc/shared";

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

export const api = {
  courses: () => request<Course[]>("/courses"),
  course: (id: string) => request<Course>(`/courses/${id}`),
  documents: (id: string) => request<CourseDocument[]>(`/courses/${id}/documents`),
  graph: (id: string) => request<CourseGraph>(`/courses/${id}/graph`),
  createCourse: (data: { name: string; code: string; description?: string }) => request<Course>("/courses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  uploadDocument: (id: string, form: FormData) => request<CourseDocument>(`/courses/${id}/documents`, { method: "POST", body: form }),
};

