"""
Automated Course Enrollment Script for Coursera / Skipera
Uses Playwright with your authenticated browser cookies to enroll in Coursera courses or guided projects.
"""

import argparse
import sys
import time
from pathlib import Path
from loguru import logger

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("Playwright is not installed. Run: uv pip install playwright")
    sys.exit(1)

from skipera.config import fetch_browser_cookies


def get_browser_cookies() -> list[dict]:
    """Fetch active cookies and format them for Playwright."""
    logger.info("Fetching Coursera cookies from browser...")
    raw_cookies = fetch_browser_cookies()
    if not raw_cookies or "CAUTH" not in raw_cookies:
        logger.error("Could not find a valid CAUTH cookie. Please log in to Coursera in your browser.")
        return []

    pw_cookies = []
    for name, value in raw_cookies.items():
        if name and value:
            pw_cookies.append({
                "name": name,
                "value": value,
                "domain": ".coursera.org",
                "path": "/"
            })
    return pw_cookies


def enroll_in_course(page, slug: str, wait_seconds: int = 10) -> bool:
    """
    Attempts to enroll in a course given its Coursera slug.
    Returns True if successfully enrolled or already enrolled, False otherwise.
    """
    logger.info(f"Processing enrollment for '{slug}'...")
    url = f"https://www.coursera.org/learn/{slug}"
    
    try:
        # wait_until='commit' avoids net::ERR_ABORTED when Coursera triggers immediate redirects to organization portal
        page.goto(url, wait_until="commit", timeout=45000)
    except Exception as e:
        logger.debug(f"Navigation redirected or committed for '{slug}': {e}")

    # Wait for Coursera SPA, organization SSO, and dynamic React components to load and hydrate
    logger.info(f"Waiting {wait_seconds}s for Coursera page to fully load and hydrate...")
    page.wait_for_timeout(wait_seconds * 1000)

    current_url = page.url
    page_title = page.title()
    logger.debug(f"Loaded page: {page_title} ({current_url})")

    # 1. Check if already enrolled
    if "/home" in current_url or "/welcome" in current_url:
        logger.success(f"Already enrolled in '{slug}' (redirected to course home).")
        return True

    for btn_text in ["Go to Course", "Go To Course", "Resume", "Continue Learning", "Already Enrolled"]:
        btn = page.locator(f'button:has-text("{btn_text}"), a:has-text("{btn_text}")').first
        if btn.is_visible():
            logger.success(f"Already enrolled in '{slug}' (detected '{btn_text}' button).")
            return True

    # 2. Look for Guided Project CTA
    guided_btn = page.locator('button:has-text("Start Guided Project"), a:has-text("Start Guided Project")').first
    if guided_btn.is_visible():
        logger.info(f"Found 'Start Guided Project' button for '{slug}'. Clicking...")
        guided_btn.click()
        page.wait_for_timeout(5000)
        logger.success(f"Successfully started guided project '{slug}'!")
        return True

    # 3. Look for standard Free / University / Organization Enrollment buttons
    enroll_btn = None
    for pattern in ["Enroll for free", "Enroll", "Start Learning", "Join Course"]:
        b = page.locator(f'button:has-text("{pattern}"), a[role="button"]:has-text("{pattern}")').first
        if b.is_visible():
            enroll_btn = b
            logger.info(f"Found primary enrollment button: '{pattern}'")
            break

    if not enroll_btn:
        # Check if it has 'Try free for 7 days'
        trial_btn = page.locator('button:has-text("Try free for 7 days")').first
        if trial_btn.is_visible():
            enroll_btn = trial_btn
            logger.info("Found 'Try free for 7 days' specialization button.")

    if not enroll_btn:
        logger.warning(f"Could not find an enrollment button for '{slug}'. You may need manual enrollment.")
        return False

    # Click the enrollment button
    enroll_btn.click()
    logger.info("Clicked enrollment button. Waiting 5s for action to process...")
    page.wait_for_timeout(5000)

    # 4. Handle modal dialogs (Audit, Specialization, Program selection)
    for dialog in page.locator('[role="dialog"]').all():
        if dialog.is_visible():
            dialog_text = dialog.inner_text()
            logger.debug(f"Modal opened: {dialog_text[:120]}...")

            # Option A: Check for free Audit link (common in specializations)
            audit_btn = page.locator('a:has-text("Audit the course"), a:has-text("Audit"), button:has-text("Audit")').first
            if audit_btn.is_visible():
                logger.info("Found 'Audit' option. Clicking to enroll in free audit mode...")
                audit_btn.click()
                page.wait_for_timeout(5000)
                logger.success(f"Successfully enrolled in '{slug}' (Audit Mode)!")
                return True

            # Option B: Check for enterprise/program selection or Start Course inside modal
            for confirm_text in ["Start Learning", "Go to Course", "Go To Course", "Enroll", "Continue"]:
                confirm_btn = dialog.locator(f'button:has-text("{confirm_text}"), a:has-text("{confirm_text}")').first
                if confirm_btn.is_visible():
                    logger.info(f"Clicking modal confirmation button: '{confirm_text}'")
                    confirm_btn.click()
                    page.wait_for_timeout(5000)
                    break

    # 5. Verify final status
    page.wait_for_timeout(3000)
    final_url = page.url
    if "/home" in final_url or "/welcome" in final_url:
        logger.success(f"Successfully enrolled in '{slug}'!")
        return True

    for btn_text in ["Go to Course", "Go To Course", "Resume", "Continue Learning"]:
        if page.locator(f'button:has-text("{btn_text}"), a:has-text("{btn_text}")').first.is_visible():
            logger.success(f"Enrollment confirmed for '{slug}'!")
            return True

    logger.warning(f"Enrollment action sent for '{slug}', but could not unambiguously verify. Check Coursera.")
    return True


