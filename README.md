# AI PeopleOps HRMS

AI PeopleOps HRMS is a Flask + MongoDB Atlas based Human Resource Management System rebuilt for the theme **“Build the Future of HR Management with AI-Powered Solutions.”**

The project combines core HRMS operations, role-based dashboards, AI recruitment, public candidate applications, interview rooms, AI voice-interview evaluation, user-specific theme kits, responsive UI, and MongoDB-backed persistence.

---

## 1. Project Objective

The goal of the system is to provide a next-generation HRMS that can manage internal employees and external recruitment workflows in one platform.

The system supports:

- Employee data management
- Attendance tracking
- Payroll management
- Performance tracking
- AI resume screening
- AI chat/voice recruitment preparation
- Interview rooms
- Role-based dashboards
- Admin-level company-wide views
- User-specific theme kits
- Responsive web/mobile UI
- MongoDB Atlas database storage

---

## 2. Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, Flask |
| Database | MongoDB Atlas using `pymongo` |
| Frontend | HTML, CSS, JavaScript |
| Authentication | JWT-style token stored client-side |
| Styling | Custom responsive CSS, theme variables |
| AI Recruitment | Lightweight deterministic vector-style scoring, keyword matching, grammar scoring |
| Resume Parsing | PDF/DOC/DOCX/TXT normalized to TXT before screening |
| Real-time-ready Layer | Interview rooms and message structure ready for SocketIO/WebSocket extension |
| Deployment Ready | Procfile, Render config, environment variables |

---

## 3. Main Functional Modules

## 3.1 Authentication and Access Control

The system supports secure login and protected pages.

Features:

- Login
- Signup
- Logout
- Token-based protected routes
- Role-aware UI visibility
- First user becomes Super User
- Later signups default to Employee
- Admins can update roles from the user management area

Main routes:

| Feature | Route |
| --- | --- |
| Login page | `/login` |
| Signup page | `/signup` |
| Auth API | `/api/auth` |

---

## 3.2 Role System

The project includes a broad HRMS role model so different users get different access.

Supported roles:

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
- Outsider/Candidate through public pages only

### Role Rules

| Role Group | Access Level |
| --- | --- |
| Super User | Full system access, all users, all modules, bulk import |
| Management Admin | Company-wide dashboards, employees, performance, recruitment, payroll overview |
| HR Leadership | Employee data, HR operations, recruitment, performance, attendance visibility |
| HR Recruiter / Talent Acquisition | Job posts, applications, resume screening, candidate reports, interview assignment |
| Interviewer Roles | Interview rooms, candidate evaluation, voice-interview lab |
| Payroll Roles | Payroll records, salary components, compensation data |
| Senior Manager | Team-level performance, attendance, interview participation, assigned employees |
| Employee | Personal dashboard, attendance, performance, profile, notifications, themes |
| Candidate/Outsider | Careers, application form, resume upload, shared interview room only |

Permission logic is mainly handled in:

```text
services/hrms_service.py
utils/decorators.py
```

---

## 3.3 Personalized Dashboards

Each logged-in user gets dashboard content based on their role and access level.

Employee dashboard includes:

- Personal profile summary
- Attendance status
- Performance indicators
- Notifications
- Personal activity
- Theme access

HR dashboard includes:

- Recruitment pipeline
- Candidate applications
- AI screening summaries
- Employee operations
- Interview room links

Admin dashboard includes:

- Company-wide employee summary
- Department activity
- Attendance overview
- Recruitment analytics
- User management access
- System activity overview

Main route:

```text
/dashboard
```

---

## 3.4 Employee Management

This module stores and manages employee data.

Features:

- Add employee records
- Update employee information
- Department and designation management
- Employment status
- Manager assignment
- Contact and profile information
- Salary-related fields
- Work history foundation

Main routes:

| Feature | Route |
| --- | --- |
| Employee page | `/employees` |
| HRMS API | `/api/hrms` |

MongoDB collection:

```text
employees
```

---

## 3.5 Attendance Management

Attendance is part of the core HRMS requirement.

Features:

- Employee check-in/check-out structure
- Attendance logs
- Working hours support
- Late/absence tracking foundation
- Employee-level attendance view
- Manager/admin scoped visibility

Main route:

```text
/attendance
```

MongoDB collection:

```text
attendance
```

---

## 3.6 Payroll Management

Payroll supports salary and compensation workflows.

Features:

- Salary component storage
- Payroll records
- Payroll status
- Allowance/deduction fields
- Attendance-linked payroll foundation
- Payslip reference support
- Payroll-role based access

