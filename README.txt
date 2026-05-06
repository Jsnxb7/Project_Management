# Team Task Management Web Application

A full-stack collaborative task management web application built using **Flask**, **MongoDB Atlas**, **HTML**, **CSS**, **JavaScript**, and **Jinja2 templates**. The application allows users to create projects, invite team members, assign tasks, track deadlines, manage task progress, upload attachments, add comments, view notifications, and analyze project performance.

This project is designed as a simplified real-world alternative to tools like Trello, Asana, and Jira, with role-based project access and secure authentication.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Folder Structure](#folder-structure)
- [Installation and Setup](#installation-and-setup)
- [Environment Variables](#environment-variables)
- [MongoDB Atlas Setup](#mongodb-atlas-setup)
- [Running the Application](#running-the-application)
- [Main Pages](#main-pages)
- [API Modules](#api-modules)
- [Role-Based Access](#role-based-access)
- [Security Features](#security-features)
- [Deployment](#deployment)
- [Requirement Verification](#requirement-verification)
- [Future Enhancements](#future-enhancements)

---

## Project Overview

The Team Task Management Web Application helps teams organize project work in a structured and visual way. Users can sign up, log in securely, create projects, add members, assign tasks, set deadlines, track progress, and collaborate through comments, attachments, notifications, and activity logs.

Each project supports two main roles:

- **Admin**: The project creator or a promoted member who can manage members, edit projects, assign tasks, delete/archive projects, and control project settings.
- **Member**: A project participant who can view assigned projects, update assigned tasks, comment, upload files to assigned tasks, and track personal workload.

---

## Key Features

### 1. User Authentication

- User signup with name, email, and password.
- Secure login using hashed passwords with Flask-Bcrypt.
- JWT-based API authentication.
- Flask session-based page protection.
- Logout with JWT token blocklisting.
- Protected pages redirect unauthenticated users to the login page.
- Browser back/forward cache protection using no-cache headers.

### 2. Project Management

- Create new projects.
- Project creator automatically becomes Admin.
- View all projects where the user is an active member.
- Edit project details.
- Archive projects.
- Soft-delete projects.
- Add members by email.
- Remove members from a project.
- Change member roles between Admin and Member.
- Pending invitation flow with accept/reject support.
- Project metadata support:
  - Start date
  - Deadline
  - Priority
  - Category
  - Workflow status
  - Visibility
  - Tags

### 3. Task Management

- Create tasks inside projects.
- Assign tasks to project members.
- Reassign tasks.
- Edit task title, description, status, priority, assignee, deadline, and labels.
- Soft-delete tasks.
- View tasks in a visual task board.
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
- Task labels for categorization and searching.

### 4. Subtasks and Completion Tracking

- Add checklist/subtasks to tasks.
- Mark subtasks as completed.
- Calculate task-level subtask completion percentage.
- Display visual progress bars.
- Show project-level completion rate.
- Show per-member completion rate.

### 5. Comments and Collaboration

- Add comments to tasks.
- Edit comments.
- Delete comments.
- Show comment counts on tasks.
- Notify users when comments are added to relevant tasks.

### 6. File Attachments

- Upload files to tasks.
- List task attachments.
- Delete attachments.
- File type validation.
- 8 MB upload size limit.
- File preview support for images.
- File icons and file size display.
- Allowed file types include:
  - PNG
  - JPG / JPEG
  - GIF
  - PDF
  - DOC / DOCX
  - TXT
  - ZIP

### 7. Dashboard and Analytics

- Global dashboard statistics.
- My Tasks page for user-specific workload tracking.
- Project analytics page.
- Status summary.
- Priority summary.
- User task summary.
- Overdue task tracking.
- Completion percentage visualization.
- Per-member performance overview.

### 8. Notifications and Activity Logs

- Notification list page.
- Mark single notification as read.
- Mark all notifications as read.
- Activity logging for:
  - Project creation
  - Member addition
  - Task creation
  - Task updates
  - Task status changes
  - Task deletion
  - Comments
  - File uploads

### 9. Frontend UI

- Responsive HTML, CSS, and JavaScript frontend.
- Jinja2 template rendering.
- Dark glassmorphism-inspired user interface.
- Animated video background.
- Reusable base layout.
- Navigation links for dashboard, projects, my tasks, notifications, profile, project management, and analytics.
- Toast-style frontend feedback.
- Search and filter controls for projects and tasks.

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
│   ├── notification_routes.py
│   ├── project_routes.py
│   ├── task_routes.py
│   └── user_routes.py
│
├── services/
│   ├── activity_service.py
│   ├── notification_service.py
│   └── permission_service.py
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
│   │   ├── profile.js
│   │   ├── projects.js
│   │   ├── project_analytics.js
│   │   └── tasks.js
│   └── uploads/
│
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html
│   ├── login.html
│   ├── manage_project.html
│   ├── my_tasks.html
│   ├── notifications.html
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

Create a `.env` file in the root folder of the project.

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/team_task_db?retryWrites=true&w=majority
DB_NAME=team_task_db
SECRET_KEY=your-long-random-flask-secret-key
JWT_SECRET_KEY=your-long-random-jwt-secret-key
FLASK_ENV=development
UPLOAD_FOLDER=static/uploads
```

For production deployment, set:

```env
FLASK_ENV=production
```

Do not commit `.env` to GitHub. The MongoDB connection string, Flask secret key, and JWT secret key must stay private.

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
| Dashboard | `/dashboard` | User dashboard and overview |
| Projects | `/projects` | View and create projects |
| My Tasks | `/my-tasks` | View tasks assigned to the logged-in user |
| Task Board | `/project/<project_id>/tasks` | Manage project tasks |
| Manage Project | `/project/<project_id>/manage` | Admin project/member settings |
| Project Analytics | `/project/<project_id>/analytics` | Project-level analytics |
| Notifications | `/notifications` | View notifications |
| Profile | `/profile` | View and update profile |

---

## API Modules

The backend is organized using Flask Blueprints.

| Module | Base Route | Purpose |
|---|---|---|
| Authentication | `/api/auth` | Signup, login, logout, current user |
| Projects | `/api/projects` | Project CRUD, members, invitations, project settings |
| Tasks | `/api/tasks` | Task creation, updates, filters, subtasks, status changes |
| Dashboard | `/api/dashboard` | Dashboard statistics and summaries |
| Comments | `/api` | Task comments |
| Attachments | `/api` | Task file upload/list/delete |
| Notifications | `/api/notifications` | Notification list and read status |
| Activity | `/api/activity` | Project activity logs |
| Users | `/api/users` | Profile and password management |

---

## Role-Based Access

### Admin Permissions

Admins can:

- Create and edit projects.
- Add members.
- Remove members.
- Change member roles.
- Create tasks.
- Assign and reassign tasks.
- Edit task details.
- Delete tasks.
- Upload/delete files for project tasks.
- Archive or delete projects.
- View analytics and activity logs.

### Member Permissions

Members can:

- View projects they belong to.
- View assigned tasks.
- Update status of assigned tasks.
- Add comments.
- Edit/delete their own comments.
- Upload files to assigned tasks.
- View notifications.
- Track their workload through My Tasks.

---

## Security Features

- Password hashing using Flask-Bcrypt.
- JWT-protected API routes.
- Session-based protection for frontend pages.
- HTTP-only session cookies.
- Secure cookies enabled in production.
- SameSite cookie protection.
- No-cache headers on protected pages to prevent browser back-button access after logout.
- Environment-variable-based secrets.
- MongoDB URI hidden using `.env`.
- File upload validation.
- File size limit of 8 MB.
- Role-based permission checks.
- Soft deletion for important entities.

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
gunicorn app:create_app()
```

### Railway Start Command

```bash
gunicorn app:create_app()
```

### Required Production Environment Variables

```env
MONGO_URI=your-mongodb-atlas-uri
DB_NAME=team_task_db
SECRET_KEY=your-production-secret-key
JWT_SECRET_KEY=your-production-jwt-secret-key
FLASK_ENV=production
```

---

## Requirement Verification

| Requirement | Status |
|---|---|
| Signup with name, email, and password | Implemented |
| Secure login | Implemented |
| Password hashing | Implemented |
| JWT/session-based authentication | Implemented |
| Create projects | Implemented |
| Creator becomes Admin | Implemented |
| Admin can add/remove members | Implemented |
| Members can view assigned projects | Implemented |
| Create and assign tasks | Implemented |
| Task deadline support | Implemented |
| Task priority support | Implemented |
| Task status tracking | Implemented |
| Role-based Admin/Member access | Implemented |
| Dashboard | Implemented |
| Project analytics | Implemented |
| Task completion percentage | Implemented |
| Subtask/checklist tracking | Implemented |
| Comments | Implemented |
| Notifications | Implemented |
| Activity logs | Implemented |
| File attachments | Implemented |
| Search and filters | Implemented |
| Profile management | Implemented |
| Session management | Implemented |
| MongoDB Atlas integration | Implemented |
| Deployment preparation | Implemented |

---

## Future Enhancements

- Email-based project invitations.
- Real-time updates using WebSockets.
- Drag-and-drop Kanban task movement.
- Calendar view for deadlines.
- Team chat inside projects.
- Admin export reports as PDF or CSV.
- User profile image upload.
- Password reset through email OTP.
- More detailed audit logs.
- Mobile-first UI improvements.

---

## Author

Developed as a full-stack Team Task Management Web Application project using Flask, MongoDB Atlas, HTML, CSS, JavaScript, and Jinja2.
