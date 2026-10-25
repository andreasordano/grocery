// Keeps the basket until Rimi's page has loaded, then rimi.js takes it.
chrome.runtime.onMessage.addListener(msg => {
  if (msg?.type !== "fill-cart" || msg.store !== "rimi") return;
  chrome.storage.local.set({ pending: { store: "rimi", items: msg.items, at: Date.now() } })
    .then(() => chrome.tabs.create({ url: "https://www.rimi.ee/epood/ee" }));
});
