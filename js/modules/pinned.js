import { api } from "./api.js";
import { md } from "./markdown.js";
export async function renderPinned(el) {
  const items = await api.list("?type=note");
  const pinned = items.filter(i => i.pinned);
  el.innerHTML = pinned.map(i =>
    `<div class="resource-tile" style="min-width:14rem">
      <strong>${i.title}</strong>${md(i.body)}
    </div>`).join("");
}
