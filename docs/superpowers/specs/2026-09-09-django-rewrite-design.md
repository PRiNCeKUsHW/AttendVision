# AttendVision Django Rewrite — Design

Date: 2026-09-09

## Goal

Replace the Streamlit prototype with a Django web app that keeps every
existing behaviour and adds a polished, interactive front end.

## Behaviour to preserve

**Home** — choose Student Portal or Teacher Portal.

**Teacher**
- Register (username, name, password, confirm) and log in with password.
- Dashboard with three tabs: Take Attendance, Manage Subjects, Attendance Records.
- Take Attendance: pick a subject, add classroom photos (camera or upload),
  run face analysis, review a results table (name, id, source photo, status),
  confirm to save or discard. Voice attendance: record classroom audio,
  analyse against enrolled students' voice profiles, review, confirm/discard.
- Manage Subjects: create subject (code, name, section); cards show student
  count and class count; share a subject via join link + QR code.
- Attendance Records: one row per session (time, subject, code, present/total),
  newest first, with expandable per-student detail.

**Student**
- Log in with FaceID (webcam). No face / multiple faces / unknown face are
  reported. Unknown face opens registration: name plus optional voice sample.
- Dashboard: enrolled subject cards with total sessions and attended count,
  enroll by subject code, unenroll.
- Join link `/join/<code>/` prompts a logged-in student to enroll; otherwise it
  routes through student login first.

## Architecture

```
manage.py
attendvision/            settings, urls, wsgi
accounts/             Teacher, Student models; teacher auth; student FaceID auth
classroom/            Subject, Enrollment, AttendanceLog; dashboards; attendance APIs
ml/                   face.py, voice.py — pure Python, no Django/Streamlit imports
templates/            base.html + per-page templates
static/               css/app.css, js/*.js
```

- **Database**: Django ORM. SQLite by default; `DATABASE_URL` switches to
  Postgres (e.g. a Supabase connection string). Embeddings stored as JSON.
- **Auth**: session based. `teacher_id` / `student_id` stored in the Django
  session; small decorators guard views. Teacher passwords use Django hashers.
- **Interactivity**: Alpine.js (cdnjs) for tabs, modals, photo gallery,
  camera and recorder state; `fetch` to JSON endpoints. No build step.
- **Photos** live in the browser until analysis; the analyse endpoint accepts
  many images in one multipart POST and returns the results table. Confirm
  posts the logs to a save endpoint.
- **Audio** is recorded with MediaRecorder, decoded with Web Audio, and
  re-encoded as 16 kHz mono WAV client-side so the server needs no ffmpeg.
- **ML caching**: dlib models and the voice encoder load once per process.
  The face classifier is cached and rebuilt when the set of students changes.

## Error handling

- JSON endpoints return `{ok: false, error: "..."}` with 400/404 for user
  errors; the UI shows them in a toast.
- Server-rendered forms show inline errors and preserve input.

## Testing

Django `TestCase`s for models, auth flows, enrollment, attendance grouping and
the JSON endpoints, with the ML functions patched out. ML code is exercised
manually through the running app.

## Out of scope

Migrating existing Supabase rows; deployment configuration beyond env vars.
