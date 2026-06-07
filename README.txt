# AI PeopleOps HRMS

AI PeopleOps HRMS is a Flask, Socket.IO, and local MongoDB based Human Resource Management System built around AI-assisted recruitment, role-based HR operations, candidate pipelines, interview rooms, and employee lifecycle management.

This README has been updated for the current application version. It replaces older README sections that described the interview module as only "ready for WebSocket", the AI interview as only a future voice lab, and pagination as a future task. The current app now includes wired Socket.IO support, paginated high-volume pages, AI interview setup/candidate/result pages, transcript storage/display, and manual HR shortlist override after AI results.

---

## 1. Current Project Scope

The app manages two connected workflows:

1. **Internal HRMS workflow** for employees, attendance, payroll, performance, messages, notifications, profiles, themes, and user administration.
2. **Recruitment workflow** for public job listings, applications, AI resume screening, shortlisted candidate accounts, AI interview rooms, human interview rooms, candidate pipeline movement, and final employee creation.

Core capabilities in the current app:

- Role-based login and protected pages.
- Public careers page with searchable, paginated open jobs.
- Public application form with resume upload.
- AI resume screening with normalized text extraction.
- Recruitment workspace with job creation, job editing, controllers/viewers, progress chips, and paginated jobs.
- Applications review with AI reports, resume downloads, human review decisions, and interview assignment.
- Candidate pipeline for AI round, human round, rejection, and employee creation.
- Candidate account creation with temporary password when shortlisted.
- AI interview controller setup page.
- AI interview candidate page.
- AI interview report with full transcript display.
- Resume RAG uses the original deterministic evidence/question-generation logic on the extracted resume text. Controllers can upload a different resume on the AI room setup page, then rerun RAG and finalize again.
- Manual HR shortlist override even when AI rejects or asks for review.
- Human interview room with candidate/interviewer media controls.
- Socket.IO/live-room support for interview room events and signalling foundations.
- MongoDB-backed persistence with connection pooling and indexes.
- Paginated large-list pages where required.
- Responsive sidebar UI, theme kits, and mobile-friendly layouts.

---

## 2. Major README Gaps Fixed

The previous README was behind the app in these areas:

| Old README Gap | Current App Reality |
| --- | --- |
| Interview rooms were described as mostly "ready" for WebSocket. | `flask-socketio`, `socket_events.py`, live-room APIs, room events, participants, and signalling collections are present. |
| AI voice interview was described mostly as a future pipeline. | AI room configuration, RAG/question generation, candidate AI interview, text/audio answer endpoints, transcript endpoints, TTS endpoints, result endpoint, and controller decision endpoint are wired. |
| Transcript visibility was not documented. | AI result now returns and displays the linked transcript in the controller result view. |
| Manual override after AI rejection was not documented. | Controller can manually shortlist using `manual_shortlist`, moving the candidate forward despite AI rejection/manual-review output. |
| Pagination was listed as a future task. | Careers, Recruitment jobs, Applications, Candidate Pipeline, Employees, Interviews, Portal Users, and second-round/candidate lists use pagination where needed. |
| Candidate pipeline was under-documented. | The current app includes `candidate-pipeline`, move-to-AI, move-to-human, reject, and create-employee workflows. |
| Second-round page was still treated as a standalone page. | `/second-round-candidates` redirects to the unified Candidate Pipeline page. Deprecated templates/scripts are kept only for compatibility/reference. |
| Mongo collections were incomplete. | Current database layer includes AI interview config/transcript/result/model event collections, live room collections, HRMS attendance/payroll/performance collections, and UI settings collections. |
| Optimizations were generic. | The app now has concrete Mongo indexes, connection pooling, server-side pagination/search, and reduced client-side overfetching. |

---

