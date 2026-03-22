# Unified Import Workflow

## Status: Design — Not yet implemented

*Created: March 22, 2026*

---

## Overview

Replace all scattered upload buttons and the Chrome extension with a single, cohesive import workflow accessible from anywhere in the app. The workflow is a modal dialog that guides users through: file upload → AI parsing → change review → AI chat → confirmation.

---

## 1. Removing the Chrome Extension

### What to remove
- `/extension/` directory (manifest.json, background.js, popup/, content/)
- All references to "chrome extension" in documentation and Guide page
- Backend endpoints that serve extension-specific flows (screenshot parsing stays but is repurposed)
- References in `ingest.py` to `chrome_extension` source

### What to keep
- The core AI parsing logic (Claude document analysis)
- The confirm workflow (user reviews changes before saving)
- The enrichment logic (showing current values, destinations, actions)

---

## 2. Import Modal: User Flow

### Step 1: Upload (supports multiple files, queued)

```
┌──────────────────────────────────────────────────┐
│  Import Data                              [X]    │
│                                                  │
│  Upload financial documents for AI analysis.     │
│  Multiple files can be uploaded — they'll be     │
│  processed and reviewed one at a time.            │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │                                            │  │
│  │  📄 Drop files here or click to browse     │  │
│  │                                            │  │
│  │     Supported: PDF, XLSX, CSV              │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Queued files:                                   │
│  ✅ 2025 W2 (1).pdf          — processing...     │
│  ⏳ Pay Date 2025-12-19.pdf  — waiting           │
│  ⏳ retirement-statement.pdf — waiting           │
│                                                  │
│  Context: Income  (from launch location)         │
│                                                  │
│  💡 For income data, try uploading:              │
│     • W2 form (annual tax summary)               │
│     • Pay stub (salary/RSU breakdown)            │
│     • 401(k) statement (retirement account)      │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Multi-file behavior**: Users can drop/select multiple files at once. Files are added to a queue. The system processes and presents them **one at a time** — after confirming or skipping one document, the next in the queue is automatically processed. Progress indicator shows which file is current and how many remain.

**Context-awareness**: When launched from a specific page, the modal pre-sets a category context that:
- Tailors the guidance text ("For income data, try uploading...")
- Tells the AI parser what to focus on
- Highlights missing data relevant to that category after parsing

**Contexts:**
| Launch Location | Context | Expected Documents | Missing Data Highlights |
|---|---|---|---|
| Income page | `income` | W2, pay stub | base_salary, rsu_income if missing |
| 401(k) page | `retirement` | 401(k) statement | contribution rates, holdings |
| Property page | `property` | Mortgage statement | balance, rate, payment |
| RSU page | `rsu` | E-Trade spreadsheet | vest events, cost basis |
| Settings/Import | `general` | Any document | None specific |
| Dashboard | `general` | Any document | None specific |

### Step 2: Processing (Loading)

```
┌──────────────────────────────────────────────────┐
│  Import Data                              [X]    │
│                                                  │
│  Analyzing: 2025 W2 (1).pdf                     │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  🔄 Reading document...                    │  │
│  │  🔄 Extracting financial values...         │  │
│  │  ⏳ Matching to database fields...         │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  This usually takes 5-15 seconds.                │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Step 3: Review Changes

