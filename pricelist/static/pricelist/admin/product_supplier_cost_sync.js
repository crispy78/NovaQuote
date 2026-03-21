/**
 * On Product admin change/add: mirror cost_price from the preferred Product supplier offer
 * row into the main Product cost_price field while editing (before save).
 */
(function () {
    "use strict";

    function totalFormsCount() {
        var el = document.querySelector('input[name="product_suppliers-TOTAL_FORMS"]');
        return el ? parseInt(el.value, 10) || 0 : 0;
    }

    function isRowDeleted(index) {
        var del = document.querySelector('input[name="product_suppliers-' + index + '-DELETE"]');
        return del && del.checked;
    }

    /** Prefer the row marked is_preferred; else first non-deleted inline row. */
    function getSourceRowIndex() {
        var n = totalFormsCount();
        var i;
        var preferred = [];
        for (i = 0; i < n; i++) {
            if (isRowDeleted(String(i))) continue;
            var pref = document.querySelector('input[name="product_suppliers-' + i + '-is_preferred"]');
            if (pref && pref.checked) {
                preferred.push(String(i));
            }
        }
        if (preferred.length > 0) {
            return preferred[0];
        }
        for (i = 0; i < n; i++) {
            if (!isRowDeleted(String(i))) {
                return String(i);
            }
        }
        return null;
    }

    function mainCostField() {
        return document.getElementById("id_cost_price");
    }

    function syncMainCostFromOffers() {
        var main = mainCostField();
        if (!main) return;
        var idx = getSourceRowIndex();
        if (idx === null) return;
        var inlineCost = document.querySelector('input[name="product_suppliers-' + idx + '-cost_price"]');
        if (!inlineCost) return;
        main.value = inlineCost.value;
    }

    function inlineIndexFromCostName(name) {
        var m = /^product_suppliers-(\d+)-cost_price$/.exec(name);
        return m ? m[1] : null;
    }

    function onDelegatedInputOrChange(ev) {
        var t = ev.target;
        if (!t || !t.name) return;
        var main = mainCostField();
        if (!main) return;

        if (t.name.indexOf("product_suppliers-") === 0 && t.name.endsWith("-cost_price")) {
            var idx = inlineIndexFromCostName(t.name);
            if (idx === null) return;
            var source = getSourceRowIndex();
            if (source === idx) {
                main.value = t.value;
            }
            return;
        }

        if (t.name.indexOf("product_suppliers-") === 0 && t.name.endsWith("-is_preferred")) {
            syncMainCostFromOffers();
            return;
        }

        if (t.name.indexOf("product_suppliers-") === 0 && t.name.endsWith("-DELETE")) {
            syncMainCostFromOffers();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    function init() {
        if (!mainCostField()) return;
        if (!document.querySelector('input[name="product_suppliers-TOTAL_FORMS"]')) return;

        document.addEventListener("input", onDelegatedInputOrChange);
        document.addEventListener("change", onDelegatedInputOrChange);
    }
})();
