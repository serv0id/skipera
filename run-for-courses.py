import argparse
import json
import subprocess
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".skipera" / "config.json"
DEFAULT_COURSES_FILE = "courses"
DEFAULT_SUMMARY_FILE = "courses_summary.txt"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "x-coursera-application": "ondemand",
    "x-coursera-version": "3bfd497de04ae0fef167b747fd85a6fbc8fb55df",
    "x-requested-with": "XMLHttpRequest",
}


def get_coursera_session_data():
    """
    Initializes an HTTP client with saved Coursera cookies and retrieves user ID
    along with active course memberships, matching `skipera --list` logic.
    Returns (client, user_id, enrolled_courses_dict).
    """
    try:
        import httpx
    except ImportError:
        return None, None, {}

    if not CONFIG_FILE.is_file():
        return None, None, {}

    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        cookies = cfg.get("cookies", {})
        if not cookies:
            return None, None, {}

        client = httpx.Client(
            cookies=cookies,
            headers=HEADERS,
            timeout=25.0,
            verify=False,
            follow_redirects=True,
        )

        # Query memberships exactly like `skipera --list`
        mem_url = (
            "https://www.coursera.org/api/memberships.v1"
            "?includes=courseId,courses.v1&q=me&showHidden=true&filter=current"
        )
        r = client.get(mem_url)
        if r.status_code != 200:
            return client, None, {}

        data = r.json()
        elements = data.get("elements", [])
        if not elements:
            return client, None, {}

        user_id = str(elements[0].get("userId", ""))
        courses_list = data.get("linked", {}).get("courses.v1", [])
        enrolled_courses = {c["slug"]: c for c in courses_list if "slug" in c}
        return client, user_id, enrolled_courses
    except Exception:
        return None, None, {}