## 3. Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, Flask |
| Realtime / live rooms | Flask-SocketIO, Eventlet |
| Database | Local MongoDB using `pymongo` |
| Frontend | HTML, CSS, JavaScript |
| Authentication | Flask session for page access + JWT token for API calls |
| Password hashing | Flask-Bcrypt |
| Resume extraction | PyPDF2, pdfplumber, python-docx, text-like parser fallbacks |
| AI recruitment scoring | Deterministic screening model with keyword, semantic-style, ATS, structure, and writing scores |
| AI interview support | RAG/question generation service, transcript storage, answer analysis, result generation, TTS hooks |
| Optional local AI packages | faster-whisper, sentence-transformers, gTTS, language-tool-python, accelerate |
| UI | Custom CSS, responsive sidebar, theme variables, page-specific JS |
| Deployment files | Procfile / Render files may exist in test or deployment notes; current local setup uses `python app.py` |

---

## 4. Folder Structure

app.py                         Main Flask app, frontend routes, blueprint registration
config.py                      Runtime config loaded from .env
config.example.py              Safe config template
database/db.py                 Mongo client, collections, connection pool, index setup
routes/                        API blueprints and interview page routes
services/                      HRMS, recruitment, AI interview, attendance, payroll, UI services
static/css/                    Global and page-specific styles
static/js/                     Page scripts and interview-room scripts
templates/                     Flask/Jinja pages
scripts/                       Setup, Mongo first-run, health-check, repair, and demo scripts
test/                          Patch notes, migration utilities, sample data, older helper scripts
_deprecated_second_third_round_ui/  Deprecated compatibility/reference files
README.md / README.txt         Updated project documentation
COMPLETED_PATCH_NOTES.md        Latest patch summary
AI_INTERVIEW_UI_AND_SCALING_NOTES.md Interview-room scaling notes


---

## 5. Main Pages

| Page | Route | Current Purpose |
| --- | --- | --- |
| Home | `/` | Landing/home page |
| Careers | `/careers` | Public searchable/paginated job listing |
| Apply | `/apply` | Public candidate application and resume upload |
| Login | `/login` | User login |
| Signup | `/signup` | First user becomes Super User; later users become Employee |
| Dashboard | `/dashboard` | Role-aware dashboard |
| Employees | `/employees` | Paginated/searchable employee management |
| Attendance | `/attendance` | Attendance, leave, meetings, corrections, rules |
| Payroll | `/payroll` | Payroll profiles, cycles, items, payouts, adjustments |
| Performance | `/performance` | Reviews, templates, goals, checklist verification |
| Recruitment | `/recruitment` | Job/JD creation, screening, job progress, shortlisted preview, paginated job cards |
| Applications | `/applications` | Paginated candidate applications and AI screening reports |
| Candidate Pipeline | `/candidate-pipeline` | Move candidates across AI, human, rejected, and employee stages |
| Second Round Candidates | `/second-round-candidates` | Compatibility redirect to `/candidate-pipeline` |
| Interviews | `/interviews` | Paginated interview room list and status overview |
| AI Room Controller | `/rooms/<room_code>/configure-ai` | Controller setup, RAG, AI result, transcript, decisions |
| AI Interview Candidate | `/rooms/<room_code>/ai-interview` | Candidate AI interview room |
| Human Interview Room | `/rooms/<room_code>/human-interview` | Personal/HR interview room with media controls |
| Compatibility Interview Link | `/interview-room/<room_code>` | Redirects users to the correct room page by role |
| Candidate Process | `/candidate-process` | Candidate-facing process/schedule page |
| AI Voice Lab | `/voice-interview` | Placeholder page showing Coming Soon while the standalone voice lab is rebuilt |
| Themes | `/themes` | User theme kits and UI preferences |
| Notifications | `/notifications` | User notification center |
| Messages | `/messages` | HRMS messaging |
| Profile | `/profile` | Profile and password management |
| User Management | `/portal/users` | Paginated/searchable user administration |
| Bulk Import | `/portal/import-users` | Bulk user import preview/commit workflow |

---

