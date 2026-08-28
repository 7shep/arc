export const DOCUMENT_TYPES = [
  "LECTURE",
  "READING",
  "ASSIGNMENT",
  "TUTORIAL",
  "PRACTICE",
  "OTHER",
] as const;

export type DocumentType = (typeof DOCUMENT_TYPES)[number];
export type ProcessingStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";
export type GraphNodeType =
  | "CONCEPT"
  | "LECTURE"
  | "DOCUMENT"
  | "EXAMPLE"
  | "FORMULA"
  | "ASSIGNMENT"
  | "QUESTION";
export type GraphEdgeType =
  | "REQUIRES"
  | "RELATED_TO"
  | "TAUGHT_IN"
  | "DEFINED_IN"
  | "USED_IN"
  | "EXAMPLE_OF"
  | "APPEARS_IN";

export interface Course {
  id: string;
  name: string;
  code: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
  documentCount: number;
  nodeCount: number;
  edgeCount: number;
}

export interface CourseDocument {
  id: string;
  courseId: string;
  filename: string;
  originalFilename: string;
  documentType: DocumentType;
  mimeType: string;
  storagePath: string;
  processingStatus: ProcessingStatus;
  createdAt: string;
  updatedAt: string;
}

export interface GraphNode {
  id: string;
  courseId: string;
  type: GraphNodeType;
  label: string;
  description: string | null;
  sourceDocumentId: string | null;
  sourceLocation: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface GraphEdge {
  id: string;
  courseId: string;
  sourceNodeId: string;
  targetNodeId: string;
  type: GraphEdgeType;
  confidence: number | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface CourseGraph { nodes: GraphNode[]; edges: GraphEdge[] }
