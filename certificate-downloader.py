#!/usr/bin/env python3
"""
Certificate Downloader for Coursera / Skipera
Fetches and downloads all official Coursera course & specialization certificate PDFs
for the authenticated user session and saves them into the 'certificates/' directory.
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

# Import skipera session configuration and utilities
try:
    from skipera.config import COOKIES, GRAPHQL_URL, HEADERS, fetch_browser_cookies, CONFIG_FILE, DEFAULT_CONFIG
    from skipera.session_utils import get_csrf_headers
except ImportError:
    # If running from outside repo root, adjust path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from skipera.config import COOKIES, GRAPHQL_URL, HEADERS, fetch_browser_cookies, CONFIG_FILE, DEFAULT_CONFIG
    from skipera.session_utils import get_csrf_headers

GET_MY_CERTIFICATES_QUERY = """
query GetMyCertificates($cursor: String, $limit: Int, $productType: Certificates_ProductType!) {
  Certificate {
    getMyCertificatesPaginated(cursor: $cursor, limit: $limit, productType: $productType) {
      elements {
        grade
        verifyCode
        grantedAt
        product {
          ... on Course_Course {
            id
            name
            slug
            partners {
              name
            }
          }
          ... on Specialization_Specialization {
            id
            name
            slug
            partners {
              name
            }
          }
        }
      }
      pagination {
        cursor
        totalElements
      }
    }
  }
}
"""


def sanitize_filename(name: str) -> str:
    """Sanitizes strings to create clean, OS-safe file and folder names."""
    # Replace illegal filename characters on Windows and UNIX
    clean = re.sub(r'[\\/*?:"<>|]', "-", name)
    # Collapse multiple spaces or dashes
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = re.sub(r"-+", "-", clean).strip(" -.")
    return clean or "certificate"


class CertificateDownloader:
    """Manages discovery and high-speed downloading of Coursera certificate PDFs."""

    def __init__(self, output_dir: Path, force: bool = False, max_workers: int = 3):
        self.output_dir = output_dir
        self.force = force
        self.max_workers = max_workers
        self.session = httpx.Client(
            headers=HEADERS,
            cookies=COOKIES,
            timeout=35.0,
            verify=False,
            follow_redirects=True,
        )

        # Validate session authentication
        self._ensure_valid_session()

    def _ensure_valid_session(self) -> None:
        """Verifies active session; attempts automatic browser cookie refresh if expired."""
        test_url = "https://www.coursera.org/api/adminUserPermissions.v1?q=my"
        res = self.session.get(test_url)
        if res.status_code == 200 and res.json().get("elements"):
            user_id = res.json()["elements"][0].get("id")
            logger.info(f"Authenticated Coursera User ID: {user_id}")
            return

        logger.warning("Session cookies appear invalid or expired. Attempting automatic refresh from browser...")
        new_cookies = fetch_browser_cookies()
        if not new_cookies or not new_cookies.get("CAUTH"):
            logger.error("Could not obtain valid CAUTH cookies. Please log in to Coursera in your browser.")
            sys.exit(1)

        self.session.cookies.clear()
        self.session.cookies.update(new_cookies)

        # Update persisted config.json
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = DEFAULT_CONFIG.copy()
            cfg["cookies"] = new_cookies
            CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        # Retry authentication check
        res = self.session.get(test_url)
        if res.status_code != 200 or not res.json().get("elements"):
            logger.error("Authentication failed even after refreshing cookies. Please log in to Coursera.")
            sys.exit(1)

        user_id = res.json()["elements"][0].get("id")
        logger.success(f"Successfully refreshed authentication! User ID: {user_id}")

    def fetch_all_certificates(self, product_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Queries Coursera GraphQL API to fetch all course and specialization certificates
        awarded to the user.
        """
        if not product_types:
            product_types = ["COURSE", "SPECIALIZATION"]

        all_records: List[Dict[str, Any]] = []

        for ptype in product_types:
            cursor = "0"
            logger.info(f"Scanning for awarded {ptype.lower()} certificates...")

            while True:
                payload = {
                    "operationName": "GetMyCertificates",
                    "variables": {
                        "cursor": cursor,
                        "limit": 50,
                        "productType": ptype,
                    },
                    "query": GET_MY_CERTIFICATES_QUERY,
                }

                headers = get_csrf_headers(self.session)
                try:
                    response = self.session.post(GRAPHQL_URL, json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Failed GraphQL query for {ptype}: {e}")
                    break

                if response.status_code != 200:
                    logger.error(f"GraphQL request failed ({response.status_code}): {response.text[:200]}")
                    break

                res_data = response.json()
                cert_data = (
                    res_data.get("data", {})
                    .get("Certificate", {})
                    .get("getMyCertificatesPaginated", {})
                )

                elements = cert_data.get("elements", [])
                pagination = cert_data.get("pagination", {})
                total_elements = pagination.get("totalElements", 0)

                for item in elements:
                    item["productType"] = ptype
                    all_records.append(item)

                next_cursor = pagination.get("cursor")
                if not next_cursor or len(elements) == 0 or len(all_records) >= total_elements:
                    break
                cursor = next_cursor

        logger.success(f"Total certificates discovered: {len(all_records)}")
        return all_records

    def download_certificate_pdf(self, cert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Downloads a single certificate PDF directly using its unique verification code.
        Returns a dict summarizing the result.
        """
        verify_code = cert.get("verifyCode")
        product = cert.get("product") or {}
        name = product.get("name") or "Coursera_Certificate"
        slug = product.get("slug") or "unknown"
        ptype = cert.get("productType", "COURSE")
        grade_pct = f"{round(cert.get('grade', 0) * 100, 1)}%" if cert.get("grade") is not None else "N/A"

        if not verify_code:
            return {"status": "FAILED", "name": name, "error": "Missing verifyCode"}

        # Format clean filename: e.g. "Advanced-Git-and-GitHub-Practices_3W57GP5WOPIZ.pdf"
        safe_name = sanitize_filename(name).replace(" ", "_")
        filename = f"{safe_name}_{verify_code}.pdf"
        dest_path = self.output_dir / filename

        # Check if already exists and is non-empty
        if dest_path.is_file() and dest_path.stat().st_size > 1024 and not self.force:
            # Verify magic bytes of existing file
            try:
                with open(dest_path, "rb") as f:
                    header = f.read(5)
                if header.startswith(b"%PDF-"):
                    return {
                        "status": "SKIPPED",
                        "name": name,
                        "slug": slug,
                        "verifyCode": verify_code,
                        "grade": grade_pct,
                        "path": str(dest_path),
                        "size": dest_path.stat().st_size,
                    }
            except Exception:
                pass  # Re-download if corrupted

        download_url = f"https://www.coursera.org/api/certificate.v1/pdf/{verify_code}"

        for attempt in range(1, 4):
            try:
                res = self.session.get(download_url)
                if res.status_code == 200 and res.content.startswith(b"%PDF-"):
                    dest_path.write_bytes(res.content)
                    return {
                        "status": "DOWNLOADED",
                        "name": name,
                        "slug": slug,
                        "verifyCode": verify_code,
                        "grade": grade_pct,
                        "path": str(dest_path),
                        "size": len(res.content),
                    }
                elif res.status_code == 404:
                    return {
                        "status": "FAILED",
                        "name": name,
                        "error": "PDF not yet generated or not found by Coursera (404)",
                    }
                else:
                    logger.warning(
                        f"Attempt {attempt}/3: Unexpected response for {name} ({verify_code}): "
                        f"status {res.status_code}"
                    )
            except Exception as e:
                logger.warning(f"Attempt {attempt}/3 error downloading {verify_code}: {e}")

            if attempt < 3:
                time.sleep(1.5 * attempt)

        return {
            "status": "FAILED",
            "name": name,
            "error": "Exceeded maximum retry attempts or invalid PDF header",
        }

    def run(
        self,
        filter_slug: Optional[str] = None,
        filter_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes the full discovery and download workflow.
        Generates a summary manifest in the output directory.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        certificates = self.fetch_all_certificates()
        if not certificates:
            logger.warning("No certificates found for this Coursera account.")
            return []

        # Apply optional filters
        if filter_code:
            certificates = [c for c in certificates if c.get("verifyCode") == filter_code]
        if filter_slug:
            certificates = [
                c for c in certificates if (c.get("product") or {}).get("slug") == filter_slug
            ]

        if not certificates:
            logger.warning("No certificates matched the specified filter criteria.")
            return []

        logger.info(f"Starting download of {len(certificates)} certificates into: {self.output_dir.resolve()}")

        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(certificates))) as executor:
            future_to_cert = {
                executor.submit(self.download_certificate_pdf, cert): cert for cert in certificates
            }
            for future in as_completed(future_to_cert):
                res = future.result()
                results.append(res)
                st = res.get("status")
                name = res.get("name")
                code = res.get("verifyCode", "")
                if st == "DOWNLOADED":
                    logger.success(f"[DOWNLOADED] {name} ({code}) -> {Path(res['path']).name}")
                elif st == "SKIPPED":
                    logger.info(f"[EXISTS]     {name} ({code}) -> {Path(res['path']).name}")
                else:
                    logger.error(f"[FAILED]     {name} ({code}) -> {res.get('error')}")

        # Generate a manifest file
        manifest_path = self.output_dir / "certificates_manifest.json"
        manifest_data = {
            "total_certificates": len(certificates),
            "downloaded": len([r for r in results if r.get("status") == "DOWNLOADED"]),
            "skipped_already_present": len([r for r in results if r.get("status") == "SKIPPED"]),
            "failed": len([r for r in results if r.get("status") == "FAILED"]),
            "certificates": [
                {
                    "title": (c.get("product") or {}).get("name"),
                    "slug": (c.get("product") or {}).get("slug"),
                    "type": c.get("productType"),
                    "verify_code": c.get("verifyCode"),
                    "grade": c.get("grade"),
                    "granted_at": c.get("grantedAt"),
                    "verification_url": f"https://www.coursera.org/account/accomplishments/certificate/{c.get('verifyCode')}",
                    "file_path": next(
                        (r.get("path") for r in results if r.get("verifyCode") == c.get("verifyCode")),
                        None,
                    ),
                }
                for c in certificates
            ],
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        logger.info(f"Saved certificates manifest to: {manifest_path}")

        # Print friendly console summary
        self.print_summary(results)
        return results

    def print_summary(self, results: List[Dict[str, Any]]) -> None:
        """Prints a structured summary table to console."""
        downloaded = [r for r in results if r.get("status") == "DOWNLOADED"]
        skipped = [r for r in results if r.get("status") == "SKIPPED"]
        failed = [r for r in results if r.get("status") == "FAILED"]

        print("\n" + "=" * 80)
        print(" COURSERA CERTIFICATES DOWNLOAD SUMMARY ".center(80, "="))
        print("=" * 80)
        print(f"Total Processed       : {len(results)}")
        print(f"Successfully Downloaded: {len(downloaded)}")
        print(f"Already Present (Skip) : {len(skipped)}")
        print(f"Failed                : {len(failed)}")
        print(f"Saved Folder          : {self.output_dir.resolve()}")
        print("-" * 80)

        for i, r in enumerate(results, 1):
            st = r.get("status", "UNKNOWN")
            mark = "[+]" if st == "DOWNLOADED" else ("[x]" if st == "SKIPPED" else "[!]")
            name = r.get("name", "Unknown")
            code = r.get("verifyCode", "")
            grade = r.get("grade", "")
            print(f"{mark} {i:2d}. {name[:48]:<48} | Grade: {grade:<6} | {st}")

        print("=" * 80 + "\n")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download all Coursera certificates as PDFs for the logged-in user account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Download all certificates to the default 'certificates/' directory:
  python certificate-downloader.py

  # Download certificates to a custom directory:
  python certificate-downloader.py --output-dir my_certs/

  # Force re-download even if certificates already exist:
  python certificate-downloader.py --force

  # Download a certificate for a specific course slug:
  python certificate-downloader.py --slug data-warehousing-business-intelligence

  # Download by specific Coursera verification code:
  python certificate-downloader.py --code KWI2G9CGIW5J
        """,
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("certificates"),
        help="Target folder to save downloaded certificate PDFs (default: 'certificates')",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-download PDFs even if they already exist in the target directory",
    )
    parser.add_argument(
        "--slug",
        "-s",
        type=str,
        default=None,
        help="Download certificate only for this specific course slug",
    )
    parser.add_argument(
        "--code",
        "-c",
        type=str,
        default=None,
        help="Download certificate only for this specific verification code",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=4,
        help="Number of concurrent download threads (default: 4)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    downloader = CertificateDownloader(
        output_dir=args.output_dir,
        force=args.force,
        max_workers=args.workers,
    )
    downloader.run(filter_slug=args.slug, filter_code=args.code)


if __name__ == "__main__":
    main()
