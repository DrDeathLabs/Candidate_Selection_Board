# User Guide

This guide explains how to use Candidate Selection Board after it is installed.

## Core Concepts

Candidate Selection Board is organized around:

- cases,
- documents,
- candidates,
- stages,
- rubrics,
- evaluations,
- adjudications,
- exports.

A case is a hiring action. Documents are the uploaded position description and resume bundle. Candidates are reconciled from the resume bundle. Each candidate advances through a fixed stage chain evaluated against a shared rubric.

## User Roles

| Role | Purpose |
| --- | --- |
| `SYSTEM_ADMINISTRATOR` | Full platform administration, user management, audit access |
| `CASE_OWNER` | Create and manage hiring cases, upload documents |
| `SELECTING_OFFICIAL` | Adjudication, final selection decisions, export approval |
| `PANEL_REVIEWER` | Score candidates in assigned stages |
| `HR_REVIEWER` | Review evaluations, validate compliance documentation |
| `READ_ONLY_AUDITOR` | Read-only access to cases and audit events |
| `SECURITY_ADMINISTRATOR` | Access to security posture, SOC log, session management |

## First Login and MFA Enrollment

After the administrator account is bootstrapped:

1. Open the app at `http://127.0.0.1:8610` (or your configured URL).
2. Sign in with the `admin` username and the password printed during bootstrap.
3. You will be directed to TOTP MFA enrollment before any other action is permitted.
4. Open your authenticator app (Microsoft Authenticator, Google Authenticator, 1Password, Bitwarden, Authy, or Duo Mobile).
5. Scan the QR code or enter the setup key.
6. Enter the six-digit code to confirm enrollment.
7. Save your recovery codes in a secure location. They are shown once.

MFA is required for all roles except `READ_ONLY_AUDITOR`. Users without MFA are blocked from all features until they complete enrollment.

## Admin Panel

Administrators and security administrators access the Admin panel from the left navigation.

The Admin panel includes:

- security posture dashboard,
- SOC audit log,
- session monitor,
- user management,
- platform settings.

### Security Posture Dashboard

Reports operational status including:

- FISMA control implementation status,
- failed login attempts and locked accounts,
- privileged MFA coverage,
- service health (PostgreSQL, Redis, OpenSearch, MinIO),
- NIST SP 800-53 control indicators.

This dashboard is a monitoring aid, not a formal compliance attestation.

### SOC Audit Log

Records all significant actions: authentication events, case modifications, evaluations, adjudication decisions, admin changes, and export actions. Use it for compliance review and incident investigation.

### Session Monitor

Lists active sessions across all users. Administrators can revoke individual sessions or all sessions for a user. Sessions expire automatically per the configured idle and absolute timeouts.

### User Management

Administrators can create users, assign roles, reset MFA, unlock locked accounts, and disable accounts. Role assignment follows least-privilege: assign only the roles needed for the user's function.

The system creates one bootstrap `admin` account. All subsequent users are created here or via OIDC.

## Creating a Case

A case represents a single competitive hiring action.

1. Navigate to **Cases** from the left menu.
2. Select **New Case**.
3. Enter the position title, organization, and hiring action type.
4. Upload the position description document.
5. Save the case.

The case starts in the **Intake** stage.

## Uploading Documents

From the Engagement Prep workspace:

1. Upload the position description if not done during case creation.
2. Upload the resume bundle (a single PDF containing all candidate resumes).
3. The system classifies documents, extracts text via OCR, and splits the bundle into individual candidate records.

Document processing runs in the background. Status is visible in the case document list.

## Rubric Generation

After the position description is processed, the system generates an evaluation rubric derived from the PD:

1. Navigate to **Rubrics** for the case.
2. Review the AI-generated dimensions, weights, and critical factors.
3. Edit dimensions, adjust weights, or add custom factors as needed.
4. Lock the rubric before the review stage begins.

A locked rubric cannot be modified after evaluations start.

## Expert Council AI

The expert council is the core AI capability. It simulates a structured selection board deliberation using 13 specialist agents and produces a full deliberation transcript alongside a board recommendation.

### How It Works

The council runs in three phases:

**Phase I — Opening Statements**

Each specialist agent independently evaluates the candidate across all rubric dimensions. Every agent statement includes:
- dimension-level assessments with cited evidence
- evidence quality tag for each claim: DOCUMENTED, INFERRED, or ABSENT
- confidence rating from 0.0 to 1.0
- list of strengths, concerns, and key findings

Agents see the full transcript of prior statements, enabling cross-referencing.

**Phase II — Skeptic Challenges and Rebuttals**

