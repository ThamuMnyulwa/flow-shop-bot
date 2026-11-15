/*
 * FLOWW shop: live stock on the website (W1, W2).
 *
 * Mark up each product with its code, then load this script:
 *
 *   <div data-floww-product="HW-01">
 *     <span data-floww="price"></span>
 *     <span data-floww="availability"></span>
 *     <a data-floww="order">Order on WhatsApp</a>
 *   </div>
 *   <script src="https://YOUR-SERVICE/static/embed/floww-shop.js" data-api="https://YOUR-SERVICE" defer></script>
 *
 * Or render the whole catalogue into one element: <div data-floww-catalogue></div>
 *
 * If the service cannot be reached, whatever the page already shows stays in place.
 */
(function () {
  var script = document.currentScript;
  var api = (script && script.getAttribute("data-api")) || "";

  function rand(cents) {
    var whole = Math.floor(cents / 100), part = cents % 100;
    var text = "R" + whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return part ? text + "." + (part < 10 ? "0" : "") + part : text;
  }

  function fill(el, p) {
    el.setAttribute("data-floww-status", p.orderable ? "available" : p.status === "launching_soon" ? "soon" : "sold-out");
    el.querySelectorAll("[data-floww]").forEach(function (part) {
      var field = part.getAttribute("data-floww");
      if (field === "price") part.textContent = rand(p.price_cents);
      else if (field === "availability") part.textContent = p.availability;
      else if (field === "name") part.textContent = p.name;
      else if (field === "description") part.textContent = p.description;
      else if (field === "image" && p.image_url) part.setAttribute("src", p.image_url);
      else if (field === "order") {
        if (p.orderable) {
          part.setAttribute("href", p.order_url);
          part.setAttribute("target", "_blank");
          part.setAttribute("rel", "noopener");
          part.removeAttribute("aria-disabled");
        } else {
          part.removeAttribute("href");
          part.setAttribute("aria-disabled", "true");
          part.textContent = p.status === "launching_soon" ? "Launching soon" : "Sold out";
        }
      }
    });
  }

  function card(p) {
    var el = document.createElement("article");
    el.className = "floww-product";
    el.innerHTML =
      (p.image_url ? '<img data-floww="image" alt="">' : "") +
      '<h3 data-floww="name"></h3><p data-floww="description"></p>' +
      '<p><strong data-floww="price"></strong> · <span data-floww="availability"></span></p>' +
      '<a data-floww="order" class="floww-order">Order on WhatsApp</a>';
    fill(el, p);
    if (p.image_url) el.querySelector("img").alt = p.name;
    return el;
  }

  fetch(api + "/api/products", { headers: { Accept: "application/json" } })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      var byCode = {};
      data.products.forEach(function (p) { byCode[p.code] = p; });
      document.querySelectorAll("[data-floww-product]").forEach(function (el) {
        var p = byCode[el.getAttribute("data-floww-product").toUpperCase()];
        if (p) fill(el, p);
        else el.setAttribute("data-floww-status", "hidden");
      });
      document.querySelectorAll("[data-floww-catalogue]").forEach(function (box) {
        box.replaceChildren.apply(box, data.products.map(card));
      });
    })
    .catch(function (err) { if (window.console) console.warn("FLOWW stock unavailable:", err); });
})();
