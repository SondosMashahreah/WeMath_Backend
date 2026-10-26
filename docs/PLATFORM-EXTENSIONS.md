# WE MATH — Teacher and public platform extensions

Incremental extension on top of the existing family/student platform patch. No changes to the existing authentication, family, student, learning, curriculum, or STEAM handlers. `app/main.py` installs a separate router and exception type; `alembic/env.py` registers the new models.

## Migration

Expected existing revision: `wemath_family_20261025`.
New revision: `wemath_platform_20261026`.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Back up the existing database first. Do not rerun SQL installation scripts, reset tables, stamp revisions, or replace the private `.env`. The new migration adds only three tables:

- `platform_teacher_profiles`: school and an independent teacher session version.
- `platform_entries`: public content and private teacher resources.
- `platform_teacher_documents`: teacher-owned lesson plans and assessments, with optimistic version guards and reversible archiving.

It ensures the `teacher` role exists and creates profiles for existing teacher-role users. It does not alter existing users, memberships, student profiles, family relationships, progress, or textbook rows. Seeds 27 explicitly marked demo entries once. Downgrade drops the three extension tables (and their new content); it leaves users and roles intact.

## API

All endpoints are under `/api/platform`.

| Method / path | Use |
| --- | --- |
| GET `/sections` | Public section categories |
| GET `/entries` | Published public entries; `section`, `category`, literal `q`, `archived`, `offset`, `limit`, optional `month=YYYY-MM` |
| GET `/entries/{id}` | Published public detail |
| GET `/guest/catalog` | Books and one sample lesson per book; no writes |
| POST `/assistant` | `{message, grade?}`; bounded arithmetic or curriculum title search |
| POST `/teachers/register` | `{username, password, full_name, school?}`; teacher role only |
| POST `/teachers/login` | `{username, password}` |
| GET `/teachers/me` | Teacher profile |
| POST `/teachers/logout` | Revoke teacher sessions only |
| GET `/teachers/library` | Teacher-only resources, search/category/pagination |
| GET / POST `/teachers/documents` | List or create own plans/assessments |
| GET / PUT `/teachers/documents/{id}` | Read or update own document; PUT requires current `version` |
| PATCH `/teachers/documents/{id}/archive` | `{archived, version}`; reversible |

Private endpoints verify signature, expiry, `aud=wemath-teachers`, role, active user, global user token version, and independent teacher session version. Logout increments only the teacher profile version, so even a multi-role user's family sessions remain intact. Role membership is checked against the database. Ownership is enforced on every document operation. Concurrent stale edits return 409. Archive restores preserve content. Plans validate grade/book/lesson membership; assessments validate answer choices and answer indexes.

Guest/public requests never create a profile or progress row. There is no public content-publishing endpoint.

## Replacing demo content

Prepare a UTF-8 JSON array using the schema below, then validate and import with the operator CLI. It transactionally upserts by `id`. It does not change any row not present in the input. Reuse an existing demo ID to replace that card, or set `published=false` to hide it. Do not edit migration seed files after deployment.

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_content content-reviewed.json --check
.\.venv\Scripts\python.exe -m scripts.platform_content content-reviewed.json
```

Required fields: `id`, `section`, `category`, `title`, `summary`, `body`. Optional: HTTPS `source_url`, ISO `event_date`, `archived`, `published`, `is_demo`, `activity`. Review all real content and explicitly set `is_demo=false` only after verification. The allowed category mapping is in `app/platform/domain.py`.

```json
[
  {
    "id": "demo-workshops-01",
    "section": "workshops",
    "category": "scientific",
    "title": "نموذج ورشة في الرياضيات",
    "summary": "وصف تجريبي يحتاج مراجعة قبل النشر الحقيقي.",
    "body": "أضف الأهداف والخطوات والمكان والمنظم والتاريخ بعد التحقق منها.",
    "source_url": null,
    "event_date": null,
    "published": true,
    "archived": false,
    "is_demo": true
  }
]
```

Algo does not call an LLM or retrieve lesson PDF contents. It evaluates only a bounded arithmetic AST (no `eval`) or queries curriculum lesson titles, returning existing book sources. No invented explanation of a PDF or false claim of full AI capability.

## Validation

```powershell
# Test-only dependencies; not required to run the app
.\.venv\Scripts\python.exe -m pip install pytest httpx
.\.venv\Scripts\python.exe -m pytest -q tests/test_platform_expansion.py
```

Ten API tests cover authentication/audience separation, logout isolation, duplicate usernames, ownership, curriculum constraints, optimistic edits, archive/restore, assessment validation, search/pagination/calendar, safe assistant behavior and read-only guest access. Additional release QA ran real Alembic migrations and API/React interactions on a disposable PostgreSQL-compatible PGlite instance, checking unchanged protected fixture rows and all 28 books / 126 units / 587 lessons. That fixture models the previously delivered family revision; it does not replace or re-test the user's actual family implementation. Real browser visual/print QA and production load testing remain deployment checks.
