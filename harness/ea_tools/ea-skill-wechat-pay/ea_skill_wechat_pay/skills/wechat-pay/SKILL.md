---
name: wechat-pay
description: WeChat Pay operations - QR code payment, transfers, red packets, bill management
metadata:
  source: clawhub
  tags: wechat-pay
user_invocable: true
hidden: true
context: inline
---

## WeChat Pay Operations Guide

### When to Use
- Make or receive payments via WeChat Pay (QR code scan, merchant payment, person-to-person transfer)
- Send or receive red packets during festivals or special occasions
- Manage WeChat Pay balance, transaction history, and linked bank cards
- Use WeChat Pay for online purchases, utility bills, and mobile top-ups

### Key Operations
**1. QR Code Payment**
- Merchant scans you: WeChat -> "+" -> "Pay" -> show payment QR code
- You scan merchant: WeChat -> "Discover" -> "Scan" -> point at merchant's QR -> enter amount -> confirm

**2. Person-to-Person Transfer**
- WeChat -> chat with contact -> "+" -> "Transfer" -> enter amount -> confirm

**3. Red Packets**
- WeChat -> chat -> "+" -> "Red Packet" -> enter amount and recipients -> send
- Normal (fixed amount per person) or Lucky (random amount)

**4. Bill Payment**
- WeChat -> "Me" -> "Pay" -> "Utilities" -> select bill type -> enter account number -> pay

### Common Pitfalls
- Transfers are instant and irreversible; verify recipient before confirming
- Never send red packets to strangers claiming to be customer service
- WeChat Pay requires at least one linked bank card for most operations
