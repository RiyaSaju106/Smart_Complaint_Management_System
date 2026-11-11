# Smart Complaint Management System (SCMS)

A web application for a residential community. Residents submit and track complaints,
administrators assign them and manage users, and maintenance staff process them through to
resolution. Residents can then leave feedback.

**Course:** UE24CS341A – Software Engineering · **Team 9** · **Methodology:** Agile (2 sprints)

| Member | SRN |
|---|---|
| Riya Saju Vithayathil (Team Lead) | PES1UG24CS378 |
| Ritu Ranganath Kashyap | PES1UG24CS377 |
| Rohan Suresh | PES1UG24CS383 |
| Rohit Krishna R | PES1UG24CS385 |

## What it does

| Role | Can do |
|---|---|
| **Resident** | Register, log in, submit a complaint (with an optional attachment) and get a unique Complaint ID, view their complaints and status history, receive notifications, give feedback after resolution |
| **Maintenance staff** | See complaints assigned to them, update status (In Progress, Resolved), add remarks and resolution details |
| **Administrator** | Manage categories and departments, assign and reassign complaints, manage resident and staff accounts, view the dashboard and reports |

Complaint lifecycle: Submitted → Assigned → In Progress → Resolved → Closed.

## Tech stack

Python 3 · Flask · MySQL 8 · PyMySQL · Jinja2 templates · plain HTML/CSS/JavaScript · pytest · GitHub Actions

## Setup

1. **Prerequisites:** Python 3.9+ and MySQL 8.0.16+ running locally.
2. **Create the databases and a database user** (once, as MySQL root). The full SQL is in
   [`db/README.md`](db/README.md).
3. **Install dependencies**

   ```bash
   python -m venv .venv
   # Windows PowerShell:  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure** — copy `.env.example` to `.env` and fill in your values (never commit `.env`).
   The demo-account variables (`DEMO_*`) are explained in `db/README.md`.
5. **Build and seed the database**

   ```bash
   python -m db.apply_schema
   python -m db.seed_reference_data
   python -m db.seed_demo_users
   ```

6. **Run**

   ```bash
   python run.py
   ```

   Open <http://127.0.0.1:5000>. Log in with the demo accounts created by the seed script
   (resident and administrator from your `.env`; staff: `staff.<department>@example.com`, e.g.
   `staff.plumbing@example.com`, using `DEMO_STAFF_PASSWORD`).

## Running the tests

Tests run against a separate database (`TEST_DB_NAME` in `.env`), never the app database.

```bash
python -m pytest tests --import-mode=importlib -q
```

Test reports (JUnit XML and coverage) are in `docs/reports/`. The same suite runs on every push and
pull request through GitHub Actions.

## Project structure

```
app/             Flask application: auth, users, complaints, categories and assignment, tracking,
                 notifications, feedback, reports, admin_users, ui (pages), templates, static
process/         Complaint processing and status module, with the staff pages
db/              MySQL schema, seed scripts, connection and password helpers
tests/           pytest suites per module
Documentation/   SRS, SAD, STP, use case diagram, API contracts, deviations
docs/reports/    Generated test and coverage reports
demo/            Sprint demo videos
```

## Documentation

- Requirements: [`Documentation/SCMS_SRS_v1.1.pdf`](Documentation/SCMS_SRS_v1.1.pdf) and
  [`Documentation/SCMS_Use_Case_Diagram.pdf`](Documentation/SCMS_Use_Case_Diagram.pdf)
- Design: [`Documentation/SAD/SCMS_Final_SAD.pdf`](Documentation/SAD/SCMS_Final_SAD.pdf)
- Test plan: [`Documentation/STP/SCMS_Final_STP.pdf`](Documentation/STP/SCMS_Final_STP.pdf)
- API contracts: [`Documentation/API/`](Documentation/API/)
- Deviations from the original documents: [`Documentation/DEVIATIONS.md`](Documentation/DEVIATIONS.md)

## Known limitations

See the "Known limitations" section of [`Documentation/DEVIATIONS.md`](Documentation/DEVIATIONS.md).