## 6. Authentication and Roles

The app uses both browser sessions and JWTs:

- Flask session protects rendered pages through `protected_page` in `app.py`.
- JWT access tokens are returned on login and used by frontend API calls.
- Logout clears the Flask session and blocklists the JWT when available.

Supported HRMS roles are defined in `services/hrms_service.py` and related access helpers. Important role groups include:

- Super User
- Management Admin
- HR Director
- HR Manager
- HR Business Partner
- HR Recruiter
- Talent Acquisition Specialist
- Technical Interviewer
- Panel Interviewer
- Payroll Manager
- Compensation and Benefits Specialist
- Learning and Development Manager
- Employee Relations Manager
- HR Operations Specialist
- Senior Manager
- Employee
- Candidate

Access behavior:

- Super User has full application access.
- HR/recruitment roles manage jobs, applications, reports, and interviews according to permissions.
- Interviewer roles access assigned interview rooms and relevant interview actions.
- Payroll roles access payroll workflows.
- Managers see team-scoped HRMS data where implemented.
- Candidates are limited to candidate-facing process and interview-room flows.
- Public outsiders only see careers and application pages until an account is created.

Important access files:

services/hrms_service.py
services/role_access.py
services/page_access.py
utils/decorators.py
app.py


---

## 7. Recruitment Workflow

### 7.1 Job and JD Management

Recruitment users can create and edit jobs with:

- Title
- Department
- Location
- Employment type
- Status
- Minimum AI score
- Posting close date/time
- Manual keywords
- Full job description
- Job viewers
- Job controllers

Jobs appear internally on `/recruitment` and publicly on `/careers` only when they are open and inside the posting window.

### 7.2 Public Job Listing

The Careers page now supports:

- Public open-role listing.
- Search by title, department, location, and description.
- Server-side pagination.
- Apply button linked to the public application form.

Endpoint:

GET /api/recruitment/public/jobs?page=1&limit=24&q=<search>


### 7.3 Public Application

Candidates can apply without internal access. The application flow stores candidate details, the uploaded resume, job reference, and screening data.

Endpoint:

POST /api/recruitment/public/apply


### 7.4 Resume Normalization

Every resume is converted to normalized text before screening where possible.

Supported inputs:

- `.pdf`
- `.doc`
- `.docx`
- `.txt`
- `.tex`
- `.rtf`
- `.md`

The app stores both:

- the original uploaded resume, and
- the converted TXT file in `static/uploads/resumes/converted_txt/`.

Scanned image-only PDFs need OCR before they can be scored reliably.

### 7.5 AI Resume Screening

The recruitment screening model performs:

- Resume/JD text extraction.
- Keyword extraction and alias matching.
- Semantic-style similarity scoring.
- Keyword coverage scoring.
- Writing/grammar-style quality scoring.
- Resume structure scoring.
- ATS parse checks.
- Category fit scoring.
- Weighted final score.
- Shortlist/reject/needs-review recommendation.
- Matched keyword and missing keyword reporting.
- Highlighted evidence snippets.
- Resume preview for authorized users.

Main files:

services/recruitment_screening_model.py
services/ai_recruitment_service.py
routes/recruitment_routes.py
static/js/recruitment.js
static/js/applications.js


### 7.6 Applications Review

The Applications page supports:

- Job filter.
- Review-status filter.
- Shortlisted-only filter.
- Paginated applications.
- Candidate application cards.
- AI report viewing.
- Human review decisions.
- Review notes.
- Original resume download.
- Converted TXT download.
- Interview room assignment.
- Delete report/application actions where authorized.

Important endpoints:

GET    /api/recruitment/applications?page=1&limit=24
GET    /api/recruitment/applications/<application_id>/report
GET    /api/recruitment/applications/<application_id>/resume
GET    /api/recruitment/applications/<application_id>/resume-text
PATCH  /api/recruitment/applications/<application_id>/review
DELETE /api/recruitment/applications/<application_id>/report
DELETE /api/recruitment/applications/<application_id>
POST   /api/recruitment/applications/<application_id>/assign-interview


