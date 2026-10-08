// apiv4 is same-origin here, so the admin session authorises these calls.

(function () {
  "use strict";
  const RECONCILE = "/api/v4/admin/storage/reconcile";
  const REPORT = "/api/v4/admin/storage/reconcile/report";

  function run(apply) {
    $("#reconcile-progress").text(apply ? "Applying…" : "Reporting…");
    $.ajax({
      type: "POST",
      url: RECONCILE,
      contentType: "application/json",
      data: JSON.stringify({ apply: !!apply }),
    })
      .done(function (res) {
        $("#reconcile-progress").text(
          "Enqueued " + res.enqueued + " pool task(s); running…"
        );
        pollReport(6);
      })
      .fail(function (xhr) {
        $("#reconcile-progress").text("Error: " + (xhr.responseText || xhr.status));
      });
  }

  function pollReport(tries) {
    $.ajax({ type: "GET", url: REPORT })
      .done(function (rep) {
        renderReport(rep);
        if (tries > 0) {
          setTimeout(function () {
            pollReport(tries - 1);
          }, 3000);
        } else {
          $("#reconcile-progress").text("Done.");
        }
      })
      .fail(function () {
        $("#reconcile-progress").text("Could not read the report.");
      });
  }

  function renderReport(rep) {
    const pools = (rep && rep.pools) || {};
    const perCat = (rep && rep.bytes_per_category) || {};
    let html = "<h4>Last report</h4>";
    html +=
      "<table class='table'><thead><tr><th>Pool</th><th>Class</th>" +
      "<th>Value</th><th>Updated</th></tr></thead><tbody>";
    Object.keys(pools).forEach(function (pool) {
      const entry = pools[pool] || {};
      const m = entry.metrics || {};
      const ts = entry.updated_at
        ? new Date(entry.updated_at * 1000).toLocaleString()
        : "";
      Object.keys(m).forEach(function (cls) {
        if (cls === "pool") return;
        html +=
          "<tr><td>" +
          pool +
          "</td><td>" +
          cls +
          "</td><td>" +
          m[cls] +
          "</td><td>" +
          ts +
          "</td></tr>";
      });
    });
    html += "</tbody></table>";
    html += "<h4>Drift bytes per category</h4><table class='table'><tbody>";
    Object.keys(perCat).forEach(function (cat) {
      html += "<tr><td>" + cat + "</td><td>" + perCat[cat] + "</td></tr>";
    });
    html += "</tbody></table>";
    $("#reconcile-report").html(html);
  }

  $(function () {
    $("#btn-reconcile-report").on("click", function () {
      run(false);
    });
    $("#btn-reconcile-apply").on("click", function () {
      if (
        window.confirm(
          "Apply will re-measure and correct the size of ready disks. Continue?"
        )
      ) {
        run(true);
      }
    });
    pollReport(0);
  });
})();