Main route:

```text
/payroll
```

MongoDB collection:

```text
payroll
```

---

## 3.7 Performance Tracking

Performance tracking supports employee growth and review management.

Features:

- KPI reviews
- Manager feedback
- Ratings
- Goal tracking foundation
- Promotion recommendation foundation
- Employee performance history

Main route:

```text
/performance
```

MongoDB collection:

```text
performance_reviews
```

---

## 3.8 Public Candidate / Outsider Portal

The candidate side is separated from the internal HRMS UI. Outsiders cannot access internal dashboards.

Candidate-visible areas:

- Careers page
- Job list
- Application form
- Resume upload
- Basic applicant details
- Shared interview room link when invited

Candidate-hidden areas:

- Employee database
- Payroll
- Attendance
- Admin dashboards
- Internal recruitment reports
- User management
- HR operations

Main public routes:

| Feature | Route |
| --- | --- |
| Careers page | `/careers` |
| Apply page | `/apply` |
| Shared interview room | `/interview-room/<room_code>` |

---

## 3.9 AI Resume Screening

The recruitment module includes AI-style automated screening.

Features:

- Job description creation
- JD keyword extraction
- Resume upload
- Resume text extraction
- Resume/JD vector-style comparison
- Cosine-style similarity score
- Keyword coverage score
- Grammar/writing quality score
- Final weighted score
- Minimum score filtering
- Shortlist/reject recommendation
- Matched keyword highlights
- Missing keyword reporting
- AI screening report per applicant

Main routes:

| Feature | Route |
| --- | --- |
| Recruitment workspace | `/recruitment` |
| Applications and AI reports | `/applications` |
| Recruitment API | `/api/recruitment` |

Main service:

```text
services/ai_recruitment_service.py
```

MongoDB collections:

```text
jobs
applications
resume_screening_results
job_knowledge_base
```

### Screening Logic

The current implementation is lightweight and works without paid AI APIs. It can later be upgraded to:

- Sentence Transformers
- FAISS
- LangChain/RAG
- Fine-tuned local models
- Hugging Face embedding models

---

## 3.10 AI Voice Interview Evaluation

The voice interview module is prepared as a hybrid evaluation layer.

Current functionality:

- Transcript-based answer evaluation
- Expected answer comparison
- Keyword coverage scoring
- Semantic similarity-style scoring
- Clarity score
- Final answer score
- AI feedback structure

Main route:

```text
/voice-interview
```

Recommended future full voice pipeline:

```text
Browser microphone
    -> MediaRecorder audio chunks
    -> Flask/WebSocket endpoint
    -> Whisper or faster-distil-whisper STT
    -> Chat/interview model
    -> RAG over job documents
    -> Similarity scoring
    -> Piper TTS response
    -> Browser audio playback
```

Suggested models/tools:

- STT: Whisper tiny/base, faster-distil-whisper
- TTS: Piper
- Chat: lightweight Hugging Face instruct/chat model
- Similarity: Sentence Transformers
- Knowledge retrieval: job knowledge base + embeddings

---

## 3.11 Interview Rooms

Interview rooms allow a logged-in HR/interviewer user to connect with another person, including candidates.

Features:

- Create interview rooms
- Assign candidate/application
- Generate shareable room codes
- Candidate can access only the shared room
- Internal users can access assigned rooms
- Message structure prepared for chat/transcripts/interview notes
- Ready for WebSocket/SocketIO upgrade

Main routes:

| Feature | Route |
| --- | --- |
| Interview rooms list | `/interviews` |
| Shared room | `/interview-room/<room_code>` |

MongoDB collections:

```text
interview_rooms
interview_sessions
interview_messages
```

---

## 3.12 User-Specific Theme Kits

Each user can customize their UI theme.

Features:

- Theme kits page
- Preset kits
- User-specific permanent theme storage
- MongoDB-backed theme values
- Custom colors
- Radius control
- Dashboard density control
- Background/video intensity handling

Theme kits included:

- Neo Mint
- Executive Dark
- Recruiter Pulse
- Payroll Focus
- Cloud Light
- Midnight Compact

Main route:

```text
/themes
```

Theme API:

```text
/api/theme
```

MongoDB collection:

```text
user_themes
```

---

## 3.13 Sidebar Navigation Behavior

The top navigation was replaced with a dynamic collapsible sidebar.

Current sidebar rules:

