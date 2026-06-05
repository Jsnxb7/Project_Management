AI PeopleOps HRMS

AI PeopleOps HRMS is a Flask + MongoDB Atlas based Human Resource Management System rebuilt for the theme **“Build the Future of HR Management with AI-Powered Solutions.”**

The project combines core HRMS operations, role-based dashboards, AI recruitment, public candidate applications, interview rooms, AI voice-interview evaluation, user-specific theme kits, responsive UI, and MongoDB-backed persistence.

------------------------------------------------------------

#1. Project Objective

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

------------------------------------------------------------

#2. Tech Stack

| Layer | Technology |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Backend | Python, Flask |
| Database | MongoDB Atlas using `pymongo` |
| Frontend | HTML, CSS, JavaScript |
| Authentication | JWT-style token stored client-side |
| Styling | Custom responsive CSS, theme variables |
| AI Recruitment | Lightweight deterministic vector-style scoring, keyword matching, grammar scoring |
| Resume Parsing | PDF/DOC/DOCX/TXT normalized to TXT before screening |
| Real-time-ready Layer | Interview rooms and message structure ready for SocketIO/WebSocket extension |
| Deployment Ready | Procfile, Render config, environment variables |

------------------------------------------------------------

#3. Main Functional Modules

#3.1 Authentication and Access Control

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Login page | `/login` |
| Signup page | `/signup` |
| Auth API | `/api/auth` |

------------------------------------------------------------

#3.2 Role System

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

##Role Rules

| Role Group | Access Level |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
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

services/hrms_service.py
utils/decorators.py


------------------------------------------------------------

#3.3 Personalized Dashboards

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

/dashboard


------------------------------------------------------------

#3.4 Employee Management

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Employee page | `/employees` |
| HRMS API | `/api/hrms` |

MongoDB collection:

employees


------------------------------------------------------------

#3.5 Attendance Management

Attendance is part of the core HRMS requirement.

Features:

- Employee check-in/check-out structure
- Attendance logs
- Working hours support
- Late/absence tracking foundation
- Employee-level attendance view
- Manager/admin scoped visibility

Main route:

/attendance


MongoDB collection:

attendance


------------------------------------------------------------

#3.6 Payroll Management

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

/payroll


MongoDB collection:

payroll


------------------------------------------------------------

#3.7 Performance Tracking

Performance tracking supports employee growth and review management.

Features:

- KPI reviews
- Manager feedback
- Ratings
- Goal tracking foundation
- Promotion recommendation foundation
- Employee performance history

Main route:

/performance


MongoDB collection:

performance_reviews


------------------------------------------------------------

#3.8 Public Candidate / Outsider Portal

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Careers page | `/careers` |
| Apply page | `/apply` |
| Shared interview room | `/interview-room/<room_code>` |

------------------------------------------------------------

#3.9 AI Resume Screening

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Recruitment workspace | `/recruitment` |
| Applications and AI reports | `/applications` |
| Recruitment API | `/api/recruitment` |

Main service:

services/ai_recruitment_service.py


MongoDB collections:

jobs
applications
resume_screening_results
job_knowledge_base


##Screening Logic

The current implementation is lightweight and works without paid AI APIs. It can later be upgraded to:

- Sentence Transformers
- FAISS
- LangChain/RAG
- Fine-tuned local models
- Hugging Face embedding models

------------------------------------------------------------

#3.10 AI Voice Interview Evaluation

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

/voice-interview


Recommended future full voice pipeline:

Browser microphone
    -> MediaRecorder audio chunks
    -> Flask/WebSocket endpoint
    -> Whisper or faster-distil-whisper STT
    -> Chat/interview model
    -> RAG over job documents
    -> Similarity scoring
    -> Piper TTS response
    -> Browser audio playback


Suggested models/tools:

- STT: Whisper tiny/base, faster-distil-whisper
- TTS: Piper
- Chat: lightweight Hugging Face instruct/chat model
- Similarity: Sentence Transformers
- Knowledge retrieval: job knowledge base + embeddings

------------------------------------------------------------

#3.11 Interview Rooms

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Interview rooms list | `/interviews` |
| Shared room | `/interview-room/<room_code>` |

MongoDB collections:

interview_rooms
interview_sessions
interview_messages


------------------------------------------------------------

#3.12 User-Specific Theme Kits

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

/themes


Theme API:

/api/theme


MongoDB collection:

user_themes


------------------------------------------------------------