```
┌──────────────────────────────────────────────────────────────────┐
│  Import Data                                              [X]   │
│                                                                 │
│  ┌─ AI Summary ────────────────────────────────────────────────┐│
│  │ Found 12 values from your 2025 W2. Gross pay ($269,131),   ││
│  │ federal tax ($49,965), state tax ($12,701), and 9 other    ││
│  │ fields were identified. Base salary and RSU income were    ││
│  │ NOT found — upload a pay stub to get the salary/RSU split. ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ⚠️ Missing for Income:                                        │
│    • base_salary — upload a pay stub or enter manually          │
│    • rsu_income — upload a pay stub or enter manually           │
│                                                                 │
│  Database Changes                          [Summary ▾ | Detail] │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ✅ W2 Records: 1 row updated (2025), 10 fields             ││
│  │    └─ gross_pay: $250,000 → $269,131                       ││
│  │    └─ federal_tax: (new) $49,965                           ││
│  │    └─ state_tax: (new) $12,701                             ││
│  │    └─ ... 7 more fields                                    ││
│  │                                                            ││
│  │ ☐ Mortgage: 1 row updated, 2 fields  (unchecked = skip)   ││
│  │    └─ current_balance: $442,000 → $440,689                 ││
│  │    └─ monthly_payment: (unchanged) $3,051                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  💬 Ask AI about these findings...                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ User: Why didn't you find my base salary?                  ││
│  │                                                            ││
│  │ AI: Base salary isn't a standard W2 field — the W2 only   ││
│  │ reports gross pay (Box 1). To get the salary vs RSU split, ││
│  │ upload your last pay stub of the year which shows YTD      ││
│  │ "Regular" and "RSU Gain" separately.                       ││
│  │                                                            ││
│  │ User: Set base_salary to 155000                            ││
│  │                                                            ││
│  │ AI: ✓ Added base_salary = $155,000 to the changes.        ││
│  │ W2 Records will now update 11 fields instead of 10.       ││
│  └─────────────────────────────────────────────────────────────┘│
│  [Type a message...]                              [Send]        │
│                                                                 │
│                              [Cancel]  [Accept Selected Changes]│
└──────────────────────────────────────────────────────────────────┘
```

### Step 4: Confirmation

```
┌──────────────────────────────────────────────────┐
│  Import Data                              [X]    │
│                                                  │
│  ✅ Import complete                              │
│                                                  │
│  • W2 Records: 11 fields updated for 2025       │
│  • Mortgage: skipped (unchecked)                 │
│                                                  │
│  Data is now reflected across the app.           │
│                                                  │
│                                       [Done]     │
└──────────────────────────────────────────────────┘
```

---

## 3. Backend Architecture

### Upload Session Model

```python
class ImportSession:
    """Tracks an import from upload through confirmation."""
    id: str  # UUID
    tenant_id: str  # for multi-tenancy
    status: str  # "uploading" | "processing" | "review" | "confirmed" | "rejected" | "expired"
    context: str  # "income" | "retirement" | "property" | "rsu" | "general"

    # File info
    filename: str
    file_type: str  # "pdf" | "xlsx" | "csv"
    file_size: int
    file_hash: str  # for dedup

    # AI results
    raw_ai_response: str  # Full Claude response
    parsed_findings: list[dict]  # Structured findings
    ai_summary: str  # Natural language summary
    missing_fields: list[dict]  # Fields expected but not found

    # Change set
    proposed_changes: list[ProposedChange]  # What will change in the DB
    accepted_changes: list[str]  # IDs of changes user accepted

    # Chat history
    chat_messages: list[dict]  # [{role, content, timestamp}]

    # Metadata
    created_at: datetime
    expires_at: datetime  # Sessions expire after 24h
    confirmed_at: datetime | None
```

```python
class ProposedChange:
    """A single proposed database change."""
    id: str  # UUID
    table: str  # "w2_records", "mortgages", etc.
    action: str  # "create" | "update" | "upsert"
    row_identifier: dict  # e.g., {"tax_year": 2025}
    fields: list[FieldChange]
    is_accepted: bool  # Default True for mapped fields, False for unmapped

class FieldChange:
    """A single field-level change."""
    column: str
    old_value: any | None
    new_value: any
    is_new: bool  # True if column was previously null
    source: str  # "ai_parsed" | "user_corrected" | "user_added"
```

### API Endpoints

```
# Session lifecycle
POST   /api/v1/import/upload      → Create session, upload file, start processing
GET    /api/v1/import/{id}        → Get session status + results
PUT    /api/v1/import/{id}/accept → Accept/reject specific changes
POST   /api/v1/import/{id}/confirm → Apply accepted changes to DB
DELETE /api/v1/import/{id}        → Cancel/discard session

# Chat
POST   /api/v1/import/{id}/chat   → Send message, get AI response
                                    (can modify proposed changes)

# Webhook (future)
POST   /api/v1/import/webhook     → Register webhook for import events
       Events: import.processing, import.ready, import.confirmed
```

### Processing Pipeline