- Desktop sidebar is collapsed by default.
- Toggle OFF means collapsed mode.
- In collapsed mode:
  - options are blurred/faded
  - the vertical app name stays visible in the center
  - hover temporarily expands the sidebar
- Toggle ON means fixed open mode.
- In fixed open mode:
  - sidebar stays open
  - hover does not trigger any collapse behavior
  - blur/fade/collapsed state is disabled
- Toggle state is stored locally in the browser so page changes do not confuse the sidebar state.
- Mobile uses a slide-out drawer instead of hover behavior.

Related files:

```text
templates/base.html
static/css/style.css
static/js/app.js
```

---

## 3.14 Responsive UI

The UI has been optimized for different screen sizes.

Supported layouts:

- Small phones
- Large phones
- Tablets
- Laptops
- Desktop monitors
- Large screens

Responsive behavior includes:

- Mobile slide-out sidebar
- Touch-safe navigation
- Adaptive cards and dashboard grids
- Stacked mobile tables
- Responsive forms
- Tap-friendly buttons
- Auto-sizing panels
- Reduced heavy visual effects on mobile/low-power devices
- Disabled hover-only behavior on touch devices

---

## 3.15 Notifications

Notifications are available for authenticated users.

Use cases:

- Leave updates
- Payroll updates
- Interview updates
- Recruitment actions
- System activity messages

Main route:

```text
/notifications
```

MongoDB collection:

```text
notifications
```

---

## 3.16 Profile Management

Each logged-in user can access their profile.

Features:

- View account information
- Role display
- Personal details foundation
- Theme personalization link

Main route:

```text
/profile
```

---

## 3.17 User Management and Bulk Import

Admin-level users can manage internal users.

Features:

- View users
- Create/update users
- Assign roles
- Bulk import users
- Conflict handling foundation
- Super User-only high-level controls

Main routes:

| Feature | Route |
| --- | --- |
| User management | `/portal/users` |
| Bulk import | `/portal/import-users` |

---

## 3.18 Performance and Scalability Optimizations

The project is designed for future high user count, including 5,000+ users.

Current optimizations:

- MongoDB connection pooling
- Collection indexes
- Reduced heavy CSS effects
- Reduced animations on mobile/low-power devices
- Background video disabled under low-performance conditions
- Responsive table conversion
- Layout containment and lower-cost rendering
- Role-aware UI rendering to reduce visible DOM clutter

Recommended future production additions:

- Gunicorn workers
- Nginx reverse proxy
- Redis caching
- Celery workers for AI/resume processing
- Queue background jobs for reports
- Pagination for large collections
- Server-side search/filtering
- WebSocket scaling using Redis message queue
- Object storage for uploaded resumes/documents

---

## 4. Main Pages

| Page | Route |
| --- | --- |
| Home | `/` |
| Careers / outsider jobs | `/careers` |
| Public application | `/apply` |
| Login | `/login` |
| Signup | `/signup` |
| Dashboard | `/dashboard` |
| Employees | `/employees` |
| Attendance | `/attendance` |
| Payroll | `/payroll` |
| Performance | `/performance` |
| Recruitment workspace | `/recruitment` |
| Applications and AI reports | `/applications` |
| AI voice interview lab | `/voice-interview` |
| Interview rooms list | `/interviews` |
| Shared interview room | `/interview-room/<room_code>` |
| Theme kits | `/themes` |
| Notifications | `/notifications` |
| Profile | `/profile` |
| User management | `/portal/users` |
| Bulk user import | `/portal/import-users` |

---

## 5. API Route Groups

| Area | Prefix |
| --- | --- |
| Authentication | `/api/auth` |
| HRMS data | `/api/hrms` |
| Recruitment + AI | `/api/recruitment` |
| User theme | `/api/theme` |
| HRMS user administration | `/api/portal` |
| Profile | `/api/users` |
| Notifications | `/api/notifications` |
| Activity logs | `/api/activity` |

---

## 6. MongoDB Collections

The system uses these collections:

```text
users
employees
attendance
payroll
performance_reviews
leave_requests
jobs
job_knowledge_base
applications
resume_screening_results
interview_sessions
interview_rooms
interview_messages
user_themes
employee_documents
hr_cases
learning_records
notifications
activity_logs
login_sessions
```

---

## 7. Local Setup

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
```

Install requirements:

```powershell
pip install -r requirements.txt
```

Create environment file:

```powershell
copy .env.example .env
```

Run the project:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

## 8. Environment Variables

Create `.env` from `.env.example`.

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/hrms_db?retryWrites=true&w=majority
DB_NAME=hrms_db
SECRET_KEY=change-this-secret
JWT_SECRET_KEY=change-this-jwt-secret
FLASK_ENV=development
UPLOAD_FOLDER=static/uploads
```

