
// Phase 21: installable app shell. Offline mode never submits orders or caches API/private data.
(() => {
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(error => console.warn("ACE Canteen offline shell unavailable:", error)));
  }
  let installPrompt = null;
  const installButton = document.querySelector("#install-app-button");
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault(); installPrompt = event;
    if (installButton) installButton.hidden = false;
  });
  installButton?.addEventListener("click", async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null; installButton.hidden = true;
  });
  window.addEventListener("appinstalled", () => { installPrompt = null; if (installButton) installButton.hidden = true; });
})();

"use strict";

// Phase 5 cart: persisted locally for convenience; prices and stock are always revalidated by the server.
const CART_STORAGE_KEY = 'ace-canteen-cart-v1';
let cart = (() => { try { const raw = JSON.parse(localStorage.getItem(CART_STORAGE_KEY) || '{}'); return raw && typeof raw === 'object' ? raw : {}; } catch { return {}; } })();
const money = value => `₹${Number(value || 0).toFixed(2)}`;
function saveCart() { try { localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart)); } catch { /* private browsing/storage disabled: cart remains in memory */ } }
function cartLines() { return Object.entries(cart).map(([id, quantity]) => ({ product_id: Number(id), quantity: Number(quantity) })).filter(line => Number.isInteger(line.product_id) && line.product_id > 0 && Number.isInteger(line.quantity) && line.quantity > 0); }
function renderCart(message = '') {
  const list = document.querySelector('#cart-items'); const status = document.querySelector('#cart-message'); const subtotal = document.querySelector('#cart-subtotal');
  if (!list || !status || !subtotal) return;
  list.replaceChildren(); const lines = cartLines();
  if (message) status.textContent = message;
  else status.textContent = lines.length ? `${lines.reduce((sum, line) => sum + line.quantity, 0)} item(s) in your cart. Review the current total before placing the order.` : 'Your cart is empty. Add items from the catalogue above.';
  let estimated = 0;
  for (const line of lines) {
    const row = document.createElement('div'); row.className = 'cart-line';
    const details = document.createElement('div'); details.className = 'cart-line-info';
    const cachedProduct = window.aceCatalogueProducts?.[line.product_id];
    const name = document.createElement('strong'); name.textContent = cachedProduct?.name || `Product #${line.product_id}`;
    const meta = document.createElement('small'); meta.textContent = `${cachedProduct ? money(cachedProduct.price) + ' each · ' : ''}Quantity: ${line.quantity} · price is checked at review`;
    details.append(name, meta);
    const controls = document.createElement('div'); controls.className = 'cart-line-controls';
    const minus = document.createElement('button'); minus.type = 'button'; minus.className = 'secondary-button'; minus.textContent = '−'; minus.setAttribute('aria-label', `Decrease product ${line.product_id} quantity`); minus.disabled = line.quantity <= 1;
    minus.addEventListener('click', () => { cart[line.product_id] = Math.max(1, line.quantity - 1); saveCart(); renderCart(); });
    const qty = document.createElement('span'); qty.textContent = String(line.quantity);
    const plus = document.createElement('button'); plus.type = 'button'; plus.className = 'secondary-button'; plus.textContent = '+'; plus.setAttribute('aria-label', `Increase product ${line.product_id} quantity`); plus.disabled = line.quantity >= 50;
    plus.addEventListener('click', () => { if (line.quantity < 50) cart[line.product_id] = line.quantity + 1; saveCart(); renderCart(); });
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary-button'; remove.textContent = 'Remove'; remove.addEventListener('click', () => { delete cart[line.product_id]; saveCart(); renderCart(); });
    controls.append(minus, qty, plus, remove); row.append(details, controls); list.append(row);
  }
  // Display cached prices only as an estimate; review obtains authoritative prices from the API.
  const cached = window.aceCatalogueProducts || {};
  for (const line of lines) estimated += Number(cached[line.product_id]?.price || 0) * line.quantity;
  subtotal.textContent = money(estimated);
  const checkout = document.querySelector('#cart-checkout'); const review = document.querySelector('#cart-review');
  if (checkout) checkout.disabled = !lines.length || window.aceCanteenClosed === true;
  if (review) review.disabled = !lines.length;
}
function addToCart(product) {
  if (!window.aceCanteenToken || !window.aceCanteenUser) { document.querySelector('#account')?.scrollIntoView({ behavior: 'smooth' }); const msg = document.querySelector('#auth-message'); if (msg) msg.textContent = 'Sign in as a student before adding items to your order.'; return; }
  if (window.aceCanteenUser.role !== 'student') { const msg = document.querySelector('#cart-message'); if (msg) msg.textContent = 'Only student accounts can place orders. Staff/admin accounts manage the canteen.'; return; }
  const id = String(product.id); const next = Number(cart[id] || 0) + 1;
  if (next > 50) { renderCart('A maximum of 50 units per product is allowed.'); return; }
  cart[id] = next; window.aceCatalogueProducts = window.aceCatalogueProducts || {}; window.aceCatalogueProducts[product.id] = product; saveCart(); renderCart(`${product.name} added to your cart.`);
  document.querySelector('#cart-section')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
async function reviewCart() {
  const lines = cartLines(); if (!lines.length) { renderCart(); return null; }
  if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'student') throw new Error('Sign in with a student account to review checkout.');
  const response = await fetch('/api/orders/quote', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${window.aceCanteenToken}`, Accept: 'application/json' }, body: JSON.stringify({ items: lines, notes: document.querySelector('#checkout-notes')?.value.trim() || null, pickup_slot: document.querySelector('#pickup-slot')?.value || null }) });
  const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || data.error?.message || 'Could not validate your cart.');
  const list = document.querySelector('#cart-items'); list.replaceChildren();
  for (const item of data.items) {
    const row = document.createElement('div'); row.className = 'cart-line'; const details = document.createElement('div'); details.className = 'cart-line-info';
    const name = document.createElement('strong'); name.textContent = item.product_name; const meta = document.createElement('small'); meta.textContent = `${item.quantity} × ${money(item.unit_price)} · ${item.stock_available} in stock`;
    details.append(name, meta);
    const controls = document.createElement('div'); controls.className = 'cart-line-controls';
    const minus = document.createElement('button'); minus.type = 'button'; minus.className = 'secondary-button'; minus.textContent = '−'; minus.setAttribute('aria-label', `Decrease ${item.product_name} quantity`); minus.disabled = item.quantity <= 1;
    minus.addEventListener('click', () => { cart[item.product_id] = Math.max(1, item.quantity - 1); saveCart(); renderCart(); });
    const qty = document.createElement('span'); qty.textContent = String(item.quantity);
    const plus = document.createElement('button'); plus.type = 'button'; plus.className = 'secondary-button'; plus.textContent = '+'; plus.setAttribute('aria-label', `Increase ${item.product_name} quantity`); plus.disabled = item.quantity >= 50;
    plus.addEventListener('click', () => { if (item.quantity < 50) cart[item.product_id] = item.quantity + 1; saveCart(); renderCart(); });
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary-button'; remove.textContent = 'Remove'; remove.addEventListener('click', () => { delete cart[item.product_id]; saveCart(); renderCart(); });
    const total = document.createElement('strong'); total.textContent = money(item.line_total); controls.append(minus, qty, plus, remove); row.append(details, controls, total); list.append(row);
    window.aceCatalogueProducts = window.aceCatalogueProducts || {}; window.aceCatalogueProducts[item.product_id] = { ...(window.aceCatalogueProducts[item.product_id] || {}), name: item.product_name, price: item.unit_price };
  }
  document.querySelector('#cart-subtotal').textContent = money(data.subtotal);
  document.querySelector('#cart-message').textContent = 'Prices and stock validated by the server. Stock is not reserved until you place the order.';
  return data;
}
async function placeCartOrder() {
  const button = document.querySelector('#cart-checkout'); if (!button) return;
  if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'student') { document.querySelector('#account')?.scrollIntoView({ behavior: 'smooth' }); const msg = document.querySelector('#auth-message'); if (msg) msg.textContent = 'Sign in as a student to check out.'; return; }
  if (!cartLines().length) { renderCart(); return; }
  if (window.acePaymentRecoveryOrderId) {
    try {
      const recoveryResponse = await fetch(`/api/payments/status/${encodeURIComponent(window.acePaymentRecoveryOrderId)}`, { headers: { Authorization: `Bearer ${window.aceCanteenToken}`, Accept: 'application/json' } });
      const recovery = await recoveryResponse.json().catch(() => ({}));
      if (!recoveryResponse.ok || !recovery.retry_allowed) {
        renderCart(recovery.message || 'A previous payment is still being verified. Do not pay again yet.');
        return;
      }
      window.acePaymentRecoveryOrderId = null;
    } catch (_) { renderCart('Could not verify the previous payment. Do not pay again yet; check your order status shortly.'); return; }
  }
  if (!window.Razorpay) { renderCart('Payment checkout did not load. Check your connection and reload the page.'); return; }
  button.disabled = true; const original = button.textContent; button.textContent = 'Preparing secure checkout…';
  try {
    const quote = await reviewCart();
    if (!quote || !window.confirm(`Continue to secure payment for ${money(quote.subtotal)}?`)) return;
    const response = await fetch('/api/payments/create-order', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${window.aceCanteenToken}`, Accept: 'application/json' }, body: JSON.stringify({ items: cartLines(), notes: document.querySelector('#checkout-notes')?.value.trim() || null, pickup_slot: document.querySelector('#pickup-slot')?.value || null }) });
    const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || data.error?.message || 'Could not start payment checkout.');
    const payment = data.payment; window.acePaymentRecoveryOrderId = data.order?.id || null;
    await new Promise((resolve, reject) => {
      const checkout = new window.Razorpay({ key: payment.key_id, amount: payment.amount, currency: payment.currency, name: payment.name, description: payment.description, order_id: payment.gateway_order_id, prefill: payment.prefill, theme: { color: '#176b4d' }, modal: { ondismiss: () => reject(new Error('Payment window closed. Check payment status before trying again.')) }, handler: async result => {
        try {
          const verifyResponse = await fetch('/api/payments/verify', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${window.aceCanteenToken}`, Accept: 'application/json' }, body: JSON.stringify(result) });
          const verified = await verifyResponse.json().catch(() => ({}));
          if (!verifyResponse.ok || verified.verified !== true) {
            renderCart(verified.message || 'Payment status is being verified. If your bank account was debited, do not pay again yet. Use Check Payment Status from your order history.');
            reject(new Error(verified.message || verified.detail || 'Payment status is uncertain. Do not pay again yet.'));
            return;
          }
          window.acePaymentRecoveryOrderId = null; resolve(verified.order);
        } catch (error) { reject(error); }
      } });
      checkout.on('payment.failed', event => { renderCart('Payment attempt failed or is still being confirmed. Checking provider status before allowing another payment.'); reject(new Error(event.error?.description || 'Payment attempt failed. Check status before retrying.')); });
      checkout.open();
    }).then(async order => {
      cart = {}; saveCart(); document.querySelector('#checkout-notes').value = ''; renderCart(`Payment successful and verified. Order #${order.id}, pickup token #${order.token_number}.`);
      document.querySelector('#my-orders-section').hidden = false; await loadMyOrders(); await loadCatalogue(); document.querySelector('#my-orders-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  } catch (error) { renderCart(`Checkout: ${error.message}`); }
  finally { button.disabled = !cartLines().length || window.aceCanteenClosed === true; button.textContent = original; }
}
document.querySelector('#cart-review')?.addEventListener('click', async () => { const button = document.querySelector('#cart-review'); button.disabled = true; try { await reviewCart(); } catch (error) { renderCart(`Could not review cart: ${error.message}`); } finally { button.disabled = !cartLines().length; } });
document.querySelector('#cart-checkout')?.addEventListener('click', placeCartOrder);
document.querySelector('#cart-clear')?.addEventListener('click', () => { cart = {}; saveCart(); renderCart('Cart cleared.'); });
renderCart();

const catalogueGrid = document.querySelector("#catalogue-grid");
const catalogueMessage = document.querySelector("#catalogue-message");
const productSearch = document.querySelector("#product-search");
const productType = document.querySelector("#product-type");
const productCategory = document.querySelector("#product-category");
const productSort = document.querySelector("#product-sort");
const loadMoreButton = document.querySelector("#catalogue-load-more");
let catalogueCategories = [];
let catalogueRequest = 0;
let catalogueOffset = 0;
const CATALOGUE_PAGE_SIZE = 12;
async function loadCatalogue({ append = false } = {}) {
  if (!catalogueGrid || !catalogueMessage) return;
  if (!append) catalogueOffset = 0;
  const requestId = ++catalogueRequest;
  catalogueMessage.textContent = "Loading catalogue…";
  if (loadMoreButton) loadMoreButton.disabled = true;
  const params = new URLSearchParams({ limit: String(CATALOGUE_PAGE_SIZE), offset: String(catalogueOffset) });
  if (productType?.value) params.set("item_type", productType.value);
  if (productCategory?.value) params.set("category_id", productCategory.value);
  if (productSearch?.value.trim()) params.set("search", productSearch.value.trim());
  const [sortBy, sortOrder] = (productSort?.value || "name:asc").split(":");
  params.set("sort_by", sortBy); params.set("sort_order", sortOrder);
  try {
    const response = await fetch(`/api/products?${params.toString()}`, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) throw new Error(`Catalogue returned HTTP ${response.status}`);
    const products = await response.json();
    if (requestId !== catalogueRequest) return;
    if (!append) catalogueGrid.replaceChildren();
    if (!products.length && !append) { catalogueMessage.textContent = "No matching in-stock items. Try another search or filter."; if (loadMoreButton) loadMoreButton.hidden = true; return; }
    if (!products.length && append) { catalogueMessage.textContent = `${catalogueOffset} items loaded · end of catalogue.`; if (loadMoreButton) loadMoreButton.hidden = true; return; }
    const fragment = document.createDocumentFragment();
    window.aceCatalogueProducts = window.aceCatalogueProducts || {};
    for (const product of products) {
      window.aceCatalogueProducts[product.id] = product;
      const card = document.createElement("article"); card.className = "product-card";
      if (product.image_url) {
        const image = document.createElement("img"); image.className = "product-image"; image.src = product.image_url; image.alt = product.name; image.loading = "lazy"; image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => { image.hidden = true; }); card.append(image);
      } else {
        const icon = document.createElement("div"); icon.className = "product-icon"; icon.textContent = product.item_type === "stationery" ? "✎" : "☕"; icon.setAttribute("aria-hidden", "true"); card.append(icon);
      }
      const title = document.createElement("h3"); title.textContent = product.name;
      const description = document.createElement("p"); description.textContent = product.description || (product.item_type === "stationery" ? "Campus study essential" : "Campus canteen favourite");
      const meta = document.createElement("div"); meta.className = "product-meta";
      const price = document.createElement("span"); price.className = "product-price"; price.textContent = `₹${Number(product.price).toFixed(2)}`;
      const stock = document.createElement("span"); stock.className = "stock-label"; stock.textContent = `${product.stock_quantity} in stock`;
      const category = document.createElement("span"); category.className = "stock-label"; category.textContent = product.category_name || product.item_type;
      meta.append(price, stock);
      card.append(title, category, description, meta);
      const actions = document.createElement('div'); actions.className = 'product-actions';
      const orderButton = document.createElement('button'); orderButton.type = 'button'; orderButton.className = 'primary-button product-order-button'; orderButton.textContent = 'Add to cart';
      orderButton.addEventListener('click', () => { addToCart(product); orderButton.textContent = 'Added ✓'; setTimeout(() => { orderButton.textContent = 'Add to cart'; }, 900); });
      const favoriteButton = document.createElement('button'); favoriteButton.type = 'button'; favoriteButton.className = 'secondary-button favorite-button'; favoriteButton.textContent = '♡ Save'; favoriteButton.setAttribute('aria-label', `Save ${product.name} to favorites`);
      favoriteButton.addEventListener('click', async () => { if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'student') { document.querySelector('#account')?.scrollIntoView({behavior:'smooth'}); const msg=document.querySelector('#auth-message'); if(msg) msg.textContent='Sign in as a student to save favourites.'; return; } favoriteButton.disabled=true; try { const response=await fetch(`/api/favorites/${product.id}`, {method:'POST', headers:{Authorization:`Bearer ${window.aceCanteenToken}`, Accept:'application/json'}}); const data=await response.json().catch(()=>({})); if(!response.ok) throw new Error(data.detail || 'Could not save item'); favoriteButton.textContent='♥ Saved'; favoriteButton.setAttribute('aria-pressed','true'); } catch(error) { favoriteButton.textContent='Try again'; favoriteButton.title=error.message; } finally { favoriteButton.disabled=false; } });
      actions.append(orderButton, favoriteButton); card.append(actions);
      if (product.dietary_info) { const dietary = document.createElement("p"); dietary.className = "product-extra"; dietary.textContent = `Dietary: ${product.dietary_info}`; card.append(dietary); }
      if (product.allergens) { const allergens = document.createElement("p"); allergens.className = "product-extra"; allergens.textContent = `Allergens: ${product.allergens}`; card.append(allergens); }
      fragment.append(card);
    }
    catalogueGrid.append(fragment);
    catalogueOffset += products.length;
    catalogueMessage.textContent = `${catalogueOffset} item${catalogueOffset === 1 ? "" : "s"} loaded · search and filters use live database data.`;
    renderCart();
    if (loadMoreButton) { loadMoreButton.hidden = products.length < CATALOGUE_PAGE_SIZE; loadMoreButton.disabled = false; }
  } catch (error) {
    catalogueMessage.textContent = "Catalogue could not load. Confirm the backend is running and /api/ready reports ready.";
    console.error("ACE Canteen catalogue failed:", error);
    if (loadMoreButton) loadMoreButton.disabled = false;
  }
}
function updatePublicCategoryOptions() {
  if (!productCategory) return;
  const selected = productCategory.value;
  productCategory.replaceChildren();
  const all = document.createElement('option'); all.value = ''; all.textContent = 'All categories'; productCategory.append(all);
  for (const category of catalogueCategories.filter(c => !productType?.value || c.item_type === productType.value)) {
    const option = document.createElement('option'); option.value = String(category.id); option.textContent = category.name; productCategory.append(option);
  }
  if ([...productCategory.options].some(option => option.value === selected)) productCategory.value = selected;
}
if (productSearch && productType) {
  productSearch.addEventListener("input", () => { clearTimeout(productSearch._debounce); productSearch._debounce = setTimeout(() => loadCatalogue(), 180); });
  productType.addEventListener("change", () => { updatePublicCategoryOptions(); loadCatalogue(); });
  productCategory?.addEventListener("change", () => loadCatalogue());
  productSort?.addEventListener("change", () => loadCatalogue());
  loadMoreButton?.addEventListener("click", () => loadCatalogue({ append: true }));
  (async () => {
    try {
      const response = await fetch('/api/categories');
      if (!response.ok) throw new Error('Could not load categories');
      catalogueCategories = await response.json();
      updatePublicCategoryOptions();
    } catch (error) { console.error('ACE Canteen categories failed:', error); }
    await loadCatalogue();
  })();
}

// Phase 3/48 account UI: sign in, register, forgot/reset password, persistent session.
// The bearer token is kept in localStorage so a page refresh (or switching to a UPI app and back on a phone)
// does not sign the student out. It is validated with /api/auth/me on every page load and removed on sign-out.
(() => {
  const form = document.querySelector('#auth-form');
  if (!form) return;
  const SESSION_KEY = 'ace-canteen-session-v1';
  const store = {
    save(value) { try { localStorage.setItem(SESSION_KEY, value); } catch { /* storage disabled: session lasts until refresh */ } },
    load() { try { return localStorage.getItem(SESSION_KEY) || ''; } catch { return ''; } },
    clear() { try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ } }
  };
  let mode = 'login'; // login | register | forgot | reset
  let resetToken = '';
  const nameWrap = document.querySelector('#auth-name-wrap');
  const nameInput = document.querySelector('#auth-name');
  const emailWrap = document.querySelector('#auth-email-wrap');
  const emailInput = document.querySelector('#auth-email');
  const passwordWrap = document.querySelector('#auth-password-wrap');
  const passwordLabel = document.querySelector('#auth-password-label');
  const passwordInput = document.querySelector('#auth-password');
  const forgotButton = document.querySelector('#auth-forgot');
  const submit = document.querySelector('#auth-submit');
  const message = document.querySelector('#auth-message');
  const accountPanel = document.querySelector('#account-panel');
  const setMessage = (text, kind = '') => { message.textContent = text; message.className = `auth-message ${kind}`.trim(); };
  const labels = {
    login: { submit: 'Sign in', hint: 'Sign in with your registered email and password.', password: 'Password', auto: 'current-password' },
    register: { submit: 'Create student account', hint: 'Registration creates a student account.', password: 'Password', auto: 'new-password' },
    forgot: { submit: 'Email me a reset link', hint: 'Enter your account email and we will send a link to set a new password.', password: 'Password', auto: 'off' },
    reset: { submit: 'Save new password', hint: 'Choose a new password of at least 12 characters.', password: 'New password (12+ characters)', auto: 'new-password' }
  };
  function setMode(next, hint) {
    mode = next;
    const label = labels[mode];
    document.querySelectorAll('[data-auth-mode]').forEach(b => b.classList.toggle('active', b.dataset.authMode === mode));
    nameWrap.hidden = mode !== 'register';
    nameInput.required = mode === 'register';
    emailWrap.hidden = mode === 'reset';
    emailInput.required = mode !== 'reset';
    passwordWrap.hidden = mode === 'forgot';
    passwordInput.required = mode !== 'forgot';
    passwordInput.autocomplete = label.auto;
    passwordLabel.textContent = label.password;
    submit.textContent = label.submit;
    forgotButton.hidden = mode !== 'login';
    setMessage(hint ?? label.hint);
  }
  document.querySelectorAll('[data-auth-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.authMode)));
  forgotButton.addEventListener('click', () => setMode('forgot'));

  function applySession(token, user) {
    window.aceCanteenToken = token;
    window.aceCanteenUser = user;
    document.dispatchEvent(new CustomEvent('ace-auth-changed', { detail: user }));
    document.querySelector('#account-name').textContent = user.full_name;
    document.querySelector('#account-role').textContent = `Role: ${user.role}`;
    accountPanel.hidden = false;
    form.hidden = true;
    document.querySelectorAll('.auth-tab').forEach(b => b.hidden = true);
    if (user.must_change_password) {
      setMessage('Your account uses a temporary password. Change it below before using staff or admin tools.', 'error');
      document.querySelector('#change-password-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      setMessage('Signed in successfully.', 'success');
    }
  }
  async function readJson(response) { try { return await response.json(); } catch { return {}; } }
  const postJson = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    setMessage('Please wait…');
    try {
      if (mode === 'forgot') {
        const response = await postJson('/api/auth/forgot-password', { email: emailInput.value.trim() });
        const data = await readJson(response);
        if (!response.ok) throw new Error(data.detail || data.error?.message || 'Could not send the reset email. Try again shortly.');
        setMessage(data.message, 'success');
        return;
      }
      if (mode === 'reset') {
        const response = await postJson('/api/auth/reset-password', { token: resetToken, new_password: passwordInput.value });
        const data = await readJson(response);
        if (!response.ok) throw new Error(data.detail || data.error?.message?.replace('The request contains invalid data.', 'Password must be at least 12 characters.') || 'Could not reset the password.');
        resetToken = ''; passwordInput.value = '';
        setMode('login', 'Password updated. Sign in with your new password.');
        message.className = 'auth-message success';
        return;
      }
      const payload = { email: emailInput.value.trim(), password: passwordInput.value };
      if (mode === 'register') payload.full_name = nameInput.value.trim();
      const response = await postJson(`/api/auth/${mode === 'register' ? 'register' : 'login'}`, payload);
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.detail || data.error?.message || 'Request failed.');
      if (mode === 'register') {
        setMode('login', 'Account created. Sign in with your new credentials.');
        message.className = 'auth-message success';
        emailInput.value = payload.email;
        passwordInput.value = '';
        return;
      }
      store.save(data.access_token);
      applySession(data.access_token, data.user);
    } catch (error) { setMessage(error.message || 'Could not connect to the server.', 'error'); }
    finally { submit.disabled = false; }
  });
  const passwordForm = document.querySelector('#change-password-form');
  passwordForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const message = document.querySelector('#password-change-message');
    const button = passwordForm.querySelector('button[type=submit]'); button.disabled = true;
    message.textContent = 'Updating password…'; message.className = 'auth-message';
    try {
      const response = await fetch('/api/auth/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${window.aceCanteenToken}` }, body: JSON.stringify({ current_password: document.querySelector('#current-password').value, new_password: document.querySelector('#new-password').value }) });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.detail || 'Could not change password.');
      message.textContent = 'Password changed. Your old session has been signed out; sign in again with your new password.'; message.className = 'auth-message success'; passwordForm.reset(); document.querySelector('#auth-logout').click();
    } catch (error) { message.textContent = error.message; message.className = 'auth-message error'; }
    finally { button.disabled = false; }
  });
  document.querySelector('#auth-logout').addEventListener('click', () => {
    store.clear();
    window.aceCanteenToken = '';
    window.aceCanteenUser = null;
    document.dispatchEvent(new CustomEvent('ace-auth-changed', { detail: null }));
    form.reset(); form.hidden = false; accountPanel.hidden = true;
    document.querySelectorAll('.auth-tab').forEach(b => b.hidden = false);
    setMode('login', 'You have signed out.');
    message.className = 'auth-message success';
  });

  setMode('login');
  // Password-reset link: /#reset=<token>. The token stays in the URL fragment (never sent to the server or in
  // Referer headers) and is removed from the address bar immediately.
  if (location.hash.startsWith('#reset=')) {
    resetToken = decodeURIComponent(location.hash.slice('#reset='.length));
    history.replaceState(null, '', location.pathname + location.search);
    setMode('reset');
    document.querySelector('#account')?.scrollIntoView({ behavior: 'smooth' });
  } else {
    const saved = store.load();
    if (saved) {
      fetch('/api/auth/me', { headers: { Authorization: `Bearer ${saved}` } })
        .then(async response => {
          if (response.ok) applySession(saved, await response.json());
          else if (response.status === 401) store.clear(); // expired or invalidated session
        })
        .catch(() => { /* offline or server restarting: keep the stored token and let the user retry */ });
    }
  }
})();


// Phase 4: staff/admin catalogue management UI. The API remains the authority for permissions.
(() => {
  const panel = document.querySelector('#catalogue-management');
  if (!panel) return;
  const productForm = document.querySelector('#product-form');
  const categoryForm = document.querySelector('#category-form');
  const productType = document.querySelector('#new-product-type');
  const categorySelect = document.querySelector('#new-product-category');
  const productList = document.querySelector('#manage-products-list');
  const productMessage = document.querySelector('#manage-products-message');
  const categoryPanel = document.querySelector('#category-management');
  const categoryList = document.querySelector('#manage-categories-list');
  const categoryMessage = document.querySelector('#manage-categories-message');
  const userPanel = document.querySelector('#user-management');
  const userList = document.querySelector('#manage-users-list');
  const userMessage = document.querySelector('#manage-users-message');
  const setMessage = (element, message, kind = '') => { element.textContent = message; element.className = `management-message ${kind}`.trim(); };
  const api = async (url, options = {}) => {
    const headers = { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(window.aceCanteenToken ? { Authorization: `Bearer ${window.aceCanteenToken}` } : {}), ...(options.headers || {}) };
    const response = await fetch(url, { ...options, headers });
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || data?.error?.message || `Request failed (${response.status})`);
    return data;
  };
  async function loadCategoryOptions() {
    const categories = await api('/api/categories');
    const previous = categorySelect.value;
    categorySelect.replaceChildren();
    const filtered = categories.filter(c => c.item_type === productType.value);
    for (const category of filtered) { const option = document.createElement('option'); option.value = String(category.id); option.textContent = category.name; categorySelect.append(option); }
    if (filtered.some(c => String(c.id) === previous)) categorySelect.value = previous;
    if (!filtered.length) { const option = document.createElement('option'); option.value = ''; option.textContent = 'Create a category first'; categorySelect.append(option); }
  }
  function addFieldInput(parent, type, value, aria) {
    const input = document.createElement('input'); input.type = type; input.value = value; input.setAttribute('aria-label', aria);
    if (type === 'number') { input.min = '0'; input.step = aria.toLowerCase().includes('price') ? '0.01' : '1'; }
    return input;
  }
  async function loadManagedProducts() {
    if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'admin') return;
    productMessage.textContent = 'Loading products…'; productList.replaceChildren();
    try {
      const products = await api('/api/admin/products');
      if (!products.length) { setMessage(productMessage, 'No products found. Add the first product above.'); return; }
      for (const product of products) {
        const row = document.createElement('div'); row.className = `managed-product ${product.is_available ? '' : 'is-archived'}`;
        const nameWrap = document.createElement('div'); nameWrap.className = 'managed-product-name';
        const name = document.createElement('strong'); name.textContent = product.name;
        const category = document.createElement('small'); category.textContent = `${product.category_name || product.item_type} · ${product.is_available ? 'Available' : 'Unavailable'}`;
        nameWrap.append(name, category);
        const price = addFieldInput(row, 'number', Number(product.price).toFixed(2), `Price for ${product.name}`);
        const stock = addFieldInput(row, 'number', product.stock_quantity, `Stock for ${product.name}`);
        const availableWrap = document.createElement('label'); availableWrap.style.display = 'flex'; availableWrap.style.alignItems = 'center'; availableWrap.style.gap = '6px'; availableWrap.style.margin = '0'; availableWrap.style.fontSize = '.8rem';
        const available = document.createElement('input'); available.type = 'checkbox'; available.checked = product.is_available; available.setAttribute('aria-label', `Available ${product.name}`); availableWrap.append(available, document.createTextNode('Available'));
        const save = document.createElement('button'); save.type = 'button'; save.textContent = 'Save'; save.addEventListener('click', async () => {
          save.disabled = true;
          try {
            await api(`/api/admin/products/${product.id}`, { method: 'PATCH', body: JSON.stringify({ price: price.value, stock_quantity: Number(stock.value), is_available: available.checked }) });
            setMessage(productMessage, `${product.name} updated.`, 'success'); await loadCatalogue(); await loadManagedProducts();
          } catch (error) { setMessage(productMessage, error.message, 'error'); }
          finally { save.disabled = false; }
        });
        const details = document.createElement('button'); details.type = 'button'; details.textContent = 'Details';
        details.addEventListener('click', async () => {
          const nameValue = window.prompt('Product name:', product.name); if (nameValue === null) return;
          const descriptionValue = window.prompt('Description:', product.description || ''); if (descriptionValue === null) return;
          const imageValue = window.prompt('Image URL (https://… or /assets/…; blank to remove):', product.image_url || ''); if (imageValue === null) return;
          const dietaryValue = window.prompt('Dietary information:', product.dietary_info || ''); if (dietaryValue === null) return;
          const allergensValue = window.prompt('Allergens (leave blank if unknown):', product.allergens || ''); if (allergensValue === null) return;
          details.disabled = true;
          try {
            await api(`/api/admin/products/${product.id}`, { method: 'PATCH', body: JSON.stringify({ name: nameValue.trim(), description: descriptionValue.trim() || null, image_url: imageValue.trim() || null, dietary_info: dietaryValue.trim() || null, allergens: allergensValue.trim() || null }) });
            setMessage(productMessage, `${product.name} details updated.`, 'success'); await loadCatalogue(); await loadManagedProducts();
          } catch (error) { setMessage(productMessage, error.message, 'error'); }
          finally { details.disabled = false; }
        });
        const archive = document.createElement('button'); archive.type = 'button'; archive.className = 'archive-button'; archive.textContent = 'Archive'; archive.disabled = !product.is_available;
        archive.addEventListener('click', async () => {
          if (!window.confirm(`Archive ${product.name}? It will no longer appear in the student catalogue.`)) return;
          archive.disabled = true;
          try { await api(`/api/admin/products/${product.id}`, { method: 'DELETE' }); setMessage(productMessage, `${product.name} archived.`, 'success'); await loadCatalogue(); await loadManagedProducts(); }
          catch (error) { setMessage(productMessage, error.message, 'error'); archive.disabled = false; }
        });
        row.append(nameWrap, price, stock, availableWrap, save, details, archive); productList.append(row);
      }
      setMessage(productMessage, `${products.length} products loaded.`);
    } catch (error) { setMessage(productMessage, error.message, 'error'); }
  }
  async function loadManagedUsers() {
    if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'admin' || !userList) return;
    userList.replaceChildren(); setMessage(userMessage, 'Loading users…');
    try {
      const users = await api('/api/admin/users');
      for (const account of users) {
        const row = document.createElement('div'); row.className = `managed-product ${account.is_active ? '' : 'is-archived'}`;
        const info = document.createElement('div'); info.className = 'managed-product-name';
        const name = document.createElement('strong'); name.textContent = account.full_name;
        const email = document.createElement('small'); email.textContent = `${account.email} · ${account.role}`; info.append(name, email);
        const role = document.createElement('select'); role.setAttribute('aria-label', `Role for ${account.email}`);
        for (const value of ['student', 'staff', 'admin']) { const option = document.createElement('option'); option.value = value; option.textContent = value; role.append(option); }
        role.value = account.role;
        const activeLabel = document.createElement('label'); activeLabel.style.display = 'flex'; activeLabel.style.alignItems = 'center'; activeLabel.style.gap = '6px'; activeLabel.style.margin = '0';
        const active = document.createElement('input'); active.type = 'checkbox'; active.checked = account.is_active; active.setAttribute('aria-label', `Active ${account.email}`); activeLabel.append(active, document.createTextNode('Active'));
        if (account.id === window.aceCanteenUser.id) { role.disabled = true; active.disabled = true; }
        const save = document.createElement('button'); save.type = 'button'; save.textContent = 'Save user';
        save.addEventListener('click', async () => {
          save.disabled = true;
          try {
            if (role.value !== account.role) await api(`/api/admin/users/${account.id}/role`, { method: 'PATCH', body: JSON.stringify({ role: role.value }) });
            if (active.checked !== account.is_active) await api(`/api/admin/users/${account.id}/active?active=${active.checked}`, { method: 'PATCH' });
            setMessage(userMessage, `${account.email} updated.`, 'success'); await loadManagedUsers();
          } catch (error) { setMessage(userMessage, error.message, 'error'); }
          finally { save.disabled = false; }
        });
        row.append(info, role, activeLabel, save); userList.append(row);
      }
      setMessage(userMessage, `${users.length} accounts loaded. Role changes apply immediately to subsequent API requests.`);
    } catch (error) { setMessage(userMessage, error.message, 'error'); }
  }

  async function loadManagedCategories() {
    if (!window.aceCanteenToken || window.aceCanteenUser?.role !== 'admin' || !categoryList) return;
    categoryList.replaceChildren(); setMessage(categoryMessage, 'Loading categories…');
    try {
      const categories = await api('/api/admin/categories');
      for (const category of categories) {
        const row = document.createElement('div'); row.className = `managed-product ${category.is_active ? '' : 'is-archived'}`;
        const info = document.createElement('div'); info.className = 'managed-product-name';
        const title = document.createElement('strong'); title.textContent = category.name;
        const meta = document.createElement('small'); meta.textContent = `${category.item_type} · ${category.slug} · ${category.is_active ? 'Active' : 'Archived'}`; info.append(title, meta);
        const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = 'Edit';
        edit.addEventListener('click', async () => {
          const name = window.prompt('Category name:', category.name); if (name === null) return;
          const slug = window.prompt('URL slug (lowercase letters, numbers and hyphens):', category.slug); if (slug === null) return;
          const description = window.prompt('Description:', category.description || ''); if (description === null) return;
          edit.disabled = true;
          try { await api(`/api/admin/categories/${category.id}`, { method: 'PATCH', body: JSON.stringify({ name: name.trim(), slug: slug.trim(), description: description.trim() || null }) }); setMessage(categoryMessage, 'Category updated.', 'success'); await refreshCategoriesAndProducts(); }
          catch (error) { setMessage(categoryMessage, error.message, 'error'); }
          finally { edit.disabled = false; }
        });
        const toggle = document.createElement('button'); toggle.type = 'button'; toggle.textContent = category.is_active ? 'Archive' : 'Reactivate';
        toggle.addEventListener('click', async () => {
          if (!window.confirm(`${category.is_active ? 'Archive' : 'Reactivate'} category “${category.name}”?`)) return;
          toggle.disabled = true;
          try { await api(`/api/admin/categories/${category.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !category.is_active }) }); setMessage(categoryMessage, 'Category status updated.', 'success'); await refreshCategoriesAndProducts(); }
          catch (error) { setMessage(categoryMessage, error.message, 'error'); }
          finally { toggle.disabled = false; }
        });
        row.append(info, edit, toggle); categoryList.append(row);
      }
      setMessage(categoryMessage, `${categories.length} categories loaded.`);
    } catch (error) { setMessage(categoryMessage, error.message, 'error'); }
  }
  async function refreshCategoriesAndProducts() {
    await loadCategoryOptions();
    const response = await fetch('/api/categories'); catalogueCategories = response.ok ? await response.json() : catalogueCategories;
    updatePublicCategoryOptions(); await loadCatalogue(); await loadManagedCategories();
  }

  function syncRole(user) {
    const allowed = user && ['staff', 'admin'].includes(user.role);
    panel.hidden = !allowed;
    const adminOnly = user?.role === 'admin';
    const productForm = document.querySelector('#product-form');
    const productManager = document.querySelector('#manage-products-list')?.closest('.management-card');
    const inventoryPanel = document.querySelector('#inventory-management');
    if (productForm) productForm.hidden = !adminOnly;
    if (productManager) productManager.hidden = !adminOnly;
    if (inventoryPanel) inventoryPanel.hidden = !adminOnly;
    categoryForm.hidden = !adminOnly;
    if (categoryPanel) categoryPanel.hidden = user?.role !== 'admin';
    if (userPanel) userPanel.hidden = user?.role !== 'admin';
    if (allowed) { if (adminOnly) { loadCategoryOptions().catch(error => setMessage(productMessage, error.message, 'error')); loadManagedProducts(); loadManagedCategories(); loadManagedUsers(); } }
  }
  document.addEventListener('ace-auth-changed', event => syncRole(event.detail));
  productType?.addEventListener('change', () => loadCategoryOptions().catch(error => setMessage(document.querySelector('#product-form-message'), error.message, 'error')));
  document.querySelector('#refresh-products')?.addEventListener('click', loadManagedProducts);
  document.querySelector('#refresh-categories')?.addEventListener('click', loadManagedCategories);
  document.querySelector('#refresh-users')?.addEventListener('click', loadManagedUsers);
  document.querySelector('#staff-account-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget; const button = form.querySelector('button[type=submit]');
    const message = document.querySelector('#staff-account-message'); button.disabled = true; setMessage(message, 'Creating account…');
    try {
      const data = { full_name: document.querySelector('#staff-full-name').value.trim(), email: document.querySelector('#staff-email').value.trim(), role: document.querySelector('#staff-role').value, temporary_password: document.querySelector('#staff-temporary-password').value };
      const account = await api('/api/admin/users', { method: 'POST', body: JSON.stringify(data) });
      form.reset(); setMessage(message, `${account.role} account created for ${account.email}. The password is not displayed again.`, 'success'); await loadManagedUsers();
    } catch (error) { setMessage(message, error.message, 'error'); }
    finally { button.disabled = false; }
  });
  productForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const message = document.querySelector('#product-form-message');
    const button = productForm.querySelector('button[type=submit]'); button.disabled = true; setMessage(message, 'Saving product…');
    try {
      const data = { name: document.querySelector('#new-product-name').value.trim(), description: document.querySelector('#new-product-description').value.trim() || null, image_url: document.querySelector('#new-product-image').value.trim() || null, dietary_info: document.querySelector('#new-product-dietary').value.trim() || null, allergens: document.querySelector('#new-product-allergens').value.trim() || null, item_type: productType.value, category_id: Number(categorySelect.value), price: document.querySelector('#new-product-price').value, stock_quantity: Number(document.querySelector('#new-product-stock').value), is_available: true };
      await api('/api/admin/products', { method: 'POST', body: JSON.stringify(data) });
      productForm.reset(); productType.value = 'food'; document.querySelector('#new-product-stock').value = '10'; await loadCategoryOptions(); await loadCatalogue(); await loadManagedProducts(); setMessage(message, 'Product saved successfully.', 'success');
    } catch (error) { setMessage(message, error.message, 'error'); }
    finally { button.disabled = false; }
  });
  const categoryName = document.querySelector('#new-category-name');
  categoryName?.addEventListener('input', () => { const slug = document.querySelector('#new-category-slug'); if (!slug.dataset.edited) slug.value = categoryName.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); });
  document.querySelector('#new-category-slug')?.addEventListener('input', event => { event.target.dataset.edited = 'true'; });
  categoryForm?.addEventListener('submit', async event => {
    event.preventDefault(); const message = document.querySelector('#category-form-message'); const button = categoryForm.querySelector('button[type=submit]'); button.disabled = true; setMessage(message, 'Saving category…');
    try {
      await api('/api/admin/categories', { method: 'POST', body: JSON.stringify({ name: categoryName.value.trim(), slug: document.querySelector('#new-category-slug').value.trim(), item_type: document.querySelector('#new-category-type').value, description: document.querySelector('#new-category-description').value.trim() || null }) });
      categoryForm.reset(); document.querySelector('#new-category-slug').dataset.edited = ''; await refreshCategoriesAndProducts(); setMessage(message, 'Category saved successfully.', 'success');
    } catch (error) { setMessage(message, error.message, 'error'); }
    finally { button.disabled = false; }
  });
  if (window.aceCanteenUser) syncRole(window.aceCanteenUser);
})();


// Phase 8: privacy-preserving public pickup board and daily token queue.
async function loadPublicQueue() {
  const list = document.querySelector('#public-queue-list');
  const message = document.querySelector('#public-queue-message');
  if (!list || !message) return;
  try {
    const response = await fetch('/api/queue/overview', { headers: { Accept: 'application/json' } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not load the pickup queue.');
    document.querySelector('#queue-active-count').textContent = String(data.active_orders ?? 0);
    document.querySelector('#queue-preparing-tokens').textContent = data.preparing_tokens?.length ? data.preparing_tokens.map(n => `#${n}`).join(', ') : 'None';
    document.querySelector('#queue-ready-tokens').textContent = data.ready_tokens?.length ? data.ready_tokens.map(n => `#${n}`).join(', ') : 'None';
    document.querySelector('#queue-estimate-note').textContent = `${data.estimate_note || 'Wait times are estimates.'} · Updated ${new Date().toLocaleTimeString()}`;
    list.replaceChildren();
    if (!data.queue?.length) {
      message.textContent = 'There are no paid orders waiting for pickup right now.';
      const empty = document.createElement('p'); empty.className = 'management-message'; empty.textContent = 'New paid orders will appear here.'; list.append(empty); return;
    }
    message.textContent = `Queue for ${data.token_date}. Tokens are listed in arrival order.`;
    for (const item of data.queue) {
      const row = document.createElement('div'); row.className = 'queue-token-row';
      const token = document.createElement('strong'); token.textContent = `Token #${item.token_number}`;
      const status = document.createElement('span'); status.className = `queue-status status-${item.status}`; status.textContent = item.status.replaceAll('_', ' ');
      const wait = document.createElement('small'); wait.textContent = item.status === 'ready' ? 'Please collect now' : item.status === 'completed' ? 'Completed' : `Estimated wait: ${item.estimated_wait_minutes} min`;
      row.append(token, status, wait); list.append(row);
    }
  } catch (error) { message.textContent = error.message; }
}

// Student order history and staff/admin order queue. Status transitions are enforced server-side.
async function orderApi(url, options = {}) {
  if (!window.aceCanteenToken) throw new Error('Please sign in first.');
  const response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), Authorization: `Bearer ${window.aceCanteenToken}`, ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error?.message || `Request failed (${response.status})`);
  return data;
}
function orderRow(order, showCustomer = false, workflowStage = "all") {
  const row = document.createElement('div'); row.className = 'managed-product order-row';
  const info = document.createElement('div'); info.className = 'managed-product-name';
  const title = document.createElement('strong'); title.textContent = `Token #${order.token_number ?? '—'} · Order ${order.id} · ${order.status.toUpperCase()}`;
  const detail = document.createElement('small'); detail.textContent = `${showCustomer ? `${order.customer_name} (${order.customer_email}) · ` : ''}Payment: ${(order.payment_status || 'pending').toUpperCase()} · ${order.items.map(i => `${i.product_name} × ${i.quantity}`).join(', ')} · ₹${Number(order.subtotal).toFixed(2)} · ${new Date(order.created_at).toLocaleString()}${order.pickup_slot ? ` · Pickup ${new Date(order.pickup_slot).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}`;
  info.append(title, detail); row.append(info);
  if (!showCustomer && order.payment_status === 'paid' && order.pickup_qr_code) {
    const pickup = document.createElement('div'); pickup.className = 'order-pickup-qr';
    const label = document.createElement('strong'); label.textContent = order.status === 'completed' ? 'Pickup completed' : 'Your unique pickup QR';
    const code = document.createElement('div'); code.className = 'pickup-qr-image';
    const note = document.createElement('small'); note.textContent = order.status === 'completed' ? 'This QR has already been used.' : 'Show this QR to canteen staff when your order is ready. Keep it private.';
    pickup.append(label, code, note); row.append(pickup);
    if (order.status !== 'completed' && window.QRCode) new window.QRCode(code, { text: `${window.location.origin}/pickup#code=${encodeURIComponent(order.pickup_qr_code)}`, width: 156, height: 156, correctLevel: window.QRCode.CorrectLevel.M });
  }
  if (!showCustomer && order.payment_status === 'paid' && !['completed', 'cancelled'].includes(order.status)) {
    const tracker = document.createElement('div'); tracker.className = 'order-live-tracker'; tracker.setAttribute('aria-live', 'polite'); tracker.textContent = 'Updating live queue position…'; row.append(tracker);
    orderApi(`/api/orders/${order.id}/queue-position`).then(position => {
      const heading = document.createElement('strong');
      const statusText = String(position.status || order.status).replaceAll('_', ' ');
      heading.textContent = position.queue_position != null ? `Live tracking · queue position ${position.queue_position}` : `Live tracking · ${statusText}`;
      const estimate = document.createElement('small');
      estimate.textContent = position.estimated_wait_minutes != null ? `Estimated wait: about ${position.estimated_wait_minutes} minute(s). Updated ${new Date().toLocaleTimeString()}.` : `${position.message || 'Your order is not waiting in the active preparation queue.'} Updated ${new Date().toLocaleTimeString()}.`;
      tracker.replaceChildren(heading, estimate);
    }).catch(() => { tracker.textContent = 'Live tracking is temporarily unavailable. Your order status is shown above.'; });
  }
  if (!showCustomer && order.payment_status === 'paid' && order.status === 'completed') {
    const feedback = document.createElement('div'); feedback.className = 'order-feedback'; feedback.setAttribute('aria-label', 'Order feedback');
    const heading = document.createElement('strong'); heading.textContent = 'How was your order?';
    const form = document.createElement('form'); form.className = 'feedback-form';
    const rating = document.createElement('select'); rating.setAttribute('aria-label', 'Rating'); rating.required = true;
    for (let score = 5; score >= 1; score--) { const option = document.createElement('option'); option.value = String(score); option.textContent = `${score} / 5 stars`; rating.append(option); }
    const comment = document.createElement('input'); comment.type = 'text'; comment.maxLength = 500; comment.placeholder = 'Optional comment (up to 500 characters)'; comment.setAttribute('aria-label', 'Optional feedback comment');
    const submit = document.createElement('button'); submit.type = 'submit'; submit.className = 'secondary-button'; submit.textContent = 'Send feedback';
    const status = document.createElement('small'); status.setAttribute('role', 'status'); form.append(rating, comment, submit, status); feedback.append(heading, form); row.append(feedback);
    orderApi(`/api/orders/${order.id}/review`).then(existing => { if (existing.review) { rating.value = String(existing.review.rating); comment.value = existing.review.comment || ''; submit.textContent = 'Update feedback'; status.textContent = 'Thanks for sharing your feedback.'; } }).catch(() => {});
    form.addEventListener('submit', async event => { event.preventDefault(); submit.disabled = true; status.textContent = 'Saving feedback…'; try { const saved = await orderApi(`/api/orders/${order.id}/review`, { method: 'POST', body: JSON.stringify({ rating: Number(rating.value), comment: comment.value }) }); status.textContent = saved.message || 'Feedback saved. Thank you!'; submit.textContent = 'Update feedback'; } catch (error) { status.textContent = error.message; } finally { submit.disabled = false; } });
  }
  if (showCustomer && order.payment_status === 'paid') {
    const next = { pending: ['confirmed'], confirmed: ['preparing'], preparing: ['ready'], ready: ['completed'], completed: [], cancelled: [] }[order.status] || [];
    const allowedNext = workflowStage === 'kitchen' ? next.filter(status => ['confirmed', 'preparing', 'ready'].includes(status)) : workflowStage === 'counter' ? next.filter(status => status === 'completed') : next;
    for (const status of allowedNext) { const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary-button'; button.textContent = status[0].toUpperCase() + status.slice(1); button.addEventListener('click', async () => { button.disabled = true; try { await orderApi(`/api/admin/orders/${order.id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }); await loadOrderQueue(); if (typeof loadStaffWorkflow === 'function') await loadStaffWorkflow(); } catch (error) { alert(error.message); } finally { button.disabled = false; } }); row.append(button); }
  }
  return row;
}
async function loadMyOrders() {
  const list = document.querySelector('#my-orders-list'), message = document.querySelector('#my-orders-message'); if (!list || !message || !window.aceCanteenToken || window.aceCanteenUser?.role !== 'student') return;
  list.replaceChildren(); message.textContent = 'Loading your orders…';
  try { const orders = await orderApi('/api/orders/mine'); if (!orders.length) message.textContent = 'You have not placed any orders yet.'; else { message.textContent = `${orders.length} order(s) found. Keep your token for collection.`; orders.forEach(order => list.append(orderRow(order))); } } catch (error) { message.textContent = error.message; }
}
async function loadOrderQueue() {
  const list = document.querySelector('#order-queue-list'), message = document.querySelector('#order-queue-message'); if (!list || !message || !['admin', 'staff'].includes(window.aceCanteenUser?.role)) return;
  list.replaceChildren(); message.textContent = 'Loading incoming orders…';
  const filter = document.querySelector('#queue-status-filter')?.value;
  const paymentFilter = document.querySelector('#queue-payment-filter')?.value;
  const isAdmin = window.aceCanteenUser?.role === 'admin';
  try {
    let orders;
    if (isAdmin) {
      const params = new URLSearchParams({ limit: '500' });
      if (filter) params.set('status', filter);
      if (paymentFilter) params.set('payment_status', paymentFilter);
      const result = await orderApi(`/api/admin/orders/all?${params.toString()}`);
      orders = result.items || [];
      message.textContent = `${orders.length} order(s) shown · newest first · admin register includes pending/failed payments.`;
    } else {
      const result = await orderApi(`/api/admin/orders${filter ? `?status=${encodeURIComponent(filter)}` : ''}`);
      orders = result;
      message.textContent = `${orders.length} paid order(s) · queue is sorted oldest first.`;
    }
    if (!orders.length) message.textContent = 'No orders match these filters.';
    else orders.forEach(order => list.append(orderRow(order, true)));
  } catch (error) { message.textContent = error.message; }
}
// Phase 10: dedicated kitchen and pickup-counter work queues.
async function loadStaffWorkflow() {
  if (!['admin', 'staff'].includes(window.aceCanteenUser?.role)) return;
  const status = document.querySelector('#workflow-kitchen-waiting');
  if (!status) return;
  try {
    const summary = await orderApi('/api/staff/workflow-summary');
    document.querySelector('#workflow-kitchen-waiting').textContent = String(summary.kitchen_waiting ?? 0);
    document.querySelector('#workflow-kitchen-preparing').textContent = String(summary.kitchen_preparing ?? 0);
    document.querySelector('#workflow-ready-pickup').textContent = String(summary.ready_for_pickup ?? 0);
    document.querySelector('#workflow-completed-today').textContent = String(summary.completed_today ?? 0);
    const orders = await orderApi('/api/admin/orders');
    const kitchenOrders = orders.filter(order => ['pending', 'confirmed', 'preparing'].includes(order.status));
    const counterOrders = orders.filter(order => order.status === 'ready');
    const kitchenList = document.querySelector('#kitchen-board-list');
    const counterList = document.querySelector('#counter-board-list');
    const kitchenMessage = document.querySelector('#kitchen-board-message');
    const counterMessage = document.querySelector('#counter-board-message');
    kitchenList.replaceChildren(); counterList.replaceChildren();
    kitchenMessage.textContent = kitchenOrders.length ? `${kitchenOrders.length} paid order(s) · oldest first.` : 'No orders waiting for kitchen preparation.';
    counterMessage.textContent = counterOrders.length ? `${counterOrders.length} order(s) waiting for collection.` : 'No orders are currently ready for pickup.';
    kitchenOrders.forEach(order => kitchenList.append(orderRow(order, true, 'kitchen')));
    counterOrders.forEach(order => counterList.append(orderRow(order, true, 'counter')));
  } catch (error) {
    for (const id of ['kitchen-board-message', 'counter-board-message']) { const el = document.getElementById(id); if (el) el.textContent = error.message; }
  }
}
// Staff-only pickup QR scanning. The server verifies the signed code and payment before showing order details.
let pickupQrScanner = null;
let scannedPickupOrder = null;
async function verifyPickupQr(rawCode) {
  const message = document.querySelector('#pickup-qr-scan-message');
  const details = document.querySelector('#pickup-qr-order-details');
  if (!message || !details) return;
  details.replaceChildren(); scannedPickupOrder = null; message.textContent = 'Verifying QR with the server…';
  try {
    const scanned = String(rawCode || '').trim();
    const order = await orderApi('/api/staff/pickup/scan', { method: 'POST', body: JSON.stringify({ code: scanned }) });
    scannedPickupOrder = order;
    const heading = document.createElement('strong'); heading.textContent = `Order #${order.order_id} · Token #${order.token_number}`;
    const status = document.createElement('p'); status.textContent = `Student: ${order.customer_name} · Payment: ${String(order.payment_status || 'unknown').toUpperCase()} · Order time: ${new Date(order.created_at).toLocaleString()} · Pickup: ${order.pickup_slot ? new Date(order.pickup_slot).toLocaleString() : 'ASAP'} · Total: ₹${Number(order.subtotal).toFixed(2)}`;
    const items = document.createElement('ul');
    order.items.forEach(item => { const li = document.createElement('li'); li.textContent = `${item.product_name} × ${item.quantity} — ₹${Number(item.line_total).toFixed(2)}`; items.append(li); });
    const confirm = document.createElement('button'); confirm.type = 'button'; confirm.className = 'primary-button'; confirm.textContent = 'Confirm handover & mark collected';
    confirm.addEventListener('click', async () => {
      confirm.disabled = true;
      try {
        await orderApi(`/api/admin/orders/${order.order_id}/status`, { method: 'PATCH', body: JSON.stringify({ status: 'completed' }) });
        message.textContent = 'Collection recorded. This QR cannot be used again.'; details.replaceChildren(); scannedPickupOrder = null;
        const input = document.querySelector('#pickup-qr-code-input'); if (input) input.value = '';
        await loadStaffWorkflow(); await loadOrderQueue();
      } catch (error) { message.textContent = error.message; confirm.disabled = false; }
    });
    details.append(heading, status, items, confirm); message.textContent = order.message;
  } catch (error) { message.textContent = error.message; }
}
document.querySelector('#pickup-qr-check')?.addEventListener('click', () => verifyPickupQr(document.querySelector('#pickup-qr-code-input')?.value));
function startPickupQrScanner() {
  const panel = document.querySelector('#pickup-qr-scanner-panel');
  if (!panel || !['admin', 'staff'].includes(window.aceCanteenUser?.role) || !window.Html5Qrcode || pickupQrScanner) return;
  try {
    pickupQrScanner = new window.Html5Qrcode('pickup-qr-reader');
    pickupQrScanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 220, height: 220 } }, async decodedText => {
      await pickupQrScanner.stop().catch(() => {}); pickupQrScanner = null;
      const input = document.querySelector('#pickup-qr-code-input'); if (input) input.value = decodedText;
      await verifyPickupQr(decodedText);
    }, () => {}).catch(() => { pickupQrScanner = null; const msg = document.querySelector('#pickup-qr-scan-message'); if (msg) msg.textContent = 'Camera scan unavailable. Allow camera access or paste the QR code manually.'; });
  } catch (_) { pickupQrScanner = null; }
}
document.querySelector('#refresh-kitchen-board')?.addEventListener('click', loadStaffWorkflow);
document.querySelector('#refresh-counter-board')?.addEventListener('click', loadStaffWorkflow);
document.querySelector('#refresh-my-orders')?.addEventListener('click', loadMyOrders);
loadPublicQueue();
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadPublicQueue(); });
document.addEventListener('ace-auth-changed', () => { startPickupQrScanner(); });
startPickupQrScanner();
document.querySelector('#refresh-order-queue')?.addEventListener('click', loadOrderQueue);
document.querySelector('#queue-status-filter')?.addEventListener('change', loadOrderQueue);
document.querySelector('#queue-payment-filter')?.addEventListener('change', loadOrderQueue);
function syncHeaderAccount(user = window.aceCanteenUser) {
  const link = document.querySelector('#header-account-link'); const label = document.querySelector('#header-account-user');
  if (!link || !label) return;
  if (user) { link.textContent = 'My account'; label.textContent = `${user.full_name || user.name || user.email || 'Signed in'} · ${user.role || 'user'}`; label.hidden = false; }
  else { link.textContent = 'Sign in / Account'; label.textContent = ''; label.hidden = true; }
}
syncHeaderAccount();
document.querySelector('#header-account-link')?.addEventListener('click', () => {
  const user = window.aceCanteenUser;
  if (user) {
    const target = user.role === 'student' ? document.querySelector('#my-orders-section') : document.querySelector('#catalogue-management');
    if (target && !target.hidden) { target.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
  }
  document.querySelector('#account')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
document.addEventListener('ace-auth-changed', event => {
  const user = event.detail; syncHeaderAccount(user); renderCart(); const my = document.querySelector('#my-orders-section'); if (my) my.hidden = user?.role !== 'student';
  if (user?.role === 'student') loadMyOrders(); if (['admin', 'staff'].includes(user?.role)) { loadOrderQueue(); loadStaffWorkflow(); }
});


// Phase 7: refresh the staff queue periodically while a staff/admin session is active.
window.setInterval(() => {
  loadPublicQueue();
  if (['admin', 'staff'].includes(window.aceCanteenUser?.role)) { loadOrderQueue(); loadStaffWorkflow(); }
  if (window.aceCanteenUser?.role === 'student') loadMyOrders();
}, 15000);

// Phase 11: inventory ledger, low-stock alerts and controlled stock adjustments.
(() => {
  const root = document.querySelector('#inventory-management');
  if (!root) return;
  const byId = id => document.getElementById(id);
  const api = async (url, options = {}) => {
    const headers = { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(window.aceCanteenToken ? { Authorization: `Bearer ${window.aceCanteenToken}` } : {}) };
    const response = await fetch(url, { ...options, headers });
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || data?.error?.message || `Request failed (${response.status})`);
    return data;
  };
  const message = (id, text, kind = '') => { const el = byId(id); if (el) { el.textContent = text; el.className = `management-message ${kind}`.trim(); } };
  const option = (select, value, label) => { const el = document.createElement('option'); el.value = String(value); el.textContent = label; select.append(el); };
  const canManage = () => Boolean(window.aceCanteenToken && ['staff', 'admin'].includes(window.aceCanteenUser?.role));
  let productsCache = [];

  async function loadProducts() {
    productsCache = await api('/api/admin/products');
    for (const id of ['inventory-product', 'inventory-threshold-product', 'inventory-ledger-product']) {
      const select = byId(id); if (!select) continue;
      const previous = select.value;
      select.replaceChildren();
      if (id === 'inventory-ledger-product') option(select, '', 'All products');
      for (const product of productsCache) option(select, product.id, `${product.name} · ${product.stock_quantity} in stock`);
      if (id === 'inventory-ledger-product') select.insertBefore(select.firstChild, select.options[0] || null);
      if ([...select.options].some(o => o.value === previous)) select.value = previous;
    }
    syncThresholdValue();
  }
  function syncThresholdValue() {
    const product = productsCache.find(p => String(p.id) === byId('inventory-threshold-product')?.value);
    if (product) byId('inventory-threshold-value').value = product.low_stock_threshold ?? 5;
  }
  async function loadSummary() {
    const data = await api('/api/admin/inventory/summary');
    byId('inventory-product-count').textContent = data.tracked_products;
    byId('inventory-unit-count').textContent = data.total_units;
    byId('inventory-low-count').textContent = data.low_stock_count;
    byId('inventory-empty-count').textContent = data.out_of_stock_count;
    const list = byId('inventory-alert-list'); list.replaceChildren();
    if (!data.low_stock_items.length) { message('inventory-alert-message', 'All available products are above their low-stock thresholds.', 'success'); return; }
    message('inventory-alert-message', `${data.low_stock_items.length} product(s) need attention.`, 'error');
    for (const item of data.low_stock_items) {
      const row = document.createElement('div'); row.className = 'inventory-alert-row';
      const name = document.createElement('div'); const strong = document.createElement('strong'); strong.textContent = item.name; const small = document.createElement('small'); small.textContent = `${item.category_name || item.item_type} · ${item.item_type}`; name.append(strong, small);
      const qty = document.createElement('span'); qty.className = item.is_out_of_stock ? 'inventory-warning' : 'inventory-warning'; qty.textContent = item.is_out_of_stock ? 'OUT OF STOCK' : `${item.stock_quantity} left`;
      const threshold = document.createElement('span'); threshold.textContent = `Alert threshold: ${item.low_stock_threshold}`;
      const act = document.createElement('button'); act.type = 'button'; act.className = 'secondary-button'; act.textContent = 'Restock'; act.addEventListener('click', () => { byId('inventory-product').value = String(item.product_id); byId('inventory-movement-type').value = 'receipt'; byId('inventory-quantity').focus(); byId('inventory-adjustment-form').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
      row.append(name, qty, threshold, act); list.append(row);
    }
  }
  async function loadLedger() {
    const list = byId('inventory-ledger-list'); list.replaceChildren();
    const params = new URLSearchParams({ limit: '100' });
    if (byId('inventory-ledger-product').value) params.set('product_id', byId('inventory-ledger-product').value);
    if (byId('inventory-ledger-type').value) params.set('movement_type', byId('inventory-ledger-type').value);
    try {
      const rows = await api(`/api/admin/inventory/movements?${params}`);
      if (!rows.length) { message('inventory-ledger-message', 'No stock movements match these filters.'); return; }
      message('inventory-ledger-message', `Showing ${rows.length} most recent movement(s).`);
      for (const item of rows) {
        const row = document.createElement('div'); row.className = 'inventory-ledger-row';
        const name = document.createElement('div'); const strong = document.createElement('strong'); strong.textContent = item.product_name; const small = document.createElement('small'); small.textContent = `#${item.id} · ${item.movement_type}`; name.append(strong, small);
        const delta = document.createElement('span'); delta.className = item.quantity_delta > 0 ? 'inventory-delta-positive' : 'inventory-delta-negative'; delta.textContent = `${item.quantity_delta > 0 ? '+' : ''}${item.quantity_delta}`;
        const qty = document.createElement('span'); qty.textContent = `${item.quantity_before} → ${item.quantity_after}`;
        const actor = document.createElement('span'); actor.textContent = item.actor_name || (item.order_id ? `Order #${item.order_id}` : 'System / checkout');
        const reason = document.createElement('div'); reason.textContent = item.reason; const time = document.createElement('small'); time.textContent = item.created_at ? new Date(item.created_at).toLocaleString() : ''; reason.append(time);
        row.append(name, delta, qty, actor, reason); list.append(row);
      }
    } catch (error) { message('inventory-ledger-message', error.message, 'error'); }
  }
  async function refreshAll() {
    if (!canManage()) return;
    try { await loadProducts(); await Promise.all([loadSummary(), loadLedger()]); }
    catch (error) { message('inventory-alert-message', error.message, 'error'); }
  }
  byId('inventory-adjustment-form')?.addEventListener('submit', async event => {
    event.preventDefault(); if (!canManage()) return;
    const submit = event.currentTarget.querySelector('button[type="submit"]'); submit.disabled = true;
    try {
      const result = await api('/api/admin/inventory/adjustments', { method: 'POST', body: JSON.stringify({ product_id: Number(byId('inventory-product').value), movement_type: byId('inventory-movement-type').value, quantity: Number(byId('inventory-quantity').value), reason: byId('inventory-reason').value.trim() }) });
      message('inventory-form-message', `${result.product_name}: stock is now ${result.stock_quantity}. Movement recorded.`, 'success'); byId('inventory-reason').value = ''; await refreshAll();
    } catch (error) { message('inventory-form-message', error.message, 'error'); }
    finally { submit.disabled = false; }
  });
  byId('inventory-threshold-product')?.addEventListener('change', syncThresholdValue);
  byId('save-inventory-threshold')?.addEventListener('click', async () => {
    if (!canManage()) return;
    const button = byId('save-inventory-threshold'); button.disabled = true;
    try { const id = byId('inventory-threshold-product').value; const result = await api(`/api/admin/inventory/products/${id}/threshold`, { method: 'PATCH', body: JSON.stringify({ low_stock_threshold: Number(byId('inventory-threshold-value').value) }) }); message('inventory-threshold-message', `Threshold saved: alert at ${result.low_stock_threshold} units or fewer.`, 'success'); await refreshAll(); }
    catch (error) { message('inventory-threshold-message', error.message, 'error'); }
    finally { button.disabled = false; }
  });
  byId('refresh-inventory')?.addEventListener('click', refreshAll);
  byId('refresh-inventory-ledger')?.addEventListener('click', loadLedger);
  byId('inventory-ledger-product')?.addEventListener('change', loadLedger);
  byId('inventory-ledger-type')?.addEventListener('change', loadLedger);
  document.addEventListener('ace-auth-changed', () => { if (canManage()) refreshAll(); else { byId('inventory-alert-list').replaceChildren(); byId('inventory-ledger-list').replaceChildren(); } });
  document.querySelector('#refresh-products')?.addEventListener('click', () => { if (canManage()) refreshAll(); });
  if (canManage()) refreshAll();
  window.setInterval(() => { if (canManage() && !document.hidden) refreshAll(); }, 30000);
})();


// Phase 12: administrator-only reports, CSV export and audit trail.
(() => {
  const panel = document.querySelector('#admin-reporting');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  let lastDailySales = [];
  const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value || 0));
  const say = (id, text, kind = '') => { $(id).textContent = text; $(id).className = `management-message ${kind}`.trim(); };
  const api = async (url, options = {}) => {
    const response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...(window.aceCanteenToken ? { Authorization: `Bearer ${window.aceCanteenToken}` } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || data?.error?.message || `Request failed (${response.status})`);
    return data;
  };
  function dates() { return `start_date=${encodeURIComponent($('report-start-date').value)}&end_date=${encodeURIComponent($('report-end-date').value)}`; }
  function addRow(parent, className, left, right, detail = '') {
    const row = document.createElement('div'); row.className = className;
    const info = document.createElement('div'); const strong = document.createElement('strong'); strong.textContent = left; info.append(strong);
    if (detail) { const small = document.createElement('div'); small.className = 'report-detail'; small.textContent = detail; info.append(small); }
    const value = document.createElement('strong'); value.textContent = right; row.append(info, value); parent.append(row);
  }
  async function loadReports() {
    if (!window.aceCanteenUser || window.aceCanteenUser.role !== 'admin') return;
    const from = $('report-start-date').value, to = $('report-end-date').value;
    if (!from || !to || from > to) { say('report-message', 'Choose a valid date range (From must be on or before To).', 'error'); return; }
    say('report-message', 'Loading reports…');
    try {
      const [overview, daily, top] = await Promise.all([api(`/api/admin/reports/overview?${dates()}`), api(`/api/admin/reports/daily-sales?${dates()}`), api(`/api/admin/reports/top-products?${dates()}`)]);
      $('report-revenue').textContent = money(overview.paid_revenue); $('report-paid-orders').textContent = overview.paid_orders; $('report-all-orders').textContent = overview.all_orders; $('report-average-order').textContent = money(overview.average_paid_order_value);
      const statuses = $('report-status-list'); statuses.replaceChildren();
      for (const [status, count] of Object.entries(overview.orders_by_status)) addRow(statuses, 'report-status-row', status.replaceAll('_', ' '), String(count));
      const products = $('report-top-products'); products.replaceChildren();
      if (!top.length) { const empty = document.createElement('p'); empty.className = 'report-detail'; empty.textContent = 'No paid product sales in this date range.'; products.append(empty); }
      for (const item of top) addRow(products, 'report-product-row', item.product_name, money(item.sales), `${item.quantity_sold} item(s) sold`);
      const tbody = $('report-daily-sales'); tbody.replaceChildren(); lastDailySales = daily;
      for (const item of daily) { const tr = document.createElement('tr'); for (const value of [item.date, item.orders, money(item.revenue)]) { const td = document.createElement('td'); td.textContent = String(value); tr.append(td); } tbody.append(tr); }
      say('report-message', `Reports loaded for ${overview.start_date} through ${overview.end_date}.`, 'success');
    } catch (error) { say('report-message', error.message, 'error'); }
  }
  async function loadAudit() {
    if (!window.aceCanteenUser || window.aceCanteenUser.role !== 'admin') return;
    say('audit-message', 'Loading audit events…');
    const params = new URLSearchParams({ limit: '100' }); if ($('audit-entity-filter').value) params.set('entity_type', $('audit-entity-filter').value); if ($('audit-action-filter').value) params.set('action', $('audit-action-filter').value);
    try {
      const events = await api(`/api/admin/audit-events?${params}`); const list = $('audit-events-list'); list.replaceChildren();
      if (!events.length) { say('audit-message', 'No audit events match these filters.'); return; }
      for (const item of events) {
        const row = document.createElement('details'); row.className = 'audit-event-row'; const summary = document.createElement('summary'); summary.textContent = `${item.action} · ${item.entity_type} #${item.entity_id ?? '—'}`;
        const meta = document.createElement('p'); meta.className = 'report-detail'; meta.textContent = `${item.created_at ? new Date(item.created_at).toLocaleString() : 'Time unavailable'} · ${item.actor_name || 'Former/unknown user'} · Actor ID ${item.actor_user_id ?? '—'}`;
        const details = document.createElement('pre'); details.textContent = JSON.stringify(item.details, null, 2); row.append(summary, meta, details); list.append(row);
      }
      say('audit-message', `Showing ${events.length} audit event(s).`);
    } catch (error) { say('audit-message', error.message, 'error'); }
  }
  function sync(user) { panel.hidden = user?.role !== 'admin'; if (user?.role === 'admin') { loadReports(); loadAudit(); } else { $('report-daily-sales').replaceChildren(); $('audit-events-list').replaceChildren(); } }
  const now = new Date(); const localIso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; const start = new Date(now); start.setDate(start.getDate() - 29); $('report-start-date').value = localIso(start); $('report-end-date').value = localIso(now);
  $('report-filter-form').addEventListener('submit', event => { event.preventDefault(); loadReports(); });
  $('refresh-reports').addEventListener('click', loadReports); $('refresh-audit-events').addEventListener('click', loadAudit);
  $('audit-entity-filter').addEventListener('change', loadAudit); $('audit-action-filter').addEventListener('change', loadAudit);
  $('export-daily-sales').addEventListener('click', () => {
    if (!lastDailySales.length) { say('report-message', 'Run a report before exporting.', 'error'); return; }
    const quote = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
    const csv = [['Date', 'Paid orders', 'Revenue INR'], ...lastDailySales.map(row => [row.date, row.orders, row.revenue])].map(row => row.map(quote).join(',')).join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `ace-canteen-daily-sales-${$('report-start-date').value}-to-${$('report-end-date').value}.csv`; link.click(); URL.revokeObjectURL(url);
  });
  document.addEventListener('ace-auth-changed', event => sync(event.detail)); if (window.aceCanteenUser) sync(window.aceCanteenUser);
})();


// Phase 13: durable in-app notifications for students and staff, with owner-scoped read actions.
(() => {
  const panel = document.querySelector('#notification-center');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  const message = (text, kind = '') => { $('notification-message').textContent = text; $('notification-message').className = `management-message ${kind}`.trim(); };
  const escDate = value => { const date = value ? new Date(value) : null; return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : 'Just now'; };
  async function loadNotifications() {
    if (!window.aceCanteenToken || !window.aceCanteenUser) return;
    try {
      const response = await fetch('/api/notifications?limit=50', { headers: { Authorization: `Bearer ${window.aceCanteenToken}`, Accept: 'application/json' } });
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Could not load notifications.');
      $('notification-unread-count').textContent = `${data.unread_count} unread`;
      const list = $('notification-list'); list.replaceChildren();
      if (!data.items.length) { message('You are all caught up. New order and canteen updates will appear here.'); return; }
      message(`${data.items.length} recent notification(s). Updates refresh automatically.`);
      for (const item of data.items) {
        const row = document.createElement('article'); row.className = `notification-item${item.is_read ? ' is-read' : ' is-unread'}`;
        const heading = document.createElement('strong'); heading.textContent = item.title;
        const body = document.createElement('p'); body.textContent = item.message;
        const meta = document.createElement('small'); meta.textContent = `${escDate(item.created_at)}${item.is_read ? ' · Read' : ' · Unread'}`;
        row.append(heading, body, meta);
        if (!item.is_read) { const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary-button'; button.textContent = 'Mark read'; button.addEventListener('click', async () => { button.disabled = true; try { const r = await fetch(`/api/notifications/${item.id}/read`, { method: 'PATCH', headers: { Authorization: `Bearer ${window.aceCanteenToken}` } }); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || 'Could not mark as read.'); await loadNotifications(); } catch (e) { message(e.message, 'error'); button.disabled = false; } }); row.append(button); }
        list.append(row);
      }
    } catch (error) { message(error.message || 'Could not load notifications.', 'error'); }
  }
  $('notifications-mark-all')?.addEventListener('click', async () => {
    if (!window.aceCanteenToken) return;
    const button = $('notifications-mark-all'); button.disabled = true;
    try { const response = await fetch('/api/notifications/read-all', { method: 'POST', headers: { Authorization: `Bearer ${window.aceCanteenToken}` } }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Could not update notifications.'); await loadNotifications(); message(`${data.marked_read} notification(s) marked as read.`, 'success'); }
    catch (error) { message(error.message, 'error'); } finally { button.disabled = false; }
  });
  document.addEventListener('ace-auth-changed', event => { if (event.detail) loadNotifications(); else { $('notification-list').replaceChildren(); $('notification-unread-count').textContent = '0 unread'; message('Sign in to view notifications.'); } });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && window.aceCanteenUser) loadNotifications(); });
  window.setInterval(() => { if (!document.hidden && window.aceCanteenUser) loadNotifications(); }, 20000);
  if (window.aceCanteenUser) loadNotifications();
})();


// Phase 45: visual admin control centre backed by the admin-only register APIs.
(() => {
  const $ = id => document.getElementById(id);
  const panel = $('admin-control-centre');
  if (!panel) return;
  let page = 0, debounce = null;
  const pageSize = 50;
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function request(path, options = {}) {
    if (!window.aceCanteenToken) throw new Error('Please sign in with an administrator account.');
    const response = await fetch(path, {...options, headers: {...(options.headers || {}), Authorization: `Bearer ${window.aceCanteenToken}`}});
    const type = response.headers.get('content-type') || '';
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { const data = type.includes('json') ? await response.json() : null; detail = data?.detail || detail; } catch {}
      throw new Error(detail);
    }
    return type.includes('json') ? response.json() : response;
  }
  function message(id, text, bad = false) { const el = $(id); if (el) { el.textContent = text; el.classList.toggle('error', bad); } }
  function adminVisible() {
    const allowed = window.aceCanteenUser?.role === 'admin' && !!window.aceCanteenToken;
    panel.hidden = !allowed;
    if (allowed) { loadSummary(); loadOrders(); loadWebhooks(); }
  }
  async function loadSummary() {
    try {
      const d = await request('/api/admin/dashboard/summary');
      const cards = [
        ['All orders', d.orders_total], ['Paid orders', d.orders_paid], ['Open orders', d.orders_open],
        ['Pending payments', d.payments_pending], ['Failed payments', d.payments_failed],
        ['Paid revenue', `₹${Number(d.paid_revenue || 0).toLocaleString('en-IN',{maximumFractionDigits:2})}`],
        ['Low-stock products', d.low_stock_products], ['Active users', d.active_users]
      ];
      $('admin-kpi-grid').replaceChildren(...cards.map(([label,value]) => {
        const card = document.createElement('div'); card.className = 'admin-kpi-card';
        const strong = document.createElement('strong'); strong.textContent = value ?? 0;
        const span = document.createElement('span'); span.textContent = label;
        card.append(strong, span); return card;
      }));
    } catch (e) { message('admin-orders-message', `Dashboard: ${e.message}`, true); }
  }
  async function loadOrders() {
    if (window.aceCanteenUser?.role !== 'admin') return;
    const body = $('admin-orders-body'); body.replaceChildren();
    message('admin-orders-message', 'Loading order register…');
    const query = new URLSearchParams({limit:String(pageSize),offset:String(page*pageSize)});
    const search = $('admin-order-search').value.trim(), status = $('admin-order-status').value, payment = $('admin-payment-status').value;
    if (search) query.set('search', search); if (status) query.set('status', status); if (payment) query.set('payment_status', payment);
    try {
      const data = await request(`/api/admin/orders/all?${query}`);
      for (const order of data.items || []) {
        const tr = document.createElement('tr');
        const values = [
          `#${order.id}`, `${order.customer_name || ''}\n${order.customer_email || ''}`,
          order.created_at ? new Date(order.created_at).toLocaleString() : '—',
          order.status, order.payment_status, `₹${Number(order.subtotal || 0).toFixed(2)}`, order.token_number || '—'
        ];
        for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
        body.append(tr);
      }
      message('admin-orders-message', `${data.returned} order(s) shown. All payment states are included unless filtered.`);
      $('admin-orders-page').textContent = `Page ${page+1} · ${data.returned} rows`;
      $('admin-orders-prev').disabled = page === 0;
      $('admin-orders-next').disabled = data.returned < pageSize;
    } catch (e) { message('admin-orders-message', e.message, true); }
  }
  async function loadWebhooks() {
    try {
      const data = await request('/api/admin/payments/webhook-events?limit=100&offset=0');
      const body = $('admin-webhooks-body'); body.replaceChildren();
      for (const event of data.items || []) {
        const tr = document.createElement('tr');
        for (const value of [event.event_id, event.event_name, event.received_at ? new Date(event.received_at).toLocaleString() : '—']) {
          const td = document.createElement('td'); td.textContent = value || '—'; tr.append(td);
        }
        body.append(tr);
      }
      message('admin-webhook-message', `${data.returned} recent webhook event(s).`);
    } catch (e) { message('admin-webhook-message', e.message, true); }
  }
  $('admin-refresh-orders').addEventListener('click', () => { page=0; loadSummary(); loadOrders(); });
  ['admin-order-status','admin-payment-status'].forEach(id => $(id).addEventListener('change', () => { page=0; loadOrders(); }));
  $('admin-order-search').addEventListener('input', () => { clearTimeout(debounce); debounce=setTimeout(() => { page=0; loadOrders(); }, 300); });
  $('admin-orders-prev').addEventListener('click', () => { if (page > 0) { page--; loadOrders(); } });
  $('admin-orders-next').addEventListener('click', () => { page++; loadOrders(); });
  $('admin-refresh-webhooks').addEventListener('click', loadWebhooks);
  $('admin-export-orders').addEventListener('click', async () => {
    try {
      const query = new URLSearchParams();
      if ($('admin-order-status').value) query.set('status',$('admin-order-status').value);
      if ($('admin-payment-status').value) query.set('payment_status',$('admin-payment-status').value);
      const response = await request(`/api/admin/orders/export.csv?${query}`);
      const blob = await response.blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href=url; a.download='ace-canteen-orders.csv'; a.click(); URL.revokeObjectURL(url);
      message('admin-orders-message','CSV export downloaded.');
    } catch(e) { message('admin-orders-message',e.message,true); }
  });
  document.addEventListener('ace-auth-changed', adminVisible);
  adminVisible();
})();


// Phase 49: canteen open/closed banner, pickup-time slots, and the staff ordering switch.
(() => {
  const $ = id => document.querySelector(id);
  const banner = $('#canteen-status'), slotWrap = $('#pickup-slot-wrap'), slotSelect = $('#pickup-slot');
  const controlState = $('#canteen-control-state'), toggle = $('#canteen-toggle'), pauseInput = $('#canteen-pause-message'), controlMessage = $('#canteen-control-message');
  if (!banner || !slotSelect) return;
  let current = null;
  function apply(status, slots) {
    current = status;
    window.aceCanteenClosed = !status.accepting_orders;
    if (!status.accepting_orders) { banner.textContent = status.message; banner.className = 'canteen-status closed'; banner.hidden = false; }
    else if (status.hours_configured) { banner.textContent = `Open now · ordering hours ${status.open_time}–${status.close_time}`; banner.className = 'canteen-status open'; banner.hidden = false; }
    else banner.hidden = true;
    const keep = slotSelect.value;
    slotSelect.replaceChildren(new Option('As soon as possible', ''));
    for (const slot of slots) { const option = new Option(slot.remaining > 0 ? slot.label : `${slot.label} (full)`, slot.slot); option.disabled = slot.remaining <= 0; slotSelect.append(option); }
    if ([...slotSelect.options].some(o => o.value === keep && !o.disabled)) slotSelect.value = keep;
    slotWrap.hidden = !status.slots_enabled || !slots.length;
    if (controlState) {
      controlState.textContent = status.paused ? `Ordering is PAUSED. ${status.message}` : (status.accepting_orders ? 'Ordering is open.' : status.message);
      toggle.textContent = status.paused ? 'Resume ordering' : 'Pause ordering';
      pauseInput.hidden = status.paused;
    }
    if (typeof renderCart === 'function') renderCart();
  }
  async function refresh() {
    try {
      const [status, slots] = await Promise.all([fetch('/api/canteen/status').then(r => r.json()), fetch('/api/canteen/slots').then(r => r.json())]);
      apply(status, slots.slots || []);
    } catch { /* offline: keep the last known state */ }
  }
  toggle?.addEventListener('click', async () => {
    toggle.disabled = true; controlMessage.textContent = 'Saving…';
    try {
      const response = await fetch('/api/admin/canteen/ordering', { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${window.aceCanteenToken}` }, body: JSON.stringify({ paused: !(current && current.paused), message: pauseInput.value.trim() || null }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not change ordering state.');
      controlMessage.textContent = data.paused ? 'Ordering paused. Students see your message.' : 'Ordering resumed.';
      await refresh();
    } catch (error) { controlMessage.textContent = error.message; }
    finally { toggle.disabled = false; }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  refresh();
})();