The Skeptic Reviewer targets 2–3 specific claims from Phase I, naming the challenged agent and the exact claim. Challenged agents respond with one of three dispositions:
- **SUSTAINED** — challenge is valid; the claim was overstated or unsupported
- **OVERTURNED** — agent provides additional evidence that refutes the challenge
- **QUALIFIED** — the claim holds with a noted caveat or limitation

The Comparative Reviewer then places the candidate in the context of the full applicant pool.

**Phase III — Chair Synthesis**

The Selection Reviewer (Chair) reads the complete transcript and delivers:
- **Recommendation:** ADVANCE, HOLD, or DECLINE
- **Tier:** A (best qualified), B (qualified), or C (minimally qualified)
- **Confidence score:** 0.0 to 1.0
- **Key agreements** across the council
- **Open questions** that require human resolution before a final decision

### Running the Council

From the case review workspace:

1. Open a candidate dossier.
2. Select **Run Expert Council** to start the council for that candidate, or use the case-level action to run the council for all candidates in a stage.
3. The board meeting runs in the background via Celery. Partial transcripts are visible in real time under **Evaluations → Board Meetings** as each agent completes their turn.
4. When all three phases complete, the full board meeting record is available: every agent turn, the full transcript, the chair recommendation, and meeting notes.

To stop a council mid-run, use **Evaluations → Stop Council**.

### Important: AI Cannot Advance Candidates

The council produces a recommendation, not a decision. All advancement, hold, and decline actions require human adjudication by the `SELECTING_OFFICIAL`. The council transcript and recommendation are evidence to inform that decision, not a substitute for it.

### Agent Configuration

Each expert agent is configured independently in **Admin → Settings → Expert Agents**:
- AI provider (Ollama, OpenAI, Anthropic, Gemini)
- Model name
- Temperature
- Maximum tokens

This allows mixed-model councils — for example, running the Skeptic and Chair agents at a higher capability model while using a faster model for opening statement specialists.

---

## Review Workflow

Candidates advance through five stages. Each stage is independently scored and must be adjudicated before candidates advance.

### Stage Chain

| Stage | Purpose |
| --- | --- |
| Resume Review | Initial rubric-aligned rating from resume evidence |
| Narrative Request | Structured written narrative evaluation |
| Screening Interview | Structured telephone or video screen |
| Panel Interview | Full panel interview with structured scoring |
| Final Selection | Final tier ranking and selectee identification |

### Scoring a Candidate

In each stage:

1. Open the candidate dossier from the stage view.
2. Review the AI-extracted evidence linked to each rubric dimension.
3. Assign a rating for each dimension with a rationale.
4. Submit the evaluation.

Reviewers see only their assigned candidates unless they hold the `CASE_OWNER` or `SELECTING_OFFICIAL` role.

### Adjudication

After all evaluations in a stage are complete:

1. The `SELECTING_OFFICIAL` reviews the stage results.
2. Dimension overrides can be applied with mandatory written rationale.
3. Candidates are marked for advancement or elimination.
4. The stage is locked and candidates advance.

Adjudication actions are immutably recorded in the audit log.

## Exports

From the decision workspace:

1. Select **Generate Export**.
2. The platform assembles a decision package for the case.
3. Download the export package.

The decision package is a ZIP archive containing a human-readable `summary.md`, the structured case record (`case.json`), per-candidate dossiers, board-meeting transcripts where present, and the case audit trail (`audit-trail.json`).

## Security Practices for Operators

- Keep `DEV_AUTH_BYPASS=false` in all non-local environments.
- Enforce TOTP MFA for all privileged accounts.
- Use OIDC SSO with upstream PIV/CAC enforcement where available.
- Limit the `SYSTEM_ADMINISTRATOR` role to the minimum number of users.
- Review the SOC audit log regularly.
- Back up PostgreSQL before and after major hiring actions.
- Protect `.env`, Docker host access, and storage credentials.
- Do not expose PostgreSQL, Redis, or OpenSearch ports to the network.

## Common Questions

### Can candidates see their evaluations?

No. The platform is an internal selection board tool. There is no candidate-facing portal.

### What happens if a rubric dimension is overridden?

Overrides require written rationale and are recorded in the adjudication history. They appear in the audit log and are included in the decision package export.

### Can a stage be reopened after it is locked?

No. Stage locks are permanent to preserve adjudication integrity. Contact a `SYSTEM_ADMINISTRATOR` if a data entry error occurred before the lock was applied.

### Can someone use this outside a federal agency?

Yes. The platform is designed for any organization that conducts structured hiring. Internal use — commercial, government, or non-profit — is permitted under the Business Source License without restriction. FISMA compliance features are optional; they do not need to be configured for non-federal deployments. See `LICENSE` and `COMMERCIAL.md`.