def check_course_status(client, user_id: str, enrolled_courses: dict, slug: str) -> dict:
    """
    Checks course status and progress using the same logic as `skipera --list`.
    Returns dict:
      {
        'status': 'completed' | 'incomplete' | 'not_enrolled' | 'unknown',
        'completed': int,
        'total': int,
        'percentage': float,
        'reason': str,
        'name': str
      }
    """
    course_name = enrolled_courses.get(slug, {}).get("name", slug)

    if not client or not user_id:
        return {
            "status": "unknown",
            "completed": 0,
            "total": 0,
            "percentage": 0.0,
            "reason": "No active Coursera session",
            "name": course_name,
        }

    try:
        course_id = None
        if slug in enrolled_courses:
            course_id = enrolled_courses[slug].get("id")

        # Get course materials and total items
        mat_url = (
            f"https://www.coursera.org/api/onDemandCourseMaterials.v2/"
            f"?q=slug&slug={slug}&includes=items,gradingParameters"
            f"&fields=onDemandGradingParameters.v1(gradedAssignmentGroups)"
        )
        mr = client.get(mat_url)
        if mr.status_code != 200:
            return {
                "status": "unknown",
                "completed": 0,
                "total": 0,
                "percentage": 0.0,
                "reason": f"Could not load materials for slug '{slug}'",
                "name": course_name,
            }

        mdata = mr.json()
        elements = mdata.get("elements", [])
        if not elements:
            return {
                "status": "unknown",
                "completed": 0,
                "total": 0,
                "percentage": 0.0,
                "reason": f"No course elements for slug '{slug}'",
                "name": course_name,
            }

        if not course_id:
            course_id = elements[0].get("id")
        if course_name == slug and elements[0].get("name"):
            course_name = elements[0].get("name")

        total = len(mdata.get("linked", {}).get("onDemandCourseMaterialItems.v2", []))
        if total == 0:
            return {
                "status": "completed",
                "completed": 0,
                "total": 0,
                "percentage": 100.0,
                "name": course_name,
            }

        # Query course progress (identical to `skipera --list`)
        prog_url = (
            f"https://www.coursera.org/api/onDemandCoursesProgress.v1/{user_id}~{course_id}"
            f"?fields=gradedAssignmentGroupProgress"
        )
        pr = client.get(prog_url)

        # Detect if user is NOT enrolled in the course
        if pr.status_code == 403 or "Not Authorized" in pr.text:
            return {
                "status": "not_enrolled",
                "completed": 0,
                "total": total,
                "percentage": 0.0,
                "reason": "403 Not Authorized - user is not enrolled in this course",
                "name": course_name,
            }

        if pr.status_code != 200:
            return {
                "status": "unknown",
                "completed": 0,
                "total": total,
                "percentage": 0.0,
                "reason": f"Progress API returned status {pr.status_code}",
                "name": course_name,
            }

        pdata = pr.json()
        pelements = pdata.get("elements", [])
        if not pelements:
            return {
                "status": "incomplete",
                "completed": 0,
                "total": total,
                "percentage": 0.0,
                "reason": "No progress elements recorded",
                "name": course_name,
            }

        pelem = pelements[0]

        # Check module scores (if all modules >= 100%, course is complete)
        modules = pelem.get("modules", {})
        if modules and all(score >= 100 for score in modules.values()):
            return {
                "status": "completed",
                "completed": total,
                "total": total,
                "percentage": 100.0,
                "name": course_name,
            }

        # Check item-level progress
        items = pelem.get("items", {})
        completed_set = {
            item_id
            for item_id, prog in items.items()
            if prog.get("progressState") == "Completed"
        }

        # Handle elective / alternative graded assignment groups
        group_progress = pelem.get("gradedAssignmentGroupProgress", {})
        grp_params = {}
        for param in mdata.get("linked", {}).get("onDemandGradingParameters.v1", []):
            grp_params.update(param.get("gradedAssignmentGroups", {}))

        for group_id, grp_prog in group_progress.items():
            grp_info = grp_params.get(group_id, {})
            grp_items = grp_info.get("itemIds", [])
            num_required = grp_info.get("gradingType", {}).get(
                "definition", {}
            ).get("numberOfSelectedItems", 0)
            if grp_prog.get("state") == "Completed" or (
                num_required > 0
                and len([i for i in grp_items if i in completed_set]) >= num_required
            ):
                for alt_id in grp_items:
                    completed_set.add(alt_id)

        completed_count = len(completed_set)
        pct = (completed_count / total * 100) if total > 0 else 0.0
        is_done = (completed_count >= total and total > 0)

        return {
            "status": "completed" if is_done else "incomplete",
            "completed": completed_count,
            "total": total,
            "percentage": pct,
            "name": course_name,
        }

    except Exception as e:
        return {
            "status": "unknown",
            "completed": 0,
            "total": 0,
            "percentage": 0.0,
            "reason": str(e),
            "name": course_name,
        }


def format_progress_str(pre_done: int, pre_tot: int, post_done: int, post_tot: int, post_pct: float) -> str:
    """
    Builds a readable progress string comparing before and after run.
    e.g. '74/75 -> 75/75 (100.0%)' or '10/10 (100.0%)' or '-'
    """
    if post_tot > 0:
        if pre_tot > 0 and pre_done != post_done:
            return f"{pre_done}/{pre_tot} -> {post_done}/{post_tot} ({post_pct:.1f}%)"
        else:
            return f"{post_done}/{post_tot} ({post_pct:.1f}%)"
    elif pre_tot > 0:
        pre_pct = (pre_done / pre_tot * 100) if pre_tot > 0 else 0.0
        return f"{pre_done}/{pre_tot} ({pre_pct:.1f}%)"
    return "-"


