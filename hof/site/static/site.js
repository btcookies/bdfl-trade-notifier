// Table sorting on any table.sortable, and the player search on the players page. No dependencies.
(function () {
  function cellValue(row, index) {
    var cell = row.children[index];
    if (!cell) return "";
    var raw = cell.getAttribute("data-sort") || cell.textContent.trim();
    var number = parseFloat(raw.replace(/[,+]/g, ""));
    return isNaN(number) ? raw.toLowerCase() : number;
  }

  function sortTable(table, index, descending) {
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.querySelectorAll("tr:not(.sub)"));
    rows.sort(function (a, b) {
      var x = cellValue(a, index), y = cellValue(b, index);
      if (typeof x === "number" && typeof y === "number") return descending ? y - x : x - y;
      x = String(x); y = String(y);
      return descending ? y.localeCompare(x) : x.localeCompare(y);
    });
    rows.forEach(function (row) { body.appendChild(row); });
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell) { cell.classList.remove("asc", "desc"); });
    table.tHead.rows[0].cells[index].classList.add(descending ? "desc" : "asc");
  }

  document.querySelectorAll("table.sortable").forEach(function (table) {
    if (!table.tHead || !table.tBodies.length) return;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell, index) {
      cell.addEventListener("click", function () {
        var descending = !cell.classList.contains("desc");
        sortTable(table, index, descending);
      });
    });
  });

  var search = document.getElementById("player-search");
  if (search) {
    var rows = document.querySelectorAll("#players tbody tr");
    search.addEventListener("input", function () {
      var needle = search.value.trim().toLowerCase();
      rows.forEach(function (row) {
        row.hidden = needle !== "" && row.getAttribute("data-name").indexOf(needle) === -1;
      });
    });
  }
})();
