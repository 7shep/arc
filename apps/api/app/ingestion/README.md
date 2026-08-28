# Ingestion boundary

Format-specific document parsing lives here. It reads stored PDF, Markdown, plain-text, and Word documents through the storage contract and replaces source-aware SQL chunks transactionally. Future knowledge extraction should consume these chunks and write graph entities through `CourseGraph`.

