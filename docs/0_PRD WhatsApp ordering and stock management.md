# PRD: WhatsApp ordering and stock management

Nov 15, 2026 · @DT

## Summary

Customers see live stock on the existing website (hosted on Netlify), then ask questions and place orders in a WhatsApp chat, and every confirmed order reserves stock in one database. The product is one small Python service with PostgreSQL that holds stock and orders, runs a menu-driven ordering bot, and gives staff a simple admin page and a shared inbox.

The bot is built and tested against a fake WhatsApp chat first, and moves to the real WhatsApp number later. An AI assistant is planned as a later phase. This version reflects the interview of 15 November 2026 and the technical review that followed it, and replaces the earlier Saleor-based design, which was larger than the business needs.

## Problem and opportunity

Customers already prefer to ask about products and buy inside WhatsApp, but a manual chat has no link to stock. That creates five problems:

- **Hard-coded stock:** the website shows stock that is typed into the site's code, so it goes out of date and needs a developer to change.
- **Overselling:** nothing stops two customers from buying the last unit.
- **Slow answers:** every price and availability question waits for a person.
- **Lost orders:** orders live in chat threads, so they are easy to miss and hard to report on.
- **Unpaid EFT orders:** nobody tracks which orders are still waiting for payment.

The business starts with 4 products, plans for 20 to 100 simple products, and expects fewer than 5 orders a day. At that size a commerce platform adds running cost without benefit, so the right answer is a small system the business owns.

## Launch catalogue

The FLOWW shop starts with four products, three on sale and one marked as launching soon. As a working assumption, each product costs R100 and starts with 10 units in stock.

| Product | Description | Price | Opening stock | Status at launch |
| --- | --- | --- | --- | --- |
| Headwrap | Bold African print headwraps, made to crown every look. | R100 | 10 | On sale |
| Notebook | A FLOWW notebook for the plans, the dreams and the lists. | R100 | 10 | On sale |
| Shea Butter Cream | Rich, natural shea butter care for skin that glows. | R100 | 10 | On sale |
| FLOWW Mug | Your morning reminder: bold, brave, beautiful. | R100 | 10 | Launching soon |

This catalogue adds two things to the design. A product needs a "Launching soon" status that shows it on the website and in the bot without allowing orders (requirement S6). Each headwrap print is its own product with its own stock, so the Headwrap row becomes one product per print once the prints are listed.

## Goals, non-goals and success metrics

**Goals**

1. A customer can go from first message to a confirmed order inside one WhatsApp chat.
2. The existing website shows live stock from the database and sends customers to WhatsApp to order.
3. Stock is reserved automatically when an order is confirmed, and an order for more than the available stock is refused.
4. Non-technical staff manage stock and orders on a simple web admin page.
5. Staff reply to customers from a shared web inbox and can take over any conversation.
6. The whole ordering flow can be tested in a fake chat before the real WhatsApp number is connected.
7. The whole system runs on the developer's machine, and every change is tested locally and on staging before release.
8. An AI assistant can be added later without rebuilding the bot.

**Non-goals for version 1**

- A cart or checkout on the website.
- Online card payment or a payment gateway.
- Cash on delivery. Payment is electronic and verified before delivery or collection.
- VAT. Prices are plain rand amounts for now, and VAT can be added later.
- An AI assistant (planned for a later phase).
- Product variants such as size or colour.
- Reselling returned products.
- Purchase orders and supplier management.
- Multiple warehouses.
- Marketing broadcasts and campaigns.
- Accounting and invoicing integration.

**Success metrics**

The targets below are proposals to confirm once real volumes are known. The service records an event for each order step and each handoff, so every metric can be measured from the database.

| Metric | Proposed target |
| --- | --- |
| Oversold orders | 0 |
| Orders dispatched or collected before payment is verified | 0 |
| Orders sent within 3 working days of verified payment | 100% |
| Orders completed without human help, apart from payment verification | 70% or more |
| Median bot response time | Under 5 seconds |
| Bot messages per completed order | 10 or fewer |
| Unpaid orders without proof of payment whose stock is released at 48 hours | 100% |
| New orders and proofs of payment seen by staff within 1 working hour | 95% or more |
| Stock accuracy at monthly count | 98% or more |
| Website stock matches the database | Always |

