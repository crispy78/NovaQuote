;(function () {
  function getProductIdsWithOptions() {
    var el = document.getElementById("product-ids-with-options");
    if (!el || !el.textContent) return [];
    try {
      var arr = JSON.parse(el.textContent);
      return Array.isArray(arr) ? arr.map(Number) : [];
    } catch (e) {
      return [];
    }
  }

  function getProductOptionsMap() {
    var el = document.getElementById("product-options-map");
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent) || {};
    } catch (e) {
      return {};
    }
  }

  function getProductIdFromRow(row) {
    var select = row.querySelector("select[name$='-product']");
    if (select && select.value) return parseInt(select.value, 10);
    var hidden = row.querySelector("input[name$='-product']");
    if (hidden && hidden.value) return parseInt(hidden.value, 10);
    return null;
  }

  function getFromSelect(optionsTd) {
    return (
      optionsTd.querySelector(".selector-available select") ||
      optionsTd.querySelector("select[id$='_from']") ||
      optionsTd.querySelector("select")
    );
  }

  function getToSelect(optionsTd) {
    return (
      optionsTd.querySelector(".selector-chosen select") ||
      optionsTd.querySelector("select[id$='_to']")
    );
  }

  function getChosenIds(optionsTd) {
    var toSelect = getToSelect(optionsTd);
    if (!toSelect || !toSelect.options) return [];
    var ids = [];
    for (var i = 0; i < toSelect.options.length; i++) {
      ids.push(String(toSelect.options[i].value));
    }
    return ids;
  }

  function getCheckedOptionIds(optionsTd) {
    var inputs = optionsTd.querySelectorAll("input[name*='selected_options']:checked");
    var ids = [];
    for (var i = 0; i < inputs.length; i++) {
      ids.push(String(inputs[i].value));
    }
    return ids;
  }

  function getSelectedOptionsFieldName(row) {
    var select = row.querySelector("select[name$='-product']");
    if (select && select.name) return select.name.replace(/-product$/, "-selected_options");
    var existing = row.querySelector("input[name*='selected_options']");
    if (existing && existing.name) return existing.name;
    return null;
  }

  function clearOptionsCell(optionsTd) {
    if (!optionsTd) return;
    optionsTd.innerHTML = "";
  }

  function fillOptionsCheckboxes(row, productId, productOptionsMap) {
    var optionsTd = row.querySelector("td.field-selected_options");
    if (!optionsTd) return;
    var options = productOptionsMap[String(productId)] || productOptionsMap[productId];
    var fieldName = getSelectedOptionsFieldName(row);
    if (!fieldName) return;

    var checkedIds = getCheckedOptionIds(optionsTd);
    var ul = document.createElement("ul");
    ul.style.listStyle = "none";
    ul.style.margin = "0";
    ul.style.padding = "0";

    if (options && options.length > 0) {
      options.forEach(function (opt) {
        var idStr = String(opt.id);
        var li = document.createElement("li");
        var label = document.createElement("label");
        var input = document.createElement("input");
        input.type = "checkbox";
        input.name = fieldName;
        input.value = idStr;
        if (checkedIds.indexOf(idStr) !== -1) input.checked = true;
        label.appendChild(input);
        label.appendChild(document.createTextNode(" " + (opt.label || idStr)));
        li.appendChild(label);
        ul.appendChild(li);
      });
    }

    optionsTd.innerHTML = "";
    optionsTd.appendChild(ul);
  }

  function fillOptionsSelect(row, productId, productOptionsMap) {
    var optionsTd = row.querySelector("td.field-selected_options");
    if (!optionsTd) return;
    var fromSelect = getFromSelect(optionsTd);
    if (!fromSelect) return;
    var options = productOptionsMap[String(productId)] || productOptionsMap[productId];
    if (!options || options.length === 0) return;
    var chosenIds = getChosenIds(optionsTd);
    var cacheId = fromSelect.id;
    if (!window.SelectBox || !cacheId) return;
    if (!window.SelectBox.cache[cacheId]) window.SelectBox.cache[cacheId] = [];
    var fromValues = {};
    for (var i = 0; i < fromSelect.options.length; i++) {
      fromValues[fromSelect.options[i].value] = true;
    }
    options.forEach(function (opt) {
      var idStr = String(opt.id);
      if (chosenIds.indexOf(idStr) !== -1) return;
      if (fromValues[idStr]) return;
      fromValues[idStr] = true;
      var option = document.createElement("option");
      option.value = idStr;
      option.textContent = opt.label;
      fromSelect.appendChild(option);
      window.SelectBox.add_to_cache(cacheId, { value: idStr, text: opt.label, displayed: 1 });
    });
  }

  function updateOptionsVisibility() {
    var productOptionsMap = getProductOptionsMap();
    var container = document.querySelector(".inline-group[data-inline-type='tabular']");
    if (!container) return;

    var rows = container.querySelectorAll("tbody tr.form-row");
    rows.forEach(function (row) {
      var optionsTd = row.querySelector("td.field-selected_options");
      if (!optionsTd) return;

      var productId = getProductIdFromRow(row);
      var hasSelectWidget = getFromSelect(optionsTd) !== null;
      var options = productId && (productOptionsMap[String(productId)] || productOptionsMap[productId]);

      optionsTd.style.display = "";

      if (productId && options && options.length > 0) {
        if (hasSelectWidget) {
          fillOptionsSelect(row, productId, productOptionsMap);
        } else {
          fillOptionsCheckboxes(row, productId, productOptionsMap);
        }
      } else {
        clearOptionsCell(optionsTd);
      }
    });
  }

  function init() {
    updateOptionsVisibility();
    setTimeout(updateOptionsVisibility, 350);
    setTimeout(updateOptionsVisibility, 750);
    window.addEventListener("load", function () {
      updateOptionsVisibility();
    });

    var container = document.querySelector(".inline-group[data-inline-type='tabular']");
    if (container) {
      container.addEventListener("change", function (e) {
        var target = e.target;
        if (
          target &&
          target.name &&
          (target.name.indexOf("-product") !== -1 || target.name.indexOf("selected_options") !== -1)
        ) {
          if (target.name.indexOf("-product") !== -1) {
            setTimeout(updateOptionsVisibility, 50);
          }
        }
      });
    }

    var addButton = document.querySelector(".add-row a");
    if (addButton) {
      addButton.addEventListener("click", function () {
        setTimeout(updateOptionsVisibility, 500);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
