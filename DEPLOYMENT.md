# Deployment Guide

## 1. Prepare Environment Variables

Set these variables in your deployment platform:

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/team_task_db?retryWrites=true&w=majority
JWT_SECRET_KEY=your-long-random-jwt-secret
SECRET_KEY=your-long-random-flask-secret
FLASK_ENV=production
```

Do not commit `.env` to GitHub.

## 2. MongoDB Atlas Checklist

1. Create a dedicated database user.
2. Give only read/write access to the project database.
3. Add the deployment platform IP in Network Access.
4. If the platform has no fixed IP, use `0.0.0.0/0` only if required.
5. Rotate the password if it is ever exposed.

## 3. Render Deployment

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:create_app()
```

## 4. Local Run

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

## 5. Main Routes

- `/`
- `/signup`
- `/login`
- `/dashboard`
- `/projects`
- `/profile`
- `/notifications`
- `/project/<project_id>/tasks`
- `/project/<project_id>/manage`
- `/project/<project_id>/analytics`
