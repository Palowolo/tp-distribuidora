'use strict';
function formatGs(value) {
  return 'Gs. ' + new Intl.NumberFormat('es-PY', {maximumFractionDigits: 0}).format(value ?? 0);
}
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
}));
document.getElementById('go-back')?.addEventListener('click', () => history.back());
const items = document.getElementById('items');
if (items) {
  let nextId = 1;
  const calculate = () => {
    let total = 0n;
    items.querySelectorAll('.order-item').forEach(row => {
      const select = row.querySelector('.item-product');
      const qty = row.querySelector('.item-qty').value;
      const price = BigInt(select.selectedOptions[0]?.dataset.price || '0');
      const subtotal = /^\d{1,7}$/.test(qty) ? BigInt(qty) * price : 0n;
      row.querySelector('.subtotal').textContent = formatGs(subtotal);
      total += subtotal;
    });
    document.getElementById('order-total').textContent = formatGs(total);
  };
  items.addEventListener('input', calculate);
  items.addEventListener('change', calculate);
  document.getElementById('add-item').addEventListener('click', () => {
    if (items.children.length >= 100) return;
    const clone = items.firstElementChild.cloneNode(true);
    clone.querySelector('select').selectedIndex = 0;
    clone.querySelector('input').value = '1';
    clone.querySelectorAll('label').forEach((label, i) => {
      const control = clone.querySelectorAll('select,input')[i];
      control.id = `${i === 0 ? 'producto' : 'cantidad'}_${nextId}`;
      label.htmlFor = control.id;
    });
    nextId += 1;
    items.append(clone);
    clone.querySelector('select').focus();
    calculate();
  });
  items.addEventListener('click', event => {
    if (event.target.matches('.remove-item') && items.children.length > 1) {
      event.target.closest('.order-item').remove(); calculate();
    }
  });
  calculate();
}
