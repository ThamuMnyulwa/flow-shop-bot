# Go live on WhatsApp (phase 3)

The bot already runs on the simulator. Going live adds a second channel behind the same interface, the official WhatsApp Cloud API through PyWa, and switches the service to it. The conversation code does not change.

## 1. Meta setup (can start during phase 2)

1. Create a Meta Business portfolio, and start business verification.
2. In the Meta developer console, create an app with the WhatsApp product.
3. Choose the number:
   - **A new dedicated number (recommended):** register it directly on the Cloud API. Point customers from the old number to it.
   - **The existing Business app number:** this needs Coexistence through a Solution Partner, and South African eligibility is unconfirmed. The app's catalogue and orders features stop working in that mode.
4. Add a payment method to the WhatsApp account. Without one, replies stop after the 1,000 free service messages each month.
5. Create a permanent System User access token with the `whatsapp_business_messaging` permission.

## 2. Templates to submit (L2)

Outside the 24-hour window, the service can only send approved templates. Submit both as **Utility** in English:

| Name | Body | Example |
| --- | --- | --- |
| `order_update` | `Your FLOWW order {{1}} is now {{2}}. Reply here if you have any questions.` | FLW-1010, paid |
| `payment_reminder` | `Reminder: FLOWW order {{1}} for {{2}} is waiting for payment. Send your proof of payment in this chat once you've paid.` | FLW-1010, R400 |

Templates with other names can be set in `FLOWSHOP_WA_TEMPLATE_ORDER_UPDATE` and `FLOWSHOP_WA_TEMPLATE_PAYMENT_REMINDER`.

## 3. Test with a Meta test number first (E10)

1. Run the service locally, and expose it through a secure tunnel, for example `cloudflared tunnel --url http://localhost:8000`.
2. Set these values in `.env`, using the test number from the developer console:

   ```
   FLOWSHOP_CHANNEL=whatsapp
   FLOWSHOP_WA_PHONE_ID=<test number's phone number ID>
   FLOWSHOP_WA_TOKEN=<token>
   FLOWSHOP_WA_APP_SECRET=<app secret, for webhook signatures>
   FLOWSHOP_WA_VERIFY_TOKEN=<any long random string>
   ```

3. In the developer console, set the webhook URL to `https://<tunnel>/webhook` with the same verify token, and subscribe to the `messages` field.
4. Message the test number from your phone, and run one full order: browse, confirm, send proof, mark paid.
5. Check the product photos. Open a product that has a photo on your phone and on WhatsApp Web, and check that:
   - the photo shows above the name and price on both
   - "Add to order" works
   - the "Added to your order" message and a one-item order summary also show the photo

   The service uploads each photo file to Meta, so photos work through the tunnel too. If an upload fails, the message still goes out without the photo, and the error is logged.

The business number is never touched during this test.

## 4. Switch production

1. On Render, set the same five values, with the business number's phone ID.
2. Set `FLOWSHOP_WA_BUSINESS_NUMBER` so the website's links open the right chat.
3. Point the webhook at `https://<production URL>/webhook`.
4. Run a short pilot with a few real customers before announcing the number.

## Rules the service already follows

- **Signatures:** every webhook is checked against the app secret, and a request with a bad signature gets a 401.
- **Duplicates:** each message is processed once, keyed on its WhatsApp message ID, so Meta's retries are harmless.
- **24-hour window:** free-form replies go out only within 24 hours of the customer's last message. Later messages use the templates above. The inbox blocks a staff reply that would break this rule.
- **WhatsApp limits:** buttons hold up to 3 options and lists up to 10, and the simulator enforces the same limits.
- **AI scope:** the AI assistant, when it's on, answers only from FLOWW's own products and orders.