### 7.7 Candidate Account Creation

When a candidate is shortlisted, the system can create or link a Candidate user account. New candidate accounts receive:

- Candidate UID.
- Candidate role.
- Temporary password.
- Linked application/job IDs.
- Candidate process access.

This allows selected applicants to log in and view their process/interview schedule without exposing internal HRMS pages.

---

## 8. Candidate Pipeline

The unified Candidate Pipeline replaces the older separate second-round candidate page.

Current candidate movement options:

- Move candidate to AI interview phase.
- Move candidate to human/personal interview phase.
- Reject candidate.
- Create permanent employee from selected candidate.

Main page:

/candidate-pipeline


Main endpoints:

GET  /api/candidate-pipeline?page=1&limit=24&phase=<phase>
GET  /api/candidate-pipeline/<application_id>
POST /api/candidate-pipeline/<application_id>/move-to-ai
POST /api/candidate-pipeline/<application_id>/move-to-human
POST /api/candidate-pipeline/<application_id>/reject
POST /api/candidate-pipeline/<application_id>/create-employee


Compatibility behavior:

/second-round-candidates -> /candidate-pipeline


Deprecated files are kept under `_deprecated_second_third_round_ui/` for reference only.

---

## 9. AI Interview Workflow

The current app includes a multi-step AI interview room workflow.

### 9.1 Controller Setup

Controllers can open:

/rooms/<room_code>/configure-ai


Controller setup supports:

- Viewing room configuration status.
- Preparing converted resume TXT from saved screening data.
- Uploading/replacing the resume used for AI RAG when the candidate needs to provide a different file.
- Removing prepared resume TXT reference.
- Uploading a tech-stack TXT file.
- Auto-generating config values.
- Running RAG question generation.
- Setting the room schedule to today.
- Finalizing/unlocking the room for the candidate.
- Previewing generated questions.
- Viewing model loading/status information.

Main endpoints:

GET    /api/ai-interview/models/status
POST   /api/ai-interview/models/unload
GET    /api/ai-interview/rooms/<room_code>/config
POST   /api/ai-interview/rooms/<room_code>/config/prepare-resume
POST   /api/ai-interview/rooms/<room_code>/config/upload-resume
DELETE /api/ai-interview/rooms/<room_code>/config/resume-txt
POST   /api/ai-interview/rooms/<room_code>/config/upload-tech-stack
POST   /api/ai-interview/rooms/<room_code>/config/auto
POST   /api/ai-interview/rooms/<room_code>/config/run-rag
POST   /api/ai-interview/rooms/<room_code>/config/set-today
POST   /api/ai-interview/rooms/<room_code>/config/finalize


### 9.2 Candidate AI Interview

Candidates open:

/rooms/<room_code>/ai-interview


Candidate interview supports:

- Entry check before starting.
- Start interview.
- Receive AI questions.
- Submit text answers.
- Submit audio answers through the available audio endpoint.
- Store answer analysis.
- Save room recordings metadata.
- Generate question TTS / generic TTS.
- Finish interview and generate final result.
- Candidate transcript view.

Main endpoints:

GET    /api/ai-interview/rooms/<room_code>/entry-check
GET    /api/ai-interview/rooms/<room_code>/phase-state
GET    /api/ai-interview/rooms/<room_code>/candidate-transcript
POST   /api/ai-interview/rooms/<room_code>/start
POST   /api/ai-interview/rooms/<room_code>/answer-text
POST   /api/ai-interview/rooms/<room_code>/answer-audio
POST   /api/ai-interview/rooms/<room_code>/recordings
GET    /api/ai-interview/rooms/<room_code>/recordings
DELETE /api/ai-interview/rooms/<room_code>/recordings/<recording_id>
POST   /api/ai-interview/rooms/<room_code>/question-tts
POST   /api/ai-interview/rooms/<room_code>/tts
POST   /api/ai-interview/rooms/<room_code>/finish