def generate_summary_report(records: list[dict]) -> str:
    """
    Generates a cleanly formatted text table and breakdown report of all courses.
    """
    if not records:
        return "No courses were processed."

    max_idx = max(len(str(len(records))), 1)
    max_slug = max(max(len(r["slug"]) for r in records), 11)
    max_status = max(max(len(r["status"]) for r in records), 6)
    max_prog = max(max(len(r["progress_str"]) for r in records), 8)
    max_details = max(max(len(r["details"]) for r in records), 7)

    header_fmt = (
        f" {{:>{max_idx}}}  "
        f"{{:<{max_slug}}}  "
        f"{{:<{max_status}}}  "
        f"{{:<{max_prog}}}  "
        f"{{:<{max_details}}}"
    )

    header = header_fmt.format("#", "Course Slug", "Status", "Progress", "Details")
    width = max(len(header) + 2, 80)
    border = "=" * width
    divider = "-" * width

    lines = [
        border,
        "COURSES RUN SUMMARY".center(width),
        border,
        header,
        divider,
    ]

    for idx, r in enumerate(records, 1):
        lines.append(
            header_fmt.format(
                idx, r["slug"], r["status"], r["progress_str"], r["details"]
            )
        )
    lines.append(divider)

    total_courses = len(records)
    already_completed = sum(1 for r in records if r["status"] == "ALREADY DONE")
    newly_completed = sum(1 for r in records if r["status"] == "COMPLETED")
    total_completed = already_completed + newly_completed
    partially_completed = sum(1 for r in records if r["status"] == "INCOMPLETE")
    not_enrolled = sum(1 for r in records if r["status"] == "NOT ENROLLED")
    failed = sum(
        1
        for r in records
        if r["status"].startswith("FAILED") or r["status"] == "ERROR"
    )
    interrupted = sum(
        1 for r in records if r["status"] in ("INTERRUPTED", "CANCELLED")
    )
    executed_other = sum(1 for r in records if r["status"] == "EXECUTED")

    lines.append("OVERALL STATISTICS:")
    lines.append(f"  - Total Courses in List      : {total_courses}")
    lines.append(f"  - Already Completed (Skipped): {already_completed}")
    lines.append(f"  - Skipped (Not Enrolled)     : {not_enrolled}")
    lines.append(f"  - Newly Completed (This Run) : {newly_completed}")
    if partially_completed > 0:
        lines.append(f"  - Incomplete / In-Progress   : {partially_completed}")
    if failed > 0:
        lines.append(f"  - Failed / Errors            : {failed}")
    if executed_other > 0:
        lines.append(f"  - Executed (No Session Check): {executed_other}")
    if interrupted > 0:
        lines.append(f"  - Interrupted / Cancelled    : {interrupted}")

    lines.append("  " + "-" * 40)
    pct_complete = (total_completed / total_courses * 100) if total_courses > 0 else 0.0
    lines.append(
        f"  - Total 100% Completed       : {total_completed} / {total_courses} ({pct_complete:.1f}%)"
    )
    lines.append(divider)

    # Breakdown: Skipped courses
    skipped = [
        r for r in records if r["status"] in ("ALREADY DONE", "NOT ENROLLED")
    ]
    if skipped:
        lines.append("SKIPPED COURSES:")
        for r in skipped:
            lines.append(f"  [x] {r['slug']}: {r['details']}")
        lines.append(divider)

    # Breakdown: Incomplete or failed courses
    incomplete = [
        r
        for r in records
        if r["status"] in ("INCOMPLETE", "ERROR") or r["status"].startswith("FAILED")
    ]
    if incomplete:
        lines.append("INCOMPLETE / FAILED COURSES:")
        for r in incomplete:
            lines.append(f"  [!] {r['slug']}: {r['progress_str']} - {r['details']}")
        lines.append(divider)

    # Breakdown: All fully completed courses
    completed = [
        r for r in records if r["status"] in ("ALREADY DONE", "COMPLETED")
    ]
    if completed:
        lines.append("COMPLETED COURSES (100%):")
        for r in completed:
            lines.append(f"  [+] {r['slug']}: {r['progress_str']} ({r['details']})")
        lines.append(divider)

    lines.append(border)
    return "\n".join(lines)


