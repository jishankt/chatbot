# Data & Business Facts TODO — Kepler Tech LLC Confirmation Catalog

**Document Version**: 1.0  
**Date**: 2026-10-26  
**Auditor**: Principal Systems Engineer  
**Purpose**: Catalogue of commercial policies and technical business facts requiring formal confirmation from Kepler Tech LLC management prior to production launch.

---

## 1. Summary of Business Decisions Required

| Item # | Business Fact | Current System State | Conflict / Uncertainty Source | Target File Location |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **UAE VAT Treatment** | `null` (Unknown) | UAE law mandates 5% VAT. Does Kepler Tech quote B2B prices inclusive or exclusive of VAT? | `.env` / `app/config.py` (`VAT_RATE`, `PRICES_INCLUDE_VAT`) |
| **2** | **Cleaning Pen Price** | `190.00 AED` | Kepler website lists 190.00 AED; older price sheet lists 95.00 AED | `data/products.json` (`CITIZEN-PEN.price`) |
| **3** | **4x6" Media Yield** | `800 prints` (Estimated) | Datasheet only certifies 5x7 (460 prints). 4x6 estimate is $2 \times 400$ | `data/products.json` (`CX2-MS46-2PC.prints_verified`) |
| **4** | **6x8" Media Yield** | `400 prints` (Estimated) | Estimate is $2 \times 200$. Needs factory verification | `data/products.json` (`CX2-MS68-2PC.prints_verified`) |
| **5** | **Warranty Coverage** | `null` (Handoff) | Official Citizen datasheet states 2-year warranty on printer / printhead. Does Kepler offer local UAE warranty? | `data/policies.json` (`warranty`) |
| **6** | **Delivery Charges** | `null` (Handoff) | Free delivery in Dubai? Flat rate for Northern Emirates / Abu Dhabi? | `data/policies.json` (`delivery_charges`) |
| **7** | **Delivery Timeline** | `null` (Handoff) | Same-day in Dubai? 24-48 hours for other Emirates? | `data/policies.json` (`delivery_time`) |
| **8** | **Payment Methods** | `null` (Handoff) | Cash on Delivery (COD), Corporate Cheque, Bank Transfer, or Credit Card? | `data/policies.json` (`payment_methods`) |
| **9** | **Return & Refund** | `null` (Handoff) | 7-day or 14-day return for unopened boxes? Restocking fee? | `data/policies.json` (`return_policy`) |
| **10** | **6x9" Media Ordering** | Unsupported (Handoff) | Hardware supports 6x9 (180 prints/roll). Does Kepler take special import orders? | `data/products.json` (`unsupported_media.6x9`) |
| **11** | **Luster Finish Support**| Documented in KB | Datasheet lists Glossy and Matte. Does firmware produce Luster finish? | `data/kb/03_media_formats.md` |

---

## 2. Detailed Technical & Configuration Specifications

### Item 1: UAE VAT Treatment
- **Current Behavior**: If `VAT_RATE` and `PRICES_INCLUDE_VAT` are undefined, quotes state *"VAT: Consult sales desk for applicable tax treatment"*.
- **Required Action**: Set configuration in `.env` based on Kepler's tax invoice format:
  ```bash
  # Option A: Prices are EXCLUSIVE of 5% VAT (Standard UAE B2B)
  VAT_RATE=0.05
  PRICES_INCLUDE_VAT=false

  # Option B: Prices are INCLUSIVE of 5% VAT (Retail format)
  VAT_RATE=0.05
  PRICES_INCLUDE_VAT=true
  ```

---

### Item 2: Citizen Thermal Printhead Cleaning Pen Price
- **File**: `data/products.json:L71-L82`
- **Current JSON Entry**:
  ```json
  "CITIZEN-PEN": {
    "sku": "CITIZEN-PEN",
    "name": "Citizen Thermal Head Cleaning Pen",
    "category": "accessory",
    "price": 190.0,
    "old_price": null,
    "in_stock": true,
    "to_confirm": true,
    "to_confirm_note": "Kepler page lists 190 AED; another document notes 95 AED. Recorded as 190 AED.",
    "url": "https://www.keplertechllc.com/product/citizen-cx-02-printhead-cleaning-pen/"
  }
  ```