Do not commit `.env`.

`.env` is intentionally excluded from the clean zip.

---

## 9. Important Files

| File | Purpose |
| --- | --- |
| `app.py` | Main Flask app entry point |
| `config.example.py` | Safe template for local `config.py`; copy it to `config.py` before running |
| `database/db.py` | MongoDB Atlas connection |
| `routes/auth_routes.py` | Login/signup/authentication APIs |
| `routes/hrms_routes.py` | Employee, attendance, payroll, performance APIs |
| `routes/recruitment_routes.py` | Jobs, applications, AI screening, interviews |
| `routes/theme_routes.py` | User-specific theme storage |
| `routes/portal_routes.py` | User management and admin routes |
| `services/ai_recruitment_service.py` | Resume screening and scoring logic |
| `services/hrms_service.py` | Role/permission helpers and HRMS logic |
| `templates/base.html` | Shared sidebar layout |
| `static/css/style.css` | Global UI, responsive layout, theme kits, sidebar behavior |
| `static/js/app.js` | Shell behavior, auth checks, themes, sidebar state |

---

## 10. Development Notes

- Use the latest zip as the main project version.
- The previous zips are only backups.
- The project currently includes lightweight AI-style scoring so it works without paid APIs.
- For a production-grade AI version, replace or extend the current scorer with embeddings and actual model inference.
- For real-time interviews, integrate Flask-SocketIO and use Redis for multi-worker scaling.
- For 5,000+ users, keep dashboard pages paginated and avoid loading entire collections into the frontend.

---

## 11. Suggested Next Development Steps

1. Add real Sentence Transformer embeddings for resume/JD matching.
2. Add FAISS or MongoDB vector search for job knowledge retrieval.
3. Add Whisper/faster-distil-whisper for speech-to-text.
4. Add Piper for text-to-speech interviewer voice.
5. Add Flask-SocketIO for live interview rooms.
6. Add Celery + Redis for background resume screening.
7. Add pagination and server-side filtering for users/applications/employees.
8. Add file storage support for resumes and employee documents.
9. Add admin analytics charts for attendance, recruitment, and payroll.
10. Add audit logs for sensitive HR actions.

---

## Recruitment Screening Model Layer

A standalone recruitment screening model has been added under:

```text
services/recruitment_screening_model.py
```

It follows the planned recruitment AI approach:

- job description keyword extraction
- resume normalization from PDF/DOC/DOCX/TXT/TEX/RTF/MD into TXT before screening
- vector embedding generation
- cosine similarity scoring
- keyword match scoring
- writing style and grammar-like scoring
- resume structure scoring
- weighted final score calculation
- minimum score based shortlist/reject decision
- matched keyword highlights for AI reports

A wrapper remains in:

```text
services/ai_recruitment_service.py
```

so the existing Flask routes continue to work while the model can be upgraded independently.

Run the standalone demo:

```bash
python scripts/demo_recruitment_screening.py
```

More details are documented in:

```text
RECRUITMENT_SCREENING_MODEL.md
```

## Latest Update: Recruitment Screening Model Wired to UI

The recruitment screening model is now connected to the Flask application and UI.

### Job and JD Creation

Recruitment users can open **Recruitment AI** from the sidebar and create a job profile with:

- job title
- department
- location
- employment type
- minimum AI score threshold
- optional manual keywords
- full job description/JD

When a job is created, the system extracts JD keywords automatically unless manual keywords are supplied. These keywords become the reference terms for resume matching, highlighted report evidence, and missing-skill analysis.

### Single Resume Screening

The Recruitment page includes a **Single Resume Screening** form. HR can select a job, upload one resume, and enter candidate details. The system then:

1. converts the uploaded resume into a normalized TXT file first, then screens that TXT against the selected JD,
2. compares the resume against the selected job JD,
3. calculates semantic similarity,
4. calculates keyword match score,
5. estimates writing/grammar quality,
6. checks resume structure,
7. generates a final weighted score,
8. creates an application record,
9. stores an explainable AI report.

### Bulk Resume Screening

The Recruitment page also includes a **Bulk Resume Screening** form. HR can upload multiple resumes at once for the selected job. Each file becomes a separate application and receives its own AI screening report. Candidate names are initially generated from filenames and can be reviewed later.

### Job-Wise Distinction

All applications and screening reports are linked to a specific job. The Applications page now supports:

