# PeopleOps HRMS Deployment

## Environment Variables

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/hrms_db?retryWrites=true&w=majority
DB_NAME=hrms_db
SECRET_KEY=replace-me
JWT_SECRET_KEY=replace-me
FLASK_ENV=production
```

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
gunicorn app:create_app()
```

## Health Check

After deployment, verify:

- `/login` renders.
- `/api/hrms/roles` returns `401` without authentication.
- Authenticated users can open `/dashboard`.
- Management Admin or HR leadership can open `/portal/users`.

## MongoDB Notes

Give the application read/write access to the HRMS database. The app creates non-destructive indexes for users, employees, attendance, payroll, performance reviews, leave requests, recruitment candidates, documents, HR cases, learning records, notifications, and activity logs.


## Config file note

`config.py` is not tracked in Git. For local development, copy `config.example.py` to `config.py`. For deployment, either create `config.py` from the example during setup or keep the same template in the deployment environment while storing real values as environment variables. Never commit `.env` or a real `config.py`.
