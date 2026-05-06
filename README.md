# Team Task Manager

A full-stack Team Task Management Web Application built with Flask, HTML, CSS, JavaScript, Jinja2, and MongoDB Atlas.

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Update `.env` with your MongoDB Atlas URI before running the app.

## First Features Included

- Flask app factory setup
- Secure environment-based config
- MongoDB Atlas connection
- Signup API
- Login API
- JWT token generation
- Basic project creation API
- Basic project listing API
- Landing, login, signup, dashboard, and projects pages


## Phase 2 Added

- Task creation API
- Task listing by project
- Task detail API
- Task update API
- Task status update API
- Soft delete task API
- Admin-only task creation/deletion
- Member status update for assigned tasks
- Add project member by email API
- View project members API
- Dashboard statistics API
- Task board frontend page
- Project cards now link to task board

## Main URLs

- `/`
- `/signup`
- `/login`
- `/dashboard`
- `/projects`
- `/project/<project_id>/tasks`


## Phase 3 Added

- Task comments API
- Comment create/read/update/delete rules
- Activity log service
- Project activity API
- Notification service
- Notification list API
- Mark notification as read API
- Mark all notifications as read API
- Notifications page
- Task-board comments panel
- Recent project activity panel
- Activity logging for project creation, member addition, task creation, task updates, task status changes, task deletion, and comments
- Notifications for task assignment, comments, status updates, and project membership


## Phase 4 Added

- File attachment upload API
- File attachment listing API
- File attachment delete API
- File type validation
- 8 MB file size validation
- Upload permissions:
  - Admin can upload/delete files for any project task
  - Member can upload files only to assigned tasks
  - Uploader or Admin can delete attachments
- Attachment activity logs
- Attachment notifications
- Task search by title, description, or label
- Task filter by status
- Task filter by priority
- Frontend upload panel inside task board
- Frontend attachment list with open/delete actions
- Frontend search and filter panel


## Phase 5 Added

- Profile page
- Profile update API
- Password change API
- Project edit API
- Project archive API
- Project soft-delete API
- Remove member API
- Change member role API
- Manage project page
- Member role controls
- Admin danger zone controls

## Phase 6 Added

- Advanced project analytics page
- Status summary API
- Priority summary API
- User task summary API
- Overdue tasks API
- Project completion rate
- Per-member completion rate

## Phase 7 Added

- Deployment preparation
- `Procfile`
- `render.yaml`
- `DEPLOYMENT.md`
- Added `gunicorn`
- UI polish for admin, analytics, members, and profile screens
- Final navigation links for profile, notifications, management, and analytics

## Enhanced Version Notes

This version was upgraded using the earlier template project as UI inspiration:

- Added animated video background with dark glassmorphism overlay.
- Reworked navbar into an authenticated shell with mobile toggle and logout.
- Added global toast feedback and reusable frontend helpers.
- Improved landing page with feature cards and clearer product positioning.
- Added signup confirm-password validation.
- Added project search and safer dynamic HTML rendering.
- Expanded dashboard with To Do, In Progress, Done, High/Critical, and completion-rate progress bar.
- Improved project/task cards, Kanban board, filters, comments, attachments, notifications, profile, and analytics UI.
- Added task labels input and preserved existing label-based task search.
- Removed committed `.env` from the deliverable zip for security. Use `.env.example` locally.

## Requirement Verification Checklist

| Requirement | Status |
|---|---|
| Signup with name/email/password | Implemented |
| Secure login | Implemented with JWT and bcrypt |
| Secure MongoDB Atlas config | Implemented through environment variables |
| Create projects | Implemented |
| Creator becomes Admin | Implemented |
| Admin add/remove members | Implemented |
| Member can view assigned projects | Implemented through project membership query |
| Create/assign/manage tasks | Implemented |
| Admin/Member role-based access | Implemented |
| Member can update assigned task status | Implemented |
| Dashboard analytics | Implemented globally and per project |
| Comments | Implemented |
| Notifications | Implemented |
| Activity logs | Implemented |
| File attachments | Implemented with file type and size validation |
| Search and filters | Implemented for projects and tasks |
| Deployment preparation | Implemented with Procfile, render.yaml, and DEPLOYMENT.md |

## Latest Feature Upgrade

This build includes the upgraded task-management feature set:

- Server-side Flask session management with no-cache protected pages.
- Assignee names on task cards and task reassignment by Admin.
- Assignee, status, priority, deadline and sorting filters.
- Full task edit modal for title, description, assignee, deadline, priority, status and labels.
- Task detail modal with assignee, creator, deadline, priority, status, labels, created/updated timestamps, checklist and task activity.
- Deadline badges: overdue, due today, due soon, future and complete.
- Visual task completion metrics and progress bars.
- Project-level settings: start date, deadline, priority, category, workflow status, visibility and tags.
- Pending invitation system with accept/reject flow.
- My Tasks page for member-specific workload tracking.
- Task checklist/subtasks with completion percentage.
- Improved comments with edit/delete support.
- Improved attachments with file icons, image thumbnails and file-size display.
