#!/usr/bin/env python3
import sys
import getpass
import json
import base64
import urllib.request
import urllib.error

# Apache Jira Server endpoint
JIRA_URL = "https://issues.apache.org/jira"

def make_request(url, method="GET", data=None, username=None, password=None, token=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    elif username and password:
        auth_str = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {encoded_auth}")
    
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            response_text = response.read().decode("utf-8")
            return status_code, response_text
    except urllib.error.HTTPError as e:
        status_code = e.getcode()
        response_text = e.read().decode("utf-8")
        return status_code, response_text
    except urllib.error.URLError as e:
        return 0, str(e.reason)

def print_401_help():
    print("\n" + "="*50)
    print("ERROR: Unauthorized (401)")
    print("="*50)
    print("Apache Jira requires secure authentication. Standard password authentication")
    print("is often blocked or restricted by the ASF infrastructure.")
    print("\nRECOMMENDED SOLUTION: Use a Personal Access Token (PAT)")
    print("--------------------------------------------------")
    print("1. Log in to Apache JIRA: https://issues.apache.org/jira")
    print("2. Click on your Profile icon in the top right -> Profile.")
    print("3. Click 'Personal Access Tokens' in the left-hand navigation menu.")
    print("4. Click 'Create Token', give it a name (e.g. 'Release-Script'), and copy it.")
    print("5. Run this script again and choose 'Option 1: Personal Access Token (PAT)'.")
    print("="*50 + "\n")

def main():
    # Check for dry-run/mock flag
    is_dry_run = "--dry-run" in sys.argv or "--mock" in sys.argv

    print("==================================================")
    if is_dry_run:
        print(" RUNNING IN DRY-RUN / SIMULATED MODE")
        print(" (No actual modifications will be made to JIRA)")
        print("==================================================")

    # 1. Gather Inputs and Choose Auth Method
    username = None
    password = None
    token = None

    try:
        version = input("Enter the current target release version (e.g., 2.2.0): ").strip()
        next_version = input("Enter the next minor/snapshot version (e.g., 2.3.0): ").strip()
        
        if is_dry_run:
            auth_choice = "1"
            token = "dryrun_token"
        else:
            print("\nChoose Authentication Method:")
            print("  [1] Personal Access Token (PAT) - Recommended / Required by ASF")
            print("  [2] Basic Username/Password")
            auth_choice = input("Select [1-2] (Default: 1): ").strip() or "1"
            
            if auth_choice == "1":
                token = getpass.getpass("Enter your Apache Jira Personal Access Token (PAT): ").strip()
            elif auth_choice == "2":
                username = input("Enter your Apache Jira username: ").strip()
                password = getpass.getpass("Enter your Apache Jira password: ")
            else:
                print("Error: Invalid choice.")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)

    # Validation
    if not version or not next_version:
        print("Error: Version fields are required.")
        sys.exit(1)
    if auth_choice == "1" and not token:
        print("Error: Personal Access Token is required.")
        sys.exit(1)
    if auth_choice == "2" and (not username or not password):
        print("Error: Username and Password are required.")
        sys.exit(1)

    # 2. Build JQL query
    jql = f"project = HDDS AND resolution = Unresolved AND (cf[12310320] = '{version}' OR fixVersion = '{version}')"
    print(f"\nQuerying Jira with JQL:\n  {jql}\n")

    # 3. Fetch/Mock issues
    if is_dry_run:
        print("[Dry-Run] Simulating API call to search endpoint...")
        issues = [
            {
                "key": "HDDS-1001",
                "fields": {
                    "summary": "Fix race condition in OM active lock acquisition",
                    "fixVersions": [{"name": version}, {"name": "Future-Release"}],
                    "customfield_12310320": None
                }
            },
            {
                "key": "HDDS-1002",
                "fields": {
                    "summary": "Enable container balancer check in Datanode",
                    "fixVersions": [{"name": version}],
                    "customfield_12310320": [{"name": version}]
                }
            },
            {
                "key": "HDDS-1003",
                "fields": {
                    "summary": "Implement protocol compatibility check CLI",
                    "fixVersions": [],
                    "customfield_12310320": [{"name": version}]
                }
            }
        ]
        total = len(issues)
    else:
        search_url = f"{JIRA_URL}/rest/api/2/search"
        search_payload = {
            "jql": jql,
            "maxResults": 100,
            "fields": ["key", "summary", "fixVersions", "customfield_12310320"]
        }
        
        status_code, response_text = make_request(
            search_url, method="POST", data=search_payload, username=username, password=password, token=token
        )
        
        if status_code == 401:
            print_401_help()
            sys.exit(1)
        elif status_code != 200:
            print(f"Error connecting to Jira ({status_code}): {response_text}")
            sys.exit(1)
            
        try:
            search_results = json.loads(response_text)
            issues = search_results.get("issues", [])
            total = search_results.get("total", 0)
        except Exception as e:
            print(f"Failed to parse Jira response: {e}")
            sys.exit(1)

    if not issues:
        print("No unresolved issues found matching the criteria. Nothing to do!")
        sys.exit(0)

    print(f"Found {total} issues to process. Showing first few:")
    for issue in issues[:10]:
        print(f" - {issue['key']}: {issue['fields'].get('summary')}")
    if total > 10:
        print(f" ... and {total - 10} more.")

    confirm = input(f"\nAre you sure you want to bulk-update these {total} issues? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Update cancelled by user.")
        sys.exit(0)

    # 4. Process each issue
    print("\nStarting bulk update...")
    success_count = 0
    fail_count = 0

    comment_body = (
        f"This issue has been bulk-deferred from target/fix version {version} to "
        f"the next minor release version {next_version} as part of the release preparation."
    )

    for issue in issues:
        key = issue["key"]
        issue_url = f"{JIRA_URL}/rest/api/2/issue/{key}"

        current_fix_versions = issue["fields"].get("fixVersions") or []
        updated_fix_versions = [
            {"name": f["name"]} for f in current_fix_versions if f["name"] != version
        ]

        update_payload = {
            "update": {
                "comment": [
                    {
                        "add": {
                            "body": comment_body
                        }
                    }
                ]
            },
            "fields": {
                "fixVersions": updated_fix_versions,
                "customfield_12310320": [{"name": next_version}]
            }
        }

        if is_dry_run:
            print(f"[Dry-Run] Simulating PUT request to update {key} with payload:")
            print(json.dumps(update_payload, indent=2))
            print(f" [+] Successfully simulated update of {key}")
            success_count += 1
        else:
            status_code, response_text = make_request(
                issue_url, method="PUT", data=update_payload, username=username, password=password, token=token
            )
            if status_code in (200, 204):
                print(f" [+] Successfully updated {key}")
                success_count += 1
            else:
                print(f" [-] Failed to update {key} ({status_code}): {response_text}")
                fail_count += 1

    print("==================================================")
    print("Bulk Update Complete Summary:")
    print(f"  Successfully updated: {success_count}")
    print(f"  Failed:               {fail_count}")
    print("==================================================")

if __name__ == "__main__":
    main()