### 9.3 AI Interview Report and Transcript

After the candidate finishes, the controller result area shows:

- Final AI score.
- Recommendation.
- Category averages.
- RAG coverage.
- Latest answer analysis.
- Full chat-style interview transcript.
- Controller decision buttons.

Result endpoint:

GET /api/ai-interview/rooms/<room_code>/result


Transcript endpoints:

GET /api/ai-interview/rooms/<room_code>/transcript
GET /api/ai-interview/rooms/<room_code>/live-transcript


### 9.4 Manual Shortlist Override

Controllers can manually shortlist a candidate even if the AI rejects the candidate or marks the candidate for manual review.

Decision endpoint:

POST /api/ai-interview/rooms/<room_code>/decision


Supported decision values include:

manual_shortlist
shortlist
move_to_personal
move_to_hr
reject


`manual_shortlist` records an override on the application/result for audit visibility and advances the candidate to the personal interview phase in the same room.

---

## 10. Human Interview Rooms and Media

Human interview rooms are available at:

/rooms/<room_code>/human-interview


Current behavior:

- Candidate and interviewer each see their own camera/microphone controls.
- Controller-only views do not show candidate AI preview controls.
- AI interview candidate page shows candidate-only camera/microphone preview.
- Personal/HR interview media controls are restored through the interview scripts and CSS.
- Human interview results can be submitted by authorized users.

Main endpoint:

POST /api/human-interview/rooms/<room_code>/submit-result


---

## 11. Live Rooms and Socket.IO

The app initializes Socket.IO through:

socket_events.py


Live-room support files/endpoints:

GET /api/live/rooms/<room_code>/events
GET /api/live/rooms/<room_code>/participants


Relevant collections:

live_room_events
live_room_participants
webrtc_signals


The current live layer supports room activity/event foundations. For heavier production realtime usage, add Redis as the Socket.IO message queue and run multiple workers behind a reverse proxy.

---

## 12. Internal HRMS Modules

### 12.1 Dashboard

Dashboard data is role-aware and uses HRMS/recruitment summaries.

Routes:

GET /api/hrms/dashboard
GET /api/hrms/dashboard/summary


### 12.2 Employee Management

Features:

- Paginated/searchable employee list.
- Create/update employee records.
- Department/designation/status fields.
- Manager assignment support.
- Salary/profile foundations.
- Employee documents foundation.

Endpoints:

GET   /api/hrms/employees?page=1&limit=20&q=<search>
POST  /api/hrms/employees
PATCH /api/hrms/employees/<employee_id>


### 12.3 Attendance, Leave, Meetings, and Corrections

Features:

- Check-in/check-out.
- Manual attendance.
- Personal/team attendance views.
- Attendance calendar.
- Pending reviews.
- Rules.
- Leave request/approval/rejection.
- Attendance meetings.
- Corrections.

Important endpoints include:

GET  /api/hrms/attendance
POST /api/hrms/attendance/check-in
POST /api/hrms/attendance/check-out
POST /api/hrms/leave/request
GET  /api/hrms/leave/my
GET  /api/hrms/leave/team
POST /api/hrms/attendance/meeting
POST /api/hrms/attendance/correction


### 12.4 Payroll

Features:

- Payroll records.
- Payroll profiles.
- Payroll cycle generation.
- Payroll item confirmation.
- Payment marking.
- Custom pay.
- Adjustments.

Important endpoints include:

GET   /api/hrms/payroll
POST  /api/hrms/payroll
POST  /api/hrms/payroll/profile
POST  /api/hrms/payroll/profiles/generate
POST  /api/hrms/payroll/generate
PATCH /api/hrms/payroll/items/<item_id>
POST  /api/hrms/payroll/items/<item_id>/confirm
POST  /api/hrms/payroll/items/<item_id>/pay


