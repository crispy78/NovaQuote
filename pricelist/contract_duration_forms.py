"""Forms for contract duration management (proposal maintenance periods)."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ContractDuration


class ContractDurationForm(forms.ModelForm):
    """Edit contract duration rows used on the proposal page."""

    class Meta:
        model = ContractDuration
        fields = [
            "name",
            "duration_months",
            "hardware_fee_percentage",
            "visits_per_contract",
            "is_active",
            "hardware_fee_basis",
            "labour_unit_basis",
            "labour_calculation_mode",
            "include_hardware_fee_in_contract",
            "include_labour_in_contract",
            "override_time_per_product_minutes",
            "override_minimum_visit_minutes",
            "override_hourly_rate",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base = (
            "w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
            "focus:ring-2 focus:ring-[var(--brand)] focus:border-[var(--brand)]"
        )
        cb = "rounded border-slate-300 text-[var(--brand)] focus:ring-[var(--brand)] shrink-0 mt-1 h-4 w-4"
        for fname in self.fields:
            w = self.fields[fname].widget
            if fname in ("is_active", "include_hardware_fee_in_contract", "include_labour_in_contract"):
                w.attrs.setdefault("class", cb)
            elif hasattr(w, "attrs"):
                w.attrs.setdefault("class", base)
        for fname in ("hardware_fee_percentage", "visits_per_contract"):
            self.fields[fname].widget.attrs.setdefault("step", "0.01")
        for fname in (
            "override_time_per_product_minutes",
            "override_minimum_visit_minutes",
            "override_hourly_rate",
        ):
            self.fields[fname].widget.attrs.setdefault("step", "0.01")
        self.fields["duration_months"].widget.attrs.setdefault("min", "1")