```
1. File Upload
   → Validate file type/size
   → Store file temporarily
   → Create ImportSession (status: "processing")
   → Return session ID immediately

2. AI Analysis (async or sync)
   → Encode file for Claude (base64 PDF, or extract text for CSV/XLSX)
   → Send to Claude with context-aware prompt
   → Parse structured response
   → Run deduplication
   → Enrich with current DB values (show old → new)
   → Identify missing fields for the context category
   → Generate natural language summary
   → Update session (status: "review")

3. Change Review
   → Client polls session status or gets webhook
   → Displays proposed changes with accept/reject per change
   → Chat messages sent to Claude with session context

4. Confirmation
   → Apply accepted changes to database
   → Log import in audit trail
   → Update session (status: "confirmed")
   → Clean up temporary file
```

### Context-Aware Prompts

Each context gets a tailored Claude prompt that focuses extraction:

```python
CONTEXT_PROMPTS = {
    "income": {
        "prompt": INCOME_PARSE_PROMPT,  # W2 + pay stub fields
        "expected_fields": ["gross_pay", "base_salary", "rsu_income", "federal_tax", ...],
        "guidance": "For income data, try uploading a W2 form or pay stub.",
        "examples": ["W2 form (annual tax summary)", "Pay stub (salary/RSU breakdown)"],
    },
    "retirement": {
        "prompt": RETIREMENT_PARSE_PROMPT,
        "expected_fields": ["total_balance", "roth_balance", "pretax_deferral_rate", ...],
        "guidance": "Upload your 401(k) quarterly statement.",
        "examples": ["401(k) statement from T. Rowe Price, Fidelity, etc."],
    },
    "property": {
        "prompt": MORTGAGE_PARSE_PROMPT,
        "expected_fields": ["current_balance", "rate", "monthly_payment", ...],
        "guidance": "Upload your mortgage statement.",
        "examples": ["Monthly mortgage statement from Chase, Wells Fargo, etc."],
    },
    "rsu": {
        "prompt": RSU_PARSE_PROMPT,  # E-Trade specific
        "expected_fields": ["grants", "vest_events", "share_price"],
        "guidance": "Upload E-Trade 'Download by Type (expanded)' spreadsheet.",
        "examples": ["E-Trade holdings export (.xlsx)"],
    },
    "general": {
        "prompt": GENERAL_PARSE_PROMPT,  # Auto-detect document type
        "expected_fields": [],
        "guidance": "Upload any financial document.",
        "examples": ["W2, pay stub, mortgage statement, 401(k) statement, bank statement"],
    },
}
```

### Chat with AI

The chat feature sends messages to Claude with the full context:

```python
async def chat_with_import(session: ImportSession, user_message: str) -> str:
    """Send a chat message about the import session."""
    context = f"""
    You are helping a user review imported financial data.

    Document: {session.filename}
    Category: {session.context}

    Findings: {json.dumps(session.parsed_findings)}
    Proposed changes: {json.dumps(session.proposed_changes)}
    Missing fields: {json.dumps(session.missing_fields)}

    Chat history: {json.dumps(session.chat_messages)}

    User's message: {user_message}

    You can:
    1. Answer questions about the findings
    2. Explain why certain fields weren't found
    3. Accept corrections like "set base_salary to 155000" — respond with a
       JSON action: {"action": "set_field", "table": "w2_records", "column": "base_salary", "value": 155000}
    4. Suggest what documents to upload for missing data

    Respond naturally. If you're making a data change, include the JSON action on a separate line.
    """

    response = claude.messages.create(...)

    # Parse any actions from the response
    # Update proposed_changes if user corrected a value

    return response_text
```

---

## 4. Frontend Architecture

### ImportModal Component

```
/frontend/src/components/import/
├── ImportModal.vue          # Main modal container, manages steps
├── UploadStep.vue           # File drop zone + context guidance
├── ProcessingStep.vue       # Loading animation with status updates
├── ReviewStep.vue           # Change review with accept/reject
├── ConfirmStep.vue          # Success summary
├── ChangePreview.vue        # Table-level + field-level diff
├── AiChat.vue               # Chat panel with AI
├── MissingFieldsAlert.vue   # Warning about expected but missing data
└── useImportSession.ts      # Composable for session state management
```

### Launching the Modal

```typescript
// Composable that any page can use
const { openImport } = useImportModal()

// From Income page:
openImport({ context: 'income' })

// From Property page:
openImport({ context: 'property' })

// From toolbar/global:
openImport({ context: 'general' })
```

The modal is registered at the App.vue level (via Teleport to body) so it overlays everything.

