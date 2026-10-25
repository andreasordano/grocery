"""The weekly plan newsletter (WEB-37): let new subscribers in, build an edition, and log what was sent.

Every step runs on the live site (core/editions.py), which has the database and the MailerLite key; this
script only needs EDITION_TOKEN, the same as on Render. It's read from the macOS Keychain (item
"pantryrun-edition"), or from the EDITION_TOKEN environment variable. Store it once with:
  security add-generic-password -s pantryrun-edition -a pantryrun -w

Each week:
  1. python -m scripts.weekly_plan promote
       Subscribers whose first visit to pantryrun was 7 or more days ago move from the new group to the
       weekly group: no reminders in a tester's first week (PROD-5).
  2. python -m scripts.weekly_plan build --title "Week 46" --dinners nd-1318,kanasupp,lohe_kartul \\
         --featured-url https://www.rimi.ee/retseptid/... [--servings 2]
       The site prices the plan at every store (refusing it when a store didn't answer, or when even the best
       store lacks something) and saves it; this prints a summary and writes the email to
       logs/edition-<plan>.html.
       --featured <id> instead of --featured-url when the featured dinner is already in pantryrun.
  3. In MailerLite: new campaign to the weekly group → Custom HTML editor → paste the file, send a test to
     yourself, then send.
  4. python -m scripts.weekly_plan sent --plan <plan>
       Logs the edition as a reminder (table nudges) for everyone in the weekly group, so the metrics can
       tell prompted visits from unprompted ones (metrics.return_7d).

Links carry {$pantryrun_id}, MailerLite's merge tag for the subscriber's pantryrun id: the plan opens as the
same person on any device.
"""

import argparse
import os
import subprocess
import sys

import requests

BASE_URL = "https://grocery-j3en.onrender.com"
KEYCHAIN_ITEM = "pantryrun-edition"
WAIT = 600  # seconds: right after a deploy the site's price cache is cold, and a build takes minutes


def token():
    """EDITION_TOKEN from the environment, else from the macOS Keychain."""
    if os.environ.get("EDITION_TOKEN"):
        return os.environ["EDITION_TOKEN"]
    try:
        found = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_ITEM, "-w"],
                               capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        found = None
    if found and found.returncode == 0 and found.stdout.strip():
        return found.stdout.strip()
    sys.exit(f"No EDITION_TOKEN. Store it in the Keychain: security add-generic-password -s {KEYCHAIN_ITEM} -a pantryrun -w")


def ask(base, path, body=None):
    """POST to the live site as the owner; exits with the site's reason when it refuses."""
    r = requests.post(f"{base.rstrip('/')}{path}", json=body, headers={"Authorization": f"Bearer {token()}"}, timeout=WAIT)
    if r.status_code != 200:
        try:
            reason = r.json().get("detail", r.text)
        except ValueError:
            reason = r.text
        sys.exit(f"The site refused ({r.status_code}): {reason}")
    return r.json()


def build(args):
    made = ask(args.base_url, "/editions", {
        "title": args.title, "dinners": [d for d in args.dinners.split(",") if d.strip()],
        "featured": args.featured, "featured_url": args.featured_url, "servings": args.servings})
    path = os.path.join("logs", f"edition-{made['token']}.html")
    os.makedirs("logs", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(made["html"])
    print(f"Plan saved: {made['token']}\n\n{made['text']}")
    print(f"\nThe email: {path} (paste it into MailerLite's Custom HTML editor)")
    print(f"After sending: python -m scripts.weekly_plan sent --plan {made['token']}")


def promote(args):
    done = ask(args.base_url, "/editions/promote")
    print(f"{done['moved']} of {done['waiting']} new subscribers moved to the weekly group.")


def sent(args):
    done = ask(args.base_url, f"/editions/{args.plan}/sent")
    print(f"Logged the edition as a reminder for {done['logged']} subscribers.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=BASE_URL)
    sub = p.add_subparsers(dest="step", required=True)
    b = sub.add_parser("build", help="save a plan and print the edition")
    b.add_argument("--title", required=True)
    b.add_argument("--dinners", required=True, help="dinner ids, comma-separated (classics, nd-… dishes, sh-… dinners sent by link)")
    b.add_argument("--featured", help="the featured dinner's id")
    b.add_argument("--featured-url", help="a store's or brand's recipe page to feature")
    b.add_argument("--servings", type=int, default=2)
    sub.add_parser("promote", help="move subscribers past their first week into the weekly group")
    s = sub.add_parser("sent", help="log a sent edition as a reminder for its readers")
    s.add_argument("--plan", required=True)
    args = p.parse_args(argv)
    {"build": build, "promote": promote, "sent": sent}[args.step](args)


if __name__ == "__main__":
    main()
