# SMTP Security, SPF, DKIM, and DMARC Requirements

**Domain**: `keplertechllc.com` / `keplertech.ae`  
**Application**: Kepler Tech Sales AI Commercial Assistant  
**Notification Source**: `sales-ai@keplertechllc.com`  

---

## 1. Overview
The Sales AI system sends automated, high-priority sales lead and human handoff notification emails to Kepler Tech sales desk (`sales@keplertechllc.com` / `sales@keplertech.ae`). To ensure 100% deliverability, prevent spoofing, and satisfy corporate mail server security policies, all outbound email dispatch must adhere to modern email authentication standards: **SPF**, **DKIM**, and **DMARC**.

---

## 2. Sender Policy Framework (SPF)
SPF prevents unauthorized servers from sending mail on behalf of the domain.

### DNS TXT Record Specification:
```text
Host: @ (or keplertechllc.com)
Type: TXT
TTL:  3600
Value: v=spf1 ip4:STATIC_SERVER_PUBLIC_IP include:_spf.google.com include:mailgun.org -all
```
- Replace `STATIC_SERVER_PUBLIC_IP` with the dedicated public IP of the Kepler Tech production host.
- `-all` (Hard Fail): Directs receiving mail transfer agents (MTAs) to reject any email claiming to be from `keplertechllc.com` that does not originate from authorized IPs or relay providers.

---

## 3. DomainKeys Identified Mail (DKIM)
DKIM provides cryptographic non-repudiation by digitally signing outbound email headers and body digests with an asymmetric private key.

### Configuration:
1. **Key Pair**: 2048-bit RSA key pair (`kepler_sales_ai_dkim.private` and `kepler_sales_ai_dkim.public`).
2. **Selector**: `salesai`
3. **Canonicalization**: `relaxed/relaxed`

### DNS TXT Record Specification:
```text
Host: salesai._domainkey.keplertechllc.com
Type: TXT
TTL:  3600
Value: v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...[PUBLIC_KEY_BASE64]...QAB
```

---

## 4. Domain-based Message Authentication, Reporting, and Conformance (DMARC)
DMARC ties SPF and DKIM together and instructs receiving mail servers on handling failures.

### DNS TXT Record Specification:
```text
Host: _dmarc.keplertechllc.com
Type: TXT
TTL:  3600
Value: v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s; rua=mailto:dmarc-reports@keplertechllc.com; pct=100
```
- `p=reject`: Highest security posture. Unaligned/spoofed emails are rejected outright.
- `adkim=s` & `aspf=s`: Strict alignment required between `From:` header and authenticated SPF/DKIM domains.
- `rua`: Aggregate delivery and failure telemetry sent to security operations.

---

## 5. Application-Level Enforcements
In [`app/notifications/salesperson.py`](file:///opt/basics/app/notifications/salesperson.py):
- **Mandatory TLS**: Outbound connections enforce `STARTTLS` using Python's `ssl.create_default_context()` with system certificate trust roots. Plaintext SMTP fallback is prohibited.
- **Header Sanitization**: All user-provided fields are stripped of newline (`\r\n`) characters before inclusion into email headers to prevent SMTP header injection attacks.
- **Body Truncation**: Customer context is capped to 500 characters to prevent SMTP body bomb/amplification attacks.
- **Retry Sweep & Permanent Failure Alerting**: If delivery fails across all channels, notifications are retried up to 3 times before transitioning to `permanent_failure` and triggering critical alerts.
