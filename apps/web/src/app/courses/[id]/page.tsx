import { notFound } from "next/navigation";
import { Workspace } from "@/components/workspace";
import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CoursePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data;
  try {
    data = await Promise.all([api.course(id), api.documents(id), api.graph(id), api.candidates(id)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [course, documents, graph, queue] = data;
  return <Workspace initialCourse={course} initialDocuments={documents} initialGraph={graph} initialQueue={queue} />;
}
