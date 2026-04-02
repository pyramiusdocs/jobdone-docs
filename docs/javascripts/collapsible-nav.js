// GitBook-style: all nav sections collapsed by default,
// only expand the section containing the current page.
document.addEventListener("DOMContentLoaded", function () {
  // Find all nav toggle checkboxes (MkDocs Material uses __nav_N ids)
  document.querySelectorAll("input.md-toggle[id^='__nav']").forEach(function (toggle) {
    // Get the parent nav item
    var item = toggle.closest(".md-nav__item");
    if (!item) return;

    // Check if this section contains the active page
    var hasActivePage = item.querySelector(".md-nav__link--active") !== null;

    // Collapse all sections except the one with the active page
    toggle.checked = hasActivePage;
  });
});