### 12.5 Performance

Features:

- Performance reviews.
- Review templates.
- Goals.
- Goal checklist completion and verification.

Important endpoints include:

GET  /api/hrms/performance
POST /api/hrms/performance
POST /api/hrms/performance/templates
POST /api/hrms/performance/goals
POST /api/hrms/performance/goals/<goal_id>/checklist/<item_id>/check
POST /api/hrms/performance/goals/<goal_id>/checklist/<item_id>/verify


### 12.6 Messaging

Features:

- Conversation list.
- Read messages with an employee.
- Send message to an employee.

Endpoints:

GET  /api/hrms/messages/conversations
GET  /api/hrms/messages/<employee_id>
POST /api/hrms/messages/<employee_id>


---

## 13. User Management and Bulk Import

Admin-level user management supports:

- Paginated user listing.
- User search.
- User creation.
- User updates.
- User deletion/deactivation behavior.
- Bulk import preview.
- Bulk import commit.
- Conflict handling and validation.

Endpoints:

GET    /api/portal/roles
GET    /api/portal/users?page=1&limit=20&q=<search>
POST   /api/portal/users
PATCH  /api/portal/users/<user_id>
DELETE /api/portal/users/<user_id>
POST   /api/portal/import/preview
POST   /api/portal/import/commit
GET    /api/portal/summary


Bulk import role handling:

- Runtime role normalization is controlled by `services/hrms_service.py`.
- Bulk import should use the current HRMS role names instead of older organization/team-only role names.
- Bulk import cannot create Super User accounts; create the first Super User through signup or the setup script.

---

## 14. Theme Kits and UI Settings

The app includes user-specific UI customization:

- Preset theme kits.
- Custom user theme values.
- Accent/background/spacing variables.
- Sidebar behavior.
- Mobile responsive handling.
- Page-group/UI-setting collections.

Endpoints:

GET /api/theme/kits
GET /api/theme/me
PUT /api/theme/me


Important files:

templates/base.html
static/css/style.css
static/js/app.js
services/ui_service.py


---

## 15. Pagination and Optimization Status

Pagination exists on these high-volume pages:

| Area | Frontend File | Backend Endpoint |
| --- | --- | --- |
| Public Careers jobs | `static/js/careers.js` | `GET /api/recruitment/public/jobs` |
| Internal Recruitment jobs | `static/js/recruitment.js` | `GET /api/recruitment/jobs` |
| Applications | `static/js/applications.js` | `GET /api/recruitment/applications` |
| Candidate Pipeline | `static/js/candidate_pipeline.js` | `GET /api/candidate-pipeline` |
| Second-round/candidate list API | `static/js/candidate_pipeline.js` | `GET /api/recruitment/second-round-candidates` |
| Interview rooms | `static/js/interviews.js` | `GET /api/recruitment/interviews` |
| Employees | `static/js/employees.js` | `GET /api/hrms/employees` |
| Portal Users | `static/js/portal_users.js` | `GET /api/portal/users` |

Current optimizations:

- MongoDB connection pooling.
- Safe index creation with conflict tolerance.
- Compound indexes for jobs, applications, interview sessions, transcripts, AI results, live rooms, users, employees, notifications, activity logs, and login sessions.
- Server-side pagination and search for large lists.
- Public careers page no longer loads all jobs at once.
- Recruitment shortlisted preview fetches only the first 8 records.
- Recruitment job select no longer triggers unnecessary full reloads.
- Responsive UI reduces expensive visual behavior on smaller/lower-power devices.

Recommended next optimizations:

- Add Redis for Socket.IO multi-worker scaling.
- Add Celery/RQ for heavy resume screening and AI interview jobs.
- Move model inference to a dedicated worker or service.
- Add object storage for production resume/document uploads.
- Add audit logs for every interview decision/manual override.
- Add OCR for scanned resumes.
- Add database-level TTL/retention rules for transient live-room events and model logs.

