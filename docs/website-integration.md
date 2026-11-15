# Connect the Netlify website (phase 2b)

The website keeps its own design and hosting. It stops hard-coding stock and reads it from the service's public, read-only API (W1). Each product gets an "Order on WhatsApp" link that opens the chat with the product code filled in (W2).

## The API

| Endpoint | Returns |
| --- | --- |
| `GET /api/products` | Every product that is on sale or launching soon |
| `GET /api/products/HW-01` | One product |
| `GET /api/shop` | Seller name, delivery fee, free-delivery threshold, dispatch days, returns link, payment methods (for W3) |

Each product looks like this:

```json
{
  "code": "HW-01", "name": "Headwrap", "description": "...",
  "price_cents": 10000, "currency": "ZAR", "status": "on_sale",
  "available": 8, "availability": "8 available", "orderable": true,
  "category": "Fashion", "image_url": null,
  "order_url": "https://wa.me/27...?text=Hi%2C%20I%27d%20like%20to%20order%20Headwrap%20%5BHW-01%5D"
}
```

Responses are cached for 30 seconds. Only the origins in `FLOWSHOP_CORS_ORIGINS` can call the API from a browser.

## Option A: the drop-in script (least work)

Add a product code to each product's markup:

```html
<div data-floww-product="HW-01">
  <h3>Headwrap</h3>
  <strong data-floww="price">R100</strong>
  <span data-floww="availability"></span>
  <a data-floww="order">Order on WhatsApp</a>
</div>
<script src="https://<service>/static/embed/floww-shop.js" data-api="https://<service>" defer></script>
```

- **Fields:** `price`, `availability`, `name`, `description`, `image` and `order` are filled in. The order link is switched off for sold-out and launching-soon products.
- **Whole catalogue:** to show every product, use `<div data-floww-catalogue></div>` instead.
- **Styling:** each product element gets `data-floww-status="available|soon|sold-out|hidden"` for CSS.
- **Fallback:** if the service is down, the page keeps the content it already had.

Try it with `docs/website-example.html`.

## Option B: build-time or framework fetch

If the site uses a framework, such as Next, Astro, Eleventy or Hugo:
1. Fetch `/api/products` in the browser for live stock.
2. Optionally also fetch it at build time, so the first paint has content.

Don't rely on build-time data alone, because stock changes between deploys.

## Steps when the repository is brought in

1. Find where products are hard-coded today, and list each product's name, price and stock.
2. Check each against the database. Add any missing products on the admin page, and keep the codes in step with the website.
3. Replace the hard-coded stock with Option A or B.
4. Add the service's URL to `FLOWSHOP_CORS_ORIGINS` on staging and production.
5. **Disclosure pages (W3):** check that the site shows the seller's identity, delivery fees, returns policy and privacy notice. `/api/shop` provides the live fee values.

**Done when:** a quantity change on the admin page shows on the website, and each product's button opens WhatsApp with its code.