#3.13 Sidebar Navigation Behavior

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

templates/base.html
static/css/style.css
static/js/app.js


------------------------------------------------------------

#3.14 Responsive UI

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

------------------------------------------------------------

#3.15 Notifications

Notifications are available for authenticated users.

Use cases:

- Leave updates
- Payroll updates
- Interview updates
- Recruitment actions
- System activity messages

Main route:

/notifications


MongoDB collection:

notifications


------------------------------------------------------------

#3.16 Profile Management

Each logged-in user can access their profile.

Features:

- View account information
- Role display
- Personal details foundation
- Theme personalization link

Main route:

/profile


------------------------------------------------------------

#3.17 User Management and Bulk Import

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
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| User management | `/portal/users` |
| Bulk import | `/portal/import-users` |

------------------------------------------------------------

#3.18 Performance and Scalability Optimizations

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

------------------------------------------------------------

#4. Main Pages

| Page | Route |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
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

------------------------------------------------------------

#5. API Route Groups

| Area | Prefix |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Authentication | `/api/auth` |
| HRMS data | `/api/hrms` |
| Recruitment + AI | `/api/recruitment` |
| User theme | `/api/theme` |
| HRMS user administration | `/api/portal` |
| Profile | `/api/users` |
| Notifications | `/api/notifications` |
| Activity logs | `/api/activity` |

------------------------------------------------------------

#6. MongoDB Collections

The system uses these collections:

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


------------------------------------------------------------

#7. Local Setup

Create and activate a virtual environment:

py -m venv .venv
.\.venv\Scripts\activate


Install requirements:

pip install -r requirements.txt


Create environment file:

copy .env.example .env


Run the project:

python app.py


Open:

http://127.0.0.1:5000


------------------------------------------------------------

#8. Environment Variables

Create `.env` from `.env.example`.

MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/hrms_db?retryWrites=true&w=majority
DB_NAME=hrms_db
SECRET_KEY=change-this-secret
JWT_SECRET_KEY=change-this-jwt-secret
FLASK_ENV=development
UPLOAD_FOLDER=static/uploads


Do not commit `.env`.

`.env` is intentionally excluded from the clean zip.

------------------------------------------------------------

#9. Important Files

| File | Purpose |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `app.py` | Main Flask app entry point |
| `config.py` | App configuration and environment loading |
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

------------------------------------------------------------

#10. Development Notes

- Use the latest zip as the main project version.
- The previous zips are only backups.
- The project currently includes lightweight AI-style scoring so it works without paid APIs.
- For a production-grade AI version, replace or extend the current scorer with embeddings and actual model inference.
- For real-time interviews, integrate Flask-SocketIO and use Redis for multi-worker scaling.
- For 5,000+ users, keep dashboard pages paginated and avoid loading entire collections into the frontend.

------------------------------------------------------------

#11. Suggested Next Development Steps

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


Recruitment Screening Model Layer
---------------------------------
A standalone recruitment screening model has been added at:
services/recruitment_screening_model.py

It supports:
- JD keyword extraction
- resume normalization from PDF/DOC/DOCX/TXT/TEX/RTF/MD into TXT before screening
- embedding/vector generation
- cosine similarity scoring
- keyword match scoring
- writing style and grammar-like scoring
- resume structure scoring
- weighted final score calculation
- shortlist/reject decision by minimum score
- matched keyword highlights for reports

The existing services/ai_recruitment_service.py file now works as a compatibility wrapper around the new model.

Demo command:
python scripts/demo_recruitment_screening.py

Detailed documentation:
RECRUITMENT_SCREENING_MODEL.md

LATEST UPDATE: RECRUITMENT SCREENING MODEL WIRED TO UI

The recruitment screening model is now connected to the Flask application and UI.

Job and JD Creation
- Recruitment users can create job profiles from the Recruitment AI page.
- A job contains title, department, location, employment type, minimum AI score, optional manual keywords, and JD text.
- The system extracts JD keywords automatically when manual keywords are not provided.

Single Resume Screening
- HR can select a job, upload one resume, and enter candidate details.
- The system extracts resume text, calculates semantic score, keyword score, writing score, structure score, and final weighted score.
- The applicant is saved as an application with a linked AI report.

Bulk Resume Screening
- HR can upload multiple resumes for one selected job.
- Each resume becomes its own application and AI report.
- Candidate names are generated from filenames and can be reviewed later.