---

## 16. MongoDB Collections

Current database layer declares these collections:

users
employees
employee_documents
attendance
hrms_attendance_rules
hrms_attendance_corrections
hrms_attendance_meetings
hrms_attendance_reviews
hrms_leave_requests
hrms_manager_assignments
leave_requests
hrms_payroll_profiles
hrms_payroll_cycles
hrms_payroll_items
hrms_payroll_adjustments
hrms_payouts
hrms_payroll_queries
payroll
performance_reviews
hrms_performance_cycles
hrms_performance_milestones
hrms_performance_feedback
hrms_performance_templates
hrms_performance_goals
hrms_performance_checklists
hrms_performance_scores
jobs
job_knowledge_base
applications
resume_screening_results
recruitment_candidates
interview_sessions
interview_messages
interview_rooms
candidate_processes
ai_interview_configs
ai_interview_transcripts
ai_interview_results
ai_interview_model_events
live_room_events
live_room_participants
webrtc_signals
hrms_messages
notifications
activity_logs
login_sessions
hrms_audit_logs
hr_cases
learning_records
user_themes
hrms_ui_settings
hrms_ui_page_groups


---

## 17. First-Time Setup

### 17.1 Requirements

Install:

- Python 3.10+
- Local MongoDB Community Server
- A Windows/Linux/macOS shell

The runtime database is local MongoDB. JSON mirror files are not used as the source of truth anymore.

### 17.2 Create Virtual Environment

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

### 17.3 One-Time Local MongoDB Setup Script

A first-run setup script is included in the `scripts/` folder. It creates local Mongo data/log folders, starts a local MongoDB server on `127.0.0.1:27017` when one is not already running, writes local Mongo values into `.env`, pings the server, and applies the app indexes.

Windows PowerShell, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_local_mongo_windows.ps1
```

macOS/Linux, from the project root:

```bash
bash scripts/setup_local_mongo_linux_mac.sh
```

The scripts use these defaults:

```env
MONGO_URI=mongodb://127.0.0.1:27017
DB_NAME=ai_hrms_local
```

The setup script is safe to run again. It will reuse the running MongoDB server if one is already active.

### 17.4 Manual Environment Setup

If you do not want to use the setup script, create `.env` from `.env.example` manually.

Windows:

```powershell
copy .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Then confirm these values exist:

```env
MONGO_URI=mongodb://127.0.0.1:27017
DB_NAME=ai_hrms_local
SECRET_KEY=change-this-local-secret
JWT_SECRET_KEY=change-this-local-jwt-secret
FLASK_ENV=development
MONGO_MAX_POOL_SIZE=200
MONGO_MIN_POOL_SIZE=5
```

Do not commit real `.env` files.

### 17.5 Check MongoDB Connection

Run this whenever you want to verify the local server and indexes:

```bash
python scripts/check_local_mongo.py
```

Expected output includes:

```text
MongoDB connection OK
Local MongoDB setup check completed successfully.
```

### 17.6 Run the App

Start MongoDB first. If you used the setup script, MongoDB should already be running. Then run:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

The first signup becomes the Super User. You can also create one manually:

```bash
python scripts/create_super_user.py
```

### 17.7 Other Optional Scripts

```bash
python scripts/demo_recruitment_screening.py
python scripts/repair_org_relations.py
python scripts/repair_team_relations.py
```

Use repair/migration scripts only after checking their source and matching them to your current database.

---

## 18. Important Files