def print_and_save_summary(records: list[dict], summary_file_path: str = DEFAULT_SUMMARY_FILE) -> None:
    """
    Prints the summary to terminal and writes it to a file.
    """
    summary_text = generate_summary_report(records)
    print("\n" + summary_text + "\n")

    if summary_file_path and summary_file_path.strip().lower() not in ("none", "no", "false", ""):
        try:
            out_file = Path(summary_file_path)
            out_file.write_text(summary_text + "\n", encoding="utf-8")
            print(f"[+] Summary report saved to '{out_file.resolve()}'\n")
        except Exception as e:
            print(f"[!] Note: Could not save summary report to '{summary_file_path}': {e}\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Run skipera on multiple courses listed in a file with automatic completion skipping and summary reporting."
    )
    parser.add_argument(
        "--file",
        "-f",
        default=DEFAULT_COURSES_FILE,
        help=f"Path to the file containing course slugs (default: '{DEFAULT_COURSES_FILE}')",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Pass --llm to skipera for automated assignment solving",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run skipera even if the course is already detected as 100%% completed",
    )
    parser.add_argument(
        "--summary-file",
        "-s",
        default=DEFAULT_SUMMARY_FILE,
        help=f"Path to save the final summary report (default: '{DEFAULT_SUMMARY_FILE}')",
    )
    args = parser.parse_args()

    courses_file = Path(args.file)

    # Fallback: if file doesn't exist, create it and prompt user
    if not courses_file.is_file():
        default_content = (
            "# Put your Coursera course slugs here, each on a new line.\n"
            "# Example:\n"
            "# data-warehousing-business-intelligence\n"
            "# descriptive-statistics-analyze-data-r\n"
        )
        courses_file.write_text(default_content, encoding="utf-8")
        print("\n" + "=" * 60)
        print(f"[!] Notice: Course list file '{courses_file}' did not exist.")
        print(f"    A new '{courses_file}' file has been created for you.")
        print("    Please add your course slugs to it (each on a new line)")
        print("    and re-run this script.")
        print("=" * 60 + "\n")
        sys.exit(0)

    slugs = []
    for line in courses_file.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            slugs.append(line)

    if not slugs:
        print("\n" + "=" * 60)
        print(f"[!] '{courses_file}' contains no course slugs.")
        print("    Please put course slugs in it (each on a new line)")
        print("    and re-run this script.")
        print("=" * 60 + "\n")
        sys.exit(0)

    print(f"Loaded {len(slugs)} course slug(s) from '{courses_file}'.")
    if args.llm:
        print("LLM mode enabled (--llm will be passed to skipera).")

    # Initialize session and enrolled courses matching `skipera --list`
    client, user_id, enrolled_courses = get_coursera_session_data()
    if not client or not user_id:
        print("[!] Note: Could not load Coursera cookies. Running skipera directly.")

    records = []

    for idx, slug in enumerate(slugs, 1):
        print("\n" + "=" * 60)
        print(f"[{idx}/{len(slugs)}] Course: {slug}".center(60))
        print("=" * 60)

        pre_info = (
            check_course_status(client, user_id, enrolled_courses, slug)
            if (client and user_id)
            else {}
        )
        status = pre_info.get("status", "unknown")
        pre_done = pre_info.get("completed", 0)
        pre_tot = pre_info.get("total", 0)
        pre_pct = pre_info.get("percentage", 0.0)
        course_name = pre_info.get("name", slug)

        # Check: Not enrolled
        if not args.force and status == "not_enrolled":
            print(f"[!] NOT ENROLLED: You are not enrolled in '{slug}'.")
            print("    (Coursera returned 403 Not Authorized)")
            print("    --> Skipping to prevent failure loops. Please enroll on coursera.org first.")
            prog_str = f"0/{pre_tot} (0.0%)" if pre_tot > 0 else "-"
            records.append({
                "slug": slug,
                "title": course_name,
                "status": "NOT ENROLLED",
                "progress_str": prog_str,
                "details": "Skipped: Not enrolled (403 Not Authorized)",
            })
            continue

        # Check: Already 100% completed
        if not args.force and status == "completed":
            print(f"[+] Already Completed ({pre_done}/{pre_tot} items, {pre_pct:.1f}%).")
            print(f"    --> Skipping '{slug}' (use --force to re-run).")
            prog_str = f"{pre_done}/{pre_tot} (100.0%)" if pre_tot > 0 else "100.0%"
            records.append({
                "slug": slug,
                "title": course_name,
                "status": "ALREADY DONE",
                "progress_str": prog_str,
                "details": "Skipped: Already 100% completed",
            })
            continue

        # Incomplete or force run
        if status == "incomplete":
            print(f"[-] Incomplete ({pre_done}/{pre_tot} items, {pre_pct:.1f}%). Running skipera...")
        else:
            print("[?] Running skipera...")

        cmd = [sys.executable, "-m", "skipera.main", slug]
        if args.llm:
            cmd.append("--llm")

        print(f"Executing: {' '.join(cmd)}\n")

        try:
            res = subprocess.run(cmd)

            # Query post-run status to accurately record final progress
            post_info = (
                check_course_status(client, user_id, enrolled_courses, slug)
                if (client and user_id)
                else {}
            )
            post_status = post_info.get("status", "unknown")
            post_done = post_info.get("completed", pre_done)
            post_tot = post_info.get("total", pre_tot)
            post_pct = post_info.get("percentage", pre_pct)

            prog_str = format_progress_str(pre_done, pre_tot, post_done, post_tot, post_pct)

            if res.returncode == 0:
                if post_status == "completed" or (post_tot > 0 and post_done >= post_tot):
                    status_label = "COMPLETED"
                    if post_done > pre_done:
                        details = f"Newly completed in this run (+{post_done - pre_done} items)"
                    else:
                        details = "Completed (100.0%)"
                elif post_status == "incomplete":
                    status_label = "INCOMPLETE"
                    if post_done > pre_done:
                        items_left = post_tot - post_done
                        details = f"Partially completed (+{post_done - pre_done} items, {items_left} left)"
                    else:
                        details = f"Incomplete: {post_done}/{post_tot} items done"
                else:
                    status_label = "EXECUTED"
                    details = "Executed successfully (exit code 0)"
            else:
                if post_status == "completed" or (post_tot > 0 and post_done >= post_tot):
                    status_label = "COMPLETED"
                    details = f"Completed (exited with code {res.returncode})"
                else:
                    status_label = f"FAILED ({res.returncode})"
                    details = f"Skipera exited with code {res.returncode}"

            records.append({
                "slug": slug,
                "title": course_name,
                "status": status_label,
                "progress_str": prog_str,
                "details": details,
            })

            if res.returncode != 0:
                print(f"\n[!] Warning: '{slug}' exited with code {res.returncode}")

        except KeyboardInterrupt:
            print(f"\n[!] Execution interrupted by user during course '{slug}'.")
            # Query status of current course so far
            post_info = (
                check_course_status(client, user_id, enrolled_courses, slug)
                if (client and user_id)
                else {}
            )
            post_done = post_info.get("completed", pre_done)
            post_tot = post_info.get("total", pre_tot)
            post_pct = post_info.get("percentage", pre_pct)
            prog_str = format_progress_str(pre_done, pre_tot, post_done, post_tot, post_pct)

            records.append({
                "slug": slug,
                "title": course_name,
                "status": "INTERRUPTED",
                "progress_str": prog_str,
                "details": "Interrupted by user (Ctrl+C)",
            })

            # Record remaining courses as CANCELLED
            for rem_slug in slugs[idx:]:
                rem_name = enrolled_courses.get(rem_slug, {}).get("name", rem_slug)
                records.append({
                    "slug": rem_slug,
                    "title": rem_name,
                    "status": "CANCELLED",
                    "progress_str": "-",
                    "details": "Not reached (run aborted)",
                })

            print_and_save_summary(records, args.summary_file)
            sys.exit(130)

        except Exception as e:
            print(f"\n[!] Error running '{slug}': {e}")
            records.append({
                "slug": slug,
                "title": course_name,
                "status": "ERROR",
                "progress_str": "-",
                "details": f"Error: {e}",
            })

    # Print and save complete summary at the end
    print_and_save_summary(records, args.summary_file)


if __name__ == "__main__":
    main()
