# Data & Business Facts TODO — Kepler Tech LLC Confirmation Catalog

**Document Version**: 2.1 (WP0.1 Live Site Reconciliation)  
**Date**: 2026-10-26  
**Status**: Open Business Items & Conflicts Requiring Kepler Tech Confirmation  
**Instruction**: Do NOT invent answers. All unconfirmed terms have `confirm_before_use: true` in `data/policies.json` and require sales desk confirmation.

---

## 1. Catalog of Open Business Decisions & Source Conflicts

| Item # | Topic | Live Site / Official Data | Conflict / Uncertainty | Target Location |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Cleaning Pen Price** | `190.00 AED` | Live product page on `keplertechllc.com` lists **190.00 AED**. The older evaluation benchmark value of 95.00 AED is incorrect. Catalog is set to 190.00 AED. | `data/products.json` (`CITIZEN-PEN.price`) |
| **2** | **Contact Numbers** | Multi-Source (4 Numbers) | At least 4 distinct phone numbers appear across `keplertechllc.com` and `keplertech.ae`: Landline `00971 4 323 1008`, Mobile `+971 50 890 1641`, plus alternate sales/support lines. Which specific numbers are designated for **sales**, **order tracking**, and **WhatsApp bot routing**? | `app/config.py`, `data/policies.json` |
| **3** | **Delivery Coverage Conflict** | GCC vs Africa | Official terms and conditions (dated 2023-09-19) state delivery is restricted to GCC countries only. However, marketing and shipping pages list African export markets (e.g., Kenya, Nigeria). Inquiries outside GCC must be routed to human sales handoff. | `data/policies.json` (`delivery_charges`) |
| **4** | **Personal vs Commercial Terms**| Terms Conflict | Website terms and conditions state services and products are for *"personal and non-commercial use only"*, whereas Kepler Tech's primary market for CX-02 is commercial B2B (photo booths, event studios, retail kiosks). Legal terms confirmation required. | `data/policies.json` (`terms_of_service`) |
| **5** | **Luster Finish Support** | Spec Sheet Conflict | The product description text mentions "glossy, matte, and luster" finishes, but the official Citizen CX-02 specification table only certifies Glossy and Matte from standard media. Is Luster supported via driver dithering? | `data/kb/CX-02/03_media_formats.md` |
| **6** | **Media Set Print Yields** | 4x6 & 6x8 Unverified | 4x6" (800 prints) and 6x8" (400 prints) remain unverified estimates ($2 \times 400$ and $2 \times 200$). 5x7" (460 prints) is verified in the datasheet. Requires factory confirmation. | `data/products.json` (`prints_verified`) |
| **7** | **UAE VAT Treatment** | `null` (Unknown) | UAE law mandates 5% VAT. Website checkout includes tax, but B2B invoices may quote net. Left `null` in `data/policies.json`. | `.env` / `app/config.py` (`VAT_RATE`, `PRICES_INCLUDE_VAT`) |
| **8** | **Hardware Warranty** | `null` (Unknown) | Citizen datasheet specifies 2-year manufacturer warranty on head/engine. Does Kepler Tech offer local Dubai warranty service or distributor swap? | `data/policies.json` (`warranty`) |
| **9** | **UAE Delivery Rate** | `AED 10` flat rate | Terms specify AED 10 flat rate across the UAE, with 1-2 business days processing. Pickup available at Bur Dubai showroom. Marked `confirm_before_use: true`. | `data/policies.json` (`delivery_charges`) |
| **10** | **Payment & Cancellation** | Paid at order | Credit Card, Debit Card, and PayPal accepted at order time; 24-hour cancellation before dispatch. Refund to original card up to 45 days. Marked `confirm_before_use: true`. | `data/policies.json` (`payment_methods`, `return_policy`) |
| **11** | **Returns Policy** | Defective / unopened | Must notify Kepler within 2 days of delivery; packaging unopened; approval required. Marked `confirm_before_use: true`. | `data/policies.json` (`return_policy`) |
| **12** | **Third-Party Media Policy**| Handoff | Use of non-Citizen paper/ribbon voids printhead warranty? Awaiting policy clarification. | `data/policies.json` (`third_party_media`) |
| **13** | **Large-Quantity Threshold** | Default: 10 units | Inquiries exceeding 10 printers trigger immediate corporate management handoff. | `config/scope.yaml` (`large_quantity_handoff_threshold`) |
| **14** | **Automated as_of Date Sync (WP11)** | Configurable sync source | Do not touch `as_of` by hand. In WP11 (Price/stock sync), automated feed/crawler will update `as_of` timestamps dynamically from the live WooCommerce shop or inventory feed. | `data/products.json` (`as_of`) |
