# AGENTS.md - Rules for cx02-sales-ai

## Project Scope
This sales assistant is built for Kepler Tech LLC (Dubai) to assist business customers (event companies, photo booth operators, freelance photographers, digital studios, retail kiosks) across the GCC and Africa.
- **Initial Active Deployment**: Citizen CX-02 photo printer (`CX-02`) and its official accessories:
  1. `CX2-MS46-2PC` (4x6" media set - 800 prints, unverified estimate)
  2. `CX2-MS57-2PC` (5x7" media set - 460 prints, verified)
  3. `CX2-MS68-2PC` (6x8" media set - 400 prints, unverified estimate)
  4. `CX-02-BAG` (Citizen CX-02 Protective carry bag)
  5. `CITIZEN-PEN` (Citizen thermal printhead cleaning pen)
- **Extensible Architecture**: Engine is product-agnostic; scope is governed by `config/scope.yaml`. Additional products are added only after passing all evaluation gates.

## Non-Negotiable Operational Rules (HARD RULES)
1. **Commercial Authority**: The LLM never produces prices, stock, delivery, warranty, VAT, discounts, totals, links, or policy statements. Those come ONLY from tools reading data files (`data/products.json`, `data/policies.json`), rendered into the reply from tool output.
2. **Strict Grounding Validation**: Every number and commercial claim in a reply MUST exist in the tool output, the retrieved text, or the customer's own message. A validator enforces this. On failure, use a deterministic template.
3. **Constrained LLM Operations**: The LLM may only (a) classify and extract entities as structured JSON, and (b) phrase replies from provided facts. If the facts do not answer the question, say so and offer a human specialist. Never guess.
4. **Configuration-Driven Scope**: Scope comes from configuration (`config/scope.yaml` active_products list), not hard-coded regexes. Inactive products and competitors: refuse politely and offer a human.
5. **No Defaulting to Products**: Unknown or ambiguous product inquiries must prompt a clarifying question or be refused politely. Never default to a product.
6. **Unknown Policy Safeguard**: Unknown policies are `null` in `data/policies.json` and must trigger an immediate human handoff.
7. **VAT Treatment Safeguard**: VAT is never stated as fact unless `VAT_RATE` and `PRICES_INCLUDE_VAT` are both configured.
8. **Fact Integrity & Labeling**: Unverified facts (prints per media set for 4x6 and 6x8) are labeled as estimates. Prices carry an `as_of` date; stale prices ($>14$ days) add a "please confirm" note.
9. **Data Protection & Privacy**: Personal data (phone, name, chat text) is protected behind authenticated endpoints, with configurable retention (default 90 days, flagged as a decision), and phone numbers are masked in logs.
10. **Test & Eval Integrity**: Do not weaken any test or eval row to make it pass. Fix the code or notify the principal engineer.
11. **Authorized Source Whitelist**: Use only these sources for product facts:
    - https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/
    - https://www.keplertechllc.com/wp-content/uploads/2023/05/Citizen-CX-02-Photo-Printer-Datasheet.pdf
    - https://citizen-systems.com/en/products/printer/photo/cx-02
    List any other source you want to use and wait for approval.
