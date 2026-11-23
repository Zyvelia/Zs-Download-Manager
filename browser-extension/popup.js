const result = document.getElementById('result');
chrome.storage.local.get('lastError', data => {
  if (data.lastError) { result.textContent = data.lastError; chrome.storage.local.remove('lastError'); chrome.action.setBadgeText({text: ''}); }
});
document.getElementById('send').addEventListener('click', () => {
  const url = document.getElementById('url').value.trim();
  if (!url) { result.textContent = 'Paste a link first.'; return; }
  result.textContent = 'Sending…';
  chrome.runtime.sendMessage({url}, response => {
    result.textContent = chrome.runtime.lastError ? chrome.runtime.lastError.message : (response?.message || 'No response.');
  });
});
