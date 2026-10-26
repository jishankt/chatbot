# Out-of-Scope & Followup Items (Technical Debt Tracker)

**Document Purpose**: Record issues found during implementation that are outside the current work package scope or require stakeholder input, rather than silently modifying them.

---

## Tracked Items

| ID | Category | Description | Status / Next Step |
| :---: | :--- | :--- | :--- |
| **FOL-01** | **Contact Numbers** | Kepler Tech maintains two separate web properties (`keplertechllc.com` and `keplertech.ae`) with differing landline and mobile numbers. Currently using `00971 4 323 1008` and `+971 50 890 1641`. | Awaiting user/client confirmation in `docs/DATA_TODO.md`. |
| **FOL-02** | **Cleaning Pen Price** | Listed at 190 AED on Kepler Tech product page, but older evaluation benchmark expected 95 AED. Catalog retained at 190 AED; eval row aligned with catalog and logged. | Awaiting client confirmation. |
| **FOL-03** | **Data Retention Period** | Personal data retention set to default 90 days. Flagged as a decision for compliance with UAE Federal Decree-Law No. 45/2021 on Personal Data Protection (PDPL). | Flagged as client policy decision. |
| **FOL-04** | **Large-Quantity Handoff** | Added configurable threshold `large_quantity_handoff_threshold: 10` in `config/scope.yaml`. Commercial orders exceeding 10 printers trigger immediate handoff. | Configurable parameter; default 10 units. |
| **FOL-05** | **WP10-WP13 In Master Plan**| User requested inclusion of WP10 (Handoff delivery), WP11 (Price sync), WP12 (Observability), WP13 (Consent & WhatsApp STOP). All 4 have been added to the master plan for execution after WP9. | Included in roadmap. |