## Users and key journeys

**Users**

- **Customer:** a person who sees a product on the website or already has the WhatsApp number, and wants to order with as few messages as possible.
- **Staff:** non-technical team members who update stock, confirm payments, arrange delivery and answer questions the bot cannot.
- **Developer:** the one person who builds and runs the system.

**Journey 1: from the website to WhatsApp**

1. The customer opens the website and sees each product with its price and live availability.
2. The customer taps "Order on WhatsApp" on a product.
3. WhatsApp opens with a pre-filled message that carries the product code, for example "Hi, I'd like to order [HW-01]", and the bot starts the order with that product.

**Journey 2: customer places an order in the chat**

1. The customer browses categories and products through list messages, or arrives with a product from the website.
2. The customer picks a quantity. The bot checks stock and adds the item to the order.
3. The customer chooses delivery, or enters a collection code to collect from the office. For delivery, the customer gives an address and the bot adds the delivery fee.
4. The bot shows a full summary: items, delivery fee, total, the 3 working day dispatch promise, and the returns policy link.
5. The customer confirms. The system creates the order and reserves the stock.
6. Collection is available only with a valid collection code. Without one, the bot offers delivery only and gives no reason. With one, the customer collects the paid order at the office.

**Journey 3: payment**

1. The bot sends the bank details and an order reference, and asks for proof of payment in the chat.
2. When the customer sends proof of payment, staff receive an alert. Staff check that the money has arrived in the bank account, then mark the order as paid on the admin page. The customer receives a confirmation.
3. Only a paid order can be dispatched or handed over at collection. A paid delivery order is sent within 3 working days.
4. An order with proof of payment never expires, even while staff have not yet checked the bank.
5. If an order has no proof of payment after 48 hours, the system releases its stock and tells the customer. The order stays open as "payment overdue", so a late payment is still accepted. If the customer pays later, the system reserves the stock again when it is available, and otherwise flags the order for staff.

**Journey 4: staff manage stock and orders**

1. Staff open the admin page, add or edit products, and change quantities.
2. The website shows the change straight away, with no developer involved.
3. Staff see new orders, mark them as paid, dispatched or delivered, and cancel them when needed.

**Journey 5: human handoff**

1. The customer asks for a person, types something the menus do not cover, or the bot fails to understand twice.
2. The bot pauses for that conversation, and the chat appears as waiting in the shared inbox.
3. A staff member replies from the inbox, then returns the conversation to the bot.

## Functional requirements

Priorities: P0 is required for launch, P1 follows soon after launch, P2 is optional.

