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


def get_coursera_client_and_user():
    """Initializes an HTTP client with saved Coursera cookies and retrieves user ID."""
    try:
        import httpx
    except ImportError:
        return None, None

    if not CONFIG_FILE.is_file():
        return None, None

    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        cookies = cfg.get("cookies", {})
        if not cookies:
            return None, None

        client = httpx.Client(
            cookies=cookies,
            headers=HEADERS,
            timeout=20.0,
            verify=False,
            follow_redirects=True,
        )

        r = client.get("https://www.coursera.org/api/adminUserPermissions.v1?q=my")
        if r.status_code == 200:
            elements = r.json().get("elements", [])
            if elements and "id" in elements[0]:
                return client, elements[0]["id"]
    except Exception:
        pass

    return None, None


def check_course_completed(client, user_id: str, slug: str):
    """
    Checks if a course is 100% completed.
    Returns (is_completed, completed_count, total_count).
    If check cannot be determined, returns (False, None, None).
    """
    if not client or not user_id:
        return False, None, None

    try:
        mat_url = (
            f"https://www.coursera.org/api/onDemandCourseMaterials.v2/"
            f"?q=slug&slug={slug}&includes=items,gradingParameters"
            f"&fields=onDemandGradingParameters.v1(gradedAssignmentGroups)"
        )
        mr = client.get(mat_url)
        if mr.status_code != 200:
            return False, None, None

        mdata = mr.json()
        elements = mdata.get("elements", [])
        if not elements:
            return False, None, None

        course_id = elements[0].get("id")
        total = len(mdata.get("linked", {}).get("onDemandCourseMaterialItems.v2", []))
        if total == 0:
            return False, None, None

        prog_url = (
            f"https://www.coursera.org/api/onDemandCoursesProgress.v1/{user_id}~{course_id}"
            f"?fields=gradedAssignmentGroupProgress"
        )
        pr = client.get(prog_url)
        if pr.status_code != 200:
            return False, None, total

        pdata = pr.json()
        pelements = pdata.get("elements", [])
        if not pelements:
            return False, 0, total

        pelem = pelements[0]

        # Check module scores (if all modules >= 100%, course is complete)
        modules = pelem.get("modules", {})
        if modules and all(score >= 100 for score in modules.values()):
            return True, total, total

        items = pelem.get("items", {})
        completed_set = {
            item_id
            for item_id, prog in items.items()
            if prog.get("progressState") == "Completed"
        }

        # Check elective / alternative graded assignment groups
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
        return (completed_count >= total), completed_count, total

    except Exception:
        return False, None, None


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

    # Initialize completion checker
    client, user_id = get_coursera_client_and_user()
    if not client or not user_id:
        print("[!] Note: Could not pre-authenticate with Coursera cookies for completion checks.")
        print("    All courses will be run directly with skipera.")

    skipped_count = 0
    executed_count = 0

    for idx, slug in enumerate(slugs, 1):
        print("\n" + "=" * 60)
        print(f"[{idx}/{len(slugs)}] Course: {slug}".center(60))
        print("=" * 60)

        # Check completion
        if not args.force and client and user_id:
            print(f"Checking completion progress for '{slug}'...")
            is_done, done_items, total_items = check_course_completed(client, user_id, slug)
            if is_done:
                pct = (done_items / total_items * 100) if total_items else 100.0
                print(f"[+] Already Completed ({done_items}/{total_items} items, {pct:.1f}%).")
                print(f"    --> Skipping '{slug}' (use --force to re-run).")
                skipped_count += 1
                continue
            elif done_items is not None and total_items is not None:
                pct = (done_items / total_items * 100) if total_items else 0.0
                print(f"[-] Incomplete ({done_items}/{total_items} items, {pct:.1f}%). Running skipera...")
            else:
                print("[?] Could not determine completion progress. Running skipera as precaution...")

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
    summary = f"Summary: {executed_count} executed, {skipped_count} skipped (already complete)"
    print(summary.center(60))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
