"""Human review of proposed graph records before they become course knowledge.

Candidates are stored in the graph tables with a non-approved review status, so approving a
candidate promotes the existing record through `CourseGraph` instead of copying data between
stores. Nothing in this module touches graph tables directly.
"""

from typing import Any

from app.documents.service import DocumentNotFoundError, DocumentService
from app.graph.service import (
    CourseGraph,
    DuplicateGraphRecord,
    GraphRecordNotFound,
    InvalidGraphReference,
    InvalidReviewTransition,
)
from app.models import (
    APPROVED_REVIEW_STATUSES,
    REVIEWABLE_STATUSES,
    Document,
    GraphEdge,
    GraphEvidence,
    GraphNode,
    ReviewStatus,
    utcnow,
)

RELATED_NODE_LIMIT = 5
#: Candidate-level problems that must not abort an otherwise valid bulk approval.
REVIEW_FAILURES = (
    DuplicateGraphRecord,
    GraphRecordNotFound,
    InvalidGraphReference,
    InvalidReviewTransition,
)


class GraphReviewService:
    """Course-scoped review actions shared by HTTP routes and future agents."""

    def __init__(self, graph: CourseGraph, documents: DocumentService) -> None:
        self.graph = graph
        self.documents = documents

    # Reading the queue ---------------------------------------------------

    def queue(self, course_id: str, *, document_id: str | None = None) -> dict[str, Any]:
        self.documents.require_course(course_id)
        if document_id is not None:
            self.documents.get_document(course_id, document_id)
        nodes = self.graph.list_candidate_nodes(course_id, document_id=document_id)
        relationships = self.graph.list_candidate_relationships(
            course_id, document_id=document_id
        )
        return {
            "pending_count": len(nodes) + len(relationships),
            "nodes": [self._node_summary(course_id, node) for node in nodes],
            "relationships": [
                self._relationship_summary(course_id, relationship)
                for relationship in relationships
            ],
        }

    def node_detail(self, course_id: str, node_id: str) -> dict[str, Any]:
        self.documents.require_course(course_id)
        node = self.graph.get_candidate_node(course_id, node_id)
        related = [
            candidate
            for candidate in self.graph.search_nodes(
                course_id, node.label, limit=RELATED_NODE_LIMIT + 1
            )
            if candidate.id != node.id
        ][:RELATED_NODE_LIMIT]
        return {
            "candidate": self._node_summary(course_id, node),
            "evidence": self._evidence(course_id, "node", node.id),
            "related_nodes": related,
        }

    def relationship_detail(self, course_id: str, relationship_id: str) -> dict[str, Any]:
        self.documents.require_course(course_id)
        relationship = self.graph.get_candidate_relationship(course_id, relationship_id)
        endpoints = [
            node
            for node in (
                self.graph.find_node(relationship.source_node_id),
                self.graph.find_node(relationship.target_node_id),
            )
            if node is not None
        ]
        return {
            "candidate": self._relationship_summary(course_id, relationship),
            "evidence": self._evidence(course_id, "relationship", relationship.id),
            "related_nodes": endpoints,
        }

    # Review actions ------------------------------------------------------

    def approve_node(self, course_id: str, node_id: str) -> dict[str, Any]:
        self.documents.require_course(course_id)
        node = self._reviewable_node(course_id, node_id)
        existing = self.graph.find_approved_node_by_label(course_id, node.label)
        if existing is not None and existing.id != node.id:
            raise DuplicateGraphRecord(
                "An approved node already uses this label; merge the candidate instead"
            )
        values: dict[str, Any] = {
            "review_status": ReviewStatus.APPROVED,
            "reviewed_at": utcnow(),
        }
        if node.review_status is ReviewStatus.EDITED:
            values["metadata"] = self._with_review_flag(node.node_metadata, "edited")
        updated = self.graph.update_node(course_id, node_id, values)
        return self._node_summary(course_id, updated)

    def approve_relationship(self, course_id: str, relationship_id: str) -> dict[str, Any]:
        self.documents.require_course(course_id)
        relationship = self._reviewable_relationship(course_id, relationship_id)
        self._require_approved_endpoints(course_id, relationship)
        existing = self.graph.find_approved_relationship(
            course_id,
            relationship.source_node_id,
            relationship.target_node_id,
            relationship.type,
        )
        if existing is not None and existing.id != relationship.id:
            raise DuplicateGraphRecord(
                "An approved relationship already connects these nodes; merge the candidate instead"
            )
        values: dict[str, Any] = {
            "review_status": ReviewStatus.APPROVED,
            "reviewed_at": utcnow(),
        }
        if relationship.review_status is ReviewStatus.EDITED:
            values["metadata"] = self._with_review_flag(relationship.edge_metadata, "edited")
        updated = self.graph.update_relationship(course_id, relationship_id, values)
        return self._relationship_summary(course_id, updated)

    def reject_node(
        self, course_id: str, node_id: str, note: str | None = None
    ) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_node(course_id, node_id)
        rejected_at = utcnow()
        self._reject_dependent_relationships(course_id, node_id, rejected_at)
        updated = self.graph.update_node(
            course_id,
            node_id,
            {
                "review_status": ReviewStatus.REJECTED,
                "review_note": note,
                "reviewed_at": rejected_at,
                "archived_at": rejected_at,
            },
        )
        return self._node_summary(course_id, updated)

    def reject_relationship(
        self, course_id: str, relationship_id: str, note: str | None = None
    ) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_relationship(course_id, relationship_id)
        rejected_at = utcnow()
        updated = self.graph.update_relationship(
            course_id,
            relationship_id,
            {
                "review_status": ReviewStatus.REJECTED,
                "review_note": note,
                "reviewed_at": rejected_at,
                "archived_at": rejected_at,
            },
        )
        return self._relationship_summary(course_id, updated)

    def edit_node(
        self, course_id: str, node_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_node(course_id, node_id)
        updated = self.graph.update_node(
            course_id, node_id, {**values, "review_status": ReviewStatus.EDITED}
        )
        return self._node_summary(course_id, updated)

    def edit_relationship(
        self, course_id: str, relationship_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_relationship(course_id, relationship_id)
        updated = self.graph.update_relationship(
            course_id, relationship_id, {**values, "review_status": ReviewStatus.EDITED}
        )
        return self._relationship_summary(course_id, updated)

    def merge_node(self, course_id: str, node_id: str, target_id: str) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_node(course_id, node_id)
        target = self.graph.merge_node(course_id, node_id, target_id)
        return {"candidate_id": node_id, "kind": "node", "target_node": target}

    def merge_relationship(
        self, course_id: str, relationship_id: str, target_id: str
    ) -> dict[str, Any]:
        self.documents.require_course(course_id)
        self._reviewable_relationship(course_id, relationship_id)
        target = self.graph.merge_relationship(course_id, relationship_id, target_id)
        return {
            "candidate_id": relationship_id,
            "kind": "relationship",
            "target_relationship": target,
        }

    def approve_many(
        self, course_id: str, node_ids: list[str], relationship_ids: list[str]
    ) -> dict[str, Any]:
        """Approve every valid candidate and report the ones that could not be approved.

        Nodes are approved first so relationships between newly approved nodes succeed in the
        same request. Each candidate is approved independently: one failure never discards the
        approvals that already succeeded.
        """
        self.documents.require_course(course_id)
        approved_nodes: list[str] = []
        approved_relationships: list[str] = []
        failures: list[dict[str, str]] = []
        for node_id in dict.fromkeys(node_ids):
            try:
                self.approve_node(course_id, node_id)
                approved_nodes.append(node_id)
            except REVIEW_FAILURES as error:
                failures.append({"id": node_id, "kind": "node", "reason": str(error)})
        for relationship_id in dict.fromkeys(relationship_ids):
            try:
                self.approve_relationship(course_id, relationship_id)
                approved_relationships.append(relationship_id)
            except REVIEW_FAILURES as error:
                failures.append(
                    {"id": relationship_id, "kind": "relationship", "reason": str(error)}
                )
        return {
            "approved_node_ids": approved_nodes,
            "approved_relationship_ids": approved_relationships,
            "failures": failures,
        }

    # Internals -----------------------------------------------------------

    def _reviewable_node(self, course_id: str, node_id: str) -> GraphNode:
        node = self.graph.get_candidate_node(course_id, node_id)
        self._require_reviewable(node.review_status, "node")
        return node

    def _reviewable_relationship(self, course_id: str, relationship_id: str) -> GraphEdge:
        relationship = self.graph.get_candidate_relationship(course_id, relationship_id)
        self._require_reviewable(relationship.review_status, "relationship")
        return relationship

    @staticmethod
    def _require_reviewable(status: ReviewStatus, kind: str) -> None:
        if status not in REVIEWABLE_STATUSES:
            raise InvalidReviewTransition(
                f"This {kind} is already {status.value.lower()} and cannot be reviewed again"
            )

    @staticmethod
    def _with_review_flag(metadata: dict[str, Any] | None, flag: str) -> dict[str, Any]:
        merged = dict(metadata or {})
        review = dict(merged.get("review") or {})
        review[flag] = True
        merged["review"] = review
        return merged

    def _require_approved_endpoints(self, course_id: str, relationship: GraphEdge) -> None:
        for node_id in (relationship.source_node_id, relationship.target_node_id):
            node = self.graph.find_node(node_id)
            if (
                node is None
                or node.course_id != course_id
                or node.archived_at is not None
                or node.review_status not in APPROVED_REVIEW_STATUSES
            ):
                raise InvalidGraphReference(
                    "Approve or merge both connected nodes before approving this relationship"
                )

    def _reject_dependent_relationships(
        self, course_id: str, node_id: str, rejected_at: Any
    ) -> None:
        """Reject pending relationships that depend on a rejected node.

        Approved graph data is never touched: only candidates still in review are affected.
        """
        for relationship in self.graph.list_candidate_relationships(course_id):
            if node_id not in (relationship.source_node_id, relationship.target_node_id):
                continue
            self.graph.update_relationship(
                course_id,
                relationship.id,
                {
                    "review_status": ReviewStatus.REJECTED,
                    "review_note": "Rejected with its candidate node",
                    "reviewed_at": rejected_at,
                    "archived_at": rejected_at,
                },
            )

    def _document(self, course_id: str, document_id: str | None) -> Document | None:
        if not document_id:
            return None
        try:
            return self.documents.get_document(course_id, document_id)
        except DocumentNotFoundError:
            return None

    def _evidence(
        self, course_id: str, target_type: str, target_id: str
    ) -> list[dict[str, Any]]:
        records: list[GraphEvidence] = self.graph.list_evidence(
            course_id, target_type, target_id
        )
        items: list[dict[str, Any]] = []
        for record in records:
            document = self._document(course_id, record.document_id)
            location = dict(record.source_location or {})
            items.append(
                {
                    "id": record.id,
                    "document_id": record.document_id,
                    "document_name": document.original_filename if document else "Unknown source",
                    "document_type": document.document_type if document else "OTHER",
                    "page": location.get("page"),
                    "section": location.get("section"),
                    "source_location": location,
                    "excerpt": record.excerpt,
                    "confidence": record.confidence,
                    "created_at": record.created_at,
                }
            )
        return items

    def _node_summary(self, course_id: str, node: GraphNode) -> dict[str, Any]:
        document = self._document(course_id, node.source_document_id)
        return {
            "kind": "node",
            "id": node.id,
            "course_id": node.course_id,
            "type": node.type,
            "label": node.label,
            "description": node.description,
            "confidence": node.confidence,
            "review_status": node.review_status,
            "review_note": node.review_note,
            "reviewed_at": node.reviewed_at,
            "merged_into_node_id": node.merged_into_node_id,
            "source_document_id": node.source_document_id,
            "source_document_name": document.original_filename if document else None,
            "metadata": node.node_metadata or {},
            "evidence_count": len(self.graph.list_evidence(course_id, "node", node.id)),
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    def _relationship_summary(self, course_id: str, relationship: GraphEdge) -> dict[str, Any]:
        document = self._document(course_id, relationship.source_document_id)
        source_node = self.graph.find_node(relationship.source_node_id)
        target_node = self.graph.find_node(relationship.target_node_id)
        return {
            "kind": "relationship",
            "id": relationship.id,
            "course_id": relationship.course_id,
            "type": relationship.type,
            "source_node_id": relationship.source_node_id,
            "target_node_id": relationship.target_node_id,
            "source_node_label": source_node.label if source_node else None,
            "target_node_label": target_node.label if target_node else None,
            "confidence": relationship.confidence,
            "review_status": relationship.review_status,
            "review_note": relationship.review_note,
            "reviewed_at": relationship.reviewed_at,
            "merged_into_edge_id": relationship.merged_into_edge_id,
            "source_document_id": relationship.source_document_id,
            "source_document_name": document.original_filename if document else None,
            "metadata": relationship.edge_metadata or {},
            "evidence_count": len(
                self.graph.list_evidence(course_id, "relationship", relationship.id)
            ),
            "created_at": relationship.created_at,
            "updated_at": relationship.updated_at,
        }