def run_enrollment(slugs: list[str], headless: bool = False, wait_seconds: int = 10) -> None:
    cookies = get_browser_cookies()
    if not cookies:
        return

    with sync_playwright() as p:
        # Try MS Edge first (default on Windows), fallback to system Chromium/Chrome
        browser = None
        for channel in ["msedge", "chrome", None]:
            try:
                if channel:
                    browser = p.chromium.launch(channel=channel, headless=headless)
                else:
                    browser = p.chromium.launch(headless=headless)
                logger.info(f"Launched browser engine: {channel or 'playwright-chromium'} (headless={headless})")
                break
            except Exception as e:
                logger.debug(f"Failed launching with channel '{channel}': {e}")
                continue

        if not browser:
            logger.error("Could not launch browser. Ensure Microsoft Edge or Google Chrome is installed.")
            return

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        success_count = 0
        for slug in slugs:
            slug = slug.strip()
            if not slug or slug.startswith("#"):
                continue
            ok = enroll_in_course(page, slug, wait_seconds=wait_seconds)
            if ok:
                success_count += 1
            time.sleep(2)  # courteous delay between requests

        browser.close()
        logger.info(f"Enrollment batch complete: {success_count}/{len(slugs)} courses processed.")


def main():
    epilog_text = """
COMMAND EXAMPLES & DETAILS:
  1. Enroll in a single course:
       python enroll.py <course-slug>
       Example:
         python enroll.py build-an-ai-travel-agent-app-with-openai

  2. Batch-enroll all courses from 'courses' file:
       python enroll.py
       Details:
         If no slug is passed, it automatically reads every slug listed in the
         'courses' file in the current directory.

  3. Custom wait time (e.g. 15 seconds for slow internet):
       python enroll.py --wait 15
       python enroll.py <course-slug> -w 15
       Details:
         Waits the specified number of seconds (default: 10) after opening the
         page for Coursera and organization SSO/React hydration before locating
         buttons.

  4. Batch-enroll from a custom file:
       python enroll.py --file path/to/my_courses.txt
       python enroll.py -f path/to/my_courses.txt
       Details:
         Reads one course slug per line from the specified file. Lines starting
         with '#' are ignored.

  5. Run silently in headless mode (background):
       python enroll.py <course-slug> --headless
       python enroll.py --headless
       Details:
         By default, a browser window opens so you can monitor progress.
         Add '--headless' to run silently in the background without UI.

END-TO-END WORKFLOW WITH SKIPERA:
  Once enrolled, courses can be completed using Skipera:

  - Single Course:
      Step 1 (Enroll)  : python enroll.py <course-slug>
      Step 2 (Complete): python -m skipera.main <course-slug> --llm

  - Batch Processing:
      Step 1 (Enroll)  : python enroll.py
      Step 2 (Complete): python run-for-courses.py

HOW ENROLLMENT WORKS:
  - Fetches active Coursera session cookies from your browser (Chrome/Firefox/Edge).
  - Waits 10 seconds for Coursera & organization portals (e.g. NMIMS) to fully hydrate.
  - Checks if you are already enrolled ('Go to Course' / 'Resume').
  - Clicks enrollment buttons ('Enroll for free', 'Start Guided Project', 'Enroll').
  - Detects specialization modals and selects the free 'Audit' option if available.
"""

    parser = argparse.ArgumentParser(
        description="Automate Coursera course enrollment for Skipera.",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("slug", nargs="?", help="Course slug from the Coursera URL (e.g. data-warehousing-business-intelligence)")
    parser.add_argument("--file", "-f", default=None, help="Path to a text file containing course slugs (one per line, e.g. courses)")
    parser.add_argument("--wait", "-w", type=int, default=10, help="Seconds to wait for Coursera page to fully hydrate before searching for buttons (default: 10)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (default: false, headed so you can see progress)")

    args = parser.parse_args()

    slugs = []
    if args.slug:
        slugs.append(args.slug)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            logger.error(f"File not found: {args.file}")
            sys.exit(1)
        slugs = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    else:
        # Default to 'courses' file if it exists
        default_file = Path("courses")
        if default_file.is_file():
            logger.info("No slug provided. Reading course slugs from 'courses' file...")
            slugs = [line.strip() for line in default_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        else:
            parser.print_help()
            sys.exit(0)

    if not slugs:
        logger.warning("No course slugs to process.")
        return

    logger.info(f"Enrolling in {len(slugs)} course(s) (waiting {args.wait}s per course)...")
    run_enrollment(slugs, headless=args.headless, wait_seconds=args.wait)


if __name__ == "__main__":
    main()
