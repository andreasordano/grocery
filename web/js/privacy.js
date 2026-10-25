// The privacy page: asking for one's data to be deleted. The request is logged with the person's ID,
// and the data is deleted by hand within 30 days (no email address needed).
import { $ } from "./dom.js";
import { identity } from "./identity.js";
import { logEvent } from "./api.js";

$("#askDelete").onclick = async () => {
  await logEvent("delete_request", { person: identity.personId });
  $("#askDelete").disabled = true;
  $("#deleteNote").textContent = "Asked. Your data will be deleted within 30 days.";
};
