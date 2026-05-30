---
name: release-manager
description: >-
  Verify environment, sign, and build Apache Ozone releases. Use when performing
  release management, GPG verification, Jira prep, protolock updates, maven staging,
  release candidate builds, or using the Sherpa docker environment.
---

# Apache Ozone Release Manager Agent Playbook & Skill

> [!CAUTION]
> **MANDATORY SAFETY PROTOCOLS — READ BEFORE COMMENCING**
> 1. **100% Confidence Rule:** The Release Manager agent must **ONLY** proceed if it is 100% confident in the current state and execution of a command.
> 2. **Mandatory Halt & Human-in-the-Loop Approval:** The agent **MUST halt execution and ask the user for permission** to proceed if:
>    - Any command fails or returns a non-zero exit code.
>    - Any output, file structure, or system response diverges from the Release Manager Guide.
>    - There is any ambiguity, missing parameter, or environment inconsistency.
> 3. **No Automatic Bypasses:** The agent is strictly forbidden from making guesses, auto-fixing unexpected errors without reporting, or ignoring warnings.

---

## Phase 1: Environment & GPG Keys Verification

### 1.1 GPG Key Autodetect and Setup Guide
Before starting any release, you must have a GPG key configured for signing the release artifacts.

**Step 1.1.1: Verify GPG Installation and Keys**
Run the following command to check if you have existing GPG secret keys:
```bash
gpg --list-secret-keys
```
- **If keys are found:** Save your key ID (e.g., `8F9C7D4A`) to the environment variable:
  ```bash
  export CODESIGNINGKEY=<your_gpg_key_id>
  ```
- **If no keys are found or GPG is not configured:** You **must halt** and guide the user through creating one using the instructions below.

---

> [!NOTE]
> **PROACTIVE GPG SETUP GUIDE (Execute only if GPG is missing)**
>
> 1. **Generate a new GPG Key:**
>    Run `gpg --full-generate-key` and select:
>    - Key type: `RSA and RSA` (default)
>    - Keysize: `4096` bits
>    - Expiration: `0` (does not expire) or your preferred duration.
>    - Name/Email: Must match your Apache ID and commit address.
> 
> 2. **Export your Public Key:**
>    Get your Key ID from `gpg --list-secret-keys` (under `sec` / `pub`). Export it:
>    ```bash
>    gpg --armor --export $CODESIGNINGKEY
>    ```
> 
> 3. **Publish to KEYS file in Subversion:**
>    ```bash
>    svn co https://dist.apache.org/repos/dist/release/ozone ozone-KEYS-repo
>    cd ozone-KEYS-repo
>    gpg --list-sigs $CODESIGNINGKEY >> KEYS
>    gpg --armor --export $CODESIGNINGKEY >> KEYS
>    svn commit -m "ozone: adding key of <your_name> to the KEYS"
>    ```
> 
> 4. **Configure Git to use this GPG Key:**
>    ```bash
>    git config --global gpg.program "$(which gpg)"
>    git config --global user.signingKey $CODESIGNINGKEY
>    ```
> 
> 5. **Configure GPG agent agent.conf:**
>    - **Mac:** `echo "pinentry-program $(which pinentry-mac)" > ~/.gnupg/gpg-agent.conf`
>    - **Linux:** Add `allow-loopback-pinentry` to `~/.gnupg/gpg-agent.conf` and `use-agent` to `~/.gnupg/gpg.conf`.
>    - Reload agent: `gpgconf --kill gpg-agent`

---

### 1.2 Maven Credentials Setup
Verify that your local `~/.m2/settings.xml` has your Apache staging credentials correctly filled:
```xml
<settings>
  <servers>
    <server>
      <id>apache.staging.https</id>
      <username>YOUR_APACHE_ID</username>
      <password>YOUR_APACHE_PASSWORD</password>
    </server>
  </servers>
</settings>
```

---

