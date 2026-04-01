---
name: vps-setup
description: >
  Guided step-by-step setup of Claude Code on a VPS via SSH. Use when the user asks to
  "set up Claude Code on my VPS", "install claude on server", "configure VPS for claude",
  "SSH setup for claude code", "install claude on remote server", "set up headless claude",
  or wants to prepare a VPS to run Claude Code with Telegram.
user-invocable: true
allowed-tools:
  - Read
  - Bash(ssh *)
  - Bash(ssh-keygen *)
  - Bash(ssh-copy-id *)
  - Bash(cat *)
  - Bash(ls *)
---

# /sentinel:vps-setup — Install Claude Code on a VPS

Guided walkthrough to install and authenticate Claude Code on a remote server via SSH.
The user runs commands from their local machine (Git Bash, Terminal, etc.) connecting
to the VPS. Claude guides each step and verifies before moving on.

Arguments passed: `$ARGUMENTS`

---

## Prerequisites to confirm with user

Before starting, collect:
1. **VPS IP address** — ask if not provided
2. **SSH access** — ask which user they connect as (root? ubuntu? other?)
3. **SSH key location** — default `~/.ssh/id_ed25519`, ask to confirm
4. **Operating system** — assume Ubuntu/Debian unless stated otherwise

Test connectivity first:
```
ssh -i <key_path> <user>@<ip> "echo 'Connection OK'"
```

If this fails, troubleshoot SSH before proceeding.

---

## Step 1: Create a non-root user

**Why this is required:** Claude Code blocks `--dangerously-skip-permissions` when running
as root for security reasons. The Telegram gateway needs this flag, so a non-root user
is mandatory — not optional.

If user is already connecting as a non-root user, skip to Step 2.

Guide the user to run these commands on the VPS:

```bash
# Connect as root (or current user with sudo)
ssh -i <key_path> root@<ip>

# Create the claude user
sudo adduser claude --disabled-password --gecos ""
sudo usermod -aG sudo claude

# Allow passwordless sudo (needed for service management)
echo "claude ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/claude

# Copy SSH key for the new user
sudo mkdir -p /home/claude/.ssh
sudo cp ~/.ssh/authorized_keys /home/claude/.ssh/
sudo chown -R claude:claude /home/claude/.ssh
sudo chmod 700 /home/claude/.ssh
sudo chmod 600 /home/claude/.ssh/authorized_keys
```

**Verify:** `ssh -i <key_path> claude@<ip> "whoami"` should return `claude`.

---

## Step 2: Install Claude Code CLI

```bash
ssh -i <key_path> claude@<ip>

# Install Claude Code (native binary, no Node.js needed)
curl -fsSL https://claude.ai/install.sh | bash

# Add to PATH for current session
export PATH="$HOME/.local/bin:$PATH"

# Verify
claude --version
```

---

## Step 3: Authenticate Claude Code

This is the trickiest step on a headless server. The OAuth flow requires a browser
which the VPS doesn't have.

**Guide the user through this exact flow:**

1. On the VPS (via SSH), run:
   ```bash
   claude auth login
   ```

2. Claude Code will display a URL like:
   ```
   https://claude.com/cai/oauth/authorize?code=true&client_id=...
   ```

3. **Tell the user:** "Copy that URL and open it in your local browser (not on the VPS)."

4. After authenticating in the browser, they'll see a code. **Tell the user:**
   "Go back to the SSH terminal and paste the code. The text won't appear as you
   type — that's normal, it's hidden like a password. Just paste and press Enter."

5. **Verify:** `claude auth status` should show `loggedIn: true`.

**Common issues:**
- If paste doesn't work in Git Bash: right-click to paste instead of Ctrl+V
- If the code expires: run `claude auth login` again for a fresh URL
- The code is one-time use — each `claude auth login` generates a new one

---

## Step 4: Install Bun runtime

The gateway and compact job are TypeScript files that run on Bun.

```bash
# Still on the VPS as claude user
curl -fsSL https://bun.sh/install | bash

# Add to PATH
export PATH="$HOME/.bun/bin:$PATH"

# Verify
bun --version
```

---

## Step 5: Enable user lingering

This keeps systemd user services running after SSH logout — critical for a VPS.

```bash
sudo loginctl enable-linger claude
```

**Verify:** `loginctl show-user claude | grep Linger` should show `Linger=yes`.

---

## Step 6: Configure Claude Code settings

Create the settings file:

```bash
mkdir -p ~/.claude
cat > ~/.claude/settings.json << 'EOF'
{
  "model": "claude-sonnet-4-6",
  "effortLevel": "high",
  "permissions": {
    "defaultMode": "bypassPermissions"
  },
  "enabledPlugins": {
    "telegram@claude-plugins-official": true
  },
  "env": {
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "60"
  }
}
EOF
```

---

## Step 7: Enable Telegram plugin

The user needs a Telegram bot token from [@BotFather](https://t.me/BotFather).
They should create the bot from their phone or desktop Telegram (not from the VPS).

Once they have the token, run on the VPS:

```bash
claude
# Inside Claude Code, run:
# /telegram:configure <bot-token>
```

Or use `/sentinel:configure <bot-token>` if this plugin is installed.

---

## Step 8: Verify everything

Run these checks and report results:

```bash
claude --version          # Should show version
claude auth status        # Should show loggedIn: true
bun --version            # Should show version
loginctl show-user claude | grep Linger  # Should show Linger=yes
```

**Next step:** Tell the user to run `/sentinel:deploy` to install the persistent
gateway, systemd services, compact job, and bot identity.

---

## Implementation notes

- All commands should be run as the `claude` user, not root
- The user is typing commands manually — don't try to execute SSH commands automatically
- If the user already has Claude Code installed, skip to the missing steps
- PATH additions should be persisted in `~/.bashrc`
- The VPS must have outbound HTTPS access (port 443) for Claude API and Telegram API
