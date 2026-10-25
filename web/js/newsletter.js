// "Get next week's plan by email" (WEB-37): offered once after the first-visit questions, and under the receipt
// until someone signs up. The address goes to MailerLite (through the server), which asks them to confirm.
import { $ } from "./dom.js";
import { esc } from "./format.js";
import { api, logEvent } from "./api.js";
import { identity } from "./identity.js";
import { storage } from "./storage.js";

const signedUp = () => storage.get("pantryrun.newsletter", null) === "yes";

const form = where => `
  <h3 id="nlTitle-${where}">Get next week's plan by email</h3>
  <p class="fine">Every week: four dinners for your household, one shopping list and the cheapest store.
    The first one comes after your first week with pantryrun.</p>
  <input class="nl-email" type="email" name="email" autocomplete="email" placeholder="you@example.com" maxlength="200"
    aria-label="Your email" required>
  <label class="nl-consent"><input type="checkbox" name="consent" required>
    <span>Email me the weekly plan. I can unsubscribe in every email. <a href="privacy.html">How pantryrun uses your email</a></span></label>
  <p class="fine nl-note" role="status"></p>`;

async function send(box, where) {
  const note = $(".nl-note", box);
  const email = $("input[name=email]", box), consent = $("input[name=consent]", box);
  if (!email.reportValidity() || !consent.reportValidity()) return false;
  note.textContent = "Signing you up…";
  try {
    await api("/newsletter", { email: email.value, consent: consent.checked, user_id: identity.personId, name: identity.name, where });
    storage.set("pantryrun.newsletter", "yes");
    return true;
  } catch (e) {
    note.textContent = { 400: "Check the email address.", 503: "Sign-up isn't open yet. Try again in a few days." }[e.message]
      ?? "Couldn't sign you up just now. Try again later.";
    return false;
  }
}

// Under the receipt: a box to fill in, until someone has signed up.
export function newsletterBox() {
  return signedUp() ? "" : `<form class="newsletter" id="newsletter" aria-labelledby="nlTitle-receipt" novalidate>
    ${form("receipt")}<button class="btn quiet" type="submit">Send me the plan</button></form>`;
}

export function bindNewsletterBox() {
  const box = $("#newsletter");
  if (!box) return;
  box.onsubmit = async e => {
    e.preventDefault();
    if (await send(box, "receipt"))
      box.innerHTML = `<p class="thanks">Almost done: check your inbox and confirm your email.</p>`;
  };
}

// After the first-visit questions: asked once, and "Not now" is fine.
export function offerNewsletter() {
  if (signedUp() || storage.get("pantryrun.newsletterAsked", false)) return Promise.resolve();
  storage.set("pantryrun.newsletterAsked", true);
  const dialog = $("#news"), box = $("#newsForm");
  box.innerHTML = `<div class="sh-top">${form("first_visit")}</div>
    <div class="sh-bottom"><button class="link" type="button" id="newsLater">Not now</button>
      <button class="btn dark" type="submit">Send me the plan</button></div>`;
  return new Promise(resolve => {
    const done = answer => { logEvent("newsletter_offer", { where: "first_visit", answer }); dialog.close(); resolve(); };
    $("#newsLater", box).onclick = () => done("later");
    dialog.oncancel = e => { e.preventDefault(); done("later"); };
    box.onsubmit = async e => {
      e.preventDefault();
      const address = $("input[name=email]", box).value;
      if (await send(box, "first_visit")) {
        $(".sh-top", box).innerHTML = `<h3>Almost done</h3><p>Check your inbox at ${esc(address)} and confirm your email.</p>`;
        $(".sh-bottom", box).innerHTML = `<button class="btn dark" type="button" id="newsDone">OK</button>`;
        $("#newsDone", box).onclick = () => done("signed_up");
      }
    };
    dialog.showModal();
  });
}
