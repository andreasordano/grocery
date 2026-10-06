// Sending a dinner by link. Whoever opens the link gets the dinner priced at their own stores.
import { $ } from "./dom.js";
import { esc } from "./format.js";
import { api } from "./api.js";
import { identity } from "./identity.js";

// On phones the share sheet opens; elsewhere the link is copied.
export async function shareDinner(recipe) {
  const note = $("#shareNote");
  try {
    const { path } = await api("/shares", { recipe_id: recipe.id, user_id: identity.userId });
    const url = location.origin + path;
    if (navigator.share && matchMedia("(pointer: coarse)").matches) {
      await navigator.share({ title: recipe.name, text: `${recipe.name}: here's where to shop for it`, url }).catch(() => {});
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      note.textContent = "Link copied. Paste it in a message.";
    } catch {  // no clipboard access: show the link to copy by hand
      note.insertAdjacentHTML("afterend", `<input readonly value="${esc(url)}" aria-label="Link to this dinner">`);
      note.textContent = "Copy this link:";
      note.nextElementSibling.select();
    }
  } catch {
    note.textContent = "Couldn't make a link. Try again.";
  }
}
