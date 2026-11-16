<<<<<<< HEAD
# PawConnect

**Stray Animal Rescue Coordination Platform with Adoption and Volunteer Management**

PawConnect connects the people who help street animals: citizens who report an animal in trouble, rescuers who
reach it, veterinarians who treat it, shelters that house it, volunteers who help with the daily work, and adopters
who give it a home. An administrator oversees everything.

It is a complete web application with a real MySQL database. You can sign in as any of the six roles, report an
animal, follow it from the first report to the adoption, and see the real numbers on every dashboard.

> **No API keys are needed.** Nothing in PawConnect uses a paid or keyed service. The maps use Leaflet with
> OpenStreetMap (free, no key). Bootstrap, Chart.js and the fonts come from public CDNs (no key), and you can
> download local copies if you want to work offline (see [Offline libraries](#offline-libraries-optional)).
> The only secret you ever type is your own MySQL password, and it stays in the `.env` file on your computer.

---

## Contents

1. [Features](#features)
2. [Technology](#technology)
3. [Quick start on Windows with VS Code](#quick-start-on-windows-with-vs-code)
4. [Sample accounts](#sample-accounts-development-only)
5. [A five-minute tour](#a-five-minute-tour)
6. [Project structure](#project-structure)
7. [Database](#database)
8. [Security](#security)
9. [Settings (.env)](#settings-env)
10. [Running the tests](#running-the-tests)
11. [Offline libraries (optional)](#offline-libraries-optional)
12. [Troubleshooting](#troubleshooting)
13. [Limitations](#limitations)
14. [Before real use](#before-real-use)
15. [Delivery notes](#delivery-notes)

---

## Features

| # | Module | What it does |
|---|--------|--------------|
| 1 | **Accounts and users** | Registration for adopters, volunteers, rescuers, veterinarians and shelters. Sign-in with lock-out after repeated wrong passwords. Profile, password change, forced change after an administrator reset. The administrator creates, suspends and reactivates accounts, resets passwords, and verifies rescuers, veterinarians and shelters. |
| 2 | **Rescue reporting** | A public form (no account needed) with a photo, address, urgency, and a map pin or the browser's location. Every report gets a unique ID such as `RPT-2026-00042`. Anyone can follow a report on the *Track* page with the ID plus the phone number or e-mail used. Signed-in users also get *My reports*. |
| 3 | **Rescue coordination** | The administrator assigns a verified rescuer. The rescuer accepts (the case becomes *In Progress*) or declines with a reason, then completes the rescue (*Rescued*, or *Closed* if the animal could not be found) and registers the rescued animal. Every step is recorded in a timeline. Declined cases can be reassigned. |
| 4 | **Animal management** | Profiles with photos, health and vaccination status, status history, unique IDs (`ANM-...`), search and filters, and a public *Adopt* page that lists only animals that are really available. |
| 5 | **Medical and vaccination records** | Veterinarians take animals under their care, add treatments and vaccinations, and the vaccination status updates by itself (*Not Vaccinated*, *Partially*, *Fully*, *Booster Due*). A critical case moves the animal to *Under Medical Treatment*. |
| 6 | **Adoption workflow** | Apply, review, approve or reject (a rejection needs a reason), then complete. Rules: only available animals, one active application per adopter and animal, only an approved application can be completed, only once. Completing is all-or-nothing: the record, the animal, the shelter place and competing applications change together. |
| 7 | **Volunteer management** | Volunteers apply and wait for approval. Administrators and rescuers create tasks with slots and deadlines. Approved volunteers accept tasks, finish them and see their history. |
| 8 | **Shelter management** | Shelter profile and public directory, capacity limits, admissions and discharges. A full shelter refuses new animals; only an administrator can override this, and must give a reason. |
| 9 | **Notifications** | Stored in the database, shown in a bell menu and a notification page, refreshed automatically every 30 seconds. They are in-app only (see [Limitations](#limitations)). |
| 10 | **Maps** | Leaflet and OpenStreetMap: a location picker on the report form, a map on each report, and a rescue overview map. If the map or its pictures cannot load, the page shows a short notice and everything else keeps working. |
| 11 | **Dashboards** | One per role, with real counts from the database and Chart.js charts. A new installation shows empty states instead of invented numbers. |
| 12 | **Search, filters and reports** | Filters and pagination on every list. The administrator's *Reports & Analytics* page, an activity log, a contact-message inbox, a broadcast notification tool, and CSV exports (reports, animals, adoptions, users, volunteers, medical records, vaccinations). |

The interface is a modern green, responsive design (it adapts to phones and tablets) with confirmation dialogs for
risky actions, loading indicators on buttons, empty states, and friendly error pages. There are about 70 pages in all.

### Roles

| Role | Joins by | Needs approval? | Main work |
|------|----------|-----------------|-----------|
| **Administrator** | Created by `init_db.py` or by another administrator | - | Everything: users, verifications, volunteer applications, assignments, reports and exports, activity log |
| **Rescuer** | Registration | Administrator **verifies** the account | Incoming reports, accept or decline cases, complete rescues, register animals, create volunteer tasks |
| **Volunteer** | Registration (volunteer page) | Administrator **approves** the application | Browse and accept tasks, task history |
| **Veterinarian** | Registration | Administrator **verifies** the account | Assigned animals, medical records, vaccinations |
| **Animal Shelter** | Registration | Administrator **verifies** the account | Shelter profile and capacity, admissions, adoption requests and records |
| **Adopter** | Registration | No | Browse animals, apply, follow applications, history |

A role is never read from a form. The register page offers only the roles that may register themselves, the volunteer
page always creates a volunteer, and every protected page checks the signed-in user's role on the server, so typing
an address by hand does not open a page that your role may not see.

---

## Technology

| Part | What is used |
|------|--------------|
| Front end | HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons, Jinja2 templates, Chart.js, Leaflet with OpenStreetMap |
| Back end | Python 3.10+, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF), Werkzeug password hashing, one blueprint per module |
| Database | MySQL 8 through SQLAlchemy and PyMySQL (the automated tests use an in-memory SQLite database) |
| Tools | pytest, ruff (optional), VS Code settings included |

---

## Quick start on Windows with VS Code

### 1. Install what you need (once)

| Program | Notes |
|---------|-------|
| **Python 3.10 or newer** | <https://www.python.org/downloads/>. In the installer, **tick "Add python.exe to PATH"**. |
| **MySQL 8** | <https://dev.mysql.com/downloads/installer/> (MySQL Installer for Windows). Choose *Server only* or *Developer Default*, keep port **3306**, and **remember the root password** you set. The Windows service is usually named `MySQL80`. |
| **Visual Studio Code** | <https://code.visualstudio.com/> with the **Python** extension from Microsoft. |

You also need an internet connection for the first `pip install`, and in the browser for the Bootstrap, Chart.js and
Leaflet files and the map pictures (or use the [offline copies](#offline-libraries-optional)).

### 2. Open the project

1. Extract `PawConnect_Project.zip`. You get a folder named `PawConnect`.
2. In VS Code choose **File > Open Folder...** and select the `PawConnect` folder.
3. Open a terminal with **Terminal > New Terminal** (or press `` Ctrl+` ``). It should be **PowerShell**
   and the path should end with `PawConnect`.

### 3. Create the virtual environment and install the packages

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

After activation the prompt starts with `(.venv)`.

**If PowerShell says "running scripts is disabled on this system"** (an execution-policy error), allow scripts for
this terminal window only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

This change disappears when you close the terminal. To make it permanent for your Windows user, run
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` instead. You can also avoid PowerShell by
using **Command Prompt** (`cmd`) and activating with `.venv\Scripts\activate.bat`.

Tell VS Code to use the environment: press `Ctrl+Shift+P`, choose **Python: Select Interpreter**, and pick the one
inside `.venv`. (The included `.vscode/settings.json` already points to it.)

### 4. Make sure MySQL is running

Press `Win+R`, type `services.msc`, find **MySQL80** and check that its status is *Running*. If it is not, right-click
it and choose *Start*. (In an Administrator terminal you can also run `net start MySQL80`.)

### 5. Create your `.env` settings file

```powershell
Copy-Item .env.example .env
code .env
```

Edit these lines and save:

```text
DB_USER=root
DB_PASSWORD=type-your-MySQL-password-here
SECRET_KEY=paste-a-long-random-text-here
```

Create a good `SECRET_KEY` with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

The `.env` file holds your passwords. It is listed in `.gitignore`: never share it or upload it.

### 6. Create the database

```powershell
python init_db.py --seed
```

This creates the database `pawconnect_db`, all 22 tables and the default administrator, and (because of `--seed`)
adds the [sample accounts](#sample-accounts-development-only) and demonstration data so every page has something
to show. For a clean, empty system use `python init_db.py` without `--seed`. Running it again is always safe: it only
adds what is missing. To wipe everything and start over: `python init_db.py --reset`.

### 7. Start the website

```powershell
python run.py
```

Open <http://127.0.0.1:5000/> in your browser. Stop the server with `Ctrl+C`.

### One-click alternative

Double-click **`start.bat`** (or run `start.bat seed` to include the sample data). It checks Python, creates `.venv`,
creates `.env` the first time and asks you to enter your MySQL password, installs the packages, prepares the
database and starts the site. Every step stops with a plain message if something is wrong; nothing is hidden.

In VS Code you can also press `F5` and choose **PawConnect (run.py)**.

### Optional: a separate MySQL user

Using `root` is fine for learning. For a tidier setup, create a user that can only touch this database. In MySQL
Workbench or the *MySQL 8.0 Command Line Client* run:

```sql
CREATE DATABASE IF NOT EXISTS pawconnect_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pawconnect'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON pawconnect_db.* TO 'pawconnect'@'localhost';
FLUSH PRIVILEGES;
```

Then set `DB_USER=pawconnect` and `DB_PASSWORD=choose-a-strong-password` in `.env` and run
`python init_db.py --seed --skip-create-database`.

### Optional: create the tables with the SQL file

`python init_db.py` is all you need. If you would rather create the tables yourself, run the SQL file in MySQL
Workbench (*File > Open SQL Script*, then the lightning button), or in **Command Prompt** (not PowerShell):

```text
mysql -u root -p < database\schema.sql
```

It creates empty tables only. Afterwards still run `python init_db.py` once to create the administrator account.

---

## Sample accounts (development only)

Created by `python init_db.py` (administrator) and `python init_db.py --seed` (everyone else). These are
**well-known development passwords: never use them on a public server.** Change them, or start without `--seed`.

| Role | E-mail | Password | State |
|------|--------|----------|-------|
| Administrator | `admin@pawconnect.test` | `Admin@12345` | Active |
| Rescuer | `rescuer@pawconnect.test` | `Paw@12345` | Verified |
| Rescuer | `rescuer2@pawconnect.test` | `Paw@12345` | Verified |
| Rescuer | `newrescuer@pawconnect.test` | `Paw@12345` | **Waiting for verification** |
| Volunteer | `volunteer@pawconnect.test` | `Paw@12345` | Approved |
| Volunteer | `volunteer2@pawconnect.test` | `Paw@12345` | Approved |
| Volunteer | `newvolunteer@pawconnect.test` | `Paw@12345` | **Waiting for approval** |
| Veterinarian | `vet@pawconnect.test` | `Paw@12345` | Verified |
| Animal Shelter | `shelter@pawconnect.test` | `Paw@12345` | Verified (Happy Tails Shelter) |
| Animal Shelter | `shelter2@pawconnect.test` | `Paw@12345` | Verified (Green Paws Sanctuary) |
| Adopter | `adopter@pawconnect.test` | `Paw@12345` | Active |
| Adopter | `adopter2@pawconnect.test` | `Paw@12345` | Active |

The two *waiting* accounts show what an unverified user sees (a status page) and give the administrator something to
approve under **Verifications** and **Volunteer Applications**. Change the administrator's e-mail, name and password
before real use with `ADMIN_EMAIL`, `ADMIN_NAME` and `ADMIN_PASSWORD` in `.env` (before the first `init_db.py`), or
change the password after signing in from **My Profile**.

---

## A five-minute tour

Run `python init_db.py --seed` first. Use a private window for each role, or sign out between steps.

1. **Report an animal as a visitor.** On the home page click *Report an animal in need*, fill in the form, click the
   map to pin the place, and submit. Note the report ID (for example `RPT-2026-00008`). Then use the *track the
   progress* link on the home page (or open <http://127.0.0.1:5000/track>) and look the report up with the ID and
   the phone number you typed.
2. **Assign a rescuer.** Sign in as `admin@pawconnect.test`, open **Rescue Reports**, open the new report and assign
   it to a rescuer.
3. **Do the rescue.** Sign in as `rescuer@pawconnect.test`, open **My Cases**, accept the case (it becomes *In
   Progress*), complete the rescue (it becomes *Rescued*), and register the animal.
4. **House and treat the animal.** Sign in as `shelter@pawconnect.test` and open **Admissions** to see capacity and
   admissions. Sign in as `vet@pawconnect.test` to take an animal under care in **Unassigned Animals** and add a
   medical record or vaccination.
5. **Adopt.** Sign in as `adopter@pawconnect.test`, open **Browse Animals**, and apply for an animal. Then, as the
   shelter, open **Adoption Requests**, approve the application and complete the adoption. The animal leaves the
   public list and the shelter's count goes down.
6. **See the numbers.** As the administrator open **Reports & Analytics** and download a CSV export.

---

## Project structure

```text
PawConnect/
├── run.py                 starts the website
├── init_db.py             creates the database, tables, default administrator (and sample data with --seed)
├── start.bat              one-click start for Windows
├── config.py              settings, read from .env
├── requirements.txt       packages needed to run the site
├── requirements-dev.txt   the same plus pytest, for the tests
├── .env.example           copy to .env and fill in
├── app/
│   ├── __init__.py        application factory, error pages, security headers
│   ├── constants.py       roles, statuses and limits in one place
│   ├── extensions.py      database, login manager, CSRF protection
│   ├── navigation.py      the sidebar menu of every role
│   ├── models/            the 22 database tables (SQLAlchemy models)
│   ├── forms/             validated forms (Flask-WTF)
│   ├── routes/            16 blueprints: the page and action handlers
│   ├── services/          business rules and database work (rescue, adoption, shelters, medical, ...)
│   ├── utils/             permission checks (RBAC), rate limiter, CSV safety, time helpers, MySQL help
│   ├── templates/         Jinja2 pages, layouts, macros and partials
│   └── static/            CSS, JavaScript (maps, charts, notifications), optional vendor/ libraries
├── database/
│   ├── schema.sql         plain SQL for all 22 tables (generated from the models)
│   └── seed_data.py       sample accounts and demonstration data
├── tests/                 automated tests
├── tools/                 check_project.py, make_schema.py, download_vendor.py, reset_password.py
└── uploads/               uploaded photos and documents (the folders are created automatically)
```

---

## Database

Database name: `pawconnect_db` (MySQL 8, InnoDB, `utf8mb4`). The tables are defined once, in `app/models/`.
`database/schema.sql` is generated from them (`python tools/make_schema.py`), and a test checks that the two never
drift apart.

| Group | Tables |
|-------|--------|
| Accounts | `users`, `user_profiles`, `volunteer_profiles`, `rescuer_profiles`, `veterinarian_profiles`, `shelter_profiles` |
| Rescue | `animal_reports`, `rescue_assignments`, `rescue_activities` |
| Animals | `animals`, `animal_images`, `animal_status_history`, `shelter_admissions` |
| Medical | `medical_records`, `vaccinations` |
| Volunteers | `volunteer_tasks`, `volunteer_task_assignments` |
| Adoption | `adoption_applications`, `adoption_records` |
| System | `notifications`, `audit_logs`, `contact_messages` |

Dates are stored in UTC and shown in the time zone given by `DISPLAY_UTC_OFFSET_MINUTES` (India, UTC+05:30, by
default).

---

## Security

* **Passwords** are never stored: only salted PBKDF2-SHA256 hashes (Werkzeug). A password needs 8 or more characters
  with at least one letter and one number.
* **Sign-in** gives the same message for a wrong password and an unknown e-mail, and locks an account for 15 minutes
  after 5 wrong passwords. A suspended or deactivated account loses its open sessions at once.
* **Role-based access** is enforced on the server for every protected page, plus checks on the individual record
  (for example an application is visible only to its adopter, the shelter that houses the animal, and the
  administrator). Unverified accounts reach only their status page.
* **CSRF tokens** protect every form; sign-out is a POST so a link cannot sign anyone out.
* **Open redirects** are blocked: the `next` address after sign-in must stay on this site.
* **Uploads** are checked for extension, real content and size, and stored under random server-chosen names.
  Verification documents are private (owner and administrators only). Public photos are served with
  `X-Content-Type-Options: nosniff`.
* **Database access** uses SQLAlchemy with bound parameters, and search text is escaped, so a typed `%` or `_` is
  searched for literally.
* **CSV exports** neutralise text that a spreadsheet could run as a formula (`=`, `+`, `-`, `@`).
* **Spam and guessing:** the public report form has a hidden bot trap, and the *Track* page slows down repeated wrong
  guesses (8 misses per 10 minutes per address).
* **Safe errors:** error pages never show SQL, file paths or stack traces. Database credentials exist only in `.env`.
* **Headers and cookies:** `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` on every response;
  session cookies are `HttpOnly` and `SameSite=Lax`.
* **Audit trail:** important actions (sign-ups, approvals, assignments, status changes, exports, resets) are written
  to an activity log that administrators can read.

---

## Settings (.env)

All settings are optional except your MySQL password. See `.env.example` for the full, commented file.

| Setting | Default | Meaning |
|---------|---------|---------|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | `127.0.0.1`, `3306`, `root`, *(empty)*, `pawconnect_db` | MySQL connection. Special characters in the password are fine. |
| `DATABASE_URL` | *(unset)* | One complete SQLAlchemy address instead of the five values above. |
| `SECRET_KEY` | a development value | Signs sessions and forms. **Set your own long random text.** Required when `FLASK_CONFIG=production`. |
| `FLASK_CONFIG` | `development` | `development` or `production`. |
| `FLASK_DEBUG` | `0` | `1` shows detailed errors and reloads on code changes (development only). |
| `FLASK_RUN_HOST`, `FLASK_RUN_PORT` | `127.0.0.1`, `5000` | Where the website listens. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | `admin@pawconnect.test`, `Admin@12345`, `PawConnect Administrator` | The administrator that `init_db.py` creates when none exists. |
| `CONTACT_EMAIL`, `CONTACT_PHONE`, `CONTACT_ADDRESS` | placeholder values | Shown in the footer and on the contact page. **Put your real details here.** |
| `DISPLAY_UTC_OFFSET_MINUTES` | `330` | Time zone for displayed times, in minutes from UTC. |
| `MAX_UPLOAD_MB` | `8` | Largest accepted upload. Photos may be PNG, JPG, GIF or WebP; documents PDF, PNG or JPG. |
| `SESSION_HOURS` | `8` | How long a sign-in lasts. |
| `USE_LOCAL_VENDOR` | `0` | `1` uses the [offline libraries](#offline-libraries-optional). |

---

## Running the tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

The tests use an in-memory SQLite database, so they never touch your MySQL data and need no setup. They cover:

* **Sign-in and accounts:** registration rules, duplicate e-mail, weak passwords, tampered role fields, lock-out,
  suspended accounts, safe redirects, forced password change.
* **Permissions:** every protected page is found automatically from the URL map and must send a signed-out visitor to
  sign-in and refuse the wrong role; record privacy; the verification and approval gates.
* **Rescue reporting:** guest reports, validation, photo upload safety, tracking, guess limiting.
* **Adoption rules:** applying, reviewing, the all-or-nothing completion, and the public list.
* **Workflows:** rescue coordination, volunteer tasks, shelter capacity and override, medical records, notifications.
* **Smoke tests:** every page opened as every role, on an empty database and on the sample data, plus a check that
  every link, file and form on those pages leads somewhere, and that CSV exports are safe.
* **Pure unit tests** of the business rules, the SQL schema, CSV safety, the rate limiter and the MySQL error help.

Two helper programs need no database and no extra packages:

```powershell
python tools/check_project.py     # cross-checks routes, links, templates, forms and model fields
python tools/make_schema.py --check   # confirms schema.sql matches the models
```

If you ever lose the administrator password, set a new one from the command line (the website sends no e-mails, so
there is no "forgot password" link):

```powershell
python tools/reset_password.py admin@pawconnect.test
```

Other accounts can be reset by an administrator on the **Users** page: a one-time temporary password is shown once,
and the person must choose a new one at the next sign-in.

An optional command creates a notification for every vaccination that is due soon (run it daily if you like):

```powershell
flask --app app:create_app send-vaccination-reminders
```

---

## Offline libraries (optional)

By default the pages load Bootstrap, Bootstrap Icons, Chart.js and Leaflet from public CDNs. To use local copies
(for example on a slow connection):

```powershell
python tools/download_vendor.py
```

Then put `USE_LOCAL_VENDOR=1` in `.env` and restart the site. The map pictures (OpenStreetMap tiles) always need
the internet; without it the map areas show a short notice and every form still works.

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| `'python' is not recognized` | Install Python from python.org and tick *Add python.exe to PATH*, then open a new terminal. Or try `py -3` instead of `python`. |
| `running scripts is disabled on this system` when activating | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again (see [step 3](#3-create-the-virtual-environment-and-install-the-packages)). Or use Command Prompt and `.venv\Scripts\activate.bat`. |
| `ModuleNotFoundError: No module named 'flask_sqlalchemy'` (or another package) | The virtual environment is not active or the packages are not installed. Activate it (the prompt shows `(.venv)`) and run `pip install -r requirements.txt`. In VS Code select the `.venv` interpreter. |
| `pip install` fails | Check your internet connection, proxy or firewall. Try `python -m pip install --upgrade pip` first. |
| **MySQL error 2003** (or 2002): *Can't connect* | MySQL is not running or the host or port is wrong. Start the `MySQL80` service ([step 4](#4-make-sure-mysql-is-running)) and check `DB_HOST` and `DB_PORT`. |
| **MySQL error 1045**: *Access denied* | `DB_USER` or `DB_PASSWORD` in `.env` is wrong. Test the same login in MySQL Workbench. |
| **MySQL error 1049**: *Unknown database* | Run `python init_db.py` (it creates the database). |
| **MySQL error 1044** or **1142**: *denied* for the database | The MySQL user may not create or change tables. Use `root`, or grant privileges as in [Optional: a separate MySQL user](#optional-a-separate-mysql-user). |
| `PawConnect cannot start yet. The database has no PawConnect tables yet.` | Run `python init_db.py`. |
| `RuntimeError: 'cryptography' package is required` (MySQL 8 sign-in) | `pip install cryptography` (it is already in `requirements.txt`; this means the install did not finish). |
| *Port 5000 is already in use* | Put `FLASK_RUN_PORT=5001` in `.env` and open <http://127.0.0.1:5001/>. |
| Pages look unstyled or icons are missing | The browser could not reach the CDNs. Check the internet connection, or use the [offline libraries](#offline-libraries-optional). |
| The map is grey or says it could not load | OpenStreetMap pictures need the internet. The notice on the page says so; everything else still works. |
| *Your form session expired* | Reload the page and submit again (forms expire after 8 hours, or when `SECRET_KEY` changes). |
| *Too many failed sign-in attempts* | Wait 15 minutes, or have an administrator reset the password on the **Users** page. |
| A photo is refused | Use PNG, JPG, GIF or WebP up to 8 MB (documents: PDF, PNG or JPG). The file must really be a picture. |
| I forgot the administrator password | `python tools/reset_password.py admin@pawconnect.test` |
| I want to start again with empty tables | `python init_db.py --reset` (deletes all PawConnect data after asking), then `python init_db.py --seed` if you want the sample data. |

---

## Limitations

* **Notifications are in-app only.** They appear in the bell and on the notification page. PawConnect does **not**
  send e-mails or text messages, so it never claims to.
* **No live GPS tracking.** Locations come from the pin the reporter places or the browser location they allow.
* **The rate limiter lives in memory.** Its counters reset when the server restarts and are not shared between
  several server processes.
* **Uploaded files are kept on the server's disk** in `uploads/` (verification documents are private, but they are
  not encrypted at rest).
* **MariaDB and XAMPP are not tested.** Use MySQL 8.
* **The built-in server is for development.** See the next section before putting the site on the internet.

---

## Before real use

PawConnect is built to run on your own computer for a project, demonstration or pilot. Before you publish it:

1. Do not run `init_db.py --seed`, and delete the sample accounts if you did.
2. Change the administrator password and set real `CONTACT_*` values.
3. Set a long random `SECRET_KEY` and `FLASK_CONFIG=production` (the site refuses to start in production without
   a key). Production mode also turns on secure cookies, so it needs **HTTPS**.
4. Use a production web server instead of `python run.py`, for example `waitress` on Windows
   (`pip install waitress`, then `waitress-serve --call app:create_app`) or `gunicorn` on Linux, behind HTTPS.
5. Back up the MySQL database and the `uploads/` folder regularly.

OpenStreetMap's public map pictures are meant for light use. For a busy public site choose a tile provider whose
terms fit your traffic.

---

## Delivery notes

*(Delete this section before you submit the project.)*

This project was written in a build environment where the Python packages (Flask-SQLAlchemy, Flask-Login, Flask-WTF,
PyMySQL) and a MySQL server could not be installed. So the checks were done in two ways.

**Run and passing in the build environment**

* every Python file compiles, and `ruff` reports no problems;
* `python tools/check_project.py`: routes, links, templates, macros, forms, CSRF tokens, route permissions, model
  attributes and service calls cross-check with no problems;
* `python tools/make_schema.py --check`: `schema.sql` matches the 22 models;
* 84 unit tests of the business rules, the SQL file, CSV safety, the rate limiter, the MySQL error help and the
  offline-libraries downloader.

**Written and checked by reading, not yet run**

* the database layer against a live MySQL server, the pages against real data, and `init_db.py` and the seed script;
* the integration tests (sign-in, permissions, rescue reporting, adoption, workflows, and the smoke test of every
  page). They skip themselves when the packages are missing.

Please run `python -m pytest` once after you install the packages, then click through the
[tour](#a-five-minute-tour). If a test or page fails, the message names the page or the rule, which makes a fix quick.
=======
# Stray-Animal-Final-Code
Stray Animal Rescue, Adoption and Management System
>>>>>>> origin/main
