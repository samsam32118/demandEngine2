---
name: email-verify
description: Verify one or more email addresses using the QuickEmailVerification API. Use this skill whenever the user says "verify this email", "check if X@Y.com is valid", "is this email real", "validate these emails", "which of these emails are safe to send", "check email deliverability", or pastes a list of email addresses and asks if they're good. Trigger even if the user just says "can you check this email?" — if there's an email address in context, use this skill.
---

## Overview

Verify email addresses via the QuickEmailVerification REST API and return a clear, actionable summary. The goal is to tell the user whether each email is safe to send to, and why if not.

## API Key

Read the key from the environment variable `QUICKEMAILVERIFICATION_API_KEY`. If it's not set, check whether a `.env` file exists in the working directory and load it with:

```bash
export $(grep -v '^#' .env | xargs)
```

If still not found, ask the user to provide it.

## Verifying a single email

```bash
curl -s "https://api.quickemailverification.com/v1/verify?email=EMAIL&apikey=$QUICKEMAILVERIFICATION_API_KEY"
```

Replace `EMAIL` with the address to verify (URL-encode it if it contains special characters).

## Verifying multiple emails

Run one `curl` per email. If there are more than 5, run them in parallel using `&` and `wait`, or a simple shell loop with background jobs:

```bash
for email in email1@example.com email2@example.com; do
  curl -s "https://api.quickemailverification.com/v1/verify?email=$email&apikey=$QUICKEMAILVERIFICATION_API_KEY" &
done
wait
```

Collect and parse each response before presenting results.

## Response fields to care about

| Field | Meaning |
|---|---|
| `safe_to_send` | `"true"` = deliverable and not risky. The primary signal. |
| `result` | `valid`, `invalid`, or `unknown` |
| `reason` | Why it's invalid (e.g. `rejected_email`, `invalid_domain`, `low_quality`) |
| `disposable` | Throwaway inbox (Mailinator, etc.) |
| `accept_all` | Domain accepts all mail — delivery unconfirmed |
| `role` | Role address (info@, support@) — lower engagement expected |
| `free` | Free provider (Gmail, Yahoo, etc.) |
| `did_you_mean` | Suggested correction if the domain looks like a typo |

## Output format

Present results in a clean table. For a single email, a short paragraph is fine. For multiple, always use a table.

**Single email example:**
> **richard@quickemailverification.com** — Not safe to send  
> Reason: rejected_email (the mailbox does not exist or rejects mail)

**Multiple emails table:**

| Email | Safe to Send | Result | Notes |
|---|---|---|---|
| alice@example.com | ✓ Yes | valid | |
| bob@throwaway.io | ✗ No | invalid | Disposable address |
| info@bigcorp.com | ⚠ Maybe | valid | Role address, accept-all domain |

Use ✓ for safe, ✗ for not safe, ⚠ for `accept_all` or `unknown` results where delivery is uncertain.

If `did_you_mean` is non-empty, mention it: "Did you mean `corrected@domain.com`?"

## After presenting results

If any emails are invalid or risky, briefly note what the user might want to do (remove them from the list, check for typos, etc.). Keep it to one sentence — don't lecture.
