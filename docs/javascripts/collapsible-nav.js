// Collapse all nav sections by default, expand only active
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("input.md-toggle[id^='__nav']").forEach(function (toggle) {
    var item = toggle.closest(".md-nav__item");
    if (!item) return;
    var hasActive = item.querySelector(".md-nav__link--active") !== null;
    toggle.checked = hasActive;
  });
});