### 1.3 Git & SSH Credentials Setup
Pushing branches and signed tags to GitHub / Apache Git repositories requires secure authentication (SSH keys or HTTPS Personal Access Tokens).

**Option A: Performing Git Push on the Host Machine (Recommended)**
Since all git commits, branching (`git checkout -b`), and tagging (`git tag -s`) can be performed on your host machine, it is highly recommended to perform git write operations on the host where your local SSH keys (`id_rsa`/`id_ed25519`) and git credential helpers are already loaded.

**Option B: Pushing from inside the Docker Container (SSH Agent Forwarding)**
If you are executing the entire release pipeline inside the Docker container and need to run `git push` or `git tag` there:
1. **Verify your local ssh-agent has your keys loaded** on the host:
   ```bash
   ssh-add -l
   ```
   *(If no keys are listed, add them using `ssh-add ~/.ssh/id_rsa` or your preferred key).*
2. **Mount the SSH Agent Socket** when starting the Docker container. Update your `docker run` command in Step 3.4.2 to include the `-v` and `-e` flags for `SSH_AUTH_SOCK`:
   ```bash
   docker run --rm -it \
     -v "$(pwd)":/workspace \
     -v "$HOME/.m2/settings.xml":/root/.m2/settings.xml:ro \
     -v "$HOME/.gnupg":/tmp/gnupg-host:ro \
     -v "$SSH_AUTH_SOCK":/tmp/ssh-agent-socket \
     -e SSH_AUTH_SOCK=/tmp/ssh-agent-socket \
     sherpa-arm bash -c "..."
   ```
   This securely forwards your host's SSH authentication socket, allowing git commands inside the container to authenticate natively and push to GitHub/Apache Git without exposing your private keys.

---

## Phase 2: Pre-Vote Preparation (On `master` branch)

