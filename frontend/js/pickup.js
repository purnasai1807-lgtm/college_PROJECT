(() => {
  const title = document.querySelector('#title');
  const message = document.querySelector('#message');
  const details = document.querySelector('#details');
  const fmtDate = value => value ? new Date(value).toLocaleString() : 'Not recorded yet';
  const el = (tag, text, cls) => { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; return node; };
  async function load() {
    const code = new URLSearchParams(window.location.hash.slice(1)).get('code');
    if (!code) throw new Error('This pickup link is missing its secure code. Please open the QR code again.');
    const response = await fetch('/api/pickup/status', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ code }), cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Could not verify this pickup code.');
    title.textContent = `Order #${data.order_id} · Token #${data.token_number ?? '—'}`;
    message.textContent = data.status === 'completed' ? 'This order has already been collected.' : 'Live order details verified with the canteen server.';
    const grid = el('div', '', 'grid');
    const paymentClass = data.payment_status === 'paid' ? 'pill' : (data.payment_status === 'failed' || data.payment_status === 'refunded' ? 'pill bad' : 'pill warn');
    const statusClass = data.status === 'completed' ? 'pill' : (data.status === 'cancelled' ? 'pill bad' : 'pill warn');
    [[ 'Payment status', data.payment_status.toUpperCase(), paymentClass ], ['Order status', data.status.replaceAll('_',' '), statusClass], ['Order placed', fmtDate(data.created_at)], ['Pickup time', fmtDate(data.pickup_slot)], ['Last updated', fmtDate(data.updated_at)], ['Collected at', fmtDate(data.collected_at)]].forEach(([label,value,cls]) => {
      const box = el('div', '', 'stat'); box.append(el('span', label)); box.append(el('strong', value, cls)); grid.append(box);
    });
    details.append(grid, el('h2', 'Products', '')); const list = el('ul', '');
    data.items.forEach(item => { const li = el('li', ''); const line = el('div', '', 'line'); line.append(el('span', `${item.product_name} × ${item.quantity}`), el('strong', `₹${Number(item.line_total).toFixed(2)}`)); li.append(line); list.append(li); });
    details.append(list); const total = el('div', '', 'line'); total.append(el('strong','Order total'),el('strong',`₹${Number(data.subtotal).toFixed(2)}`)); details.append(total);
    if (data.payment_status !== 'paid') message.textContent += ' Do not hand over products unless authorized staff can verify payment as paid.';
  }
  load().catch(error => { title.textContent = 'Unable to verify pickup'; message.textContent = error.message; message.className = 'error'; });
})();