- **Required Action**: Update `price` to either `190.0` or `95.0`, remove `to_confirm: true`, and adjust `data/eval/questions.jsonl` expectations.

---

### Items 3 & 4: Media Set Print Yields (4x6" and 6x8")
- **File**: `data/products.json:L22-L34`, `L48-L60`
- **Current Status**:
  * `CX2-MS46-2PC`: 800 prints per box (2 rolls $\times$ 400). Unverified estimate.
  * `CX2-MS57-2PC`: 460 prints per box (2 rolls $\times$ 230). Verified in official Citizen datasheet.
  * `CX2-MS68-2PC`: 400 prints per box (2 rolls $\times$ 200). Unverified estimate.
- **Required Action**: If Citizen or Kepler confirms exact yield counts, change `"prints_verified": true` and clear `"estimate_note": null`.

---

### Items 5 through 9: Commercial Policy Templates
- **File**: `data/policies.json`
- **Current Status**: All set to `null` to force human handoff.
- **Proposed Completed Structure Once Kepler Tech Confirms**:
  ```json
  {
    "company_contact": {
      "name": "Kepler Tech LLC",
      "address": "D79 Khalid Bin Waleed Road, Dubai",
      "phone": "00971 4 323 1008",
      "whatsapp": "+971 50 890 1641",
      "hours": "Mon-Fri 8:30-17:30, Sat 8:30-13:00"
    },
    "warranty": {
      "duration": "1 Year Kepler Local Warranty / 2 Years Manufacturer Warranty on Printhead",
      "coverage": "Hardware defects and thermal printhead (up to 50,000 cuts or 24 months)",
      "service_location": "Kepler Tech Service Center, Bur Dubai"
    },
    "delivery_time": {
      "dubai": "Same-day or next-business-day delivery",
      "other_emirates": "1 to 2 business days (Abu Dhabi, Sharjah, Ajman, RAK, Fujairah)"
    },
    "delivery_charges": {
      "free_threshold": 1000.0,
      "standard_fee": 35.0,
      "currency": "AED",
      "note": "Free delivery across Dubai for orders exceeding 1,000 AED."
    },
    "payment_methods": [
      "Bank Transfer (EFT)",
      "Cash on Delivery (Dubai only)",
      "Credit Card (Visa / Mastercard at Showroom)",
      "Corporate Purchase Order (Approved B2B accounts)"
    ],
    "return_policy": {
      "window_days": 7,
      "condition": "Unopened, original packaging with all factory seals intact.",
      "consumables": "Media boxes and opened printheads are strictly non-refundable."
    },
    "installation": {
      "provided": true,
      "charge": "Free phone/remote setup; on-site engineer visit available in Dubai for 250 AED."
    },
    "support_terms": {
      "hours": "Mon-Fri 8:30-17:30, Sat 8:30-13:00",
      "helpline": "00971 4 323 1008"
    },
    "vat_treatment": {
      "rate": 0.05,
      "inclusive": false,
      "tax_registration_number": "TRN-100XXXXXXXXXXXX"
    }
  }
  ```

---

### Item 10: 6x9" Media Ordering Policy
- **Hardware Capability**: Citizen CX-02 hardware engine natively supports 6x9" roll paper (180 prints per roll).
- **Kepler Stock**: Kepler does not stock `CX2-MS69-2PC`.
- **Confirmation Needed**: Can Kepler accept indent orders for 6x9 media (e.g. minimum order 10 cartons), or should customers be redirected to standard 6x8 media?

---

### Item 11: Luster Finish Capability
- **Datasheet**: Citizen CX-02 datasheet states "Glossy and Matte finishes available from the same media".
- **Product Page**: Mentions "glossy, matte, and luster".
- **Confirmation Needed**: Does CX-02 driver offer a third "luster" dithering mode via driver firmware, or is it strictly two finishes (glossy and matte)?
