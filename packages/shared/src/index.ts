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

export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED" | "EDITED" | "MERGED";

export interface GraphNode {
  id: string;
  courseId: string;
  type: GraphNodeType;
  label: string;
  description: string | null;
  sourceDocumentId: string | null;
  sourceLocation: string | null;
  confidence: number | null;
  reviewStatus: ReviewStatus;
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
  reviewStatus: ReviewStatus;
  sourceDocumentId: string | null;
  sourceLocation: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface CourseGraph { nodes: GraphNode[]; edges: GraphEdge[] }

export interface CandidateEvidence {
  id: string;
  documentId: string;
  documentName: string;
  documentType: DocumentType;
  page: number | null;
  section: string | null;
  sourceLocation: Record<string, unknown>;
  excerpt: string;
  confidence: number;
  createdAt: string;
}

interface CandidateBase {
  id: string;
  courseId: string;
  confidence: number | null;
  reviewStatus: ReviewStatus;
  reviewNote: string | null;
  reviewedAt: string | null;
  sourceDocumentId: string | null;
  sourceDocumentName: string | null;
  metadata: Record<string, unknown>;
  evidenceCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface CandidateNode extends CandidateBase {
  kind: "node";
  type: GraphNodeType;
  label: string;
  description: string | null;
  mergedIntoNodeId: string | null;
}

export interface CandidateRelationship extends CandidateBase {
  kind: "relationship";
  type: GraphEdgeType;
  sourceNodeId: string;
  targetNodeId: string;
  sourceNodeLabel: string | null;
  targetNodeLabel: string | null;
  mergedIntoEdgeId: string | null;
}

export type Candidate = CandidateNode | CandidateRelationship;

export interface CandidateQueue {
  pendingCount: number;
  nodes: CandidateNode[];
  relationships: CandidateRelationship[];
}

export interface CandidateDetail<T extends Candidate = Candidate> {
  candidate: T;
  evidence: CandidateEvidence[];
  relatedNodes: GraphNode[];
}

export interface BulkApproveResult {
  approvedNodeIds: string[];
  approvedRelationshipIds: string[];
  failures: { id: string; kind: "node" | "relationship"; reason: string }[];
}

export interface CandidateMergeResult {
  candidateId: string;
  kind: "node" | "relationship";
  targetNode: GraphNode | null;
  targetRelationship: GraphEdge | null;
}
