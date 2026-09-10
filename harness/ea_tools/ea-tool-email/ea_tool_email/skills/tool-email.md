---
name: tool-email
description: "Send and read emails via SMTP/IMAP -- compose and send messages, read the inbox, search by criteria, or list available folders. WHEN to use: sending notifications or reports via email, reading inbox messages, searching for specific emails by sender/subject/date. WHEN NOT to use: for chat/messaging platforms (use the platform gateway tools), for file transfer (use ssh upload/download or cloud_storage), or for real-time communication (email is asynchronous). TIPS: use app-specific passwords (not the account password) for Gmail/Outlook; set use_tls=true for port 587 and use_ssl for port 993; keep max_emails low (10-20) to avoid large responses. PITFALLS: some providers block SMTP from unknown IPs; IMAP search criteria syntax varies by server; large attachments may exceed size limits."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# email

Send and read emails via SMTP/IMAP -- compose and send messages, read the inbox, search by criteria, or list available folders. WHEN to use: sending notifications or reports via email, reading inbox messages, searching for specific emails by sender/subject/date. WHEN NOT to use: for chat/messaging platforms (use the platform gateway tools), for file transfer (use ssh upload/download or cloud_storage), or for real-time communication (email is asynchronous). TIPS: use app-specific passwords (not the account password) for Gmail/Outlook; set use_tls=true for port 587 and use_ssl for port 993; keep max_emails low (10-20) to avoid large responses. PITFALLS: some providers block SMTP from unknown IPs; IMAP search criteria syntax varies by server; large attachments may exceed size limits.