| File | Purpose |
| --- | --- |
| `app.py` | Flask app, protected pages, frontend routes, blueprint registration |
| `socket_events.py` | Socket.IO setup and realtime event hooks |
| `database/db.py` | Mongo connection, collection exports, index creation |
| `routes/auth_routes.py` | Signup, login, logout, current user |
| `routes/hrms_routes.py` | Employees, attendance, leave, payroll, performance, messages |
| `routes/recruitment_routes.py` | Jobs, applications, resume screening, candidate accounts, interview assignment, room details/messages |
| `routes/ai_interview_routes.py` | AI room config, candidate interview, transcript, result, decisions |
| `routes/human_interview_routes.py` | Human room state and result submission |
| `routes/candidate_pipeline_routes.py` | Candidate pipeline movement and employee creation |
| `routes/interview_pages_v2_routes.py` | Controller/candidate/human interview page routes |
| `services/recruitment_screening_model.py` | Resume/JD scoring model |
| `services/ai_recruitment_service.py` | Resume extraction, conversion, screening wrapper, answer evaluation |
| `services/ai_interview_service.py` | AI interview workflow, transcript/result logic, model lifecycle helpers |
| `services/ai_interview_rag.py` | Original deterministic RAG/question-generation support using resume and tech-stack evidence extraction |
| `services/candidate_pipeline_service.py` | Candidate phase and employee conversion helpers |
| `services/page_access.py` | Page permission mapping |
| `services/role_access.py` | Role and module visibility helpers |
| `scripts/setup_local_mongo_windows.ps1` | One-time Windows local MongoDB setup and startup script |
| `scripts/setup_local_mongo_linux_mac.sh` | One-time Linux/macOS local MongoDB setup and startup script |
| `scripts/check_local_mongo.py` | MongoDB ping, collection, and index health check |
| `static/js/recruitment.js` | Recruitment workspace UI, paginated jobs, shortlisted preview |
| `static/js/careers.js` | Public careers search and pagination |
| `static/js/applications.js` | Applications list and reports |
| `static/js/candidate_pipeline.js` | Candidate pipeline UI |
| `static/js/interviews/ai_room_config.js` | AI controller setup/result/transcript/manual shortlist UI |
| `static/js/interviews/ai_interview_candidate.js` | Candidate AI interview flow |
| `static/js/interviews/human_interview_room.js` | Human interview media/result UI |
| `static/css/style.css` | Main UI styling, sidebar, responsive behavior |
| `static/css/interview_pages_v2.css` | AI/human interview room styling |

---

## 19. API Route Groups

| Area | Prefix |
| --- | --- |
| Authentication | `/api/auth` |
| Core HRMS | `/api/hrms` |
| Recruitment | `/api/recruitment` |
| AI Interview | `/api/ai-interview` |
| Human Interview | `/api/human-interview` |
| Candidate Pipeline | `/api/candidate-pipeline` |
| Live Rooms | `/api/live` |
| Portal/User Admin | `/api/portal` |
| Profile/User | `/api/users` |
| Themes | `/api/theme` |
| Notifications | `/api/notifications` |
| Activity | `/api/activity` |

---

## 20. Current Known Limitations

- Local MongoDB is required; runtime JSON mirroring is no longer used.
- Scanned resume PDFs need OCR before screening.
- Heavy local AI models should not be run concurrently without a queue/worker setup.
- Socket.IO is wired, but production multi-worker Socket.IO needs Redis or another message queue.
- Some files under `test/` are patch/migration utilities, not automated test cases.
- `_deprecated_second_third_round_ui/` is retained for reference and should not be treated as active UI.

---

## 21. Suggested Next Development Steps

1. Add complete audit logging for manual shortlist/reject/move decisions.
2. Add OCR for scanned resumes.
3. Queue heavy resume screening and AI interview jobs with Celery/RQ + Redis.
4. Add Redis message queue for Socket.IO scaling.
5. Add stronger candidate identity and room-entry validation.
6. Add WebRTC signalling completion for real peer-to-peer interview media.
7. Add analytics charts for recruitment funnel, attendance, payroll, and performance.
8. Add object storage for uploaded resumes and employee documents.
9. Add admin controls for transcript retention and deletion.
10. Add production deployment documentation for Gunicorn/Eventlet/Nginx.
