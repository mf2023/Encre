---
name: payment-alipay
description: Alipay operations guide - send/receive money, scan QR codes, pay bills, transfer, use Alipay for shopping, check balance, understand Alipay ecosystem (Alipay app, AlipayHK, Alipay+)
aliases: [alipay, zhifubao, alipay-payment, alipay-transfer]
when_to_use: ""
argument_hint: "[Alipay operation request: what to do, amount, recipient]"
user_invocable: true
hidden: true
context: inline
---

## Alipay Operations Guide

You are helping the user operate Alipay (支付宝): **{{args}}**

### When to Use
- Send or request money via Alipay (transfer to Alipay account, bank card, or QR code)
- Scan a QR code to pay at a merchant (offline or online)
- Pay bills (utilities, phone top-up, credit card, education, fines) via Alipay
- Check Alipay balance, transaction history, or Yu'e Bao (余额宝) balance
- Use Alipay for online shopping (Taobao, Tmall, Fliggy, Ele.me, etc.)
- Transfer money between Alipay and bank accounts (withdraw or top-up)
- Understand Alipay features: Huabei (花呗), Jiebei (借呗), Yu'e Bao, insurance, donations
- Use Alipay overseas (Alipay+, AlipayHK, cross-border payments)

### When NOT to Use
- **WeChat Pay operation** -> `payment-wechat-pay` (WeChat Pay has different UI, limits, and merchant network)
- **Online banking** -> `banking-online` (bank transfers outside Alipay)
- **General financial advice** -> just answer directly (this skill is for *operating* Alipay, not financial planning)
- **Tax or legal questions about payments** -> the user needs a professional, not an operation guide

### Key Operations

**1. Send/Transfer Money**
- **To Alipay account**: need recipient's Alipay ID (phone number, email, or Alipay account name). Open Alipay app -> Transfer -> Transfer to Alipay account -> enter amount -> confirm with password/face.
- **To bank card**: Open Alipay app -> Transfer -> Transfer to bank card -> enter card number, bank name, recipient name -> confirm. Takes 2 hours to 2 business days depending on bank and time.
- **Via QR code**: the sender scans the recipient's收款码 (collection QR). Open Alipay -> Scan -> point at the QR code -> enter amount -> confirm.
- **Daily limits**: unverified accounts ~5000 RMB/day; verified real-name accounts up to 200,000 RMB/day (varies). Larger amounts need bank transfer instead.

**2. Pay at a Merchant (Offline)**
- **Merchant scans you**: Open Alipay -> click "Pay/付钱" -> show your payment QR code to the merchant's scanner. The merchant enters the amount, you confirm on your phone.
- **You scan the merchant**: Open Alipay -> Scan -> point at the merchant's收款码 (collection QR) -> enter amount -> confirm with password/face/fingerprint.
- **Sound Wave Pay (声波支付)**: rare now; used in vending machines. Open Alipay -> Pay -> click "Sound Wave/声波付" -> hold phone near the receiver.
- **NFC**: some POS terminals support Alipay NFC. Unlock phone with NFC enabled -> tap near the POS terminal.

**3. Pay Bills (生活缴费)**
- Open Alipay app -> "Life Payment/生活缴费" -> select bill type (water, electricity, gas, phone, internet, property management).
- Enter the account number (户号 for utilities, phone number for mobile top-up) -> enter amount -> confirm.
- Can set up auto-pay (自动缴费) for recurring bills.
- Credit card repayment: Alipay -> "Credit Card Repayment/信用卡还款" -> select card -> enter amount. Free for most cards; some charge 0.1% fee.

**4. Yu'e Bao (余额宝)**
- Money market fund integrated with Alipay. Money in Yu'e Bao earns interest and can be used for payments directly.
- **Deposit**: Alipay -> Yu'e Bao -> Transfer In. Instant from Alipay balance; 1 business day from bank card.
- **Withdraw**: Alipay -> Yu'e Bao -> Transfer Out. To Alipay balance (instant); to bank card (next business day for same bank).
- **Daily limit**: 10,000 RMB fast-withdraw; larger amounts take 1-2 business days.

**5. Huabei (花呗) / Jiebei (借呗)**
- **Huabei**: credit product (like a credit card). Use Alipay with Huabei as payment method -> pay later (next month, or installment). Check Huabei额度 (credit limit) in Alipay -> "My/我的" -> "Huabei/花呗".
- **Jiebei**: loan product. Borrow cash directly to your Alipay balance or bank card. Alipay -> "Jiebei/借呗" -> enter amount -> choose repayment period -> confirm. Interest varies by credit score.
- **Warning**: both affect your credit score (芝麻信用). Late payments damage credit. Use responsibly.

**6. Alipay Cross-Border / Overseas**
- **Alipay+**: accepted at many overseas merchants (Japan, Korea, SE Asia, Europe). Open Alipay -> scan the merchant's Alipay+ QR code. Exchange rate is applied automatically.
- **AlipayHK**: Hong Kong version. Separate app, supports HKD. Can transfer between Alipay and AlipayHK via AlipayHK app.
- **Overseas bank card top-up**: some overseas cards (Visa, Mastercard) can top up Alipay for cross-border use. Check the "Cards" section in Alipay app.

**7. Security & Settings**
- **Payment password**: 6-digit PIN, separate from login password. Change in Alipay -> Settings -> Security.
- **Face recognition**: supports face ID for payments on supported phones. Alipay -> Settings -> Security -> Face Recognition.
- **Account protection**: Alipay -> "Security Center/安全中心" -> check account security status, device management, login history.
- **Report fraud**: if you suspect a fraudulent transaction, report immediately via Alipay -> "My/我的" -> "Customer Service/客服" -> "Report Fraud/举报诈骗".

### Common Pitfalls
- **Sending to the wrong account** - Alipay transfers are instant and irreversible once confirmed. Always triple-check the recipient's Alipay ID/phone number before confirming. There is no "recall" feature.
- **Assuming real-name limits are higher than they are** - an unverified account has strict sending/receiving limits. Verify real-name (实名认证) with ID card to raise limits.
- **Ignoring the Yu'e Bao withdrawal limit** - fast-withdraw from Yu'e Bao is capped at 10,000 RMB/day. If you need more, plan ahead and use the slower "regular withdrawal" (1-2 business days).
- **Using the wrong QR code type** - a 收款码 (collection QR) is for others to pay you; a 付款码 (payment QR) is for you to pay merchants. Showing the wrong one confuses the transaction.
- **Scam: fake refund/invoice QR codes** - never scan a QR code sent by someone claiming to "refund" or "verify" an account. Only scan QR codes at trusted merchants and official Alipay channels.
- **Huabei installment interest hidden** - the "0% interest" offer is for specific merchants/short periods. Check the actual APR (年化利率) before choosing installment; it can be 15-20%+.
- **Cross-border exchange rate surprise** - Alipay+ applies its own exchange rate, which may be less favorable than the market rate. Check the rate before paying; sometimes a local credit card is cheaper.
- **Forgetting to check the payment method** - Alipay defaults to the last used payment method. Before a large payment, check whether it's coming from balance, Yu'e Bao, bank card, or Huabei - the fee and limit differ.

### Pairing with Other Tools
- `web_search` - search for Alipay official help pages, latest fee schedules, and merchant QR code verification
- `web_fetch` - read Alipay's official help documentation (help.alipay.com) for specific feature details
- `travel-destination` - combine with destination info if the user is traveling and needs to understand Alipay acceptance abroad
- `payment-wechat-pay` - for WeChat Pay operations (complementary, not a replacement)