Job-Wise Distinction
- Every application belongs to a job.
- The Applications page supports job filtering, review-status filtering, and shortlisted-only view.

AI Report Highlights
- Reports include final score, semantic score, keyword score, writing score, structure score, recommendation, confidence, matched keywords, missing keywords, and highlighted resume snippets.

Human Review Workflow
- Relevant users can mark applications as Pending Review, Needs Review, Shortlisted, Interview Scheduled, Selected, Rejected, or On Hold.
- Review notes are stored with the application.

Interview Connection
- Authorized users can assign an application to an interview room directly from Applications.

New API Endpoints
- GET    /api/recruitment/jobs
- GET    /api/recruitment/jobs/<job_id>
- POST   /api/recruitment/jobs
- PATCH  /api/recruitment/jobs/<job_id>
- POST   /api/recruitment/screen/single
- POST   /api/recruitment/screen/bulk
- GET    /api/recruitment/applications
- GET    /api/recruitment/applications/<application_id>/report
- PATCH  /api/recruitment/applications/<application_id>/review
- POST   /api/recruitment/applications/<application_id>/assign-interview


Resume file extraction update

The AI recruitment screening module now accepts and attempts text extraction from PDF, DOCX, DOC, TXT, TEX, RTF, and MD files. PDF extraction uses PyPDF2 first and pdfplumber as a fallback. DOCX extraction uses python-docx and includes paragraphs, tables, headers, and footers. Legacy DOC files are handled on a best-effort basis with antiword/catdoc when available, then a readable-text fallback. Scanned image-only PDFs need OCR before screening.

LATEST RECRUITMENT ENHANCEMENTS

Editable Jobs and Posting Window
- Existing jobs can be edited from the Recruitment workspace.
- Recruiters/controllers can update title, department, location, employment type, status, minimum AI score, JD text, and manual keywords.
- Each job supports a Posting Open Until date/time. Public applicants can apply only while status is Open and the closing time has not passed.

Job Visibility and Control
- Super User can see and control every job, applicant, resume, AI report, and progress tracker.
- Job creators can always view/control their own jobs.
- Extra Viewers and Controllers can be assigned per job.
- Viewers can see job, applicants, resumes, AI reports, and progress.
- Controllers can edit jobs, screen resumes, review applicants, shortlist/reject, and assign interviews.

Progress Tracking
- Job progress: JD Created, Open for Applications, Applicants Screened, Shortlist Ready, Interview Process, Final Selection.
- Applicant progress: Applied, Screened, Pending Review, Shortlisted, Interview Scheduled, Selected.

Improved Resume Screening Model
- Skill aliases and synonyms are now handled, for example MongoDB, Mongo DB, MongoDB Atlas, NoSQL, document database, and non-relational database.
- Screening combines semantic score, keyword score, writing score, structure score, ATS parse checks, category fit, and highlighted evidence.
- Reports include ATS score, category fit, parse warnings, matched aliases, missing keywords, resume evidence, and resume preview.

Applicant Resume Access
- Uploaded resumes are linked to application reports.
- Authorized viewers/controllers can download resumes from the Applications Review page.


### Resume Normalization Before Screening

Every uploaded resume is now converted into a normalized `.txt` file before AI screening starts. The system stores both files:

- the original uploaded resume, such as PDF/DOC/DOCX/TXT/TEX/RTF/MD, and
- the converted text file inside `static/uploads/resumes/converted_txt/`.

The screening model then reads only the converted TXT content. This makes scoring consistent across file formats, makes extraction failures easier to debug, and lets authorized recruitment users download the exact text that was used by the AI report. Older applications can be backfilled automatically when the converted TXT download endpoint is used.

Scanned image-only PDFs still need OCR before conversion because they do not contain selectable text.

Latest Recruitment Process Update: Candidate Access, Deletion, and Interview Room Workspace

- Recruitment controllers can delete only an AI report or delete the full application and linked reports.
- Shortlisted applicants now trigger a warning to schedule interview and assign an interview room.
- Assigning an interview creates or links a limited Candidate user account.
- Candidate accounts can access only the candidate process tracker and assigned interview rooms.
- Candidate process page added at /candidate-process.
- Interview room now includes chat, transcript area, webcam placeholder, AI avatar placeholder, and voice activity bar placeholders.
- Controllers can assign main interviewer, panel members, schedule date/time, mode, and further process steps.
- Candidate can view application progress, interview room link, schedule, and assigned steps.
