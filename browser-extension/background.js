const HOST = 'com.zyvelia.z_download_manager';
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({id: 'send-link', title: "Send link to Z's Download Manager", contexts: ['link']});
});
function send(url) {
  return new Promise(resolve => {
    chrome.runtime.sendNativeMessage(HOST, {url}, response => {
      if (chrome.runtime.lastError) resolve({ok: false, message: chrome.runtime.lastError.message});
      else resolve(response || {ok: false, message: 'No response from the local app.'});
    });
  });
}
chrome.contextMenus.onClicked.addListener(async info => {
  if (info.menuItemId !== 'send-link' || !info.linkUrl) return;
  const result = await send(info.linkUrl);
  if (!result.ok) {
    chrome.action.setBadgeText({text: '!'});
    chrome.action.setBadgeBackgroundColor({color: '#dc426b'});
    chrome.storage.local.set({lastError: result.message});
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !message || typeof message.url !== 'string') return;
  send(message.url).then(respond); return true;
});
