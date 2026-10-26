# skipera
<img width="96" height="96" alt="image" src="https://github.com/user-attachments/assets/8cf9428c-ef58-45b2-8fff-184ae353a890" />

Automated toolset to facilitate completing Coursera (https://www.coursera.org/) courses, videos, readings, assessments, and downloading earned certificates.

---

## Table of Contents
- [Why?](#why)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Cookies (Automatic & Manual)](#cookies-automatic--manual)
  - [LLM API Keys (Groq, Gemini, Perplexity)](#llm-api-keys)
- [End-to-End Workflow](#end-to-end-workflow)
- [Scripts & Command Reference](#scripts--command-reference)
  - [1. Core CLI (`skipera` / `skipera.main`)](#1-core-cli-skipera--skiperamain)
  - [2. Automated Enrollment (`enroll.py`)](#2-automated-enrollment-enrollpy)
  - [3. Batch Course Runner (`run-for-courses.py`)](#3-batch-course-runner-run-for-coursespy)
  - [4. Certificate Downloader (`certificate-downloader.py`)](#4-certificate-downloader-certificate-downloaderpy)
- [Troubleshooting & Tips](#troubleshooting--tips)

---

## Why?
Skipera assists in automatically skipping irrelevant MOOC courses made mandatory by universities as credit fillers. Progress and completions are submitted directly to Coursera's APIs, allowing learners to fulfill credit requirements without wasting hundreds of hours on busywork.

## How It Works
* **Videos & Lectures**: Automatically checks whether a video is skippable; if non-skippable, simulates playback tracking progress (`onDemandVideoProgresses.v1`) and triggers the completed event.
* **Reading & Supplements**: Direct submission to `onDemandSupplementCompletions.v1`.
* **Interactive Coach Items**: Automatically queries session membership branch IDs and dispatches `UpdateCoachItemProgress` GraphQL mutations.
* **Ungraded Widgets & LTI**: Marks interactive sessions and LTI tool launches complete.
* **Graded Quizzes & Discussions**: Uses LLM APIs with schema-constrained JSON outputs to solve single-choice, multiple-choice, numerical, mathematical, exact match, and reflective text questions. Includes an automated retry loop with Coursera grader feedback to correct incorrect answers.
* **Certificates**: Automatically queries Coursera's GraphQL certificate records and downloads official vector PDF certificates directly from Coursera's CDN.

---

## Installation

```bash
git clone https://github.com/serv0id/skipera
cd skipera
pip install -r requirements.txt
pip install -e .
```

If using [`uv`](https://github.com/astral-sh/uv):
```bash
uv pip install -r requirements.txt
uv pip install -e .
```

*Note: For browser-based auto-enrollment, Playwright is used:*
```bash
playwright install
```

---

## Configuration

On first run, skipera creates a configuration file at `~/.skipera/config.json`.

### Cookies (Automatic & Manual)
If you are logged into Coursera in **Chrome**, **Firefox**, or **Edge**, skipera automatically extracts active authentication cookies (`CAUTH`, `CSRF3-Token`, etc.). Expired cookies are also re-fetched automatically.

> **Windows Note:** Ensure your browser is closed if cookie database locking errors occur. On Windows, if elevated database access is required, a UAC prompt may appear to read cookies securely.

If you prefer manual configuration, edit `~/.skipera/config.json`:
```json
{
  "cookies": {
    "CAUTH": "...",
    "CSRF3-Token": "...",
    "__204u": "..."
  },
  "perplexity_api_key": "",
  "gemini_api_key": "",
  "groq_api_key": "",
  "perplexity_model": "sonar-pro",
  "gemini_model": "gemini-3.1-flash-lite",
  "groq_model": "openai/gpt-oss-120b"
}
```

### LLM API Keys
To enable automatic solving of graded assessments and discussion prompts, configure at least one LLM provider:
1. **Groq (Recommended - High speed & generous rate limits)**:
   Add your key to `~/.skipera/config.json` or create a `.env` file in the project root:
   ```bash
   GROQ_API_KEYS="gsk_key1,gsk_key2,gsk_key3"
   ```
   *Multiple comma-separated keys enable automatic round-robin fallback when rate limits are reached.*
2. **Google Gemini**: Add `gemini_api_key` to `config.json`.
3. **Perplexity**: Add `perplexity_api_key` to `config.json`.

---

## End-to-End Workflow

A complete pipeline from enrollment to certificate downloads:

```text
Step 1: Enumerate or Enroll Courses
  ├── List enrolled:        python -m skipera.main --list
  └── Auto-enroll:          python enroll.py [course-slug]

Step 2: Automate Completion
  ├── Single Course:        python -m skipera.main <course-slug> --llm
  └── Batch Runner:         python run-for-courses.py --llm

Step 3: Download All Earned Certificates
  └── Download PDFs:        python certificate-downloader.py
```

---

## Scripts & Command Reference

### 1. Core CLI (`skipera` / `skipera.main`)

The main engine that interacts with Coursera course materials, videos, and quizzes.

> **Windows Tip:** Run via `python -m skipera.main` to bypass Windows Application Control policies that may block `.exe` console scripts.

#### Complete a Single Course (Videos + Readings + Coach)
```bash
python -m skipera.main <course-slug>
# or
skipera <course-slug>
```

#### Complete Course with LLM Assessment & Quiz Solving
```bash
python -m skipera.main <course-slug> --llm
```

#### List Enrolled Courses & Calculate Progress
Fetches all active course memberships, calculates percentage completed for each, prints a formatted table, and saves the list to `output.list`:
```bash
python -m skipera.main --list
```

#### CLI Options:
| Flag | Description |
| :--- | :--- |
| `SLUG` | Course slug from the Coursera URL (e.g. `introduction-to-data-analytics`). |
| `--llm` | Enables LLM-powered solving of graded assessments and discussion prompts. |
| `--list` | Lists all enrolled courses with progress breakdown and writes `output.list`. |
| `--help` | Displays help message and CLI options. |

---

### 2. Automated Enrollment (`enroll.py`)

A Playwright-driven browser automation script that injects your authenticated session cookies into Microsoft Edge or Google Chrome to enroll in courses or guided projects automatically.

#### Features:
* Handles standard courses, enterprise/degree portals (e.g., NMIMS, university SSO).
* Automatically selects **"Enroll for free"**, **"Start Guided Project"**, or the free **"Audit"** option in specialization modals.
* Verifies if already enrolled ("Go to Course" / "Resume") and skips redundant enrollment actions.

#### Commands:
```bash
# 1. Enroll in a single course
python enroll.py <course-slug>
# Example:
python enroll.py build-an-ai-travel-agent-app-with-openai

# 2. Batch-enroll all courses listed in 'courses' file
python enroll.py

# 3. Batch-enroll from a custom slug file
python enroll.py --file my_courses.txt
# or:
python enroll.py -f my_courses.txt

# 4. Custom hydration delay for slow networks (default: 10 seconds)
python enroll.py <course-slug> --wait 15

# 5. Run silently in headless mode (background)
python enroll.py --headless
```

#### CLI Options:
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `slug` | | `None` | Optional single course slug. If omitted, reads from `--file`. |
| `--file` | `-f` | `courses` | Path to text file containing course slugs (one per line). |
| `--wait` | `-w` | `10` | Seconds to wait for Coursera React hydration before locating buttons. |
| `--headless` | | `False` | Run browser in background without showing the UI window. |

---

### 3. Batch Course Runner (`run-for-courses.py`)

A batch supervisor that reads a list of course slugs, checks real-time completion status against Coursera's progress API, skips courses that are already 100% completed, and runs `skipera` sequentially on pending courses.

#### Commands:
```bash
# Run batch with LLM solving on all courses in 'courses'
python run-for-courses.py --llm

# Run batch on a custom list of courses
python run-for-courses.py --file path/to/my_courses.txt --llm

# Force run even if course is detected as 100% completed
python run-for-courses.py --force --llm

# Save run report to a custom file (default: courses_summary.txt)
python run-for-courses.py --summary-file my_report.txt --llm
```

#### Summary Report (`courses_summary.txt`):
After execution, a report table is generated:
```
================================================================================
                              COURSES RUN SUMMARY                               
================================================================================
  #  Course Slug                             Status        Progress     Details
--------------------------------------------------------------------------------
  1  data-warehousing-business-intelligence  ALREADY DONE  30/30 (100%) Skipped: Already 100%
  2  descriptive-statistics-analyze-data-r   ALREADY DONE  4/4 (100%)   Skipped: Already 100%
  3  agentic-ai                              ALREADY DONE  25/25 (100%) Skipped: Already 100%
--------------------------------------------------------------------------------
OVERALL STATISTICS:
  - Total Courses in List      : 12
  - Already Completed (Skipped): 9
  - Newly Completed (This Run) : 0
  - Incomplete / In-Progress   : 3
================================================================================
```

#### CLI Options:
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--file` | `-f` | `courses` | Path to the text file containing course slugs. |
| `--llm` | | `False` | Passes `--llm` flag to `skipera` for automated quiz solving. |
| `--force` | | `False` | Runs `skipera` even if the course is already at 100% completion. |
| `--summary-file` | `-s` | `courses_summary.txt` | Destination file path for the summary report. |

---

### 4. Certificate Downloader (`certificate-downloader.py`)

High-speed direct PDF downloader that queries Coursera's GraphQL certificate records and downloads official vector PDF certificates directly into the `certificates/` directory.

#### Features:
* Queries all awarded **Course** and **Specialization** certificates.
* Multi-threaded concurrent downloads.
* Idempotent: validates `%PDF-` file integrity and skips already downloaded certificates.
* Automatically creates `certificates/certificates_manifest.json` indexing all credentials with grades, verification codes, URLs, and local paths.

#### Commands:
```bash
# 1. Download all earned certificates to 'certificates/'
python certificate-downloader.py

# 2. Re-download / update existing certificates
python certificate-downloader.py --force

# 3. Save certificates to a custom folder
python certificate-downloader.py --output-dir my_certificates/

# 4. Download certificate for a specific course slug
python certificate-downloader.py --slug data-warehousing-business-intelligence

# 5. Download certificate by Coursera verification code
python certificate-downloader.py --code KWI2G9CGIW5J

# 6. Adjust concurrent download threads (default: 4)
python certificate-downloader.py --workers 6
```

#### CLI Options:
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--output-dir` | `-o` | `certificates` | Folder to save downloaded certificate PDFs. |
| `--force` | `-f` | `False` | Overwrite/re-download existing certificate files. |
| `--slug` | `-s` | `None` | Download certificate only for this course slug. |
| `--code` | `-c` | `None` | Download certificate only for this verification code. |
| `--workers` | `-w` | `4` | Number of concurrent download worker threads. |

---

## Troubleshooting & Tips

* **Cookie Expiration**: If you receive `Cookies are invalid`, simply log into [Coursera](https://www.coursera.org/) in your browser, close the browser window, and rerun the script. Skipera will auto-refresh the session.
* **Locked Modules / Prerequisites**: Some courses lock future modules until previous assignments are graded or deadlines pass. Incomplete items are reported in `courses_summary.txt`.
* **Grader Feedback Review**: When an assessment fails to meet the passing grade, Skipera inspects the previous attempt's feedback and incorrect answer review page (saved to `wrong_answers.txt`) to feed corrective context to the LLM on the next attempt.
* **Rate Limits**: If using Groq and you hit rate limits, provide multiple API keys in `.env` as `GROQ_API_KEYS="key1,key2,key3"`. Skipera will automatically rotate through keys.