- filter by job,
- filter by review status,
- show shortlisted only,
- job-wise candidate comparison,
- job-wise AI reports.

### AI Report Highlights

Each report includes:

- final score,
- semantic score,
- keyword score,
- writing score,
- structure score,
- recommendation,
- confidence label,
- matched keywords,
- missing keywords,
- highlighted resume snippets using `<mark>` tags.

This makes the screening output explainable instead of just showing a score.

### Human Review Workflow

Relevant recruitment users can review AI-screened candidates and update the review state:

- Pending Review
- Needs Review
- Shortlisted
- Interview Scheduled
- Selected
- Rejected
- On Hold

Review notes can be saved with the application. This keeps the AI decision separate from the final HR review.

### Interview Connection

From the Applications page, authorized recruitment users can create interview rooms for candidates. This connects the resume screening workflow to the existing interview-room and AI voice interview modules.

### New API Endpoints

```text
GET    /api/recruitment/jobs
GET    /api/recruitment/jobs/<job_id>
POST   /api/recruitment/jobs
PATCH  /api/recruitment/jobs/<job_id>
POST   /api/recruitment/screen/single
POST   /api/recruitment/screen/bulk
GET    /api/recruitment/applications
GET    /api/recruitment/applications/<application_id>/report
PATCH  /api/recruitment/applications/<application_id>/review
POST   /api/recruitment/applications/<application_id>/assign-interview
```

### Permissions Used

- `can_view_recruitment`: view jobs and applications.
- `can_manage_recruitment`: create and update jobs.
- `can_ai_screen_resumes`: run single and bulk resume screening.
- `can_review_recruitment`: save human review decisions and notes.
- `can_assign_interviewers`: create interview rooms.


## Resume file extraction update

The AI recruitment screening module now accepts and attempts text extraction from:

- `.pdf` using `PyPDF2` first and `pdfplumber` fallback
- `.docx` using `python-docx`, including paragraphs, tables, headers, and footers
- `.doc` using best-effort legacy extraction through `antiword`/`catdoc` if available, then readable binary-string fallback
- `.txt`, `.tex`, `.rtf`, and `.md` as text-like files

Important: scanned image-only PDFs do not contain selectable text. Those files need an OCR layer before screening. The current module returns a clear error instead of silently generating a bad score when no readable text is extracted.

## Latest Recruitment Enhancements

### Editable Jobs and Posting Window
- Existing jobs can now be opened in edit mode from the Recruitment workspace.
- Recruiters/controllers can update title, department, location, employment type, status, minimum AI score, JD text, and manual keywords.
- Each job supports a `Posting Open Until` date/time. Public applicants can apply only when the job status is `Open` and the closing date/time has not passed.

### Job Visibility and Control
- Super User can see and control every job, applicant, resume, AI report, and progress tracker.
- Job creators can always view/control their own jobs.
- Job creators/controllers can assign extra Viewers and Controllers.
- Viewers can see the job, applicants, resumes, AI reports, and progress.
- Controllers can edit jobs, screen resumes, review applicants, shortlist/reject, and assign interviews.

### Progress Tracking
- Job progress now tracks: JD Created, Open for Applications, Applicants Screened, Shortlist Ready, Interview Process, and Final Selection.
- Applicant progress now tracks: Applied, Screened, Pending Review, Shortlisted, Interview Scheduled, and Selected.
- Progress bars and step chips are visible in job cards, selected job details, and application cards.

### Improved Resume Screening Model
- Screening now handles skill aliases and synonyms. For example, `MongoDB`, `Mongo DB`, `MongoDB Atlas`, `NoSQL`, `document database`, and `non-relational database` are treated as related skill evidence.
- The model now combines semantic scoring, keyword coverage, writing quality, resume structure, ATS parse checks, category fit scores, and explainable keyword evidence.
- Added ATS-style checks for contact details, standard sections, skills, experience, projects, education, action verbs, and measurable achievements.
- Reports now include ATS score, category fit, parse warnings, matched aliases, missing keywords, highlighted evidence, and resume preview.

### Applicant Resume Access
- Applicant-uploaded resumes are linked to their job-specific application and AI report.
- Authorized viewers/controllers can download both the original resume and the converted TXT file that was actually used for screening from the Applications Review page.
- Resume download is protected by the same job visibility rules.


### Resume Normalization Before Screening

Every uploaded resume is now converted into a normalized `.txt` file before AI screening starts. The system stores both files:

- the original uploaded resume, such as PDF/DOC/DOCX/TXT/TEX/RTF/MD, and
- the converted text file inside `static/uploads/resumes/converted_txt/`.

The screening model then reads only the converted TXT content. This makes scoring consistent across file formats, makes extraction failures easier to debug, and lets authorized recruitment users download the exact text that was used by the AI report. Older applications can be backfilled automatically when the converted TXT download endpoint is used.

Scanned image-only PDFs still need OCR before conversion because they do not contain selectable text.

## Latest Recruitment Process Update: Candidate Access, Deletion, and Interview Room Workspace

This version extends the recruitment workflow after AI resume screening.

### Application and AI report deletion

Authorized recruitment controllers can now:

- Delete only the AI screening report for an application.
- Keep the application for rescreening after deleting the report.
- Delete the full application and linked AI report.
- Automatically cancel linked interview sessions when an application is deleted.

The delete controls are available from the Applications Review page.

### Shortlist warning and interview scheduling

When an applicant is marked as `Shortlisted`, the system now warns HR/controllers that the next required action is to:

1. Create or link a candidate account.
2. Schedule the interview.
3. Assign an interview room.
4. Define further process steps.

The applicant progress tracker now includes:

- Applied
- Screened
- Pending Review
- Shortlisted
- Candidate Account
- Interview Scheduled
- Interview Steps
- Selected

### Candidate user creation

When an authorized controller assigns an interview to a shortlisted applicant, the system automatically creates or links a limited candidate user account.

Candidate accounts use the role:

```text
Candidate
```

Candidate users can only access:

- Candidate process tracker
- Assigned interview room links

They are blocked from internal HRMS pages such as dashboard, recruitment, employees, payroll, performance, and admin screens.

The assignment response shows:

- Candidate UID
- Candidate email
- Temporary password if a new account was created
- Interview room link

Existing candidate accounts keep their current password.

### Candidate process page

A new page was added:

```text
/candidate-process
```

Candidates can use it to view:

- Application status
- Review status
- AI score summary
- Assigned interview room
- Scheduled interview time
- Process steps assigned by HR

### Interview room workspace

The interview room page was redesigned to include placeholders for the full AI voice and human interview experience.

The room now includes:

- Candidate webcam placeholder
- AI avatar placeholder
- Candidate voice activity bar
- AI voice activity bar
- Room chat
- Message type selector
- Transcript area
- Assigned process steps
- Candidate/job/interview details

Message types supported now:

```text
chat
transcript
ai-note
system
```

Transcript messages are also displayed in the live transcript panel. Actual webcam, STT, TTS, and AI avatar streaming can be wired later.

### Further process assignment

From the AI report page, controllers can assign:

- Main interviewer
- Panel members
- Scheduled date/time
- Interview mode
- Candidate process steps

Example process steps:

```text
Join interview room
Complete AI voice round
Attend technical panel
Wait for HR decision
```

These steps become visible to both HR/controllers and the candidate.

---

## 12. GitHub-Safe `config.py` Setup

The real `config.py` file is intentionally **not included for GitHub upload** because it can indirectly expose environment setup and deployment secrets. The project includes `config.example.py` instead.

### Create `config.py` locally

From the project root, copy the example file:

```powershell
copy config.example.py config.py
```

On Linux/macOS:

```bash
cp config.example.py config.py
```

### Create `.env` locally

Copy the environment example:

```powershell
copy .env.example .env
```

On Linux/macOS:

```bash
cp .env.example .env
```

Then edit `.env` with your MongoDB Atlas and secret values:

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/hrms_db?retryWrites=true&w=majority
DB_NAME=hrms_db
SECRET_KEY=replace-with-a-long-random-secret
JWT_SECRET_KEY=replace-with-another-long-random-secret
FLASK_ENV=development
UPLOAD_FOLDER=static/uploads
```

### Why this is needed

`app.py` imports `Config` from `config.py`, so the app needs a local `config.py` file to run. However, Git should only track `config.example.py`. The real `config.py` and `.env` stay private on your machine or deployment server.

### Git tracking rules

The `.gitignore` now includes:

```gitignore
.env
config.py
!.env.example
!config.example.py
```

This means:

- `.env` is private.
- `config.py` is private.
- `.env.example` is safe to upload.
- `config.example.py` is safe to upload.

### Files you should commit

```text
config.example.py
.env.example
README.md
README.txt
```

### Files you should not commit

```text
config.py
.env
```

If the project fails with `ModuleNotFoundError: No module named 'config'`, create `config.py` by copying `config.example.py`.
