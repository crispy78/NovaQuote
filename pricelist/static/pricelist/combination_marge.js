;(function () {
  function getProductPrices() {
    var el = document.getElementById("product-prices") || document.getElementById("product-prijzen");
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent) || {};
    } catch (e) {
      return {};
    }
  }

  function getMarginLabels() {
    var el = document.getElementById("combination-margin-labels") || document.getElementById("combinatie-marge-labels");
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent) || {};
    } catch (e) {
      return {};
    }
  }

  var defaultLabels = {
    label_col: "Item",
    margin_products: "Margin products",
    other_revenue: "Other revenue",
    other_revenue_not_discountable: "Other revenue (not discountable)",
    total: "Total",
    subtotal: "Subtotal",
    margin: "Margin",
    discount: "Discount (fixed amount or %)",
    margin_after_discount: "Margin after discount",
    selling_price: "Selling price",
    info: "Info",
    below_minimum_margin: "Below minimum margin ({min}%)",
  };

  document.addEventListener("DOMContentLoaded", function () {
    var info = document.getElementById("live-marge-info");
    if (info) {
      var fieldset = info.closest("fieldset");
      if (fieldset && !fieldset.querySelector(".prijs-marge-kolommen")) {
        var rows = Array.prototype.slice.call(fieldset.querySelectorAll(".form-row"));
        if (rows.length >= 4) {
          var wrapper = document.createElement("div");
          wrapper.className = "prijs-marge-kolommen";
          wrapper.style.cssText = "display:flex;flex-wrap:nowrap;gap:2rem;align-items:flex-start;margin-top:1rem;min-width:900px;";
          var left = document.createElement("div");
          left.style.cssText = "flex:0 0 auto;width:280px;";
          var right = document.createElement("div");
          right.style.cssText = "flex:0 0 auto;width:600px;";
          for (var i = 0; i < 3; i++) left.appendChild(rows[i]);
          right.appendChild(rows[3]);
          wrapper.appendChild(left);
          wrapper.appendChild(right);
          rows[0].parentNode.insertBefore(wrapper, rows[0]);
          fieldset.style.overflowX = "auto";
        }
      }
    }

    var typeEl = document.getElementById("id_offer_type");
    if (!typeEl) return;

    var discountAmountEl = document.getElementById("id_discount_amount");
    var discountPercEl = document.getElementById("id_discount_percentage");

    var ds = typeEl.dataset || {};
    var minMargin = parseFloat(ds.minMargin || ds.minMarge || "0") || 0;
    var currency = (ds.currency || ds.valuta || "EUR").trim();

    function findRow(el) {
      if (!el) return null;
      return el.closest(".form-row") || el.parentNode;
    }
    var discountAmountRow = findRow(discountAmountEl);
    var discountPercRow = findRow(discountPercEl);

    var info = document.getElementById("live-margin-info") || document.getElementById("live-marge-info");
    if (!info) return;

    var labelSource = getMarginLabels();
    function L(key) {
      return labelSource[key] || defaultLabels[key];
    }

    var productPrices = getProductPrices();

    function parseVal(input) {
      if (!input) return 0;
      var v = (input.value || "").replace(",", ".").trim();
      var n = parseFloat(v);
      return isNaN(n) ? 0 : n;
    }

    function formatAmount(n) {
      var sign = n < 0 ? "-" : "";
      n = Math.abs(n);
      var s = n.toFixed(2);
      var parts = s.split(".");
      var intPart = parts[0];
      var frac = parts[1];
      var withThousands = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      var formattedNumber = sign + withThousands + "," + frac;
      return (currency ? currency + " " : "") + formattedNumber;
    }

    function updateVisibility(type) {
      if (discountAmountRow) discountAmountRow.style.display = type === "discount_amount" ? "" : "none";
      if (discountPercRow) discountPercRow.style.display = type === "discount_percentage" ? "" : "none";
      var visibleRow = type === "discount_amount" ? discountAmountRow : discountPercRow;
      if (visibleRow) {
        var lab = visibleRow.querySelector("label");
        var opt = typeEl.options[typeEl.selectedIndex];
        if (lab && opt) lab.textContent = opt.text.trim() + (lab.classList.contains("required") ? " *" : "");
      }
    }

    function getLiveTotals() {
      var container = document.querySelector(".inline-group[data-inline-type='tabular']");
      if (!container) {
        return {
          original: parseFloat(ds.original || "0") || 0,
          cost: parseFloat(ds.cost || "0") || 0,
          salesMargin: 0,
          costMargin: 0,
          otherRevenue: 0,
        };
      }
      var rows = container.querySelectorAll("tbody tr.form-row");
      var totalSales = 0;
      var totalCost = 0;
      var salesMargin = 0;
      var costMargin = 0;
      rows.forEach(function (row) {
        var productSelect = row.querySelector("select[name$='-product']");
        var productId = productSelect && productSelect.value ? productSelect.value : null;
        if (!productId) return;
        var prices = productPrices[productId];
        if (!prices) return;
        var mp = prices.margin_product !== false;
        var v = parseFloat(prices.sales || "0") || 0;
        var i = parseFloat(prices.cost || "0") || 0;
        totalSales += v;
        totalCost += i;
        if (mp) {
          salesMargin += v;
          costMargin += i;
        }
        var optionsTd = row.querySelector("td.field-selected_options");
        if (optionsTd) {
          var toSelect = optionsTd.querySelector(".selector-chosen select") || optionsTd.querySelector("select[id$='_to']");
          if (toSelect && toSelect.options) {
            for (var j = 0; j < toSelect.options.length; j++) {
              var optionId = toSelect.options[j].value;
              var optionPrices = productPrices[optionId];
              if (optionPrices) {
                var ov = parseFloat(optionPrices.sales || "0") || 0;
                var oi = parseFloat(optionPrices.cost || "0") || 0;
                totalSales += ov;
                totalCost += oi;
                if (optionPrices.margin_product !== false) {
                  salesMargin += ov;
                  costMargin += oi;
                }
              }
            }
          }
        }
      });
      var otherRevenue = totalSales - salesMargin;
      return {
        original: totalSales,
        cost: totalCost,
        salesMargin: salesMargin,
        costMargin: costMargin,
        otherRevenue: otherRevenue,
      };
    }

    function recalc() {
      var totals = getLiveTotals();
      var salesMargin = totals.salesMargin;
      var costMargin = totals.costMargin;
      var otherRevenue = totals.otherRevenue;

      var type = typeEl.value;
      updateVisibility(type);

      var marginPartAfterDiscount = salesMargin;
      if (type === "discount_amount") {
        var kb = parseVal(discountAmountEl);
        marginPartAfterDiscount = Math.max(salesMargin - kb, 0);
      } else if (type === "discount_percentage") {
        var kp = parseVal(discountPercEl);
        var factor = 1 - kp / 100;
        if (factor < 0) factor = 0;
        marginPartAfterDiscount = salesMargin * factor;
      }
      var offerPrice = marginPartAfterDiscount + otherRevenue;

      var marginBefore = null;
      var marginAfter = null;
      var marginAfterText = "";
      var minText = "";
      if (costMargin > 0) {
        marginBefore = ((salesMargin - costMargin) / costMargin) * 100;
        marginAfter = ((marginPartAfterDiscount - costMargin) / costMargin) * 100;
        if (isFinite(marginAfter)) {
          marginAfterText = marginAfter.toFixed(1).replace(".", ",") + " %";
          if (minMargin && marginAfter < minMargin) {
            minText = L("below_minimum_margin").replace("{min}", minMargin.toFixed(1).replace(".", ","));
          }
        }
      }

      var discountLabel = "—";
      if (type === "discount_amount") {
        var kb = parseVal(discountAmountEl);
        if (kb > 0) discountLabel = formatAmount(kb);
      } else if (type === "discount_percentage") {
        var kp = parseVal(discountPercEl);
        if (kp > 0) discountLabel = kp.toFixed(1).replace(".", ",") + " %";
      }

      var subtotal = salesMargin + otherRevenue;
      var tableStyle =
        "font-size:13px; border-collapse:collapse; min-width:520px; max-width:620px; width:100%;";
      var thStyle =
        "padding:4px 8px 4px 0; font-weight:600; border-bottom:1px solid #eee;";
      var thStyleRight =
        "text-align:right; padding:4px 8px 4px 0; font-weight:600; border-bottom:1px solid #eee;";
      var tdStyle = "text-align:right; padding:4px 8px 4px 0; border-bottom:1px solid #eee;";
      var tdLabelStyle = "text-align:left; padding:4px 8px 4px 0; border-bottom:1px solid #eee;";

      var html =
        '<table style="' +
        tableStyle +
        '">' +
        "<thead><tr><th style='" +
        thStyle +
        " text-align:left;'>" + L("label_col") + "</th><th style='" +
        thStyleRight +
        "'>" + L("margin_products") + "</th><th style='" +
        thStyleRight +
        "'>" + L("other_revenue") + "</th><th style='" +
        thStyleRight +
        "'>" + L("total") + "</th><th style='" +
        thStyleRight +
        "'>" + L("info") + "</th></tr></thead>" +
        "<tbody>" +
        "<tr><td style='" +
        tdLabelStyle +
        "'>" + L("margin_products") + "</td><td style='" +
        tdStyle +
        "'>" +
        formatAmount(salesMargin) +
        "</td><td style='" +
        tdStyle +
        "'>—</td><td style='" +
        tdStyle +
        "'>" +
        formatAmount(salesMargin) +
        "</td><td style='" +
        tdStyle +
        "'></td></tr>" +
        "<tr><td style='" +
        tdLabelStyle +
        "'>" + L("other_revenue_not_discountable") + "</td><td style='" +
        tdStyle +
        "'>—</td><td style='" +
        tdStyle +
        "'>" +
        formatAmount(otherRevenue) +
        "</td><td style='" +
        tdStyle +
        "'>" +
        formatAmount(otherRevenue) +
        "</td><td style='" +
        tdStyle +
        "'></td></tr>" +
        "<tr><td style='" +
        tdLabelStyle +
        "'>" + L("subtotal") + "</td><td style='" +
        tdStyle +
        "'></td><td style='" +
        tdStyle +
        "'></td><td style='" +
        tdStyle +
        "'>" +
        formatAmount(subtotal) +
        "</td><td style='" +
        tdStyle +
        "'></td></tr>";
      if (costMargin > 0 && marginBefore !== null && isFinite(marginBefore)) {
        html +=
          "<tr><td style='" +
          tdLabelStyle +
          "'>" + L("margin") + "</td><td colspan='3' style='" +
          tdStyle +
          "'></td><td style='" +
          tdStyle +
          "'>" +
          marginBefore.toFixed(1).replace(".", ",") +
          " %</td></tr>";
      }
      html +=
        "<tr><td style='" +
        tdLabelStyle +
        "'>" + L("discount") + "</td><td style='" +
        tdStyle +
        "'>" +
        discountLabel +
        "</td><td style='" +
        tdStyle +
        "'>—</td><td style='" +
        tdStyle +
        "'></td><td style='" +
        tdStyle +
        "'></td></tr>";
      if (marginAfterText) {
        html +=
          "<tr><td style='" +
          tdLabelStyle +
          "'>" + L("margin_after_discount") + "</td><td colspan='3' style='" +
          tdStyle +
          "'></td><td style='" +
          tdStyle +
          "'>" +
          marginAfterText +
          "</td></tr>";
      }
      html +=
        "<tr><td style='" +
        tdLabelStyle +
        "'><strong>" + L("selling_price") + "</strong></td><td style='" +
        tdStyle +
        "'></td><td style='" +
        tdStyle +
        "'></td><td style='" +
        tdStyle +
        "'><strong>" +
        formatAmount(offerPrice) +
        "</strong></td><td style='" +
        tdStyle +
        "'></td></tr>" +
        "</tbody></table>";
      if (minText) {
        html += '<p style="margin-top:6px; color:#b91c1c; font-weight:600;">' + minText + "</p>";
        info.style.color = "";
      } else {
        info.style.color = "";
      }
      info.innerHTML = html;
    }

    [typeEl, discountAmountEl, discountPercEl].forEach(function (el) {
      if (!el) return;
      el.addEventListener("input", recalc);
      el.addEventListener("change", recalc);
    });

    var recalcDebounce = null;
    function scheduleRecalc() {
      if (recalcDebounce) clearTimeout(recalcDebounce);
      recalcDebounce = setTimeout(function () {
        recalcDebounce = null;
        recalc();
      }, 50);
    }

    var container = document.querySelector(".inline-group[data-inline-type='tabular']");
    if (container && !container._marginListenersAttached) {
      container._marginListenersAttached = true;
      container.addEventListener("change", function () {
        recalc();
      });
      container.addEventListener("click", function (e) {
        if (e.target.closest(".selector-add, .selector-remove, .selector-chooseall, .selector-clearall")) {
          setTimeout(recalc, 80);
        }
      });
      container.addEventListener("dblclick", function (e) {
        if (e.target.tagName === "OPTION") {
          setTimeout(recalc, 80);
        }
      });
    }

    window.addEventListener("load", function () {
      recalc();
      var cont = document.querySelector(".inline-group[data-inline-type='tabular']");
      if (!cont || typeof MutationObserver === "undefined") return;
      var toSelects = cont.querySelectorAll(".selector-chosen select, select[id$='_to']");
      toSelects.forEach(function (sel) {
        if (sel._marginObserved) return;
        sel._marginObserved = true;
        var observer = new MutationObserver(scheduleRecalc);
        observer.observe(sel, { childList: true, subtree: true });
      });
      var tbody = cont.querySelector("tbody");
      if (tbody) {
        var rowObserver = new MutationObserver(function () {
          scheduleRecalc();
          cont.querySelectorAll(".selector-chosen select, select[id$='_to']").forEach(function (sel) {
            if (sel._marginObserved) return;
            sel._marginObserved = true;
            var ob = new MutationObserver(scheduleRecalc);
            ob.observe(sel, { childList: true, subtree: true });
          });
        });
        rowObserver.observe(tbody, { childList: true, subtree: true });
      }
    });

    var addButton = document.querySelector(".add-row a");
    if (addButton) {
      addButton.addEventListener("click", function () {
        setTimeout(recalc, 400);
      });
    }

    updateVisibility(typeEl.value);
    recalc();
  });
})();