| ID | Area | Requirement | Priority |
| --- | --- | --- | --- |
| S1 | Stock | Products, prices and quantities live in PostgreSQL, loaded once from the values now hard-coded in the website. | P0 |
| S2 | Stock | Each product has an on-hand and a reserved quantity, and the available quantity is on-hand minus reserved. | P0 |
| S3 | Stock | Confirming an order reserves stock in one database transaction, and an order above the available quantity is refused with a clear message. | P0 |
| S4 | Stock | Marking an order as dispatched or collected removes its items from on-hand stock, because the goods have left the building. Cancelling an order, or reaching the 48-hour mark without proof of payment, releases its reservation. | P0 |
| S5 | Stock | Staff receive an alert when a product sells out or falls below a set level. | P1 |
| S6 | Stock | Each product has a status of on sale, launching soon or hidden. A launching-soon product appears on the website and in the bot but cannot be ordered. | P0 |
| A1 | Admin | Staff sign in to a simple web admin page that works on a phone. | P0 |
| A2 | Admin | Staff can add and edit products, prices, images and quantities, with every stock change logged. | P0 |
| A3 | Admin | Staff can see orders by status and mark them as paid, dispatched, delivered or cancelled. | P0 |
| A4 | Admin | A simple report shows orders, revenue and top products per week. | P2 |
| A5 | Admin | Staff receive an alert for every new order and every proof of payment, so nothing waits for someone to open the admin page. | P0 |
| A6 | Admin | Every order status change records who made it and when, including who marked an order as paid. | P0 |
| A7 | Admin | Staff can create an order on the admin page for a customer who orders by phone or in person, with the same stock rules. | P1 |
| W1 | Website | The existing Netlify website reads products, prices and availability from the service's public read-only API, never from the database directly. | P0 |
| W2 | Website | Each product has an "Order on WhatsApp" link that opens the chat with the product code pre-filled. | P0 |
| W3 | Website | The website shows the seller's identity, delivery fees, returns policy and privacy notice. | P0 |
| B1 | Bot | The bot talks to customers through a channel interface, so the simulator and WhatsApp use the same conversation code. | P0 |
| B2 | Bot | The customer can browse categories and products through list messages (10 options at most) and reply buttons (3 at most). | P0 |
| B3 | Bot | The customer can search for a product by name and receive price and live availability. | P0 |
| B4 | Bot | The customer can build an order with several items, change quantities and remove items. | P0 |
| B5 | Bot | The bot offers delivery, accepts a collection code for office collection, collects the address for delivery, and applies the delivery fee. | P0 |
| B6 | Bot | The bot shows a full order summary and requires explicit confirmation. | P0 |
| B7 | Bot | Conversation state survives a restart and expires after a set idle period. | P0 |
| B8 | Bot | The customer can ask for a person at any time, and any message the menus do not cover goes to staff. | P0 |
| B9 | Bot | A repeated confirmation, such as a double tap on Confirm, never creates a second order. | P0 |
| B10 | Bot | The customer can cancel their own order in the chat until it is paid. | P1 |
| M1 | Simulator | A fake chat web page lets the team play the customer, with the same buttons and lists WhatsApp shows. The simulator sends the service the same webhook JSON that Meta sends, so message parsing is tested from the start. | P0 |
| M2 | Simulator | The simulator supports several test customers at once and can be reset. | P1 |
| P1 | Payment | The bot sends bank details and a short order reference with a check digit, such as FLW-4821, and asks for proof of payment. EFT is the only payment method. | P0 |
| P2 | Payment | Staff mark an order as paid on the admin page, and the customer receives a confirmation. | P0 |
| P3 | Payment | An order without proof of payment 48 hours after confirmation has its stock released and moves to "payment overdue", and the customer is told. The order is not cancelled, and an order with proof of payment never expires. | P0 |
| P4 | Payment | An order cannot be marked as dispatched or collected until staff have marked it as paid. | P0 |
| P5 | Payment | The customer receives a reminder 24 hours before an unpaid order's stock is released. | P1 |
| P6 | Payment | When staff mark a "payment overdue" order as paid, the system reserves its stock again if it is available. If it is not, the order is flagged for staff to resolve with the customer. | P0 |
| D1 | Delivery | A paid delivery order shows a dispatch-by date 3 working days after payment was verified, and the admin page highlights orders that are close to or past that date. | P0 |
| D2 | Delivery | Collection from the office is available only to a customer who enters the collection code. There is one shared code, and staff change it on the admin page whenever they see the need. Without the current code the bot offers delivery only and gives no reason. The office address is shared only after the order is paid. | P0 |
| D4 | Delivery | Wrong collection code attempts are limited per phone number, and further attempts are refused for a period after a few failures. | P0 |
| D3 | Delivery | Local delivery costs R200 and is free when the products in the order total more than R1,000. The fee and the threshold are settings staff can change. | P0 |
| R1 | Returns | Staff can record a return against an order when there is a clear issue with the product, with a reason and the refund amount. Returned items are written off and never added back to sellable stock. | P1 |
| I1 | Inbox | Staff see all conversations in a shared web inbox, with chats that wait for a person at the top. | P0 |
| I2 | Inbox | Staff can reply, see the customer's orders beside the chat, and hand the conversation back to the bot. | P0 |
| I3 | Inbox | Several staff can use the inbox at once, and each reply shows who sent it. | P1 |
| L1 | Live WhatsApp | The service connects to the official Cloud API through PyWa, verifies webhook signatures and ignores duplicate deliveries. | P0 for go-live |
| L2 | Live WhatsApp | Order status updates and payment reminders use approved utility templates. | P1 |
| L3 | Live WhatsApp | Marketing opt-in is recorded separately from the order. | P1 |
| O1 | Operations | Errors raise an alert to the developer, an uptime check watches the service, and logs are structured. | P0 for go-live |
| AI1 | AI assistant | An AI answers free-text product questions from the product database, limited to the seller's products and orders, with staff as backup. | Later phase |

