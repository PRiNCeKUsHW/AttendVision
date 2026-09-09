# AttendVision

AI attendance for classrooms, built with Django by Anuj.

- **Students** log in with FaceID from their webcam, register in one step (with an optional voice profile), enroll in subjects with a code or QR link, and see how many classes they've attended.
- **Teachers** register with a password, create subjects, share join codes / QR codes, take attendance from classroom photos (camera or upload) or a voice roll call, review the result, and browse every saved session.

## Run it locally

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/.

Want something to click on right away? `python manage.py seed_demo` creates the teacher `demo` / `demo123`, five students, two subjects and a few attendance sessions. The demo students have random embeddings, so register yourself through the student portal to try face or voice recognition.

Camera and microphone access needs a secure context: `localhost` works, but any other host must be served over HTTPS.

## Configuration

Everything is read from environment variables (see [.env.example](.env.example)).

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | insecure dev key | Django secret key. Set it in production. |
| `DEBUG` | `1` | Set to `0` in production. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames. |
| `DATABASE_URL` | SQLite `db.sqlite3` | Any `dj-database-url` URL, e.g. a Supabase Postgres connection string (install `psycopg[binary]`). |
| `TIME_ZONE` | `Asia/Kolkata` | Time zone used for displaying sessions. |
| `FACE_MATCH_THRESHOLD` | `0.6` | Max face-embedding distance to count as a match (lower is stricter). |
| `VOICE_MATCH_THRESHOLD` | `0.65` | Min voice similarity to count as a match (higher is stricter). |

## Project layout

```
attendvision/   Django project: settings, urls
accounts/    Teacher and Student models, teacher login, student FaceID login/registration
classroom/   Subject, Enrollment, AttendanceLog, dashboards, JSON endpoints
ml/          Face (dlib + SVM) and voice (Resemblyzer) pipelines, framework-free
templates/   Server-rendered pages; Alpine.js handles the interactive parts
static/      app.css (design tokens + components) and app.js (camera, recorder, API helper)
```

The browser converts recorded audio to 16 kHz WAV before uploading, so the server does not need ffmpeg.

## Tests

```powershell
python manage.py test
```

The tests patch the ML functions so they run without a camera, a GPU or model downloads.

## Admin

Create a superuser with `python manage.py createsuperuser` and open `/admin/` to inspect teachers, students, subjects and attendance logs.
