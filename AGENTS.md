# Chanakya / SIH 2026 Development Rules

## Project
This repository is being developed for SIH 2026 Problem Statement 26189.

## Important Paths
Main project:
C:\Users\hamda\OneDrive\Desktop\codex_sih\Chanakya

## Python Environments

### Backend
- Backend Python version: 3.11.0
- Backend uses its own `.venv`
- All backend dependencies must be installed only in the Backend Python 3.11 environment.

### DocRE
- DocRE uses a separate `.venv`
- DocRE Python version: 3.10.11
- DocRE dependencies must remain inside the DocRE environment.
- NEVER mix DocRE Python 3.10 dependencies into the Backend Python 3.11 environment.

If Backend needs to communicate with DocRE, use a clean integration boundary such as a subprocess/service rather than importing incompatible DocRE dependencies into Backend.

## AI/NLP Pipeline

The intended pipeline is:

Document ingestion
→ file type detection
→ native text extraction where possible
→ OCR where necessary
→ text preprocessing
→ GLiNER entity extraction
→ UIE relationship/information extraction
→ temporal extraction
→ Pydantic validation
→ structured graph-ready JSON
→ FastAPI API
→ existing frontend

## Required Technologies

### OCR
Use PaddleOCR as the primary OCR system.

### Entity Extraction
Use GLiNER as the primary entity extraction / NER system.

### Relationship / Information Extraction
Use UIE as the primary relationship/information extraction system.

### PDF Text Extraction
Use PyMuPDF for native text extraction from text-based PDFs before using OCR.

### Validation
Use Pydantic for structured output validation.

### Backend
Use FastAPI for the backend API where appropriate.

## Entity Resolution

Entity resolution is OUT OF SCOPE for the current NLP implementation.

Do NOT implement:
- global identity matching
- cross-document entity merging
- database identity resolution
- graph-based entity resolution

Document-level/local entity IDs are acceptable.

The graph team will handle integration with historical graph/database identities.

## Semantic Search

Semantic search is OUT OF SCOPE.

Do NOT add:
- FAISS
- vector database
- embeddings-based document search
- RAG
- semantic search infrastructure

## Graph / GNN

Do NOT implement the graph team's components.

Out of scope:
- Memgraph integration
- GNN
- HGT
- temporal GNN
- graph neural network training
- federated learning
- Flower
- FedProx
- homomorphic encryption

The NLP module should produce clean graph-ready structured JSON for the graph team.

## Frontend

The existing Chanakya UI must be preserved.

Do NOT replace or redesign the existing UI unnecessarily.

Only integrate the required backend/API functionality into the existing interface.

## Input Formats

The system must support the actual document/input formats provided with the project.

Inspect the provided examples before deciding what formats need to be implemented.

Do not assume the system only receives FIR PDFs.

Use an extensible document-ingestion abstraction where appropriate.

## Provenance

Extracted entities and relationships should retain useful provenance such as:

- document ID
- page number where applicable
- source location where applicable
- evidence text
- confidence

This is for investigator traceability.

Do not claim that model output is automatically legally admissible evidence.

## Development Method

Always inspect the existing implementation before modifying it.

Do not rewrite working components unnecessarily.

Work incrementally.

After each meaningful phase:
1. run tests
2. verify the result
3. inspect the diff
4. commit stable changes

Do not make a huge unrelated refactor.

## First Task

The first task is ONLY an audit.

Before making major changes, inspect:

1. existing frontend
2. existing backend
3. Backend Python environment
4. DocRE repository
5. DocRE Python environment
6. existing APIs
7. upload/document-processing code
8. configuration files
9. requirements files
10. provided input examples

Report:
- current architecture
- what already exists
- what can be reused
- what is missing
- dependency conflicts
- recommended implementation order

Do NOT perform a large implementation during the audit.

Do NOT redesign the frontend.

## Supported Input Sources

The system must be designed for multiple investigative data sources.

Expected input formats include:

- FIR / Police reports: PDF, TXT, DOCX
- CDR: CSV, Excel
- Financial transactions: CSV, Excel
- Criminal history: JSON, CSV, database exports
- Surveillance reports: PDF, TXT
- Social-media intelligence: JSON, CSV, TXT

Do not assume that all inputs are documents requiring OCR.

The ingestion layer must detect the input type and route it to the appropriate parser.

Use OCR only when the input actually requires OCR.
Use native/structured parsing whenever possible.

## Evidence and Provenance

Evidence/provenance is a first-class requirement.

Every extracted or normalized item should retain enough information to trace it back to its original source.

The system should distinguish:

### Provenance
Where the information came from:
- document_id
- page number where applicable
- paragraph where applicable
- line number where applicable
- sheet name
- row/column
- JSON path
- character offsets where applicable

### Evidence
The original text or source data supporting the item:
- evidence_text / original value
- confidence where applicable

Examples:

PDF:
page_number + character offsets + source text

TXT:
line number + character offsets + source text

DOCX:
paragraph/table location + source text

CSV/XLSX:
sheet + row + column + original value

JSON:
JSON path + original value

Never discard source-location information during normalization.