### State Management

```typescript
// useImportSession.ts
interface ImportSession {
  id: string
  status: 'idle' | 'uploading' | 'processing' | 'review' | 'confirming' | 'done' | 'error'
  context: string
  filename: string
  aiSummary: string
  missingFields: MissingField[]
  proposedChanges: ProposedChange[]
  chatMessages: ChatMessage[]
  result: ConfirmResult | null
}
```

---

## 5. Migration from Current Upload Buttons

### Current upload locations to replace:
1. **Income page** → "Upload W2" + "Upload Pay Stub" buttons → Single "Import" button → `openImport({ context: 'income' })`
2. **401(k) page** → "Upload Statement" button → `openImport({ context: 'retirement' })`
3. **Property page** → "Upload Mortgage Statement" button → `openImport({ context: 'property' })`
4. **RSU page** → "Import E-Trade Export" button → `openImport({ context: 'rsu' })`

### Backend consolidation:
- Merge `/api/ingest/w2-upload`, `/api/ingest/paystub-upload`, `/api/ingest/mortgage-upload`, `/api/retirement/upload-statement` into a single `/api/v1/import/upload` endpoint
- The context parameter determines which Claude prompt to use
- The confirm logic routes to the correct table(s) based on what was found

### What stays separate:
- The Plaid sync flow (not file-based, different UX)
- Manual data entry in Settings

---

## 6. API Flow (Programmatic)

```
# 1. Upload a file
POST /api/v1/import/upload
Content-Type: multipart/form-data
X-API-Key: sk_...
body: file=@w2.pdf, context=income

Response: { "session_id": "abc-123", "status": "processing" }

# 2. Poll for status (or use webhook)
GET /api/v1/import/abc-123
X-API-Key: sk_...

Response: {
  "status": "review",
  "ai_summary": "Found 12 values from 2025 W2...",
  "proposed_changes": [...],
  "missing_fields": [...]
}

# 3. Accept changes
PUT /api/v1/import/abc-123/accept
X-API-Key: sk_...
body: { "accepted_change_ids": ["change-1", "change-2", ...] }

# 4. Confirm (apply to database)
POST /api/v1/import/abc-123/confirm
X-API-Key: sk_...

Response: { "status": "confirmed", "changes_applied": 10 }
```

---

## 7. Implementation Phases

### Phase 1: Core Modal + Unified Upload
- [ ] Create ImportModal.vue with step-based flow
- [ ] Create unified `/api/v1/import/upload` endpoint
- [ ] Create ImportSession model + CRUD
- [ ] Implement context-aware prompting
- [ ] Replace individual upload buttons with `openImport()`
- [ ] Delete Chrome extension code

### Phase 2: Change Review UX
- [ ] Build ChangePreview component (summary + detail toggle)
- [ ] Build MissingFieldsAlert component
- [ ] Add accept/reject per change group
- [ ] AI summary generation

### Phase 3: AI Chat
- [ ] Build AiChat component
- [ ] Chat API endpoint with session context
- [ ] Support value corrections via chat
- [ ] Chat history persistence in session

### Phase 4: API + Webhook
- [ ] Versioned API endpoints (`/api/v1/import/`)
- [ ] Session polling endpoint
- [ ] Webhook delivery for import events
- [ ] API documentation

---

## 8. Design Decisions (Finalized)

1. **Chat corrections**: Explicit accept per suggestion — AI proposes a change inline in chat, user clicks "Accept" on the suggestion, only then does it appear in the change preview.
2. **Chrome extension**: Remove immediately as part of this work. Delete `/extension/` directory and all references.
3. **Transition**: Replace all existing upload buttons immediately with the new modal. No dual-mode period.
4. **Modal layout**: Full-screen (~90% viewport) with sidebar chat panel. Left: AI summary + change preview (scrollable). Right: persistent chat (~300px).
5. **Multi-file**: Multiple files can be queued, processed and reviewed one at a time sequentially. After confirming/skipping one, the next auto-starts.

## 9. Open Questions

1. **File size limits**: What's the max PDF size to send to Claude? Currently ~10MB for base64.
2. **Session storage**: Store sessions in DB or Redis? DB is simpler, Redis is faster for expiry.
3. **Import history**: Should users be able to see past imports and what they changed? The ImportLog table partially does this already.
