import "./marked.min.js";

// DOMPurify is loaded as a global via <script> tag in index.html
// We reference it via the global window.DOMPurify

export function md(s) {
  if (!s) return "";
  let html;
  try {
    html = window.marked ? window.marked.parse(s) : s;
  } catch (e) {
    console.warn("markdown parse failed:", e);
    return escapeHtml(String(s));
  }

  // Sanitize HTML to prevent XSS
  if (window.DOMPurify && window.DOMPurify.sanitize) {
    try {
      html = window.DOMPurify.sanitize(html, {
        ALLOWED_TAGS: [
          "h1","h2","h3","h4","h5","h6","p","br","hr",
          "strong","em","b","i","u","s","del","ins","sub","sup",
          "a","img","code","pre","blockquote",
          "ul","ol","li","table","thead","tbody","tr","th","td",
          "div","span","details","summary","section","nav"
        ],
        ALLOWED_ATTR: ["href","src","alt","title","class","id","target","rel"],
        ALLOW_DATA_ATTR: false,
      });
    } catch (e) {
      console.warn("DOMPurify sanitize failed, using escaped output:", e);
      html = escapeHtml(String(s));
    }
    return html;
  }

  return escapeHtml(String(s));
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
