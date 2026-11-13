const adminToken = window.HAGAR_TOKEN;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setAdminStatus(text, isError) {
  const box = document.getElementById('status');
  if (!box) return;
  box.textContent = text || '';
  box.classList.toggle('error', Boolean(isError));
}

async function adminApi(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Hagar-Token': adminToken,
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || ('HTTP ' + response.status));
  }
  return data;
}

function formatBytes(value) {
  if (value === null || value === undefined) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let number = Number(value);
  let index = 0;
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024;
    index++;
  }
  return (index === 0 ? number : number.toFixed(1)) + ' ' + units[index];
}