### 2.1 Jira Preparation
1. Create a parent Jira (e.g. `HDDS-XXXXX: Apache Ozone <Version> Release`) to track all release candidate efforts.
2. **Bulk Move Unresolved Target Jiras:**
   Use the JQL search query below (replacing `<Version>` with target release version, e.g., `2.2.0`):
   ```text
   project = HDDS AND resolution = Unresolved AND (cf[12310320] = <Version> OR fixVersion = <Version>) ORDER BY priority DESC, updated DESC
   ```

   **Option A: Manual Bulk Change (Web UI)**
   *Instructions:* In Jira, click `Tools` -> `Bulk Change` -> `Select all` -> `Edit Issues` -> Clear the `Fix Version/s` field and set `Target Version/s` to the next minor version (e.g., `2.3.0`). Add a bulk comment notifying developers that the target version has been deferred unless it's critical.

   **Option B: Automated Local Script (Python & Secure)**
   If you want to automate this step securely without using the browser UI, you can run the zero-dependency Python script provided in the playbook (`sherpa/jira_release_prep.py`):
   ```bash
   python3 sherpa/jira_release_prep.py
   ```
   This script supports both standard credentials and **Personal Access Token (PAT) Bearer authentication** (strongly recommended and often required by Apache's secure Jira infrastructure). If a `401 Unauthorized` error occurs, the script automatically catches it and displays helpful instructions on how to generate a PAT in your Apache profile.

### 2.2 Protolock Compatibility Updates
Protolock is used to check backwards compatibility of network protocols. Run this script from the Ozone repo root to update the lock files (filtering for source files only, ensuring you are on the release branch matching the version being released, and strictly validating that no protocol changes are introduced in patch releases):
```bash
#!/usr/bin/env sh
if [ -z "$VERSION" ]; then
  echo "Error: VERSION environment variable is not set."
  exit 1
fi

current_branch=$(git rev-parse --abbrev-ref HEAD)
expected_branch="ozone-${VERSION%.*}"
if [ "$current_branch" != "$expected_branch" ]; then
  echo "Error: Current branch is '$current_branch', but expected '$expected_branch' for version $VERSION."
  exit 1
fi

# Determine if this is a patch/dot release (third digit > 0, e.g., 2.1.1)
patch_version=$(echo "$VERSION" | cut -d. -f3)
is_patch_release=false
if [ -n "$patch_version" ] && [ "$patch_version" -gt 0 ]; then
  is_patch_release=true
fi

for lock in $(find . -name proto.lock | grep "/src/"); do
  lockdir="$(dirname "$lock")"
  protoroot="$lockdir"/../proto
  if protolock status --lockdir="$lockdir" --protoroot="$protoroot"; then
    protolock commit --lockdir="$lockdir" --protoroot="$protoroot"
  else
    echo "protolock update failed for $protoroot"
    exit 1
  fi
done

# If this is a patch release, strictly enforce that no protocol files were changed
if [ "$is_patch_release" = true ]; then
  # Refresh git index to clear metadata/mtime touches from the container
  git update-index --refresh > /dev/null 2>&1 || true
  
  modified_locks=$(git diff --name-only | grep "proto.lock" || true)
  if [ -n "$modified_locks" ]; then
    echo "=================================================="
    echo "ERROR: Protocol changes detected in patch release!"
    echo "=================================================="
    echo "A dot/patch release ($VERSION) is strictly forbidden from having protocol changes."
    echo "The following lock files were modified:"
    echo "$modified_locks"
    echo "Please revert these protocol changes before continuing."
    exit 1
  else
    echo "Verified: No protocol changes detected in patch release $VERSION."
  fi
fi
```
Commit and submit a PR to the release branch `ozone-${VERSION%.*}`:
```bash
git commit -am "Update proto.lock for Ozone $VERSION"
```

### 2.3 Increment Version on Master Branch

> [!WARNING]
> **APPLICABILITY NOTE:** This step is **ONLY** applicable when preparing a new Major or Minor release. 
> For **Patch / Dot releases** (e.g. `2.1.1`), **SKIP this step completely** since the `master` branch was already bumped when the release branch was originally cut.

Once the protolock changes are merged, update the `master` branch version to the next snapshot (e.g. `2.3.0-SNAPSHOT` and update `<ozone.release>` to the next US National Park):
```bash
mvn versions:set -DnewVersion=2.3.0-SNAPSHOT
mvn versions:set-property -Dproperty=ozone.version -DnewVersion=2.3.0-SNAPSHOT
mvn versions:set-property -Dproperty=ozone.release -DnewVersion="Yosemite"
```
Submit a pull request to `master`. The parent of this PR will serve as the branch point.

### 2.4 Cut the Release Branch

> [!WARNING]
> **APPLICABILITY NOTE:** This step is **ONLY** applicable when preparing a new Major or Minor release. 
> For **Patch / Dot releases** (e.g. `2.1.1`), **DO NOT cut a new branch**. Instead, simply checkout and pull the **existing** release branch (e.g. `ozone-2.1` for version `2.1.1`):
> ```bash
> git checkout ozone-2.1
> git pull origin ozone-2.1
> ```

From the release point, branch off:
```bash
git checkout -b ozone-2.2
git push origin ozone-2.2
```

---

## Phase 3: Build & Package (On Release Branch `ozone-2.2`)

### 3.1 Setup Staging Variables
Set up environment variables for the release candidate build:
```bash
export VERSION=2.2.0
export RELEASE_DIR=~/ozone-release/
export CODESIGNINGKEY=<your_gpg_key_id>
export RC=0
mkdir -p "$RELEASE_DIR"
```

### 3.2 Update Version on Release Branch
Remove the `SNAPSHOT` suffix:
```bash
mvn versions:set -DnewVersion=$VERSION
mvn versions:set-property -Dproperty=ozone.version -DnewVersion=$VERSION
git commit -am "Update Ozone version to $VERSION"
```

### 3.3 Create Staging Git Tag
Create a signed git tag for the release candidate:
```bash
git tag -s "ozone-$VERSION-RC$RC" -m "Ozone $VERSION RC$RC"
```

### 3.4 Docker Container Environment Setup
To build release binaries with maximum compatibility and fidelity, use the provided Dockerfile under `sherpa/` to build the standalone compilation environment, mount the Ozone source directory, and share GPG keys for artifact signing.

**Step 3.4.1: Build the Docker Image**
Run the appropriate build command from the parent directory of `sherpa/` based on your platform architecture:

*   **For Intel/AMD64 (Default Release Build)**:
    ```bash
    docker build -t sherpa -f sherpa/Dockerfile sherpa/
    ```
*   **For Apple Silicon / ARM64 (Native ARM64 Build)**:
    ```bash
    docker build -t sherpa-arm -f sherpa/Dockerfile.arm64 sherpa/
    ```

**Step 3.4.2: Start the Container with Git Workspace, Maven Credentials, GPG Keys, and SSH Agent Mounted**
To compile, sign, deploy, and push from inside the container using the host's GPG keys, Maven staging credentials, and SSH authentication agent securely, mount your settings.xml, GPG directory, and SSH agent socket:

*   **Using Intel/AMD64 Image (`sherpa`)**:
    ```bash
    docker run --rm -it \
      -v "$(pwd)":/workspace \
      -v "$HOME/.m2/settings.xml":/root/.m2/settings.xml:ro \
      -v "$HOME/.gnupg":/tmp/gnupg-host:ro \
      -v "$SSH_AUTH_SOCK":/tmp/ssh-agent-socket \
      -e SSH_AUTH_SOCK=/tmp/ssh-agent-socket \
      sherpa bash -c "
        mkdir -p ~/.gnupg && \
        find /tmp/gnupg-host -maxdepth 1 -type f -exec cp {} ~/.gnupg/ \; && \
        if [ -d /tmp/gnupg-host/private-keys-v1.d ]; then \
          mkdir -p ~/.gnupg/private-keys-v1.d && \
          cp /tmp/gnupg-host/private-keys-v1.d/* ~/.gnupg/private-keys-v1.d/; \
          chmod 700 ~/.gnupg/private-keys-v1.d ~/.gnupg/private-keys-v1.d/*; \
        fi && \
        chmod 700 ~/.gnupg ~/.gnupg/* && \
        exec bash
      "
    ```
*   **Using Apple Silicon / ARM64 Image (`sherpa-arm`)**:
    ```bash
    docker run --rm -it \
      -v "$(pwd)":/workspace \
      -v "$HOME/.m2/settings.xml":/root/.m2/settings.xml:ro \
      -v "$HOME/.gnupg":/tmp/gnupg-host:ro \
      -v "$SSH_AUTH_SOCK":/tmp/ssh-agent-socket \
      -e SSH_AUTH_SOCK=/tmp/ssh-agent-socket \
      sherpa-arm bash -c "
        mkdir -p ~/.gnupg && \
        find /tmp/gnupg-host -maxdepth 1 -type f -exec cp {} ~/.gnupg/ \; && \
        if [ -d /tmp/gnupg-host/private-keys-v1.d ]; then \
          mkdir -p ~/.gnupg/private-keys-v1.d && \
          cp /tmp/gnupg-host/private-keys-v1.d/* ~/.gnupg/private-keys-v1.d/; \
          chmod 700 ~/.gnupg/private-keys-v1.d ~/.gnupg/private-keys-v1.d/*; \
        fi && \
        chmod 700 ~/.gnupg ~/.gnupg/* && \
        exec bash
      "
    ```

Once inside the container shell, verify that GPG works and shows your signing key:
```bash
gpg --list-secret-keys
```

### 3.5 Compile Release Artifacts
Run the complete compilation script inside the x86 container environment:
```bash
# Clean the repository completely
git reset --hard && git clean -dfx

# Perform the native build (signs the jars and generates dist and source tarballs)
mvn clean install -DskipTests -Psign,dist,src -Dtar -Dgpg.keyname="$CODESIGNINGKEY" -Drocks_tools_native

# Optional: Build native RPM and Debian packages
mvn clean package -Prpm -DskipTests=true -Drpm.release=1
mvn clean package -Pdeb
```

---

## Phase 4: Sign and Stage Release Candidates

### 4.1 Generate Checksums and Signatures
Copy generated tarballs to the local release directory and run signing commands:
```bash
cp hadoop-ozone/dist/target/ozone-*.tar.gz "$RELEASE_DIR"/
cd "$RELEASE_DIR"

# Generate GPG Detached Signatures (.asc)
for i in *.tar.gz; do
  gpg -u "$CODESIGNINGKEY" --armor --output "$i.asc" --detach-sig "$i"
done

# Generate SHA512 Checksums (.sha512)
for i in *.tar.gz; do
  sha512sum "$i" > "$i.sha512"
done

# Generate MDS file (.mds)
for i in *.tar.gz; do
  gpg --print-mds "$i" > "$i.mds"
done
```

### 4.2 Mandatory Sanity Verification Checklists

Before promoting to dev staging, the Release Manager **MUST** execute and pass all items:

- [ ] **GPG Signature Verification:**
  ```bash
  for x in *.tar.gz; do gpg --verify $x.asc $x; done
  ```
  *Expectation:* Must return `Good signature` matching your key fingerprint.
- [ ] **SHA-512 Checksum Verification:**
  ```bash
  sha512sum --check *.tar.gz.sha512
  ```
  *Expectation:* Must return `OK` for all files.
- [ ] **Release Contents Check:** Extract the binary tarball:
  - Check that the unzipped directory size and contents are complete.
  - Verify that the `docs/` folder exists and `docs/index.html` loads correctly.
- [ ] **Executable Command Check:** Run the binary locally or inside a container:
  ```bash
  ./bin/ozone version
  ```
  *Expectation:* Output must list correct version `2.2.0`, the correct national park name, a non-snapshot version of Ratis, and the precise Git hash.
- [ ] **Rat License Check:**
  Run the license audit script from the source directory:
  ```bash
  ./hadoop-ozone/dev-support/checks/rat.sh
  ```
  *Expectation:* No license violations.

---

## Phase 5: Upload Staging and Send Vote Email

### 5.1 Deploy Maven Staging Repository
From the release branch, build and upload artifacts to Apache Staging Repository:
```bash
mvn deploy -DdeployAtEnd=true -DskipTests -Psign,dist,src -Dtar -Dgpg.keyname="$CODESIGNINGKEY" -Drocks_tools_native
```
Log in to https://repository.apache.org/#stagingRepositories, find your staging repository `orgapacheozone-xxxx`, review the files, and click **Close**.

### 5.2 Upload Tarballs to ASF Dev SVN
Upload all tarballs, checksums, and signatures to Apache's dev Subversion repository:
```bash
svn checkout https://dist.apache.org/repos/dist/dev/ozone svn-dev-ozone
cd svn-dev-ozone
mkdir "$VERSION-rc$RC"
cp -v "$RELEASE_DIR"/* "$VERSION-rc$RC"/
svn add "$VERSION-rc$RC"
svn commit -m "Ozone $VERSION RC$RC"
```

### 5.3 Push the Git Tag
```bash
git push origin "ozone-$VERSION-RC$RC"
```

### 5.4 Draft and Send Vote Email
Send a vote email to `dev@ozone.apache.org` mailing list.

---

> [!NOTE]
> **VOTE EMAIL DRAFT TEMPLATE**
> 
> **Subject:** [VOTE] Release Apache Ozone 2.2.0 RC0
> 
> **Body:**
> Hello Ozone Devs,
> 
> I have created a release candidate for Apache Ozone 2.2.0. This is the first release candidate (RC0).
> 
> The release candidate tag on GitHub:
> https://github.com/apache/ozone/releases/tag/ozone-2.2.0-RC0
> 
> The Git commit hash for the tag:
> <TAG_COMMIT_HASH>
> 
> The source and binary tarballs are staged in Subversion:
> https://dist.apache.org/repos/dist/dev/ozone/2.2.0-rc0/
> 
> Staged Maven artifacts are available at Sonatype Staging:
> https://repository.apache.org/content/repositories/orgapacheozone-<REPO_ID>/
> 
> Public KEYS file containing GPG signing key:
> https://dist.apache.org/repos/dist/release/ozone/KEYS
> 
> Key fingerprint used to sign:
> <KEY_FINGERPRINT>
> 
> The list of Jiras fixed in this release can be found at:
> https://issues.apache.org/jira/issues/?jql=project%20%3D%20HDDS%20AND%20status%20in%20(Resolved%2C%20Closed)%20AND%20fixVersion%20%3D%202.2.0
> 
> Please vote on releasing this package as Apache Ozone 2.2.0.
> The vote will run for 7 days (ending on <VOTE_END_DATE>).
> 
> [ ] +1 Release this package
> [ ]  0 No opinion
> [ ] -1 Do not release (please explain why)
> 
> Thanks,
> <YOUR_NAME>

---

## Phase 6: Promoting and Finalizing the Release

### 6.1 Move SVN Artifacts to Release SVN
Move the staging candidate to the final official release SVN:
```bash
svn mv -m "Release ozone-$VERSION-rc$RC as ozone-$VERSION" \
  https://dist.apache.org/repos/dist/dev/ozone/"$VERSION-rc$RC" \
  https://dist.apache.org/repos/dist/release/ozone/"$VERSION"
```

### 6.2 Release Sonatype Maven Repository
Log in to https://repository.apache.org/#stagingRepositories, select `orgapacheozone-xxxx`, and click **Release**.

### 6.3 Push Final Signed Release Git Tag
```bash
git checkout "ozone-$VERSION-RC$RC"
git tag -s "ozone-$VERSION" -m "Ozone $VERSION release"
git push origin "ozone-$VERSION"
```

### 6.4 Update the Website and Documentation
1. Clone the `ozone-site` repository.
2. In `master` branch, add release notes and the release haiku image (see PR examples).
3. In `asf-site` branch, extract `docs/` folder from the release binary and commit it under `docs/2.2.0/`. Update `docs/current` symlink.
4. Run `hugo serve` to verify layout correctness.

### 6.5 Publish Docker Image
Tag and push the docker image in the `ozone-docker` repo:
```bash
git checkout ozone-latest
git merge --ff-only origin/latest
git push origin ozone-latest
git checkout -b "ozone-$VERSION"
git push origin "ozone-$VERSION"
```

### 6.6 Draft and Send Announcement Email

---

> [!NOTE]
> **ANNOUNCEMENT EMAIL DRAFT TEMPLATE**
> 
> **Subject:** [ANNOUNCEMENT] Apache Ozone 2.2.0 Released
> 
> **Body:**
> The Apache Ozone community is pleased to announce the release of Apache Ozone 2.2.0.
> 
> Apache Ozone is a redundant, distributed, and scalable object store for Hadoop and cloud-native environments. It is designed to scale to billions of objects and files.
> 
> High-level release notes can be found at:
> https://ozone.apache.org/release/2.2.0/
> 
> Downloads are available at the official downloads page:
> https://ozone.apache.org/downloads/
> 
> Documentation for version 2.2.0 is published at:
> https://ozone.apache.org/docs/2.2.0/
> 
> We would like to thank all the contributors who helped make this release possible!
> 
> Regards,
> The Apache Ozone Team
