import argparse
import json
import subprocess
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".skipera" / "config.json"
DEFAULT_COURSES_FILE = "courses"

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
        'reason': str
      }
    """
    if not client or not user_id:
        return {"status": "unknown", "reason": "No active Coursera session"}

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
            return {"status": "unknown", "reason": f"Could not load materials for slug '{slug}'"}

        mdata = mr.json()
        elements = mdata.get("elements", [])
        if not elements:
            return {"status": "unknown", "reason": f"No course elements for slug '{slug}'"}

        if not course_id:
            course_id = elements[0].get("id")

        total = len(mdata.get("linked", {}).get("onDemandCourseMaterialItems.v2", []))

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
            }

        if pr.status_code != 200:
            return {"status": "unknown", "reason": f"Progress API returned status {pr.status_code}"}

        pdata = pr.json()
        pelements = pdata.get("elements", [])
        if not pelements:
            return {
                "status": "incomplete",
                "completed": 0,
                "total": total,
                "percentage": 0.0,
                "reason": "No progress elements recorded",
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
        }

    except Exception as e:
        return {"status": "unknown", "reason": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Run skipera on multiple courses listed in a file with automatic completion skipping."
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
        line = line.strip()
        if line and not line.startswith("#"):
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

    skipped_completed = 0
    skipped_not_enrolled = 0
    executed_count = 0

    for idx, slug in enumerate(slugs, 1):
        print("\n" + "=" * 60)
        print(f"[{idx}/{len(slugs)}] Course: {slug}".center(60))
        print("=" * 60)

        # Check course status (matching skipera --list)
        if not args.force and client and user_id:
            info = check_course_status(client, user_id, enrolled_courses, slug)
            status = info.get("status")

            if status == "not_enrolled":
                print(f"[!] NOT ENROLLED: You are not enrolled in '{slug}'.")
                print("    (Coursera returned 403 Not Authorized)")
                print("    --> Skipping to prevent failure loops. Please enroll on coursera.org first.")
                skipped_not_enrolled += 1
                continue

            elif status == "completed":
                done = info.get("completed", 0)
                tot = info.get("total", 0)
                pct = info.get("percentage", 100.0)
                print(f"[+] Already Completed ({done}/{tot} items, {pct:.1f}%).")
                print(f"    --> Skipping '{slug}' (use --force to re-run).")
                skipped_completed += 1
                continue

            elif status == "incomplete":
                done = info.get("completed", 0)
                tot = info.get("total", 0)
                pct = info.get("percentage", 0.0)
                print(f"[-] Incomplete ({done}/{tot} items, {pct:.1f}%). Running skipera...")

            else:
                reason = info.get("reason", "unknown")
                print(f"[?] Could not determine progress ({reason}). Running skipera as precaution...")

        cmd = ["uv", "run", "skipera", slug]
        if args.llm:
            cmd.append("--llm")

        print(f"Executing: {' '.join(cmd)}\n")
        executed_count += 1
        try:
            res = subprocess.run(cmd)
            if res.returncode != 0:
                print(f"\n[!] Warning: '{slug}' exited with code {res.returncode}")
        except KeyboardInterrupt:
            print("\nExecution interrupted by user. Exiting...")
            sys.exit(130)
        except Exception as e:
            print(f"\n[!] Error running '{slug}': {e}")

    print("\n" + "=" * 60)
    summary_parts = [f"{executed_count} executed", f"{skipped_completed} skipped (completed)"]
    if skipped_not_enrolled > 0:
        summary_parts.append(f"{skipped_not_enrolled} skipped (not enrolled)")
    summary = f"Summary: {', '.join(summary_parts)}"
    print(summary.center(60))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