## Order lifecycle and stock rules

Every order moves through a fixed set of statuses, and each status decides what happens to stock.

```
draft ──confirm──▶ pending_payment ──proof received──▶ proof_received ──staff verify──▶ paid
                        │                                                            │
                        ├──48h, no proof──▶ payment_overdue ──staff verify──▶ paid    ├──▶ dispatched ──▶ delivered
                        │                                                            └──▶ collected
                        └──cancel──▶ cancelled        (any unpaid status can be cancelled)
```

| Status | Meaning | Stock effect on entry |
| --- | --- | --- |
| draft | The customer is building the order in the chat. | None. Availability is checked but nothing is held. |
| pending_payment | The customer confirmed, and bank details were sent. | Reserved. |
| proof_received | The customer sent proof of payment, and staff have not checked it yet. | Still reserved. Never expires. |
| payment_overdue | 48 hours passed with no proof of payment. The order stays open for a late payment. | Reservation released. |
| paid | Staff confirmed the money is in the bank. | Stays reserved, or is reserved again from payment_overdue if available (P6). |
| dispatched / collected | The goods left the building. | Removed from on hand and from reserved. |
| delivered | The customer received a delivery. | None. |
| cancelled | Cancelled by the customer, or by staff before dispatch. | Reservation released, if any. |

**Rules**

- **Reservation is atomic.** A reservation is one conditional update, `reserved = reserved + q` only where `on_hand - reserved >= q`, inside the transaction that creates the order. Database constraints keep `0 <= reserved <= on_hand`, so a bug cannot oversell.
- **Status changes are guarded.** Each change only applies if the order is still in the expected status, for example `WHERE status = 'pending_payment'`. So the 48-hour job and a staff member marking the order paid at the same moment cannot both succeed.
- **Confirmation is idempotent.** Each draft carries a key, and confirming the same draft twice returns the existing order (B9).
- **Every stock change is a row in a stock movement log,** with the reason, the order or staff member, and the time. Quantities can be rebuilt from the log.
- **Money is stored as whole cents in rand.** Totals are always calculated by the service from database prices.
- **Working days** use the Africa/Johannesburg time zone and skip weekends and South African public holidays.
- **Availability seen in the chat is not a hold.** A customer can see stock while browsing and still be refused at confirmation if someone else confirmed first. The bot then offers the quantity that is left.
- **A paid order that is cancelled needs a refund.** Staff record the refund by hand, because there is no payment gateway.

## Non-functional requirements

**Reliability**

- Stock reservation and order creation happen in one database transaction, so two customers cannot both get the last unit. The order lifecycle section gives the exact rules.
- Once live, the webhook endpoint acknowledges Meta within a few seconds, and each inbound message is processed once, keyed on its id.
- PostgreSQL is backed up daily, and a restore is tested before go-live.

**Security**

- The admin page and inbox require a sign-in, with one account per staff member, hashed passwords, CSRF protection and sessions that expire.
- The collection code protects the office address, so wrong attempts are rate limited (D4) and the code can be changed at any time (D2).
- Proof-of-payment files sit in private storage and are shown to signed-in staff through short-lived links.
- Webhook signatures from Meta are verified on every request once the service is live.
- Secrets are kept in environment configuration and never in the repository.
- Prices and totals always come from the database, never from message content.
- No card or bank login data is collected. Proof-of-payment images are visible to staff only.

**WhatsApp platform rules**

- Only the official Cloud API is used. Unofficial libraries are excluded because they risk a ban on the number.
- Free-form replies are sent only within 24 hours of the customer's last message. Anything later uses an approved template.
- Any AI assistant stays limited to the seller's own products and orders, in line with Meta's rule against general-purpose assistants.

**Legal (South Africa)**

These points come from one law firm's summaries and are not legal advice.

