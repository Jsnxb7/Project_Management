# Team Task Management Web Application

A full-stack collaborative task management web application built with **Flask**, **MongoDB Atlas**, **HTML**, **CSS**, **JavaScript**, and **Jinja2 templates**. The system supports organizations, role-based access, projects, task boards, milestones, comments, attachments, notifications, analytics, and relationship warnings for safer project administration.

The application is designed as a simplified real-world alternative to tools like Trello, Asana, and Jira, while keeping the codebase suitable for academic/project submission, deployment, and further extension.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Role Model](#role-model)
- [Relationship Rules](#relationship-rules)
- [Tech Stack](#tech-stack)
- [Folder Structure](#folder-structure)
- [Installation and Setup](#installation-and-setup)
- [Environment Variables](#environment-variables)
- [MongoDB Atlas Setup](#mongodb-atlas-setup)
- [Running the Application](#running-the-application)
- [Main Pages](#main-pages)
- [API Modules](#api-modules)
- [Security and Git Safety](#security-and-git-safety)
- [Deployment](#deployment)
- [Post-Deployment Setup](#post-deployment-setup)
- [Requirement Verification](#requirement-verification)
- [Future Enhancements](#future-enhancements)

---

## Project Overview

The Team Task Management Web Application helps teams organize work inside organizations and projects. Users can sign up, log in securely, create or join organizations, create projects under organizations, add project members, assign tasks, track deadlines, manage milestones, upload attachments, comment on tasks, receive notifications, and view analytics.

The latest version adds a stronger relationship layer so that projects, users, tasks, comments, attachments, milestones, and activity logs stay connected to the correct organization and project scope.

---

## Key Features

### 1. User Authentication

- User signup with name, email, and password.
- Secure login using hashed passwords with Flask-Bcrypt.
- JWT-based API authentication.
- Flask session-based page protection.
- Logout with JWT token blocklisting.
- Browser back/forward cache protection using no-cache headers.
- HTTP-only session cookie configuration.

### 2. Organization Management

- Create and manage organizations.
- Organization detail page.
- Organization configuration page.
- Add members to organizations.
- Change organization-level roles.
- Track user-to-organization membership through `user_org_memberships`.
- Keep embedded organization members compatible with the separate membership collection.
- Super User and organization managers can manage organization-level settings.

### 3. Project Management

- Create projects under organizations.
- Every project must belong to an organization.
- Project creator/admin can manage project settings.
- Add members from the same organization.
- Show organization-only candidates when inviting project members.
- Remove members from a project.
- Change project member roles.
- Pending invitation flow with accept/reject support.
- Archive projects.
- Soft-delete projects.
- Project metadata support:
  - Start date
  - Deadline
  - Priority
  - Category
  - Workflow status
  - Visibility
  - Tags

### 4. Task / Job Management

- Create tasks inside projects.
- Assign tasks only to active project members.
- Reassign tasks.
- Edit task title, description, status, priority, assignee, deadline, labels, and milestone.
- View tasks in a visual task board.
- Details/edit UI is designed to work through popup-style task panels rather than pushing content far below the board.
- Soft-delete tasks.
- Track tasks using statuses:
  - To Do
  - In Progress
  - Done
  - Blocked
  - Under Review
  - Cancelled
- Task priority support:
  - Low
  - Medium
  - High
  - Critical
- Deadline badges for overdue, due today, due soon, future, and completed tasks.
- Task labels for categorization and filtering.
- My Tasks page for member-specific assigned work.

### 5. Milestones

- Create project milestones.
- Archive milestones.
- Link tasks to milestones.
- Validate task deadlines against project and milestone deadlines.
- Track milestone progress in analytics.
- Include overdue milestone warnings in the Warning Center.

### 6. Subtasks and Completion Tracking

- Add checklist/subtasks to tasks.
- Mark subtasks as completed.
- Calculate task-level subtask completion percentage.
- Display visual progress bars.
- Prevent marking a task as Done when required checklist items are incomplete.
- Show project-level completion rate.
- Show per-member completion rate.

### 7. Comments and Collaboration

- Add comments to tasks.
- Edit comments.
- Delete comments.
- Show comment counts on tasks.
- Notify users when comments are added to relevant tasks.
- Comments carry project and organization metadata.

### 8. File Attachments

- Upload files to tasks.
- List task attachments.
- Delete attachments.
- File type validation.
- 8 MB upload size limit.
- File preview support for images.
- File icons and file size display.
- Attachments carry project and organization metadata.
- Allowed file types include:
  - PNG
  - JPG / JPEG
  - GIF
  - PDF
  - DOC / DOCX
  - TXT
  - ZIP

### 9. Dashboard, Analytics, and Warnings

- Global dashboard statistics.
- Role scope summary.
- Warning Center for relationship issues.
- Project analytics page.
- Project Health card with risk score.
- Status summary.
- Priority summary.
- User task summary.
- Overdue task tracking.
- Blocked task count.
- Unassigned task count.
- Milestone count.
- Milestone progress analytics.
- Completion percentage visualization.
- Workload/user completion progress bars.
- Per-member performance overview.

### 10. Notifications and Activity Logs

- Notification list page.
- Mark a single notification as read.
- Mark all notifications as read.
- Activity logging for:
  - Organization creation/update
  - Project creation/update
  - Member addition/removal
  - Task creation/update/deletion
  - Task status changes
  - Checklist/subtask updates
  - Milestone creation/update/archive
  - Comments
  - File uploads

### 11. Frontend UI

- Responsive HTML, CSS, and JavaScript frontend.
- Jinja2 template rendering.
- Dark neon/glassmorphism-inspired interface.
- Animated video background using `stars.mp4` / `stars.webm`.
- Reusable base layout.
- Navigation links for dashboard, organizations, projects, my tasks/jobs, notifications, profile, project management, and analytics.
- Toast-style frontend feedback.
- Search and filter controls for projects and tasks.

---

## Role Model

The application supports multiple scopes of access.

### Super User

- Global access across organizations, users, projects, dashboards, and warnings.
- Can view orphan users and organization relation warnings.
- Can create and manage organizations.
- Can access portal-level user management.

### Org Head / Organization Admin

- Organization-level management access.
- Can manage organization configuration.
- Can add organization members.
- Can create projects inside the organization.
- Can invite organization members into projects.
- Can view organization-level warnings and analytics.

### Team Lead / Project Admin

- Project-level management access.
- Can manage project members.
- Can create, assign, edit, and delete project tasks.
- Can create and archive milestones.
- Can manage project analytics and activity logs.

### Member

- Can view organizations/projects where they are an active member.
- Can view assigned tasks/jobs.
- Can update assigned task status where allowed.
- Can comment on relevant tasks.
- Can upload files to assigned/relevant tasks.
- Can track personal workload through My Tasks.

---

## Relationship Rules

The latest version enforces safer logical relationships while showing most relation violations as warnings instead of breaking the user flow.

- Every project should belong to at least one organization.
- Every user/member should belong to an organization.
- Project members should also be active members of the project organization.
- Task `organization_id` is inherited from the project.
- Task assignees must be active project members.
- Comments, attachments, subtasks, milestones, and activity logs store organization/project context.
- Task milestone must belong to the same project.
- Task deadline should not exceed project or milestone deadline.
- Organizations should have at least one active manager such as Admin or Org Head.
- Projects should have at least one active project manager/admin.
- Warnings include:
  - User without organization
  - Project without organization
  - Organization missing head/admin
  - Project missing manager
  - Project member not present in organization
  - Task organization mismatch
  - Task assignee mismatch
  - Overdue task
  - Overdue milestone

---

## Tech Stack

### Frontend

- HTML5
- CSS3
- JavaScript
- Jinja2 templates

### Backend

- Python
- Flask
- Flask Blueprints
- Flask-CORS
- Flask-Bcrypt
- Flask-JWT-Extended
- Flask sessions

### Database

- MongoDB Atlas
- PyMongo
- BSON ObjectId

### Deployment

- Gunicorn
- Render-compatible `render.yaml`
- Railway-compatible environment variable setup
- `Procfile` for platform deployment

### Other Tools

- python-dotenv
- Werkzeug
- dnspython

---

## Folder Structure

```text
Project_Management/
│
├── app.py
├── config.py
├── requirements.txt
├── Procfile
├── render.yaml
├── DEPLOYMENT.md
├── mongo_setup.py
│
├── database/
│   └── db.py
│
├── routes/
│   ├── activity_routes.py
│   ├── attachment_routes.py
│   ├── auth_routes.py
│   ├── comment_routes.py
│   ├── dashboard_routes.py
│   ├── milestone_routes.py
│   ├── notification_routes.py
│   ├── organization_routes.py
│   ├── portal_routes.py
│   ├── project_routes.py
│   ├── task_routes.py
│   └── user_routes.py
│
├── scripts/
│   ├── create_super_user.py
│   └── repair_org_relations.py
│
├── services/
│   ├── activity_service.py
│   ├── notification_service.py
│   ├── permission_service.py
│   └── relation_service.py
│
├── static/
│   ├── css/
│   │   └── style.css
│   ├── images/
│   │   ├── stars.mp4
│   │   └── stars.webm
│   ├── js/
│   │   ├── app.js
│   │   ├── auth.js
│   │   ├── dashboard.js
│   │   ├── manage_project.js
│   │   ├── my_tasks.js
│   │   ├── notifications.js
│   │   ├── organization_config.js
│   │   ├── organization_detail.js
│   │   ├── organizations.js
│   │   ├── portal_users.js
│   │   ├── profile.js
│   │   ├── project_analytics.js
│   │   ├── projects.js
│   │   └── tasks.js
│   └── uploads/
│       └── .gitkeep
│
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html
│   ├── login.html
│   ├── manage_project.html
│   ├── my_tasks.html
│   ├── notifications.html
│   ├── organization_config.html
│   ├── organization_detail.html
│   ├── organizations.html
│   ├── portal_users.html
│   ├── profile.html
│   ├── projects.html
│   ├── project_analytics.html
│   ├── signup.html
│   └── task_board.html
│
└── utils/
    ├── decorators.py
    ├── response.py
    └── validators.py
```

---

## Installation and Setup

### 1. Clone or Download the Project

```bash
git clone <your-repository-url>
cd Project_Management
```

If you are using a downloaded ZIP file, extract it and open the `Project_Management` folder.

### 2. Create a Virtual Environment

For Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

For macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file in the root folder of the project. Use `.env.example` as the template.

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/team_task_db?retryWrites=true&w=majority
DB_NAME=team_task_db
SECRET_KEY=your-long-random-flask-secret-key
JWT_SECRET_KEY=your-long-random-jwt-secret-key
FLASK_ENV=development
UPLOAD_FOLDER=static/uploads
ENABLE_SEED=false
```

For production deployment, set:

```env
FLASK_ENV=production
```

Never commit the real `.env` file. The MongoDB connection string, Flask secret key, and JWT secret key must stay private.

---

## MongoDB Atlas Setup

1. Create a MongoDB Atlas account.
2. Create a new cluster.
3. Create a database user with a strong password.
4. Give the user read/write access to the project database.
5. Go to **Network Access** and add your allowed IP address.
6. For local development, add your current IP address.
7. For platforms like Railway or Render, use the platform-provided outbound IP if available.
8. If the platform does not provide a fixed outbound IP, `0.0.0.0/0` may be required, but it is less secure.
9. Copy the MongoDB connection string and place it in `.env` as `MONGO_URI`.

Example:

```env
MONGO_URI=mongodb+srv://myuser:mypassword@cluster0.xxxxx.mongodb.net/team_task_db?retryWrites=true&w=majority
```

---

## Running the Application

Start the Flask server:

```bash
python app.py
```

The application will run on:

```text
http://127.0.0.1:5000
```

If a deployment platform sets a `PORT` environment variable, the app automatically uses that port.

---

## Main Pages

| Page | Route | Description |
|---|---|---|
| Landing Page | `/` | Public homepage |
| Signup | `/signup` | Create a new account |
| Login | `/login` | User login page |
| Dashboard | `/dashboard` | User dashboard, role scope, statistics, and warnings |
| Organizations | `/organizations` | View and create organizations |
| Organization Detail | `/organizations/<org_id>` | View organization members and projects |
| Organization Config | `/organizations/<org_id>/config` | Manage organization settings and members |
| Portal Users | `/portal/users` | Super-user style user administration |
| Projects | `/projects` | View and create projects |
| My Tasks | `/my-tasks` | View tasks/jobs assigned to the logged-in user |
| Task Board | `/project/<project_id>/tasks` | Manage project tasks/jobs |
| Manage Project | `/project/<project_id>/manage` | Admin project/member/milestone settings |
| Project Analytics | `/project/<project_id>/analytics` | Project-level analytics and health |
| Notifications | `/notifications` | View notifications |
| Profile | `/profile` | View and update profile |

---

## API Modules

The backend is organized using Flask Blueprints.

| Module | Base Route | Purpose |
|---|---|---|
| Authentication | `/api/auth` | Signup, login, logout, current user |
| Organizations | `/api/organizations` | Organization CRUD, members, organization configuration |
| Portal | `/api/portal` | Portal-level user controls |
| Projects | `/api/projects` | Project CRUD, members, invitations, project settings |
| Tasks | `/api/tasks` | Task creation, updates, filters, subtasks, status changes |
| Milestones | `/api` | Project milestone creation, updates, archive, and task relations |
| Dashboard | `/api/dashboard` | Dashboard statistics, role scope, warnings, summaries |
| Comments | `/api` | Task comments |
| Attachments | `/api` | Task file upload/list/delete |
| Notifications | `/api/notifications` | Notification list and read status |
| Activity | `/api/activity` | Project and organization activity logs |
| Users | `/api/users` | Profile and password management |

---

## Security and Git Safety

- Password hashing is handled with Flask-Bcrypt.
- API routes are protected with JWT where required.
- Frontend pages are protected with Flask sessions.
- Session cookies are HTTP-only.
- Secure cookies are enabled when `FLASK_ENV=production`.
- SameSite cookie protection is enabled.
- Protected pages include no-cache headers to prevent browser back-button access after logout.
- Secrets are loaded from environment variables.
- MongoDB URI is stored in `.env`, not inside source code.
- File uploads are validated and limited to 8 MB.
- Role-based and relation-based permission checks are applied.
- Important entities use soft deletion where appropriate.

### Important Secret Handling Notes

The real `.env` file must never be uploaded to GitHub or shared publicly.

Recommended `.gitignore` entries:

```gitignore
.env
.env.*
!.env.example
__pycache__/
*.pyc
venv/
env/
.venv/
instance/
static/uploads/*
!static/uploads/.gitkeep
*.db
*.sqlite
*.sqlite3
*.pem
*.key
*.crt
*.p12
*.pfx
.DS_Store
Thumbs.db
.vscode/
.idea/
```

Before committing, check tracked files:

```bash
git status
git ls-files .env
```

If `.env` appears in tracked files, remove it from Git tracking without deleting your local file:

```bash
git rm --cached .env
git commit -m "Remove env file from tracking"
```

To create a clean ZIP without ignored secrets:

```bash
git archive --format=zip --output=Project_Management_clean.zip HEAD
```

---

## Deployment

The project includes deployment-ready files:

- `Procfile`
- `render.yaml`
- `DEPLOYMENT.md`
- `requirements.txt`
- Gunicorn support

### Render Start Command

```bash
gunicorn "app:create_app()"
```

### Railway Start Command

```bash
gunicorn "app:create_app()"
```

### Required Production Environment Variables

```env
MONGO_URI=your-mongodb-atlas-uri
DB_NAME=team_task_db
SECRET_KEY=your-production-secret-key
JWT_SECRET_KEY=your-production-jwt-secret-key
FLASK_ENV=production
ENABLE_SEED=false
```

Do not put production values directly into `render.yaml`, `Procfile`, `README.md`, or source files. Add them through the hosting platform's environment variable dashboard.

---

## Post-Deployment Setup

After deploying or after pulling relation-rule updates, run the database setup and repair scripts once from your local terminal or deployment shell:

```bash
python mongo_setup.py
python scripts/repair_org_relations.py
```

Use the super-user creation script only when you intentionally want to create or repair the first privileged user:

```bash
python scripts/create_super_user.py
```

Keep the super-user script out of public commits if it contains local-only credentials or hardcoded setup values.

---

## Requirement Verification

| Requirement | Status |
|---|---|
| Signup with name, email, and password | Implemented |
| Secure login | Implemented |
| Password hashing | Implemented |
| JWT/session-based authentication | Implemented |
| Logout and token blocklist | Implemented |
| Browser back-button/session protection | Implemented |
| Create organizations | Implemented |
| Organization member management | Implemented |
| Super User and Org Head options | Implemented |
| Create projects under organizations | Implemented |
| Projects must belong to organizations | Implemented |
| Users/members should belong to organizations | Implemented |
| Admin can add/remove project members | Implemented |
| Project members limited to organization members | Implemented |
| Members can view assigned projects | Implemented |
| Create and assign tasks/jobs | Implemented |
| My Tasks assigned-work page | Implemented |
| Task deadline support | Implemented |
| Task priority support | Implemented |
| Task status tracking | Implemented |
| Popup-style task details/edit flow | Implemented |
| Role-based Admin/Member access | Implemented |
| Warning-only relation checks | Implemented |
| Dashboard Warning Center | Implemented |
| Milestones | Implemented |
| Task-to-milestone relation | Implemented |
| Subtask/checklist tracking | Implemented |
| Task completion percentage | Implemented |
| Checklist guard before Done | Implemented |
| Comments | Implemented |
| Notifications | Implemented |
| Activity logs | Implemented |
| File attachments | Implemented |
| Search and filters | Implemented |
| Profile management | Implemented |
| Project analytics and health card | Implemented |
| MongoDB Atlas integration | Implemented |
| Deployment preparation | Implemented |

---

## Future Enhancements

- Email-based project invitations.
- Real-time updates using WebSockets.
- Drag-and-drop Kanban task movement.
- Calendar view for deadlines and milestones.
- Team chat inside projects.
- Admin export reports as PDF or CSV.
- User profile image upload.
- Password reset through email OTP.
- More detailed audit logs.
- Fine-grained custom permissions per organization.
- Mobile-first UI improvements.

---

## Author

Developed as a full-stack Team Task Management Web Application project using Flask, MongoDB Atlas, HTML, CSS, JavaScript, and Jinja2.