- **ECT Act:** the seller's identity, address, full price including delivery, payment method and returns policy are disclosed, and the customer can review and correct the order before confirming.
- **Returns policy against consumer law:** the business accepts returns only when there is a clear issue with the product. The ECT Act's seven-day cooling-off right and the Consumer Protection Act may give customers wider rights than that for some products, so the policy wording needs a legal check before launch.
- **POPIA:** marketing messages need opt-in consent, and personal data is limited to what an order needs.
- **POPIA cross-border transfer:** the business does not require customer data to stay in South Africa. Section 72 still applies when data is stored abroad, so the privacy notice says where data is held, and the chosen providers must offer adequate protection.

**Cost and footprint**

- The whole system runs on one small server: one Python service and one PostgreSQL database.
- Flows are designed to reach a confirmed order in 10 bot messages or fewer, because each number has 1,000 free service replies a month.

## Architecture and technology choices

One FastAPI service with one PostgreSQL database holds stock, orders and conversations, and everything else reads from it.

&#91;embedded content: system architecture · 2 channels, 1 stock system\]

The chat channel is swappable. The bot is built against a simulator first, and the same conversation code later runs on the WhatsApp Cloud API. The website never takes orders itself: it shows stock and hands the customer to the chat.

| Component | Choice | Role |
| --- | --- | --- |
| Order service | Python with FastAPI, managed with UV | Bot conversation logic as an explicit state machine, stock and order rules, the 48-hour EFT job, and the read-only API the website calls. |
| Database | PostgreSQL, with SQLAlchemy and Alembic migrations | Products, stock, stock movement log, orders, order status history, customers, conversations and messages. |
| Admin page and inbox | Server-rendered pages with HTMX inside the same service | Stock editing, order status, shared inbox. Built in, so there is nothing extra to run and no JavaScript framework. |
| Chat simulator | A small web page inside the same service | A fake WhatsApp chat for building and testing, with buttons and lists. It posts Meta's webhook JSON format. |
| WhatsApp connection | [PyWa](https://github.com/david-lev/pywa) (MIT) on Meta's official Cloud API | Added at go-live as a second channel behind the same interface. |
| Website | The existing site on Netlify | Calls the service's public API in the browser for products and live stock, and links to the chat. The service allows the site's domain through CORS. |
| AI assistant | Later phase | Plugs in where unmatched messages go to staff today. |
| Hosting | One small server with Docker | Runs the service and the database. |

**Key decisions**

- **No commerce platform.** With 20 to 100 simple products and fewer than 5 orders a day, a few PostgreSQL tables cover the need. Saleor would add five or more containers and about 4 GB of RAM for features that are out of scope.
- **Simulator first.** A channel interface with two implementations (simulator and Cloud API) lets the whole flow be built and tested before any Meta setup.
- **Official Cloud API only at go-live.** The business number is the shopfront, so libraries that imitate WhatsApp Web are excluded.
- **Built-in inbox first.** The service already stores every message, so a basic shared inbox is a small addition. Chatwoot stays an option if staff need more.
- **No payment gateway.** Payment is by EFT only, verified by staff before dispatch or collection.
- **The website uses an API, not the database.** The Netlify site is static and cannot hold a database connection safely, and an API keeps the website working when the schema changes.
- **Room for the AI assistant.** Every message the menus cannot handle passes through one fallback step. Today that step hands off to staff, and later the AI answers first.

**Fallbacks**

- If the catalogue or order volume grows well beyond this plan, the stock and order tables can move to Saleor or InvenTree behind the same bot.
- If the built-in inbox proves too basic, Chatwoot (MIT core) can replace it, at the cost of a Rails stack to run.

## Environments, local testing and release

Every change is run and tested on the developer's own machine first, then on a staging copy, and only then released to customers.

| Environment | Where it runs | Database | Chat channel | Purpose |
| --- | --- | --- | --- | --- |
| Local | The developer's machine | PostgreSQL in Docker, filled with sample data | Simulator | Build and test changes with no internet account needed |
| Staging | Hosted, private link | A separate hosted database | Simulator, later a Meta test number | Staff try a change before customers see it |
| Production | Hosted, public | The live database | Simulator until go-live, then the business WhatsApp number | Real customers and real stock |

**Local development requirements**

| ID | Requirement | Priority |
| --- | --- | --- |
| E1 | One command starts the whole system locally: the service, PostgreSQL, the admin page, the inbox and the simulator. | P0 |
| E2 | A seed command loads sample data: the four FLOWW launch products at R100 with 10 units each, a staff account and a few test orders. | P0 |
| E3 | The local setup needs no WhatsApp account, no Meta setup and no paid service. | P0 |
| E4 | All settings, such as the database address and the delivery fee, come from environment configuration, so the same code runs in every environment. | P0 |
| E5 | Database changes are versioned migrations that run the same way locally, on staging and in production. | P0 |
| E6 | Automated tests cover the stock rules: reserving, refusing an oversell under concurrent orders, releasing on cancellation, releasing at 48 hours without proof, no release once proof is received, reserving again on late payment, double confirmation, and blocking dispatch before payment. | P0 |
| E7 | Automated tests run whole bot conversations through the simulator channel, from first message to confirmed order. | P0 |
| E8 | Time can be moved forward in local and staging, so the 48-hour expiry and the 3 working day dispatch date can be tested in minutes. | P0 |
| E9 | The tests run automatically on every change before it can be released. | P1 |
| E10 | After go-live, the real WhatsApp connection can be tested locally through a secure tunnel and a Meta test number, without touching the business number. | P1 |
| E11 | The service builds into one container image that runs unchanged locally, on staging and on every deployment target. | P0 |
| E12 | Scheduled work, such as the 48-hour expiry, runs from an endpoint that an external scheduler calls. | P0 |
| E13 | The repository holds a tested deployment guide and configuration for the chosen production target. | P0 |

**Release steps**

1. Make and test the change locally, with the automated tests passing.
2. Deploy it to staging and check it there, with staff where the change affects them.
3. Back up the production database, then deploy to production.
4. If something goes wrong, roll back to the previous version.

**Hosting proposal**

The choice is Render for the service and Neon for PostgreSQL, at roughly $7 a month to start. Neon's database branching gives staging a copy of the data at no extra cost. The website stays on Netlify and calls the service over HTTPS, so the two do not need to sit together. Customer data does not have to stay in South Africa, so Frankfurt is acceptable.

Neon's free plan pauses an idle database, and the first request after a pause is slow. That can break the 5-second response target, so production either uses a plan that stays awake or has a scheduled ping.

**Deployment targets: GCP, AWS and Azure**

The service is packaged as one container image and uses plain PostgreSQL, so the same build can run on Render, Google Cloud, AWS or Azure. Only the production target gets a deployment guide (E13). The table below is kept as reference in case the business later needs a South African region.

| Target | Service runs on | Database | South African region | Database cost, compute only | Notes |
| --- | --- | --- | --- | --- | --- |
| Render with Neon (proposal) | Render web service | Neon PostgreSQL | None found; Frankfurt is nearest | Free plan to start | Simplest and cheapest. Data sits outside South Africa. |
| Google Cloud | Cloud Run | Cloud SQL for PostgreSQL | Johannesburg (africa-south1) | About $26 a month for the small shared instance | Cloud Run has a monthly free allowance and can scale to zero. |
| AWS | Amazon ECS Express Mode | Amazon RDS for PostgreSQL | Cape Town (af-south-1), not verified for Express Mode | Not yet priced | App Runner closed to new customers on 30 April 2026, and AWS points new projects to ECS Express Mode. |
| Azure | Azure Container Apps | Azure Database for PostgreSQL flexible server | South Africa North (Johannesburg); verified for the database only | About $16 a month for the B1ms burstable instance | Container Apps availability in the region still needs a check. |

The three large clouds cost more than the Render proposal at this size, mainly because of the managed database. Their advantage is a South African region, which keeps customer data in the country and shortens response times. Storage, backups and network charges come on top of the database figures.

**Portability rules**

- The service ships as a single container image, and nothing in the code depends on one cloud's own services.
- The 48-hour expiry and the payment reminders run from an endpoint that each platform's scheduler calls, because services that scale to zero cannot keep a timer running.
- Product images and proof-of-payment files go through one storage interface, with a local folder for development and the chosen cloud's object storage in production.
- Moving to another target needs only a new deployment guide and configuration file, not code changes.

## Release plan

The build runs in six phases plus the website step, and the first three phases need no WhatsApp account at all. Phase 2b can run whenever the website repository is ready, because it depends only on the product API from phase 1. Dates are not set yet.

| Phase | Scope | Done when |
| --- | --- | --- |
| 0. Foundations | Project set up with UV, the local environment (E1 to E6), PostgreSQL schema with the order lifecycle, the four launch products seeded. | One command starts the system locally with sample data, and the stock tests pass. |
| 1. Stock and admin | Requirements S1 to S4, S6, A1 to A3, A5, A6, and the public product API. | Staff change a quantity on the admin page and the product API shows it, with no developer involved. |
| 2. Bot on the simulator | Requirements B1 to B9, M1, P1 to P4, P6, D1 to D4, I1, I2. | A test order runs end to end in the fake chat: browse, order, EFT proof, marked paid. An order above available stock is refused, an order without proof releases its stock after 48 hours, and a late payment is still accepted. |
| 2b. Website | Requirements W1 to W3, once the Netlify repository is brought in. Each product's hard-coded values are checked against the database. | The website shows live stock from the API, and each product links to the chat. |
| 3. Go live on WhatsApp | Meta business setup, number connected, requirements L1 to L3 and O1, templates approved. | A real customer completes an order on the business number, and staff reply from the inbox. |
| 4. Operations | Requirements S5, P5, R1, I3, M2, A4, A7, B10. | Staff receive a low-stock alert, and a customer receives a payment reminder. |
| 5. AI assistant | Requirement AI1. | The AI answers product questions from live data, and hands off to staff when unsure. |

Meta business verification and the decision on the number can start during phase 2, because they take time and do not block the build.

## Costs

Running costs are close to zero until go-live, and small after it. The software is free, there are no payment gateway fees, and the costs are one small server and WhatsApp messages.

| Item | Cost | Basis |
| --- | --- | --- |
| Simulator phases (0 to 2) | No messaging cost | No WhatsApp account is used |
| Service replies after go-live (bot or staff, through the API) | First 1,000 a month free per number, then about $0.0095 (roughly R0.17) each | Third-party pages; Meta's own South African rate card was not read |
| Utility templates (order status, payment reminders) | About $0.0095 each | Same |
| Marketing templates | About $0.0379 (roughly R0.69) each | Same; out of scope |
| Payment fees | None | EFT only |
| Server | Not yet priced | One small server for a Python service and PostgreSQL |
| AI assistant | Not yet priced | Later phase; depends on the model and message volume |

**Worked example:** 5 orders a day is about 150 orders a month. At 10 replies each, that is 1,500 service messages. After the free 1,000, the 500 billable messages cost about $5 (roughly R85). Staff replies from the inbox count toward the same total.

## Risks, assumptions and open questions

**Risks**

| Risk | Effect | Response |
| --- | --- | --- |
| Moving the existing Business app number to the API depends on Meta's Coexistence feature, and its availability in South Africa is not confirmed. | The existing number may not be usable with the bot, or the move may need a provider. | Check eligibility during phase 2. Fall back to a new dedicated number, with the old number pointing customers to it. |
| Coexistence onboarding goes through a Solution Partner or Tech Provider. | A provider fee and less direct control. | Compare one provider's cost against registering a new number directly. |
| The simulator behaves differently from real WhatsApp (button limits, the 24-hour reply window, templates). | Surprises at go-live. | Build WhatsApp's limits into the simulator, and plan a short pilot with a few real customers in phase 3. |
| Custom stock code has bugs that a mature platform would not. | Wrong stock or oversold orders. | Keep the stock rules small, cover reservation and release with automated tests, and log every stock change. |
| A basic built-in inbox frustrates staff. | Slow replies to customers. | Test the inbox with staff in phase 2, and switch to Chatwoot if it falls short. |
| PyWa is run by one maintainer. | Slow fixes if the Cloud API changes. | Pin the version. The MIT licence allows a fork, and the Cloud API can be called directly. |
| Meta changes pricing or policy again. | Higher message costs or new limits. | Keep flows short and review Meta's rate card every quarter. |
| Fake or unclear proof of EFT payment. | Goods released without payment. | Staff confirm the money in the bank account before they mark an order as paid, and the system records who did it (A6). |
| The single shared collection code leaks. | Strangers can choose collection and later learn the office address. | Staff change the code whenever needed (D2), wrong attempts are limited (D4), and the address is sent only after payment. |
| Late payments arrive for "payment overdue" orders after the stock has sold out. | A paid order cannot be filled. | The system flags the order for staff (P6), and staff offer a refund or a wait. The reminder (P5) lowers how often this happens. |

**Assumptions**

- The business starts with 4 products and grows to between 20 and 100 simple products, from one stock location.
- Order volume stays below 5 a day in the first months.
- Customers pay by EFT only, and payment is verified before delivery or collection. Prices are in rand, and no VAT is charged or shown for now.
- Orders are delivered by the business locally or by courier nationwide, and are sent within 3 working days of verified payment. Local delivery costs R200 and is free for orders above R1,000. Collection from the office is available only to customers who hold a collection code, for safety.
- The existing website is hosted on Netlify, and the developer has access to its repository and will bring it into this work later.
- There is one shared collection code, which staff change on the admin page whenever they see the need.
- Customer data does not have to stay in South Africa.
- One developer builds and runs the system, and non-technical staff operate it.

**Open questions**

- [ ] What does courier delivery outside the local area cost, and does the free delivery threshold apply to it?
- [ ] Which areas count as local for the R200 fee?
- [ ] Does "above R1,000" mean the product total before the delivery fee, as this PRD assumes?
- [ ] How many headwrap prints are there at launch, and what are they called?
- [ ] Do the 3 working days count from verified payment, as this PRD assumes, or from the order?
- [ ] VAT is out of scope for now. Will the business register for VAT later, so that it needs to be added?
- [ ] Does the "clear issue only" returns policy hold up against the cooling-off right? This needs a legal check.
- [ ] The ECT Act asks online sellers to disclose a physical address. How does that fit with keeping the address private for safety? This needs a legal check.
- [ ] Should customers be able to ask for a message when the FLOWW Mug launches?
- [ ] How many staff will use the admin page and inbox, and during which hours?
- [ ] Which framework does the Netlify website use, and are its products hard-coded in HTML, JavaScript or data files?
- [ ] Is the built-in inbox enough, or is Chatwoot preferred from the start?
- [ ] For the later AI assistant: should it only answer questions, or also take orders?
- [ ] How do staff send a new alert (A5): WhatsApp to a staff number, email, or both?
- [ ] How long can a "payment overdue" order stay open before staff close it?
- [ ] How do staff refund a paid order that is cancelled, and who approves it?
- [ ] Who passes the collection code to trusted customers, and how?
- [ ] Should the website and the bot mention collection at all to customers who have no code?

**Resolved on 15 November 2026**

- [x] An order with proof of payment never expires. An order without proof releases its stock at 48 hours but stays open for a late payment.
- [x] There is one shared collection code, which staff change on the admin page when needed.
- [x] Customer data does not have to stay in South Africa, so production uses Render with Neon.
- [x] The existing website is hosted on Netlify, and its repository will be brought in later.

## Sources

This PRD draws on the research report "WhatsApp ordering and stock repos" (15 November 2026) and on the interview of the same day. The report lists its sources inline and states what was not verified. Key references:

- [PyWa repository](https://github.com/david-lev/pywa)
- [Chatwoot repository](https://github.com/chatwoot/chatwoot)
- [Meta pricing for non-template messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages/)
- [Meta onboarding for Business app users (Coexistence)](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users)
- [Saleor repository](https://github.com/saleor/saleor), kept as the growth path
- [AWS App Runner availability change](https://docs.aws.amazon.com/ja_jp/apprunner/latest/dg/apprunner-availability-change.html)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing?hl=id) and [Cloud SQL db-g1-small pricing by region](https://www.bytebase.com/dbcost/cloudsql/instance/db-g1-small/)
- [Azure PostgreSQL flexible server B1ms pricing by region](https://www.bytebase.com/dbcost/azure-flexible/instance/B1ms/)
- [Neon free plan limits](https://neon.com/faqs/free-plan-limits-and-quotas) and [Render pricing review](https://jwatte.com/blog/render-com-platform-review/)
